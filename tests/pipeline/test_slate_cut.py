"""T368 step 1: the post-gate survivor list recorded at the slate cut, ordering nothing.

The keystone test is `test_the_slate_and_lanes_are_identical_with_the_record_on_and_stubbed_out`:
the list may only be RECORDED. The rest pin what the file says. Expected values come from each
fixture's construction (the seeded postings, the fake judge's fixed answer, the gate rows'
own write order), never from the module's own reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardwatch.core.settings import load_settings
from boardwatch.delivery.review_gate import REVIEW_DIR
from boardwatch.pipeline import runner
from boardwatch.pipeline import slate_cut as sc
from boardwatch.store.db import get_engine
from tests.pipeline.test_gate_stage import (
    _arm_gate_with_depth,
    _depth_pipeline,
    _dispositions,
    _entry_band,
    _gate_row_order,
    _needs_an_executable_fake,
    _ready,
    _seed,
    env,
    fake_claude,
)
from tests.pipeline.test_value_shadow import _verdict_rows

__all__ = ["env", "fake_claude"]  # the fixtures, imported so pytest resolves them here


def _world(
    data_dir: Path, apps: Path, monkeypatch: pytest.MonkeyPatch, *, hold: bool = False
) -> tuple[object, list[int]]:
    """Five postings, `--top 2`, `gate.depth = 5`, a judge that reads every one `eligible` and
    above band: three survivors sit beyond the cut. With `hold`, an above-band reading sends a
    delivered lead to the review lane (`gate.seniority_hold`)."""
    _ready(data_dir)
    ids = [_seed(data_dir, slug=f"acme-cut-{n}") for n in range(5)]
    _arm_gate_with_depth(data_dir, depth=5)
    if hold:
        config = load_settings(data_dir=data_dir).config_dir / "config.toml"
        config.write_text(config.read_text() + "seniority_hold = true\n", encoding="utf-8")
    _entry_band(data_dir)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    monkeypatch.setenv("GATE_FAKE_SENIORITY", "no")
    return _depth_pipeline(data_dir, apps, top_n=2), ids


def _file(apps: Path) -> dict[str, object]:
    (path,) = apps.glob("*/slate-cut-*.json")
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@_needs_an_executable_fake
def test_every_survivor_is_recorded_in_ranker_order_with_its_reading_and_slate_membership(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five survivors, two delivered: the file lists all five, not the delivered two."""
    summary, ids = _world(env, tmp_path / "apps", monkeypatch)
    assert summary.fatal is None, summary.fatal  # type: ignore[attr-defined]
    delivered = [lead.posting_id for lead in summary.tailored]  # type: ignore[attr-defined]
    assert len(delivered) == 2

    report = _file(tmp_path / "apps")
    rows = report["survivors"]
    assert (report["run_id"], report["top_n"], report["slate_size"]) == (
        summary.run_id, 2, 2  # type: ignore[attr-defined]
    )
    assert report["slate_ceiling"] == 0
    # Ranker order: the gate wrote its rows in the order the ranker handed the leads over.
    assert [r["posting_id"] for r in rows] == _gate_row_order(env)  # type: ignore[index]
    assert sorted(r["posting_id"] for r in rows) == sorted(ids)  # type: ignore[index]
    assert [r["position"] for r in rows] == [1, 2, 3, 4, 5]  # type: ignore[index]
    ranks = [r["shortlist_rank"] for r in rows]  # type: ignore[index]
    assert ranks == sorted(ranks) and len(set(ranks)) == 5
    # Slate membership: exactly the leads the run delivered, and the first two in ranker order.
    assert [r["in_slate"] for r in rows] == [True, True, False, False, False]  # type: ignore[index]
    assert [r["posting_id"] for r in rows if r["in_slate"]] == delivered  # type: ignore[index]
    # The fake judge's one answer, judged by THIS run's request.
    for row in rows:  # type: ignore[attr-defined]
        assert (row["decision"], row["seniority_fit"], row["reading"]) == (
            "eligible", "no", "judged"
        )


@_needs_an_executable_fake
def test_a_cached_survivor_with_no_new_gate_row_is_recorded_with_its_cached_reading(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason the list exists: run 2 judges nothing, so the gate wrote no row for the three
    queued survivors, and gate rows alone would show an empty run."""
    _world(env, tmp_path / "apps1", monkeypatch)
    rows_after_run_1 = _verdict_rows(env)
    assert len(rows_after_run_1) == 5

    summary2 = _depth_pipeline(env, tmp_path / "apps2", top_n=2)

    assert summary2.fatal is None, summary2.fatal
    assert summary2.gate_judged == 0
    assert _verdict_rows(env) == rows_after_run_1, "run 2 wrote no gate row"
    rows = _file(tmp_path / "apps2")["survivors"]
    assert len(rows) == 3, "the three survivors run 1 queued"  # type: ignore[arg-type]
    for row in rows:  # type: ignore[attr-defined]
        assert (row["decision"], row["seniority_fit"], row["reading"]) == (
            "eligible", "no", "cached"
        )
    assert [r["in_slate"] for r in rows] == [True, True, False]  # type: ignore[attr-defined]


@_needs_an_executable_fake
def test_tier_and_the_rankers_own_rank_are_recorded_when_a_lead_above_a_survivor_is_removed(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run 1 judges five and delivers two, so three queue as tier 1 (a standing `eligible`).
    Two fresh postings then join at tier 2. In run 2 the liveness sweep withholds the queued
    lead the ranker put FIRST, so every survivor's recorded rank is one above its position:
    the file must carry the ranker's rank and tier, not an index into the survivors."""
    from rich.console import Console

    from boardwatch.core.liveness import Liveness
    from boardwatch.core.settings import load_settings
    from boardwatch.pipeline.runner import run_pipeline

    _world(env, tmp_path / "apps1", monkeypatch)
    queued = [r["posting_id"] for r in _file(tmp_path / "apps1")["survivors"]][2:]  # type: ignore[index]
    fresh = [_seed(env, slug=f"acme-fresh-{n}") for n in range(2)]
    dead_id = queued[0]  # the first queued lead: ranker order, tier 1

    def probe(posting_id: int, url: str) -> Liveness:
        if posting_id == dead_id:
            return Liveness(posting_id, "dead", "refetch_gone", "HTTP 404")
        return Liveness(posting_id, "alive", "refetch_ok", "HTTP 200")

    settings = load_settings(data_dir=env)
    summary = run_pipeline(
        get_engine(env), settings, console=Console(quiet=True), out_root=tmp_path / "apps2",
        resume_path=settings.config_dir / "resume.yaml", skip_scan=True, top_n=2,
        liveness_prober=probe,
    )

    assert summary.fatal is None, summary.fatal
    assert summary.liveness_dead == 1
    rows = _file(tmp_path / "apps2")["survivors"]
    # Hand-built from the fixture: the two queued leads left (tier 1, ranks 2 and 3 behind the
    # withheld first), then the two fresh postings (tier 2, ranks 4 and 5).
    assert [r["posting_id"] for r in rows] == [*queued[1:], *fresh]  # type: ignore[index]
    assert [r["tier"] for r in rows] == [1, 1, 2, 2]  # type: ignore[index]
    assert [r["shortlist_rank"] for r in rows] == [2, 3, 4, 5]  # type: ignore[index]
    assert [r["position"] for r in rows] == [1, 2, 3, 4]  # type: ignore[index]


@_needs_an_executable_fake
def test_the_header_says_whether_the_run_scanned(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_depth_pipeline` runs with `skip_scan=True`: not a nightly."""
    _world(env, tmp_path / "apps", monkeypatch)
    assert _file(tmp_path / "apps")["scan_ran"] is False


@_needs_an_executable_fake
def test_a_survivor_the_judge_never_answered_is_recorded_with_no_reading(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge that fails open leaves every survivor unread: the file says `absent`, never a
    guessed `unclear` or `eligible`."""
    _ready(env)
    [_seed(env, slug=f"acme-cut-{n}") for n in range(3)]
    _arm_gate_with_depth(env, depth=3)
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")

    summary = _depth_pipeline(env, tmp_path / "apps", top_n=2)

    assert summary.fatal is None, summary.fatal
    rows = _file(tmp_path / "apps")["survivors"]
    assert len(rows) == 3  # type: ignore[arg-type]
    for row in rows:  # type: ignore[attr-defined]
        assert (row["decision"], row["seniority_fit"], row["reading"]) == (None, None, "absent")


@_needs_an_executable_fake
def test_each_delivered_survivors_lane_is_the_one_the_lane_split_gave_it(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The split is forced so the two lanes are told apart: the first delivered lead goes to
    review, the second stays in apply, and a lead beyond the cut has no lane."""
    real = runner._lead_lanes

    def split(*args: object, **kwargs: object) -> object:
        lane_of, absent, tenant = real(*args, **kwargs)  # type: ignore[arg-type]
        first = next(iter(lane_of))
        lane_of[first] = (REVIEW_DIR, lane_of[first][1])
        return lane_of, absent, tenant

    monkeypatch.setattr(runner, "_lead_lanes", split)
    summary, _ = _world(env, tmp_path / "apps", monkeypatch)

    assert summary.fatal is None, summary.fatal  # type: ignore[attr-defined]
    rows = _file(tmp_path / "apps")["survivors"]
    assert [r["lane"] for r in rows] == ["review", "apply", None, None, None]  # type: ignore[index]


@_needs_an_executable_fake
def test_the_slate_and_lanes_are_identical_with_the_record_on_and_stubbed_out(
    tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant: the list may only be recorded. Two identical stores and judges, one with
    the record stubbed out; the delivered slate and its order, the gate's tally, every verdict
    written, the `seen` ledger and the folders (the lanes) the leads landed in are the same."""

    def run(name: str, stub: bool) -> tuple[object, list[str], list[str]]:
        monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / f"cfg-{name}"))
        data, apps = tmp_path / f"data-{name}", tmp_path / f"apps-{name}"
        queue_root = tmp_path / f"queue-{name}"
        with monkeypatch.context() as patch:
            patch.setattr(runner, "DEFAULT_QUEUE_ROOT", queue_root)
            if stub:
                patch.setattr(sc.SlateCutRecord, "capture", lambda *a, **k: None)
                patch.setattr(sc.SlateCutRecord, "set_lanes", lambda *a, **k: None)
            summary, _ = _world(data, apps, monkeypatch, hold=True)
        tree = sorted(
            str(path.relative_to(apps)) for path in apps.rglob("*")
            if path.is_file() and not path.name.startswith(("slate-cut", "funnel", "morning",
                                                            "near-miss", "digest"))
            and "queue" not in path.parts
        )
        queue = sorted(
            str(path.relative_to(queue_root)) for path in queue_root.rglob("*")
            if path.is_file()
        )
        return summary, tree, queue

    on_summary, on_tree, on_queue = run("on", stub=False)
    off_summary, off_tree, off_queue = run("off", stub=True)
    on_apps, off_apps = tmp_path / "apps-on", tmp_path / "apps-off"

    def facts(summary: object) -> object:
        return (
            [(lead.title, lead.tier) for lead in summary.tailored],  # type: ignore[attr-defined]
            summary.gate_judged, summary.gate_eligible, summary.gate_beyond_slate,  # type: ignore[attr-defined]
            summary.beyond_slate_ids, summary.fatal,  # type: ignore[attr-defined]
        )

    assert on_summary.tailored, "the run must deliver leads for this comparison to mean anything"  # type: ignore[attr-defined]
    assert on_summary.gate_beyond_slate == 3  # type: ignore[attr-defined]
    assert facts(on_summary) == facts(off_summary)
    assert on_tree == off_tree
    # The folders the delivery queue filed the leads under are the lanes the run produced.
    assert on_queue == off_queue
    assert any(REVIEW_DIR in part for part in on_queue), "the world must exercise the review lane"
    assert _verdict_rows(tmp_path / "data-on") == _verdict_rows(tmp_path / "data-off")
    assert _dispositions(tmp_path / "data-on") == _dispositions(tmp_path / "data-off")
    assert len(list(on_apps.glob("*/slate-cut-*.json"))) == 1
    assert not list(off_apps.glob("*/slate-cut-*"))


@_needs_an_executable_fake
def test_a_record_failure_is_noted_above_the_morning_digest_and_never_fails_the_run(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_a: object, **_k: object) -> object:
        raise RuntimeError("cut probe")

    monkeypatch.setattr(sc, "current_gate_verdicts", broken)
    summary, _ = _world(env, tmp_path / "apps", monkeypatch)

    assert summary.fatal is None, summary.fatal  # type: ignore[attr-defined]
    assert summary.tailored, "the run still delivered"  # type: ignore[attr-defined]
    note = "slate cut record not written: cut probe"
    assert note in summary.errors  # type: ignore[attr-defined]
    assert note in summary.morning.markdown_path.read_text()  # type: ignore[attr-defined]
    assert not list((tmp_path / "apps").glob("*/slate-cut-*"))


@_needs_an_executable_fake
def test_a_run_with_the_gate_off_writes_no_record(env: Path, tmp_path: Path) -> None:
    _ready(env)
    _seed(env)
    summary = _depth_pipeline(env, tmp_path / "apps", top_n=2)
    assert summary.fatal is None, summary.fatal
    assert not list((tmp_path / "apps").glob("*/slate-cut-*"))
    assert "slate_cut" not in [stage.name for stage in summary.stage_durations]
