"""One layered validation run, and the report it produces (design §20, §21).

Every command and every test reaches validation through `validate_bundle`. That is deliberate: the
layers are separately testable pure functions, but the *order* they run in and the inputs they are
given are themselves contracts, and a caller assembling them by hand is a caller who can forget one.

## Three things this module owns and the layers cannot

**The blob reader.** `validate_digest` returns nothing at all when `ctx.blobs is None` — a digest
needs the bytes, and reporting a mismatch that was never computed would be a measurement nobody
took. That silence is only safe because a reader is constructed here, unconditionally, and a test
asserts it here rather than there (D-115: test a guarantee where it lands).

**The date.** §20 makes structural, referential, evidence, semantic and digest validity pure
functions of bundle content — "wall-clock time cannot turn the same bytes from valid to invalid" —
so nothing under `profile_bundle/` reads a clock. `as_of` therefore arrives from the caller, and
requesting completeness without one is refused rather than defaulted: substituting today's date
would make the report claim a measurement against a moment the operator never chose. The CLI owns
that default, because the CLI is where "today" is a decision a human made.

**The order.** Referential validation assumes IDs are unique, semantic validation assumes references
resolve, and completeness assumes the catalogs it reads are present. Nothing short-circuits on a
finding — one hand edit that breaks fifty references reports fifty times — but completeness is
skipped outright when a structural prerequisite is absent, because a hundred consequences of one
missing catalog is not a more useful report than the missing catalog.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from boardwatch.profile_bundle import secret_scan
from boardwatch.profile_bundle.canonical import (
    CanonicalizationError,
    FilesystemBlobReader,
    MissingBlobError,
    candidate_content_digest,
)
from boardwatch.profile_bundle.errors import (
    Diagnostic,
    OperationOutcome,
    ProfileBundleError,
    diagnostic,
)
from boardwatch.profile_bundle.models.manifests import RevisionManifest
from boardwatch.profile_bundle.paths import blobs_dir
from boardwatch.profile_bundle.reports import (
    ValidationReport,
    count_diagnostics,
    empty_report,
    outcome_for_report,
)
from boardwatch.profile_bundle.validation.completeness import (
    ancestry_completeness,
    validate_completeness,
)
from boardwatch.profile_bundle.validation.context import (
    STRUCTURAL_PREREQUISITES,
    ParentSnapshot,
    TreeMode,
    ValidationContext,
    build_context,
    parse_error_diagnostics,
)
from boardwatch.profile_bundle.validation.digest import (
    recomputed_candidate_digest,
    validate_digest,
)
from boardwatch.profile_bundle.validation.evidence import (
    evidence_completeness,
    validate_evidence_structural,
)
from boardwatch.profile_bundle.validation.history import validate_history
from boardwatch.profile_bundle.validation.imports import imports_completeness, validate_imports
from boardwatch.profile_bundle.validation.referential import validate_referential
from boardwatch.profile_bundle.validation.semantic import semantic_completeness, validate_semantic
from boardwatch.profile_bundle.validation.structural import validate_structural


def installed_secret_ruleset_version() -> int:
    """The secret-scan ruleset version THIS build ships, read at call time.

    Not a default argument and not a by-name import: both would snapshot the value when this module
    loaded. `evidence_completeness` exists so a caller can ask "what would today's catalog say?"
    about an older revision, and a snapshot would silently keep asking yesterday's question.
    """
    return secret_scan.CURRENT_RULESET_VERSION


def validate_bundle(
    root: Path,
    *,
    bundle_root: Path,
    mode: TreeMode,
    completeness: bool = False,
    as_of: date | None = None,
    parent: ParentSnapshot | None = None,
    deep_history: bool = False,
) -> OperationOutcome[ValidationReport]:
    """Validate one logical tree and report everything every layer found.

    `root` is the tree — a digest-named revision directory or a draft — and `bundle_root` is the
    bundle it lives in. Both are required because the blob store, `CURRENT`, and the ancestor chain
    all live at the root while the documents live in the tree; deriving one from the other would
    guess at a layout the caller already knows.

    `completeness` is separate from `as_of` so that asking for a date cannot silently widen what a
    plain `validate` reports. Requesting completeness without a date raises: that is a programming
    error at the call boundary, not something a bundle did, so it is not a diagnostic.
    """
    # Imported here rather than at module scope, and this is the one import in the package that is:
    # `storage` reads `validation.context`, which executes this package's `__init__`, which imports
    # this module. A module-level import therefore made `storage` — and every module that reads it,
    # which is all four commands — impossible to import FIRST in a fresh interpreter. Nothing caught
    # it because a test session and the CLI both happen to import `validation` earlier. Deferring
    # the lower-level module's import to call time breaks the cycle without moving either
    # responsibility, and `test_profile_bundle_promotion.py` pins the outside fact: every module in
    # the package imports on its own.
    from boardwatch.profile_bundle.storage import SelectionError, require_confined_root

    if completeness and as_of is None:
        raise ValueError(
            "completeness validation needs an explicit as_of date; this package reads no clock, so "
            "the caller chooses the date and the report states it"
        )
    if deep_history and not completeness:
        raise ValueError(
            "deep_history is the ancestor audit inside completeness validation, so it needs "
            "completeness=True; accepting it alone would answer the one question that makes an "
            "edited ancestor visible with a clean report nobody ran"
        )
    try:
        # Before a single byte is read: §6's self-containment is what makes the digest layer's
        # answer mean anything, and a symlinked `blobs/` would otherwise hash content from outside
        # the root into `evidence_set_digest` and so into `bundle_digest`.
        require_confined_root(bundle_root)
    except SelectionError as exc:
        return outcome_for_report(empty_report((diagnostic(exc.code, str(exc)),)))
    blobs = FilesystemBlobReader(blobs_dir(bundle_root))
    try:
        ctx = build_context(
            root, mode=mode, blobs=blobs, parent=parent, bundle_root=bundle_root
        )
    except ProfileBundleError as exc:
        # There is no partially-parsed tree worth handing to a layer, and no identity to report.
        return outcome_for_report(empty_report(parse_error_diagnostics(exc)))

    findings: list[Diagnostic] = [
        *validate_structural(ctx),
        *validate_referential(ctx),
        *validate_evidence_structural(ctx),
        *validate_semantic(ctx),
        *validate_history(ctx),
        *validate_imports(ctx),
        *validate_digest(ctx),
    ]
    # `as_of` in the report means exactly "the dated checks ran at this date", so it is set from
    # what happened rather than from what was asked for. A skipped run that still reported the
    # requested date and `blocker: 0` was indistinguishable in JSON from a completeness run that
    # found nothing — and it reads as the reassuring one of the two.
    completeness_ran = completeness and as_of is not None and _prerequisites_are_present(ctx)
    if completeness_ran and as_of is not None:
        findings.extend(
            evidence_completeness(
                ctx, installed_ruleset_version=installed_secret_ruleset_version()
            )
        )
        findings.extend(semantic_completeness(ctx))
        findings.extend(imports_completeness(ctx))
        findings.extend(validate_completeness(ctx, as_of=as_of))
        findings.extend(ancestry_completeness(ctx, deep=deep_history))

    return outcome_for_report(
        ValidationReport(
            schema_version=ctx.manifest.schema_version,
            bundle_digest=_reported_bundle_digest(ctx),
            candidate_digest=_reported_candidate_digest(ctx),
            as_of=as_of if completeness_ran else None,
            diagnostics=tuple(findings),
            counts=count_diagnostics(findings),
        )
    )


def _prerequisites_are_present(ctx: ValidationContext) -> bool:
    """Whether completeness has the catalogs it reads.

    Both `STRUCTURAL_PREREQUISITES` entries are named there with the reason they matter: every fact
    is checked against `policy/predicates.yaml` and every fact and metric cites evidence from
    `evidence/records.yaml`. Without them completeness would report the consequences of one missing
    file as dozens of independent blockers. The absence is already an error from the structural
    layer, so a run that skips completeness here still never reads as clean.
    """
    return all(ctx.documents.get(path) is not None for path in STRUCTURAL_PREREQUISITES)


def _reported_bundle_digest(ctx: ValidationContext) -> str | None:
    """A draft's `bundle_digest` is the `""` sentinel, so there is nothing to report."""
    manifest = ctx.manifest
    return manifest.bundle_digest if isinstance(manifest, RevisionManifest) else None


def _reported_candidate_digest(ctx: ValidationContext) -> str | None:
    """The candidate digest THIS TREE recomputes — never a value it merely declares.

    For a draft that is the digest the owner is being asked to approve (§19 step 7); for a promoted
    revision it is the inverse candidate view §20.6 requires to equal both the manifest's
    `approved_candidate_digest` and the appended approval stamp. Both are computed from the bytes on
    disk, so the field means one thing in machine output.

    Reporting `manifest.approved_candidate_digest` verbatim is what this replaces: a re-sealed
    revision nobody approved printed its own claim under the same key as a verified value, and no
    consumer could tell them apart. `None` is "this run made no claim" — a missing blob, an
    unrecoverable candidate view, or a parent that is not on disk — and it is deliberately
    indistinguishable from a draft whose parent was not supplied, because both are the same absence.
    """
    manifest = ctx.manifest
    if isinstance(manifest, RevisionManifest):
        return recomputed_candidate_digest(ctx)
    if manifest.parent_bundle_digest is not None and ctx.parent is None:
        return None
    blobs = ctx.blobs
    if blobs is None:  # pragma: no cover - `validate_bundle` always supplies one
        return None
    try:
        return candidate_content_digest(
            ctx.documents, blobs, ctx.parent.envelope if ctx.parent is not None else None
        )
    except (MissingBlobError, CanonicalizationError):
        # A missing blob is the evidence layer's finding and an unrecoverable candidate view is
        # `validate_history`'s; reporting a digest here would be inventing one either way.
        return None


__all__ = ["installed_secret_ruleset_version", "validate_bundle"]
