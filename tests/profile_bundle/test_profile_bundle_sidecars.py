"""The private root sidecar `local-sources.yaml` (design §6).

This is the one file in the bundle that may hold an absolute machine path, and the reason it is safe
is that it is structurally incapable of holding anything else: a `dict[SourceId, AbsolutePath]` has no
room for a fact, a contact, or a claim. The tests pin that, plus the exclusion that matters most —
nothing about this file can reach a revision, a digest, or an export.

Paths here are built from `tmp_path` rather than written as literals: the repository's generalization
scan refuses a home-directory absolute path in any tracked file, and a test fixture is a tracked file.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.layout import ENTITY_DOCUMENT_DIRECTORIES, FIXED_DOCUMENTS
from boardwatch.profile_bundle.models.sidecars import EMPTY_SIDECAR, LocalSourcesSidecar
from boardwatch.profile_bundle.paths import LOCAL_SOURCES_FILE, local_sources_path


def test_the_sidecar_maps_source_ids_to_absolute_roots(tmp_path: Path) -> None:
    sidecar = LocalSourcesSidecar.model_validate(
        {"source.synthetic-notes": str(tmp_path / "notes")}
    )
    assert sidecar.resolved_source_ids() == frozenset({"source.synthetic-notes"})
    assert sidecar.roots["source.synthetic-notes"] == str(tmp_path / "notes")


def test_a_relative_root_is_refused() -> None:
    """A relative root resolves against whatever the process's working directory happened to be."""
    with pytest.raises(ValidationError):
        LocalSourcesSidecar.model_validate({"source.synthetic-notes": "notes/synthetic"})
    with pytest.raises(ValidationError):
        LocalSourcesSidecar.model_validate({"source.synthetic-notes": "./notes"})
    with pytest.raises(ValidationError):
        LocalSourcesSidecar.model_validate({"source.synthetic-notes": ""})


def test_a_windows_drive_root_is_accepted() -> None:
    assert LocalSourcesSidecar.model_validate({"source.a": "C:\\sources\\notes"}).roots


def test_keys_must_be_source_ids(tmp_path: Path) -> None:
    for bad_key in ("project.packet-pantry", "evidence.a.001", "notes", "source", ""):
        with pytest.raises(ValidationError):
            LocalSourcesSidecar.model_validate({bad_key: str(tmp_path)})


def test_the_sidecar_cannot_carry_professional_record_fields(tmp_path: Path) -> None:
    """There is nowhere for a fact to go: the value type is a path string, not an object."""
    with pytest.raises(ValidationError):
        LocalSourcesSidecar.model_validate(
            {"source.a": {"root": str(tmp_path), "facts": ["fact.a.001"]}}
        )
    with pytest.raises(ValidationError):
        LocalSourcesSidecar.model_validate({"facts": [{"fact_id": "fact.a.001"}]})


def test_an_empty_sidecar_is_a_legitimate_state() -> None:
    """`init` writes it empty so "no local originals are mapped" is visible, not merely absent."""
    assert EMPTY_SIDECAR.roots == {}
    assert LocalSourcesSidecar.model_validate({}).roots == {}


def test_the_sidecar_lives_at_the_root_and_in_no_revision() -> None:
    """§6: it is excluded from revision and evidence digests and is never exported."""
    declared = {str(path) for path in FIXED_DOCUMENTS}
    assert LOCAL_SOURCES_FILE not in declared
    assert PurePosixPath(LOCAL_SOURCES_FILE) not in FIXED_DOCUMENTS
    assert PurePosixPath(LOCAL_SOURCES_FILE).parent not in ENTITY_DOCUMENT_DIRECTORIES


def test_the_sidecar_path_is_derived_from_the_bundle_root(tmp_path: Path) -> None:
    assert local_sources_path(tmp_path) == tmp_path / "local-sources.yaml"


def test_the_sidecar_is_frozen(tmp_path: Path) -> None:
    sidecar = LocalSourcesSidecar.model_validate({"source.a": str(tmp_path)})
    with pytest.raises(ValidationError):
        sidecar.root = {}  # type: ignore[misc]
