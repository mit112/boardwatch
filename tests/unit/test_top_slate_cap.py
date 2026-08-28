"""The delivery slate cap: one lead per company, title and byte-identical JD per run (D-345).

**The gap this closes.** `exact_quad` — the only identity kind that suppresses — includes
`locations`. So one requisition posted to nine cities is nine `exact_quad` groups of one, and
dedup is structurally incapable of touching it no matter how complete the backfill is. Run 129
spent 9 of its 10 delivery slots on a single CGS Federal `ServiceNow Developer`: one
`company_id`, one `normalized_title`, one byte-identical `content_hash`, nine cities.

**What these tests pin, and what they deliberately do not.** They pin that the cap fires on that
exact shape, that the freed slot is REFILLED from further down the ranking rather than shrinking
the slate, that a same-title posting with a DIFFERENT JD is never capped, and that a capped lead
is not recorded `seen` so it ranks again next run. They do not assert that two capped postings
are the same job — the cap makes no such claim, which is the whole reason it is not D-295.

Every seeding shape here sets DISTINCT `locations_json`, because a shared location would let
`exact_quad` suppress the group first and the test would pass without the cap existing at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()
TITLE = "Backend Engineer"
# One byte-identical JD, the thing that makes the cap's claim falsifiable rather than a guess.
SAME_JD = "We are hiring a backend engineer."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Config dir == data dir, the same reason test_top_accounting.py does it: split, the
    # eligibility policy the ranker reads is not the one the test wrote.
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed(data_dir: Path, rows: Sequence[tuple[str, str, str]], *, body: str = SAME_JD) -> Engine:
    """One open posting per row of `(company_slug, title, content_hash)`.

    Explicit about all three key components on purpose: the cap keys on a 3-tuple, so a test
    that hid any part of it behind a flag could not show which component did the work.

    `locations_json` is unique per posting, so no two rows ever form an `exact_quad` group and
    dedup is out of the picture by construction. `posted_at` descends with row order, so the
    ranking is total and "which row won the slot" is a fact rather than a broken tie.
    """
    engine = get_engine(data_dir)
    ensure_schema(engine)
    company_ids: dict[str, int] = {}
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        for offset, (slug, title, content_hash) in enumerate(rows):
            if slug not in company_ids:
                company_ids[slug] = int(conn.execute(insert(companies).values(
                    name=slug.title(), provider="greenhouse", slug=slug,
                    source="user", watched=True,
                )).inserted_primary_key[0])
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_ids[slug], job_id=job_id,
                provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.casefold(),
                # Distinct per posting — see the docstring. This is what reproduces the
                # location-split shape instead of an exact_quad group.
                locations_json=[f"City {offset}"], remote_policy="onsite",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=content_hash,
                body_text=body,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash, body_text=body,
                captured_at=NOW, capture_reason="new",
            ))
    return engine


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _rank(
    data_dir: Path,
    rows: Sequence[tuple[str, str, str]],
    *,
    limit: int,
    body: str = SAME_JD,
    **kwargs: bool,
) -> RankedResults:
    engine = _seed(data_dir, rows, body=body)
    return rank_open_postings(engine, _settings(data_dir), limit=limit, **kwargs)


# Three postings of ONE requisition (run 129's shape), then two other companies' real leads.
# The trio is the most recent, so without a cap it takes all three slots and the two real
# leads fall below the cutoff.
RUN_129_SHAPE: list[tuple[str, str, str]] = [
    ("cgs-federal", TITLE, "jd-hash"),
    ("cgs-federal", TITLE, "jd-hash"),
    ("cgs-federal", TITLE, "jd-hash"),
    ("beta-corp", TITLE, "beta-hash"),
    ("gamma-corp", TITLE, "gamma-hash"),
]


def test_the_cap_frees_slots_and_refills_them_from_further_down(env: Path) -> None:
    """The discriminating test: it is about the slate that RESULTS, not just the count.

    Without the cap this returns three copies of one requisition and `hidden_below_cutoff == 2`
    — Beta and Gamma never ship. That is precisely run 129: 9 of 10 slots, one req. With it,
    the two freed slots are refilled, so the run delivers three DISTINCT employers at the same
    `limit`. Asserting the company set is what makes this fail against the broken version;
    asserting only `len(visible) == 3` would pass against both.
    """
    results = _rank(env, RUN_129_SHAPE, limit=3)
    assert results.hidden_slate_cap == 2
    assert [p.company for p in results.visible] == ["Cgs-Federal", "Beta-Corp", "Gamma-Corp"]
    # The slate did not shrink: the cap defers leads, it does not spend the day's capacity.
    assert len(results.visible) == 3
    # Nothing was beaten by rank — the two slots the trio would have taken were refilled.
    assert results.hidden_below_cutoff == 0


def test_the_same_title_with_a_different_jd_is_never_capped(env: Path) -> None:
    """Run 125's real shape, and the reason the key requires the hash.

    Its two Evlo AI `mobile engineer ios android` leads share a company and a normalized title
    but carry DIFFERENT content hashes — two genuinely distinct requisitions. A
    `(company, title)` key at N=1 drops one of them; this key must not.
    """
    results = _rank(
        env,
        [("evlo-ai", TITLE, "hash-a"), ("evlo-ai", TITLE, "hash-b")],
        limit=10,
    )
    assert results.hidden_slate_cap == 0
    assert len(results.visible) == 2


# SHA-256 of the empty string: the hash EVERY body-less posting carries. All 245 body-less
# open postings in the live corpus share it, which is why its presence proves nothing.
EMPTY_BODY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_a_body_less_posting_is_never_capped(env: Path) -> None:
    """The guard that separates the cap from a fabrication, on the REACHABLE shape.

    `postings.content_hash` is NOT NULL and is never empty, so "no hash" is not a case that can
    occur — an earlier version of this test asserted it and could not even be inserted. The real
    hazard is the opposite: every body-less posting hashes the EMPTY STRING, so two distinct
    body-less reqs from one company share a byte-identical `content_hash` while having no JD in
    common at all. The live corpus already holds six such `(company, title, hash)` groups,
    including a `software engineer frontend` pair. Capping them would drop a real lead and claim
    its JD matched.
    """
    results = _rank(
        env,
        [("acme", TITLE, EMPTY_BODY_HASH), ("acme", TITLE, EMPTY_BODY_HASH)],
        limit=10,
        body="",
    )
    assert results.hidden_slate_cap == 0
    assert len(results.visible) == 2


def test_two_companies_posting_the_same_jd_are_not_capped(env: Path) -> None:
    """`company_id` is in the key, and shared boilerplate across employers is not one req.

    This is the failure mode that refuted `(company_id, content_hash)` as a corpus key: 39.1%
    of its groups spanned more than one title. Here the reverse — one JD, two employers — must
    yield two leads.
    """
    results = _rank(
        env,
        [("acme", TITLE, "shared-hash"), ("beta-corp", TITLE, "shared-hash")],
        limit=10,
    )
    assert results.hidden_slate_cap == 0
    assert len(results.visible) == 2


def test_a_capped_lead_is_not_recorded_seen_so_it_ranks_again(env: Path) -> None:
    """The re-entry path, and the reason this cap needs no scheduled drain.

    A capped row must not reach `surfaced_job_ids`: recording it `seen` would suppress it for
    the TTL and the cap would become a silent one-way consumption of the queue, which CLAUDE.md
    forbids for every quarantine. Only the survivor is surfaced.
    """
    results = _rank(env, RUN_129_SHAPE, limit=3)
    assert results.hidden_slate_cap == 2
    # Three leads shipped, so exactly three jobs were surfaced — not five.
    assert len(results.surfaced_job_ids) == 3
    surfaced = set(results.surfaced_job_ids)
    assert len(surfaced) == 3


def test_the_drain_surfaces_a_capped_lead_annotated_with_its_survivor(env: Path) -> None:
    """A suppression that cannot be listed is a leak, so the bucket has to be inspectable.

    The annotation carries the survivor's posting_id, not a bare flag: a cap the operator
    cannot trace to the row that displaced it cannot be audited.
    """
    shown = _rank(env, RUN_129_SHAPE, limit=3, include_slate_cap=True)
    assert shown.hidden_slate_cap == 0
    capped = [p for p in shown.visible if p.slate_capped_by is not None]
    assert len(capped) == 2
    survivors = {p.posting_id for p in shown.visible if p.slate_capped_by is None}
    # Every annotation points at a row that is actually on the slate.
    assert {p.slate_capped_by for p in capped} <= survivors
    # Drained rows do not consume limit slots, so the drain returns more than `limit`.
    assert len(shown.visible) > 3


def test_every_considered_posting_still_lands_in_exactly_one_bucket(env: Path) -> None:
    """The reconciliation identity has to survive the new bucket (P0 item 3)."""
    results = _rank(env, RUN_129_SHAPE, limit=3)
    accounted = (
        len(results.visible)
        + results.skipped_not_new
        + results.hidden_hard_filter
        + results.hidden_non_swe
        + results.hidden_zero_signal
        + results.hidden_over_seniority
        + results.hidden_ineligible
        + results.hidden_below_cutoff
        + results.hidden_duplicate
        + results.hidden_slate_cap
    )
    assert results.considered == 5
    assert accounted == results.considered
