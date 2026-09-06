"""FETCH wall clock per provider (D-330) — the run-cost unit the artifact never had.

`board_scans.started_at -> finished_at` cannot answer "what did this board cost": `apply_board`
is handed an already-fetched snapshot and stamps `started_at` at the top of the APPLY, so those
timestamps summed to ~26 s of a ~3,300 s production run. The only other signal was the gap
between consecutive scan completions, and the scan fetches through a `scan_workers`-wide pool,
so those gaps sum to wall clock by construction. Hence a measurement at the fetch seam.
"""

from pathlib import Path
from typing import Any

import httpx
import respx
from provider_cases import ProviderCase
from sqlalchemy import Engine, insert

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.settings import Settings
from boardwatch.reports.run_funnel import ProviderFetchCost
from boardwatch.scan.coordinator import run_scan
from boardwatch.scan.workers import fetch_board_job
from boardwatch.store import tables


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)


def _add_company(engine: Engine, slug: str, provider: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider=provider, slug=slug, source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


# ------------------------------------------------------------------ the measurement itself

def test_a_scanned_board_records_its_fetch_seconds(
    engine: Engine, tmp_path: Path, case: ProviderCase
) -> None:
    """The seam every scanned board passes through must produce a number, per provider."""
    _add_company(engine, "acme", case.name)
    with respx.mock:
        respx.get(case.board_url()).mock(
            return_value=httpx.Response(200, content=case.wrap(case.jobs()[:2]))
        )
        summary = run_scan(engine, _settings(tmp_path))

    assert set(summary.fetch_cost) == {case.name}
    cost = summary.fetch_cost[case.name]
    assert cost.boards == 1
    assert cost.untimed == 0
    assert cost.seconds > 0.0


def test_a_failed_fetch_is_still_charged_for_the_seconds_it_burned(
    engine: Engine, tmp_path: Path, case: ProviderCase
) -> None:
    """A board that spends its time failing still cost the run that time.

    Charging only successful fetches would make the expensive failures — the timeouts and the
    bot-walls, exactly the boards worth dropping — invisible in the cost report.
    """
    _add_company(engine, "acme", case.name)
    with respx.mock:
        respx.get(case.board_url()).mock(return_value=httpx.Response(500))
        summary = run_scan(engine, _settings(tmp_path))

    assert summary.failed == 1
    cost = summary.fetch_cost[case.name]
    assert cost.boards == 1
    assert cost.seconds > 0.0
    assert cost.untimed == 0


def test_the_worker_seam_times_a_snapshot_the_provider_already_marked_failed() -> None:
    """`fetch_board_job` must not special-case the provider's own failure mapping."""

    class _Failing:
        def fetch_board(self, _fetcher: Any, request: BoardRequest) -> BoardSnapshot:
            return BoardSnapshot(
                status="failed", postings=[], url=request.url, error="boom"
            )

    request = BoardRequest(provider="greenhouse", slug="acme", url="https://example.test/b")
    snapshot = fetch_board_job(_Failing(), None, request)  # type: ignore[arg-type]
    assert snapshot.status == "failed"
    assert snapshot.fetch_seconds is not None
    assert snapshot.fetch_seconds >= 0.0


# ------------------------------------------------------- untimed is never folded into the sum

def test_an_untimed_board_is_never_folded_into_the_mean() -> None:
    """`untimed` is its own field so a partial number reads as partial.

    Folding an untimed board in as 0.0 seconds would drag the mean DOWN, which is the
    direction that makes an expensive provider look affordable.
    """
    row = ProviderFetchCost(provider="workday", boards=4, seconds=80.0, untimed=2)
    assert row.mean_latency_seconds == 40.0  # 80 / 2 timed, NOT 80 / 4


def test_a_fully_untimed_provider_reports_no_mean_rather_than_zero() -> None:
    row = ProviderFetchCost(provider="workday", boards=3, seconds=0.0, untimed=3)
    assert row.mean_latency_seconds is None


# --------------------------------------- not measured is a different claim from measured-empty

def test_the_markdown_distinguishes_not_measured_from_nothing_timed() -> None:
    """A `--no-scan` run measured nothing; a scan that timed nothing is a DEFECT. Reporting
    both as an empty table would hide the second inside the first."""
    from boardwatch.reports.run_funnel import _fetch_cost_markdown

    assert "not measured" in "\n".join(_fetch_cost_markdown(None))
    assert "no board was timed" in "\n".join(_fetch_cost_markdown(()))


def test_the_markdown_states_the_unit_it_is_NOT() -> None:
    """The number is provider LATENCY. Predicting added wall clock means dividing by
    `scan_workers`, and conflating the two is what made a 14 s/board average mispredict a
    346-board run by 24 minutes. The artifact says so where the number is read."""
    from boardwatch.reports.run_funnel import _fetch_cost_markdown

    rendered = "\n".join(
        _fetch_cost_markdown((ProviderFetchCost("workday", 114, 2512.0),))
    )
    assert "scan_workers" in rendered
    assert "not the wall clock" in rendered.lower()


def test_the_costliest_provider_is_the_first_row() -> None:
    """Ordered by cost so the constraint is what a reader sees first, not alphabetical luck."""
    from boardwatch.reports.run_funnel import _fetch_cost_markdown

    rows = (
        ProviderFetchCost("ashby", 60, 51.0),
        ProviderFetchCost("workday", 114, 2512.0),
        ProviderFetchCost("greenhouse", 107, 126.0),
    )
    rendered = _fetch_cost_markdown(rows)
    body = [line for line in rendered if line.startswith("| `")]
    assert body[0].startswith("| `workday`")
    assert body[-1].startswith("| `ashby`")


def test_the_artifact_version_does_not_move_for_the_fetch_cost_key() -> None:
    """ADDITIVE, on the D-113 -> D-285 -> D-325 precedent, so no bump.

    The bumps that DID happen changed how an existing value must be read: v5 because
    `tailor.entered` stopped meaning the ranker's `shortlisted`, v6 because `board_coverage`
    supplied a denominator the `scan` block had been read without, v7 for D-323's lead
    locations. `scan.fetch_cost` changes the meaning of nothing already in the artifact —
    `boards_attempted`, `boards_complete`, `boards_failed` and `postings_seen` all count
    exactly what they counted before, and a consumer that ignores the new key is not wrong,
    merely uninformed.

    Pinned from the constant because a bump made there alone would still change every artifact
    a consumer reads, and pinned in THIS file because the equivalent pin in the death-probe
    suite went stale the moment D-323 landed — a literal that nothing re-derives needs a test
    per change, not one shared one.
    """
    from boardwatch.reports.run_funnel import ARTIFACT_VERSION

    assert ARTIFACT_VERSION == 8
