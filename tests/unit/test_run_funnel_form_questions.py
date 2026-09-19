"""The funnel's `form_questions` section (T96) — the pure half.

The Greenhouse application-form sweep is the only thing in this repo that can see a requirement
that is on the FORM and not in the frozen JD: measured 2026-09-17, three apply-lane leads a hand
pre-flight withdrew each carried a citizenship or export-control hard stop, and a `body_text` grep
for citizen/clearance/ITAR/export returned 0 hits on all three. Until this ticket its counts
reached a console line and no artifact, because the sweep ran inside `_sync_queue` — which the
runner deliberately schedules AFTER the funnel, so the queue can never sit upstream of an artifact
a gate reads. The fix hoists the sweep above the funnel rather than moving the funnel below the
queue; what this file pins is the section that hoist makes possible.

`artifact_version` is left ALONE (8 since T60). Asserted here as well as at the sites that pin it,
so the additive-key ruling is visible from the change that relies on it — the same precedent
`death_probe` and `lanes` were admitted on: no existing value changes meaning, and a consumer that
has never heard of `form_questions` reads exactly what it read before.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.delivery.form_questions import FormQuestionSweep
from boardwatch.eligibility.catalog import load_rules
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    RunFunnel,
    RunManifest,
    ScanContext,
    build_run_funnel,
    funnel_to_dict,
    funnel_to_markdown,
)
from boardwatch.store.run_funnel_queries import CorpusCounts, TailoredArtifactCounts


def _funnel(form_questions: FormQuestionSweep | None = None) -> RunFunnel:
    """The smallest funnel that renders, with only the form-question section varying."""
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
            # Required since D-323 bumped the artifact to v7. `soft` is the default, and this
            # section has nothing to do with the location gate — it is supplied so the helper
            # constructs, not because the value matters here.
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
            # No override dir: `load_rules` falls back to the bundled catalog.
            load_rules(Path("does-not-exist")), {}, not_applicable_families=frozenset()
        ),
        form_questions=form_questions,
    )


def _sample() -> FormQuestionSweep:
    """Every bucket a DIFFERENT number, so a pass-through that crossed two of them fails.

    The five do reconcile — `candidates = cached + fetched + unfetched + budget_refused` — because
    that identity is the one a consumer checks, and a sample that violated it would let a renderer
    ship a section whose own arithmetic does not close.
    """
    return FormQuestionSweep(
        candidates=19,
        cached=4,
        fetched=7,
        unfetched=5,
        budget_refused=3,
    )


def test_every_sweep_bucket_reaches_the_artifact() -> None:
    payload = funnel_to_dict(_funnel(_sample()))["form_questions"]

    assert payload == {
        "instrumented": True,
        "candidates": 19,
        "cached": 4,
        "fetched": 7,
        "unfetched": 5,
        "budget_refused": 3,
    }


def test_an_unswept_run_reports_UNMEASURED_rather_than_zero() -> None:  # noqa: N802
    """The D-022/D-023 rule, and this section is one of the worse places to break it.

    `_sweep_form_questions` already returns `None` for `fetcher is None` and for a budget of 0,
    so "not emitted" is a state the pipeline reaches on every run that is not the daily driver.
    `candidates: 0` from such a run is byte-identical to a real sweep over a slate holding no
    Greenhouse leads — and it would read as "the delivered leads were checked for a form hard
    stop", which is the opposite of what happened. `instrumented` is emitted so a reader never
    has to infer the difference from a null.
    """
    payload = funnel_to_dict(_funnel())["form_questions"]

    assert payload == {
        "instrumented": False,
        "candidates": None,
        "cached": None,
        "fetched": None,
        "unfetched": None,
        "budget_refused": None,
    }


def test_the_section_is_its_own_key_and_moves_no_neighbour() -> None:
    """A third population — the leads this run DELIVERED — and therefore its own block.

    Folded under `liveness` (the shortlist re-fetch) or `death_probe` (the unwatched corpus) its
    counts would be summed with two different questions' answers. Asserted against the unswept
    funnel as well, because an omission-direction bug that emitted the block only when the sweep
    ran would still pass the two tests above.
    """
    swept = funnel_to_dict(_funnel(_sample()))
    unswept = funnel_to_dict(_funnel())

    assert "form_questions" in swept
    assert "form_questions" in unswept
    assert swept["liveness"] == unswept["liveness"]
    assert swept["death_probe"] == unswept["death_probe"]
    assert swept["gate"] == unswept["gate"]


def test_the_markdown_names_the_measured_class_and_the_reach() -> None:
    """The numbers the section has to be read against. `fetched: 0` on a run with candidates is
    an unreachable endpoint, not a clean slate, and a reader with no reach figure cannot tell
    a small section from a broken one."""
    rendered = funnel_to_markdown(_funnel(_sample()))

    assert "## Application forms" in rendered
    assert "19 greenhouse leads delivered" in rendered
    assert "4 already cached" in rendered
    assert "7 fetched" in rendered
    assert "5 unfetched" in rendered
    assert "3 refused by the budget" in rendered
    # The class this whole section exists for, and the honest bound on it.
    assert "22 of 400 apply-lane leads" in rendered
    assert "NEVER produces a verdict" in rendered


def test_the_markdown_says_UNMEASURED_when_the_sweep_did_not_run() -> None:  # noqa: N802
    rendered = funnel_to_markdown(_funnel())

    assert "## Application forms" in rendered
    assert "no delivered lead's Greenhouse form was asked for this run" in rendered
    assert "NOT the same as no lead carrying a form-only hard stop" in rendered


def test_the_artifact_version_does_not_move_for_the_form_questions_section() -> None:
    """An ADDITIVE top-level key on the D-113 -> D-285 precedent: it does not move the version.

    Nothing that already existed changes meaning. `liveness` still counts the shortlist re-fetch,
    `death_probe` still counts the unwatched corpus, every stage's `entered`/`advanced` is
    untouched, and a consumer that has never heard of `form_questions` reads an artifact
    identical to the one it read yesterday. `death_probe` and `lanes` settled the identical
    question the identical way.

    Asserted from BOTH directions, because a bump made in the constant alone would still change
    every artifact a consumer reads, and a bump made only at the emission site would leave the
    constant lying. The literal tracks whatever `main` currently declares; what this test defends
    is that adding `form_questions` leaves it ALONE.
    """
    assert ARTIFACT_VERSION == 8
    assert funnel_to_dict(_funnel())["artifact_version"] == 8
    assert funnel_to_dict(_funnel(_sample()))["artifact_version"] == 8
