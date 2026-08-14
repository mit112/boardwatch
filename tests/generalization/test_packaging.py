"""R12 wheel completeness, and the contents of the artifact itself.

Membership and content are separate questions. `shipped_data_files` walks the source tree, so
every assertion built on it describes the CHECKOUT; only the wheel describes what an installed
user receives. The bundle's JSON Schema and synthetic example are the two files where that
distinction bites hardest — both exist purely to be read by someone who pip-installed
boardwatch and will never see this repo — so they are additionally asserted through the built
artifact, by bytes, against the live models rather than against a copy of themselves.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest
from pydantic import TypeAdapter

from boardwatch.profile_bundle.layout import FIXED_DOCUMENTS, DocumentKind
from boardwatch.profile_bundle.models.manifests import BundleManifest
from boardwatch.profile_bundle.schema import model_for_kind, schema_json
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tools.generalization.allowlists import SHIPPED_DATA
from tools.generalization.discovery import (
    PRODUCTION_MINIMUM_FILES,
    Repo,
    discover,
    find_repo_root,
)
from tools.generalization.packaging import (
    built_wheel,
    check_wheel_completeness,
    missing_from_wheel,
    shipped_data_files,
)

#: How the wheel names the packaged example and the schema resource.
WHEEL_EXAMPLE_ROOT = "boardwatch/profile_bundle/examples/comprehensive"
WHEEL_SCHEMA_MEMBER = "boardwatch/profile_bundle/resources/career-profile.schema.json"

#: The same example as the reviewed inventory names it. Comparing the artifact against this
#: table compares two independently maintained things: a human-reviewed allowlist and whatever
#: the build actually emitted.
INVENTORY_SOURCE_ROOT = "src/boardwatch/profile_bundle/examples/comprehensive/"


def _repo() -> Repo:
    return discover(find_repo_root(Path.cwd().resolve()), minimum_files=PRODUCTION_MINIMUM_FILES)


@pytest.fixture(scope="module")
def wheel() -> Iterator[zipfile.ZipFile]:
    """One build for the whole module: `uv build` is the slow part, not the assertions."""
    with built_wheel(_repo().root) as archive:
        yield archive


def test_shipped_data_files_finds_the_known_data_files() -> None:
    """Non-vacuity: if this returned an empty set the rule would pass on anything."""
    found = shipped_data_files(_repo())
    assert "boardwatch/eligibility/rules.yaml" in found
    assert "boardwatch/extract/taxonomy.yaml" in found
    assert "boardwatch/registry/companies.yaml" in found
    assert "boardwatch/py.typed" in found
    assert len(found) >= 6


def test_the_bundle_schema_and_example_are_in_the_r12_input_set() -> None:
    """Non-vacuity for R12 on the bundle's files: they have to be in the expected set before
    the tree-versus-wheel difference can say anything about them. This is still the CHECKOUT —
    the tests below are the ones that read the artifact."""
    found = shipped_data_files(_repo())
    assert "boardwatch/profile_bundle/resources/career-profile.schema.json" in found
    for document in (
        "manifest.yaml",
        "policy/predicates.yaml",
        "application/gated-facts.yaml",
        "evidence/records.yaml",
        "policy/secret-scan.yaml",
    ):
        assert f"boardwatch/profile_bundle/examples/comprehensive/{document}" in found
    example = {p for p in found if p.startswith("boardwatch/profile_bundle/examples/")}
    assert len(example) == 35


def test_shipped_data_files_excludes_python_and_caches() -> None:
    found = shipped_data_files(_repo())
    assert not [p for p in found if p.endswith(".py")]
    assert not [p for p in found if "__pycache__" in p]


def test_missing_from_wheel_flags_an_absent_file() -> None:
    """Positive control: the diff must actually report a gap."""
    found = missing_from_wheel(
        {"boardwatch/eligibility/rules.yaml", "boardwatch/py.typed"},
        {"boardwatch/py.typed"},
    )
    assert len(found) == 1
    assert found[0].rule == "R12"
    assert found[0].path == "src/boardwatch/eligibility/rules.yaml"


def test_missing_from_wheel_is_quiet_when_everything_ships() -> None:
    assert missing_from_wheel({"boardwatch/py.typed"}, {"boardwatch/py.typed", "extra"}) == []


def test_the_real_wheel_ships_every_data_file() -> None:
    """The end-to-end rule against the real tree. Builds a wheel; takes a second or two."""
    assert check_wheel_completeness(_repo()) == []


# --------------------------------------------------------------------------------------
# The artifact's contents, read from the wheel rather than from src/
# --------------------------------------------------------------------------------------


def test_the_wheel_carries_the_generated_json_schema_byte_for_byte(
    wheel: zipfile.ZipFile,
) -> None:
    """Presence is not enough: the schema exists so an authoring person or agent can read the
    contract without running the code, which is worth nothing if the packaged copy describes
    models that have since changed. Compared against `schema_json()` — the live generator —
    rather than against the file in src/, so a regenerated model with a stale committed
    resource fails here and not in a user's editor."""
    assert WHEEL_SCHEMA_MEMBER in wheel.namelist()
    shipped = wheel.read(WHEEL_SCHEMA_MEMBER).decode("utf-8")
    assert shipped == f"{schema_json()}\n"
    assert json.loads(shipped)["title"] == "boardwatch career-profile bundle"


def test_the_wheels_example_is_exactly_the_reviewed_inventory(wheel: zipfile.ZipFile) -> None:
    """Two independently maintained descriptions of the same 33 documents: the reviewed
    SHIPPED_DATA table and whatever the build emitted. A file that ships without review and a
    reviewed file that fails to ship are both failures, and each is only visible from one side."""
    reviewed = {
        path.removeprefix(INVENTORY_SOURCE_ROOT)
        for path in SHIPPED_DATA
        if path.startswith(INVENTORY_SOURCE_ROOT)
    }
    packaged = {
        name.removeprefix(f"{WHEEL_EXAMPLE_ROOT}/")
        for name in wheel.namelist()
        if name.startswith(f"{WHEEL_EXAMPLE_ROOT}/")
    }
    assert reviewed
    assert packaged == reviewed


@pytest.mark.parametrize(
    ("relative", "kind"),
    sorted((str(path), kind) for path, kind in FIXED_DOCUMENTS.items()),
    ids=lambda value: str(value),
)
def test_every_packaged_example_document_parses_from_the_wheel(
    wheel: zipfile.ZipFile, relative: str, kind: DocumentKind
) -> None:
    """The packaged example is the readable companion to the schema, so it has to be a VALID
    bundle in the artifact, not merely a set of present filenames. Each document is read out of
    the wheel and driven through the restricted loader and its own model — the same two gates
    the product applies to a real user's bundle.

    Parametrised from the live layout grammar rather than a hand-picked subset, so a document
    kind added to `FIXED_DOCUMENTS` is covered the day it lands."""
    member = f"{WHEEL_EXAMPLE_ROOT}/{relative}"
    assert member in wheel.namelist()
    parsed = load_yaml_bytes(wheel.read(member), logical_path=PurePosixPath(relative))
    if kind is DocumentKind.MANIFEST:
        # The manifest is a discriminated draft/revision union, not one model, so
        # `model_for_kind` deliberately refuses it and the loader dispatches it explicitly.
        TypeAdapter(BundleManifest).validate_python(parsed)
    else:
        model_for_kind(kind).model_validate(parsed)


def test_the_three_documents_the_gate_names_are_among_those_parsed() -> None:
    """The parametrisation above is only as good as its source. These three are named in the
    Gate A criteria, so their absence from the live grammar would be a silent scope loss."""
    declared = {str(path) for path in FIXED_DOCUMENTS}
    for required in ("manifest.yaml", "policy/predicates.yaml", "application/gated-facts.yaml"):
        assert required in declared
