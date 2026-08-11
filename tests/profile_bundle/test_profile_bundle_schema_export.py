"""JSON Schema parity, the document-kind registry, and the schema-v1 bootstrap head.

The committed schema is what an authoring LLM reads without running the code, so the authoritative
check is exact generated-document equality: if the models change and the file does not, the shipped
contract describes a schema that no longer exists.

`DOCUMENT_MODELS` totality is the other property here. The layout grammar says which files are
declared; this registry says how each one parses. A kind present in one and missing from the other
would leave a file that is "declared" but unparseable, and the gap would only surface when somebody
authored that file.
"""

from __future__ import annotations

import json
import re

import pytest

from boardwatch.profile_bundle.errors import UnsupportedSchemaVersionError
from boardwatch.profile_bundle.layout import FIXED_DOCUMENTS, DocumentKind
from boardwatch.profile_bundle.schema import (
    CURRENT_SCHEMA_VERSION,
    DOCUMENT_MODELS,
    SUPPORTED_SCHEMA_VERSIONS,
    bundle_json_schema,
    committed_schema_json,
    model_for_kind,
    require_supported_schema,
    schema_json,
)


def test_committed_json_schema_matches_models() -> None:
    assert json.loads(committed_schema_json()) == bundle_json_schema()


def test_the_committed_bytes_are_the_exact_rendering() -> None:
    """Sorted keys and a fixed indent, so an import reshuffle cannot rewrite the whole file."""
    assert committed_schema_json() == schema_json()


def test_the_schema_declares_its_bundle_schema_version() -> None:
    schema = bundle_json_schema()
    assert schema["x-bundle-schema-version"] == CURRENT_SCHEMA_VERSION
    assert schema["title"] == "boardwatch career-profile bundle"


def test_the_schema_defines_every_document_wrapper() -> None:
    defs = bundle_json_schema()["$defs"]
    assert isinstance(defs, dict)
    for expected in (
        "DraftManifest",
        "RevisionManifest",
        "IdentityDocument",
        "EmploymentFactsDocument",
        "ProjectFactsDocument",
        "GatedFactsDocument",
        "PredicateCatalog",
        "UnitCatalog",
        "AssertionTagCatalog",
        "SecretRuleset",
        "SourceLedger",
        "CandidatePackage",
        "ExclusionLedger",
        "ChangeLedger",
        "ApprovalLedger",
        "LocalSourcesSidecar",
    ):
        assert expected in defs, expected


def test_every_declared_document_kind_has_a_parser() -> None:
    parsed_kinds = set(DOCUMENT_MODELS) | {DocumentKind.MANIFEST}
    assert parsed_kinds == set(DocumentKind)


def test_every_declared_file_kind_appears_in_the_registry() -> None:
    for kind in set(FIXED_DOCUMENTS.values()):
        if kind is DocumentKind.MANIFEST:
            continue
        assert kind in DOCUMENT_MODELS, kind


def test_the_manifest_is_a_union_and_has_no_single_registry_entry() -> None:
    assert DocumentKind.MANIFEST not in DOCUMENT_MODELS
    with pytest.raises(KeyError):
        model_for_kind(DocumentKind.MANIFEST)


def test_model_for_kind_returns_the_wrapper() -> None:
    from boardwatch.profile_bundle.models.documents import IdentityDocument

    assert model_for_kind(DocumentKind.IDENTITY) is IdentityDocument


def test_schema_head_is_one_and_the_supported_set_is_exactly_one() -> None:
    """Design §7: schema v1 is the bootstrap release and supports exactly `{1}`. No invented v0."""
    assert CURRENT_SCHEMA_VERSION == 1
    assert SUPPORTED_SCHEMA_VERSIONS == frozenset({1})
    assert 0 not in SUPPORTED_SCHEMA_VERSIONS


def test_a_supported_version_passes_through() -> None:
    assert require_supported_schema(1) == 1


@pytest.mark.parametrize("found", [0, 2, 99])
def test_an_unsupported_version_raises_the_typed_refusal(found: int) -> None:
    with pytest.raises(UnsupportedSchemaVersionError) as excinfo:
        require_supported_schema(found)
    assert excinfo.value.found == found
    assert excinfo.value.supported == (1,)


def test_the_schema_is_json_serialisable_and_stable_across_calls() -> None:
    assert schema_json() == schema_json()
    json.loads(schema_json())


def test_the_exported_schema_constrains_the_portable_locator() -> None:
    """The exported schema is what an external authoring tool validates against.

    `NonBlankStr`'s `\\S` was the only constraint that reached it, so the schema admitted
    `../escape/source.md` and `/absolute/source.md` — spellings the model refuses and that read
    outside the root the owner approved.
    """
    from boardwatch.profile_bundle.models.policy import PORTABLE_LOCATOR_PATTERN

    field = bundle_json_schema()["$defs"]["SourceSpec"]["properties"]["portable_locator"]
    assert field["pattern"] == PORTABLE_LOCATOR_PATTERN
    constraint = re.compile(field["pattern"])
    assert constraint.search("notes/synthetic.md")
    for refused in ["../escape/source.md", "/absolute/source.md", "C:/x.md", "a\\b", "n\x00.md"]:
        assert not constraint.search(refused), refused
