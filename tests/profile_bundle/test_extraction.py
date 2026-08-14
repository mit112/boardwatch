"""Deterministic extraction interpreter (Gate B, Slice B).

The mapping is declarative data; these tests pin the interpreter that reads it, so an operation the
spec describes but the schema cannot express fails here rather than in a user's bundle.
"""

from __future__ import annotations

from boardwatch.profile_bundle.enumerators import EnumeratedSourceRecord
from boardwatch.profile_bundle.extraction import (
    ExtractionRule,
    extract_proposals,
    locator_matches,
)
from boardwatch.profile_bundle.models.facts import StringValue


def _record(locator: str, atomic_value: object) -> EnumeratedSourceRecord:
    return EnumeratedSourceRecord(
        source_record_id="source-record." + "a" * 64,
        source_id="source.resume",
        normalized_locator=locator,
        atomic_value=atomic_value,
        record_content_digest="sha256:" + "b" * 64,
    )


def test_a_wildcard_segment_matches_any_one_segment() -> None:
    assert locator_matches("skill-groups/*/*", "skill-groups/Languages/1")


def test_a_wildcard_does_not_match_a_different_head() -> None:
    assert not locator_matches("skill-groups/*/*", "header/1")


def test_a_literal_non_head_segment_does_not_overmatch() -> None:
    # header/1 must select the professional name and leave header/2 (the email) unmatched, so the
    # email ends no_predicate_exists rather than being claimed as a name.
    assert locator_matches("header/1", "header/1")
    assert not locator_matches("header/1", "header/2")


def test_a_pattern_of_different_length_never_matches() -> None:
    assert not locator_matches("skill-groups/*/*", "skill-groups/Languages")
    assert not locator_matches("header/1", "header/1/extra")


def test_a_literal_rule_proposes_a_candidate_from_the_named_field() -> None:
    record = _record("skill-groups/Languages/1", {"label": "Languages", "item": "Python"})
    rule = ExtractionRule(
        locator_pattern="skill-groups/*/*",
        predicate="technology.used",
        value_from="item",
        value_type="string",
        display_from="item",
    )
    [proposal] = extract_proposals([record], [rule])
    assert proposal.source_record_id == record.source_record_id
    assert proposal.predicate == "technology.used"
    assert proposal.original_display_value == "Python"
    assert proposal.value == StringValue(type="string", value="Python")


def test_a_rule_whose_pattern_does_not_match_proposes_nothing() -> None:
    record = _record("header/1", "Mit Sheth")
    rule = ExtractionRule(
        locator_pattern="skill-groups/*/*",
        predicate="technology.used",
        value_from="item",
        value_type="string",
        display_from="item",
    )
    assert extract_proposals([record], [rule]) == []
