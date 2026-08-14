"""The builtin extraction mapping, end to end at the library level (Gate B, Slice B).

Proves every résumé bucket produces the candidates §6.2a specifies: the two literal buckets
(`header/1`, skill items) and — through the one `entry_kind_model` — entry metadata (by kind) and
bullets (by the parent entry's kind). Records → the builtin `boardwatch-resume-v1` mapping →
`run_extraction` → the real `build_candidate_package`, typed and identified against the *seeded*
starter catalog. No bundle document, no CLI, no schema bump — this is the interface settled in code
(D-178) before the mapping is persisted (schema v2) and wired to a command.
"""

from __future__ import annotations

import pytest

from boardwatch.profile_bundle.enumerators import (
    EnumeratedSourceRecord,
    derive_source_record_id,
)
from boardwatch.profile_bundle.extraction import (
    EntryKindSpec,
    ExtractionMapping,
    ExtractionMappingError,
    ModelRoutedRule,
    Slot,
    extract_proposals,
    run_extraction,
    validate_mapping_against_catalog,
)
from boardwatch.profile_bundle.extraction_mapping import (
    BUILTIN_EXTRACTION_MAPPINGS,
    RESUME_ADAPTER_ID,
)
from boardwatch.profile_bundle.imports import EnumeratedSource, build_candidate_package
from boardwatch.profile_bundle.models.facts import (
    DateRangeValue,
    SkillRefValue,
    StringValue,
    YearMonthValue,
)
from boardwatch.profile_bundle.models.imports import CompleteFileScope
from boardwatch.profile_bundle.predicate_catalog import builtin_catalog

_SOURCE_ID = "source.resume"
_MAPPING = BUILTIN_EXTRACTION_MAPPINGS[RESUME_ADAPTER_ID]
_CATALOG = builtin_catalog(1)


def _record(locator: str, atomic_value: object) -> EnumeratedSourceRecord:
    return EnumeratedSourceRecord(
        source_record_id=derive_source_record_id(_SOURCE_ID, locator),
        source_id=_SOURCE_ID,
        normalized_locator=locator,
        atomic_value=atomic_value,
        record_content_digest="sha256:" + "b" * 64,
    )


def _metadata(entry_id: str, kind: str, **fields: object) -> EnumeratedSourceRecord:
    """A metadata record shaped like the enumerator's `entry.model_dump(exclude={'bullets'})`."""
    value = {
        "entry_id": entry_id,
        "kind": kind,
        "heading": fields.get("heading", ""),
        "title": fields.get("title"),
        "dates": fields.get("dates"),
        "subtitle": fields.get("subtitle"),
        "location": fields.get("location"),
    }
    return _record(f"entries/{entry_id}/metadata", value)


def _bullet(entry_id: str, bullet_id: str, text: str) -> EnumeratedSourceRecord:
    return _record(
        f"entries/{entry_id}/bullets/{bullet_id}",
        {"bullet_id": bullet_id, "text": text, "tech_tags": []},
    )


def _package(records: tuple[EnumeratedSourceRecord, ...]):
    source = EnumeratedSource(
        source_id=_SOURCE_ID,
        enumerator_id=RESUME_ADAPTER_ID,
        enumerator_version=1,
        source_content_digest="sha256:" + "c" * 64,
        approved_scope=CompleteFileScope(kind="complete_file"),
        records=records,
    )
    proposals = run_extraction(source.records, _MAPPING).proposals
    return build_candidate_package((source,), proposals, predicates=_CATALOG)


def _by_predicate(package, predicate: str):
    return [c for c in package.candidates if c.predicate == predicate]


def _reasons(records: tuple[EnumeratedSourceRecord, ...]) -> dict[str, str]:
    result = run_extraction(records, _MAPPING)
    return {f.source_record_id: f.reason for f in result.failures}


# --- the builtin mapping is a legal member of the seeded catalog (§6.2a, invariant 4) -------------


def test_the_builtin_mapping_is_catalog_legal() -> None:
    # Every slot predicate exists and admits its entry kind's subject kind — no per-entry
    # PREDICATE_SUBJECT_KIND_ILLEGAL surprise at promotion.
    validate_mapping_against_catalog(_MAPPING, _CATALOG)


def test_a_slot_predicate_illegal_for_its_subject_kind_is_refused() -> None:
    bad = ExtractionMapping(
        model_routed_rules=(ModelRoutedRule("entries/*/metadata", "self", "metadata"),),
        entry_kind_model={
            "project": EntryKindSpec(
                subject_kind="project",
                # employment.organization is legal for `employment` only.
                slots=(Slot("metadata", "heading", "string", "employment.organization", "heading"),),
            )
        },
    )
    with pytest.raises(ExtractionMappingError, match="does not admit subject kind 'project'"):
        validate_mapping_against_catalog(bad, _CATALOG)


# --- the two literal buckets (unchanged behaviour) ------------------------------------------------


def test_the_header_name_bucket_lands_one_professional_name_candidate() -> None:
    package = _package((_record("header/1", "Ada Lovelace"),))
    [name] = _by_predicate(package, "person.professional_name")
    assert name.original_display_value == "Ada Lovelace"
    assert name.canonicalized_typed_value == StringValue(type="string", value="Ada Lovelace")


def test_each_skill_item_lands_a_technology_used_candidate_with_a_derived_id() -> None:
    package = _package(
        (
            _record("skill-groups/Languages/1", {"label": "Languages", "item": "Python"}),
            _record("skill-groups/Frameworks/1", {"label": "Frameworks", "item": "React.js"}),
        )
    )
    by_display = {
        c.original_display_value: c.canonicalized_typed_value
        for c in _by_predicate(package, "technology.used")
    }
    assert by_display["Python"] == SkillRefValue(type="skill_ref", skill_id="skill.python")
    assert by_display["React.js"] == SkillRefValue(type="skill_ref", skill_id="skill.react-js")


# --- entry metadata, routed by kind through the entry_kind_model -----------------------------------


def test_experience_metadata_lands_organization_title_daterange_and_location() -> None:
    record = _metadata(
        "nio",
        "experience",
        heading="NIO",
        title="Software Engineer",
        dates="Jul 2024 -- Feb 2025",
        location="Shanghai",
    )
    package = _package((record,))
    [org] = _by_predicate(package, "employment.organization")
    assert org.canonicalized_typed_value == StringValue(type="string", value="NIO")
    [title] = _by_predicate(package, "employment.title")
    assert title.canonicalized_typed_value == StringValue(type="string", value="Software Engineer")
    [loc] = _by_predicate(package, "entity.location")
    assert loc.canonicalized_typed_value == StringValue(type="string", value="Shanghai")
    [dates] = _by_predicate(package, "employment.date_range")
    from datetime import date

    assert dates.canonicalized_typed_value == DateRangeValue(
        type="date_range", start=date(2024, 7, 1), end=date(2025, 2, 1)
    )
    # The date candidate grounds against the RAW dates string, not the parsed component.
    assert dates.original_display_value == "Jul 2024 -- Feb 2025"


def test_an_experience_with_only_a_heading_lands_just_the_organization() -> None:
    package = _package((_metadata("x", "experience", heading="Acme"),))
    assert len(_by_predicate(package, "employment.organization")) == 1
    # Null title/dates/location emit nothing — no candidate, never an error.
    assert len(package.candidates) == 1


def test_a_project_metadata_lands_name_two_year_months_and_location() -> None:
    record = _metadata(
        "kf",
        "project",
        heading="ignored",
        title="Knowledge Forge",
        dates="Jun 2022 -- Apr 2023",
        location="Remote",
    )
    package = _package((record,))
    [name] = _by_predicate(package, "project.name")
    assert name.canonicalized_typed_value == StringValue(type="string", value="Knowledge Forge")
    [start] = _by_predicate(package, "project.start_date")
    assert start.canonicalized_typed_value == YearMonthValue(type="year_month", value="2022-06")
    [end] = _by_predicate(package, "project.end_date")
    assert end.canonicalized_typed_value == YearMonthValue(type="year_month", value="2023-04")
    assert len(_by_predicate(package, "entity.location")) == 1


def test_a_project_name_falls_back_to_heading_when_title_is_null() -> None:
    package = _package((_metadata("p", "project", heading="Crop RF", title=None),))
    [name] = _by_predicate(package, "project.name")
    assert name.canonicalized_typed_value == StringValue(type="string", value="Crop RF")
    assert name.original_display_value == "Crop RF"  # grounded against the CHOSEN field


def test_a_project_with_an_open_end_lands_a_start_but_no_end() -> None:
    package = _package((_metadata("s", "project", heading="Streaksync", dates="Jun 2025 -- Present"),))
    assert len(_by_predicate(package, "project.start_date")) == 1
    # The open end is a legitimately absent component — no end candidate, not value_not_typeable.
    assert _by_predicate(package, "project.end_date") == []
    assert _reasons((_metadata("s", "project", heading="S", dates="Jun 2025 -- Present"),)) == {}


# --- bullets, routed by the PARENT entry's kind (O6 cross-record lookup) ---------------------------


def test_an_experience_bullet_lands_an_accomplishment() -> None:
    records = (
        _metadata("nio", "experience", heading="NIO"),
        _bullet("nio", "b1", "Shipped the extraction interpreter"),
    )
    package = _package(records)
    [acc] = _by_predicate(package, "employment.accomplishment")
    assert acc.canonicalized_typed_value == StringValue(
        type="string", value="Shipped the extraction interpreter"
    )


def test_a_project_bullet_lands_a_contribution_not_an_accomplishment() -> None:
    records = (
        _metadata("kf", "project", heading="Knowledge Forge"),
        _bullet("kf", "b1", "Built the RAG pipeline"),
    )
    package = _package(records)
    assert len(_by_predicate(package, "project.contribution")) == 1
    # A project bullet can NEVER resolve to an employment predicate — that was the rev-5 defect.
    assert _by_predicate(package, "employment.accomplishment") == []


# --- the drain: every record that lands nothing carries exactly one closed reason (§6.3a) ----------


def test_an_unsupported_entry_kind_drains_both_its_metadata_and_its_bullet() -> None:
    records = (
        _metadata("aw", "award", heading="Best Paper"),
        _bullet("aw", "b1", "Recognised at a conference"),
    )
    result = run_extraction(records, _MAPPING)
    assert result.proposals == ()
    reasons = {f.source_record_id: f.reason for f in result.failures}
    assert set(reasons.values()) == {"unsupported_entry_kind"}
    assert len(reasons) == 2


def test_the_header_email_and_education_carry_their_specific_reasons() -> None:
    reasons = _reasons(
        (
            _record("header/2", "ada@example.com"),
            _record("education/1", "Northeastern University, MS Computer Science"),
        )
    )
    assert reasons[derive_source_record_id(_SOURCE_ID, "header/2")] == "no_predicate_exists"
    assert reasons[derive_source_record_id(_SOURCE_ID, "education/1")] == "free_text_deferred"


def test_a_garbled_dates_string_drains_value_not_typeable() -> None:
    reasons = _reasons((_metadata("q", "project", heading="Q", dates="whenever it was"),))
    # heading still lands project.name, so the record is NOT review_required — no failure for it.
    # Force the no-candidate case: a project whose only field is a garbled date.
    only_dates = _record(
        "entries/z/metadata",
        {"entry_id": "z", "kind": "project", "heading": "", "title": None,
         "dates": "garbled", "subtitle": None, "location": None},
    )
    result = run_extraction((only_dates,), _MAPPING)
    assert {f.reason for f in result.failures} == {"value_not_typeable"}
    assert reasons == {}  # the heading-bearing project produced project.name, so no drain


# --- the literal primitive still works for the easy buckets ----------------------------------------


def test_extract_proposals_still_returns_the_literal_candidates() -> None:
    rules = _MAPPING.literal_rules
    proposals = extract_proposals((_record("header/1", "Ada Lovelace"),), rules)
    assert [p.predicate for p in proposals] == ["person.professional_name"]
