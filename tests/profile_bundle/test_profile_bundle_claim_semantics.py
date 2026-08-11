"""Approved-claim semantics: fact eligibility, figure traceability, and protected-token survival (§15).

The rule this file exists to pin is the strict one: **every** numeral in claim text must trace to a
referenced metric's rendered phrasing. Not "every numeral that looks like a measurement" — the design
opens §11 by saying "a number embedded only in claim prose is not an authoritative metric", and a
scanner that tried to tell a real figure from an incidental one would be making exactly the informal
judgement the bundle exists to replace. So a year, a version number, and a "24/7" are all untraceable
figures, and tests say so rather than leaving it to be discovered.

**A carried fixture gap, asserted so it cannot silently close.** The packaged example declares only
`qualitative_only` metric mentions, so every `rendered` path below is exercised by a constructed case.
`test_the_example_declares_no_rendered_metric_mention` states the absence: if a future fixture change
adds one, that test fails and whoever makes the change learns these cases now have fixture coverage
too. Adding one now would move `evidence_set_digest` and every digest pinned against it, which is a
deliberate fixture change and not this slice's business.
"""

from __future__ import annotations

from typing import Any

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.claims import MetricRendering
from boardwatch.profile_bundle.validation import build_context, validate_semantic
from tests.profile_bundle.conftest import SyntheticBundle
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document

CLAIMS = "claims/bullet-candidates.yaml"
SUMMARIES = "claims/summary-candidates.yaml"
METRICS = "metrics/records.yaml"
PROJECT_FACTS = "facts/projects/project.packet-pantry.yaml"
BACKEND = "claim.packet-pantry.backend.001"
THROUGHPUT = "metric.packet-pantry.throughput.001"

#: The example's throughput metric authorises this wording, and it carries both protected tokens.
RENDERED_PHRASING = "sustained approximately 120 items/s"


def context(bundle: SyntheticBundle) -> Any:
    return build_context(bundle.draft, mode="draft", bundle_root=bundle.root)


def findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    return validate_semantic(context(bundle))


def about(bundle: SyntheticBundle, claim_id: str) -> tuple[Any, ...]:
    return tuple(f for f in findings(bundle) if f.record_id == claim_id)


def codes(found: tuple[Any, ...]) -> set[str]:
    return {f.code for f in found}


def edit_claim(bundle: SyntheticBundle, claim_id: str, **changes: Any) -> None:
    def apply(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == claim_id:
                claim.update(changes)

    edit_document(bundle, CLAIMS, apply)


# --------------------------------------------------------------------------------------
# The fixture's own shape
# --------------------------------------------------------------------------------------


def test_the_example_declares_no_rendered_metric_mention(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The carried gap, asserted so closing it is a deliberate act.

    Every `rendered`-path test below constructs its own case. If the packaged example ever declares a
    rendered mention, this fails — which is the signal that those cases have fixture coverage and that
    `evidence_set_digest` has moved.
    """
    ctx = context(synthetic_bundle)
    renderings = {
        mention.rendering for claim in ctx.index.claims for mention in claim.metric_mentions
    }
    assert renderings == {MetricRendering.QUALITATIVE_ONLY}


def test_no_approved_claim_in_the_example_carries_a_numeral(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Which is why the example validates clean under the strict figure rule."""
    ctx = context(synthetic_bundle)
    for claim in ctx.index.claims:
        assert not any(character.isdigit() for character in claim.text), claim.claim_id


# --------------------------------------------------------------------------------------
# Fact eligibility and support
# --------------------------------------------------------------------------------------


def test_an_approved_claim_with_no_required_facts_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_claim(synthetic_bundle, BACKEND, required_fact_ids=[])
    assert IssueCode.CLAIM_WITHOUT_FACTS in codes(about(synthetic_bundle, BACKEND))


def test_a_draft_claim_with_no_required_facts_is_not_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example ships one, and it is legitimate: a draft is wording still being supported.

    Failing the revision over an unfinished draft would make the bundle unable to hold work in
    progress, which is the opposite of "preserve uncertainty rather than resolve it".
    """
    ctx = context(synthetic_bundle)
    draft = next(c for c in ctx.index.claims if c.claim_id == "claim.packet-pantry.draft.001")
    assert draft.required_fact_ids == ()
    assert about(synthetic_bundle, "claim.packet-pantry.draft.001") == ()


def test_a_required_fact_that_is_not_effective_makes_the_claim_ineligible(
    synthetic_bundle: SyntheticBundle,
) -> None:
    def stale_it(data: Any) -> None:
        for fact in data["facts"]:
            if fact["fact_id"] == "fact.packet-pantry.contribution.001":
                fact["verification_state"] = "stale"

    edit_document(synthetic_bundle, PROJECT_FACTS, stale_it)
    found = about(synthetic_bundle, BACKEND)
    finding = next(f for f in found if f.code == IssueCode.CLAIM_FACT_INELIGIBLE)
    assert finding.details["required_record_id"] == "fact.packet-pantry.contribution.001"
    assert finding.details["verification_state"] == "stale"


def test_a_required_metric_with_a_disqualifying_caveat_makes_the_claim_ineligible(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§11 makes it ineligible for projection; §15 requires every referenced record to be eligible.

    Composing the two sentences is what makes an approved bullet resting on a withdrawn methodology an
    error rather than only a blocker on the metric.
    """
    edit_claim(
        synthetic_bundle,
        BACKEND,
        required_metric_ids=["metric.packet-pantry.legacy-score.001"],
        metric_mentions=[
            {
                "metric_id": "metric.packet-pantry.legacy-score.001",
                "rendering": "qualitative_only",
            }
        ],
    )
    found = about(synthetic_bundle, BACKEND)
    ineligible = [f for f in found if f.code == IssueCode.CLAIM_FACT_INELIGIBLE]
    assert ineligible
    assert ineligible[0].details["required_record_id"] == "metric.packet-pantry.legacy-score.001"
    assert "disqualifying caveat" in ineligible[0].message


def test_a_required_fact_blocked_by_an_unresolved_conflict_makes_the_claim_ineligible(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Conflicts block dependent claims and nothing else (§13's locality)."""
    edit_claim(
        synthetic_bundle,
        BACKEND,
        required_fact_ids=sorted(
            ["fact.packet-pantry.contribution.001", "fact.packet-pantry.end-date.001"]
        ),
    )
    found = about(synthetic_bundle, BACKEND)
    assert IssueCode.CLAIM_FACT_INELIGIBLE in codes(found)
    others = about(synthetic_bundle, "claim.example-labs.ownership.001")
    assert others == (), "an unrelated claim must stay usable"


# --------------------------------------------------------------------------------------
# Mention declarations
# --------------------------------------------------------------------------------------


def test_a_required_metric_with_no_mention_entry_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§15: a referenced metric omitted from the text "must be declared `qualitative_only`"."""
    edit_claim(synthetic_bundle, BACKEND, metric_mentions=[])
    found = about(synthetic_bundle, BACKEND)
    finding = next(f for f in found if f.code == IssueCode.CLAIM_METRIC_MENTION_MISSING)
    assert finding.details["required_record_id"] == THROUGHPUT


def test_a_mention_naming_a_metric_the_claim_does_not_require_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_claim(
        synthetic_bundle,
        BACKEND,
        required_metric_ids=[],
        assertion_tags=["built"],
        metric_mentions=[{"metric_id": THROUGHPUT, "rendering": "qualitative_only"}],
    )
    found = about(synthetic_bundle, BACKEND)
    finding = next(f for f in found if f.code == IssueCode.CLAIM_METRIC_MENTION_MISSING)
    assert "does not require" in finding.message


def test_a_qualitative_only_mention_needs_no_phrasing_in_the_text(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The example's own case: the throughput metric is referenced and only alluded to."""
    ctx = context(synthetic_bundle)
    claim = next(c for c in ctx.index.claims if c.claim_id == BACKEND)
    assert claim.mention_by_metric[THROUGHPUT] is MetricRendering.QUALITATIVE_ONLY
    assert RENDERED_PHRASING not in claim.text
    assert about(synthetic_bundle, BACKEND) == ()


# --------------------------------------------------------------------------------------
# Rendered metrics
# --------------------------------------------------------------------------------------


def render_backend_claim(bundle: SyntheticBundle, text: str) -> None:
    """Declare the backend claim's metric `rendered`, with `text` as its wording."""
    edit_claim(
        bundle,
        BACKEND,
        text=text,
        metric_mentions=[{"metric_id": THROUGHPUT, "rendering": "rendered"}],
    )


def test_a_rendered_metric_whose_allowed_phrasing_is_absent_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    render_backend_claim(
        synthetic_bundle, "Built a retry-safe ingestion path with strong throughput."
    )
    found = about(synthetic_bundle, BACKEND)
    finding = next(f for f in found if f.code == IssueCode.METRIC_PHRASING_MISSING)
    assert finding.details["required_record_id"] == THROUGHPUT


def test_a_rendered_metric_in_an_allowed_phrasing_is_accepted(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The positive case, and the one that proves the figure scanner is not simply rejecting digits."""
    render_backend_claim(
        synthetic_bundle, f"Built a retry-safe ingestion path that {RENDERED_PHRASING}."
    )
    found = about(synthetic_bundle, BACKEND)
    assert found == (), [(f.code, f.message) for f in found]


def test_a_forbidden_phrasing_in_the_text_is_rejected(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """"handled thousands of items per second" is exactly the rounding `protected_tokens` exists for."""
    edit_claim(
        synthetic_bundle,
        BACKEND,
        text="Built an ingestion path that handled thousands of items per second.",
    )
    found = about(synthetic_bundle, BACKEND)
    assert IssueCode.METRIC_FORBIDDEN_PHRASING in codes(found)


def test_a_forbidden_phrasing_is_rejected_even_alongside_an_allowed_one(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """An authorised wording does not license an unauthorised one in the same sentence."""
    render_backend_claim(
        synthetic_bundle,
        f"It {RENDERED_PHRASING}, and handled thousands of items per second.",
    )
    found = about(synthetic_bundle, BACKEND)
    assert IssueCode.METRIC_FORBIDDEN_PHRASING in codes(found)


def test_rendering_a_metric_while_dropping_a_protected_token_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A phrasing that carries the number but not the unit is a rendering that lost half the figure.

    Constructed by authorising a unit-free wording on the metric, then using it: the claim renders an
    allowed phrasing, so `METRIC_PHRASING_MISSING` stays silent and only the token check notices.
    """

    def authorise_unitless(data: Any) -> None:
        for metric in data["metrics"]:
            if metric["metric_id"] == THROUGHPUT:
                metric["allowed_phrasings"] = [*metric["allowed_phrasings"], "sustained about 120"]
                metric["protected_tokens"] = ["120", "items/s"]

    edit_document(synthetic_bundle, METRICS, authorise_unitless)
    render_backend_claim(synthetic_bundle, "Built an ingestion path that sustained about 120.")
    found = about(synthetic_bundle, BACKEND)
    assert IssueCode.CLAIM_PROTECTED_TOKEN_DROPPED in codes(found)
    assert IssueCode.METRIC_PHRASING_MISSING not in codes(found)


# --------------------------------------------------------------------------------------
# Figure traceability
# --------------------------------------------------------------------------------------


def test_a_figure_with_no_referenced_metric_at_all_is_untraceable(
    synthetic_bundle: SyntheticBundle,
) -> None:
    edit_claim(
        synthetic_bundle,
        "claim.example-labs.ownership.001",
        text="Led the ingestion service and cut incidents by 40%.",
    )
    found = about(synthetic_bundle, "claim.example-labs.ownership.001")
    assert IssueCode.CLAIM_UNTRACEABLE_FIGURE in codes(found)


def test_a_figure_matching_a_metric_declared_qualitative_only_is_untraceable(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§15: the `qualitative_only` permission "does not allow an unreferenced figure".

    The number is the metric's real value and the metric is referenced — but the claim declared it
    would not be rendered, so the figure has no authorised rendering to trace to.
    """
    edit_claim(
        synthetic_bundle,
        BACKEND,
        text=f"Built an ingestion path that {RENDERED_PHRASING}.",
    )
    found = about(synthetic_bundle, BACKEND)
    assert IssueCode.CLAIM_UNTRACEABLE_FIGURE in codes(found)


def test_a_figure_absent_from_the_rendered_phrasing_is_untraceable(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """One authorised figure does not authorise a second one beside it."""
    render_backend_claim(
        synthetic_bundle, f"It {RENDERED_PHRASING} across 3 regions."
    )
    found = about(synthetic_bundle, BACKEND)
    untraceable = [f for f in found if f.code == IssueCode.CLAIM_UNTRACEABLE_FIGURE]
    assert len(untraceable) == 1
    assert untraceable[0].details["offset"] > 0


def test_the_scanner_is_deliberately_strict_about_incidental_numbers(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A year and an on-call shorthand are untraceable figures, and that is the intended reading.

    Recorded as a test rather than left implicit: the alternative is a scanner that decides which
    numbers "count", which is the informal judgement §11 exists to remove.
    """
    edit_claim(
        synthetic_bundle,
        "claim.example-labs.ownership.001",
        text="Led the ingestion service since 2024 and its 24/7 rotation.",
    )
    found = about(synthetic_bundle, "claim.example-labs.ownership.001")
    untraceable = [f for f in found if f.code == IssueCode.CLAIM_UNTRACEABLE_FIGURE]
    assert len(untraceable) == 3  # 2024, 24, 7


def test_a_diagnostic_locates_a_figure_by_offset_and_never_quotes_the_claim_text(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The wording is the owner's private draft; a report an operator may paste must not carry it."""
    secret = "Led the rollout to 12 undisclosed partners."
    edit_claim(synthetic_bundle, "claim.example-labs.ownership.001", text=secret)
    for finding in findings(synthetic_bundle):
        assert "undisclosed partners" not in finding.message
        assert "undisclosed partners" not in str(finding.details)


def test_a_draft_claims_untraceable_figure_is_not_an_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Same boundary as `CLAIM_WITHOUT_FACTS`: a draft is not yet an authorised wording."""

    def add_figure(data: Any) -> None:
        for claim in data["claims"]:
            if claim["claim_id"] == "claim.packet-pantry.draft.001":
                claim["text"] = "Designed the ingestion path around 3 idempotency keys."

    edit_document(synthetic_bundle, CLAIMS, add_figure)
    assert about(synthetic_bundle, "claim.packet-pantry.draft.001") == ()


def test_a_summary_claim_is_held_to_the_same_figure_rule(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`claims/summary-candidates.yaml` is a different owning file, not a different contract."""

    def add_figure(data: Any) -> None:
        data["claims"][0]["text"] = "Engineer with 7 years of building instrumented services."

    edit_document(synthetic_bundle, SUMMARIES, add_figure)
    found = about(synthetic_bundle, "claim.example.summary.001")
    assert IssueCode.CLAIM_UNTRACEABLE_FIGURE in codes(found)
