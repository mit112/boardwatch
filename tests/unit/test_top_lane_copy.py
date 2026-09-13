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
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import (
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
                    algorithm_version=1, created_at=NOW,
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
    """The null control. Same lane row, same group key, no employer-board member — nothing fires.

    Without this, every assertion above would also pass against a rule that simply deleted every
    lane row it saw.
    """
    results = _rank(env, [_lane(0), _lane(1, provider="indeed"), *FILLER])
    assert results.hidden_lane_copy == 0
    assert _providers(env, results) == ["jobapps", "indeed", "greenhouse", "greenhouse"]


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
