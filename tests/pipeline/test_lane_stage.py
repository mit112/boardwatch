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
from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings, load_settings
from boardwatch.lanes import hiringcafe
from boardwatch.lanes.base import (
    CompanyAdmission,
    LaneCompanySnapshot,
    LaneContext,
    LaneResult,
    lane_snapshot,
)
from boardwatch.lanes.facets import LaneFacets
from boardwatch.lanes.linkedin import search_urls
from boardwatch.lanes.outcomes import AcquisitionTally
from boardwatch.pipeline import runner as runner_mod
from boardwatch.pipeline.runner import (
    PipelineSummary,
    _collect_lane,
    _linkedin_lane,
    _run_lanes,
    run_pipeline,
)
from boardwatch.reports.run_funnel import ARTIFACT_VERSION
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import (
    finish_run,
    insert_run,
    save_profile,
    upsert_lane_company,
)
from boardwatch.store.seed_queries import SeedReader, record_seeds, unresolved_seeds
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
        resolver_errors: tuple[str, ...] = (),
        seed_attempts: tuple[tuple[int, bool], ...] = (),
        discovered_seeds: tuple[str, ...] = (),
    ) -> None:
        self._companies = companies
        self._outcomes = outcomes
        self._raises = raises
        # Carried onto the returned `LaneResult` so the stage can be presented a lane that crashed
        # its resolver on a seed (`resolver_errors`), a lane with a drainable backlog
        # (`seed_attempts`), and a lane that discovered seed URLs to persist (`discovered_seeds`),
        # without a real network resolver.
        self._resolver_errors = resolver_errors
        self._seed_attempts = seed_attempts
        self._discovered_seeds = discovered_seeds
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
        return LaneResult(
            snapshots=tuple(snapshots),
            tally=tally,
            resolver_errors=self._resolver_errors,
            seed_attempts=self._seed_attempts,
            discovered_seeds=self._discovered_seeds,
        )


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


def test_a_lane_with_an_override_gets_its_own_cap_and_a_lane_without_falls_back(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-lane cap override. Three lanes, one run, so a bug that applies the override to
    every lane and a bug that ignores the override both fail this test:

      * `overridden` is named in `lane_new_companies_per_run_overrides` with its OWN, smaller
        cap than the shared default.
      * `unlimited` is named with `"unlimited"` and must admit every company offered, well past
        the shared default.
      * `shared` is named nowhere and must fall back to `lane_new_companies_per_run` unchanged.
    """
    overridden = StubLane([("greenhouse", s) for s in ("a", "b", "c")])
    unlimited = StubLane([("greenhouse", s) for s in ("d", "e", "f", "g")])
    shared = StubLane([("greenhouse", s) for s in ("h", "i", "j")])
    overridden.name, unlimited.name, shared.name = "overridden", "unlimited", "shared"
    monkeypatch.setattr(
        runner_mod,
        "LANE_FACTORIES",
        {
            "overridden": lambda _ctx: overridden,
            "unlimited": lambda _ctx: unlimited,
            "shared": lambda _ctx: shared,
        },
    )

    settings = _settings(
        tmp_path,
        lanes_enabled=("overridden", "unlimited", "shared"),
        lane_new_companies_per_run=2,
        lane_new_companies_per_run_overrides={"overridden": 1, "unlimited": "unlimited"},
    )
    reports, errors = _run_lanes(engine, settings, insert_run(engine))

    assert errors == []
    by_name = {report.name: report for report in reports}
    assert len(by_name["overridden"].admitted) == 1, "must use its OWN cap, not the shared 2"
    assert len(by_name["unlimited"].admitted) == 4, "'unlimited' must admit everything offered"
    assert len(by_name["shared"].admitted) == 2, "no override: must fall back to the shared cap"


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
        runner_mod, "LANE_FACTORIES", {"boom": lambda _ctx: boom, "good": lambda _ctx: good}
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
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _ctx: lane})

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
        {"boom": lambda _ctx: StubLane([], raises=RuntimeError("aggregator moved"))},
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
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _ctx: lane})

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
        runner_mod, "LANE_FACTORIES", {"stub": lambda _ctx: StubLane([("hiringcafe", "src:acme")])}
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
    """Every PROFILE facet tuple the stage constructed a lane with.

    The profile half only. Mined facets are a separate source with separate evidence and their
    own tests (`tests/unit/test_lane_facet_mining.py`); folding them in here would make these
    three assertions about the profile pass or fail on delivered-lead history instead.
    """
    handed: list[tuple[str, ...]] = []
    lane = StubLane([("hiringcafe", "src:acme")])

    def _factory(ctx: LaneContext) -> StubLane:
        handed.append(ctx.facets.profile)
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
            runner_mod.LANE_FACTORIES, name, lambda _ctx, _lane=lane: _lane
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


def test_a_resolver_crash_reaches_the_RETURNED_errors_not_only_errors_json(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BLOCKER: a resolver crash must be visible where an operator looks, not only in errors_json.

    `_persist_seed_work` used to write the crash straight to `runs.errors_json` -- a column the CLI,
    the funnel and the morning digest all leave unqueried, so the crash was durable and INVISIBLE at
    once. It has to reach `_run_lanes`' RETURNED errors, which the pipeline extends onto
    `summary.errors` (the morning digest, the console) and `stage_errors` (`runs.errors_json`, via
    `finish_run`). And it must reach `errors_json` ONLY that way -- a direct write here as well would
    double-record it.

    The lane APPLIES CLEANLY (its one company lands), so this is the apply-success path: the crash
    still has to surface. `seed_attempts` rides along because a real crash always leaves the seed's
    attempt beside it -- `_resolve` appends the attempt whether or not it produced a posting.
    """
    crash = "https://careers.hireology.com/x/1/description: RuntimeError('selectolax fell over')"
    _register(
        monkeypatch,
        alpha=StubLane(
            [("hiringcafe", "src:a")],
            resolver_errors=(crash,),
            seed_attempts=((1, False),),
        ),
    )
    run_id = insert_run(engine)
    reports, errors = _run_lanes(engine, _settings(tmp_path, lanes_enabled=["alpha"]), run_id)

    assert [r.name for r in reports] == ["alpha"], "the clean apply must still be reported"
    assert any("crashed the resolver" in e for e in errors), (
        f"a resolver crash must reach the RETURNED errors, not only errors_json: {errors}"
    )
    assert any("selectolax fell over" in e for e in errors), "the first crash's repr must ride along"

    # `finish_run` (the pipeline's own persistence of the returned errors) is the ONE path the
    # crash reaches `errors_json`. Before the fix it was written twice -- directly here AND via
    # `finish_run`; the direct write is gone, so BEFORE `finish_run` there are ZERO notes and AFTER
    # it there is EXACTLY ONE. Asserting only "zero direct writes" would miss a regression that
    # dropped the crash from the returned errors too.
    def _persisted() -> list[str]:
        with engine.connect() as conn:
            return list(
                conn.execute(
                    select(tables.runs.c.errors_json).where(tables.runs.c.id == run_id)
                ).scalar_one()
                or []
            )

    assert not any("crashed the resolver" in note for note in _persisted()), (
        f"no direct write to errors_json (that direct write was the double-record): {_persisted()}"
    )
    finish_run(engine, run_id, errors=errors)
    assert sum("crashed the resolver" in note for note in _persisted()) == 1, (
        f"the crash must be persisted EXACTLY ONCE, and only via finish_run: {_persisted()}"
    )


def test_a_refused_seed_url_reaches_the_RETURNED_errors_not_only_errors_json(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BLOCKER: a refused (unroutable) seed URL must be visible where an operator looks.

    `_persist_seed_work` used to write the refusal straight to `runs.errors_json` -- a column the
    CLI, the funnel and the morning digest all leave unqueried, so a lane emitting URLs nothing can
    route looked exactly like a lane finding nothing. It has to reach `_run_lanes`' RETURNED errors,
    which the pipeline extends onto `summary.errors` (the morning digest, the console) and
    `stage_errors` (`runs.errors_json`, via `finish_run`) -- and reach `errors_json` ONLY that way,
    so it is recorded exactly once. Mirrors the resolver-crash de-dup.

    The lane APPLIES CLEANLY (its one company lands) and discovers two seeds: one routable, one an
    empty-label host `is_seedable_url` refuses. The clean apply must still be reported AND the
    refusal must surface.
    """
    bad, good = "https://tenant..applytojob.com/apply/Z", "https://newco.applytojob.com/apply/Y"
    _register(
        monkeypatch,
        alpha=StubLane([("hiringcafe", "src:a")], discovered_seeds=(good, bad)),
    )
    run_id = insert_run(engine)
    reports, errors = _run_lanes(engine, _settings(tmp_path, lanes_enabled=["alpha"]), run_id)

    assert [r.name for r in reports] == ["alpha"], "the clean apply must still be reported"
    assert any("not safely" in e and "skipped" in e for e in errors), (
        f"a refused seed url must reach the RETURNED errors, not only errors_json: {errors}"
    )
    assert any(bad in e for e in errors), "the first refused url's repr must ride along"

    # Only the good seed persisted; the bad one was refused, never stored as an undrainable row.
    with engine.connect() as conn:
        stored = conn.execute(select(tables.lane_seeds.c.url)).scalars().all()
    assert stored == [good], f"the refused url must not persist: {stored}"

    # `finish_run` is the ONE path the refusal reaches `errors_json`: BEFORE it there are ZERO notes
    # (the direct write that double-recorded is gone) and AFTER it there is EXACTLY ONE.
    def _persisted() -> list[str]:
        with engine.connect() as conn:
            return list(
                conn.execute(
                    select(tables.runs.c.errors_json).where(tables.runs.c.id == run_id)
                ).scalar_one()
                or []
            )

    assert not any("not safely" in note for note in _persisted()), (
        f"no direct write to errors_json (that direct write was the double-record): {_persisted()}"
    )
    finish_run(engine, run_id, errors=errors)
    assert sum("not safely" in note for note in _persisted()) == 1, (
        f"the refusal must be persisted EXACTLY ONCE, and only via finish_run: {_persisted()}"
    )


def test_a_clean_apply_with_a_broken_seed_drain_is_labelled_persistence_not_apply(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SHOULD-FIX: a persistence-only failure must not be reported as `apply failed`.

    `_apply_lane` runs the seed drain even when the apply SUCCEEDED, and a drain that raises there
    is a different fault from a broken apply -- it wants a different fix. Labelling both `apply
    failed` sends an operator to the wrong phase. The apply here LANDS (its company applies
    cleanly); only `record_seed_attempt` raises.
    """
    _register(
        monkeypatch,
        alpha=StubLane([("hiringcafe", "src:a")], seed_attempts=((1, False),)),
    )

    def _drain_broken(*_a: object, **_k: object) -> None:
        raise RuntimeError("the seed drain is broken")

    monkeypatch.setattr(runner_mod, "record_seed_attempt", _drain_broken)
    reports, errors = _run_lanes(
        engine, _settings(tmp_path, lanes_enabled=["alpha"]), insert_run(engine)
    )

    assert reports == [], "a lane whose drain raised produces no report"
    assert len(errors) == 1
    assert "seed persistence failed" in errors[0], errors
    assert "the seed drain is broken" in errors[0]
    assert "apply failed" not in errors[0], (
        "a clean apply with a broken drain must not be mislabelled the apply phase"
    )


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
    empty.mkdir(parents=True)
    _, moved = _run_lanes(
        engine,
        _settings(tmp_path, lanes_enabled=("jobapps",), jobapps_discovery_dir=empty),
        insert_run(engine),
    )
    assert "record format has probably moved" in bumped[0]
    assert "no group folder anywhere" in moved[0]
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


# --- the MINED facet reaches ONE lane, from the user's own delivered leads ------------------


def _delivered_lead(engine: Engine, title: str, *, employers: int) -> None:
    """One title, delivered at `employers` distinct employers, landed the way a run lands it.

    Through `apply_board` and `record_disposition` rather than raw inserts, so the acquisition
    provenance and the ledger row are the ones production writes. `employers` is what the miner's
    two-employer threshold reads, so a helper that used one company would silently test nothing.
    """
    url = search_urls(("seeded facet",))[0]
    for index in range(employers):
        slug = f"employer-{index}"
        with engine.begin() as conn:
            company_id = upsert_lane_company(conn, provider="linkedin", slug=slug, name=slug)
        raw = RawPosting(
            provider_posting_id=f"{slug}-1",
            title=title,
            url=f"https://example.invalid/{slug}",
            locations=["Anywhere"],
            body_text="body",
            raw_json={},
        )
        apply_board(
            engine, lane_snapshot([raw], url), company_id, insert_run(engine), scan_kind="lane"
        )
        with engine.begin() as conn:
            job_id = int(
                conn.execute(
                    select(tables.postings.c.job_id).where(
                        tables.postings.c.company_id == company_id
                    )
                ).scalar_one()
            )
            record_disposition(
                conn,
                job_id,
                disposition="built",
                reason="lead_built",
                policy_version="test-policy",
                now=utcnow(),
            )


def test_the_stage_mines_a_facet_the_profile_never_asked_for(engine: Engine) -> None:
    """The yield claim, asserted where it can actually be broken.

    The profile asks for one title; the leads this program built name another, at two employers.
    Before this change the stage read the profile and nothing else, so the second title was a
    search the lane could never make however many runs delivered it.
    """
    _profile(engine, ["Registered Nurse"])
    _delivered_lead(engine, "Perioperative Nurse", employers=2)

    facets = runner_mod._lane_facets(engine)

    assert facets.profile == ("registered nurse",)
    assert facets.mined == ("perioperative nurse",)


def test_a_store_with_no_delivered_leads_mines_nothing(engine: Engine) -> None:
    """Every store before the program has built anything, and the honest answer there is the
    behaviour that shipped: the profile's facets, and no inference on top of them."""
    _profile(engine, ["Registered Nurse"])

    assert runner_mod._lane_facets(engine) == LaneFacets(profile=("registered nurse",), mined=())


def test_only_the_lane_whose_provenance_can_retire_a_mined_facet_receives_one(
    tmp_path: Path,
) -> None:
    """Routing, and it is not tidiness. The trial record that prunes a barren mined term is the
    LinkedIn lane's own `keywords=` provenance; a lane whose acquisitions leave no such record
    would spend its request budget on terms nothing could ever measure or retire.
    """
    facets = LaneFacets(profile=("registered nurse",), mined=("perioperative nurse",))
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path)

    ctx = LaneContext(settings=settings, facets=facets, rotation_index=0)
    linkedin_lane = runner_mod.LANE_FACTORIES["linkedin"](ctx)
    hiringcafe_lane = runner_mod.LANE_FACTORIES["hiringcafe"](ctx)

    assert linkedin_lane._search_facets == ("registered nurse", "perioperative nurse")
    assert hiringcafe_lane._search_facets == ("registered nurse",)


# --------------------------------------------------------------------------------------
# LinkedIn hub nets: the two boundaries the lane stage owns
# --------------------------------------------------------------------------------------

def test_the_hub_rotation_advances_PER_RUN_and_is_never_a_fixed_constant(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half of the rotation no unit test of `hub_nets` can reach.

    `hub_nets` is tested exhaustively against a `rotation_index` a test hands it. That says
    nothing about which index PRODUCTION hands it, and the whole rotation collapses if the answer
    is a constant: the lane would draw the same cells forever while every test stayed green and
    the run reported that it had searched its nets.

    Two runs are made and the values that actually cross the boundary are compared to the run ids
    the store assigned. It was the calendar date ordinal, which made **two runs on one day draw
    the identical slice** -- so the assertion is deliberately made on two runs created back to
    back, which share a date and must still differ.
    """
    recorded: list[int] = []

    def _factory(ctx: LaneContext) -> StubLane:
        recorded.append(ctx.rotation_index)
        return StubLane([])

    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"linkedin": _factory})
    settings = _settings(tmp_path, lanes_enabled=("linkedin",))
    first, second = insert_run(engine), insert_run(engine)
    _run_lanes(engine, settings, first)
    _run_lanes(engine, settings, second)

    assert recorded == [first, second]
    assert first != second, "two runs must not share a rotation index"


def test_a_mined_facet_is_searched_usa_wide_but_is_never_crossed_with_a_hub(
    tmp_path: Path,
) -> None:
    """The contract `_linkedin_lane` states, pinned where it can be broken silently.

    A USA-wide facet costs one request per term whether it was asked for or inferred, so
    `search_facets` gets both halves. A NET costs one request per term PER HUB, so folding the
    mined half into the matrix multiplies the number of days a full rotation takes by however
    many titles the repo happened to infer that week -- and the user's DECLARED targets reach
    each metro proportionally later, which is the one thing the net exists to do.

    Both halves are asserted: dropping `mined` from `search_facets` would be a real regression
    too, and a test that only checked the nets would not see it.
    """
    lane = _linkedin_lane(
        LaneContext(
            settings=Settings(
                data_dir=tmp_path,
                config_dir=tmp_path,
                lane_search_hubs=("Austin, TX",),
                lane_hub_combos_per_run=99,
            ),
            facets=LaneFacets(profile=("software engineer",), mined=("platform engineer",)),
            rotation_index=0,
        )
    )

    assert lane._search_facets == ("software engineer", "platform engineer")
    assert lane._search_nets == (("software engineer", "Austin, TX"),)


# --------------------------------------------------------------------------------------
# The seed channel: a lane never writes `lane_seeds` itself
# --------------------------------------------------------------------------------------

class SeedLane:
    """A lane that returns seed effects instead of performing them.

    Deliberately holds no engine and no connection. That is the property under test: if a lane
    could write its own seeds it would be a second writer on one SQLite store, running in a
    fetch worker while `apply_board` — the pipeline's single writer — runs on the main thread.
    """

    name = "stub"

    def __init__(
        self,
        *,
        discovered: tuple[str, ...] = (),
        attempts: tuple[tuple[int, bool], ...] = (),
        uncharged_resolved: tuple[int, ...] = (),
        reads: tuple[frozenset[str], int, int] | None = None,
    ) -> None:
        self._discovered = discovered
        self._attempts = attempts
        self._uncharged_resolved = uncharged_resolved
        self._reads = reads
        self.read_back: tuple[str, ...] = ()

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        if self._reads is not None:
            hosts, max_attempts, limit = self._reads
            self.read_back = tuple(
                seed.url
                for seed in self._pending(hosts=hosts, max_attempts=max_attempts, limit=limit)
            )
        return LaneResult(
            snapshots=(),
            tally=AcquisitionTally(),
            discovered_seeds=self._discovered,
            seed_attempts=self._attempts,
            uncharged_resolved=self._uncharged_resolved,
        )


def _seed_rows(engine: Engine) -> list[tuple]:
    with engine.begin() as conn:
        return [
            (r.url, r.host, r.discovered_by, r.attempts, r.resolved_at is not None)
            for r in conn.execute(
                select(tables.lane_seeds).order_by(tables.lane_seeds.c.id)
            )
        ]


def test_a_lanes_discovered_seeds_are_persisted_by_the_runner_not_the_lane(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write half of the seed channel, attributed to the run that applied it.

    The lane returns URLs; the runner records them in the SERIAL apply phase. `discovered_by` is
    the LANE's name and not a value the lane passed, so a lane cannot misattribute its own
    discoveries.
    """
    lane = SeedLane(discovered=("https://WWW.Breezy.HR/p/abc", "https://k2j.careerplug.com/j/1"))
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _ctx: lane})
    run_id = insert_run(engine)

    _run_lanes(engine, _settings(tmp_path, lanes_enabled=("stub",)), run_id)

    assert _seed_rows(engine) == [
        ("https://WWW.Breezy.HR/p/abc", "breezy.hr", "stub", 0, False),
        ("https://k2j.careerplug.com/j/1", "k2j.careerplug.com", "stub", 0, False),
    ]


def test_a_lanes_seed_attempts_are_charged_by_the_runner(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain. A resolver that consumed seeds but whose attempts were never charged retries
    them forever at one request each -- a cost leak with no bound, which is exactly what the
    counter exists to stop."""
    run_id = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://a.test/1", "https://b.test/2"),
            discovered_by="seeder",
            run_id=run_id,
            now=utcnow(),
        )
        ids = [
            s.id
            for s in unresolved_seeds(
                conn, hosts=frozenset({"a.test", "b.test"}), max_attempts=9, limit=9
            )
        ]

    lane = SeedLane(attempts=((ids[0], True), (ids[1], False)))
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _ctx: lane})
    _run_lanes(engine, _settings(tmp_path, lanes_enabled=("stub",)), insert_run(engine))

    assert _seed_rows(engine) == [
        ("https://a.test/1", "a.test", "seeder", 1, True),
        ("https://b.test/2", "b.test", "seeder", 1, False),
    ]


def test_a_redundant_aliass_resolution_is_closed_without_charging_the_ceiling(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A redundant alias resolves WITHOUT a GET, so the runner must close it (`resolved_at`) without
    moving `attempts`. The counter means fetch cost; a row that cost no request must not spend the
    retirement ceiling for it. The seed the lane actually fetched IS charged, so the two rows come
    out with different attempt counts though both are resolved."""
    run_id = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://a.test/1", "https://a.test/1-alias"),
            discovered_by="seeder",
            run_id=run_id,
            now=utcnow(),
        )
        ids = [
            s.id
            for s in unresolved_seeds(
                conn, hosts=frozenset({"a.test"}), max_attempts=9, limit=9
            )
        ]

    fetched, alias = ids
    # Both resolved; the alias resolved without a GET, so the lane lists it as uncharged.
    lane = SeedLane(attempts=((fetched, True), (alias, True)), uncharged_resolved=(alias,))
    monkeypatch.setattr(runner_mod, "LANE_FACTORIES", {"stub": lambda _ctx: lane})
    _run_lanes(engine, _settings(tmp_path, lanes_enabled=("stub",)), insert_run(engine))

    assert _seed_rows(engine) == [
        ("https://a.test/1", "a.test", "seeder", 1, True),
        ("https://a.test/1-alias", "a.test", "seeder", 0, True),
    ]


def test_the_runner_hands_a_lane_a_reader_that_only_returns_its_own_hosts(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read half, exercised through the real stage rather than by calling the query.

    Calling `unresolved_seeds` directly would say nothing about whether the runner actually
    builds a reader and puts it on the context -- a stage that forgot to would leave every
    resolver reporting an empty backlog forever, which reads exactly like a drained one.
    """
    run_id = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(
            conn,
            ("https://a.test/1", "https://b.test/2"),
            discovered_by="seeder",
            run_id=run_id,
            now=utcnow(),
        )

    lane = SeedLane(reads=(frozenset({"b.test"}), 3, 9))
    monkeypatch.setattr(
        runner_mod,
        "LANE_FACTORIES",
        {"stub": lambda ctx: _bind(lane, ctx.pending_seeds)},
    )
    _run_lanes(engine, _settings(tmp_path, lanes_enabled=("stub",)), insert_run(engine))

    assert lane.read_back == ("https://b.test/2",)


def _bind(lane: SeedLane, reader: SeedReader) -> SeedLane:
    """What a real lane's factory does with `ctx.pending_seeds`: capture it."""
    lane._pending = reader  # type: ignore[attr-defined]
    return lane
