"""store.facet_queries: the evidence a mined facet is allowed to stand on.

Every row these two queries read is written by the PRODUCTION path in this file — `apply_board`
for the postings and their acquisition provenance, `record_disposition` for the delivered
verdict. Hand-inserted rows would let the write path move (a different `source_url`, a different
disposition name) while these stayed green, and the miner would go quietly blind. That is the
failure mode the fixture rule exists for: a green end-to-end test whose fixture sits still while
production churns.

No field's vocabulary appears below, for the same reason it does not appear in the module: if a
software word were ever needed to make one of these pass, the mechanism would have stopped being
generic where nothing else could catch it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from boardwatch.core.clock import utcnow
from boardwatch.core.models import RawPosting
from boardwatch.lanes.base import lane_snapshot
from boardwatch.lanes.linkedin import search_urls
from boardwatch.scan.apply import apply_board
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.facet_queries import delivered_postings, facet_trials
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import insert_run, upsert_lane_company
from boardwatch.store.tables import postings

# The adversarial facet pair, and it is adversarial BY DESIGN. Both are ordinary ward titles, and
# their search URLs are `keywords=ward%20b%20nurse` and `keywords=ward%2020b%20nurse`. Read as a
# LIKE pattern, the first matches the second: `%` is a wildcard and percent-encoding puts one in
# EVERY multi-word facet URL, so a SQL prefix match cannot decide which facet a provenance row
# belongs to. Only the literal per-row check can, and this pair is what makes the difference
# observable.
WILDCARD_COLLISION_FACETS = ("ward b nurse", "ward 20b nurse")


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _raw(posting_id: str, title: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=f"https://example.invalid/{posting_id}",
        locations=["Anywhere"],
        body_text=f"body for {posting_id}",
        raw_json={},
    )


def _acquire(engine: Engine, *, slug: str, url: str, raw: list[RawPosting]) -> list[int]:
    """Land postings through the real lane write path and return their posting ids."""
    with engine.begin() as conn:
        company_id = upsert_lane_company(conn, provider="linkedin", slug=slug, name=slug)
    apply_board(engine, lane_snapshot(raw, url), company_id, insert_run(engine), scan_kind="lane")
    with engine.connect() as conn:
        return [
            int(row.id)
            for row in conn.execute(
                select(postings.c.id)
                .where(postings.c.company_id == company_id)
                .order_by(postings.c.id)
            ).all()
        ]


def _build_lead(engine: Engine, posting_id: int, *, decided_at=None) -> None:
    with engine.begin() as conn:
        record_disposition(
            conn,
            _job_id(conn, posting_id),
            disposition="built",
            reason="lead_built",
            policy_version="test-policy",
            now=decided_at or utcnow(),
        )


def _surface_only(engine: Engine, posting_id: int) -> None:
    """A job the program SURFACED and never built a lead for — the other live disposition.

    Present so the built filter has something to refuse. A posting with no ledger row at all is
    excluded by the join alone, so a test built only from those would stay green with the
    disposition predicate deleted.
    """
    with engine.begin() as conn:
        record_disposition(
            conn,
            _job_id(conn, posting_id),
            disposition="seen",
            reason="surfaced",
            expires_at=utcnow() + timedelta(days=7),
            now=utcnow(),
        )


def _job_id(conn, posting_id: int) -> int:
    return int(
        conn.execute(select(postings.c.job_id).where(postings.c.id == posting_id)).scalar_one()
    )


# ---------------------------------------------------------------------------------------
# delivered_postings
# ---------------------------------------------------------------------------------------


def test_only_postings_the_program_built_a_lead_for_are_evidence(engine: Engine) -> None:
    """Measured on the live store, mining the wider `eligible` corpus instead would poison the
    lane outright: of 3,656 open eligible postings the strongest recurring titles were
    `sales agent` (169), `universal banker` (78) and `account executive` (84) — eligibility
    judges work authorization and experience, not whether the user wants the role. `built` is the
    end-of-line population that cleared ranking, the role gate and delivery.
    """
    url = search_urls(("registered nurse",))[0]
    kept, ignored = _acquire(
        engine,
        slug="mercy",
        url=url,
        raw=[_raw("1", "Perioperative Nurse"), _raw("2", "Sales Agent")],
    )
    _build_lead(engine, kept)
    _surface_only(engine, ignored)

    mined = delivered_postings(engine.connect(), since=utcnow() - timedelta(days=30))

    assert [row.title for row in mined] == ["Perioperative Nurse"]
    assert ignored not in {row.posting_id for row in mined}


def test_a_lead_decided_before_the_window_is_no_longer_evidence(engine: Engine) -> None:
    """The window is the drain the generation half owes: a title the user has moved on from
    ages out on its own, with no second mechanism needed to release it."""
    url = search_urls(("registered nurse",))[0]
    (posting_id,) = _acquire(engine, slug="mercy", url=url, raw=[_raw("1", "Perioperative Nurse")])
    _build_lead(engine, posting_id, decided_at=utcnow() - timedelta(days=45))

    assert delivered_postings(engine.connect(), since=utcnow() - timedelta(days=30)) == ()
    assert len(delivered_postings(engine.connect(), since=utcnow() - timedelta(days=60))) == 1


def test_the_raw_title_is_returned_and_not_the_identity_normalization(engine: Engine) -> None:
    """`postings.normalized_title` is written by the same `apply_board` call and is the wrong
    space to mine: it folds `+` to ` plus `, so a facet built from it asks for a string no
    posting contains. Both columns exist on the row this reads, so nothing but the query itself
    decides which one the miner sees.
    """
    url = search_urls(("registered nurse",))[0]
    (posting_id,) = _acquire(
        engine, slug="mercy", url=url, raw=[_raw("1", "C++ Instrumentation Technician")]
    )
    _build_lead(engine, posting_id)

    (row,) = delivered_postings(engine.connect(), since=utcnow() - timedelta(days=30))

    assert row.title == "C++ Instrumentation Technician"
    with engine.connect() as conn:
        stored = conn.execute(
            select(postings.c.normalized_title).where(postings.c.id == posting_id)
        ).scalar_one()
    assert stored == "c plus plus instrumentation technician"


# ---------------------------------------------------------------------------------------
# facet_trials
# ---------------------------------------------------------------------------------------


def test_a_facet_is_credited_with_the_postings_its_own_search_page_acquired(
    engine: Engine,
) -> None:
    """The credit comes from the store's `posting_version_sources` provenance, not from any
    lane's self-report — a component's own tally cannot verify itself."""
    first, second = search_urls(("registered nurse", "charge nurse"))
    _acquire(engine, slug="mercy", url=first, raw=[_raw("1", "A"), _raw("2", "B")])
    (delivered_id,) = _acquire(engine, slug="stjohn", url=second, raw=[_raw("3", "C")])
    _build_lead(engine, delivered_id)

    trials = facet_trials(
        engine.connect(), (first, second), since=utcnow() - timedelta(days=30)
    )

    assert trials[first].credited == 2
    assert trials[first].delivered == 0
    assert trials[second] == trials[second].__class__(credited=1, delivered=1)


def test_a_percent_encoded_facet_url_cannot_claim_another_facets_postings(
    engine: Engine,
) -> None:
    """WILDCARD_COLLISION_FACETS: crediting is decided by a LITERAL prefix, per row.

    `ward b nurse` acquired nothing; `ward 20b nurse` acquired two postings and delivered one.
    The SQL `LIKE` cannot make this call — every multi-word facet URL is percent-encoded, and
    `%` is a LIKE wildcard — so the credit is decided in Python, where `str.startswith` is
    literal. Drop that per-row check on the reasoning that the query already filtered, and the
    barren facet is handed the productive one's two postings and its delivered lead, and a facet
    that has never converted anything can never be pruned.
    """
    barren, productive = search_urls(WILDCARD_COLLISION_FACETS)
    ids = _acquire(engine, slug="mercy", url=productive, raw=[_raw("1", "A"), _raw("2", "B")])
    _build_lead(engine, ids[0])

    trials = facet_trials(
        engine.connect(), (barren, productive), since=utcnow() - timedelta(days=30)
    )

    assert barren not in trials
    assert trials[productive].credited == 2
    assert trials[productive].delivered == 1


def test_a_facet_that_acquired_nothing_is_absent_rather_than_zero(engine: Engine) -> None:
    """Never-searched and searched-with-nothing-to-show are different facts, and
    `surviving_mined_facets` must not read the first as the second — a zero row would prune a
    facet that has never run."""
    url = search_urls(("registered nurse",))[0]

    assert facet_trials(engine.connect(), (url,), since=utcnow() - timedelta(days=30)) == {}
    assert facet_trials(engine.connect(), (), since=utcnow() - timedelta(days=30)) == {}


def test_a_trial_older_than_the_window_no_longer_counts_against_a_facet(engine: Engine) -> None:
    """The drain the pruning half owes. A facet retired for converting nothing becomes eligible
    again once the trials that condemned it age out; a permanent quarantine with no re-entry
    path is the leak this repo refuses.
    """
    url = search_urls(("registered nurse",))[0]
    _acquire(engine, slug="mercy", url=url, raw=[_raw("1", "A")])

    assert facet_trials(engine.connect(), (url,), since=utcnow() - timedelta(days=30))[
        url
    ].credited == 1
    assert facet_trials(engine.connect(), (url,), since=utcnow() + timedelta(days=1)) == {}


def test_a_lead_built_before_the_window_still_counts_as_a_facets_conversion(
    engine: Engine,
) -> None:
    """The window bounds which TRIALS still count, never which conversions do. Expiring the
    credit while keeping the trial would manufacture a barren record for a facet that was never
    barren, and prune the one thing that worked."""
    url = search_urls(("registered nurse",))[0]
    (posting_id,) = _acquire(engine, slug="mercy", url=url, raw=[_raw("1", "A")])
    _build_lead(engine, posting_id, decided_at=utcnow() - timedelta(days=90))

    assert facet_trials(engine.connect(), (url,), since=utcnow() - timedelta(days=30))[
        url
    ].delivered == 1
