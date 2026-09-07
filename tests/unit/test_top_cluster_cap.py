"""The delivery cluster cap: at most `CLUSTER_CAP_PER_KEY` leads per company, title and
location on one slate (T73).

**The gap this closes.** `SLATE_CAP_PER_KEY` already caps `(company_id, normalized_title,
content_hash)` at 1, and the hash is what makes its claim falsifiable — equal hashes mean a
byte-identical JD. The shape it therefore cannot see is ONE OPENING EXPRESSED SEVERAL WAYS. Run
10 spent 5 of its 40 delivered slots on a single security-engineering cluster at one employer:
one company, one normalized title, one city, titles differing only in a word and a dash, and
five bodies of 3343 / 4321 / 3839 / 3938 / 2756 bytes. Five different hashes, so the exact-key
cap read five distinct requisitions and delivered all five.

**What these tests pin, and what they deliberately do not.** They pin that the cap fires on that
exact shape, that the freed slots are REFILLED from further down the ranking, that the withheld
rows are counted in their OWN bucket and are not recorded `seen`, that a byte-identical twin is
attributed to the exact-key cap instead, and that a large group spread over DIFFERENT locations
is untouched. They do not assert that two capped postings are the same job — a
`company_title_location` SUPPRESSOR was measured and refused (D-295), and this cap makes no
identity claim at all.

Every seeding shape here gives the cluster members DIFFERENT `content_hash` values, because
equal hashes would let the exact-key cap fire first and the test would pass without this cap
existing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.cli.top_cmd import (
    CLUSTER_CAP_PER_KEY,
    RankedResults,
    rank_open_postings,
)
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()

# The run-10 shape, synthesised: one normalized title, one city, five spellings of the display
# title, five different bodies. `normalized_title` is what the cap keys on, so the display
# titles differ here on purpose — a test that made them identical could not show which column
# did the work.
CLUSTER_TITLE = "security engineer"
DALLAS = ["Dallas, TX"]

# (company_slug, display_title, normalized_title, content_hash, body, locations)
Row = tuple[str, str, str, str, str, list[str] | None]


def _cluster(n: int, *, slug: str = "acme-bank", locations: list[str] | None = None) -> list[Row]:
    """`n` postings of ONE opening: same company, same normalized title, same place, n bodies.

    The bodies differ in LENGTH as well as content, mirroring the measured cluster — that is
    what gives each member its own `content_hash` and puts the exact-key cap out of the picture.
    """
    return [
        (
            slug,
            f"Security Engineer, Engineering{' Division' if i % 2 else ''} - Dallas",
            CLUSTER_TITLE,
            f"cluster-hash-{i}",
            f"We are hiring a security engineer. {'detail ' * (i + 1)}",
            list(DALLAS) if locations is None else locations,
        )
        for i in range(n)
    ]


OTHER_LEADS: list[Row] = [
    ("beta-corp", "Backend Engineer", "backend engineer", "beta-hash", "Beta JD.", ["Austin, TX"]),
    ("gamma-corp", "Backend Engineer", "backend engineer", "gamma-hash", "Gamma JD.", ["Reno, NV"]),
]


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Config dir == data dir, for the reason test_top_slate_cap.py does it: split, the
    # eligibility policy the ranker reads is not the one the test wrote.
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed(data_dir: Path, rows: Sequence[Row]) -> Engine:
    """One open posting per row. `posted_at` descends with row order, so the ranking is total
    and "which row won the slot" is a fact rather than a broken tie."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    company_ids: dict[str, int] = {}
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        for offset, (slug, title, normalized, hashed, body, locations) in enumerate(rows):
            if slug not in company_ids:
                company_ids[slug] = int(conn.execute(insert(companies).values(
                    name=slug.replace("-", " ").title(), provider="greenhouse", slug=slug,
                    source="user", watched=True,
                )).inserted_primary_key[0])
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_ids[slug], job_id=job_id,
                provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=normalized,
                locations_json=locations, remote_policy="onsite",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=hashed, body_text=body,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=hashed, body_text=body,
                captured_at=NOW, capture_reason="new",
            ))
    return engine


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _rank(
    data_dir: Path, rows: Sequence[Row], *, limit: int, **kwargs: bool
) -> RankedResults:
    engine = _seed(data_dir, rows)
    return rank_open_postings(engine, _settings(data_dir), limit=limit, **kwargs)


def _job_ids(data_dir: Path) -> dict[int, int]:
    """posting_id -> job_id, so a test can say WHICH leads were recorded `seen`."""
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        return {
            int(row.id): int(row.job_id)
            for row in conn.execute(select(postings.c.id, postings.c.job_id)).all()
        }


# ---------------------------------------------------------------------- the cap itself

RUN_10_SHAPE: list[Row] = [*_cluster(5), *OTHER_LEADS]


def test_five_ways_of_writing_one_opening_take_two_slots_not_five(env: Path) -> None:
    """The discriminating test, and it is about the slate that RESULTS, not just a count.

    Without the cap this returns four copies of one opening and the two real leads fall below
    the cutoff — precisely run 10, at a smaller scale. With it, the three freed slots are
    refilled, so the run delivers three DISTINCT employers at the same `limit`. Asserting the
    company sequence is what makes this fail against the old code; `len(visible) == 4` passes
    against both.
    """
    results = _rank(env, RUN_10_SHAPE, limit=4)
    assert [p.company for p in results.visible] == [
        "Acme Bank", "Acme Bank", "Beta Corp", "Gamma Corp",
    ]
    assert results.hidden_cluster_cap == 3
    # The slate did not shrink: the cap defers leads, it does not spend the day's capacity.
    assert len(results.visible) == 4
    # Nothing was beaten by rank — the slots the cluster would have taken were refilled.
    assert results.hidden_below_cutoff == 0
    # The five bodies differ, so the exact-key cap could not and did not fire. This is the
    # assertion that says the two caps are not the same mechanism.
    assert results.hidden_slate_cap == 0


def test_the_cap_is_two_and_not_one(env: Path) -> None:
    """Two, because a limit of 1 would collapse groups that are REAL.

    A `company_title_location` suppressor at N=1 was refused for exactly that reason: groups of
    42 and 75 genuine separate openings exist at one company, title and place. Pinned as an
    assertion so lowering the constant is a deliberate act with a failing test attached.
    """
    assert CLUSTER_CAP_PER_KEY == 2
    results = _rank(env, _cluster(2), limit=10)
    assert results.hidden_cluster_cap == 0
    assert len(results.visible) == 2


def test_the_capped_leads_are_not_recorded_seen_so_they_rank_again(env: Path) -> None:
    """The re-entry path, and the reason this quarantine needs no scheduled drain.

    A capped row must not reach `surfaced_job_ids`: recording it `seen` would suppress it for
    the TTL and the cap would be a one-way consumption of the queue, which CLAUDE.md forbids of
    every quarantine. Counting the CLUSTER's surfaced jobs is what discriminates — the total is
    `limit` either way, because the freed slots refill.
    """
    results = _rank(env, RUN_10_SHAPE, limit=4)
    by_posting = _job_ids(env)
    cluster_jobs = {by_posting[p] for p in list(by_posting)[:5]}
    surfaced_cluster = [j for j in results.surfaced_job_ids if j in cluster_jobs]
    assert len(surfaced_cluster) == CLUSTER_CAP_PER_KEY
    # Every delivered row was surfaced and nothing else was.
    assert set(results.surfaced_job_ids) == {by_posting[p.posting_id] for p in results.visible}


def test_a_byte_identical_twin_is_attributed_to_the_slate_cap_not_this_one(env: Path) -> None:
    """The two buckets are held for different reasons, so a row caught by both is attributed to
    the STRONGER claim and counted once.

    The exact-key cap says a byte-identical JD is already in front of the owner; this one says
    only that one role at one place had taken its slots. Folding them would tell the reader a
    redundant copy and a third genuine opening are the same kind of thing.
    """
    same = [
        ("acme-bank", "Security Engineer", CLUSTER_TITLE, "one-hash", "One JD.", list(DALLAS))
        for _ in range(3)
    ]
    results = _rank(env, same, limit=10)
    assert results.hidden_slate_cap == 2
    assert results.hidden_cluster_cap == 0
    assert len(results.visible) == 1


# ---------------------------------------------------------------------- the location key


def test_a_group_of_42_with_different_locations_is_untouched(env: Path) -> None:
    """The collateral the refused suppressor caused, and the case the cap must never touch.

    42 genuinely separate openings for one title at one employer, one per city. The location is
    in the key, so these are 42 keys and not one — nothing is capped.
    """
    rows = [
        (
            "acme-bank", "Lead Software Engineer, Full Stack", "lead software engineer full stack",
            f"real-hash-{i}", f"Real JD {i}.", [f"City {i}, TX"],
        )
        for i in range(42)
    ]
    results = _rank(env, rows, limit=50)
    assert len(results.visible) == 42
    assert results.hidden_cluster_cap == 0


def test_locations_listed_in_a_different_ORDER_are_still_one_cluster(env: Path) -> None:
    """Why the key is the WHOLE canonical location list and not a "primary" location.

    A list's serialization order is not identity (`posting_identity.normalized_locations` says
    so in its own docstring), and providers do reorder one requisition's cities between scans.
    Keying on `locations[0]` — the reduction the queue renders as the primary location — would
    give these three copies of one opening two different keys, so the cap would miss; it would
    also collide a 20-city posting with a single-city one, so the cap would fire on unrelated
    leads. The canonical list is order-insensitive, which is what makes both cases right.
    """
    pairs = [["Dallas, TX", "Austin, TX"], ["Austin, TX", "Dallas, TX"], ["Dallas, TX", "Austin, TX"]]
    rows = [
        ("acme-bank", "Security Engineer", CLUSTER_TITLE, f"pair-hash-{i}", f"JD {i}.", locs)
        for i, locs in enumerate(pairs)
    ]
    results = _rank(env, rows, limit=10)
    assert results.hidden_cluster_cap == 1
    assert len(results.visible) == CLUSTER_CAP_PER_KEY


@pytest.mark.parametrize("locations", [None, [], ["", "  "]])
def test_a_posting_naming_no_location_is_never_capped(
    env: Path, locations: list[str] | None
) -> None:
    """The decision the ticket demanded be stated: absence of a location is NOT a location.

    `normalized_locations` returns None for no location evidence rather than an `"[]"` sentinel,
    precisely so that every location-less posting does not become equal to every other one. A
    None key is not stored, so these rows are unkeyed and uncappable. Fail-open, and the same
    direction as the empty-title and `EMPTY_BODY_HASH` guards on the exact-key cap: the cost of
    not firing is one redundant slot, the cost of firing wrongly is a real lead nobody sees.

    All three shapes are exercised because they reach the None by different routes — a NULL
    column, an empty list, and a list that is present but blank.
    """
    rows = [
        ("acme-bank", "Security Engineer", CLUSTER_TITLE, f"nl-hash-{i}", f"JD {i}.", locations)
        for i in range(3)
    ]
    results = _rank(env, rows, limit=10)
    assert results.hidden_cluster_cap == 0
    assert len(results.visible) == 3


def test_two_companies_at_one_title_and_place_are_not_capped(env: Path) -> None:
    """`company_id` is in the key: two employers hiring one role in one city is two leads."""
    rows = [
        (slug, "Security Engineer", CLUSTER_TITLE, f"{slug}-h-{i}", f"JD {i}.", list(DALLAS))
        for slug in ("acme-bank", "beta-corp")
        for i in range(2)
    ]
    results = _rank(env, rows, limit=10)
    assert results.hidden_cluster_cap == 0
    assert len(results.visible) == 4


# ---------------------------------------------------------------------- the drain


def test_the_drain_surfaces_the_capped_leads_annotated_with_a_holder(env: Path) -> None:
    """A quarantine that cannot be listed is a leak, so the bucket has to be inspectable.

    The annotation carries a holder's posting_id, not a bare flag: a cap the operator cannot
    trace to a row that displaced it cannot be audited.
    """
    shown = _rank(env, RUN_10_SHAPE, limit=4, include_cluster_cap=True)
    assert shown.hidden_cluster_cap == 0
    capped = [p for p in shown.visible if p.cluster_capped_by is not None]
    assert len(capped) == 3
    holders = {p.posting_id for p in shown.visible if p.cluster_capped_by is None}
    # Every annotation points at a row actually on this slate. The cap is not seeded from the
    # standing queue, so unlike `slate_capped_by` this IS the general invariant.
    assert {p.cluster_capped_by for p in capped} <= holders
    # Drained rows do not consume limit slots, so the drain returns more than `limit`.
    assert len(shown.visible) > 4


def test_the_drain_does_not_close_behind_the_reader(env: Path) -> None:
    """Inspecting the bucket must not record those rows `seen` (D-110)."""
    shown = _rank(env, RUN_10_SHAPE, limit=4, include_cluster_cap=True)
    by_posting = _job_ids(env)
    capped_jobs = {
        by_posting[p.posting_id] for p in shown.visible if p.cluster_capped_by is not None
    }
    assert capped_jobs
    assert capped_jobs.isdisjoint(shown.surfaced_job_ids)


def test_the_drained_row_says_so_in_its_why_cell(env: Path) -> None:
    """A drained row must never read as an ordinary lead in the table."""
    from boardwatch.cli.top_cmd import _why_cell  # noqa: PLC0415

    shown = _rank(env, RUN_10_SHAPE, limit=4, include_cluster_cap=True)
    drained = next(p for p in shown.visible if p.cluster_capped_by is not None)
    cell = _why_cell(drained)
    assert "cluster cap" in cell
    assert str(drained.cluster_capped_by) in cell


def test_the_notice_names_the_bucket_and_its_drain(env: Path) -> None:
    """A quarantine whose drain is unmentioned is a leak (CLAUDE.md)."""
    from rich.console import Console  # noqa: PLC0415

    from boardwatch.cli.top_cmd import _print_hidden_notices  # noqa: PLC0415

    results = _rank(env, RUN_10_SHAPE, limit=4)
    console = Console(record=True, width=200)
    _print_hidden_notices(
        console, results,
        include_ineligible=False, include_non_swe=False, include_zero_signal=False,
        include_over_seniority=False, include_hard_filter=False, include_duplicates=False,
        include_slate_cap=False, include_cluster_cap=False, include_handled=False,
        include_applied=False,
    )
    text = console.export_text()
    assert "cluster cap" in text
    assert "--include-cluster-cap" in text


# ---------------------------------------------------------------------- reconciliation


def _accounted(r: RankedResults) -> int:
    """Every term of `RankedResults`' declared identity, spelled out.

    A sum missing a term passes vacuously whenever that bucket happens to be 0 in the fixture,
    which is exactly how T60 went unnoticed for three runs.
    """
    return (
        len(r.visible)
        + r.skipped_not_new
        + r.hidden_hard_filter
        + r.hidden_non_swe
        + r.hidden_zero_signal
        + r.hidden_over_seniority
        + r.hidden_ineligible
        + r.hidden_duplicate
        + r.hidden_applied
        + r.hidden_handled
        + r.hidden_slate_cap
        + r.hidden_cluster_cap
        + r.hidden_below_cutoff
    )


def test_the_ranker_identity_still_balances_with_and_without_the_drain(env: Path) -> None:
    """A new bucket that is not in the identity makes the funnel report DOES NOT RECONCILE,
    which is how T60 was found. Verified, not eyeballed."""
    engine = _seed(env, RUN_10_SHAPE)
    for drained in (False, True):
        # `record_surfaced=False` so the two passes are independent: a recording pass writes
        # `seen` for the delivered rows and the next pass would count them `hidden_handled`.
        r = rank_open_postings(
            engine, _settings(env), limit=4,
            include_cluster_cap=drained, record_surfaced=False,
        )
        assert r.considered == 7
        assert _accounted(r) == r.considered, (drained, r)


def test_the_funnel_gives_the_cluster_cap_its_own_drop_and_still_reconciles() -> None:
    """Its own named bucket in the funnel, never folded into `hidden_slate_cap`.

    Built through the real `build_run_funnel` rather than by inspecting a Drop list, so what is
    checked is the stage's own `reconciled` verdict — the field Gate P0's headline claim is read
    off and the one that said `DOES NOT RECONCILE` on runs 7, 8 and 9.
    """
    stage = _shortlist_stage(hidden_cluster_cap=3, hidden_slate_cap=1)
    counts = {drop.reason: drop.count for drop in stage.drops}
    assert counts["hidden_cluster_cap"] == 3
    # Not folded: the exact-key cap's own count is untouched and separately reported.
    assert counts["hidden_slate_cap"] == 1
    assert stage.reconciled is True


def test_the_funnel_stage_stops_reconciling_if_the_bucket_is_dropped_from_the_identity() -> None:
    """The reconciliation assertion above is only evidence if it can fail.

    `considered` is measured independently of the drop counters, so a bucket that never reaches
    the funnel shows up here as an imbalance rather than as silence. This is the same failure a
    forgotten `Drop` would produce, induced deliberately.
    """
    stage = _shortlist_stage(hidden_cluster_cap=3, considered_excludes_cluster_cap=True)
    assert stage.reconciled is False


def _shortlist_stage(
    *,
    hidden_cluster_cap: int = 0,
    hidden_slate_cap: int = 0,
    considered_excludes_cluster_cap: bool = False,
):
    """The funnel's `shortlist` stage, built through the production path.

    Only the arguments this module varies are parameters; the rest are the minimum a funnel
    needs and are deliberately not shared with `test_run_funnel.py` — a helper imported across
    test modules is a second place the funnel's shape has to be maintained.
    """
    from boardwatch.eligibility.catalog import load_rules  # noqa: PLC0415
    from boardwatch.reports.abstain import build_abstain_report  # noqa: PLC0415
    from boardwatch.reports.run_funnel import (  # noqa: PLC0415
        RunManifest,
        ScanContext,
        ShortlistCounts,
        build_run_funnel,
    )
    from boardwatch.store.run_funnel_queries import (  # noqa: PLC0415
        CorpusCounts,
        TailoredArtifactCounts,
    )

    shortlisted = 2
    considered = shortlisted + hidden_slate_cap + (
        0 if considered_excludes_cluster_cap else hidden_cluster_cap
    )
    funnel = build_run_funnel(
        run_id=42,
        started_at=None,
        finished_at=None,
        manifest=RunManifest(
            code_fingerprint="engine-1+abc", config_hash="c0ffee",
            profile_facts_hash="pf00", profile_row_hash="pr00", rules_hash="ru1e5",
            status="ok", location_filter_mode="soft",
        ),
        scan=ScanContext(ran=True),
        corpus=CorpusCounts(
            open_postings=considered, evaluated=considered, no_current_evaluation=0,
            by_verdict={}, judged_this_run=0,
            cache_hit_prior_run=0, cache_hit_unattributed=0,
        ),
        shortlist=ShortlistCounts(
            considered=considered,
            shortlisted=shortlisted,
            hidden_slate_cap=hidden_slate_cap,
            hidden_cluster_cap=hidden_cluster_cap,
        ),
        sources=[],
        leads=[],
        tailor_failed=shortlisted,
        tailored_artifacts=TailoredArtifactCounts(rows=0, with_pdf=0),
        marked_applied=0,
        stub_postings=0,
        rewrite_rows=[],
        unattributed_evaluations=0,
        abstain=build_abstain_report(load_rules(Path("does-not-exist")), {}),
    )
    return next(stage for stage in funnel.stages if stage.name == "shortlist")


def test_the_operator_summary_line_names_the_bucket() -> None:
    """Nothing statically catches a miss in `_shortlist_line`; this is the only guard, and it
    is the operator's one-line summary of the day."""
    from boardwatch.cli.run_cmd import _shortlist_line  # noqa: PLC0415
    from boardwatch.pipeline.runner import PipelineSummary  # noqa: PLC0415
    from boardwatch.reports.run_funnel import ShortlistCounts  # noqa: PLC0415

    summary = PipelineSummary(run_id=1)
    summary.shortlist = ShortlistCounts(
        considered=100, shortlisted=1, hidden_cluster_cap=3,
    )
    assert "3 cluster-capped" in _shortlist_line(summary)
