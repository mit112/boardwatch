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
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.normalize import content_hash
from boardwatch.core.settings import Settings
from boardwatch.store.applications import create_application
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import save_profile
from boardwatch.store.queue_state import mark_job_reported, mark_job_skipped
from boardwatch.store.tables import artifacts, companies, jobs, posting_versions, postings

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
    # Every annotation points at a row that is actually on the slate. **This holds because this
    # fixture has NO standing leads (D-439) — it is not the general invariant it reads as.** Once
    # the cap is seeded from the queue the blocker may be a lead delivered weeks ago and absent
    # from `visible` entirely; `test_slate_capped_by_names_the_STANDING_lead_when_that_is_the_
    # blocker` pins that case. Narrowed here rather than deleted, because within a run the
    # annotation must still resolve on the slate.
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


# ------------------------------------------------- the cap across RUNS, not just within one (D-439)


def _delivered_by_a_PRIOR_run(
    engine: Engine, posting_id: int, *, at: datetime = NOW
) -> int:
    """Put `posting_id` in the standing queue the way a previous run leaves it.

    **Both halves are required and the test is vacuous without the second.** The artifact is what
    puts a lead in the queue; the `built` disposition is what stops it ranking again. Deliver
    without it and the lead is still a candidate in the next ranking, so the ordinary PER-RUN cap
    fires on the pair and the test passes whether or not the cap is seeded from the queue — which
    is exactly what a first version of these tests did, caught by mutation.
    """
    with engine.begin() as conn:
        # `.first()` on a DESC order, not `.one()`: a posting may carry several versions, and the
        # current delivery is against the newest.
        version_id = int(
            conn.execute(
                posting_versions.select()
                .where(posting_versions.c.posting_id == posting_id)
                .order_by(posting_versions.c.id.desc())
            ).first().id
        )
        conn.execute(insert(artifacts).values(
            posting_version_id=version_id, kind="resume_tailored",
            uri=f"/out/{posting_id}.typ", generator="boardwatch.tailor",
            media_type="text/x-typst", meta_json={}, created_at=at, run_id=None,
        ))
        job_id = int(
            conn.execute(postings.select().where(postings.c.id == posting_id)).one().job_id
        )
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built", policy_version="v1", now=NOW,
        )
        return job_id


def test_a_lead_already_standing_in_the_queue_caps_its_byte_identical_twin(env: Path) -> None:
    """The defect D-345 could not see, because it reasoned about a slate and not about a pile.

    Its cap DEFERS rather than drops — "a capped row is never recorded `seen`, so it ranks again on
    the very next run". Scoped to one call, that means the group delivers its next member the next
    day whether or not the owner ever looked at the first. Over runs it accumulates: measured on the
    live store, **49 exact-key groups holding 84 redundant standing leads**, one delivering on six
    consecutive runs, every run respecting the cap.

    So the cap is seeded from the standing queue. The second copy is withheld while the first is
    still waiting, and the assertion is on `hidden_slate_cap` as well as the slate, because a
    version that simply dropped the row would pass an assertion on `visible` alone.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    _delivered_by_a_PRIOR_run(engine, first)

    result = rank_open_postings(engine, _settings(env), limit=10)

    delivered = [p.posting_id for p in result.visible]
    assert second not in delivered, (
        "the twin of a lead already standing in the queue must not be delivered again"
    )
    assert result.hidden_slate_cap == 1, "it must be DEFERRED by the cap, not dropped elsewhere"
    # The standing lead does not re-rank at all — it carries a live `built` disposition — so the
    # ONLY thing the cap can be acting on is the queue seed. That is what makes this fail against
    # the per-run version.
    assert first not in delivered
    assert result.hidden_handled == 1


def test_the_deferral_ENDS_when_the_owner_actions_the_standing_lead(env: Path) -> None:
    """The re-entry path, and it is the half that makes this a deferral rather than suppression.

    D-345's quarantine needs no scheduled drain because the next run is the drain. Seeding the cap
    changes WHEN that fires, not whether: a second copy of a byte-identical JD becomes useful
    exactly when the owner has dealt with the first, and `applied` is what says so.

    Without this arm the change would be indistinguishable from permanent suppression of the twin —
    which is D-295, and is refused.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    job_id = _delivered_by_a_PRIOR_run(engine, first)

    held = rank_open_postings(engine, _settings(env), limit=10)
    assert held.hidden_slate_cap == 1 and second not in [p.posting_id for p in held.visible]

    with engine.begin() as conn:
        create_application(conn, job_id=job_id, status="applied", source="test")

    released = rank_open_postings(engine, _settings(env), limit=10)
    assert second in [p.posting_id for p in released.visible], (
        "once the standing lead is applied its twin must be delivered"
    )
    assert released.hidden_slate_cap == 0


def test_a_standing_lead_with_a_DIFFERENT_jd_caps_nothing(env: Path) -> None:
    """The control that keeps the seeded cap out of D-295 territory.

    `content_hash` is what separates one requisition multi-posted from two genuinely distinct ones.
    D-345 measured the looser `(company, title)` key wrongly collapsing run 125's two Evlo AI leads,
    which carry different hashes. Same company, same title, different JD: the standing lead must not
    withhold it.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "other-hash")])
    with engine.begin() as conn:
        first = int(conn.execute(postings.select().order_by(postings.c.id)).first().id)
        second = int(list(conn.execute(postings.select().order_by(postings.c.id)))[1].id)
    _delivered_by_a_PRIOR_run(engine, first)

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert [p.posting_id for p in result.visible] == [second]
    assert result.hidden_slate_cap == 0


def test_a_delivered_lead_that_is_still_rankable_does_not_cap_ITSELF(env: Path) -> None:
    """The seed carries standing posting ids, so a standing lead that is still a candidate would
    find its OWN id in the holders and defer itself forever.

    That window is real, not hypothetical. `rank_open_postings(..., record_surfaced=False)` is the
    pipeline's own call — the docstring on `surfaced_job_ids` says the disposition is recorded
    later, "at the point it genuinely takes one" — so between delivery and that write a lead has an
    artifact and no live disposition. A `seen` that ages out reopens the same window on purpose.

    Without the self-exclusion the lead is withheld by its own presence in the queue and the TTL
    that was supposed to bring it back never can. Delivered here WITHOUT a disposition, which is
    the only difference from the test above and the whole of the scenario.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        only = int(conn.execute(postings.select().order_by(postings.c.id)).first().id)
        version_id = int(
            conn.execute(
                posting_versions.select().where(posting_versions.c.posting_id == only)
            ).one().id
        )
        conn.execute(insert(artifacts).values(
            posting_version_id=version_id, kind="resume_tailored", uri="/out/x.typ",
            generator="boardwatch.tailor", media_type="text/x-typst", meta_json={},
            created_at=NOW, run_id=None,
        ))

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert [p.posting_id for p in result.visible] == [only], (
        "a lead must not be withheld by its own presence in the standing queue"
    )
    assert result.hidden_slate_cap == 0


def _close(engine: Engine, posting_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(postings.update().where(postings.c.id == posting_id).values(status="closed"))


def test_a_CLOSED_standing_lead_does_not_hold_its_twins_slot(env: Path) -> None:
    """The first of the two suppression bugs the first cut shipped (D-439).

    A closed lead is out of the queue and **can never be applied to or skipped**, so if it holds a
    cap slot it holds it forever and its still-OPEN byte-identical twin is never delivered again —
    with no reachable drain. `top_cmd`'s own guard comment is exactly this case: *"the cost of
    firing wrongly is a real lead nobody ever sees."*

    **The rule underneath: liveness is a property of the POSTING, content is a property of the
    JOB.** The closed lead's twin may be open — same bytes, different liveness — which is D-432's
    buried-live-requisition bug arriving from the other direction. That is why `closed` is excluded
    and `ineligible` is not.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    _delivered_by_a_PRIOR_run(engine, first)
    _close(engine, first)

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert second in [p.posting_id for p in result.visible], (
        "a closed standing lead must not withhold its still-open twin"
    )
    assert result.hidden_slate_cap == 0


def test_a_REPORTED_standing_lead_does_not_hold_its_twins_slot(env: Path) -> None:
    """The second suppression bug, and the worse one.

    A report says "this looks wrongly-eligible, hold it for investigation". The owner will by
    definition never apply to it, and it is already hidden from the web queue, so **neither release
    condition can ever fire.** Holding a slot on it is permanent suppression of a distinct posting —
    D-295 by accident, which is what D-439 exists to avoid.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    job_id = _delivered_by_a_PRIOR_run(engine, first)
    with engine.begin() as conn:
        mark_job_reported(conn, job_id=job_id, at=NOW)

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert second in [p.posting_id for p in result.visible]
    assert result.hidden_slate_cap == 0


def test_a_SKIPPED_standing_lead_releases_its_twin_too(env: Path) -> None:
    """The `skipped` half of the release condition, pinned separately from `applied`.

    Without this, deleting `or job_id in skipped` from the seed leaves every other test green and a
    skipped lead's twin is withheld forever with nothing failing. A mutation reported as one is two.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    job_id = _delivered_by_a_PRIOR_run(engine, first)

    held = rank_open_postings(engine, _settings(env), limit=10)
    assert held.hidden_slate_cap == 1 and second not in [p.posting_id for p in held.visible]

    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_id, at=NOW)

    released = rank_open_postings(engine, _settings(env), limit=10)
    assert second in [p.posting_id for p in released.visible]
    assert released.hidden_slate_cap == 0


def test_a_NBSP_body_cannot_be_capped_against_a_body_less_standing_lead(env: Path) -> None:
    """The reachable half of the empty-body guard, and the reason `content_hash != ""` was not it.

    **The two guards use different definitions of empty.** `top_cmd` asks SQLite
    `trim(body_text, " \\t\\n\\r\\f\\v")`, which does NOT strip U+00A0; `content_hash` normalises
    with Python's Unicode-aware `\\s`, which does. So a JD that is only `&nbsp;` after extraction
    passes `not row.body_empty`, **gets a slate key**, and hashes to the empty digest — where a
    body-less standing lead would be waiting for it. All 245 body-less postings live share that one
    digest, so the collision is with every one of them at the same company and title.

    The seed therefore refuses the empty digest outright. `content_hash != ""` could not: the column
    is NOT NULL and a hash is always 64 hex chars, so it excluded nothing at all.
    """
    # DERIVED from the body the fixture writes, never a literal: if `normalize_body`'s whitespace
    # class ever stopped being Unicode-aware, production would stop collapsing nbsp and the guard
    # would go dead — and a hard-coded digest would keep this test green while it happened.
    nbsp_hash = content_hash("\u00a0")
    assert nbsp_hash == content_hash(""), "nbsp must normalise to the empty digest"
    engine = _seed(
        env,
        [("cgs-federal", TITLE, nbsp_hash), ("cgs-federal", TITLE, nbsp_hash)],
        body="\u00a0",
    )
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    _delivered_by_a_PRIOR_run(engine, first)

    result = rank_open_postings(engine, _settings(env), limit=10, include_zero_signal=True)

    assert second in [p.posting_id for p in result.visible], (
        "the empty digest must never become a slate key a real candidate can collide with"
    )
    assert result.hidden_slate_cap == 0


def test_the_seed_keys_on_the_DELIVERED_version_not_the_posting_s_current_hash(env: Path) -> None:
    """`scan/apply.py` rewrites `postings.content_hash` in place on a revision; the owner's queue
    renders the FROZEN `posting_versions.body_text`.

    The cap's claim is that a byte-identical JD is *already in front of the owner*. What they were
    given is the frozen body, so the seed must key on it — otherwise a revision silently moves the
    claim onto text they have never seen, in either direction.

    Here the standing lead was delivered at `jd-hash` and its posting has since been revised to
    `revised-hash`. The candidate carries `jd-hash`: the JD the owner actually holds. It must be
    capped. Against the mutable column the seed would hold `revised-hash` and the candidate would
    ship as a second copy of a JD the owner already has.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    _delivered_by_a_PRIOR_run(engine, first)
    with engine.begin() as conn:  # the posting is revised AFTER delivery; the version is frozen
        conn.execute(
            postings.update().where(postings.c.id == first).values(content_hash="revised-hash")
        )

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert second not in [p.posting_id for p in result.visible], (
        "the cap must key on the JD the owner was actually given, not the posting's current hash"
    )
    assert result.hidden_slate_cap == 1


def test_a_body_less_standing_lead_holds_NO_slot(env: Path) -> None:
    """The guard the first cut only claimed to have. `content_hash != ""` was a tautology — the
    column is NOT NULL and a hash is always 64 hex chars — so a body-less standing lead seeded the
    **empty digest** as a slate key and would collide every other body-less posting at the same
    company and title. All 245 body-less postings live share that one digest.
    """
    empty = content_hash("")
    engine = _seed(env, [("cgs-federal", TITLE, empty), ("cgs-federal", TITLE, empty)], body="")
    assert empty == content_hash(""), "derived, not written down"
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    _delivered_by_a_PRIOR_run(engine, first)

    result = rank_open_postings(
        engine, _settings(env), limit=10, include_zero_signal=True
    )

    assert second in [p.posting_id for p in result.visible], (
        "an empty JD must not become a slate key that collides every body-less posting"
    )
    assert result.hidden_slate_cap == 0


def test_slate_capped_by_names_the_STANDING_lead_when_that_is_the_blocker(env: Path) -> None:
    """`slate_capped_by` has to stay traceable now that the blocker may not be in this output.

    The existing invariant test asserts `{p.slate_capped_by} <= survivors` and stays green only
    because its fixture has no standing leads — after the seed, the blocker can be a lead delivered
    weeks ago and absent from `visible` entirely. That is the honest cost of seeding the cap; the
    alternative is a cap that cannot say what blocked a row.

    So the field is pinned to name the STANDING posting, which is a real id the reader can look up.
    Without this, an implementation that left it `None` when the blocker is off-slate would satisfy
    every other test here and silently make the cap unauditable.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    _delivered_by_a_PRIOR_run(engine, first)

    shown = rank_open_postings(engine, _settings(env), limit=10, include_slate_cap=True)
    capped = [p for p in shown.visible if p.slate_capped_by is not None]

    assert [p.posting_id for p in capped] == [second]
    assert capped[0].slate_capped_by == first, (
        "the cap must name the standing lead that blocked it, even though that lead is not in "
        "this output"
    )
    assert first not in {p.posting_id for p in shown.visible}




def test_the_two_deferrals_are_counted_APART_not_folded_into_one_number(env: Path) -> None:
    """D-439 gave `hidden_slate_cap` two drain conditions and left it one number.

    A row capped by THIS RUN's slate returns tomorrow whatever the owner does. A row capped by a
    lead already in the queue returns only when they apply to or skip it. Reported as one total,
    a queue the owner has stopped draining looks identical to a busy run — the standing half
    climbs while the total holds, and nothing says so.

    Both directions are pinned here, so neither `standing == total` nor `standing == 0` survives:
    the first arm has no standing lead at all and the second is blocked by nothing else.
    """
    within_run = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    result = rank_open_postings(within_run, _settings(env), limit=10)
    assert result.hidden_slate_cap == 1
    assert result.hidden_slate_cap_standing == 0, (
        "a row displaced by this run's own slate returns on the next run and must not be "
        "reported as waiting on the owner"
    )


def test_a_row_capped_by_a_STANDING_lead_is_counted_as_waiting_on_the_owner(env: Path) -> None:
    """The other arm of the split, and the one that carries the operational signal.

    See `test_the_two_deferrals_are_counted_APART_not_folded_into_one_number` for why one number
    is not enough. Here the only blocker is a lead delivered by a previous run, so the deferral
    ends when the owner actions it and nothing the program does on its own will release it.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "jd-hash"), ("cgs-federal", TITLE, "jd-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    _delivered_by_a_PRIOR_run(engine, int(rows[0].id))

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert result.hidden_slate_cap == 1
    assert result.hidden_slate_cap_standing == 1, (
        "the blocker is in the queue, not on this slate, so the wait is on the owner"
    )


def test_slate_capped_by_names_the_MOST_RECENTLY_delivered_of_several_holders(env: Path) -> None:
    """Which holder gets named, when a key holds more than one standing lead.

    `slate_capped_by` renders to the operator as "same JD as <id>", so the id has to be one they
    can place. With several standing holders the seed's ordering decides which one that is, and
    ordering the seed on `postings.id` names whichever copy happens to carry the lowest row id —
    which may be a lead delivered a month ago, buried under everything since. **49 of the live
    store's exact-key groups hold more than one lead**, so this is the ordinary case.

    Delivery recency is the answer: name the copy the owner saw most recently. Here the OLDER
    delivery deliberately carries the LOWER posting id, so a seed ordered on `postings.id` would
    name it and this test would fail.
    """
    engine = _seed(
        env,
        [
            ("cgs-federal", TITLE, "jd-hash"),
            ("cgs-federal", TITLE, "jd-hash"),
            ("cgs-federal", TITLE, "jd-hash"),
        ],
    )
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    stale, recent, candidate = (int(row.id) for row in rows)
    _delivered_by_a_PRIOR_run(engine, stale, at=NOW - timedelta(days=30))
    _delivered_by_a_PRIOR_run(engine, recent, at=NOW)

    shown = rank_open_postings(engine, _settings(env), limit=10, include_slate_cap=True)
    capped = [p for p in shown.visible if p.slate_capped_by is not None]

    assert [p.posting_id for p in capped] == [candidate]
    assert capped[0].slate_capped_by == recent, (
        "with several standing holders the cap must name the one the owner saw most recently, "
        "not whichever carries the lowest posting id"
    )


def test_a_posting_delivered_TWICE_seeds_its_most_recent_version(env: Path) -> None:
    """The tie-break, and without it SQLite may emit either delivered version.

    A posting can carry more than one tailored artifact: delivered at run 100 against JD v1, its
    ledger disposition lapses, `scan/apply` revises the body, and it is delivered again at run 140
    against v2. The join then yields two rows for that posting, and a seed that keeps whichever
    comes first can hold **v1's hash — a JD the owner no longer has** — which is the exact failure
    the frozen hash exists to prevent.

    Ordering by `artifacts.created_at DESC` is the recency half of `_supersedes`; the liveness half
    is the `status == 'open'` filter. Here the candidate carries v2, the version the owner actually
    holds, and must be capped.
    """
    engine = _seed(env, [("cgs-federal", TITLE, "v2-hash"), ("cgs-federal", TITLE, "v2-hash")])
    with engine.begin() as conn:
        rows = list(conn.execute(postings.select().order_by(postings.c.id)))
    first, second = int(rows[0].id), int(rows[1].id)
    with engine.begin() as conn:
        current_version = int(
            conn.execute(
                posting_versions.select().where(posting_versions.c.posting_id == first)
            ).one().id
        )
        stale_version = int(conn.execute(insert(posting_versions).values(
            posting_id=first, content_hash="v1-hash", body_text=SAME_JD,
            captured_at=NOW - timedelta(days=30), capture_reason="new",
        )).inserted_primary_key[0])
        # An OLD delivery against v1 and the CURRENT one against v2. The stale version carries the
        # HIGHER row id, so a seed ordering on `postings.id` alone would pick exactly the wrong one.
        for version_id, at, uri in (
            (stale_version, NOW - timedelta(days=30), "/out/old.typ"),
            (current_version, NOW, "/out/new.typ"),
        ):
            conn.execute(insert(artifacts).values(
                posting_version_id=version_id, kind="resume_tailored", uri=uri,
                generator="boardwatch.tailor", media_type="text/x-typst", meta_json={},
                created_at=at, run_id=None,
            ))
        record_disposition(
            conn, int(rows[0].job_id), disposition="built", reason="lead_built",
            policy_version="v1", now=NOW,
        )

    result = rank_open_postings(engine, _settings(env), limit=10)

    assert second not in [p.posting_id for p in result.visible], (
        "the seed must hold the MOST RECENTLY delivered version's hash, not an older one"
    )
    assert result.hidden_slate_cap == 1
