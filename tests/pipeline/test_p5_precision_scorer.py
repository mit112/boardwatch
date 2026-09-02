"""P5b B0 — the precision scorer harness (the Gate P5 measurement machine).

Gate P5 (PROGRAM.md §3.P5): precision >= 0.95 on INELIGIBLE on a human-verified
labeled set, abstain rate reported per rule, and 0 INELIGIBLE without a quoted span.
This exercises `eligibility.scoring`, the harness that produces those numbers.

The synthetic cases here are NOT the Gate P5 labeled set. They are the smallest set
that pins the scorer's ARITHMETIC (precision/recall counting, span-violation detection,
None-vs-measurable discipline). The real, human-verified labeled set is Mit's data and
loads from a directory at gate time; do not conflate the two (design-p5b.md B0).
"""

from __future__ import annotations

import json

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import EvaluationResult
from boardwatch.eligibility.facts import Facts
from boardwatch.eligibility.scoring import (
    LabeledCase,
    LabeledSetError,
    blocking_requirements,
    carries_valid_span,
    load_labeled_set,
    reference_all_blocker_policy,
    score,
)
from boardwatch.store.eligibility import RequirementItem


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    return load_rules(tmp_path_factory.mktemp("no-override"))


# --------------------------------------------------------------------------- #
# reference all-blocker policy
# --------------------------------------------------------------------------- #


def test_reference_policy_sets_every_declared_family_to_blocker(catalog) -> None:
    policy = reference_all_blocker_policy(catalog)
    families = {family.id for family in catalog.families}
    assert set(policy.families) == families
    assert all(choice == "blocker" for choice in policy.families.values())
    # materialised over the catalog it must leave no family on its softer default.
    severity = catalog.materialised_policy(policy)
    assert all(choice == "blocker" for choice in severity.values())


# --------------------------------------------------------------------------- #
# blocking_requirements + carries_valid_span (the shared span property)
# --------------------------------------------------------------------------- #


def _req(disposition: str, span, rule_id: str = "work_auth:x", requiredness="required"):
    locator = {} if span is None else {"span": span}
    return RequirementItem(
        requiredness=requiredness,
        requirement_text="x",
        jd_locator=locator,
        disposition=disposition,
        rule_id=rule_id,
    )


def test_blocking_requirements_picks_required_unmet_blocker_rows() -> None:
    severity = {"work_auth": "blocker", "experience_years": "preference"}
    result = EvaluationResult(
        verdict="ineligible",
        requirements=(
            _req("unmet", (0, 5), "work_auth:a"),  # blocking
            _req("met", (0, 5), "work_auth:b"),  # met, not blocking
            _req("unmet", (0, 5), "experience_years:c"),  # preference, not blocking
            _req("unmet", (0, 5), "work_auth:d", requiredness="preferred"),  # not required
        ),
    )
    blocking = blocking_requirements(result, severity)
    assert [req.rule_id for req in blocking] == ["work_auth:a"]


def test_carries_valid_span_true_when_blocking_span_slices_body() -> None:
    severity = {"work_auth": "blocker"}
    body = "Must be a US citizen."
    result = EvaluationResult("ineligible", (_req("unmet", (0, 4)),))
    assert carries_valid_span(result, severity, body) is True


@pytest.mark.parametrize(
    "span",
    [None, (5, 3), (-1, 4), (3, 3)],
    ids=["no-span", "reversed", "negative-start", "empty-range"],
)
def test_carries_valid_span_false_on_bad_span(span) -> None:
    severity = {"work_auth": "blocker"}
    result = EvaluationResult("ineligible", (_req("unmet", span),))
    assert carries_valid_span(result, severity, "Must be a US citizen.") is False


def test_carries_valid_span_false_when_no_blocking_requirement() -> None:
    severity = {"work_auth": "blocker"}
    result = EvaluationResult("eligible", (_req("met", (0, 5)),))
    assert carries_valid_span(result, severity, "anything") is False


# --------------------------------------------------------------------------- #
# score() — precision / recall arithmetic
# --------------------------------------------------------------------------- #

# Real JD sentences whose verdicts under the all-blocker policy are known from the
# oracle corpus. Facts drive met/unmet, so each case carries its own.
_SPONSOR_JD = "We are unable to provide visa sponsorship for this role."
_YEARS_JD = "Requires 5+ years of experience."
_AUTH_JD = "Candidates must be legally authorized to work in the United States."
_ABSTAIN_JD = "Must be authorized to work in the United States."


def _needs_sponsorship() -> Facts:
    return Facts.model_validate(
        {"work_authorization": {"status": "needs_sponsorship", "jurisdiction": "us"}}
    )


def _citizen() -> Facts:
    return Facts.model_validate(
        {"work_authorization": {"status": "citizen", "jurisdiction": "us"}}
    )


def test_score_precision_and_recall_on_ineligible(catalog) -> None:
    cases = [
        # engine=ineligible, human=ineligible -> true positive
        LabeledCase("sponsor-tp", _SPONSOR_JD, _needs_sponsorship(), "ineligible"),
        # engine=ineligible, human=ineligible -> true positive
        LabeledCase("years-tp", _YEARS_JD, Facts.model_validate({"total_years_experience": 2}), "ineligible"),
        # engine=ineligible, human=ELIGIBLE -> false positive (the expensive error)
        LabeledCase("years-fp", _YEARS_JD, Facts.model_validate({"total_years_experience": 2}), "eligible"),
        # engine=eligible, human=eligible -> true negative
        LabeledCase("auth-tn", _AUTH_JD, _citizen(), "eligible"),
    ]
    report = score(cases, catalog)
    assert report.total == 4
    assert report.predicted_ineligible == 3
    assert report.true_ineligible == 2
    assert report.ineligible_true_positives == 2
    assert report.precision == pytest.approx(2 / 3)
    assert report.recall == pytest.approx(1.0)
    assert report.is_measurable is True
    assert report.meets_gate(0.95) is False
    assert report.meets_gate(0.5) is True
    # the false positive is surfaced by label for triage
    assert [m.label for m in report.false_positives] == ["years-fp"]
    assert not report.span_violations


# A foreign body — an aggregator's rendered page, not the employer's JD — carrying two catalog
# markers ("Apply on Employer Site", "H1B Sponsor Likely"), so `is_employer_body` rejects it.
_FOREIGN_BODY = (
    "Software Engineer. Apply on Employer Site. H1B Sponsor Likely. "
    "Responsibilities: build things."
)


def test_score_excludes_a_foreign_body_from_measurement(catalog) -> None:
    """Defense in depth (round-4): a worksheet corrupted before the write guard existed — a
    foreign body carrying a fabricated `ineligible` — must never reach precision measurement.
    `score` refuses the row (abstain by omission), so `total` and `true_ineligible` count only
    the real employer JD, not the third party's guess."""
    real = LabeledCase("sponsor-tp", _SPONSOR_JD, _needs_sponsorship(), "ineligible")
    foreign = LabeledCase("foreign-ineligible", _FOREIGN_BODY, _needs_sponsorship(), "ineligible")
    report = score([real, foreign], catalog)
    assert report.total == 1, "the foreign body must be excluded from the measured set"
    assert report.true_ineligible == 1
    assert [m.label for m in report.false_positives] == []


def test_score_precision_none_when_nothing_predicted_ineligible(catalog) -> None:
    cases = [LabeledCase("auth-tn", _AUTH_JD, _citizen(), "eligible")]
    report = score(cases, catalog)
    assert report.predicted_ineligible == 0
    assert report.precision is None
    assert report.meets_gate(0.95) is False  # undefined precision is never a pass


def test_score_is_not_measurable_without_a_true_ineligible(catalog) -> None:
    cases = [LabeledCase("auth-tn", _AUTH_JD, _citizen(), "eligible")]
    report = score(cases, catalog)
    assert report.true_ineligible == 0
    assert report.recall is None
    assert report.is_measurable is False
    assert report.meets_gate(0.5) is False


def test_score_reports_abstain_rate_per_fired_rule(catalog) -> None:
    # prefer_not_to_say -> work_auth abstains (unknown) -> uncertain verdict.
    abstaining = Facts.model_validate(
        {"work_authorization": {"status": "prefer_not_to_say", "jurisdiction": "us"}}
    )
    cases = [LabeledCase("auth-abstain", _ABSTAIN_JD, abstaining, "uncertain")]
    report = score(cases, catalog)
    assert report.abstain_rate_by_rule.get("work_auth:us_authorization_required") == pytest.approx(1.0)


def test_score_flags_a_predicted_ineligible_without_a_span(catalog, monkeypatch) -> None:
    """A span-less INELIGIBLE is exactly the keystone failure Gate P5 forbids; the
    scorer must catch it on the labeled set as P5a S1 catches it on the corpus."""
    from boardwatch.eligibility import scoring

    def _stub_evaluate(body, facts, policy, cat):
        return EvaluationResult("ineligible", (_req("unmet", None),))

    monkeypatch.setattr(scoring, "evaluate", _stub_evaluate)
    cases = [LabeledCase("no-span", _SPONSOR_JD, _needs_sponsorship(), "ineligible")]
    report = score(cases, catalog)
    assert report.span_violations == ("no-span",)
    assert report.meets_gate(0.0) is False  # a span violation fails the gate outright


# --------------------------------------------------------------------------- #
# audited_coverage + meets_ship_gate — the mechanical deferred-audit drain
# --------------------------------------------------------------------------- #


def test_audited_coverage_zero_for_all_oracle(catalog) -> None:
    cases = [
        LabeledCase(
            "sponsor-tp", _SPONSOR_JD, _needs_sponsorship(), "ineligible", label_provenance="oracle"
        ),
        LabeledCase("auth-tn", _AUTH_JD, _citizen(), "eligible", label_provenance="oracle"),
    ]
    report = score(cases, catalog)
    assert report.audited_coverage == 0.0
    # precision clears the bar on its own; the drain is what should still block ship.
    assert report.meets_gate(0.95) is True
    assert report.meets_ship_gate() is False


def test_audited_coverage_counts_audited(catalog) -> None:
    cases = [
        LabeledCase(
            "sponsor-tp", _SPONSOR_JD, _needs_sponsorship(), "ineligible", label_provenance="audited"
        ),
        LabeledCase("auth-tn", _AUTH_JD, _citizen(), "eligible", label_provenance="oracle"),
    ]
    report = score(cases, catalog)
    assert report.audited_coverage == pytest.approx(0.5)


def test_meets_ship_gate_requires_coverage(catalog) -> None:
    cases = [
        LabeledCase(
            "sponsor-tp", _SPONSOR_JD, _needs_sponsorship(), "ineligible", label_provenance="oracle"
        ),
        LabeledCase("auth-tn", _AUTH_JD, _citizen(), "eligible", label_provenance="oracle"),
    ]
    report = score(cases, catalog)
    assert report.precision == pytest.approx(1.0)
    assert report.audited_coverage == 0.0
    assert report.meets_gate(0.95) is True
    # meets_gate alone passes on precision; meets_ship_gate additionally requires
    # audited coverage to clear its own bar.
    assert report.meets_ship_gate() is False
    assert report.meets_ship_gate(min_audited_coverage=0.0) is True


# --------------------------------------------------------------------------- #
# load_labeled_set — the on-disk format the worksheet fills in
# --------------------------------------------------------------------------- #


def _write_jsonl(path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_load_labeled_set_reads_labeled_rows(tmp_path) -> None:
    _write_jsonl(
        tmp_path / "a.jsonl",
        [
            {
                "label": "sponsor",
                "body_text": _SPONSOR_JD,
                "facts": {"work_authorization": {"status": "needs_sponsorship", "jurisdiction": "us"}},
                "expected_verdict": "ineligible",
                "spans": [[3, 20]],
                "source": "job-apps/no_sponsorship/Acme",
            }
        ],
    )
    cases = load_labeled_set(tmp_path)
    assert len(cases) == 1
    case = cases[0]
    assert case.label == "sponsor"
    assert case.expected_verdict == "ineligible"
    assert case.spans == ((3, 20),)
    assert case.facts.work_authorization is not None
    assert case.source == "job-apps/no_sponsorship/Acme"


def test_load_labeled_set_skips_unlabeled_worksheet_rows(tmp_path) -> None:
    """The worksheet and the labeled set are the same file, progressively filled: a
    row whose verdict is still null is not yet labeled and is skipped, not an error."""
    _write_jsonl(
        tmp_path / "a.jsonl",
        [
            {"label": "unlabeled", "body_text": "x", "facts": {}, "expected_verdict": None},
            {"label": "done", "body_text": _AUTH_JD, "facts": {}, "expected_verdict": "eligible"},
        ],
    )
    cases = load_labeled_set(tmp_path)
    assert [c.label for c in cases] == ["done"]


def test_load_labeled_set_missing_dir_is_empty(tmp_path) -> None:
    assert load_labeled_set(tmp_path / "nope") == []


def test_load_labeled_set_raises_on_invalid_verdict(tmp_path) -> None:
    _write_jsonl(
        tmp_path / "a.jsonl",
        [{"label": "bad", "body_text": "x", "facts": {}, "expected_verdict": "maybe"}],
    )
    with pytest.raises(LabeledSetError):
        load_labeled_set(tmp_path)


def test_load_labeled_set_raises_on_malformed_facts(tmp_path) -> None:
    """A malformed labeled row is a curation bug and must fail LOUD, unlike the
    fail-closed parse_facts used on stored production JSON."""
    _write_jsonl(
        tmp_path / "a.jsonl",
        [{"label": "bad", "body_text": "x", "facts": {"nonsense": 1}, "expected_verdict": "eligible"}],
    )
    with pytest.raises(LabeledSetError):
        load_labeled_set(tmp_path)


@pytest.mark.parametrize(
    "spans",
    [[[10, 25], [30]], "10-25", [["a", "b"]]],
    ids=["short-pair", "not-a-list", "non-int"],
)
def test_load_labeled_set_raises_on_malformed_spans(tmp_path, spans) -> None:
    """spans is the hand-edited field; a typo must fail loud with a location, not a
    bare ValueError/TypeError (the latter isn't even a LabeledSetError subclass)."""
    _write_jsonl(
        tmp_path / "a.jsonl",
        [{"label": "bad", "body_text": "x", "facts": {}, "expected_verdict": "ineligible", "spans": spans}],
    )
    with pytest.raises(LabeledSetError):
        load_labeled_set(tmp_path)


def test_load_labeled_set_skips_blank_lines(tmp_path) -> None:
    (tmp_path / "a.jsonl").write_text(
        '\n\n{"label":"done","body_text":"x","facts":{},"expected_verdict":"eligible"}\n\n',
        encoding="utf-8",
    )
    assert [c.label for c in load_labeled_set(tmp_path)] == ["done"]


def test_load_labeled_set_raises_on_invalid_json(tmp_path) -> None:
    (tmp_path / "a.jsonl").write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(LabeledSetError):
        load_labeled_set(tmp_path)


def test_load_labeled_set_raises_on_non_object_row(tmp_path) -> None:
    (tmp_path / "a.jsonl").write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(LabeledSetError):
        load_labeled_set(tmp_path)


def test_load_labeled_set_raises_when_label_or_body_not_string(tmp_path) -> None:
    _write_jsonl(
        tmp_path / "a.jsonl",
        [{"label": 5, "body_text": "x", "facts": {}, "expected_verdict": "eligible"}],
    )
    with pytest.raises(LabeledSetError):
        load_labeled_set(tmp_path)


def test_score_ignores_requirements_without_a_rule_id(catalog, monkeypatch) -> None:
    """A requirement carrying no rule_id can't be attributed to an abstain bucket; it
    must be skipped, not crash the per-rule accounting."""
    from boardwatch.eligibility import scoring

    def _stub_evaluate(body, facts, policy, cat):
        return EvaluationResult("eligible", (_req("unknown", (0, 5), rule_id=None),))

    monkeypatch.setattr(scoring, "evaluate", _stub_evaluate)
    report = score([LabeledCase("no-rule", _AUTH_JD, _citizen(), "eligible")], catalog)
    assert report.abstain_rate_by_rule == {}
    assert report.total == 1
