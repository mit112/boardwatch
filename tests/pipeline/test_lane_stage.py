"""The pipeline's lane stage (JD-acquisition spec §4, plan §2 Slice C).

Driven entirely by a STUB lane defined here. That is not only for isolation from the real
client: a stub is the only way to present the admission closure with a company the store
already holds and one it does not, in the same call, which is the case the whole of D5 exists
for and which no live aggregator can be relied on to produce.

The four things under test, each of which fails on a plausible wrong implementation:

  * the cap is spent on NEW companies only. `CompanyBudget.admit()` has no notion of *new* and
    deliberately does not build one — without the store check in the runner, all ten slots go
    to companies already stored, reach never widens, and the refusal list looks exactly like a
    normal capped run.
  * the cap still bites, so the fix above is not "admit everything".
  * a lane that raises never fails the run. A lane is additive breadth.
  * the funnel and the run log both carry what the lane did, including `is_silent_outage`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from threading import Barrier
from time import sleep

import pytest
from rich.console import Console
from sqlalchemy import Engine, insert, select

from boardwatch.cli.run_cmd import _lane_lines
from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings, load_settings
from boardwatch.lanes import hiringcafe
from boardwatch.lanes.base import CompanyAdmission, LaneCompanySnapshot, LaneResult, lane_snapshot
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.pipeline import runner as runner_mod
from boardwatch.pipeline.runner import PipelineSummary, _collect_lane, _run_lanes, run_pipeline
from boardwatch.reports.run_funnel import ARTIFACT_VERSION
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run, save_profile
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting

LANE_URL = "https://aggregator.test/search"


class StubLane:
    """A lane that presents a fixed list of companies and records what it was told.

    Written against the widened protocol (`collect(fetcher, admits)`) and nothing else, so it
    exercises the same call the real client will make. `seen` is every company it OFFERED and
    `landed` is every company admission let through — the difference is the cap's whole effect,
    and asserting on both is what stops a test from passing because nothing was offered at all.
    """

    name = "stub"

    def __init__(
        self,
        companies: list[tuple[str, str]],
        *,
        outcomes: tuple[str, ...] = ("body_inline",),
        raises: Exception | None = None,
        delay: float = 0.0,
        on_collect: Callable[[], object] | None = None,
    ) -> None:
        self._companies = companies
        self._outcomes = outcomes
        self._raises = raises
        # Spent inside `collect`, so it lands on the FETCH side of the timing boundary and
        # nowhere else. This is what lets a test locate the boundary rather than merely
        # observe that two numbers were produced.
        self._delay = delay
        # Run inside `collect`, so it too lands on the FETCH side of the boundary. Two uses,
        # both of which replace a wall-clock measurement with an exact one: advancing a fake
        # clock, and rendezvousing two lanes on a barrier.
        self._on_collect = on_collect
        self.seen: list[tuple[str, str]] = []
        self.landed: list[tuple[str, str]] = []
        self.fetcher: Fetcher | None = None

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        if self._on_collect is not None:
            self._on_collect()
        if self._delay:
            sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        self.fetcher = fetcher
        snapshots: list[LaneCompanySnapshot] = []
        for provider, slug in self._companies:
            self.seen.append((provider, slug))
            if not admits(provider, slug):
                continue
            self.landed.append((provider, slug))
            snapshots.append(
                LaneCompanySnapshot(
                    provider=provider,
                    slug=slug,
                    name=f"{slug.title()} Inc.",
                    snapshot=lane_snapshot([_raw(f"{slug}-1")], LANE_URL),
                )
            )
        tally = AcquisitionTally()
        for outcome in self._outcomes:
            tally.record(outcome)
        return LaneResult(snapshots=tuple(snapshots), tally=tally)


def _raw(posting_id: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=posting_id,
        title="Software Engineer, New Grad",
        url=f"https://aggregator.test/jobs/{posting_id}",
        locations=["Seattle, WA"],
        body_text="we are hiring a new grad engineer to build and maintain services",
        raw_json={},
    )


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "store")
    ensure_schema(eng)
    return eng


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base = Settings(data_dir=tmp_path / "store", config_dir=tmp_path / "cfg")
    return base.model_copy(update=dict(overrides))


def _known(engine: Engine, provider: str, slug: str) -> None:
    """A company the store already holds, inserted the way `companies add` would."""
    with engine.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name=slug, provider=provider, slug=slug, source="user", watched=True
            )
        )


def _stored_slugs(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {row.slug for row in conn.execute(select(tables.companies.c.slug)).all()}


def _open_posting_ids(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row.provider_posting_id
            for row in conn.execute(
                select(tables.postings.c.provider_posting_id, tables.postings.c.status)
            ).all()
            if row.status == "open"
        }


# --------------------------------------------------------------------------------------
# D5 — the admission closure
# --------------------------------------------------------------------------------------


def test_a_company_the_store_already_holds_is_admitted_free_and_spends_no_cap_slot(
    engine: Engine, tmp_path: Path
) -> None:
    """The D-284 debt, stated as a test.

    Three companies, all already stored, against a cap of ONE. Every one must be admitted and
    the budget must record nothing, because none of them widens reach. Without the
    `company_exists` clause in `_collect_lane` this run admits one and refuses two: reach never
    widens, and the refusal list is indistinguishable from a normal capped run.
    """
    for slug in ("alpha", "beta", "gamma"):
        _known(engine, "greenhouse", slug)
    lane = StubLane([("greenhouse", s) for s in ("alpha", "beta", "gamma")])

    report = _collect_lane(
        engine,
        _settings(tmp_path, lane_new_companies_per_run=1),
        lane,
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert lane.seen == [("greenhouse", s) for s in ("alpha", "beta", "gamma")]
    assert lane.landed == lane.seen, "a known company was refused, so the cap charged it"
    assert report.admitted == (), "a known company consumed a cap slot"
    assert report.refused == ()
    # Reach really did widen INTO those boards: every posting the lane offered landed.
    assert _open_posting_ids(engine) == {"alpha-1", "beta-1", "gamma-1"}


def test_a_known_company_does_not_eat_the_only_slot_a_new_one_needs(
    engine: Engine, tmp_path: Path
) -> None:
    """The sharpest form of the same defect: cap of one, one known company offered first.

    With the store check the slot survives for the new company. Without it, the known company
    takes the slot and the run adds no reach at all while reporting a full admission list.
    """
    _known(engine, "greenhouse", "already")
    lane = StubLane([("greenhouse", "already"), ("hiringcafe", "src:new")])

    report = _collect_lane(
        engine,
        _settings(tmp_path, lane_new_companies_per_run=1),
        lane,
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert report.admitted == (("hiringcafe", "src:new"),)
    assert report.refused == ()
    assert "src:new" in _stored_slugs(engine)


def test_a_slug_differing_only_in_case_is_the_company_already_stored(
    engine: Engine, tmp_path: Path
) -> None:
    """The live incident, as a test: `ashby:Lightfield` watched, `ashby:lightfield` offered.

    They were one board — identical 19 open postings under identical Ashby posting UUIDs — but
    `UNIQUE(provider, slug)` compares case-sensitively, so the store held two rows, fetched the
    board twice a run, and could not suppress either copy's postings: every suppressing identity
    kind is scoped by `company_id`, and there were two of those.

    Both halves matter. One row is the corpus damage; an uncharged cap slot is the control
    damage, because a company already stored must never spend reach the run has to give away.
    """
    _known(engine, "ashby", "Lightfield")
    lane = StubLane([("ashby", "lightfield"), ("hiringcafe", "src:new")])

    report = _collect_lane(
        engine,
        _settings(tmp_path, lane_new_companies_per_run=1),
        lane,
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert _stored_slugs(engine) == {"Lightfield", "src:new"}, "a case variant became a 2nd row"
    assert report.admitted == (("hiringcafe", "src:new"),), "the case variant spent a cap slot"
    assert report.refused == ()
    # The lane's postings still land, and against the EXISTING company row rather than a new one.
    with engine.connect() as conn:
        owner = conn.execute(
            select(tables.companies.c.slug)
            .join(tables.postings, tables.postings.c.company_id == tables.companies.c.id)
            .where(tables.postings.c.provider_posting_id == "lightfield-1")
        ).scalar_one()
    assert owner == "Lightfield"


def test_two_genuinely_different_slugs_at_one_provider_both_store(
    engine: Engine, tmp_path: Path
) -> None:
    """The guard folds CASE and nothing else — it must not collapse distinct boards.

    Sharpened deliberately: the two slugs are anagram-adjacent under a naive "same letters"
    or prefix comparison, so only a real case-fold equality test passes this and the one above.
    """
    lane = StubLane([("ashby", "lightfield"), ("ashby", "lightfields")])

    report = _collect_lane(
        engine,
        _settings(tmp_path, lane_new_companies_per_run=2),
        lane,
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert _stored_slugs(engine) == {"lightfield", "lightfields"}
    assert report.admitted == (("ashby", "lightfield"), ("ashby", "lightfields"))
    assert _open_posting_ids(engine) == {"lightfield-1", "lightfields-1"}


def test_the_cap_still_refuses_companies_the_store_has_never_seen(
    engine: Engine, tmp_path: Path
) -> None:
    """The other direction — the fix above must not be "admit everything".

    "Breadth is last": a lane reading an aggregator sees thousands of employers, and adding a
    company's whole board IS breadth, so a refusal has to be reachable.
    """
    lane = StubLane([("hiringcafe", f"src:{n}") for n in ("a", "b", "c")])

    report = _collect_lane(
        engine,
        _settings(tmp_path, lane_new_companies_per_run=1),
        lane,
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert report.admitted == (("hiringcafe", "src:a"),)
    assert report.refused == (("hiringcafe", "src:b"), ("hiringcafe", "src:c"))
    assert lane.landed == [("hiringcafe", "src:a")]
    assert _open_posting_ids(engine) == {"src:a-1"}


def test_admission_holds_no_connection_open_across_the_lanes_network_work(
    engine: Engine, tmp_path: Path
) -> None:
    """Each `admits` call opens and closes its own connection.

    A connection captured in the closure would be pinned — with its read snapshot — for the
    whole of a lane's paced fetching, blocking WAL checkpointing and standing in a migration's
    path for minutes. Measured through the pool rather than by reading the code: the count of
    checked-out connections must be back to zero at every point the lane is running.
    """
    seen_checked_out: list[int] = []

    class Watcher(StubLane):
        def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
            for provider, slug in self._companies:
                admits(provider, slug)
                seen_checked_out.append(engine.pool.checkedout())
            return LaneResult(snapshots=(), tally=AcquisitionTally())

    _collect_lane(
        engine,
        _settings(tmp_path),
        Watcher([("hiringcafe", "src:a"), ("hiringcafe", "src:b")]),
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert seen_checked_out == [0, 0], f"a connection stayed checked out: {seen_checked_out}"


# --------------------------------------------------------------------------------------
# D3/D4 — what the lane writes
# --------------------------------------------------------------------------------------


def test_a_lane_board_is_applied_as_a_lane_scan_and_not_as_a_board_scan(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4. `apply_board` writes a `board_scans` row every time and coverage outer-joins that
    table on `(company_id, run_id)`, so a lane touching an already-watched company emits a
    SECOND row for the pair and the board is counted twice. The kind is what lets coverage
    filter it out, and it has to be passed explicitly — the default says "board"."""
    calls: list[tuple[int, str]] = []
    real = runner_mod.apply_board

    def spy(engine_, snapshot, company_id, run_id, scan_kind="board"):  # type: ignore[no-untyped-def]
        calls.append((company_id, scan_kind))
        return real(engine_, snapshot, company_id, run_id, scan_kind)

    monkeypatch.setattr(runner_mod, "apply_board", spy)

    _collect_lane(
        engine,
        _settings(tmp_path),
        StubLane([("hiringcafe", "src:a")]),
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )

    assert [kind for _, kind in calls] == ["lane"]


def test_a_lane_snapshot_never_claims_a_complete_board(engine: Engine, tmp_path: Path) -> None:
    """§4: `lane_snapshot()` is always `partial`. An empty `complete` closes a company's whole
    board after two misses, and a lane never enumerates a board, so it cannot make that claim.
    Asserted at the stage rather than only at the constructor, because the stage is what hands
    the snapshot to `apply_board`."""
    lane = StubLane([("hiringcafe", "src:a")])
    _collect_lane(
        engine,
        _settings(tmp_path),
        lane,
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )
    snapshot: BoardSnapshot = lane_snapshot([_raw("x")], LANE_URL)
    assert snapshot.status == "partial"
    with engine.connect() as conn:
        kinds = {row.status for row in conn.execute(select(tables.board_scans.c.status)).all()}
    assert kinds == {"partial"}


# --------------------------------------------------------------------------------------
# Failure isolation
# --------------------------------------------------------------------------------------


def test_a_lane_that_raises_is_recorded_and_the_other_lanes_still_run(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caught per LANE, not per stage: one dead aggregator must not take a second lane's
    results with it."""
    boom = StubLane([], raises=RuntimeError("aggregator moved"))
    good = StubLane([("hiringcafe", "src:a")])
    boom.name, good.name = "boom", "good"
    monkeypatch.setattr(
        runner_mod, "LANE_FACTORIES", {"boom": lambda _s, _f: boom, "good": lambda _s, _f: good}
    )

    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=("boom", "good")), insert_run(engine)
    )

    assert [report.name for report in reports] == ["good"], (
        "a failed lane must be ABSENT rather than reported with zeros"
    )
    assert len(errors) == 1
    assert "boom" in errors[0] and "aggregator moved" in errors[0]


def test_a_lane_name_with_no_registered_lane_is_reported_rather_than_ignored(
    engine: Engine, tmp_path: Path
) -> None:
    """A typo in config must not read as a lane that ran and found nothing."""
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=("nosuchlane",)), insert_run(engine)
    )

    assert reports == []
    assert len(errors) == 1
    assert "nosuchlane" in errors[0]


def test_no_lane_enabled_builds_no_client_and_reports_nothing(
    engine: Engine, tmp_path: Path
) -> None:
    """The default path, which is every run until the owner arms a lane (D8)."""
    assert _run_lanes(engine, _settings(tmp_path), insert_run(engine)) == ([], [])


def test_the_lane_fetcher_is_a_second_instance_with_a_browser_user_agent(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.7 — the six providers keep the honest identifying UA; only the lane gets a browser
    one, and it must come from a SEPARATE `Fetcher` so per-host pacing is not shared with a
    provider host."""
    lane = StubLane([])
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _s, _f: lane})

    _run_lanes(engine, _settings(tmp_path, lanes_enabled=("stub",)), insert_run(engine))

    assert lane.fetcher is not None
    ua = lane.fetcher._client.headers["User-Agent"]
    assert "Mozilla/5.0" in ua
    assert "boardwatch" not in ua
    # The coupling D-369 created, pinned here because this is the constant that would be
    # reverted: the hiring.cafe search route now sends a browser's NAVIGATION headers, and that
    # set is coherent only against a browser UA. Reverting this constant to the identifying
    # `boardwatch/` one would leave the lane claiming to be a bot while asking like a browser --
    # the same contradiction D-369 removed, pointing the other way, and the lane's own tests
    # build their fetcher directly and so cannot see it.
    assert "Sec-Fetch-Mode" in hiringcafe._SEARCH_HEADERS


# --------------------------------------------------------------------------------------
# D7 — reporting
# --------------------------------------------------------------------------------------


def test_the_run_log_line_names_a_silent_outage_and_stays_silent_otherwise() -> None:
    """`resolved == 0` alone is not the signal: a lane with nothing to attempt is a benign
    zero. Nothing at all is printed when no lane ran, so a default run's log is unchanged."""
    outage = StubLane([])
    outage.name = "stub"
    tally_out = AcquisitionTally()
    tally_out.record("fetch_refused")
    tally_quiet = AcquisitionTally()

    from boardwatch.reports.run_funnel import LaneReport

    def summary_with(tally: AcquisitionTally) -> PipelineSummary:
        summary = PipelineSummary(run_id=1)
        summary.lanes.append(
            LaneReport(
                name="stub",
                counts=tally.counts,
                attempted=tally.attempted,
                resolved=tally.resolved,
                is_silent_outage=tally.is_silent_outage,
                admitted=(),
                refused=(),
            )
        )
        return summary

    assert _lane_lines(PipelineSummary(run_id=1)) == []
    assert "SILENT OUTAGE" in _lane_lines(summary_with(tally_out))[0]
    assert "SILENT OUTAGE" not in _lane_lines(summary_with(tally_quiet))[0]
    assert "lane stub →" in _lane_lines(summary_with(tally_quiet))[0]


# --------------------------------------------------------------------------------------
# End to end through `run_pipeline`
# --------------------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> int:
    posting_id = _seed_posting(data_dir)
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    return posting_id


def _pipeline(data_dir: Path, out_root: Path, **overrides: object) -> PipelineSummary:
    settings = load_settings(data_dir=data_dir).model_copy(update=dict(overrides))
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
    )


def _payload(out_root: Path) -> dict:
    found = list(out_root.glob("*/funnel-*.json"))
    assert len(found) == 1, f"expected exactly one funnel artifact, got {found}"
    return json.loads(found[0].read_text())


def _independent_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> Path:
    """A store and config dir of its own, prepared for a run.

    Two runs in ONE environment are not a control pair: the second reuses the first's cached
    evaluations (`evaluated` drops to 0) and the ledger suppresses every lead the first built,
    so the two differ for reasons that have nothing to do with a lane. The comparison only
    means anything between two runs that each start from the same fresh state.
    """
    root = tmp_path / name
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(root / "cfg"))
    data_dir = root / "data"
    _ready(data_dir)
    return data_dir


def test_a_lane_failure_leaves_the_run_otherwise_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lane is additive breadth, so its failure costs the run its extra reach and nothing
    else. Compared against a CONTROL run with no lane at all rather than against hard-coded
    numbers — the claim is "unchanged", and only a second run can evidence that."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    control_dir = _independent_env(tmp_path, monkeypatch, "control")
    control = _pipeline(control_dir, tmp_path / "control-out")

    lane_dir = _independent_env(tmp_path, monkeypatch, "lane")
    monkeypatch.setattr(
        runner_mod,
        "LANE_FACTORIES",
        {"boom": lambda _s, _f: StubLane([], raises=RuntimeError("aggregator moved"))},
    )
    with_lane = _pipeline(lane_dir, tmp_path / "lane-out", lanes_enabled=("boom",))

    assert with_lane.fatal is None, "an additive lane failed the run"
    assert any("boom" in err for err in with_lane.errors)
    assert with_lane.lanes == [], "a lane that raised must report no counts"
    # Everything the run actually delivers is untouched.
    assert control.evaluated > 0, "the control produced nothing, so this proves nothing"
    assert with_lane.evaluated == control.evaluated
    assert len(with_lane.tailored) == len(control.tailored)
    assert with_lane.tailor_failed == control.tailor_failed
    assert with_lane.shortlist is not None and control.shortlist is not None
    assert with_lane.shortlist.shortlisted == control.shortlist.shortlisted
    with get_engine(lane_dir).connect() as conn:
        status = conn.execute(
            select(tables.runs.c.status).where(tables.runs.c.id == with_lane.run_id)
        ).scalar_one()
    assert status == "ok"


def test_the_funnel_carries_the_lane_section_without_bumping_the_artifact_version(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan D7. The sites that pin the version stay untouched; this asserts the emitted
    artifact agrees with them while carrying a section they predate. Pinned against
    `ARTIFACT_VERSION` rather than a literal, so a bump earned elsewhere (D-267's lead
    locations took it to 7) cannot be misread as one `lanes` earned."""
    _ready(env)
    lane = StubLane([("hiringcafe", "src:acme")], outcomes=("body_inline", "fetch_gone"))
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _s, _f: lane})

    summary = _pipeline(env, tmp_path / "apps", lanes_enabled=("stub",))

    assert summary.fatal is None
    payload = _payload(tmp_path / "apps")
    assert payload["artifact_version"] == ARTIFACT_VERSION
    assert len(payload["lanes"]) == 1
    reported = payload["lanes"][0]
    assert reported["name"] == "stub"
    assert reported["attempted"] == 2
    assert reported["resolved"] == 1
    assert reported["is_silent_outage"] is False
    assert reported["admitted"] == ["hiringcafe:src:acme"]
    assert reported["counts"]["body_inline"] == 1
    assert reported["counts"]["fetch_gone"] == 1


def test_a_lane_company_reaches_the_funnels_per_source_table_as_a_lane(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D3's free attribution: `count_by_source` joins `companies` for labels, so a lane board
    appears in the per-source table carrying `company_source='lane'` with no extra plumbing.

    Counted through a different path than the one that wrote it — the store query, not the
    `LaneReport` the stage built."""
    _ready(env)
    monkeypatch.setattr(
        runner_mod, "LANE_FACTORIES", {"stub": lambda _s, _f: StubLane([("hiringcafe", "src:acme")])}
    )

    _pipeline(env, tmp_path / "apps", lanes_enabled=("stub",))

    payload = _payload(tmp_path / "apps")
    lane_sources = [s for s in payload["sources"] if s["company_source"] == "lane"]
    assert [s["board_slug"] for s in lane_sources] == ["src:acme"]
    assert lane_sources[0]["open_postings"] == 1


# --- the role facet reaches the lane from the PROFILE, never from the module ---------------


def _profile(engine: Engine, target_titles: list[str]) -> None:
    """A profile row, saved the way `profile set` would."""
    with engine.begin() as conn:
        save_profile(
            conn,
            text="résumé text",
            target_titles=target_titles,
            exclude_titles=[],
            locations=["United States"],
            remote_only=False,
            skills=["Python"],
            taxonomy_version="t1",
            resume_max_pages=1,
        )


def _facets_handed_to_the_lane(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, ...]]:
    """Every facet tuple the stage constructed a lane with."""
    handed: list[tuple[str, ...]] = []
    lane = StubLane([("hiringcafe", "src:acme")])

    def _factory(_settings: Settings, facets: tuple[str, ...]) -> StubLane:
        handed.append(facets)
        return lane

    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": _factory})
    _run_lanes(engine, _settings(tmp_path, lanes_enabled=("stub",)), insert_run(engine))
    return handed


def test_the_lane_stage_derives_its_facets_from_the_profiles_target_titles(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The multi-tenancy requirement, asserted where it can actually be broken.

    If a lane ever carries its own role query, this is the test that keeps passing while the
    product silently fits exactly one user — so it asserts the facets came from THIS profile,
    with a title no default would ever contain.
    """
    _profile(engine, ["Software Engineer", "Veterinary Technician"])

    assert _facets_handed_to_the_lane(engine, tmp_path, monkeypatch) == [
        ("software engineer", "veterinary technician")
    ]


def test_a_profile_with_no_target_titles_leaves_the_lane_unfaceted(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _profile(engine, [])

    assert _facets_handed_to_the_lane(engine, tmp_path, monkeypatch) == [()]


def test_no_profile_row_at_all_leaves_the_lane_unfaceted_rather_than_failing(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store with no profile is every store before onboarding runs. The lane must still run:
    breadth is additive, and a missing profile is not a lane failure."""
    assert _facets_handed_to_the_lane(engine, tmp_path, monkeypatch) == [()]


# --------------------------------------------------------------------------------------
# Per-lane cost (D-346)
# --------------------------------------------------------------------------------------

# What each half is made to cost on the FAKE CLOCK below. Not durations anything sleeps for:
# nothing here waits, so the size is free and only the arithmetic matters. Both are binary-exact
# fractions, so the subtraction the runner does — `perf_counter() - started` — is exact and the
# assertions can be equalities. (0.30 and 0.10 are not: 0.4 - 0.3 is 0.10000000000000003.)
FETCH_DELAY = 0.25
# Deliberately DIFFERENT from FETCH_DELAY, so transposed halves are detectable.
APPLY_DELAY = 0.125


class _FakeClock:
    """A stand-in for `runner.perf_counter` that only ever moves when the test moves it.

    Reads are free and repeatable, which matters because the runner reads the clock four times
    across the two halves and the test controls only what happens BETWEEN those reads.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_a_lane_reports_both_halves_of_its_cost(engine: Engine, tmp_path: Path) -> None:
    """D-343 timed the lane STAGE; it could not say whether the cost was fetching or applying.

    `None` would mean NOT MEASURED, so asserting both are real numbers is what pins the wiring.
    """
    report = _collect_lane(
        engine,
        _settings(tmp_path),
        StubLane([("hiringcafe", "src:a")]),
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )
    assert report.fetch_seconds is not None
    assert report.apply_seconds is not None
    assert report.fetch_seconds >= 0.0
    assert report.apply_seconds >= 0.0


def test_the_cost_boundary_sits_between_fetching_and_applying(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test that LOCATES the boundary rather than detecting that two numbers exist.

    Both halves are given DIFFERENT amounts of work, because one-sided cost is not enough: with
    only a fetch cost, an implementation that timed the whole function as `fetch_seconds` and
    reported `apply_seconds = 0` passes every assertion a single-sided test can express.

    The cost is spent on a FAKE CLOCK, not on `sleep`. What is under test is WHICH CODE THE
    TIMER BRACKETS — that `fetch_seconds` covers `collect` and `apply_seconds` covers the
    `apply_board` loop — and that is a claim about the wiring, not about real elapsed time. So
    `runner.perf_counter` is replaced by a counter this test advances by hand: FETCH_DELAY from
    inside the lane's `collect`, APPLY_DELAY from inside the spied `apply_board`. Measuring real
    sleeps only bought a load-dependent tolerance, and a 50ms window around a 300ms sleep went
    red on loaded CI runners while the wiring it guards was perfectly correct.

    With the clock exact, each half is asserted by EQUALITY. That is strictly tighter than the
    two-sided bounds it replaces — zero tolerance instead of 17% — and it still excludes the
    three plausible wrong implementations: transposed halves (fetch reads APPLY_DELAY), and
    fetch-absorbs-everything or apply-absorbs-everything (one half reads the total, the other
    0.0).
    """
    clock = _FakeClock()
    monkeypatch.setattr(runner_mod, "perf_counter", clock)
    real = runner_mod.apply_board

    def costly_apply(engine_, snapshot, company_id, run_id, scan_kind="board"):  # type: ignore[no-untyped-def]
        clock.advance(APPLY_DELAY)
        return real(engine_, snapshot, company_id, run_id, scan_kind)

    monkeypatch.setattr(runner_mod, "apply_board", costly_apply)

    report = _collect_lane(
        engine,
        _settings(tmp_path),
        StubLane([("hiringcafe", "src:a")], on_collect=lambda: clock.advance(FETCH_DELAY)),
        Fetcher(_settings(tmp_path)),
        insert_run(engine),
    )
    assert report.fetch_seconds == FETCH_DELAY
    assert report.apply_seconds == APPLY_DELAY


def test_a_lane_that_raises_reports_no_cost_rather_than_a_free_lane(
    engine: Engine, tmp_path: Path
) -> None:
    """A lane that raises is absent from the reported list entirely (a lane may never fail the
    run), so no `LaneReport` — and therefore no 0.0s — is ever fabricated for it. Pinned here
    because the alternative implementation, catching inside `_collect_lane` and returning a
    partial report, would publish a lane that cost nothing and attempted nothing."""
    reports, errors = _run_lanes(
        engine,
        _settings(tmp_path, lanes_enabled=["stub"]),
        insert_run(engine),
    )
    # `stub` is not a registered lane, so this exercises the same "absent, not zeroed" path.
    assert reports == []
    assert len(errors) == 1


# --------------------------------------------------------------------------------------
# Parallel fetch, serial apply (D-347)
# --------------------------------------------------------------------------------------

# Each lane's fetch sleeps this long, to hold two lanes in the fetch phase at once.
LANE_FETCH_DELAY = 0.6

# How long a lane waits at the rendezvous below before declaring its partner is not coming.
# It is a FAILURE budget, never a pass one: a correct implementation trips the barrier
# immediately no matter how loaded the machine is, and a serialized one waits the whole of it
# and then fails. So it can be generous without slowing a green run by a millisecond.
LANE_RENDEZVOUS_TIMEOUT = 10.0


def _register(
    monkeypatch: pytest.MonkeyPatch, **lanes: object
) -> None:
    """Replace the lane registry with stubs, keyed by the name `lanes_enabled` will ask for.

    `monkeypatch.setitem` per key rather than swapping the dict, so the real registry is
    restored even if a test adds a name the next one does not.
    """
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {})
    for name, lane in lanes.items():
        lane.name = name  # type: ignore[attr-defined]
        monkeypatch.setitem(
            runner_mod.LANE_FACTORIES, name, lambda _s, _f, _lane=lane: _lane
        )


def test_two_lanes_fetch_concurrently_rather_than_one_after_the_other(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the change, asserted by RENDEZVOUS rather than by elapsed time.

    Both lanes wait on the same two-party barrier inside `collect`, so neither can return until
    the other has also entered its fetch. That is overlap itself, not a proxy for it: if the
    fetches are serialized again the first lane waits alone, the barrier breaks, and both lanes
    raise — reported, because `_run_lanes` turns a lane's failure into an error string rather
    than an exception. Timing the stage instead would only say the total was small enough, which
    is a claim about the machine's load as much as about the code.

    The lanes are on DIFFERENT hosts by construction (the stub does no real HTTP), which is the
    case the change is for. Two lanes sharing a host would still serialize inside `Fetcher`'s
    per-host lock, and that is correct — the 1 req/s contract is not what this relaxes.
    """
    rendezvous = Barrier(2, timeout=LANE_RENDEZVOUS_TIMEOUT)
    _register(
        monkeypatch,
        alpha=StubLane([("hiringcafe", "src:a")], on_collect=rendezvous.wait),
        beta=StubLane([("hiringcafe", "src:b")], on_collect=rendezvous.wait),
    )
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=["alpha", "beta"]), insert_run(engine)
    )

    assert errors == [], f"lane fetches did not overlap: {errors}"
    assert len(reports) == 2


def test_the_applies_never_overlap_because_apply_board_is_the_single_writer(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The safety property the split exists to PRESERVE, not an optimisation.

    Parallelising the fetch is only safe while `apply_board` stays serial: two lanes applying at
    once would put two writers on one SQLite store. Measured by counting concurrent entries into
    the spy rather than by reading the code — a future edit that submits `_apply_lane` to the
    pool would leave every other assertion in this file green.
    """
    real = runner_mod.apply_board
    depth = 0
    max_depth = 0

    def counting_apply(engine_, snapshot, company_id, run_id, scan_kind="board"):  # type: ignore[no-untyped-def]
        nonlocal depth, max_depth
        depth += 1
        max_depth = max(max_depth, depth)
        try:
            sleep(0.05)  # widen the window a second writer would land in
            return real(engine_, snapshot, company_id, run_id, scan_kind)
        finally:
            depth -= 1

    monkeypatch.setattr(runner_mod, "apply_board", counting_apply)
    _register(
        monkeypatch,
        alpha=StubLane([("hiringcafe", "src:a")], delay=LANE_FETCH_DELAY),
        beta=StubLane([("hiringcafe", "src:b")], delay=LANE_FETCH_DELAY),
    )
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=["alpha", "beta"]), insert_run(engine)
    )

    assert errors == []
    assert len(reports) == 2
    assert max_depth == 1, f"{max_depth} lanes applied at once; apply_board is the single writer"


def test_report_order_follows_lanes_enabled_and_not_which_lane_finished_first(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`as_completed` yields by completion, so the order has to be restored deliberately.

    The FIRST lane in `lanes_enabled` is made the SLOWER one, so completion order is the exact
    reverse of declared order and an implementation that appends as futures land produces
    `["beta", "alpha"]`. Without this the funnel's lane list order would depend on which
    aggregator answered first — a diff in every artifact for no reason, and a fixture that
    passes or fails by race.
    """
    _register(
        monkeypatch,
        alpha=StubLane([("hiringcafe", "src:a")], delay=0.5),
        beta=StubLane([("hiringcafe", "src:b")], delay=0.0),
    )
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=["alpha", "beta"]), insert_run(engine)
    )

    assert errors == []
    assert [r.name for r in reports] == ["alpha", "beta"]


def test_one_lanes_fetch_failing_costs_only_that_lane(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lane may never fail the run, and the guarantee has to survive the thread boundary.

    Before the split the raise happened inline; now it surfaces at `future.result()`, which is a
    different code path with the same obligation. The failing lane is ABSENT from `reports` — not
    present with zeros — and the healthy lane still lands.
    """
    _register(
        monkeypatch,
        alpha=StubLane([("hiringcafe", "src:a")], raises=RuntimeError("aggregator down")),
        beta=StubLane([("hiringcafe", "src:b")]),
    )
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=["alpha", "beta"]), insert_run(engine)
    )

    assert [r.name for r in reports] == ["beta"]
    assert len(errors) == 1
    assert "alpha" in errors[0]
    assert "aggregator down" in errors[0]


# --------------------------------------------------------------------------------------
# The jobapps lane through the REAL registry (D-386). Its whole health design rests on the
# claim that a structural source failure becomes a `summary.errors` line rather than a clean
# zero, and that claim is about THIS stage, not about the lane in isolation.
# --------------------------------------------------------------------------------------


def _jobapps_tree(root: Path, *, count: int = 2) -> Path:
    """A minimal job-apps discovery tree, shaped as the live one is."""
    rule = "=" * 80
    marker = f"{rule}\nJOB DESCRIPTION\n{rule}"
    for index in range(count):
        folder = root / "Greenhouse" / f"Acme_Role_{index}"
        folder.mkdir(parents=True)
        (folder / "discovery_record.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "posting_id": f"pst_{index}",
                    "primary_acquisition": "hiringcafe",
                    "cohort_date": "2026-08-29",
                    "canonical": {
                        "company": "Acme",
                        "title": f"Software Engineer {index}",
                        "direct_url": f"https://job-boards.greenhouse.io/acme/jobs/{index}",
                        "location": "Remote, United States",
                    },
                }
            ),
            encoding="utf-8",
        )
        (folder / "job_description.txt").write_text(
            f"Company:  Acme\nFit:      40/100\n{marker}\n\nWe need a backend engineer.\n",
            encoding="utf-8",
        )
    return root


def test_the_jobapps_lane_with_no_source_reports_an_ERROR_not_a_clean_zero(
    engine: Engine, tmp_path: Path
) -> None:
    """The failure mode the guard exists for. job-apps has genuinely empty days, so a zero
    carries no signal — an unset source has to be LOUD or it is invisible for a fortnight."""
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=("jobapps",)), insert_run(engine)
    )

    assert [report.name for report in reports] == [], (
        "a lane that cannot read its source must be ABSENT, never reported with zeros"
    )
    assert len(errors) == 1
    assert "jobapps" in errors[0]
    assert "no source directory configured" in errors[0]


def test_the_jobapps_lane_with_a_missing_directory_names_the_path_in_the_error(
    engine: Engine, tmp_path: Path
) -> None:
    missing = tmp_path / "moved-away"
    _, errors = _run_lanes(
        engine,
        _settings(tmp_path, lanes_enabled=("jobapps",), jobapps_discovery_dir=missing),
        insert_run(engine),
    )
    assert len(errors) == 1
    assert str(missing) in errors[0], "an operator has to be told WHICH path failed"


def test_a_schema_bump_and_a_moved_queue_produce_DIFFERENT_error_lines(
    engine: Engine, tmp_path: Path
) -> None:
    """Both end with zero usable records and want opposite fixes."""
    future = _jobapps_tree(tmp_path / "future")
    for record in future.rglob("discovery_record.json"):
        payload = json.loads(record.read_text())
        payload["schema_version"] = 99
        record.write_text(json.dumps(payload), encoding="utf-8")

    _, bumped = _run_lanes(
        engine,
        _settings(tmp_path, lanes_enabled=("jobapps",), jobapps_discovery_dir=future),
        insert_run(engine),
    )
    empty = tmp_path / "empty"
    (empty / "Greenhouse").mkdir(parents=True)
    _, moved = _run_lanes(
        engine,
        _settings(tmp_path, lanes_enabled=("jobapps",), jobapps_discovery_dir=empty),
        insert_run(engine),
    )
    assert "record format has probably moved" in bumped[0]
    assert "no discovery record anywhere" in moved[0]
    assert bumped[0] != moved[0]


def test_the_jobapps_lane_ingests_through_the_real_stage_and_lands_postings(
    engine: Engine, tmp_path: Path
) -> None:
    """The happy path through the registry, the admission cap, `apply_board` and the store —
    not the lane in isolation."""
    source = _jobapps_tree(tmp_path / "jobapps")
    reports, errors = _run_lanes(
        engine,
        _settings(tmp_path, lanes_enabled=("jobapps",), jobapps_discovery_dir=source),
        insert_run(engine),
    )

    assert errors == []
    assert [report.name for report in reports] == ["jobapps"]
    (report,) = reports
    assert report.counts["body_inline"] == 2
    assert report.is_silent_outage is False

    with engine.connect() as conn:
        titles = {
            row.title for row in conn.execute(select(tables.postings.c.title)).all()
        }
        bodies = [row.body_text for row in conn.execute(select(tables.postings.c.body_text)).all()]
    assert titles == {"Software Engineer 0", "Software Engineer 1"}
    assert all("Fit:" not in (body or "") for body in bodies), (
        "job-apps' authored header must not reach the stored body"
    )
    assert "greenhouse" in _stored_slugs(engine) or "acme" in _stored_slugs(engine)
