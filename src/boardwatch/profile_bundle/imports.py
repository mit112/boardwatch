"""Candidate identity, the immutable ledger package, and idempotent import merging (design §18).

The importer, not an LLM, assigns identity. Extraction receives the *enumerated* records and may
propose a predicate, a typed value, and a display string for any of them; anything it proposes as
an ID is accepted and discarded, because the stored ID is derived from
`source_record_id | predicate | canonicalized_typed_value`. That is what makes re-extraction free:
the same material re-read with different ordering, grouping, proposed IDs, or whitespace produces
the same IDs and therefore no new candidates.

The three-way outcome of a re-import (§18, §21) is the whole point of separating identity from
lineage:

- same record, same digests, same derived ID — an exact duplicate, recorded once;
- changed source or record digest with the same canonical value — one occurrence appended to the
  existing candidate, so the history of where a value was seen survives a source edit;
- changed canonical value — a new candidate ID, because it is a different assertion.

Nothing here reads a repository, resolves a personal path, or performs Gate B extraction: every
entry point takes bytes or a typed package that a caller supplied explicitly. Nothing here mutates
accepted facts, evidence, conflicts, rulings, or history — those documents are not even imported.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from typing import Any, Final

from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.canonical import canonical_json_bytes
from boardwatch.profile_bundle.enumerators import (
    SOURCE_KIND_ADAPTERS,
    EnumeratedSourceRecord,
    enumerator_for,
    source_content_digest,
)
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.models.base import CandidateId
from boardwatch.profile_bundle.models.facts import (
    FactValue,
    FactValueKind,
    StringListValue,
    StringValue,
)
from boardwatch.profile_bundle.models.imports import (
    ApprovedScope,
    CandidatePackage,
    CandidateRecord,
    Disposition,
    ExclusionRecord,
    SourceLedger,
    SourceLedgerSource,
)
from boardwatch.profile_bundle.models.policy import (
    ExclusivitySpec,
    PredicateCatalog,
    PredicateSpec,
    SourceSpec,
)

_VALUE_ADAPTER: Final[TypeAdapter[FactValue]] = TypeAdapter(FactValue)


class CandidateImportError(ProfileBundleError):
    """An import cannot proceed: a refused scope, an uncanonicalisable value, a forged ID.

    Raised rather than reported, for the same reason enumeration raises: a half-built candidate
    package would be counted against the Gate B denominator while describing less than it claims.
    """


# --------------------------------------------------------------------------------------
# The immutable ledger package (§18)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EnumeratedSource:
    """One deterministically enumerated source, exactly as candidate extraction receives it.

    Frozen on purpose. §18 hands extraction "the immutable enumerated ledger package rather than
    raw authority to redefine source boundaries"; a mutable package would make that a convention.
    """

    source_id: str
    enumerator_id: str
    enumerator_version: int
    source_content_digest: str
    approved_scope: ApprovedScope
    records: tuple[EnumeratedSourceRecord, ...]

    @property
    def ledger_source(self) -> SourceLedgerSource:
        """This source's `imports/source-ledger.yaml` row, in the adapter's canonical order."""
        return SourceLedgerSource.model_validate(
            {
                "source_id": self.source_id,
                "enumerator_id": self.enumerator_id,
                "enumerator_version": self.enumerator_version,
                "source_content_digest": self.source_content_digest,
                "approved_scope": self.approved_scope.model_dump(mode="json"),
                "source_record_ids": [record.source_record_id for record in self.records],
            }
        )


def enumerate_source(
    spec: SourceSpec, source: bytes, *, scope: ApprovedScope
) -> EnumeratedSource:
    """Enumerate one owner-approved source from bytes the caller already holds.

    Takes bytes rather than a path: the generalized importer must not fetch a user's repositories
    or follow a machine-local personal path (§18), and a function that cannot open a file cannot
    be talked into opening the wrong one.
    """
    binding = SOURCE_KIND_ADAPTERS[spec.source_kind]
    if scope.kind != binding.scope_kind:
        raise CandidateImportError(
            f"{spec.source_id}: source kind {spec.source_kind.value} is approved with a "
            f"{binding.scope_kind} scope, not {scope.kind}"
        )
    adapter = enumerator_for(spec.source_kind, source_id=spec.source_id)
    return EnumeratedSource(
        source_id=spec.source_id,
        enumerator_id=binding.enumerator_id,
        enumerator_version=binding.enumerator_version,
        source_content_digest=source_content_digest(source),
        approved_scope=scope,
        records=adapter.enumerate(source, scope=scope),
    )


# --------------------------------------------------------------------------------------
# Value canonicalization (§18)
# --------------------------------------------------------------------------------------


def _collapsed(text: str) -> str:
    """NFC, every Unicode whitespace run collapsed to one space, ends trimmed.

    `str.split()` splits on Unicode whitespace and discards empty pieces, so the collapse and the
    trim are one operation and a non-breaking space cannot survive as a second spelling of a space.
    """
    return " ".join(unicodedata.normalize("NFC", text).split())


def canonicalize_candidate_value(value: FactValue, predicate: PredicateSpec) -> FactValue:
    """The canonical form of a proposed value, under the authority its predicate declares.

    Only the predicate's contract authorizes a transformation. Case is never folded: §18 permits
    casefolding "only when the predicate contract declares case-insensitive identity", and no
    field of `PredicateSpec` declares it, so folding would be this module inventing an authority
    the catalog cannot express — and it would silently merge two genuinely different titles.
    """
    kind = FactValueKind(value.type)
    if kind not in predicate.legal_value_types:
        raise CandidateImportError(
            f"{predicate.predicate_id}: value type {kind.value!r} is not legal for this predicate"
        )

    payload: dict[str, Any] = value.model_dump(mode="json")
    if isinstance(value, StringValue):
        payload["value"] = _collapsed(value.value)
        if predicate.legal_string_values and payload["value"] not in predicate.legal_string_values:
            raise CandidateImportError(
                f"{predicate.predicate_id}: value is outside the predicate's enumerated values"
            )
    elif isinstance(value, StringListValue):
        collapsed = [_collapsed(item) for item in value.values]
        # A set-like list has no meaningful order, so sorting it makes two spellings of one set
        # produce one candidate ID. An ordered list keeps its order: reordering it would be a
        # different assertion, and §18 says so explicitly.
        payload["values"] = (
            sorted(collapsed)
            if predicate.exclusivity is ExclusivitySpec.ONE_EFFECTIVE_SET
            else collapsed
        )

    try:
        return _VALUE_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise CandidateImportError(
            f"{predicate.predicate_id}: the canonicalized value is not a valid typed value "
            f"({exc.error_count()} field error(s))"
        ) from exc


def derive_candidate_id(
    source_record_id: str, predicate: str, value: FactValue
) -> CandidateId:
    """`candidate.<64hex>` over the canonical JSON of
    `["candidate", source_record_id, predicate, canonicalized_typed_value]`."""
    payload = ["candidate", source_record_id, predicate, value.model_dump(mode="json")]
    return "candidate." + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


# --------------------------------------------------------------------------------------
# Building a candidate package
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProposedCandidate:
    """One assertion extraction proposes about one already-enumerated source record.

    It carries no locator and no authority over boundaries: the only way to reach the denominator
    is to name a `source_record_id` an adapter already produced. `proposed_candidate_id` exists so
    an LLM's output can be handed over verbatim; it is never read.
    """

    source_record_id: str
    predicate: str
    value: FactValue
    original_display_value: str
    proposed_candidate_id: str | None = None


def build_candidate_package(
    sources: Sequence[EnumeratedSource],
    proposals: Sequence[ProposedCandidate],
    *,
    predicates: PredicateCatalog,
    candidates_version: int = 1,
) -> CandidatePackage:
    """Turn proposals into typed candidates whose IDs this function derives."""
    lineage: dict[str, tuple[EnumeratedSourceRecord, str]] = {
        record.source_record_id: (record, source.source_content_digest)
        for source in sources
        for record in source.records
    }
    catalog = predicates.by_id
    built: dict[str, dict[str, Any]] = {}

    for proposal in proposals:
        entry = lineage.get(proposal.source_record_id)
        if entry is None:
            raise CandidateImportError(
                f"{proposal.source_record_id} is not a record of any enumerated source; "
                "extraction cannot create denominator units"
            )
        spec = catalog.get(proposal.predicate)
        if spec is None:
            raise CandidateImportError(f"unknown predicate {proposal.predicate!r}")

        canonical = canonicalize_candidate_value(proposal.value, spec)
        candidate_id = derive_candidate_id(
            proposal.source_record_id, proposal.predicate, canonical
        )
        record, digest = entry
        occurrence = {
            "source_content_digest": digest,
            "record_content_digest": record.record_content_digest,
        }
        existing = built.get(candidate_id)
        if existing is None:
            built[candidate_id] = {
                "candidate_id": candidate_id,
                "source_record_id": proposal.source_record_id,
                "predicate": proposal.predicate,
                "canonicalized_typed_value": canonical.model_dump(mode="json"),
                "original_display_value": proposal.original_display_value,
                "occurrences": [occurrence],
            }
        elif occurrence not in existing["occurrences"]:
            existing["occurrences"].append(occurrence)

    return _package(built, candidates_version)


def _package(built: Mapping[str, dict[str, Any]], candidates_version: int) -> CandidatePackage:
    """Sorted by candidate ID, so the result does not depend on extraction order or grouping."""
    try:
        return CandidatePackage.model_validate(
            {
                "candidates_version": candidates_version,
                "candidates": [built[key] for key in sorted(built)],
            }
        )
    except ValidationError as exc:
        raise CandidateImportError(
            f"the candidate package is not valid ({exc.error_count()} field error(s))"
        ) from exc


# --------------------------------------------------------------------------------------
# Merging (§18, §21)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportMergeResult:
    """The merged package and which candidates each of §18's three outcomes applied to."""

    package: CandidatePackage
    added: tuple[str, ...]
    appended_occurrences: tuple[str, ...]
    unchanged: tuple[str, ...]


def uncanonical_value(value: FactValue) -> str | None:
    """Why `value` is not in canonical form, or `None` if it is.

    Only the predicate-independent half — NFC, collapsed whitespace, trimmed ends. Casefolding and
    set-like ordering need the predicate contract and are checked where the catalog is in hand.

    This exists because a self-consistent hash proves nothing about canonicality: an uncollapsed
    string hashes perfectly well against its own ID, and the resulting candidate is a second
    identity for an assertion that already has one — which is exactly the idempotence §18 promises.
    """
    if isinstance(value, StringValue) and _collapsed(value.value) != value.value:
        return "string value is not NFC-normalised with collapsed, trimmed whitespace"
    if isinstance(value, StringListValue) and any(
        _collapsed(item) != item for item in value.values
    ):
        return "a list element is not NFC-normalised with collapsed, trimmed whitespace"
    return None


def _require_derived(
    candidate: CandidateRecord, where: str, predicates: PredicateCatalog
) -> None:
    """Every reason a stored candidate could not have come from the importer.

    The catalog is required rather than optional because canonicality is predicate-dependent: a
    set-like list stored out of order has every element collapsed and trimmed, so only
    `application.authorized_regions`'s own contract knows it is wrong. Without the catalog this
    function could check that an ID hashes the payload beside it and nothing more, which is exactly
    what a forger supplies.
    """
    spec = predicates.by_id.get(candidate.predicate)
    if spec is None:
        raise CandidateImportError(
            f"{where}: {candidate.candidate_id} asserts unknown predicate "
            f"{candidate.predicate!r}"
        )
    violation = uncanonical_value(candidate.canonicalized_typed_value)
    if violation is not None:
        raise CandidateImportError(f"{where}: {candidate.candidate_id}: {violation}")
    if canonicalize_candidate_value(candidate.canonicalized_typed_value, spec) != (
        candidate.canonicalized_typed_value
    ):
        raise CandidateImportError(
            f"{where}: {candidate.candidate_id}: stored value is not the canonical form "
            f"{candidate.predicate!r} authorizes"
        )
    derived = derive_candidate_id(
        candidate.source_record_id, candidate.predicate, candidate.canonicalized_typed_value
    )
    if derived != candidate.candidate_id:
        raise CandidateImportError(
            f"{where}: {candidate.candidate_id} is not the ID its record, predicate, and value "
            "derive; the importer assigns identity, not its caller"
        )


def merge_candidate_package(
    existing: CandidatePackage, incoming: CandidatePackage, *, predicates: PredicateCatalog
) -> ImportMergeResult:
    """Merge `incoming` into `existing` without overwriting anything already recorded."""
    if existing.candidates_version != incoming.candidates_version:
        raise CandidateImportError(
            f"cannot merge candidates_version {incoming.candidates_version} into "
            f"{existing.candidates_version}"
        )

    merged: dict[str, dict[str, Any]] = {}
    for candidate in existing.candidates:
        _require_derived(candidate, "existing package", predicates)
        merged[candidate.candidate_id] = candidate.model_dump(mode="json")

    added: list[str] = []
    appended: list[str] = []
    unchanged: list[str] = []

    for candidate in incoming.candidates:
        _require_derived(candidate, "incoming package", predicates)
        payload = candidate.model_dump(mode="json")
        current = merged.get(candidate.candidate_id)
        if current is None:
            merged[candidate.candidate_id] = payload
            added.append(candidate.candidate_id)
            continue
        # The display value is deliberately not replaced: §18 preserves the original display value
        # beside the canonical one, and a later sighting is a second spelling, not a correction.
        seen = {
            (item["source_content_digest"], item["record_content_digest"])
            for item in current["occurrences"]
        }
        fresh = [
            item
            for item in payload["occurrences"]
            if (item["source_content_digest"], item["record_content_digest"]) not in seen
        ]
        if fresh:
            current["occurrences"].extend(fresh)
            appended.append(candidate.candidate_id)
        else:
            unchanged.append(candidate.candidate_id)

    return ImportMergeResult(
        package=_package(merged, existing.candidates_version),
        added=tuple(sorted(added)),
        appended_occurrences=tuple(sorted(appended)),
        unchanged=tuple(sorted(unchanged)),
    )


# --------------------------------------------------------------------------------------
# Authoritative per-source rebuild (§6.6)
# --------------------------------------------------------------------------------------


def rebuild_source_candidates(
    existing: CandidatePackage,
    fresh: CandidatePackage,
    *,
    source_record_ids: Set[str],
) -> CandidatePackage:
    """Replace one source's candidates with a fresh extraction, authoritatively (§6.6).

    `merge_candidate_package` is append-only, so a re-extraction that produced a *different*
    candidate ID — corrected material yields a new identity — would leave the superseded candidate
    behind and let a record name both. Extraction is authoritative per source instead: every
    candidate whose `source_record_id` is one of this source's records is dropped and rebuilt from
    `fresh`, while every other source's candidate is carried over untouched.

    `source_record_ids` is this source's record IDs — both those the fresh enumeration produced and
    any the old ledger still carried, so a record that vanished from the source takes its stale
    candidates with it. Occurrence lineage is preserved only for a candidate ID that *survives* the
    rebuild: a re-extraction seeing the same assertion appends nothing, but a superseded assertion's
    occurrences are not retained, which is exactly what "the same assertion seen again" means.
    """
    if existing.candidates_version != fresh.candidates_version:
        raise CandidateImportError(
            f"cannot rebuild candidates_version {fresh.candidates_version} into "
            f"{existing.candidates_version}"
        )

    prior_this_source = {
        candidate.candidate_id: candidate.model_dump(mode="json")
        for candidate in existing.candidates
        if candidate.source_record_id in source_record_ids
    }
    built: dict[str, dict[str, Any]] = {
        candidate.candidate_id: candidate.model_dump(mode="json")
        for candidate in existing.candidates
        if candidate.source_record_id not in source_record_ids
    }
    for candidate in fresh.candidates:
        payload = candidate.model_dump(mode="json")
        prior = prior_this_source.get(candidate.candidate_id)
        if prior is not None:
            seen = {
                (item["source_content_digest"], item["record_content_digest"])
                for item in prior["occurrences"]
            }
            merged = list(prior["occurrences"])
            for item in payload["occurrences"]:
                if (item["source_content_digest"], item["record_content_digest"]) not in seen:
                    merged.append(item)
            payload["occurrences"] = merged
        built[candidate.candidate_id] = payload

    return _package(built, existing.candidates_version)


# --------------------------------------------------------------------------------------
# The ledger (§18)
# --------------------------------------------------------------------------------------


def build_source_ledger(
    sources: Sequence[EnumeratedSource],
    package: CandidatePackage,
    *,
    exclusions: Mapping[str, ExclusionRecord],
    ledger_version: int = 1,
) -> SourceLedger:
    """Assemble `imports/source-ledger.yaml` from enumerated sources and their candidates.

    Disposition is derived, never authored: a record with candidates is `imported`, a record the
    owner excluded is `excluded`, and everything left is `review_required` — the undispositioned
    Gate B blocker. There is no fourth branch, which is what makes the three counts sum to the
    denominator by construction rather than by a check.
    """
    by_record: dict[str, list[str]] = {}
    for candidate in package.candidates:
        by_record.setdefault(candidate.source_record_id, []).append(candidate.candidate_id)

    records: list[dict[str, Any]] = []
    for source in sources:
        for record in source.records:
            candidate_ids = sorted(by_record.get(record.source_record_id, ()))
            if candidate_ids:
                disposition = Disposition.IMPORTED
            elif record.source_record_id in exclusions:
                disposition = Disposition.EXCLUDED
            else:
                disposition = Disposition.REVIEW_REQUIRED
            records.append(
                {
                    "source_record_id": record.source_record_id,
                    "source_id": record.source_id,
                    "normalized_locator": record.normalized_locator,
                    "disposition": disposition.value,
                    "candidate_ids": candidate_ids,
                }
            )

    try:
        return SourceLedger.model_validate(
            {
                "ledger_version": ledger_version,
                "sources": [source.ledger_source.model_dump(mode="json") for source in sources],
                "records": records,
            }
        )
    except ValidationError as exc:
        raise CandidateImportError(
            f"the assembled source ledger is not valid ({exc.error_count()} field error(s))"
        ) from exc
