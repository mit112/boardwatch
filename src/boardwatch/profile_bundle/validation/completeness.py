"""Completeness validation: what a valid revision still cannot be used for (design §20.5).

Completeness is reported separately from validity because "a bundle may validly preserve
uncertainty while being incomplete for downstream use". An unresolved conflict, a lapsed credential
and a stale fact are all faithful records of what is known; none of them makes the revision invalid,
and every one of them makes some named record unusable.

## The only clock in the package

`as_of` is a parameter, never a read of the system clock. §20 requires structural, referential,
evidence, semantic and digest validity to be pure functions of bundle content — "wall-clock time
cannot turn the same bytes from valid to invalid" — so the date has to arrive from the caller or the
guarantee is unverifiable. It follows `evidence_completeness`'s `installed_ruleset_version`: a
time- or environment-varying input is a keyword argument the caller injects, so a caller can ask
"what would this bundle look like on 1 March?" without this layer deciding.

## Three conditions that look alike and are not

- `stale_fact` is the **declared** `VerificationState.STALE`. No date is read.
- `expired_review` is **computed**: the fact's `reviewed_at` plus its predicate's
  `review_interval_days` is in the past at `as_of`.
- `fact_value_expired` is also computed, from a different declaration: the fact's `expires_at` under
  a predicate whose `ExpiryBehaviour` is `block_active_use_after_value_date`.

They are separate codes because they call for separate actions — retire the record, re-review it, or
renew the credential — and a code whose meaning depends on which check emitted it cannot be acted on
from the JSON.

## What §20.5 lists that is NOT checked here

"One person entity", "explicit education/employment/project status" and metric review coverage are
all model contracts: `IdentityDocument.person` is one required field, every entity kind §9 gives a
status declares it as a required closed enum, and `MetricRecord.reviewed_at` is a required `date`
while `review_interval_days` is a column on a `PredicateSpec` no metric has. Per D-115 a check that
cannot fire is deleted rather than shipped, so there is no branch and no issue code for any of the
three; `test_profile_bundle_completeness.py` names the layer each guarantee actually lands in.

## Expiry is evaluated only over effective facts

Exactly as §10.4 evaluates cardinality and exclusivity. A `stale`, `rejected` or `superseded` record
is already locally blocked (§21), and reporting that its review also lapsed would hand the operator
a second finding about a record they have already retired. The packaged example proves the point: it
carries one stale fact whose `expires_at` is also in the past, and it is reported exactly once.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.canonical import (
    CanonicalizationError,
    MissingBlobError,
    bundle_digest,
)
from boardwatch.profile_bundle.effective import effective_fact_ids, eligible_metric
from boardwatch.profile_bundle.errors import (
    BundlePathError,
    Diagnostic,
    IssueCode,
    JsonValue,
    ProfileBundleError,
    RestrictedYamlError,
    UnsupportedSchemaVersionError,
    diagnostic,
    tier_of,
)
from boardwatch.profile_bundle.models.base import EFFECTIVE_STATES, Surface, VerificationState
from boardwatch.profile_bundle.models.claims import ClaimStatus
from boardwatch.profile_bundle.models.evidence import SufficiencyState
from boardwatch.profile_bundle.models.imports import ExclusionLedger
from boardwatch.profile_bundle.models.manifests import BundleManifest, RevisionManifest
from boardwatch.profile_bundle.models.policy import ExpiryBehaviour
from boardwatch.profile_bundle.paths import revision_root
from boardwatch.profile_bundle.schema import require_supported_schema
from boardwatch.profile_bundle.validation.context import ValidationContext, load_documents
from boardwatch.profile_bundle.validation.imports import import_totals
from boardwatch.profile_bundle.validation.referential import (
    records_blocked_by_unresolved_conflicts,
)
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

IDENTITY_PATH: Final = "facts/identity.yaml"
CONFLICTS_PATH: Final = "conflicts/groups.yaml"
MANIFEST_PATH: Final = "manifest.yaml"

_MANIFEST_ADAPTER: Final[TypeAdapter[BundleManifest]] = TypeAdapter(BundleManifest)

#: Why one ancestor could not be verified. Typed at the raise site so a consumer classifies on
#: `details["reason"]` rather than on the message text.
AncestorFault = Literal[
    "absent",
    "unreadable",
    "malformed",
    "unsupported_schema",
    "not_a_revision",
    "declared_digest_mismatch",
    "content_digest_mismatch",
    "cycle",
]


def validate_completeness(ctx: ValidationContext, *, as_of: date) -> tuple[Diagnostic, ...]:
    """Every completeness finding derivable from this revision's own content, plus the counts.

    `as_of` is required, not defaulted: a completeness run whose date nobody chose is a measurement
    whose meaning nobody can reconstruct, and §20 requires the date to be reported in machine
    output.
    """
    # Hoisted once. `effective_fact_ids` is O(facts + conflict candidates) per call, so asking it
    # per fact would make every check below quadratic for no benefit — the context is frozen.
    effective = effective_fact_ids(ctx)
    return (
        *_every_projected_surface_has_a_contact_channel(ctx, effective),
        *_imported_facts_declare_a_review_state(ctx),
        *_stale_facts_are_locally_blocked(ctx),
        *_effective_facts_are_inside_their_review_interval(ctx, as_of, effective),
        *_effective_facts_have_not_passed_their_value_date(ctx, as_of, effective),
        *_unresolved_conflicts_block_their_candidates(ctx),
        completeness_counts(ctx, effective),
    )


# --------------------------------------------------------------------------------------
# Required profile fields (§20.5)
# --------------------------------------------------------------------------------------


def _projected_surfaces(ctx: ValidationContext, effective: frozenset[str]) -> frozenset[Surface]:
    """The surfaces this bundle actually asks to be projected to.

    Derived from what is usable rather than from the `Surface` enum: a résumé-only profile has not
    "requested" a public surface, and demanding a public contact channel for it would make an
    entirely reasonable bundle permanently incomplete.
    """
    surfaces: set[Surface] = set()
    for fact in ctx.index.facts:
        if fact.fact_id in effective:
            surfaces.update(fact.allowed_surfaces)
    for metric in ctx.index.metrics:
        if eligible_metric(metric, ctx):
            surfaces.update(metric.allowed_surfaces)
    for skill in ctx.index.skills:
        if skill.verification_state in EFFECTIVE_STATES:
            surfaces.update(skill.allowed_surfaces)
    for claim in ctx.index.claims:
        if claim.status is ClaimStatus.APPROVED:
            surfaces.update(claim.allowed_surfaces)
    return frozenset(surfaces)


def _contact_surfaces(ctx: ValidationContext) -> frozenset[Surface]:
    return frozenset(
        surface
        for contact in ctx.index.contacts
        if contact.verification_state in EFFECTIVE_STATES
        for surface in contact.allowed_surfaces
    )


def _every_projected_surface_has_a_contact_channel(
    ctx: ValidationContext, effective: frozenset[str]
) -> Iterator[Diagnostic]:
    """§20.5: "at least one contact channel for a requested surface".

    The finding names the surface and never the channel: a diagnostic is pasted into bug reports,
    and an email address or phone number is exactly what must not travel in one.
    """
    missing = _projected_surfaces(ctx, effective) - _contact_surfaces(ctx)
    for surface in sorted(missing, key=str):
        yield diagnostic(
            IssueCode.MISSING_CONTACT_CHANNEL,
            f"records are projected to the {surface} surface but no usable contact channel "
            f"declares it, so nothing produced for that surface can reach the person",
            path=IDENTITY_PATH,
            surface=str(surface),
        )


def _imported_facts_declare_a_review_state(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§20.5: "a declared review state for every imported fact".

    `verification_state` is a required field, so "undeclared" cannot mean absent. The non-vacuous
    reading is the one §18 sets up: an imported fact still sitting at `unresolved` is one nobody has
    decided about, and the import is not finished until somebody has.
    """
    for fact in ctx.index.facts:
        if fact.import_lineage is None:
            continue
        if fact.verification_state is not VerificationState.UNRESOLVED:
            continue
        yield diagnostic(
            IssueCode.MISSING_REVIEW_STATE,
            f"{fact.fact_id} was imported from {fact.import_lineage.source_id} and is still "
            f"unresolved; an imported fact needs a decided review state before it can be used",
            path=ctx.path_of(fact.fact_id),
            record_id=fact.fact_id,
            source_id=fact.import_lineage.source_id,
        )


# --------------------------------------------------------------------------------------
# Declared and computed staleness (§20.5, §21)
# --------------------------------------------------------------------------------------


def _stale_facts_are_locally_blocked(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§21: a stale fact is "retained and locally blocked".

    Retained is the point — nothing here proposes deleting it. The blocker exists so an operator
    reading the report can see that a record they may believe is in play is not.
    """
    for fact in ctx.index.facts:
        if fact.verification_state is not VerificationState.STALE:
            continue
        yield diagnostic(
            IssueCode.STALE_FACT,
            f"{fact.fact_id} declares verification_state 'stale', so it is retained but cannot be "
            f"used downstream until it is re-verified or superseded",
            path=ctx.path_of(fact.fact_id),
            record_id=fact.fact_id,
        )


def _effective_facts_are_inside_their_review_interval(
    ctx: ValidationContext, as_of: date, effective: frozenset[str]
) -> Iterator[Diagnostic]:
    """The computed half of §20.5's expiry clause: `reviewed_at` plus the predicate's interval.

    Strictly after, not on: the interval says how long a review remains good for, so reporting the
    due date itself as past would make every interval one day shorter than the catalog states.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return  # `MISSING_REQUIRED_FILE`; the caller skips completeness when this is absent
    specs = catalog.by_id
    for fact in ctx.index.facts:
        if fact.fact_id not in effective:
            continue
        spec = specs.get(fact.predicate)
        if spec is None:
            continue  # `UNKNOWN_PREDICATE` is the semantic layer's finding
        interval = spec.expiry.review_interval_days
        if interval is None:
            continue
        due = fact.reviewed_at + timedelta(days=interval)
        if due >= as_of:
            continue
        yield diagnostic(
            IssueCode.EXPIRED_REVIEW,
            f"{fact.fact_id} was last reviewed on {fact.reviewed_at.isoformat()} and "
            f"{fact.predicate} requires review every {interval} days, so it was due on "
            f"{due.isoformat()}",
            path=ctx.path_of(fact.fact_id),
            record_id=fact.fact_id,
            reviewed_at=fact.reviewed_at.isoformat(),
            review_due=due.isoformat(),
            as_of=as_of.isoformat(),
            predicate=str(fact.predicate),
        )


def _effective_facts_have_not_passed_their_value_date(
    ctx: ValidationContext, as_of: date, effective: frozenset[str]
) -> Iterator[Diagnostic]:
    """§10.4's `block_active_use_after_value_date`, evaluated at `as_of`.

    Both declarations are required: the fact's `expires_at` and the predicate's behaviour. A date
    authored on a fact whose predicate expires `never` records when the author expects to revisit
    it, not a date after which the value stops being true — blocking on that alone would retire a
    live skill because somebody left themselves a note.
    """
    catalog = ctx.index.predicates
    if catalog is None:
        return
    specs = catalog.by_id
    for fact in ctx.index.facts:
        if fact.fact_id not in effective or fact.expires_at is None:
            continue
        spec = specs.get(fact.predicate)
        if spec is None or spec.expiry.behaviour is not (
            ExpiryBehaviour.BLOCK_ACTIVE_USE_AFTER_VALUE_DATE
        ):
            continue
        if fact.expires_at >= as_of:
            continue
        yield diagnostic(
            IssueCode.FACT_VALUE_EXPIRED,
            f"{fact.fact_id} expired on {fact.expires_at.isoformat()} and {fact.predicate} blocks "
            f"active use after its value date",
            path=ctx.path_of(fact.fact_id),
            record_id=fact.fact_id,
            expires_at=fact.expires_at.isoformat(),
            as_of=as_of.isoformat(),
            predicate=str(fact.predicate),
        )


def _unresolved_conflicts_block_their_candidates(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """One finding per group, listing the facts the group blocks.

    The group is the record an owner rules on; the blocked facts are the consequence, so they travel
    as detail rather than as separate findings. The membership comes from
    `records_blocked_by_unresolved_conflicts` — the same derivation `effective_fact_ids` uses — so
    the report and the effectiveness rule can never disagree about which facts a group blocks.
    """
    blocked = records_blocked_by_unresolved_conflicts(ctx.index)
    unresolved = ctx.index.unresolved_conflict_ids
    for conflict in ctx.index.conflicts:
        if conflict.conflict_id not in unresolved:
            continue
        candidates = sorted(
            fact_id for fact_id in conflict.candidate_fact_ids if fact_id in blocked
        )
        yield diagnostic(
            IssueCode.UNRESOLVED_CONFLICT,
            f"{conflict.conflict_id} is {conflict.state} and blocks {len(candidates)} candidate "
            f"fact(s) about {conflict.subject_id} until the owner rules on it",
            path=ctx.path_of(conflict.conflict_id) or CONFLICTS_PATH,
            record_id=conflict.conflict_id,
            state=str(conflict.state),
            blocked_record_ids=candidates,
        )


# --------------------------------------------------------------------------------------
# The information summary (§20.5's fourth tier)
# --------------------------------------------------------------------------------------


def completeness_counts(ctx: ValidationContext, effective: frozenset[str]) -> Diagnostic:
    """One `information` row carrying everything §20.5 says completeness output includes.

    One row rather than one per topic because every row would carry the same code, and a consumer
    reading the JSON could not tell them apart. Counts only: the strings they were counted from are
    contact values and capture excerpts, which must never reach a report.
    """
    index = ctx.index
    ledger = index.source_ledger
    totals = import_totals(ledger, _exclusion_ledger(ctx)) if ledger is not None else None
    reviewed = sorted(metric.reviewed_at for metric in index.metrics)
    details: dict[str, JsonValue] = {
        "records": {
            "entities": len(index.entities),
            "contacts": len(index.contacts),
            "facts": len(index.facts),
            "effective_facts": len(effective),
            "skills": len(index.skills),
            "metrics": len(index.metrics),
            "claims": len(index.claims),
            "relations": len(index.relations),
            "evidence": len(index.evidence),
        },
        "facts_by_state": {
            state.value: sum(1 for f in index.facts if f.verification_state is state)
            for state in VerificationState
        },
        "entity_status_distribution": _entity_status_distribution(ctx),
        "surface_coverage": _surface_coverage(ctx, effective),
        "evidence": {
            "records": len(index.evidence),
            "owner_approved": sum(
                1
                for record in index.evidence
                if record.sufficiency_review.state is SufficiencyState.OWNER_APPROVED
            ),
            "unreviewed": sum(
                1
                for record in index.evidence
                if record.sufficiency_review.state is SufficiencyState.UNREVIEWED
            ),
            "facts_citing_evidence": sum(1 for f in index.facts if f.evidence_ids),
        },
        "metric_review": {
            "metrics": len(index.metrics),
            "eligible": sum(1 for m in index.metrics if eligible_metric(m, ctx)),
            "oldest_reviewed_at": reviewed[0].isoformat() if reviewed else None,
            "newest_reviewed_at": reviewed[-1].isoformat() if reviewed else None,
        },
        "conflicts": {
            "groups": len(index.conflicts),
            "unresolved": len(index.unresolved_conflict_ids),
            "rulings": len(index.rulings),
        },
        "source_ledger": (
            None
            if totals is None
            else {
                "denominator": totals.denominator,
                "imported": totals.imported,
                "excluded": totals.excluded,
                "review_required": totals.review_required,
                "candidates": len(index.candidates),
            }
        ),
        "exclusions_by_reason": (
            {}
            if totals is None
            else {reason.value: count for reason, count in totals.exclusions_by_reason.items()}
        ),
    }
    # Built directly rather than through `diagnostic(...)`: the whole payload is one mapping, and
    # splatting it as keyword arguments would let a future count named `path` or `tier` silently
    # become a Diagnostic field instead of a number. The tier still comes from `tier_of`.
    return Diagnostic(
        tier=tier_of(IssueCode.COMPLETENESS_COUNTS),
        code=str(IssueCode.COMPLETENESS_COUNTS),
        path=None,
        record_id=None,
        message=(
            "completeness summary: record counts, surface coverage, status distribution, "
            "evidence coverage, and import totals"
        ),
        details=details,
    )


def _exclusion_ledger(ctx: ValidationContext) -> ExclusionLedger | None:
    """`imports/exclusions.yaml`, when the tree has one.

    Read through the documents rather than the index because `import_totals` takes the ledger
    document, and `BundleIndex` deliberately flattens it to its records.
    """
    document = ctx.documents.get("imports/exclusions.yaml")
    return document if isinstance(document, ExclusionLedger) else None


def _entity_status_distribution(ctx: ValidationContext) -> Mapping[str, int]:
    """`<entity_type>.<status>` -> count. `person` contributes nothing: §9 gives it no catalog."""
    distribution: dict[str, int] = {}
    for entity in ctx.index.entities.values():
        status = getattr(entity, "status", None)
        if status is None:
            continue
        key = f"{getattr(entity, 'entity_type', 'unknown')}.{status.value}"
        distribution[key] = distribution.get(key, 0) + 1
    return dict(sorted(distribution.items()))


def _surface_coverage(ctx: ValidationContext, effective: frozenset[str]) -> Mapping[str, JsonValue]:
    """How much usable material each surface has.

    Facts are counted by their DECLARED surfaces restricted to the effective set, not by
    `eligible_fact_surfaces`. For a bundle that passes semantic validation the two are the same set
    — `PREDICATE_SURFACE_ILLEGAL` and `APPLICATION_ONLY_LEAK` are exactly the findings that make a
    declared surface an eligible one — and the declared form is linear rather than quadratic in the
    fact count.
    """
    index = ctx.index
    coverage: dict[str, JsonValue] = {}
    for surface in Surface:
        coverage[surface.value] = {
            "facts": sum(
                1 for f in index.facts if f.fact_id in effective and surface in f.allowed_surfaces
            ),
            "metrics": sum(
                1
                for m in index.metrics
                if eligible_metric(m, ctx) and surface in m.allowed_surfaces
            ),
            "skills": sum(
                1
                for s in index.skills
                if s.verification_state in EFFECTIVE_STATES and surface in s.allowed_surfaces
            ),
            "claims": sum(
                1
                for c in index.claims
                if c.status is ClaimStatus.APPROVED and surface in c.allowed_surfaces
            ),
            "contacts": sum(
                1
                for contact in index.contacts
                if contact.verification_state in EFFECTIVE_STATES
                and surface in contact.allowed_surfaces
            ),
        }
    return coverage


# --------------------------------------------------------------------------------------
# Ancestor traversal (§20.6's last clause, reported as completeness)
# --------------------------------------------------------------------------------------


class _AncestorUnverifiable(ProfileBundleError):
    """One ancestor could not be verified, with the reason typed rather than described."""

    def __init__(self, reason: AncestorFault, message: str) -> None:
        super().__init__(message)
        self.reason: AncestorFault = reason


def ancestry_completeness(
    ctx: ValidationContext, *, deep: bool = False
) -> tuple[Diagnostic, ...]:
    """Walk the parent chain through stored manifest envelopes (§20.6).

    §20.6 is explicit that "validation of an already selected revision does not deep-parse ancestors
    to repeat that promotion-time check", so the default reads each ancestor's manifest and nothing
    else. `deep=True` is the opt-in audit: it recomputes each intact ancestor's bundle digest from
    its own bytes, which is the only way an edited ancestor becomes visible at all.

    A missing or unreadable ancestor is a blocker and never an error: §21 keeps the selected
    revision structurally valid when its history is unavailable, because the alternative is that
    restoring one old directory from backup decides whether the bundle is usable at all.
    """
    if ctx.bundle_root is None:
        return ()  # nothing was handed over to look in
    return tuple(_walk_ancestors(ctx, ctx.bundle_root, deep=deep))


def _walk_ancestors(
    ctx: ValidationContext, bundle_root: Path, *, deep: bool
) -> Iterator[Diagnostic]:
    seen: set[str] = set()
    digest = ctx.manifest.parent_bundle_digest
    while digest is not None:
        if digest in seen:
            yield _ancestor_finding(digest, "cycle", "the ancestor chain revisits a revision it "
                                    "has already traversed")
            return
        seen.add(digest)
        try:
            manifest = _ancestor_manifest(bundle_root, digest, blobs_deep=deep, ctx=ctx)
        except _AncestorUnverifiable as exc:
            yield _ancestor_finding(digest, exc.reason, str(exc))
            return  # everything above an unverifiable ancestor is unreachable too
        digest = manifest.parent_bundle_digest


def _ancestor_finding(digest: str, reason: AncestorFault, message: str) -> Diagnostic:
    return diagnostic(
        IssueCode.UNVERIFIABLE_ANCESTOR,
        f"ancestor {digest} could not be verified: {message}",
        path=MANIFEST_PATH,
        ancestor_bundle_digest=digest,
        reason=reason,
    )


def _ancestor_manifest(
    bundle_root: Path, digest: str, *, blobs_deep: bool, ctx: ValidationContext
) -> RevisionManifest:
    """The stable envelope of one ancestor, or a typed refusal naming why it is unverifiable."""
    try:
        root = revision_root(bundle_root, digest)
    except BundlePathError as exc:
        raise _AncestorUnverifiable("malformed", str(exc)) from exc
    path = root / MANIFEST_PATH
    if not root.is_dir() or not path.is_file():
        raise _AncestorUnverifiable("absent", f"{root.name} is not on disk")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _AncestorUnverifiable("unreadable", str(exc)) from exc
    try:
        parsed = load_yaml_bytes(raw, logical_path=PurePosixPath(MANIFEST_PATH))
        manifest = _MANIFEST_ADAPTER.validate_python(parsed)
    except (RestrictedYamlError, ValidationError) as exc:
        raise _AncestorUnverifiable("malformed", f"its manifest does not parse: {exc}") from exc
    try:
        require_supported_schema(manifest.schema_version)
    except UnsupportedSchemaVersionError as exc:
        raise _AncestorUnverifiable("unsupported_schema", str(exc)) from exc
    if not isinstance(manifest, RevisionManifest):
        raise _AncestorUnverifiable(
            "not_a_revision", "its manifest declares state 'draft'; an ancestor is always promoted"
        )
    if manifest.bundle_digest != digest:
        raise _AncestorUnverifiable(
            "declared_digest_mismatch",
            f"the directory names {digest} but its manifest declares {manifest.bundle_digest}",
        )
    if blobs_deep:
        _audit_ancestor_bytes(root, digest, ctx)
    return manifest


def _audit_ancestor_bytes(root: Path, digest: str, ctx: ValidationContext) -> None:
    """Recompute the ancestor's digest from its own documents. Only reached with `deep=True`."""
    blobs = ctx.blobs
    if blobs is None:
        # `validation/run.py` always supplies a reader, and a test asserts it there. Recomputing a
        # digest without the blob bytes is not possible, and reporting one that was never computed
        # would be worse than declining the audit.
        return
    try:
        documents = load_documents(root, mode="revision")
        computed = bundle_digest(documents, blobs)
    except (ProfileBundleError, MissingBlobError, CanonicalizationError) as exc:
        raise _AncestorUnverifiable("malformed", f"its documents do not load: {exc}") from exc
    if computed != digest:
        raise _AncestorUnverifiable(
            "content_digest_mismatch",
            f"its documents produce {computed}, not the {digest} that names it",
        )


__all__ = [
    "AncestorFault",
    "ancestry_completeness",
    "completeness_counts",
    "validate_completeness",
]
