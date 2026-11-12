"""D-683: where `slate_direct_share`'s direct and other leads leave the slate, counted per tier and
route at every step. The share's reorder runs BEFORE the ranker's filters and nothing re-reserves
after them, so a direct lead that ranked can still vanish; these tests pin that the vanishing is
now counted, by tier, by route and by step, and that counting changed no decision.

**Every expected number below is written out from the fixture's facts** (which row is which, which
filter it was built to meet), never read off the code under test. `WIDE` names each row and the
step it is built to meet, so a reader can check the table against the rows without running
anything. A control on the same fixture with the share off and with the tally disabled shows the
delivered order is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert, select
from typer.testing import CliRunner

from boardwatch.cli import top_cmd
from boardwatch.cli.app import app
from boardwatch.cli.top_cmd import RankedResults, interleave_direct, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.posting_identity import compute_identities
from boardwatch.core.settings import load_settings
from boardwatch.rank.direct_share import DirectShareTally
from boardwatch.store import tables
from boardwatch.store.applications import mark_job_applied
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.identity_queries import load_identity_inputs, write_identities
from boardwatch.store.ledger_queries import record_disposition

NOW = utcnow()
_INIT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\nsoftware\n"
_ROUTES = 'auto_hosts = ["ashbyhq.com"]\nunresolved_hosts = ["linkedin.com"]\n'

# "Backend Engineer" ranks in tier 2 on the fresh-store verdict (uncertain, in field); "Software
# Wizard" carries no role signal and ranks in tier 3. Two tiers is what lets a count be wrong
# about WHICH tier it files a lead under.
T2, T3 = "Backend Engineer", "Software Wizard"


@dataclass(frozen=True)
class Row:
    name: str
    title: str
    direct: bool
    company: str  # display name; also the slug
    provider: str = "greenhouse"
    location: str | None = None  # default: unique per row
    content_hash: str | None = None  # default: unique per row
    older: bool = False  # first seen earlier, so it is the exact_quad survivor of its pair
    url: str | None = None  # default: unique per row and routed by `direct`


def _url(row: Row, n: int) -> str:
    if row.url is not None:
        return row.url
    if row.direct:
        return f"https://jobs.ashbyhq.com/{row.company}/00000000-0000-0000-0000-{n:012d}"
    return f"https://boards.greenhouse.io/{row.company}/jobs/{n}"


# The fixture, in rank order within each kind (posted_at descends with the list). The comment on
# each group is the step it is built to meet and the answer, per route.
WIDE: tuple[Row, ...] = (
    # Tier 2 -------------------------------------------------------------------------------
    # Plain: nothing removes them. 2 direct, 2 other.
    Row("a2d1", T2, True, "plain1"), Row("a2n1", T2, False, "plain2"),
    Row("a2d2", T2, True, "plain3"), Row("a2n2", T2, False, "plain4"),
    # Handled: a live `built` disposition. 1 direct, 1 other.
    Row("h2d", T2, True, "handled1"), Row("h2n", T2, False, "handled2"),
    # Applied: the job carries a submitted application. 1 direct, 1 other.
    Row("p2d", T2, True, "applied1"), Row("p2n", T2, False, "applied2"),
    # Slate cap: one company, title and JD hash, two cities; the later one is capped.
    Row("s2d1", T2, True, "slate1", content_hash="same-d"),
    Row("s2d2", T2, True, "slate1", content_hash="same-d"),
    Row("s2n1", T2, False, "slate2", content_hash="same-n"),
    Row("s2n2", T2, False, "slate2", content_hash="same-n"),
    # Cluster cap: one company, title and city, three JDs; the third is capped (cap is 2).
    Row("c2d1", T2, True, "cluster1", location="Reno, NV"),
    Row("c2d2", T2, True, "cluster1", location="Reno, NV"),
    Row("c2d3", T2, True, "cluster1", location="Reno, NV"),
    Row("c2n1", T2, False, "cluster2", location="Reno, NV"),
    Row("c2n2", T2, False, "cluster2", location="Reno, NV"),
    Row("c2n3", T2, False, "cluster2", location="Reno, NV"),
    # Duplicate: one company, title, city and JD twice; the later-seen one is suppressed.
    Row("d2d1", T2, True, "dup1", location="Elko, NV", content_hash="dup-d", older=True),
    Row("d2d2", T2, True, "dup1", location="Elko, NV", content_hash="dup-d"),
    Row("d2n1", T2, False, "dup2", location="Elko, NV", content_hash="dup-n", older=True),
    Row("d2n2", T2, False, "dup2", location="Elko, NV", content_hash="dup-n"),
    # Requisition twin: the holder was delivered earlier (so it is `handled` here); the twin names
    # the same requisition under another spelling and is held. 1 direct, 1 other; and the two
    # holders add 1 direct, 1 other to `handled`.
    Row("r2dh", T2, True, "reqd", url="https://jobs.ashbyhq.com/reqd/aaaaaaaa-0000-0000-0000-000000000001"),
    Row("r2dt", T2, True, "reqd2", url="https://jobs.ashbyhq.com/REQD/AAAAAAAA-0000-0000-0000-000000000001"),
    Row("r2nh", T2, False, "reqn", url="https://boards.greenhouse.io/reqn/jobs/4000001"),
    Row("r2nt", T2, False, "reqn2", url="https://boards.greenhouse.io/Reqn/jobs/4000001"),
    # Lane copy removed AFTER the loop: a lane row beside the employer's board row, both on the
    # slate. The lane copy goes; the board copy stays. 1 direct, 1 other.
    Row("lbd", T2, False, "Lane A", location="Ely, NV"),
    Row("lcd", T2, True, "Lane A", provider="jobapps", location="Ely, NV"),
    Row("lbn", T2, False, "Lane B", location="Wells, NV"),
    Row("lcn", T2, False, "Lane B", provider="jobapps", location="Wells, NV",
        url="https://example.test/lane/b"),
    # Lane copy held IN the loop: its group has a copy delivered earlier (the holder is `handled`
    # here), so the copy never takes a slot. 1 direct, 0 other.
    Row("lhh", T2, False, "Lane C", location="Fallon, NV"),
    Row("lhd", T2, True, "Lane C", provider="jobapps", location="Fallon, NV"),
    # Tier 3 -------------------------------------------------------------------------------
    # Handled: 1 direct. Applied: 1 other.
    Row("h3d", T3, True, "handled3"), Row("p3n", T3, False, "applied3"),
    # Plain, in rank order. With the share at 0.5 the tier orders D N D N D N D N, and the top-N
    # cut keeps the first four of them: 2 direct and 2 other are cut.
    Row("t3d1", T3, True, "tail1"), Row("t3n1", T3, False, "tail2"),
    Row("t3d2", T3, True, "tail3"), Row("t3n2", T3, False, "tail4"),
    Row("t3d3", T3, True, "tail5"), Row("t3n3", T3, False, "tail6"),
    Row("t3d4", T3, True, "tail7"), Row("t3n4", T3, False, "tail8"),
)
HANDLED = ("h2d", "h2n", "r2dh", "r2nh", "lhh", "h3d")
APPLIED = ("p2d", "p2n", "p3n")
# The rows a prior run delivered: an artifact and the `built` disposition that stops them ranking.
DELIVERED_EARLIER = ("r2dh", "r2nh", "lhh")
LIMIT = 20


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed(data_dir: Path, rows: tuple[Row, ...] = WIDE) -> dict[str, int]:
    """Seed `rows`, give every posting its real identities, and run `init`. name -> posting id."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    ids: dict[str, int] = {}
    companies: dict[tuple[str, str], int] = {}
    with engine.begin() as conn:
        for n, row in enumerate(rows):
            key = (row.provider, row.company)
            if key not in companies:
                companies[key] = int(conn.execute(insert(tables.companies).values(
                    name=row.company, provider=row.provider, slug=row.company.replace(" ", "-"),
                    source="user", watched=True,
                )).inserted_primary_key[0])
            job_id = int(conn.execute(insert(tables.jobs).values(created_at=NOW))
                         .inserted_primary_key[0])
            body = f"Backend services in Python and Go. Opening {row.content_hash or n}."
            seen = NOW - timedelta(days=30) if row.older else NOW
            ids[row.name] = int(conn.execute(insert(tables.postings).values(
                company_id=companies[key], job_id=job_id, provider_posting_id=f"pp-{n}",
                title=row.title, normalized_title=row.title.lower(), url=_url(row, n),
                locations_json=[row.location or f"City {n}, NV"], remote_policy="onsite",
                posted_at=NOW - timedelta(hours=n), first_seen_at=seen, last_seen_at=NOW,
                status="open", consecutive_missing=0,
                content_hash=row.content_hash or f"hash-{n}", body_text=body,
            )).inserted_primary_key[0])
            conn.execute(insert(tables.posting_versions).values(
                posting_id=ids[row.name], content_hash=row.content_hash or f"hash-{n}",
                body_text=body, captured_at=NOW, capture_reason="new",
            ))
    result = CliRunner().invoke(app, ["--data-dir", str(data_dir), "init"], input=_INIT)
    assert result.exit_code == 0, result.output
    with engine.begin() as conn:
        for inputs in load_identity_inputs(conn, None):
            write_identities(conn, inputs.posting_id, compute_identities(inputs), now=NOW)
        for name in HANDLED + APPLIED:
            job_id = int(conn.execute(
                select(tables.postings.c.job_id).where(tables.postings.c.id == ids[name])
            ).scalar_one())
            if name in APPLIED:
                mark_job_applied(conn, posting_id=ids[name], source="test")
                continue
            if name in DELIVERED_EARLIER:
                version_id = int(conn.execute(
                    select(tables.posting_versions.c.id)
                    .where(tables.posting_versions.c.posting_id == ids[name])
                ).scalar_one())
                conn.execute(insert(tables.artifacts).values(
                    posting_version_id=version_id, kind="resume_tailored",
                    uri=f"/out/{ids[name]}.typ", generator="boardwatch.tailor",
                    media_type="text/x-typst", meta_json={}, created_at=NOW, run_id=None,
                ))
            record_disposition(
                conn, job_id, disposition="built", reason="lead_built", policy_version="v1",
                now=NOW,
            )
    (data_dir.parent / "cfg").mkdir(exist_ok=True)
    (data_dir.parent / "cfg" / "apply-routes.toml").write_text(_ROUTES)
    return ids


def _rank(
    data_dir: Path, share: float, *, limit: int = LIMIT
) -> tuple[RankedResults, str]:
    settings = load_settings(data_dir=data_dir).model_copy(update={"slate_direct_share": share})
    buffer = StringIO()
    ranked = rank_open_postings(
        get_engine(data_dir), settings, limit=limit, record_surfaced=False,
        output_console=Console(file=buffer, width=200),
    )
    return ranked, buffer.getvalue()


def _names(ids: dict[str, int], *names: str) -> list[int]:
    return sorted(ids[n] for n in names)


def _removed(tally: DirectShareTally, tier: int, direct: bool) -> dict[str, int]:
    return {
        step: n for (t, d, step), n in tally.removed.items() if t == tier and d == direct and n
    }


# ---------------------------------------------------------------------------------------------
# the ranker's half
# ---------------------------------------------------------------------------------------------


def test_every_ranker_step_is_counted_by_tier_and_route(env: Path) -> None:
    """The discriminating fixture: each step removes at least one direct and one other lead, in
    two tiers, and the numbers are the ones the rows above were built to produce."""
    ids = _seed(env)
    ranked, out = _rank(env, 0.5)
    tally = ranked.direct_share
    assert tally is not None and tally.state == "measured"
    # Every row but none are pre-filtered: all 42 ranked rows entered the interleave.
    assert ranked.considered == len(WIDE)

    # entered the interleave, by tier and route (tier 2 = 32 rows, tier 3 = 10 rows).
    assert dict(tally.entered) == {(2, True): 15, (2, False): 17, (3, True): 5, (3, False): 5}
    # What the ranker removed, per tier and route. Handled counts the three delivered holders.
    assert _removed(tally, 2, True) == {
        "hidden_handled": 2,          # h2d, r2dh
        "hidden_applied": 1,          # p2d
        "hidden_slate_cap": 1,        # s2d2
        "hidden_cluster_cap": 1,      # c2d3
        "hidden_duplicate": 1,        # d2d2
        "hidden_requisition_twin": 1,  # r2dt
        "hidden_lane_copy": 2,        # lhd (held in the loop) and lcd (suppressed after it)
    }
    assert _removed(tally, 2, False) == {
        "hidden_handled": 3,          # h2n, r2nh, lhh
        "hidden_applied": 1,          # p2n
        "hidden_slate_cap": 1,        # s2n2
        "hidden_cluster_cap": 1,      # c2n3
        "hidden_duplicate": 1,        # d2n2
        "hidden_requisition_twin": 1,  # r2nt
        "hidden_lane_copy": 1,        # lcn
    }
    assert _removed(tally, 3, True) == {"hidden_handled": 1, "capped_by_top_n": 2}
    assert _removed(tally, 3, False) == {"hidden_applied": 1, "capped_by_top_n": 2}

    # The ids of the DIRECT leads removed, by tier and step. Other leads' ids are never kept.
    assert {k: sorted(v) for k, v in tally.dropped_ids.items()} == {
        (2, "hidden_handled"): _names(ids, "h2d", "r2dh"),
        (2, "hidden_applied"): _names(ids, "p2d"),
        (2, "hidden_slate_cap"): _names(ids, "s2d2"),
        (2, "hidden_cluster_cap"): _names(ids, "c2d3"),
        (2, "hidden_duplicate"): _names(ids, "d2d2"),
        (2, "hidden_requisition_twin"): _names(ids, "r2dt"),
        (2, "hidden_lane_copy"): _names(ids, "lhd", "lcd"),
        (3, "hidden_handled"): _names(ids, "h3d"),
        (3, "capped_by_top_n"): _names(ids, "t3d3", "t3d4"),
    }
    # The positions the share rule claimed, hand-traced from `interleave_direct`'s rule at 0.5.
    # Tier 3 alternates D N D N, so each of its five directs sits where the quota falls: 5.
    # Tier 2 has 15 directs among 32 positions. The quota (taken directs < 0.5 * (position + 1))
    # claims positions 0, 2, 4, 6, 8, 12, 18, 22, 26 and 28; the directs at positions 9, 13, 14,
    # 19 and 23 are taken because they are the best remaining lead, not by the quota: 10.
    assert tally.reserved == {2: 10, 3: 5}
    # The leads left on the list: 14 in tier 2 and 4 in tier 3, each routed by its link.
    assert {pid: tier_route for pid, tier_route in tally.survivors.items()} == {
        ids["a2d1"]: (2, True), ids["a2n1"]: (2, False), ids["a2d2"]: (2, True),
        ids["a2n2"]: (2, False), ids["s2d1"]: (2, True), ids["s2n1"]: (2, False),
        ids["c2d1"]: (2, True), ids["c2d2"]: (2, True), ids["c2n1"]: (2, False),
        ids["c2n2"]: (2, False), ids["d2d1"]: (2, True), ids["d2n1"]: (2, False),
        ids["lbd"]: (2, False), ids["lbn"]: (2, False),
        ids["t3d1"]: (3, True), ids["t3n1"]: (3, False), ids["t3d2"]: (3, True),
        ids["t3n2"]: (3, False),
    }
    assert "slate_direct_share 0.5" in out


def test_each_step_total_equals_the_counter_the_ranker_already_keeps(env: Path) -> None:
    """The cross-check the funnel makes, made here without the funnel: the tally and the
    existing `hidden_*` counters are separate code and have to agree step by step."""
    _seed(env)
    ranked, _ = _rank(env, 0.5)
    tally = ranked.direct_share
    assert tally is not None
    by_step: dict[str, int] = {}
    for (_, _, step), n in tally.removed.items():
        by_step[step] = by_step.get(step, 0) + n
    assert by_step == {
        "hidden_handled": ranked.hidden_handled,                  # 6
        "hidden_applied": ranked.hidden_applied,                  # 3
        "hidden_slate_cap": ranked.hidden_slate_cap,              # 2
        "hidden_cluster_cap": ranked.hidden_cluster_cap,          # 2
        "hidden_duplicate": ranked.hidden_duplicate,              # 2
        "hidden_requisition_twin": ranked.hidden_requisition_twin,  # 2
        "hidden_lane_copy": ranked.hidden_lane_copy,              # 3
        "capped_by_top_n": ranked.hidden_below_cutoff,            # 4
    }
    assert sum(tally.entered.values()) == ranked.considered == 42
    assert len(tally.survivors) == len(ranked.visible) == 18
    assert (
        sum(tally.entered.values()) - sum(by_step.values()) == len(tally.survivors)
    ), "entered = removed + still on the list"


def test_the_ranked_slate_is_the_same_with_the_tally_off_and_with_it_on(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counting changes no decision. The visible order is written out by hand from the fixture
    (the interleave's output less each lead the filters remove), and the same fixture ranked with
    the tally's recording disabled must give the same rows and the same counters."""
    ids = _seed(env)
    on, _ = _rank(env, 0.5)
    expected = [
        "a2d1", "a2n1", "a2d2", "a2n2", "s2d1", "s2n1", "c2d1", "c2d2", "c2n1", "c2n2",
        "d2d1", "d2n1", "lbd", "lbn", "t3d1", "t3n1", "t3d2", "t3n2",
    ]
    assert [p.posting_id for p in on.visible] == [ids[n] for n in expected]

    monkeypatch.setattr(DirectShareTally, "drop", lambda *a, **k: None)
    monkeypatch.setattr(DirectShareTally, "finish", lambda *a, **k: None)
    off, _ = _rank(env, 0.5)
    monkeypatch.undo()

    def counters(r: RankedResults) -> tuple[int, ...]:
        return (
            r.considered, r.hidden_handled, r.hidden_applied, r.hidden_duplicate,
            r.hidden_slate_cap, r.hidden_cluster_cap, r.hidden_lane_copy,
            r.hidden_requisition_twin, r.hidden_below_cutoff, len(r.visible),
        )

    assert [p.posting_id for p in off.visible] == [p.posting_id for p in on.visible]
    assert counters(off) == counters(on) == (42, 6, 3, 2, 2, 2, 3, 2, 4, 18)
    assert off.surfaced_job_ids == on.surfaced_job_ids


def test_the_reserved_count_does_not_change_the_interleave() -> None:
    """`reserved=` only counts. The same rows with and without it come out in one order."""
    leads = [
        top_cmd.RankedPosting(
            posting_id=i, title=f"{'D' if i % 3 == 0 else 'O'}{i}", company="c",
            score=top_cmd.Score(0.0, {}, 0, 0), why="", tier=2 if i < 6 else 3,
        )
        for i in range(10)
    ]

    def is_direct(r: top_cmd.RankedPosting) -> bool:
        return r.title.startswith("D")

    counted: dict[int, int] = {}
    plain = interleave_direct(leads, is_direct, 0.5)
    with_count = interleave_direct(leads, is_direct, 0.5, reserved=counted)
    assert [r.posting_id for r in plain] == [r.posting_id for r in with_count]
    # Tier 2 is ids 0-5 with directs 0 and 3 (list positions 0 and 3). p0: quota (0 < 0.5) takes
    # id 0. p1: 1 < 1 fails and the direct at index 3 is not ahead of the other at index 1, so an
    # other goes. p2: 1 < 1.5, quota takes id 3. Two claimed. Tier 3 is ids 6-9 with directs 6 and
    # 9 in the same shape: p0 takes id 6, p1 an other, p2 takes id 9. Two claimed.
    assert counted == {2: 2, 3: 2}


# ---------------------------------------------------------------------------------------------
# off, inert
# ---------------------------------------------------------------------------------------------


def test_share_zero_says_off_and_records_nothing(env: Path) -> None:
    _seed(env)
    ranked, out = _rank(env, 0.0)
    tally = ranked.direct_share
    assert tally is not None
    assert tally.state == "off" and tally.share == 0.0
    assert not tally.entered and not tally.removed and not tally.survivors
    assert "slate_direct_share" not in out


def test_no_routes_file_says_inert_with_the_reason_and_records_nothing(env: Path) -> None:
    _seed(env)
    (env.parent / "cfg" / "apply-routes.toml").unlink()
    ranked, out = _rank(env, 0.5)
    tally = ranked.direct_share
    assert tally is not None
    assert tally.state == "inert"
    assert tally.detail == "no apply-routes.toml in the config directory"
    assert "slate_direct_share 0.5 is inert: no apply-routes.toml in the config directory" in out
    assert not tally.entered and not tally.removed


def test_every_ranker_drop_bucket_is_either_traced_or_before_the_interleave() -> None:
    """A new ranker bucket must be a decision here: traced, or declared a pre-interleave drop.

    `RankedResults`' own identity names the buckets; the tally's `RANKER_STEP_COUNTER` names the
    ones it traces, and the rest are filters that run before `eligible` exists.
    """
    import re

    from boardwatch.rank.direct_share import RANKER_STEP_COUNTER

    identity = set(re.findall(
        r"\b(?:hidden_\w+|skipped_not_new)\b", top_cmd.RankedResults.__doc__ or ""
    ))
    before_the_interleave = {
        "skipped_not_new", "hidden_hard_filter", "hidden_non_swe", "hidden_zero_signal",
        "hidden_over_seniority", "hidden_ineligible",
    }
    traced = set(RANKER_STEP_COUNTER.values())
    assert identity - before_the_interleave == traced
    assert not traced & before_the_interleave


# ---------------------------------------------------------------------------------------------
# the pipeline's half: one fate per surviving lead
# ---------------------------------------------------------------------------------------------

#: The 18 leads the ranker leaves on WIDE, and what the run then does to each. Written out by hand.
#: dead        a2d1 (direct, tier 2)  t3n1 (other, tier 3)
#: gate        c2d1 (direct, tier 2)
#: beyond      t3d2 (direct, tier 3)  t3n2 (other, tier 3)
#: deferred    s2d1 (direct, tier 2)
#: projection  c2n1 (other, tier 2)
#: tailoring   d2n1 (other, tier 2)
#: delivered   a2d2 c2d2 d2d1 t3d1 (direct); a2n1 s2n1 c2n2 lbd lbn (other) and a2n2 (other, review)
RUN_FATES = {
    "dead": ("a2d1", "t3n1"),
    "gate": ("c2d1",),
    "beyond": ("t3d2", "t3n2"),
    "deferred": ("s2d1",),
    "projection": ("c2n1",),
    "tailoring": ("d2n1",),
    "delivered": ("a2d2", "c2d2", "d2d1", "t3d1", "a2n1", "s2n1", "c2n2", "lbd", "lbn", "a2n2"),
}


def _attribute(ids: dict[str, int], tally: DirectShareTally, **overrides: object):  # type: ignore[no-untyped-def]
    from boardwatch.rank.direct_share import attribute

    def of(key: str) -> list[int]:
        return [ids[n] for n in RUN_FATES[key]]

    kwargs: dict[str, object] = dict(
        liveness_ran=True, gate_armed=True, projection_ran=True,
        dead_ids=of("dead"), gate_excluded_ids=of("gate"), beyond_slate_ids=of("beyond"),
        execution_deferred_ids=of("deferred"), projection_failed_ids=of("projection"),
        tailor_failed_ids=of("tailoring"),
        delivered={ids[n]: n == "a2n2" for n in RUN_FATES["delivered"]},
    )
    kwargs.update(overrides)
    return attribute(tally, **kwargs)  # type: ignore[arg-type]


def test_attribution_files_every_lead_under_its_tier_route_and_step(env: Path) -> None:
    ids = _seed(env)
    tally = _rank(env, 0.5)[0].direct_share
    assert tally is not None
    report = _attribute(ids, tally)
    assert report.state == "measured" and report.reconciles is True and report.unaccounted == 0

    t2, t3 = report.tiers[2], report.tiers[3]
    assert set(report.tiers) == {2, 3}
    # Tier 2, direct: 15 entered = 12 removed (9 by the ranker, a2d1 dead, c2d1 gate, s2d1
    # deferred) + 3 delivered (a2d2, c2d2, d2d1).
    assert t2.direct.entered == 15 and t2.direct.delivered == 3
    assert dict(t2.direct.removed) == {
        "hidden_duplicate": 1, "hidden_handled": 2, "hidden_applied": 1, "hidden_lane_copy": 2,
        "hidden_requisition_twin": 1, "hidden_slate_cap": 1, "hidden_cluster_cap": 1,
        "capped_by_top_n": 0, "withheld_not_live": 1, "gate_rejected": 1, "beyond_slate": 0,
        "execution_deferred": 1, "projection_failed": 0, "tailor_failed": 0,
    }
    # Tier 2, other: 17 entered = 11 removed (9 by the ranker, c2n1 projection, d2n1 tailoring)
    # + 6 delivered, one of which went to the review folder.
    assert t2.non_direct.entered == 17 and t2.non_direct.delivered == 6
    assert t2.non_direct.delivered_review_lane == 1 and t2.direct.delivered_review_lane == 0
    assert dict(t2.non_direct.removed) == {
        "hidden_duplicate": 1, "hidden_handled": 3, "hidden_applied": 1, "hidden_lane_copy": 1,
        "hidden_requisition_twin": 1, "hidden_slate_cap": 1, "hidden_cluster_cap": 1,
        "capped_by_top_n": 0, "withheld_not_live": 0, "gate_rejected": 0, "beyond_slate": 0,
        "execution_deferred": 0, "projection_failed": 1, "tailor_failed": 1,
    }
    # Tier 3, direct: 5 = handled 1 + cut 2 + beyond the slate 1 + delivered t3d1.
    assert t3.direct.entered == 5 and t3.direct.delivered == 1
    assert {k: v for k, v in t3.direct.removed.items() if v} == {
        "hidden_handled": 1, "capped_by_top_n": 2, "beyond_slate": 1,
    }
    # Tier 3, other: 5 = applied 1 + cut 2 + t3n1 dead + t3n2 beyond the slate, none delivered.
    assert t3.non_direct.entered == 5 and t3.non_direct.delivered == 0
    assert {k: v for k, v in t3.non_direct.removed.items() if v} == {
        "hidden_applied": 1, "capped_by_top_n": 2, "withheld_not_live": 1, "beyond_slate": 1,
    }
    assert report.reserved == 15

    # The direct ids, by tier and step: the evidence the history lacked.
    assert {step: sorted(v) for step, v in t2.direct.dropped_ids.items()} == {
        "hidden_handled": _names(ids, "h2d", "r2dh"), "hidden_applied": _names(ids, "p2d"),
        "hidden_slate_cap": _names(ids, "s2d2"), "hidden_cluster_cap": _names(ids, "c2d3"),
        "hidden_duplicate": _names(ids, "d2d2"), "hidden_requisition_twin": _names(ids, "r2dt"),
        "hidden_lane_copy": _names(ids, "lhd", "lcd"), "withheld_not_live": _names(ids, "a2d1"),
        "gate_rejected": _names(ids, "c2d1"), "execution_deferred": _names(ids, "s2d1"),
    }
    assert {step: sorted(v) for step, v in t3.direct.dropped_ids.items()} == {
        "hidden_handled": _names(ids, "h3d"), "capped_by_top_n": _names(ids, "t3d3", "t3d4"),
        "beyond_slate": _names(ids, "t3d2"),
    }
    assert not t2.non_direct.dropped_ids and not t3.non_direct.dropped_ids


def test_the_delivered_slate_recounted_from_its_own_links_matches(env: Path) -> None:
    """Delivery recounted by a path that shares nothing with the tally: the delivered leads' own
    stored links, routed afresh by the routes file."""
    from boardwatch.delivery.apply_routes import load_apply_routes

    ids = _seed(env)
    tally = _rank(env, 0.5)[0].direct_share
    assert tally is not None
    report = _attribute(ids, tally)
    routes = load_apply_routes(load_settings(data_dir=env).config_dir)
    with get_engine(env).connect() as conn:
        urls = dict(conn.execute(
            select(tables.postings.c.id, tables.postings.c.url)
            .where(tables.postings.c.id.in_([ids[n] for n in RUN_FATES["delivered"]]))
        ).all())
    direct = sum(routes.is_direct_auto(url) for url in urls.values())
    assert (direct, len(urls) - direct) == (4, 6)
    assert report.total("direct", "delivered") == direct
    assert report.total("non_direct", "delivered") == len(urls) - direct


def test_a_lead_in_no_step_and_not_delivered_is_unaccounted_not_hidden(env: Path) -> None:
    """The remainder is named and fails the reconciliation: nothing balances it away."""
    ids = _seed(env)
    tally = _rank(env, 0.5)[0].direct_share
    assert tally is not None
    # c2d2 (direct, tier 2) is in no id set and not delivered, as after an aborted tailor loop.
    delivered = {ids[n]: n == "a2n2" for n in RUN_FATES["delivered"] if n != "c2d2"}
    report = _attribute(ids, tally, delivered=delivered)
    assert report.tiers[2].direct.unaccounted == 1
    assert report.tiers[2].direct.delivered == 2
    assert report.unaccounted == 1 and report.reconciles is False


def test_offsetting_errors_do_not_cancel_in_the_remainder() -> None:
    """Two leads, one direct and one other, both in tier 2. The tally is made to remove two
    DIRECT leads (one too many) and no other lead (one too few). Signed, the two buckets cancel
    to 0 and the identity would hold; as magnitudes they are 1 + 1."""
    from boardwatch.rank.direct_share import attribute

    tally = DirectShareTally.measured(
        0.5, leads=[(1, 2), (2, 2)], direct_ids=frozenset({1}), reserved={2: 1}
    )
    tally.removed[(2, True, "hidden_handled")] = 2
    report = attribute(
        tally, liveness_ran=True, gate_armed=False, projection_ran=False, dead_ids=[],
        gate_excluded_ids=[], beyond_slate_ids=[], execution_deferred_ids=[],
        projection_failed_ids=[], tailor_failed_ids=[], delivered={},
    )
    assert report.tiers[2].direct.unaccounted == -1
    assert report.tiers[2].non_direct.unaccounted == 1
    assert report.unaccounted == 2 and report.reconciles is False


def test_a_lead_in_two_id_sets_takes_the_earlier_fate_and_leaves_the_other_step_short(
    env: Path,
) -> None:
    """The id sets are meant to be disjoint. If one is not, the lead is counted once, at the
    earlier step, so the funnel's per-step counter for the later one disagrees."""
    ids = _seed(env)
    tally = _rank(env, 0.5)[0].direct_share
    assert tally is not None
    both = [ids[n] for n in RUN_FATES["tailoring"]] + [ids["a2d1"]]
    report = _attribute(ids, tally, tailor_failed_ids=both)
    assert report.step_total("withheld_not_live") == 2        # a2d1 stays dead
    assert report.step_total("tailor_failed") == 1            # a2d1 is not also counted here


def test_a_step_the_run_did_not_take_is_absent_not_zero(env: Path) -> None:
    ids = _seed(env)
    tally = _rank(env, 0.5)[0].direct_share
    assert tally is not None
    report = _attribute(
        ids, tally, liveness_ran=False, gate_armed=False, projection_ran=False,
        dead_ids=[], gate_excluded_ids=[], projection_failed_ids=[],
        delivered={ids[n]: False for n in (*RUN_FATES["delivered"], "a2d1", "c2d1", "c2n1", "t3n1")},
    )
    assert "withheld_not_live" not in report.steps
    assert "gate_rejected" not in report.steps
    assert "projection_failed" not in report.steps
    assert "withheld_not_live" not in report.tiers[2].direct.removed
    assert report.reconciles is True


def test_attribution_of_an_unarmed_or_missing_tally_is_not_counts() -> None:
    from boardwatch.rank.direct_share import attribute, direct_share_to_dict

    common = dict(
        liveness_ran=True, gate_armed=True, projection_ran=True, dead_ids=[],
        gate_excluded_ids=[], beyond_slate_ids=[], execution_deferred_ids=[],
        projection_failed_ids=[], tailor_failed_ids=[], delivered={},
    )
    off = attribute(DirectShareTally.off(0.0), **common)  # type: ignore[arg-type]
    inert = attribute(DirectShareTally.inert(0.5, "no apply-routes.toml"), **common)  # type: ignore[arg-type]
    missing = attribute(None, **common)  # type: ignore[arg-type]
    assert (off.state, inert.state, missing.state) == ("off", "inert", "not_measured")
    for report in (off, inert, missing):
        assert not report.tiers and report.reconciles is None
    assert direct_share_to_dict(off) == {
        "instrumented": False, "state": "off", "share": 0.0, "detail": "slate_direct_share is 0",
    }
    assert direct_share_to_dict(inert) == {
        "instrumented": False, "state": "inert", "share": 0.5, "detail": "no apply-routes.toml",
    }
    assert direct_share_to_dict(None)["state"] == "not_measured"


# ---------------------------------------------------------------------------------------------
# the funnel: cross-checks, JSON, Markdown
# ---------------------------------------------------------------------------------------------


def _funnel(report, **overrides):  # type: ignore[no-untyped-def]
    """A balanced funnel for the run RUN_FATES describes, so `reconciles` is true unless a test
    breaks one number on purpose.

    Shortlist: 42 considered less 26 removed (dup 2, handled 6, applied 3, lane copy 3, twin 2,
    slate cap 2, cluster cap 2, cut 4 + 2 beyond the slate) = 16 shortlisted of 18 ranked.
    Run: 16 = 10 delivered + 2 dead + 1 gate + 1 deferred + 1 projection + 1 tailoring.
    Projection: 10 projected; the stage drops dead 2, gate 1, review 1, deferred 1, failed 1.
    """
    from pathlib import Path as _P

    from boardwatch.eligibility.catalog import load_rules
    from boardwatch.projection.run import ProjectionLeadOutcome
    from boardwatch.reports.abstain import build_abstain_report
    from boardwatch.reports.run_funnel import (
        GateCounters,
        Lead,
        LivenessCheck,
        RunManifest,
        ScanContext,
        ShortlistCounts,
        SourceOutcome,
        build_projection_counters,
        build_run_funnel,
    )
    from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts

    leads = [
        Lead(
            posting_id=n, title="t", company="c", provider="greenhouse", board_slug="b",
            company_source="user", out_dir=f"/o/{n}", pdf_built=n != 0, locations=None,
            pending_tailor=n == 0,
        )
        for n in range(10)
    ]
    shortlist = ShortlistCounts(
        considered=42, shortlisted=16, hidden_duplicate=2, hidden_handled=6, hidden_applied=3,
        hidden_lane_copy=3, hidden_requisition_twin=2, hidden_slate_cap=2, hidden_cluster_cap=2,
        hidden_below_cutoff=6, beyond_slate=2,
    )
    kwargs = dict(
        run_id=7, started_at=None, finished_at=None,
        manifest=RunManifest(
            code_fingerprint="f", config_hash="c", profile_facts_hash=None,
            profile_row_hash=None, rules_hash=None, status="ok", location_filter_mode="soft",
        ),
        scan=ScanContext(ran=False),
        corpus=CorpusCounts(
            open_postings=100, evaluated=100, no_current_evaluation=0,
            by_verdict={"eligible": 60, "uncertain": 40}, judged_this_run=100,
            cache_hit_prior_run=0, cache_hit_unattributed=0,
        ),
        shortlist=shortlist, sources=[SourceOutcome(
            provider="greenhouse", board_slug="b", company_source="user", open_postings=100,
            eligible=60, leads=10, applied=0, stubs=0,
        )],
        leads=leads, tailor_failed=1,
        liveness=LivenessCheck(checked=16, dead=2, unknown=0),
        gate=GateCounters(judged=14, eligible=13, ineligible=1, uncertain=0, failed_open_batches=0),
        execution_deferred=1, execution_deferred_after_projection=0,
        projection=build_projection_counters({
            ProjectionLeadOutcome.PROJECTED: 10, ProjectionLeadOutcome.CANDIDATE_UNRENDERABLE: 1,
        }),
        projected_lineage_rows=9,
        tailored_artifacts=TailoredArtifactCounts(rows=10, with_pdf=9),
        marked_applied=0, stub_postings=0, rewrite_rows=[], unattributed_evaluations=0,
        abstain=build_abstain_report(
            load_rules(_P("does-not-exist")), {}, not_applicable_families=frozenset()
        ),
        direct_share=report, delivered_direct_from_store=(4, 6),
    )
    kwargs.update(overrides)
    return build_run_funnel(**kwargs)  # type: ignore[arg-type]


def _checks(funnel) -> dict[str, tuple[int, int]]:  # type: ignore[no-untyped-def]
    return {
        c.name: (c.in_memory, c.from_store) for c in funnel.cross_checks
        if c.name.startswith("direct_share:")
    }


def _report(env: Path):  # type: ignore[no-untyped-def]
    ids = _seed(env)
    tally = _rank(env, 0.5)[0].direct_share
    assert tally is not None
    return ids, tally, _attribute(ids, tally)


def test_the_funnel_cross_checks_every_step_against_its_own_counter(env: Path) -> None:
    _, _, report = _report(env)
    funnel = _funnel(report)
    assert _checks(funnel) == {
        "direct_share:entered": (42, 42),
        "direct_share:hidden_duplicate": (2, 2),
        "direct_share:hidden_handled": (6, 6),
        "direct_share:hidden_applied": (3, 3),
        "direct_share:hidden_lane_copy": (3, 3),
        "direct_share:hidden_requisition_twin": (2, 2),
        "direct_share:hidden_slate_cap": (2, 2),
        "direct_share:hidden_cluster_cap": (2, 2),
        "direct_share:capped_by_top_n": (6, 6),   # 4 cut by the ranker + 2 beyond the slate
        "direct_share:withheld_not_live": (2, 2),
        "direct_share:gate_rejected": (1, 1),
        "direct_share:execution_deferred": (1, 1),
        "direct_share:projection_failed": (1, 1),
        "direct_share:tailor_failed": (1, 1),
        "direct_share:delivered": (10, 10),
        "direct_share:delivered_direct": (4, 4),
        "direct_share:unaccounted": (0, 0),
    }
    assert funnel.disagreements == () and funnel.reconciles is True


def test_a_regression_in_any_counter_shows_as_a_named_disagreement(env: Path) -> None:
    """Each existing counter moved by one, on its own: the funnel names that step and stops
    reconciling, rather than the section quietly carrying a wrong number."""
    from dataclasses import replace

    from boardwatch.reports.run_funnel import GateCounters, ShortlistCounts

    _, _, report = _report(env)
    base = _funnel(report)
    shortlist = ShortlistCounts(
        considered=42, shortlisted=16, hidden_duplicate=2, hidden_handled=6, hidden_applied=3,
        hidden_lane_copy=3, hidden_requisition_twin=2, hidden_slate_cap=2, hidden_cluster_cap=2,
        hidden_below_cutoff=6, beyond_slate=2,
    )
    for field in (
        "hidden_duplicate", "hidden_handled", "hidden_applied", "hidden_lane_copy",
        "hidden_requisition_twin", "hidden_slate_cap", "hidden_cluster_cap",
    ):
        moved = replace(shortlist, **{field: getattr(shortlist, field) + 1})
        broken = _funnel(report, shortlist=moved)
        assert [c.name for c in broken.disagreements] == [f"direct_share:{field}"], field
        assert not broken.reconciles
    assert base.reconciles

    cases = {
        "direct_share:capped_by_top_n": dict(
            shortlist=replace(shortlist, hidden_below_cutoff=7)
        ),
        "direct_share:withheld_not_live": dict(
            liveness=type(base.liveness)(checked=16, dead=3, unknown=0)
        ),
        "direct_share:gate_rejected": dict(gate=GateCounters(
            judged=14, eligible=12, ineligible=2, uncertain=0, failed_open_batches=0)),
        "direct_share:execution_deferred": dict(execution_deferred=2),
        "direct_share:tailor_failed": dict(tailor_failed=2),
    }
    for name, override in cases.items():
        names = [c.name for c in _funnel(report, **override).disagreements]
        assert name in names, name


def test_the_unaccounted_remainder_and_a_wrong_delivered_recount_disagree(env: Path) -> None:
    ids, tally, _ = _report(env)
    short = {ids[n]: n == "a2n2" for n in RUN_FATES["delivered"] if n != "c2d2"}
    funnel = _funnel(_attribute(ids, tally, delivered=short))
    assert "direct_share:unaccounted" in [c.name for c in funnel.disagreements]
    assert not funnel.reconciles
    # The store recount says 3 direct leads were delivered where the attribution said 4.
    wrong = _funnel(_attribute(ids, tally), delivered_direct_from_store=(3, 7))
    assert [c.name for c in wrong.disagreements] == ["direct_share:delivered_direct"]


def test_no_checks_unless_the_share_was_measured(env: Path) -> None:
    from boardwatch.rank.direct_share import not_measured

    _, tally, _ = _report(env)
    off = DirectShareTally.off(0.0)
    from boardwatch.rank.direct_share import attribute

    common = dict(
        liveness_ran=True, gate_armed=True, projection_ran=True, dead_ids=[],
        gate_excluded_ids=[], beyond_slate_ids=[], execution_deferred_ids=[],
        projection_failed_ids=[], tailor_failed_ids=[], delivered={},
    )
    for report in (None, attribute(off, **common), not_measured("x")):  # type: ignore[arg-type]
        assert _checks(_funnel(report)) == {}


def test_the_json_section_and_the_markdown_for_the_fixture(env: Path) -> None:
    from boardwatch.reports.run_funnel import funnel_to_dict, funnel_to_markdown

    ids, _, report = _report(env)
    funnel = _funnel(report)
    payload = funnel_to_dict(funnel)
    section = payload["direct_share"]
    assert isinstance(section, dict)
    assert section["instrumented"] is True and section["state"] == "measured"
    assert section["share"] == 0.5 and section["reconciles"] is True
    assert section["reserved"] == 15
    assert section["totals"] == {
        "direct": {
            "entered": 20,
            "removed": {
                "hidden_duplicate": 1, "hidden_handled": 3, "hidden_applied": 1,
                "hidden_lane_copy": 2, "hidden_requisition_twin": 1, "hidden_slate_cap": 1,
                "hidden_cluster_cap": 1, "capped_by_top_n": 2, "withheld_not_live": 1,
                "gate_rejected": 1, "beyond_slate": 1, "execution_deferred": 1,
                "projection_failed": 0, "tailor_failed": 0,
            },
            "delivered": 4, "delivered_review_lane": 0, "unaccounted": 0,
        },
        "non_direct": {
            "entered": 22,
            "removed": {
                "hidden_duplicate": 1, "hidden_handled": 3, "hidden_applied": 2,
                "hidden_lane_copy": 1, "hidden_requisition_twin": 1, "hidden_slate_cap": 1,
                "hidden_cluster_cap": 1, "capped_by_top_n": 2, "withheld_not_live": 1,
                "gate_rejected": 0, "beyond_slate": 1, "execution_deferred": 0,
                "projection_failed": 1, "tailor_failed": 1,
            },
            "delivered": 6, "delivered_review_lane": 1, "unaccounted": 0,
        },
    }
    tiers = section["tiers"]
    assert isinstance(tiers, dict) and sorted(tiers) == ["2", "3"]
    assert tiers["3"]["direct"]["dropped_ids"] == {
        "hidden_handled": [ids["h3d"]],
        "capped_by_top_n": sorted([ids["t3d3"], ids["t3d4"]]),
        "beyond_slate": [ids["t3d2"]],
    }
    assert "dropped_ids" not in tiers["3"]["non_direct"]
    assert payload["artifact_version"] == 9

    text = funnel_to_markdown(funnel)
    block = text[text.index("## Direct share"):]
    block = block[:block.index("\n## ", 5)]
    assert "`slate_direct_share` 0.5, over 2 rank tier(s)." in block
    assert "| entered the interleave | 20 | 22 |" in block
    assert "| reserved positions | 15 | — |" in block
    assert "| hidden_lane_copy | 2 | 1 |" in block
    assert "| delivered | 4 | 6 |" in block
    assert "| unaccounted | 0 | 0 |" in block
    assert "| projection_failed | 0 | 1 |" in block
    assert "DOES NOT RECONCILE" not in block
    assert f"- `hidden_handled`: {', '.join(str(i) for i in sorted(_names(ids, 'h2d', 'r2dh', 'h3d')))}" in block
    assert len(block.splitlines()) < 45, "a short section even when every step removed a direct lead"


def test_markdown_says_off_inert_and_not_measured_in_words(env: Path) -> None:
    from boardwatch.rank.direct_share import attribute, direct_share_lines, not_measured

    common = dict(
        liveness_ran=True, gate_armed=True, projection_ran=True, dead_ids=[],
        gate_excluded_ids=[], beyond_slate_ids=[], execution_deferred_ids=[],
        projection_failed_ids=[], tailor_failed_ids=[], delivered={},
    )
    off = "\n".join(direct_share_lines(attribute(DirectShareTally.off(0.0), **common)))  # type: ignore[arg-type]
    assert "*OFF." in off and "Nothing here is a zero reading" in off and "| entered" not in off
    inert = "\n".join(direct_share_lines(attribute(  # type: ignore[arg-type]
        DirectShareTally.inert(0.5, "no apply-routes.toml in the config directory"), **common)))
    assert "*INERT." in inert and "no apply-routes.toml in the config directory" in inert
    assert "*NOT MEASURED." in "\n".join(direct_share_lines(not_measured("the ranker did not run")))
    assert "*NOT MEASURED." in "\n".join(direct_share_lines(None))


def test_an_unreconciled_report_warns_in_the_markdown(env: Path) -> None:
    from boardwatch.rank.direct_share import direct_share_lines

    ids, tally, _ = _report(env)
    short = {ids[n]: n == "a2n2" for n in RUN_FATES["delivered"] if n != "c2d2"}
    text = "\n".join(direct_share_lines(_attribute(ids, tally, delivered=short)))
    assert "DOES NOT RECONCILE: 1 lead(s)" in text


def test_a_relink_after_ranking_is_counted_both_ways_for_delivered_leads_only(env: Path) -> None:
    # D-689/D-690 write links after the ranker classified each lead. The recount sees the new
    # route, so the cross-check adds `to_direct` and subtracts `off_direct`.
    ids, tally, _ = _report(env)
    delivered = {ids[n] for n in RUN_FATES["delivered"]}
    direct = sorted(p for p in delivered if tally.survivors[p][1])
    other = sorted(p for p in delivered if not tally.survivors[p][1])
    dead = [ids[n] for n in RUN_FATES["dead"]]
    report = _attribute(ids, tally, relinked={
        direct[0]: False,  # a direct lead re-linked to a non-direct URL
        other[0]: True, other[1]: True,  # two non-direct leads re-linked to direct ones
        dead[0]: not tally.survivors[dead[0]][1],  # re-routed but never delivered: not counted
    })
    assert (report.relinked_to_direct, report.relinked_off_direct) == (2, 1)
    # Route totals stay the ranker's: 4 direct delivered, as before.
    assert report.total("direct", "delivered") == 4
    # 4 + 2 - 1 = 5 direct by the stored links: agrees. A recount of 4 (the ranker's count
    # alone) or 7 (the difference added the wrong way) disagrees.
    assert _checks(_funnel(report, delivered_direct_from_store=(5, 5)))[
        "direct_share:delivered_direct"
    ] == (5, 5)
    assert _funnel(report, delivered_direct_from_store=(5, 5)).reconciles
    for wrong in (4, 7):
        funnel = _funnel(report, delivered_direct_from_store=(wrong, 10 - wrong))
        assert [c.name for c in funnel.disagreements] == ["direct_share:delivered_direct"]
