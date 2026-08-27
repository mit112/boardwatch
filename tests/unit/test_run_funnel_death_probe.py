"""The funnel's `death_probe` section (D-325) — the pure half.

A detector that quietly stops firing must show up as a number that moved, not as silence, and
this one has an unusual amount of room to stop firing: its measured sensitivity is 6.7% (4 of 60
postings the scanner had PROVED closed; workday 0 of 37), so `closed: 0` is the EXPECTED reading
and is nearly worthless as evidence about the corpus. Every other bucket exists to tell a reader
which of the many zeros they are looking at — a budget that refused everything, a due set with
no URLs, a redirect rule swallowing every gone-status, a drain that never fires.

`artifact_version` stays at 6. Asserted here as well as at the four sites that already pin it,
so the additive-key ruling is visible from the change that relies on it.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.eligibility.catalog import load_rules
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    DeathProbeReport,
    RunFunnel,
    RunManifest,
    ScanContext,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts


def _funnel(death_probe: DeathProbeReport | None = None) -> RunFunnel:
    """The smallest funnel that renders, with only the death-probe section varying."""
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
            # No override dir: `load_rules` falls back to the bundled catalog.
            load_rules(Path("does-not-exist")), {}, not_applicable_families=frozenset()
        ),
        death_probe=death_probe,
    )


def _sample() -> DeathProbeReport:
    return DeathProbeReport(
        due=12,
        unprobeable=2,
        attempted=5,
        budget_refused=7,
        gone=3,
        unknown=1,
        alive=1,
        closed=2,
        strikes_cleared=1,
    )


def test_every_probe_bucket_reaches_the_artifact() -> None:
    payload = funnel_to_dict(_funnel(_sample()))["death_probe"]

    assert payload == {
        "instrumented": True,
        "due": 12,
        "unprobeable": 2,
        "attempted": 5,
        "budget_refused": 7,
        "gone": 3,
        "unknown": 1,
        "alive": 1,
        "closed": 2,
        "strikes_cleared": 1,
    }


def test_an_unswept_run_reports_UNMEASURED_rather_than_zero() -> None:  # noqa: N802
    """The D-022/D-023 rule. `closed: 0` from a run that never swept asserts a measurement
    nobody took, and would read as "the class is healthy" from the same JSON a genuinely clean
    sweep produces. `instrumented` is emitted so a reader never has to infer it from a null."""
    payload = funnel_to_dict(_funnel())["death_probe"]

    assert payload == {
        "instrumented": False,
        "due": None,
        "unprobeable": None,
        "attempted": None,
        "budget_refused": None,
        "gone": None,
        "unknown": None,
        "alive": None,
        "closed": None,
        "strikes_cleared": None,
    }


def test_the_markdown_names_the_measured_sensitivity() -> None:
    """The number this whole section has to be read against. Ship it without, and `closed: 0`
    gets trusted as evidence about the corpus rather than about the probe."""
    rendered = funnel_to_markdown(_funnel(_sample()))

    assert "## Death probe" in rendered
    assert "6.7%" in rendered
    assert "5 of 12 due probed" in rendered
    assert "7 refused by the budget" in rendered


def test_the_markdown_says_UNMEASURED_when_the_sweep_did_not_run() -> None:  # noqa: N802
    rendered = funnel_to_markdown(_funnel())

    assert "not instrumented" in rendered
    assert "NOT the same as nothing having died" in rendered


def test_the_artifact_version_does_not_move_for_the_death_probe_section() -> None:
    """An ADDITIVE top-level key on the D-113 -> D-285 precedent, not a v7.

    v5 bumped because an existing value CHANGED MEANING (`tailor.entered` stopped being the
    ranker's `shortlisted`); v6 bumped because `board_coverage` supplied a denominator the
    `scan` block had been read without. `death_probe` does neither — `liveness` still counts the
    shortlist probe, and every stage's `entered`/`advanced` is untouched. The `lanes` key settled
    the identical question the identical way. Asserted from both directions, because a bump made
    in the constant alone would still change every artifact a consumer reads.
    """
    assert ARTIFACT_VERSION == 6
    assert funnel_to_dict(_funnel())["artifact_version"] == 6
    assert funnel_to_dict(_funnel(_sample()))["artifact_version"] == 6
