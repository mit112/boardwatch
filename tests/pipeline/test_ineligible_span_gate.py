"""Gate P5: 0 INELIGIBLE without a quoted span — as a corpus-wide PROPERTY, not per-case.

The engine gives every `RequirementItem` a `jd_locator` cut from a real detection span, and
an `ineligible` verdict is produced ONLY by a blocking UNMET `required` row in a `blocker`
family (engine.evaluate's `blocking(UNMET)`). Today that is a STRUCTURAL guarantee plus a
handful of per-case span assertions; nothing checks it over the whole oracle corpus.

This asserts the keystone directly across every `ineligible` corpus case: the result carries
at least one blocking requirement whose span is present, well-ordered (`span[1] > span[0] >=
0`), and slices a non-empty quote out of the body it was cut from. A span-less INELIGIBLE
would make this go RED, which is exactly the failure the keystone forbids.
"""

from __future__ import annotations

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy
from tests.pipeline.test_eligibility_corpus import CASES

# (label, body, facts, policy, verdict, rows) — reuse the same oracle corpus `evaluate` is
# already pinned against, filtered to the verdict this gate is about.
INELIGIBLE_CASES = [case for case in CASES if case[4] == "ineligible"]


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    return load_rules(tmp_path_factory.mktemp("no-override"))


def test_the_corpus_has_ineligible_cases_to_guard() -> None:
    """A gate over an empty set passes vacuously; assert the scope is non-empty first."""
    assert INELIGIBLE_CASES


@pytest.mark.parametrize(
    "label,body,facts,policy,verdict,rows",
    INELIGIBLE_CASES,
    ids=[case[0] for case in INELIGIBLE_CASES],
)
def test_ineligible_carries_a_quoted_span(
    catalog, label, body, facts, policy, verdict, rows
) -> None:
    result = evaluate(body, Facts.model_validate(facts), Policy(families=policy), catalog)
    assert result.verdict == "ineligible"

    severity = catalog.materialised_policy(Policy(families=policy))
    # The rows the roll-up counts as blocking: a `required` UNMET detection in a `blocker`
    # family (engine.evaluate.blocking(UNMET)). requirements and rows are built in lockstep,
    # so every blocking row has a matching RequirementItem here.
    blocking = [
        req
        for req in result.requirements
        if req.requiredness == "required"
        and req.disposition == "unmet"
        and req.rule_id is not None
        and severity.get(req.rule_id.split(":")[0]) == "blocker"
    ]
    assert blocking, f"{label}: ineligible with no blocking requirement"

    for req in blocking:
        span = req.jd_locator.get("span")
        assert span is not None, f"{label}: blocking requirement carries no span"
        start, end = span[0], span[1]
        assert 0 <= start < end, f"{label}: span not well-ordered: {span!r}"
        assert body[start:end], f"{label}: span slices empty text out of the body"
