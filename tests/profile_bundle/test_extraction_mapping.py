"""The builtin extraction mapping, end to end at the library level (Gate B, Slice B — easy buckets).

Proves the two literal-rule buckets actually produce candidates: enumerated records → the builtin
`boardwatch-resume-v1` rules → `extract_proposals` → the real `build_candidate_package` typed and
identified against the *seeded* starter catalog. No bundle document, no CLI, no schema bump — this is
the interface settled in code (D-178) before the mapping is persisted (schema v2) and wired to a
command. `header/1` (string) and skill items (`skill_ref`) are the buckets that need none of the
`entry_kind_model` machinery; the rest match no rule yet and produce nothing, as intended.
"""

from __future__ import annotations

from boardwatch.profile_bundle.enumerators import (
    EnumeratedSourceRecord,
    derive_source_record_id,
)
from boardwatch.profile_bundle.extraction import extract_proposals
from boardwatch.profile_bundle.extraction_mapping import (
    BUILTIN_EXTRACTION_MAPPINGS,
    RESUME_ADAPTER_ID,
)
from boardwatch.profile_bundle.imports import EnumeratedSource, build_candidate_package
from boardwatch.profile_bundle.models.facts import SkillRefValue, StringValue
from boardwatch.profile_bundle.models.imports import CompleteFileScope
from boardwatch.profile_bundle.predicate_catalog import builtin_catalog

_SOURCE_ID = "source.resume"
_RULES = BUILTIN_EXTRACTION_MAPPINGS[RESUME_ADAPTER_ID]
_CATALOG = builtin_catalog(1)


def _record(locator: str, atomic_value: object) -> EnumeratedSourceRecord:
    return EnumeratedSourceRecord(
        source_record_id=derive_source_record_id(_SOURCE_ID, locator),
        source_id=_SOURCE_ID,
        normalized_locator=locator,
        atomic_value=atomic_value,
        record_content_digest="sha256:" + "b" * 64,
    )


def _source(records: tuple[EnumeratedSourceRecord, ...]) -> EnumeratedSource:
    return EnumeratedSource(
        source_id=_SOURCE_ID,
        enumerator_id=RESUME_ADAPTER_ID,
        enumerator_version=1,
        source_content_digest="sha256:" + "c" * 64,
        approved_scope=CompleteFileScope(kind="complete_file"),
        records=records,
    )


def _package(records: tuple[EnumeratedSourceRecord, ...]):
    source = _source(records)
    proposals = extract_proposals(source.records, _RULES)
    return build_candidate_package((source,), proposals, predicates=_CATALOG)


def _by_predicate(package, predicate: str):
    return [c for c in package.candidates if c.predicate == predicate]


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
    skills = _by_predicate(package, "technology.used")
    by_display = {c.original_display_value: c.canonicalized_typed_value for c in skills}
    assert by_display["Python"] == SkillRefValue(type="skill_ref", skill_id="skill.python")
    # The slug is lossy/normalised, but the verbatim item survives as the display value.
    assert by_display["React.js"] == SkillRefValue(type="skill_ref", skill_id="skill.react-js")


def test_a_lossy_skill_name_still_grounds_its_verbatim_display() -> None:
    package = _package(
        (_record("skill-groups/Languages/1", {"label": "Languages", "item": "C++"}),)
    )
    [skill] = _by_predicate(package, "technology.used")
    assert skill.original_display_value == "C++"
    assert skill.canonicalized_typed_value == SkillRefValue(type="skill_ref", skill_id="skill.c")


def test_a_record_no_literal_rule_matches_produces_no_candidate() -> None:
    # header/2 is the email: no rule matches it (it has no catalog predicate), so it lands nothing —
    # it stays review_required, not misfiled as a name.
    package = _package((_record("header/2", "ada@example.com"),))
    assert package.candidates == ()


def test_the_two_easy_buckets_land_together_over_a_mixed_record_set() -> None:
    package = _package(
        (
            _record("header/1", "Ada Lovelace"),
            _record("header/2", "ada@example.com"),
            _record("skill-groups/Languages/1", {"label": "Languages", "item": "Python"}),
            _record("skill-groups/Languages/2", {"label": "Languages", "item": "Rust"}),
            # a metadata record: no literal rule matches it yet (needs entry_kind_model)
            _record(
                "entries/exp-1/metadata",
                {"entry_id": "exp-1", "kind": "experience", "heading": "Acme", "title": "Engineer"},
            ),
        )
    )
    assert len(_by_predicate(package, "person.professional_name")) == 1
    assert len(_by_predicate(package, "technology.used")) == 2
    # header/2 and the metadata record contribute nothing under the literal-only mapping.
    assert len(package.candidates) == 3
