"""Parsing one logical tree, and the context every validation layer reads.

Two shapes of failure are deliberately different here.

**A file that will not parse raises**, carrying every per-file diagnostic at once. There is no
partially-parsed context worth handing to a later layer: referential validation over a tree missing
`evidence/records.yaml` would report a hundred broken references that are really one missing file.

**Everything a parsed tree can express is a diagnostic.** Once the bytes are models, layers
accumulate independent findings and never stop at the first, because an operator fixing a bundle
wants the whole list.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.canonical import BlobReader
from boardwatch.profile_bundle.errors import (
    BundleIoError,
    BundleLayoutError,
    Diagnostic,
    IssueCode,
    ProfileBundleError,
    RestrictedYamlError,
    UnsupportedSchemaVersionError,
    diagnostic,
)
from boardwatch.profile_bundle.index import BundleIndex, build_index
from boardwatch.profile_bundle.layout import (
    DocumentKind,
    SourceFile,
    discover_source_files,
)
from boardwatch.profile_bundle.models.documents import BundleDocuments, DocumentModel
from boardwatch.profile_bundle.models.manifests import BundleManifest, StableManifestEnvelope
from boardwatch.profile_bundle.schema import model_for_kind, require_supported_schema
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

_MANIFEST_ADAPTER: Final[TypeAdapter[BundleManifest]] = TypeAdapter(BundleManifest)

TreeMode = Literal["draft", "revision"]


class BundleParseError(ProfileBundleError):
    """One or more documents could not be turned into models.

    Carries every finding rather than only the first, so `validate` on a freshly hand-edited bundle
    lists all the broken files in one pass.
    """

    def __init__(self, diagnostics: Sequence[Diagnostic]) -> None:
        ordered = tuple(sorted(diagnostics, key=lambda d: d.sort_key()))
        super().__init__(
            f"{len(ordered)} document(s) could not be parsed: "
            + ", ".join(sorted({d.path or "<tree>" for d in ordered}))
        )
        self.diagnostics = ordered


def _model_error_diagnostics(path: PurePosixPath, error: ValidationError) -> list[Diagnostic]:
    """Pydantic errors, one diagnostic per field error.

    Only the location and Pydantic's own message go in; the rejected input does NOT, because a
    contact channel or a capture excerpt failing a constraint would otherwise be echoed into a
    report an operator may paste elsewhere.
    """
    found: list[Diagnostic] = []
    for detail in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in detail["loc"]) or "<document>"
        found.append(
            diagnostic(
                IssueCode.MODEL_VALIDATION_ERROR,
                f"{path}: {location}: {detail['msg']}",
                path=path.as_posix(),
                field=location,
                error_type=str(detail["type"]),
            )
        )
    return found


def _read(entry: SourceFile) -> bytes:
    try:
        return entry.abspath.read_bytes()
    except OSError as exc:
        raise BundleIoError(f"{entry.logical_path}: {exc}") from exc


def load_documents(root: Path, *, mode: TreeMode) -> BundleDocuments:
    """Parse the logical tree at `root` into models.

    `mode` decides only whether a `COMPLETE` marker is admissible beside the documents: a promoted
    revision has one, a draft must not. It does not relax any document contract, because a draft
    that cannot become a revision should fail while it is still cheap to fix.

    Missing declared files are NOT reported here — `validate_structural` owns that, so an operator
    sees the missing file listed alongside every other finding instead of as an exception.
    """
    entries = discover_source_files(root, final_revision=mode == "revision")

    findings: list[Diagnostic] = []
    by_path: dict[PurePosixPath, DocumentModel] = {}
    manifest: BundleManifest | None = None

    for entry in entries:
        try:
            parsed = load_yaml_bytes(_read(entry), logical_path=entry.logical_path)
        except RestrictedYamlError as exc:
            findings.append(
                diagnostic(
                    exc.code,
                    str(exc),
                    path=entry.logical_path.as_posix(),
                )
            )
            continue
        try:
            if entry.kind is DocumentKind.MANIFEST:
                manifest = _MANIFEST_ADAPTER.validate_python(parsed)
            else:
                model = model_for_kind(entry.kind)
                # `model_for_kind` is typed as returning `type[BaseModel]`; the mapping it reads
                # is what guarantees the result is a member of the `DocumentModel` union.
                by_path[entry.logical_path] = cast(DocumentModel, model.model_validate(parsed))
        except ValidationError as exc:
            findings.extend(_model_error_diagnostics(entry.logical_path, exc))

    if manifest is None:
        findings.append(
            diagnostic(
                IssueCode.MISSING_REQUIRED_FILE,
                "manifest.yaml is absent; the revision cannot be identified",
                path="manifest.yaml",
            )
        )
    if findings:
        raise BundleParseError(findings)
    assert manifest is not None  # narrowed by the findings check above

    # Refusing an unsupported schema version before any layer runs: a future version may have moved
    # a contract this build still checks, and reporting it clean would be worse than refusing.
    require_supported_schema(manifest.schema_version)
    return BundleDocuments(manifest=manifest, by_path=by_path)


@dataclass(frozen=True)
class ParentSnapshot:
    """The direct parent revision, when one is on disk and readable.

    Optional on purpose: §17 lets a bundle be validated with its ancestry unavailable, and the
    ancestry-dependent checks then report `unverifiable_ancestor` as a blocker rather than
    pretending to have compared against something.
    """

    root: Path
    documents: BundleDocuments
    envelope: StableManifestEnvelope
    index: BundleIndex


@dataclass(frozen=True)
class ValidationContext:
    """Everything the layers read. Constructed once so no layer re-parses the tree."""

    root: Path
    mode: TreeMode
    documents: BundleDocuments
    index: BundleIndex
    blobs: BlobReader | None = None
    parent: ParentSnapshot | None = None
    #: The bundle root, when validating a tree that lives inside one. Blob paths and orphan
    #: reporting need it; a bare tree handed in for inspection legitimately has none.
    bundle_root: Path | None = None

    @property
    def manifest(self) -> BundleManifest:
        return self.documents.manifest

    def path_of(self, record_id: str) -> str | None:
        return self.index.path_of(record_id)


def build_context(
    root: Path,
    *,
    mode: TreeMode,
    blobs: BlobReader | None = None,
    parent: ParentSnapshot | None = None,
    bundle_root: Path | None = None,
) -> ValidationContext:
    """Parse and index in one step.

    Raises `BundleParseError` or `BundleLayoutError` on bytes that will not become models.
    """
    documents = load_documents(root, mode=mode)
    return ValidationContext(
        root=root,
        mode=mode,
        documents=documents,
        index=build_index(documents),
        blobs=blobs,
        parent=parent,
        bundle_root=bundle_root,
    )


def context_from_documents(
    documents: BundleDocuments,
    *,
    root: Path,
    mode: TreeMode,
    blobs: BlobReader | None = None,
    parent: ParentSnapshot | None = None,
    bundle_root: Path | None = None,
) -> ValidationContext:
    """Index an already-parsed tree. Used by tests and by the promotion path, which parses once."""
    return ValidationContext(
        root=root,
        mode=mode,
        documents=documents,
        index=build_index(documents),
        blobs=blobs,
        parent=parent,
        bundle_root=bundle_root,
    )


def parse_error_diagnostics(exc: ProfileBundleError) -> tuple[Diagnostic, ...]:
    """Turn a typed load failure into diagnostics the report layer can print.

    `BundleLayoutError` and `BundleIoError` become one diagnostic each; a `BundleParseError` already
    carries its own list. Nothing here guesses at a code from an exception message.

    `UnsupportedSchemaVersionError` needs its own arm because `load_documents` raises it directly
    from `require_supported_schema`: without one it falls through to `internal_error`, which is the
    right exit code (both are `could_not_complete`) under the wrong name, so an operator would file
    a bug instead of upgrading Boardwatch. There is deliberately no arm for
    `UnsupportedSecretRulesetError` — it is raised while scanning captures, which happens inside a
    layer that reports its own diagnostics, and never on the load path this function serves.
    """
    if isinstance(exc, BundleParseError):
        return exc.diagnostics
    if isinstance(exc, UnsupportedSchemaVersionError):
        return (diagnostic(IssueCode.UNSUPPORTED_SCHEMA_VERSION, str(exc)),)
    if isinstance(exc, BundleLayoutError):
        return (diagnostic(IssueCode.UNKNOWN_FILE, str(exc)),)
    if isinstance(exc, BundleIoError):
        return (diagnostic(IssueCode.IO_ERROR, str(exc)),)
    return (diagnostic(IssueCode.INTERNAL_ERROR, str(exc)),)


def sorted_diagnostics(found: Sequence[Diagnostic]) -> tuple[Diagnostic, ...]:
    """The one ordering every report uses: tier, code, path, record ID, message."""
    return tuple(sorted(found, key=lambda d: d.sort_key()))


#: Documents whose absence is reported once, as a missing file, instead of as the flood of broken
#: references it would otherwise produce.
STRUCTURAL_PREREQUISITES: Final[Mapping[str, str]] = {
    "evidence/records.yaml": "every fact and metric cites evidence from here",
    "policy/predicates.yaml": "every fact's predicate is checked against this catalog",
}
