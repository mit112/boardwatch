"""The adaptive slate: `slate_ceiling` lets the delivered slate grow past `--top`, but only by
decided-good leads (ranker tiers 0-1), and never past the ceiling.

The arithmetic is pinned on `_slate_size` directly; the end-to-end tests drive the real runner,
ranker, gate stage (a fake `claude`, see `test_gate_stage`) and funnel, because the claims that
matter are what the tailor received, what the ledger holds and whether the funnel reconciles.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from boardwatch.cli.top_cmd import RankedPosting
from boardwatch.core.settings import Settings, load_settings
from boardwatch.pipeline.runner import _slate_size
from tests.pipeline.test_gate_stage import (
    _depth_pipeline,
    _dispositions,
    _job_of,
    _needs_an_executable_fake,
    _ready,
    _seed,
    env,  # noqa: F401 — pytest fixture
    fake_claude,  # noqa: F401 — pytest fixture
)


def _leads(tiers: list[int]) -> list[RankedPosting]:
    return [
        cast(RankedPosting, SimpleNamespace(posting_id=n, tier=tier))
        for n, tier in enumerate(tiers, start=1)
    ]


def test_the_default_ceiling_is_zero() -> None:
    """Mutation caught: a non-zero default would change every existing tenant's slate."""
    assert Settings(data_dir=Path("d"), config_dir=Path("c")).slate_ceiling == 0


@pytest.mark.parametrize("ceiling", [0, 1, 3])
def test_a_ceiling_at_or_below_top_is_exactly_top(ceiling: int) -> None:
    """Mutation caught: dropping the `ceiling <= top_n` guard — `min(0, ...)` would deliver
    nothing, and a ceiling of 1 would cut a 3-lead slate to 1."""
    assert _slate_size(_leads([1, 1, 1, 1, 1, 2]), top_n=3, ceiling=ceiling) == 3


def test_the_ceiling_grows_the_slate_only_by_decided_good_leads() -> None:
    """Five tier 0-1 leads, three undecided, top 2, ceiling 10: the slate is the five and not the
    eight. Mutation caught: counting every survivor (`len(leads)`) or counting tier 2 as decided
    (`tier <= 2`) would read 8."""
    assert _slate_size(_leads([0, 1, 1, 1, 1, 2, 2, 3]), top_n=2, ceiling=10) == 5


def test_the_slate_never_exceeds_the_ceiling() -> None:
    """Mutation caught: dropping the `min(ceiling, ...)` would read 6."""
    assert _slate_size(_leads([1] * 6 + [2]), top_n=2, ceiling=4) == 4


def test_the_slate_never_shrinks_below_top() -> None:
    """One decided lead, top 3, ceiling 10: undecided leads still fill to top. Mutation caught:
    dropping the `max(top_n, ...)` would read 1."""
    assert _slate_size(_leads([1, 2, 2, 3]), top_n=3, ceiling=10) == 3


def _write_config(data_dir: Path, *, gate_enabled: bool, depth: int, ceiling: int) -> None:
    config_dir = load_settings(data_dir=data_dir).config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        f"slate_ceiling = {ceiling}\n"
        f'[gate]\nenabled = {"true" if gate_enabled else "false"}\nmodel = "sonnet"\n'
        f"batch_size = 13\ncall_timeout_s = 30\ndepth = {depth}\n",
        encoding="utf-8",
    )


def _five_decided_three_fresh(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> tuple[list[int], list[int]]:
    """Run 1 judges six leads `eligible` and delivers one, so five queue as tier 1 (a persisted
    judge `eligible` on an in-field title). Three fresh postings then join, undecided: tier 2."""
    _ready(env)
    first_ids = [_seed(env, slug=f"acme-slate-{n}") for n in range(6)]
    _write_config(env, gate_enabled=True, depth=6, ceiling=0)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    first = _depth_pipeline(env, tmp_path / "apps1", top_n=1)
    assert first.fatal is None, first.fatal
    assert first.gate_eligible == 6
    assert len(first.tailored) == 1, "ceiling 0 must deliver exactly --top"
    delivered = {lead.posting_id for lead in first.tailored}
    decided = [pid for pid in first_ids if pid not in delivered]
    fresh = [_seed(env, slug=f"acme-fresh-{n}") for n in range(3)]
    return decided, fresh


@_needs_an_executable_fake
@pytest.mark.parametrize(
    ("ceiling", "expected", "beyond"),
    # Ceiling 4 ranks only 4 deep, so the fifth decided lead is cut by the ranker, not the slate.
    [(10, 5, 3), (4, 4, 0)],
    ids=["ceiling-above-the-decided-count", "ceiling-binds"],
)
def test_the_run_delivers_every_decided_lead_up_to_the_ceiling_and_reconciles(
    env: Path,  # noqa: F811
    tmp_path: Path,
    fake_claude: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    ceiling: int,
    expected: int,
    beyond: int,
) -> None:
    """Run 2 ranks five tier-1 leads above three tier-2 ones with `--top 2`. With the gate
    DISARMED, so the ceiling alone must make the run rank deep enough to see them.

    Mutations caught: the cut left at `leads[:top_n]` (delivers 2); no `max(rank_limit, ceiling)`
    (only 2 ranked, delivers 2); the tier never stamped on `RankedPosting` (every row tier 3, so
    the slate stays at 2); counting undecided leads (ceiling 10 delivers 8). A dropped
    `min(ceiling, ...)` is NOT caught here — the rank depth already stops at the ceiling — so
    `test_the_slate_never_exceeds_the_ceiling` owns it. The funnel's reconciliation must hold with
    the grown slate, and every lead past it — decided or not — must carry no disposition.
    """
    decided, fresh = _five_decided_three_fresh(env, tmp_path, monkeypatch)
    _write_config(env, gate_enabled=False, depth=0, ceiling=ceiling)

    summary = _depth_pipeline(env, tmp_path / "apps2", top_n=2)

    assert summary.fatal is None, summary.fatal
    delivered = [lead.posting_id for lead in summary.tailored]
    assert len(delivered) == expected, delivered
    assert set(delivered) <= set(decided), "the slate may grow past --top only by tier 0-1 leads"
    assert summary.gate_beyond_slate == beyond

    anchors = _job_of(env, decided + fresh)
    dispositions = _dispositions(env)
    for posting_id in decided + fresh:
        if posting_id not in delivered:
            assert anchors[posting_id] not in dispositions, posting_id

    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["reconciles"] is True, [
        (stage["name"], stage) for stage in payload["stages"] if stage.get("reconciled") is False
    ]
    assert summary.shortlist is not None
    assert summary.shortlist.shortlisted == expected


@_needs_an_executable_fake
def test_undecided_leads_still_fill_to_top_under_a_ceiling(
    env: Path,  # noqa: F811
    tmp_path: Path,
    fake_claude: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five tier-1 leads, `--top 7`, ceiling 10: all five plus two undecided. Mutation caught:
    sizing the slate on the decided count alone (`min(ceiling, decided)`) delivers 5."""
    decided, fresh = _five_decided_three_fresh(env, tmp_path, monkeypatch)
    _write_config(env, gate_enabled=False, depth=0, ceiling=10)

    summary = _depth_pipeline(env, tmp_path / "apps2", top_n=7)

    assert summary.fatal is None, summary.fatal
    delivered = {lead.posting_id for lead in summary.tailored}
    assert len(delivered) == 7
    assert set(decided) <= delivered
    assert len(delivered & set(fresh)) == 2
