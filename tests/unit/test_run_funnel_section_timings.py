"""T361. The funnel's `section_timings`: what collecting each funnel section cost.

The nightly spent 598 s and an intraday pass 354-678 s building the funnel, and nothing recorded
which section took it. The key is additive, like `stage_durations`: `artifact_version` stays 9
and no existing key changes meaning; the nightly's artifact is pinned against what the code
before this change wrote.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    HostFetchCost,
    ProviderFetchCost,
    RunFunnel,
    RunManifest,
    ScanContext,
    SectionTiming,
    StageDuration,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts


def _scanning_funnel() -> RunFunnel:
    """A scanning run's funnel with every scan-derived field populated, and nothing timed."""
    return build_run_funnel(
        run_id=2910,
        started_at=None,
        finished_at=None,
        manifest=RunManifest(
            code_fingerprint="f",
            config_hash="c",
            profile_facts_hash=None,
            profile_row_hash=None,
            rules_hash=None,
            status="ok",
            location_filter_mode="soft",
        ),
        scan=ScanContext(
            ran=True,
            boards_attempted=7,
            boards_complete=4,
            boards_partial=1,
            boards_unchanged=1,
            boards_failed=1,
            dead_boards=("acme",),
            postings_seen=120,
            fetch_cost=(
                ProviderFetchCost(provider="greenhouse", boards=4, seconds=12.5, untimed=0),
            ),
            host_cost=(
                HostFetchCost(
                    host="boards-api.greenhouse.io", requests=9, attempts=10, span_seconds=11.0,
                    service_seconds=8.0, pace_seconds=2.0, lock_wait_seconds=0.5, in_flight=2,
                ),
            ),
            watched_never_complete=(),
            watched_stale_complete=(),
        ),
        corpus=CorpusCounts(
            open_postings=0,
            evaluated=0,
            no_current_evaluation=0,
            by_verdict={},
            judged_this_run=0,
            cache_hit_prior_run=0,
            cache_hit_unattributed=0,
        ),
        shortlist=None,
        sources=(),
        leads=(),
        tailor_failed=0,
        tailored_artifacts=TailoredArtifactCounts(rows=0, with_pdf=0),
        marked_applied=0,
        stub_postings=0,
        rewrite_rows=(),
        unattributed_evaluations=0,
        abstain=build_abstain_report(
            load_rules(Path("does-not-exist")), {}, not_applicable_families=frozenset()
        ),
        stage_durations=(StageDuration(name="scan", seconds=3703.1236),),
        errors=["one"],
    )


_ROWS = (
    SectionTiming(name="corpus", seconds=63.2564),
    SectionTiming(name="dedup", seconds=161.8),
)

# sha256 of the canonical JSON of `_scanning_funnel()` through `funnel_to_dict`, with the
# `section_timings` key removed, computed on the code BEFORE this ticket. It fails if any
# existing key moved or changed meaning, which comparing the output against itself cannot.
_PRE_T361_SCANNING_JSON_SHA256 = "b47a3f2fa3c8d9c6e2b7d28893773a067c518f093dc4e583709bbf71e557ac82"


def _canonical(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_each_section_reaches_the_artifact_in_the_order_it_was_collected() -> None:
    funnel = replace(_scanning_funnel(), section_timings=_ROWS)

    assert funnel_to_dict(funnel)["section_timings"] == [
        {"name": "corpus", "seconds": 63.256},
        {"name": "dedup", "seconds": 161.8},
    ]


def test_the_markdown_tabulates_each_section_and_its_total() -> None:
    markdown = funnel_to_markdown(replace(_scanning_funnel(), section_timings=_ROWS))

    assert "| `corpus` | 63.3 |" in markdown
    assert "| `dedup` | 161.8 |" in markdown
    assert "| **total** | **225.1** |" in markdown


def test_an_untimed_funnel_says_null_rather_than_reporting_no_sections() -> None:
    """`None` is NOT MEASURED, which is not `[]`: a table of zero sections would claim a timing
    nobody took. The markdown carries no table at all."""
    funnel = _scanning_funnel()

    assert funnel_to_dict(funnel)["section_timings"] is None
    assert "Collection cost by funnel section" not in funnel_to_markdown(funnel)


def test_the_key_is_additive_and_does_not_bump_the_artifact_version() -> None:
    assert ARTIFACT_VERSION == 9
    assert funnel_to_dict(replace(_scanning_funnel(), section_timings=_ROWS))[
        "artifact_version"
    ] == 9


def test_a_scanning_runs_artifact_is_unchanged_apart_from_the_timing_key() -> None:
    """The nightly's content does not move (its reader keeps working): with the timing key
    removed, the artifact is byte-identical to what the code before T361 wrote for the same
    funnel, timed or not."""
    for timings in (None, _ROWS):
        payload = funnel_to_dict(replace(_scanning_funnel(), section_timings=timings))
        payload.pop("section_timings")

        assert _canonical(payload) == _PRE_T361_SCANNING_JSON_SHA256


def test_a_raising_report_callback_loses_neither_the_row_nor_the_sections_own_error() -> None:
    from boardwatch.pipeline.funnel_writer import SectionClock

    def failing(row: SectionTiming) -> None:
        raise OSError("log closed")

    clock = SectionClock(failing)
    with clock.time("corpus"):
        pass  # a section whose read succeeded must not be aborted by its progress line
    with pytest.raises(ValueError, match="the read failed"), clock.time("dedup"):
        raise ValueError("the read failed")  # the section's exception, not the callback's

    assert [row.name for row in clock.rows] == ["corpus", "dedup"]
