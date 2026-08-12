"""Characterization: the four existing serializers keep their exact current output.

Design §7 forbids consolidating the bundle's canonical serializer with `eligibility/hashing.py`,
`extract/taxonomy.py::_version_of`, `eligibility/catalog.py::_version_of`, or
`tailor/persona.py::_version_of`. Those four feed stored identities and `policy_version`, so their
bytes are load-bearing history: the eligibility tables carry BEFORE UPDATE/DELETE triggers, and a
row that can only ever be superseded cannot be re-keyed by a refactor.

The difference is visible and deliberate. All four use `json.dumps(sort_keys=True,
separators=(",", ":"))` with `ensure_ascii` at its DEFAULT of `True` and no Unicode normalisation, so
a non-ASCII payload comes out `\\uXXXX`-escaped and a decomposed character stays decomposed. The
bundle serializer uses `ensure_ascii=False` and NFC. One fixed non-ASCII payload pins both facts,
which is what makes an accidental consolidation fail here rather than in a user's ledger.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import _version_of as catalog_version_of
from boardwatch.eligibility.hashing import canonical as eligibility_canonical
from boardwatch.eligibility.hashing import digest as eligibility_digest
from boardwatch.extract.taxonomy import _version_of as taxonomy_version_of
from boardwatch.profile_bundle.canonical import canonical_json_bytes, digest_of
from boardwatch.tailor.persona import _version_of as persona_version_of
from tests.profile_bundle.import_graph import containing_package, imported_modules

REPO_ROOT = Path(__file__).resolve().parents[2]

#: One payload, chosen to expose both differences at once: a non-ASCII character that has a
#: composed and a decomposed spelling, plus a key that sorts after it.
COMPOSED = "Zürich"
DECOMPOSED = unicodedata.normalize("NFD", COMPOSED)
PAYLOAD = {"city": COMPOSED, "note": "café"}


def test_the_eligibility_serializer_keeps_its_exact_output() -> None:
    """A literal digest, not a length check: the point is that these BYTES do not move."""
    assert eligibility_canonical(PAYLOAD) == '{"city":"Z\\u00fcrich","note":"caf\\u00e9"}'
    assert (
        eligibility_digest(PAYLOAD)
        == "16691294d6a873bd1d24fc218720dd1f856cfc7419e33fe880142d3c3d2bdfc1"
    )


def test_existing_serializers_escape_non_ascii_and_the_bundle_one_does_not() -> None:
    """The visible, deliberate difference. If these ever agree, something was consolidated."""
    assert "\\u00fc" in eligibility_canonical(PAYLOAD)
    assert "ü" not in eligibility_canonical(PAYLOAD)
    assert "ü".encode() in canonical_json_bytes(PAYLOAD)
    assert b"\\u00fc" not in canonical_json_bytes(PAYLOAD)


def test_existing_serializers_do_not_normalise_unicode() -> None:
    """Composed and decomposed spellings hash DIFFERENTLY through the existing serializers."""
    composed = eligibility_digest({"city": COMPOSED})
    decomposed = eligibility_digest({"city": DECOMPOSED})
    assert composed != decomposed


def test_the_bundle_serializer_does_normalise_unicode() -> None:
    """And identically through the bundle's, which is why they must not be merged."""
    assert digest_of({"city": COMPOSED}) == digest_of({"city": DECOMPOSED})


def test_the_three_version_of_helpers_keep_their_revision_suffixed_construction() -> None:
    """Each combines canonical JSON with its own revision constant. Pinned by reproduction rather
    than by a literal digest, so the test says WHICH construction is being held still."""
    import hashlib

    from boardwatch.eligibility.catalog import CATALOG_REVISION
    from boardwatch.extract.taxonomy import EXTRACTOR_REVISION
    from boardwatch.tailor.persona import PERSONA_REVISION

    canonical = json.dumps(PAYLOAD, sort_keys=True, separators=(",", ":"))
    assert (
        taxonomy_version_of(PAYLOAD)
        == hashlib.sha256(
            f"{canonical}|extractor_revision={EXTRACTOR_REVISION}".encode()
        ).hexdigest()
    )
    assert (
        catalog_version_of(PAYLOAD)
        == hashlib.sha256(f"{canonical}|catalog_revision={CATALOG_REVISION}".encode()).hexdigest()
    )
    assert (
        persona_version_of(PAYLOAD)
        == hashlib.sha256(f"{canonical}|persona_revision={PERSONA_REVISION}".encode()).hexdigest()
    )


def test_the_three_version_of_helpers_disagree_with_the_bundle_serializer() -> None:
    """They are delimiter-framed and ASCII-escaped; the bundle's is neither."""
    bundle = digest_of(PAYLOAD).removeprefix("sha256:")
    assert taxonomy_version_of(PAYLOAD) != bundle
    assert catalog_version_of(PAYLOAD) != bundle
    assert persona_version_of(PAYLOAD) != bundle


CANONICAL_MODULE = "boardwatch.profile_bundle.canonical"
BUNDLE_PACKAGE = "boardwatch.profile_bundle"


def reaches_the_bundle_serializer(source: str, *, package: str = "") -> bool:
    """Whether `source` gets hold of the bundle's private serializer, by any spelling.

    Two lenses, because neither sees the other's cases. The dotted substring catches a name
    assembled for `importlib` and any attribute path a parser would not recognise as an import;
    the import resolver catches `from boardwatch.profile_bundle import canonical`, which contains
    no dotted path at all and is the form every other sibling module is imported by in
    `cli/profile_bundle_cmd.py`. A guard written against only the first catches the one instance
    that was removed and not the class it belongs to.

    The resolving half is `import_graph.imported_modules` rather than an `ast.walk` written out
    here again. Two independent rewrites of this guard landed in the same merge — one keeping the
    substring lens, one resolving through the shared graph — and a second AST walker beside the
    first is precisely the "same rule written down twice" this package has already paid several
    review rounds for. `package` is what makes a *relative* import resolvable, so
    `from ..profile_bundle import canonical` inside `cli/` is caught rather than mis-resolved.
    """
    if f"{BUNDLE_PACKAGE}.canonical" in source:
        return True
    return CANONICAL_MODULE in imported_modules(source, package=package)


@pytest.mark.parametrize(
    ("source", "reaches"),
    [
        ("from boardwatch.profile_bundle.canonical import digest_of", True),
        ("import boardwatch.profile_bundle.canonical", True),
        # The spelling the substring lens cannot see, and the one a next author would reach for:
        # it is how `cli/profile_bundle_cmd.py` imports every other sibling in the package.
        ("from boardwatch.profile_bundle import canonical", True),
        ("from boardwatch.profile_bundle import canonical as bundle_hash", True),
        ("def later():\n    from boardwatch.profile_bundle import canonical\n", True),
        ("importlib.import_module('boardwatch.profile_bundle.canonical')", True),
        # Controls: reaching the package, or a differently-named module in it, is not this.
        ("from boardwatch.profile_bundle import authoring, drafts", False),
        ("import boardwatch.profile_bundle", False),
        ("from boardwatch.eligibility.hashing import canonical", False),
        ("canonical = {'not': 'an import'}", False),
    ],
)
def test_the_guard_sees_every_spelling_of_the_forbidden_import(source: str, reaches: bool) -> None:
    """The guard's own positive controls, so it is not merely agreeing with the tree it scans.

    A detector asserted only against a clean repository passes for every reason including being
    unable to fire, which is exactly how the previous version of this check went blind to the one
    import form the CLI already uses.
    """
    assert reaches_the_bundle_serializer(source) is reaches


def test_no_existing_module_imports_the_bundle_serializer() -> None:
    """The one-directional dependency: nothing outside the package touches the private serializer.

    Its bytes are identity, and a second caller elsewhere is how a shared hash quietly acquires a
    second meaning.

    Residual limit, stated rather than hidden: `from boardwatch import profile_bundle` followed by
    attribute access is not matched, because `cli/profile_bundle_cmd.py` legitimately imports the
    package that way. The tailor side of that route is closed by prefix in
    `test_profile_bundle_tailor_isolation.py`.
    """
    offenders = []
    for path in (REPO_ROOT / "src" / "boardwatch").rglob("*.py"):
        if "profile_bundle" in path.parts:
            continue
        if reaches_the_bundle_serializer(
            path.read_text(encoding="utf-8"), package=containing_package(path)
        ):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_the_bundle_serializer_does_not_import_the_existing_hashers() -> None:
    """And nothing in the other direction either: `canonical.py` must stand alone."""
    text = (REPO_ROOT / "src/boardwatch/profile_bundle/canonical.py").read_text(encoding="utf-8")
    for existing in (
        "eligibility.hashing",
        "extract.taxonomy",
        "eligibility.catalog",
        "tailor.persona",
    ):
        assert f"import {existing}" not in text
        assert f"from boardwatch.{existing}" not in text
