"""P5 precision scorer — the Gate P5 measurement machine (design-p5b.md B0).

Gate P5 (PROGRAM.md §3.P5): precision >= 0.95 on INELIGIBLE on a human-verified
labeled set, abstain rate reported per rule, and 0 INELIGIBLE without a quoted span.
This module produces those numbers. It is the *mechanism* — no user data — and every
verdict-changing P5 rule (B1..B4) must run through it and hold precision before it ships;
building rules before this scorer exists reproduces job-apps' anti-pattern §11.6 (a
procedure that cannot produce the evidence it needs).

**Scored under the reference all-blocker policy, not a user's tolerance** (PROGRAM.md:384).
Under the shipped all-`preference` default, INELIGIBLE is structurally 0 — engine.evaluate's
`blocking()` finds no `blocker` family — so precision is 0/0 and undefined. The reference
policy sets every DECLARED family to `blocker` so the gate measures the RULES, not a user's
policy. Mit's personal policy is a separate, unscored instance.

The deferred-audit drain is mechanical, not a printed warning: `LabeledCase.label_provenance`
marks a row `"oracle"` (AI-judged only) or `"audited"` (human-checked), `PrecisionReport.
audited_coverage` measures the audited fraction of the labeled set, and `meets_ship_gate`
refuses to pass unless BOTH precision and audited coverage clear their bars — so an
all-oracle, zero-audit run cannot ship on `meets_gate` alone.

This module changes as the mechanism it measures changes — this file legitimately changes
here too — but it still lives OUTSIDE the digested engine set (catalog/detect/resolve/engine):
adding a helper to any of those re-keys the whole cached corpus via `engine_version()`, while
edits here do not. The "0 INELIGIBLE without a span" property is defined here once
(`carries_valid_span`) and shared with the P5a S1 corpus gate so the two cannot drift.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.engine import EvaluationResult, evaluate
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.resolve import UNKNOWN
from boardwatch.store.eligibility import RequirementItem

LABELED_VERDICTS = frozenset({"eligible", "ineligible", "uncertain"})

# Placeholder bar for PrecisionReport.meets_ship_gate's audited-coverage requirement.
# Mit confirms the real value at ship time; 0.20 is not a measured or negotiated number.
SHIP_AUDIT_COVERAGE_BAR: float = 0.20


class LabeledSetError(ValueError):
    """A curated labeled row is malformed. Fails LOUD on purpose: unlike stored
    production JSON (parse_facts fails closed to empty facts), a bad row in the human
    ground-truth set would silently mis-score the gate."""


def reference_all_blocker_policy(catalog: RulesCatalog) -> Policy:
    """PROGRAM.md:384 reference policy: every catalog family a `blocker`.

    Derived from `catalog.families`, so a family added in B4 is scored without editing
    this — the reason it is a code constant rather than a pinned yaml fixture (no drift,
    no SHIPPED_DATA entry to keep in step with the catalog)."""
    return Policy(families={family.id: "blocker" for family in catalog.families})


def blocking_requirements(
    result: EvaluationResult, severity: dict[str, str]
) -> list[RequirementItem]:
    """The requirement rows engine.evaluate counts as blocking an INELIGIBLE verdict:
    a `required` UNMET detection in a `blocker` family (engine.evaluate.blocking(UNMET)).
    Requirements are built in lockstep with those rows, so every blocking row has a
    matching RequirementItem here."""
    return [
        req
        for req in result.requirements
        if req.requiredness == "required"
        and req.disposition == "unmet"
        and req.rule_id is not None
        and severity.get(req.rule_id.split(":")[0]) == "blocker"
    ]


def carries_valid_span(
    result: EvaluationResult, severity: dict[str, str], body_text: str
) -> bool:
    """True iff this result has at least one blocking requirement and EVERY blocking
    requirement carries a well-ordered span slicing non-empty text from `body_text` —
    the keystone "INELIGIBLE must carry a quoted span", matching the corpus gate."""
    blocking = blocking_requirements(result, severity)
    if not blocking:
        return False
    for req in blocking:
        span = req.jd_locator.get("span")
        if span is None:
            return False
        start, end = span[0], span[1]
        if not (0 <= start < end) or not body_text[start:end]:
            return False
    return True


@dataclass(frozen=True)
class LabeledCase:
    """One human-verified row: a frozen JD body, the candidate facts it is judged
    against, the verified verdict under the reference policy, and — for an INELIGIBLE —
    the quoted span(s) the human cited."""

    label: str
    body_text: str
    facts: Facts
    expected_verdict: str
    spans: tuple[tuple[int, int], ...] = ()
    source: str | None = None
    label_provenance: str | None = None


@dataclass(frozen=True)
class Mismatch:
    label: str
    expected: str
    predicted: str


@dataclass(frozen=True)
class PrecisionReport:
    total: int
    predicted_ineligible: int
    true_ineligible: int
    ineligible_true_positives: int
    precision: float | None
    recall: float | None
    abstain_rate_by_rule: dict[str, float]
    span_violations: tuple[str, ...]
    false_positives: tuple[Mismatch, ...]
    mismatches: tuple[Mismatch, ...]
    audited_coverage: float

    @property
    def is_measurable(self) -> bool:
        """The set must contain a true INELIGIBLE, or the gate is vacuous (a set with
        no hard stops trivially has no false positives)."""
        return self.true_ineligible > 0

    def meets_gate(self, threshold: float = 0.95) -> bool:
        """Gate P5: measurable, precision defined and >= threshold, and no span
        violation. An undefined precision (nothing predicted INELIGIBLE) is never a
        pass — you cannot claim >= 0.95 on 0/0."""
        return (
            self.is_measurable
            and self.precision is not None
            and self.precision >= threshold
            and not self.span_violations
        )

    def meets_ship_gate(
        self,
        threshold: float = 0.95,
        min_audited_coverage: float = SHIP_AUDIT_COVERAGE_BAR,
    ) -> bool:
        """The mechanical deferred-audit drain: `meets_gate` alone can pass on an
        all-oracle labeled set with zero human audit. Shipping requires BOTH the
        precision bar and a minimum audited fraction of the labeled set."""
        return self.meets_gate(threshold) and self.audited_coverage >= min_audited_coverage


def score(
    cases: Sequence[LabeledCase],
    catalog: RulesCatalog,
    policy: Policy | None = None,
) -> PrecisionReport:
    """Run the engine over the labeled set under the reference all-blocker policy and
    report INELIGIBLE precision/recall, per-rule abstain rate, and span violations."""
    effective = policy if policy is not None else reference_all_blocker_policy(catalog)
    severity = catalog.materialised_policy(effective)

    predicted_ineligible = 0
    true_ineligible = 0
    true_positives = 0
    span_violations: list[str] = []
    false_positives: list[Mismatch] = []
    mismatches: list[Mismatch] = []
    fired: dict[str, int] = {}
    abstained: dict[str, int] = {}

    for case in cases:
        result = evaluate(case.body_text, case.facts, effective, catalog)
        expected = case.expected_verdict
        predicted = result.verdict

        if expected == "ineligible":
            true_ineligible += 1
        if predicted == "ineligible":
            predicted_ineligible += 1
            if expected == "ineligible":
                true_positives += 1
            else:
                false_positives.append(Mismatch(case.label, expected, predicted))
            if not carries_valid_span(result, severity, case.body_text):
                span_violations.append(case.label)
        if predicted != expected:
            mismatches.append(Mismatch(case.label, expected, predicted))

        # Per-rule abstain accounting: a rule "fired" once per requirement row it
        # produced, "abstained" when that row's disposition is UNKNOWN.
        for req in result.requirements:
            if req.rule_id is None:
                continue
            fired[req.rule_id] = fired.get(req.rule_id, 0) + 1
            if req.disposition == UNKNOWN:
                abstained[req.rule_id] = abstained.get(req.rule_id, 0) + 1

    precision = true_positives / predicted_ineligible if predicted_ineligible else None
    recall = true_positives / true_ineligible if true_ineligible else None
    abstain_rate_by_rule = {
        rule_id: abstained.get(rule_id, 0) / count for rule_id, count in fired.items()
    }
    audited = sum(1 for case in cases if case.label_provenance == "audited")
    audited_coverage = audited / len(cases) if cases else 0.0

    return PrecisionReport(
        total=len(cases),
        predicted_ineligible=predicted_ineligible,
        true_ineligible=true_ineligible,
        ineligible_true_positives=true_positives,
        precision=precision,
        recall=recall,
        abstain_rate_by_rule=abstain_rate_by_rule,
        span_violations=tuple(span_violations),
        false_positives=tuple(false_positives),
        mismatches=tuple(mismatches),
        audited_coverage=audited_coverage,
    )


def load_labeled_set(directory: Path) -> list[LabeledCase]:
    """Read the human-verified labeled set from every `*.jsonl` file in `directory`.

    Each non-blank line is one case: {label, body_text, facts, expected_verdict,
    spans?, source?}. A row whose `expected_verdict` is null/absent is an unlabeled
    worksheet row (the worksheet and the labeled set are the same file, filled in over
    time) and is SKIPPED. A row with a non-null but invalid verdict or malformed facts
    raises `LabeledSetError`. A missing directory returns [] so the gate can report
    'not measurable' rather than crash.
    """
    if not directory.is_dir():
        return []
    cases: list[LabeledCase] = []
    for path in sorted(directory.glob("*.jsonl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            where = f"{path.name}:{lineno}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LabeledSetError(f"{where}: not valid JSON: {exc}") from exc
            case = _parse_row(row, where)
            if case is not None:
                cases.append(case)
    return cases


def _parse_row(row: object, where: str) -> LabeledCase | None:
    if not isinstance(row, dict):
        raise LabeledSetError(f"{where}: row is not an object")
    verdict = row.get("expected_verdict")
    if verdict is None:
        return None  # unlabeled worksheet row
    if verdict not in LABELED_VERDICTS:
        raise LabeledSetError(
            f"{where}: expected_verdict {verdict!r} not in {sorted(LABELED_VERDICTS)}"
        )
    try:
        facts = Facts.model_validate(row.get("facts", {}))
    except ValidationError as exc:
        raise LabeledSetError(f"{where}: malformed facts: {exc}") from exc
    label = row.get("label")
    body_text = row.get("body_text")
    if not isinstance(label, str) or not isinstance(body_text, str):
        raise LabeledSetError(f"{where}: label and body_text must be strings")
    try:
        spans = tuple((int(a), int(b)) for a, b in row.get("spans", []))
    except (ValueError, TypeError) as exc:
        # spans is the hand-edited, error-prone field; a typo must fail loud with a
        # location like every other field, not surface a bare ValueError/TypeError.
        raise LabeledSetError(f"{where}: malformed spans: {exc}") from exc
    source = row.get("source")
    label_provenance = row.get("label_provenance")
    return LabeledCase(
        label=label,
        body_text=body_text,
        facts=facts,
        expected_verdict=verdict,
        spans=spans,
        source=source if isinstance(source, str) else None,
        label_provenance=label_provenance if isinstance(label_provenance, str) else None,
    )
