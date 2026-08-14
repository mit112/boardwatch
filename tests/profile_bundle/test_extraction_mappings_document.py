"""The persisted form of the deterministic extraction mapping (schema v2; §6.2/§6.2a, D-172/D-174).

The load-bearing property is round-trip fidelity: the document seeded into a bundle must reconstruct
the exact interpreter dataclasses `run_extraction` consumes, so a revision's extraction behaviour is
fixed by its own digest-bound rows rather than by whatever the installed build means by an adapter
name. These tests pin that both ways (dataclass <-> document) and across a real YAML round-trip
through the bundle's restricted writer/loader.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.extraction import validate_mapping_against_catalog
from boardwatch.profile_bundle.extraction_mapping import (
    BUILTIN_EXTRACTION_MAPPINGS,
    RESUME_ADAPTER_ID,
    builtin_extraction_mappings_document,
    extraction_mappings_document,
    mappings_from_document,
)
from boardwatch.profile_bundle.models.policy import (
    AdapterExtractionMapping,
    EntryKindModelEntry,
    ExtractionMappingsDocument,
    SlotModel,
)
from boardwatch.profile_bundle.predicate_catalog import builtin_catalog
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes

_LOGICAL = PurePosixPath("policy/extraction-mappings.yaml")


def test_round_trip_reconstructs_the_builtin_dataclasses() -> None:
    # The persisted form must reconstruct the EXACT interpreter mapping — frozen dataclasses compare
    # by value, so this is a deep equality over every rule, slot, and deferral.
    doc = builtin_extraction_mappings_document()
    assert mappings_from_document(doc) == dict(BUILTIN_EXTRACTION_MAPPINGS)


def test_the_document_survives_the_restricted_yaml_round_trip() -> None:
    doc = builtin_extraction_mappings_document()
    payload = doc.model_dump(mode="json")
    # `document_bytes` reads its own output back and refuses anything the loader would retype; the
    # explicit re-parse below proves the model reconstructs from those bytes unchanged.
    raw = document_bytes(payload, logical_path=_LOGICAL)
    reloaded = load_yaml_bytes(raw, logical_path=_LOGICAL)
    assert ExtractionMappingsDocument.model_validate(reloaded) == doc


def test_the_reconstructed_mapping_is_catalog_legal() -> None:
    doc = builtin_extraction_mappings_document()
    mapping = mappings_from_document(doc)[RESUME_ADAPTER_ID]
    validate_mapping_against_catalog(mapping, builtin_catalog(1))


def test_the_document_is_seeded_non_empty_with_the_resume_adapter() -> None:
    doc = builtin_extraction_mappings_document()
    assert doc.mappings_version >= 1
    assert RESUME_ADAPTER_ID in doc.by_adapter


def test_extraction_mappings_document_honours_an_explicit_version() -> None:
    doc = extraction_mappings_document(BUILTIN_EXTRACTION_MAPPINGS, version=7)
    assert doc.mappings_version == 7


def test_value_from_union_parses_a_list_to_a_tuple_and_a_scalar_to_a_str() -> None:
    coalesce = SlotModel(
        group="metadata",
        value_from=["title", "heading"],
        value_type="string",
        predicate="project.name",
        display_from="chosen",
    )
    assert isinstance(coalesce.value_from, tuple)
    assert coalesce.value_from == ("title", "heading")

    scalar = SlotModel(
        group="metadata",
        value_from="heading",
        value_type="string",
        predicate="employment.organization",
        display_from="heading",
    )
    assert isinstance(scalar.value_from, str)
    assert scalar.value_from == "heading"


def _adapter(adapter_id: str) -> AdapterExtractionMapping:
    return AdapterExtractionMapping(
        adapter_id=adapter_id,
        literal_rules=(),
        model_routed_rules=(),
        entry_kind_model=(),
        deferrals=(),
    )


def test_a_duplicate_adapter_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractionMappingsDocument(
            mappings_version=1, adapters=(_adapter("resume-a"), _adapter("resume-a"))
        )


def test_a_duplicate_entry_kind_is_rejected() -> None:
    entry = EntryKindModelEntry(kind="experience", subject_kind="employment", slots=())
    with pytest.raises(ValidationError):
        AdapterExtractionMapping(
            adapter_id="resume-a",
            literal_rules=(),
            model_routed_rules=(),
            entry_kind_model=(entry, entry),
            deferrals=(),
        )
