"""The funnel's `stage_durations` section — where a run's wall clock went.

The artifact could already say what the SCAN cost per provider (`scan.fetch_cost`, D-330) and
nothing at all about the other stages. Run 128 spent 26.8 minutes between its last board apply
and its first lane apply, and no artifact could say on which stage: reconstructing it meant
joining four tables on their side-effect timestamps and guessing at the stages that write no
rows. This section is that measurement.

The load-bearing property is that consecutive marks SUM to the run, so an unaccounted block is
a visible row rather than a missing total; and that an untimed run says `None` rather than
reporting a stageless run.

`artifact_version` is left ALONE (8): this is an additive key, the same ruling `scan.fetch_cost`
took. Asserted here so the reliance on it is visible from the change that relies on it.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.eligibility.catalog import load_rules
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    RunFunnel,
    RunManifest,
    ScanContext,
    StageDuration,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts


def _funnel(stage_durations: tuple[StageDuration, ...] | None = None) -> RunFunnel:
    """The smallest funnel that renders, with only the stage-duration section varying."""
    return build_run_funnel(
        run_id=1,
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
        scan=ScanContext(ran=False),
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
        stage_durations=stage_durations,
    )


_SAMPLE = (
    StageDuration(name="scan", seconds=5568.2),
    StageDuration(name="projection", seconds=1.4),
    StageDuration(name="lanes", seconds=1605.0),
    StageDuration(name="eligibility", seconds=271.9),
)


def test_every_stage_reaches_the_artifact_in_the_order_it_RAN() -> None:  # noqa: N802
    """Not sorted by cost. The whole point is that consecutive marks sum to the run, and a
    reader can only see an unaccounted block between two stages if the rows are in run order —
    sorting them descending would put the 26.8-minute gap that motivated this section at the
    top with nothing beside it to say what it sat between."""
    payload = funnel_to_dict(_funnel(_SAMPLE))["stage_durations"]

    assert payload == [
        {"name": "scan", "seconds": 5568.2},
        {"name": "projection", "seconds": 1.4},
        {"name": "lanes", "seconds": 1605.0},
        {"name": "eligibility", "seconds": 271.9},
    ]


def test_an_untimed_run_reports_NOT_MEASURED_rather_than_a_stageless_run() -> None:  # noqa: N802
    """The D-022/D-023 rule. `[]` from a run nobody timed claims a measurement that was never
    taken and reads identically to a run that ended before its first mark."""
    assert funnel_to_dict(_funnel())["stage_durations"] is None
    assert "**not measured**" in funnel_to_markdown(_funnel())


def test_a_timed_run_that_reached_no_boundary_is_NOT_the_same_as_an_untimed_one() -> None:  # noqa: N802
    """A run that crashed before the scan closed has an empty list, and the artifact must not
    render that as "we did not time this run" — the timing worked and there was nothing to
    report, which is the difference between a broken instrument and a short run."""
    rendered = funnel_to_markdown(_funnel(()))

    assert "no stage boundary was reached" in rendered
    assert "**not measured**" not in rendered
    assert funnel_to_dict(_funnel(()))["stage_durations"] == []


def test_the_markdown_names_each_stages_share_of_the_run() -> None:
    """Seconds alone do not answer "what should I fix first" without dividing by the total in
    your head for every row."""
    rendered = funnel_to_markdown(_funnel(_SAMPLE))

    assert "## Wall clock" in rendered
    assert "`scan`" in rendered and "5568.2" in rendered
    assert "74.8%" in rendered, "the scan's share of 7446.5 s is not rendered"
    assert "**7446.5**" in rendered, "the rows are not totalled"


def test_the_markdown_says_the_TOTAL_is_not_the_whole_process() -> None:  # noqa: N802
    """The last mark closes before the funnel, the morning file and the queue sync — the funnel
    cannot contain its own duration. Without saying so, a table whose shares add to 100% claims
    to account for a run it does not: a 90-second queue sync inside a 100-second run would be
    invisible while every row read as a share of the whole thing."""
    rendered = funnel_to_markdown(_funnel(_SAMPLE))

    assert "not the whole process" in rendered
    assert "delivery-queue sync" in rendered


def test_the_section_is_additive_and_does_not_bump_the_artifact_version() -> None:
    """A new key nothing reads back cannot invalidate a stored artifact — the ruling
    `scan.fetch_cost` took (D-330) and the one this section relies on."""
    assert ARTIFACT_VERSION == 8
    assert funnel_to_dict(_funnel(_SAMPLE))["artifact_version"] == 8
