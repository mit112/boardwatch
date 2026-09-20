"""D-498 rule (a): an aggregator lane's copy of a job the employer's own board also carries.

**The shape.** The queue's duplicate rate was 10.1% apply / 12.8% review after T73's ranking cap,
and 71 redundant leads decompose by GROUP MEMBERSHIP: 37 are a lane row beside the employer's own
board, 19 are lanes only, 15 are board-vs-board. The store already groups 45 of the 71 under
`cross_host` and delivers them anyway, because `cross_host` GROUPS and never SUPPRESSES (§3.1) —
the counterexample that ruling protects is Microsoft's four same-title Redmond requisitions.

**What these tests pin.** That the LANE copy is the one removed and never the board copy; that
nothing fires unless a board member of the same group is demonstrably in front of the owner;
that the four same-title board requisitions are untouched; that the removed row is counted in its
own bucket, is NOT recorded `seen`, and comes back through `--include-lane-copy` carrying the id
of the board posting that displaced it.

**What they deliberately do not pin.** That two grouped postings are the same job. Nothing here
makes an identity claim — `cross_host.suppresses` stays False and `core/dedup.py` stays
unreachable from `resolve_duplicates`. This is a delivery-policy read of an existing grouping.

The employer-board test is `companies.provider in PROVIDER_NAMES`, NOT the URL host class, and
one test below exists only to hold that line: the job-apps lane writes the employer's own apply
URL, so `core/host_class.classify_host` reads a lane copy as `ats` and a URL-keyed rule would
elect nothing on the commonest shape there is.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import (
    artifacts,
    companies,
    jobs,
    posting_identities,
    posting_versions,
    postings,
)

NOW = utcnow()

# (company_slug, provider, display_title, normalized_title, hash, body, cross_host key or None)
Row = tuple[str, str, str, str, str, str, str | None]

GROUP = "acme|backend engineer|austin, tx"


def _board(i: int, *, key: str | None = GROUP, slug: str = "acme") -> Row:
    return (
        slug, "greenhouse", "Backend Engineer", "backend engineer",
        f"board-hash-{i}", f"Employer JD {i}. " + "detail " * (i + 1), key,
    )


def _lane(i: int, *, provider: str = "jobapps", key: str | None = GROUP) -> Row:
    return (
        f"{provider}-acme", provider, "Backend Engineer", "backend engineer",
        f"lane-hash-{i}", f"Aggregator JD {i}. " + "detail " * (i + 2), key,
    )


FILLER: list[Row] = [
    ("beta", "greenhouse", "Backend Engineer", "backend engineer",
     "beta-hash", "Beta JD.", "beta|backend engineer|reno, nv"),
    ("gamma", "greenhouse", "Backend Engineer", "backend engineer",
     "gamma-hash", "Gamma JD.", "gamma|backend engineer|reno, nv"),
]


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed(data_dir: Path, rows: Sequence[Row]) -> Engine:
    """One open posting per row, `posted_at` descending so the ranking is total.

    The BOARD rows are seeded LAST in each group on purpose where it matters, so a test that
    passes only because the board copy happened to rank first is not possible: `posted_at`
    descends with row order, so a lane row listed first outranks the board row beneath it.
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
        for offset, (slug, provider, title, normalized, hashed, body, key) in enumerate(rows):
            if slug not in company_ids:
                company_ids[slug] = int(conn.execute(insert(companies).values(
                    name=slug.replace("-", " ").title(), provider=provider, slug=slug,
                    source="user", watched=True,
                )).inserted_primary_key[0])
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_ids[slug], job_id=job_id,
                provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=normalized,
                locations_json=["Austin, TX"], remote_policy="onsite",
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=hashed, body_text=body,
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=hashed, body_text=body,
                captured_at=NOW, capture_reason="new",
            ))
            if key is not None:
                conn.execute(insert(posting_identities).values(
                    posting_id=posting_id, kind="cross_host", identity_key=key,
                    algorithm_version=IDENTITY_ALGORITHM_VERSION, created_at=NOW,
                ))
    return engine


def _rank(data_dir: Path, rows: Sequence[Row], *, limit: int = 10, **kw: bool) -> RankedResults:
    return rank_open_postings(_seed(data_dir, rows), _settings(data_dir), limit=limit, **kw)


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _providers(data_dir: Path, results: RankedResults) -> list[str]:
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        by_posting = {
            int(row.id): str(row.provider)
            for row in conn.execute(
                select(postings.c.id, companies.c.provider).join(
                    companies, companies.c.id == postings.c.company_id
                )
            ).all()
        }
    return [by_posting[p.posting_id] for p in results.visible]


def _seen_job_ids(data_dir: Path) -> set[int]:
    from boardwatch.store.tables import job_dispositions

    engine = get_engine(data_dir)
    with engine.connect() as conn:
        return {
            int(row.job_id)
            for row in conn.execute(
                select(job_dispositions.c.job_id).where(
                    job_dispositions.c.disposition == "seen"
                )
            ).all()
        }


# ------------------------------------------------------------------- the rule itself


def test_the_lane_copy_is_removed_and_the_employer_board_copy_survives(env: Path) -> None:
    """The discriminating test, and it asserts WHICH row survived, not just a count.

    The lane row is seeded FIRST, so it outranks the board row — the case an in-loop cap gets
    wrong, because in slate order the lane copy would have taken the allowance and the board
    copy would have been the one displaced.
    """
    results = _rank(env, [_lane(0), _board(1), *FILLER])
    assert _providers(env, results) == ["greenhouse", "greenhouse", "greenhouse"]
    assert results.hidden_lane_copy == 1


def test_a_lane_copy_with_no_board_member_in_its_group_is_delivered(env: Path) -> None:
    """The null control. A lane row, a real group key, and nothing else in its group — delivered.

    Without this, every assertion above would also pass against a rule that simply deleted every
    lane row it saw. **ONE lane row, deliberately**: two of them in one group is rule (b)'s own
    case, pinned separately below, and seeding two here would make this control fail for the
    right reason and stop being a control.
    """
    results = _rank(env, [_lane(0), *FILLER])
    assert results.hidden_lane_copy == 0
    assert _providers(env, results) == ["jobapps", "greenhouse", "greenhouse"]


def test_four_same_title_board_requisitions_are_untouched(env: Path) -> None:
    """Microsoft's four Redmond requisitions: the counterexample §3.1 refuses `cross_host`
    suppression for. All four are EMPLOYER-BOARD rows, so no rule here can look at them.

    Seeded at four DIFFERENT companies sharing one `cross_host` key, because at one company,
    title and city T73's cluster cap fires first at 2 and this test would then pass on a bucket
    that is not the one under test."""
    results = _rank(env, [_board(i, slug=f"acme-{i}") for i in range(4)])
    assert results.hidden_lane_copy == 0
    assert len(results.visible) == 4


def test_a_lane_copy_is_not_recorded_seen_so_it_returns_once_the_board_copy_is_actioned(
    env: Path,
) -> None:
    """The re-entry path, and the reason this quarantine needs no scheduled drain.

    A removed row written `seen` would be suppressed by the ledger on the next run too, and the
    deferral would never end — the drain would close behind the operator.
    """
    engine = _seed(env, [_lane(0), _board(1), *FILLER])
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 1
    with engine.connect() as conn:
        lane_job = int(
            conn.execute(
                select(postings.c.job_id)
                .join(companies, companies.c.id == postings.c.company_id)
                .where(companies.c.provider == "jobapps")
            ).scalar_one()
        )
    assert lane_job not in _seen_job_ids(env)
    assert lane_job not in results.surfaced_job_ids


def test_the_drain_returns_the_row_naming_the_board_posting_that_displaced_it(env: Path) -> None:
    """`--include-lane-copy`. A suppression the operator cannot trace to a row is not auditable."""
    results = _rank(env, [_lane(0), _board(1), *FILLER], include_lane_copy=True)
    assert results.hidden_lane_copy == 0
    (surfaced,) = [p for p in results.visible if p.lane_copy_of is not None]
    board = [p for p in results.visible if p.posting_id != surfaced.posting_id]
    assert surfaced.lane_copy_of in {p.posting_id for p in board}


def test_a_lane_row_in_no_cross_host_group_at_all_is_delivered(env: Path) -> None:
    """No identity row means no group, and an ungrouped row is never removed by a group rule."""
    results = _rank(env, [_lane(0, key=None), _board(1), *FILLER])
    assert results.hidden_lane_copy == 0
    assert "jobapps" in _providers(env, results)


def test_the_removed_row_leaves_the_slate_and_is_counted_where_it_left(env: Path) -> None:
    """The funnel's identity: `considered` == what was surfaced + every drop, each counted where
    the posting actually leaves. The slate SHRINKS rather than refilling — the removed lead is a
    copy of one being delivered, so the day's distinct jobs are unchanged, and refilling would
    mean re-running every cap against a replacement the loop had already ruled out by rank."""
    rows = [_lane(0), _board(1), *FILLER]
    results = _rank(env, rows, limit=10)
    assert results.considered == len(rows)
    assert results.considered == (
        len(results.visible)
        + results.skipped_not_new
        + results.hidden_hard_filter
        + results.hidden_non_swe
        + results.hidden_zero_signal
        + results.hidden_over_seniority
        + results.hidden_ineligible
        + results.hidden_duplicate
        + results.hidden_applied
        + results.hidden_handled
        + results.hidden_slate_cap
        + results.hidden_cluster_cap
        + results.hidden_lane_copy
        + results.hidden_below_cutoff
    )


def test_the_employer_board_test_is_the_company_row_not_the_url_host(env: Path) -> None:
    """The line this rule would quietly lose if it keyed on `classify_host`.

    The job-apps lane writes `url = record.direct_url`, the EMPLOYER's own apply page — so a lane
    copy and a board copy both classify `ats`, `elect_cross_host_survivor` sees two ATS rows,
    calls the choice unforced and returns None. Both copies would then be delivered, which is the
    defect. Seeding both rows with an employer ATS url proves the rule reads the company ROW.
    """
    engine = _seed(env, [_lane(0), _board(1), *FILLER])
    with engine.begin() as conn:
        conn.execute(
            postings.update().values(url="https://job-boards.greenhouse.io/acme/jobs/1")
        )
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 1
    assert _providers(env, results) == ["greenhouse", "greenhouse", "greenhouse"]


# ------------------------------------------------------- rule (b): a lanes-only group


def test_a_lanes_only_group_keeps_the_highest_ranked_copy(env: Path) -> None:
    """D-498 rule (b). No employer board covers this company at all, so no rule-(a) survivor
    exists — the highest-ranked LANE copy is kept and the rest are deferred.

    `_seed` makes `posted_at` descend with row order and the ranker is recency-dominated, so the
    FIRST-seeded row outranks the others; asserting which id survived is what separates this from
    a rule that merely counted.
    """
    results = _rank(env, [_lane(0), _lane(1, provider="indeed"), _lane(2, provider="linkedin"),
                          *FILLER])
    assert results.hidden_lane_copy == 2
    assert _providers(env, results) == ["jobapps", "greenhouse", "greenhouse"]


def test_rule_b_never_fires_when_a_board_member_is_present(env: Path) -> None:
    """Attribution: with a board member in the group every lane copy is rule (a), and the
    survivor is the BOARD posting — not the highest-ranked lane copy rule (b) would have kept."""
    results = _rank(env, [_lane(0), _lane(1, provider="indeed"), _board(2), *FILLER],
                    include_lane_copy=True)
    surfaced = [p for p in results.visible if p.lane_copy_of is not None]
    assert len(surfaced) == 2
    board_id = next(
        p.posting_id for p in results.visible
        if p.lane_copy_of is None and p.company == "Acme"
    )
    assert {p.lane_copy_of for p in surfaced} == {board_id}


def test_two_lane_rows_in_DIFFERENT_groups_are_both_delivered(env: Path) -> None:
    """The null control for rule (b): same providers, same shape, different `cross_host` key."""
    results = _rank(env, [_lane(0), _lane(1, provider="indeed", key="other|backend engineer|x"),
                          *FILLER])
    assert results.hidden_lane_copy == 0
    assert sorted(_providers(env, results)) == ["greenhouse", "greenhouse", "indeed", "jobapps"]


# ------------------------------------------- retired identity generations (T114)

#: A generation the identity subsystem has retired. `write_identities` writes BESIDE history — the
#: UNIQUE key is (posting_id, kind, algorithm_version) — and `identities reap` is manual-only
#: with no scheduler behind it, so retired rows sit on disk indefinitely. Live population is 0
#: today only because the machine reset rebuilt the store; the version has already moved twice
#: (p6.1 -> p6.2 -> p6.3), so this is a latent reader defect, not an unreachable one.
RETIRED = "p6.1"
assert RETIRED != IDENTITY_ALGORITHM_VERSION  # the fixtures below must actually be stale

#: A second group, for the posting that carries BOTH generations at once.
OTHER_GROUP = "acme|backend developer|austin, tx"


def _identity(engine: Engine, posting_id: int, key: str, version: str) -> None:
    """One `cross_host` row at an EXPLICIT generation.

    The tests below seed their postings with `key=None` and write every identity row by hand,
    because what they pin is the generation the reader selects and `_seed` can express only one
    per run. Insertion ORDER is the caller's, which is what lets a test show that the answer does
    not depend on which row SQLite hands back first.
    """
    with engine.begin() as conn:
        conn.execute(
            insert(posting_identities).values(
                posting_id=posting_id, kind="cross_host", identity_key=key,
                algorithm_version=version, created_at=NOW,
            )
        )


def _posting_id(engine: Engine, slug: str) -> int:
    """By company SLUG, never by provider: `FILLER` is two more `greenhouse` rows, so a
    provider lookup would match three postings and the seed would be ambiguous."""
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(postings.c.id)
                .join(companies, companies.c.id == postings.c.company_id)
                .where(companies.c.slug == slug)
            ).scalars().one()
        )


def _delivered_by_a_PRIOR_run(engine: Engine, posting_id: int) -> int:
    """Put `posting_id` in the STANDING queue the way a previous run leaves it.

    Both halves are required: the artifact is what puts the lead in the queue, and the `built`
    disposition is what stops it ranking again. Without the second the board copy re-ranks, lands
    on the slate, and rule (a)'s ON-SLATE arm answers the question — so the test would pass
    whether or not `standing_board_cross_host_keys` was consulted at all.
    """
    with engine.begin() as conn:
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
            media_type="text/x-typst", meta_json={}, created_at=NOW, run_id=None,
        ))
        job_id = int(
            conn.execute(postings.select().where(postings.c.id == posting_id)).one().job_id
        )
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built", policy_version="v1", now=NOW,
        )
        return job_id


# -------------------------------------- reader 1: `_suppress_lane_copies`, on-slate


@pytest.mark.parametrize("board_first", [False, True])
def test_a_group_held_only_at_a_RETIRED_generation_suppresses_nothing(
    env: Path, board_first: bool
) -> None:
    """The defect. Both copies carry a `cross_host` key the identity subsystem has RETIRED, so
    no current evidence says these two rows are the same job — and missing current evidence must
    mean no suppression, which is the fail-open direction for a delivery policy.

    Run under both insertion orders because the production read carries no `ORDER BY`: a filter
    that happened to keep the last row seen would pass one order and fail the other.
    """
    engine = _seed(env, [_lane(0, key=None), _board(1, key=None), *FILLER])
    lane, board = _posting_id(engine, "jobapps-acme"), _posting_id(engine, "acme")
    for posting_id in ((board, lane) if board_first else (lane, board)):
        _identity(engine, posting_id, GROUP, RETIRED)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 0
    assert "jobapps" in _providers(env, results)


@pytest.mark.parametrize("board_first", [False, True])
def test_the_control_a_group_held_at_the_CURRENT_generation_still_defers_the_lane_copy(
    env: Path, board_first: bool
) -> None:
    """The control the test above is worthless without: the same shape at the CURRENT generation
    must still defer the lane copy, under either insertion order. Without it, a reader that had
    simply stopped suppressing would look identical."""
    engine = _seed(env, [_lane(0, key=None), _board(1, key=None), *FILLER])
    lane, board = _posting_id(engine, "jobapps-acme"), _posting_id(engine, "acme")
    for posting_id in ((board, lane) if board_first else (lane, board)):
        _identity(engine, posting_id, GROUP, IDENTITY_ALGORITHM_VERSION)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 1
    assert "jobapps" not in _providers(env, results)


@pytest.mark.parametrize("retired_first", [True, False])
def test_a_retired_key_is_not_matched_against_a_current_one(
    env: Path, retired_first: bool
) -> None:
    """A posting that carries BOTH generations: a retired key matching the board's group, and a
    current key that does not. The current key is the only one that speaks for this posting, so
    the lane row belongs to no group the board is in and must be delivered.

    **This test does NOT go red against the unfiltered read, and that is measured, not assumed.**
    SQLite answers the production select through `sqlite_autoindex_posting_identities_1`
    (posting_id, kind, algorithm_version), so a posting's rows come back in VERSION order and a
    retired generation sorts below the current one — the unfiltered "last row wins" loop
    therefore lands on the current key here by accident of the query plan, under either
    insertion order. What makes the property real is the filter plus that UNIQUE key: together
    they leave exactly one `cross_host` row per posting, so the answer cannot depend on row
    order at all, and no `ORDER BY` is needed to pin it.

    Justified by mutation: drop the version predicate AND read the first row instead of the last
    (`key_of.setdefault`) — the other choice an unordered read permits — and both parameter sets
    fail with `assert 1 == 0`.
    """
    engine = _seed(env, [_lane(0, key=None), _board(1, key=None), *FILLER])
    lane, board = _posting_id(engine, "jobapps-acme"), _posting_id(engine, "acme")
    rows = [(GROUP, RETIRED), (OTHER_GROUP, IDENTITY_ALGORITHM_VERSION)]
    for key, version in rows if retired_first else reversed(rows):
        _identity(engine, lane, key, version)
    _identity(engine, board, GROUP, IDENTITY_ALGORITHM_VERSION)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 0
    assert "jobapps" in _providers(env, results)


def test_rule_b_does_not_group_two_lane_rows_at_a_RETIRED_generation(env: Path) -> None:
    """Rule (b) reads the same `key_of` map, so it inherits the same defect: a lanes-only group
    held only at a retired generation must keep every member, not elect a survivor."""
    engine = _seed(env, [_lane(0, key=None), _lane(1, provider="indeed", key=None), *FILLER])
    for slug in ("jobapps-acme", "indeed-acme"):
        _identity(engine, _posting_id(engine, slug), GROUP, RETIRED)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 0
    assert sorted(_providers(env, results)) == ["greenhouse", "greenhouse", "indeed", "jobapps"]


# --------------- reader 2: `standing_board_cross_host_keys`, reached from the ranker


def test_a_STANDING_board_copy_at_a_RETIRED_generation_holds_no_slot(env: Path) -> None:
    """Rule (a)'s standing arm. The board copy is in the queue but its only `cross_host` row is
    retired, so nothing current says it covers this lane row — and the lane row is work.

    The lane row is seeded at the CURRENT generation, so the reader under test here is
    `standing_board_cross_host_keys` alone: `_suppress_lane_copies` finds a current key for the
    visible lane row either way, and only the holder set moves.
    """
    engine = _seed(env, [_lane(0, key=None), _board(1, key=None), *FILLER])
    lane, board = _posting_id(engine, "jobapps-acme"), _posting_id(engine, "acme")
    _identity(engine, lane, GROUP, IDENTITY_ALGORITHM_VERSION)
    _identity(engine, board, GROUP, RETIRED)
    _delivered_by_a_PRIOR_run(engine, board)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 0
    assert "jobapps" in _providers(env, results)


def test_the_control_a_STANDING_board_copy_at_the_CURRENT_generation_holds(env: Path) -> None:
    """The control for the test above, and the proof the standing arm is reached at all: the
    board copy never enters `visible` — it carries a live `built` disposition — so the ON-SLATE
    arm cannot be what defers the lane row here."""
    engine = _seed(env, [_lane(0, key=None), _board(1, key=None), *FILLER])
    lane, board = _posting_id(engine, "jobapps-acme"), _posting_id(engine, "acme")
    _identity(engine, lane, GROUP, IDENTITY_ALGORITHM_VERSION)
    _identity(engine, board, GROUP, IDENTITY_ALGORITHM_VERSION)
    _delivered_by_a_PRIOR_run(engine, board)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 1
    assert "jobapps" not in _providers(env, results)


def test_a_lane_row_at_a_RETIRED_generation_is_not_held_by_a_CURRENT_standing_board_copy(
    env: Path,
) -> None:
    """The mirror image, isolating `_suppress_lane_copies` against a standing holder: the holder
    set is correct and current, and it is the LANE row whose only key is retired. It carries no
    current group, so no group rule can reach it."""
    engine = _seed(env, [_lane(0, key=None), _board(1, key=None), *FILLER])
    lane, board = _posting_id(engine, "jobapps-acme"), _posting_id(engine, "acme")
    _identity(engine, lane, GROUP, RETIRED)
    _identity(engine, board, GROUP, IDENTITY_ALGORITHM_VERSION)
    _delivered_by_a_PRIOR_run(engine, board)
    results = rank_open_postings(engine, _settings(env), limit=10)
    assert results.hidden_lane_copy == 0
    assert "jobapps" in _providers(env, results)
