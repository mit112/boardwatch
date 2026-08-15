"""The owner-initiated writes that are not promotion (design §12, §13, §19).

Capture an evidence record, rule on a conflict, enumerate a source into the import ledger, and file
the owner's approval of a candidate. They live here rather than in the command layer because the
command layer is a translation: everything below decides what happens to the bundle, and nothing
here imports `typer`, reads a clock, or prints.

That boundary is not a preference. `test_profile_bundle_hash_isolation` makes the bundle's
canonical serializer one-directional — nothing outside this package may reference it — because it
is a private serializer whose bytes are identity, and a second caller elsewhere is how a shared
hash quietly acquires a second meaning. The candidate digest an approval binds is computed with
that serializer, so the whole approval flow except the terminal question belongs here.

## A refusal writes nothing

Every check runs before the first byte is written, and the writes themselves are staged and
renamed. That matters more here than anywhere else in the package, because the operator's response
to a refusal is to fix their input and run the command again — and a half-applied first attempt
would make the second one refuse for a different reason, about a state they never authored.

The blob store is the one place a refusal can leave something behind, and it is not an exception to
the rule: `add_evidence` writes the blob after every check has passed but before the evidence
document, so only an I/O failure between the two can strand it. §7 retains unreferenced blobs and
§21 forbids deleting them, so that residue is the designed outcome rather than a leak — `inventory`
reports it, and the same capture re-offered lands on the same digest and is reused.

## Owner gates are derived, not asserted

What a change makes owner-gated is computed by `required_approval_decisions` against the draft as
it was a moment ago. Stating "a new ruling needs `authorize_conflict_ruling`" a second time here
would be a rule that could drift from the one `validate_history` enforces at promotion; asking the
same function is what keeps them one rule.

## Refusals travel as an exception, and never leave this module

Each step either produces its value or raises `_Refused`. The alternative — returning a union of a
value and an outcome at every step — made every caller re-narrow the same two cases, and the one
that forgot would have carried on with a refusal in hand. The exception is typed and carries
diagnostics, so nothing here classifies a failure by reading a message.
"""

from __future__ import annotations

import os
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from boardwatch.profile_bundle.approvals import (
    ApprovalDecision,
    approval_stamp_bytes,
    build_approval_stamp,
    required_approval_decisions,
)
from boardwatch.profile_bundle.blobs import (
    MAX_CAPTURE_BYTES,
    BlobDigestMismatchError,
    quarantined_blobs,
    write_blob,
)
from boardwatch.profile_bundle.candidate_promotion import (
    PromotionError,
    build_promotion,
)
from boardwatch.profile_bundle.canonical import (
    EVIDENCE_PATH,
    MANIFEST_PATH,
    FilesystemBlobReader,
    MissingBlobError,
    candidate_content_digest,
    evidence_set_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.enumerators import (
    SOURCE_KIND_ADAPTERS,
    EnumerationError,
)
from boardwatch.profile_bundle.errors import (
    BundleIoError,
    BundlePathError,
    Diagnostic,
    IssueCode,
    OperationOutcome,
    ProfileBundleError,
    RestrictedYamlError,
    diagnostic,
    io_reason,
    outcome_with,
)
from boardwatch.profile_bundle.extraction import (
    ExtractionFailure,
    ExtractionMapping,
    ExtractionMappingError,
    run_extraction,
    validate_mapping_against_catalog,
)
from boardwatch.profile_bundle.extraction_mapping import mappings_from_document
from boardwatch.profile_bundle.imports import (
    CandidateImportError,
    EnumeratedSource,
    ProposedCandidate,
    build_candidate_package,
    build_source_ledger,
    enumerate_source,
    rebuild_source_candidates,
)
from boardwatch.profile_bundle.index import record_id_of
from boardwatch.profile_bundle.models.base import (
    EFFECTIVE_STATES,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    DocumentModel,
    EmploymentFactsDocument,
    EvidenceRecordsDocument,
    FactBearingDocument,
    MetricRecordsDocument,
    ProjectFactsDocument,
    SkillInventoryDocument,
)
from boardwatch.profile_bundle.models.evidence import AnyEvidence, EvidenceRecord
from boardwatch.profile_bundle.models.facts import FactRecord
from boardwatch.profile_bundle.models.history import (
    ConflictGroups,
    ConflictRecord,
    ConflictRulings,
    ConflictState,
    RulingDecision,
    RulingRecord,
)
from boardwatch.profile_bundle.models.imports import (
    ApprovedScope,
    CandidatePackage,
    CompleteFileScope,
    Disposition,
    ExclusionLedger,
    ExclusionRecord,
    ExtractionReport,
    ExtractionReportReason,
    SourceLedger,
)
from boardwatch.profile_bundle.models.manifests import (
    BundleManifest,
    DraftManifest,
    RevisionManifest,
    StableManifestEnvelope,
)
from boardwatch.profile_bundle.models.policy import (
    ExtractionMappingsDocument,
    PredicateCatalog,
    SkillCategoryCatalog,
    SourceCatalog,
    SourceSpec,
)
from boardwatch.profile_bundle.models.sidecars import LocalSourcesSidecar
from boardwatch.profile_bundle.paths import (
    LOCAL_SOURCES_FILE,
    approval_path,
    approvals_dir,
    blobs_dir,
    draft_root,
    local_sources_path,
)
from boardwatch.profile_bundle.secret_scan import (
    CURRENT_RULESET_VERSION,
    InvalidUtf8CaptureError,
    scan_capture,
)
from boardwatch.profile_bundle.storage import (
    SelectedRevision,
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation import load_documents, parse_error_diagnostics
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes

CONFLICT_GROUPS_PATH: Final = PurePosixPath("conflicts/groups.yaml")
CONFLICT_RULINGS_PATH: Final = PurePosixPath("conflicts/rulings.yaml")
SOURCE_LEDGER_PATH: Final = PurePosixPath("imports/source-ledger.yaml")
IMPORT_CANDIDATES_PATH: Final = PurePosixPath("imports/candidates.yaml")
IMPORT_EXCLUSIONS_PATH: Final = PurePosixPath("imports/exclusions.yaml")
EXTRACTION_REPORT_PATH: Final = PurePosixPath("imports/extraction-report.yaml")
EXTRACTION_MAPPINGS_PATH: Final = PurePosixPath("policy/extraction-mappings.yaml")
PREDICATE_CATALOG_PATH: Final = PurePosixPath("policy/predicates.yaml")
SOURCE_CATALOG_PATH: Final = PurePosixPath("policy/sources.yaml")
SKILL_INVENTORY_PATH: Final = PurePosixPath("skills/inventory.yaml")
SKILL_CATEGORIES_PATH: Final = PurePosixPath("policy/skill-categories.yaml")

#: The names the operator's input files are reported under. They are not bundle documents, so they
#: have no path inside the tree — and naming the operator's own filesystem path in a diagnostic
#: would put an absolute path into JSON they may paste elsewhere.
EVIDENCE_INPUT: Final = PurePosixPath("--evidence-file")
RULING_INPUT: Final = PurePosixPath("--ruling-file")
SOURCE_INPUT: Final = PurePosixPath("--from")

_EVIDENCE_ADAPTER: Final[TypeAdapter[AnyEvidence]] = TypeAdapter(EvidenceRecord)
_RULING_ADAPTER: Final[TypeAdapter[RulingRecord]] = TypeAdapter(RulingRecord)

#: Read back by `inspection._authoring_residue`, which is what gives the residue a drain.
AUTHORING_TEMP_PREFIX: Final = ".tmp-authoring-"

#: How an owner's decision leaves the group it rules on. `not_applicable` settles the group for the
#: same reason `select_candidate` does — the owner has stated there is nothing left to decide — and
#: `ConflictState` has no fourth member to represent "decided to be a non-conflict" separately.
#: `keep_unresolved` is the one decision that leaves the group open, which is the whole point of it.
#: `reopened` is never reached from here: it is what *new evidence* does to a settled group, not
#: what a ruling does, so a mapping onto it could not fire.
_STATE_AFTER: Final[Mapping[RulingDecision, ConflictState]] = {
    RulingDecision.SELECT_CANDIDATE: ConflictState.RESOLVED,
    RulingDecision.REPLACE_ALL: ConflictState.RESOLVED,
    RulingDecision.NOT_APPLICABLE: ConflictState.RESOLVED,
    RulingDecision.KEEP_UNRESOLVED: ConflictState.UNRESOLVED,
}

_T = TypeVar("_T")


class _Refused(Exception):  # noqa: N818 - a control-flow signal, not an error condition
    """One step refused, and carries the diagnostics that say why."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__(diagnostics[0].message if diagnostics else "refused")
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class EvidenceAddition:
    """What `add-evidence` did, in the terms the operator asked in."""

    draft_name: str
    evidence_id: str
    capture_kind: Literal["inline", "blob"]
    #: The bare digest of the stored capture, and `None` for an inline one — which has no blob leaf
    #: at all (§7 step 2), rather than a blob of zero length.
    blob_digest: str | None
    blob_outcome: Literal["written", "reused"] | None
    owner_gates: tuple[ApprovalDecision, ...]
    #: The fact and metric documents this capture cited itself back from (D-143), sorted. Reported
    #: because the operator asked to add one evidence record and this may rewrite up to thirteen
    #: other documents; `owner_gates` does not cover them, since a fact that is not
    #: `owner_confirmed` is rewritten without incurring a gate. An edit nothing names is one nobody
    #: can review.
    cited_back: tuple[str, ...]


@dataclass(frozen=True)
class SourceImport:
    """What `import` did, in the terms Gate B counts in."""

    draft_name: str
    source_id: str
    enumerator_id: str
    source_content_digest: str
    #: Records this source contributes — its share of the denominator, not the whole of it.
    record_count: int
    #: This source's records by disposition. Every member of `Disposition` is present, including
    #: the zeroes: a count that disappears when it is zero is one nobody can see go wrong, which is
    #: the same reason the eligibility engine never folds `ABSTAIN` into a neighbour.
    counts: Mapping[str, int]
    #: The whole ledger's record count after the import — the Gate B denominator.
    denominator: int
    #: Whether the ledger's content actually moved. A re-import of an unchanged source writes
    #: nothing, so the operator can tell "already current" from "just updated".
    changed: bool


@dataclass(frozen=True)
class SourceExtraction:
    """What `extract` did for one source, in the terms Gate B counts in."""

    draft_name: str
    source_id: str
    enumerator_id: str
    source_content_digest: str
    #: Records this source contributes — its share of the denominator, not the whole of it.
    record_count: int
    #: This source's records by disposition after the rebuild, every member of `Disposition`
    #: present including the zeroes (the same reason `SourceImport.counts` keeps them).
    counts: Mapping[str, int]
    #: The whole ledger's record count after the extraction — the Gate B denominator.
    denominator: int
    #: This source's `review_required` records by the closed drain reason the report attaches
    #: (§6.3a). Sums to this source's `review_required` count; empty when every record resolved.
    report_reasons: Mapping[str, int]
    #: Whether any of the three documents actually moved. A re-extraction of an unchanged source
    #: writes nothing, so the operator can tell "already current" from "just rebuilt".
    changed: bool


@dataclass(frozen=True)
class CandidatePromotion:
    """What `promote-candidates` did for one source (§6.8)."""

    draft_name: str
    source_id: str
    #: Entities created (one per promoted résumé entry).
    entity_count: int
    #: Facts across those entities — metadata, bullet, and the tech_tags-grounded technology use.
    fact_count: int
    #: `SkillRecord`s created — one per skill a bullet's tech_tags grounded to an entity.
    skill_count: int
    #: Categories added to `policy/skill-categories.yaml` (derived from skill-group labels).
    category_count: int
    #: Whether anything was written. A promotion that produced no documents wrote nothing.
    changed: bool


@dataclass(frozen=True)
class ConflictResolution:
    """What `resolve-conflict` did."""

    draft_name: str
    ruling_id: str
    conflict_id: str
    conflict_state: ConflictState
    owner_gates: tuple[ApprovalDecision, ...]


@dataclass(frozen=True)
class FactEdit:
    """What `edit-fact` did: one correction, filed as an edge rather than a mutation."""

    draft_name: str
    #: The record the operator named. Still on disk, still carrying its original value, now
    #: `superseded` — reported so a caller can show what the correction replaced.
    fact_id: str
    successor_fact_id: str
    #: Where both records live, so the operator can read the result back.
    document: str
    owner_gates: tuple[ApprovalDecision, ...]


@dataclass(frozen=True)
class FactAddition:
    """What `add-fact` did."""

    draft_name: str
    fact_id: str
    document: str
    owner_gates: tuple[ApprovalDecision, ...]


def add_evidence(
    bundle_root: Path,
    *,
    draft_name: str,
    evidence_document: bytes,
    capture: bytes,
) -> OperationOutcome[EvidenceAddition]:
    """Capture one evidence record into `drafts/<name>/evidence/records.yaml` (§12, §19).

    `capture` is the bytes the record describes, always — for a blob capture they are what gets
    stored under its digest, and for an inline one they are what the record must already quote. The
    parameter is not optional for the inline case because the secret scan has to run over real
    bytes: scanning the text a record claims, without ever seeing the file it came from, would
    approve a redaction nobody performed.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        record = _parse(evidence_document, _EVIDENCE_ADAPTER, logical_path=EVIDENCE_INPUT)
        _within_capture_limit(capture, record)
        _scan(capture, record)
        documents = _load(tree)
        existing = _evidence_document(documents)
        _unused_evidence_id(existing, record)
        blob_digest, blob_outcome = _capture_bytes(bundle_root, record, capture)
        appended = EvidenceRecordsDocument.model_validate(
            {
                "evidence": [
                    *(item.model_dump(mode="json") for item in existing.evidence),
                    record.model_dump(mode="json"),
                ]
            }
        )
        citing_back = _documents_citing_back(documents, record)
        restated = _manifest_restating_the_evidence_set(bundle_root, documents, appended)
        # Evidence, then the manifest that describes it, then the records that cite it.
        #
        # The evidence record goes first for the reason `resolve_conflict` writes its ruling first:
        # the pointer target before the pointer, so no intermediate state holds a fact citing an
        # evidence ID no document has.
        #
        # The manifest goes SECOND rather than last, which is the part that is easy to get wrong.
        # `evidence_set_digest` describes the evidence document alone, so it is stale from the
        # moment the first rename lands. Left until the end it gives every citing document its own
        # failure position reporting `evidence_set_digest_mismatch` — the code §21 reserves for
        # evidence mutated after promotion, which no command repairs — on top of the citation that
        # did not land. Written second, each remaining position carries exactly one error class,
        # `evidence_link_asymmetry`, which is the state this used to leave on every capture and
        # which an ordinary draft edit repairs.
        _write_documents(tree, {EVIDENCE_PATH: appended, MANIFEST_PATH: restated, **citing_back})
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    return OperationOutcome.clean(
        EvidenceAddition(
            draft_name=draft_name,
            evidence_id=record.evidence_id,
            capture_kind=record.capture.kind,
            blob_digest=blob_digest,
            blob_outcome=blob_outcome,
            owner_gates=_gates(documents, {EVIDENCE_PATH: appended, **citing_back}),
            cited_back=tuple(sorted(path.as_posix() for path in citing_back)),
        )
    )


def resolve_conflict(
    bundle_root: Path,
    *,
    draft_name: str,
    ruling_document: bytes,
) -> OperationOutcome[ConflictResolution]:
    """Append one owner ruling and update only the group it rules on (§13, §19).

    Nothing is deleted: prior rulings stay, every candidate stays, and the group keeps its history.
    A later ruling on the same group is how a reopened conflict is settled again.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        ruling = _parse(ruling_document, _RULING_ADAPTER, logical_path=RULING_INPUT)
        documents = _load(tree)
        rulings, groups = _conflict_documents(documents)
        _unused_ruling_id(rulings, ruling)
        target = _ruled_group(groups, ruling)

        state = _STATE_AFTER[ruling.decision]
        updated = ConflictRecord.model_validate(
            {
                **target.model_dump(mode="json"),
                "state": state.value,
                "active_ruling_id": ruling.ruling_id,
            }
        )
        new_groups = ConflictGroups.model_validate(
            {
                "conflicts": [
                    (updated if group.conflict_id == target.conflict_id else group).model_dump(
                        mode="json"
                    )
                    for group in groups.conflicts
                ]
            }
        )
        new_rulings = ConflictRulings.model_validate(
            {
                "rulings": [
                    *(item.model_dump(mode="json") for item in rulings.rulings),
                    ruling.model_dump(mode="json"),
                ]
            }
        )
        # The ruling first: a ledger entry no group names yet is a decision waiting to be applied,
        # which the next validation reports plainly. A group naming a ruling the ledger does not
        # hold is a broken reference to a decision nobody can read.
        _write_documents(
            tree, {CONFLICT_RULINGS_PATH: new_rulings, CONFLICT_GROUPS_PATH: new_groups}
        )
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    return OperationOutcome.clean(
        ConflictResolution(
            draft_name=draft_name,
            ruling_id=ruling.ruling_id,
            conflict_id=ruling.conflict_id,
            conflict_state=state,
            owner_gates=_gates(
                documents,
                {CONFLICT_RULINGS_PATH: new_rulings, CONFLICT_GROUPS_PATH: new_groups},
            ),
        )
    )


def edit_fact(
    bundle_root: Path,
    *,
    draft_name: str,
    fact_id: str,
    value: str,
    as_of: date,
) -> OperationOutcome[FactEdit]:
    """Correct one fact's wording by filing a successor that supersedes it (§10.2, §19).

    The alternative — rewriting the value in place — is what `FactRecord` was designed against:
    "`supersedes_fact_ids` is an edge, not a mutation: a corrected fact gets a NEW `fact_id` and the
    superseded record stays immutable, so history is derivable rather than overwritten."

    Three documents move together, which is the whole reason this is a command rather than an
    instruction to edit YAML. The successor cites the evidence its parent cited, so
    `evidence/records.yaml` has to name it back or §12's two directions disagree; and the evidence
    document changing makes the manifest's `evidence_set_digest` a statement about content that
    moved. An owner doing this by hand writes the first and forgets the other two.

    **The successor claims no import lineage.** The parent's `source_content_digest` asserts a match
    against source bytes that no longer contain this text, and nothing recomputes it — so carrying
    it forward would be a provenance claim no layer checks and no command repairs. What supports an
    owner's wording is the owner's attestation, which is why a basis the owner cannot attest is
    refused rather than inherited.

    **The successor joins no conflict group.** A group lists its candidates by ID, and a record it
    does not name reports `conflict_candidate_mismatch`; adding one is a ruling, which
    `resolve_conflict` owns. The parent stays a candidate, now superseded — which is what "this
    candidate was corrected" means.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        documents = _load(tree)
        path, document, position, original = _fact_position(documents, fact_id)
        _correctable(original)

        payload = document.model_dump(mode="json")
        rows = payload["facts"]
        parent = dict(rows[position])
        successor_id = _successor_fact_id(fact_id, documents)
        # The parent row is captured above, so flipping its state cannot reach the successor built
        # from it — which would file a correction that is already superseded by nothing.
        rows[position] = {**parent, "verification_state": VerificationState.SUPERSEDED.value}
        rows.insert(
            position + 1,
            {
                **parent,
                "fact_id": successor_id,
                "value": {"type": "string", "value": value},
                "supersedes_fact_ids": [fact_id],
                "conflict_group_id": None,
                "import_lineage": None,
                "reviewed_at": as_of.isoformat(),
            },
        )
        rewritten = _revalidated(type(document), payload, path)

        evidence = _evidence_naming(documents, original.evidence_ids, successor_id)
        restated = _manifest_restating_the_evidence_set(bundle_root, documents, evidence)
        changed = {EVIDENCE_PATH: evidence, MANIFEST_PATH: restated, path: rewritten}
        # Evidence, the manifest that describes it, then the record that cites it — `add_evidence`'s
        # order and for its reason. The two evidence-shaped documents land together, so a rename
        # that fails after them leaves exactly one error class, `evidence_link_asymmetry`, which an
        # ordinary draft edit repairs; leaving the manifest last would add
        # `evidence_set_digest_mismatch`, which §21 reserves for evidence mutated after promotion
        # and no command repairs.
        _write_documents(tree, changed)
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    return OperationOutcome.clean(
        FactEdit(
            draft_name=draft_name,
            fact_id=fact_id,
            successor_fact_id=successor_id,
            document=path.as_posix(),
            owner_gates=_gates(documents, changed),
        )
    )


def add_fact(
    bundle_root: Path,
    *,
    draft_name: str,
    fact_id: str,
    subject_id: str,
    predicate: str,
    value: str,
    evidence_id: str,
    verification_state: str,
    verification_basis: str,
    usage_context: str,
    surfaces: Sequence[str],
    as_of: date,
) -> OperationOutcome[FactAddition]:
    """Write one new fact into the document that owns its subject (§10.1, §19).

    The same three-document write `edit_fact` performs, without the supersession: a new record, the
    evidence naming it back, and the manifest restating the evidence set.

    **`verification_state` and `verification_basis` are required and never defaulted.** They are the
    two fields that say how strongly the bundle believes this fact, and a default would make the
    command assert `owner_confirmed` on the owner's behalf every time a caller omitted it — the
    failure mode where a shared writer's defaulted status quietly reports success for paths that
    never earned it. A caller that cannot say how it knows something has not established it.

    The owning document is found by the subject's existing facts rather than by entity kind, so the
    twelve fact-bearing document types stay one question instead of a list that goes stale. A
    subject with no facts at all therefore reads as absent, which is the same refusal a genuinely
    unknown subject gets and sends the operator to the same place: promote the entity first.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        documents = _load(tree)
        _unused_fact_id(documents, fact_id)
        path, document = _document_owning(documents, subject_id)

        payload = document.model_dump(mode="json")
        payload["facts"] = [
            *payload["facts"],
            {
                "fact_id": fact_id,
                "subject_id": subject_id,
                "predicate": predicate,
                "value": {"type": "string", "value": value},
                "verification_state": verification_state,
                "verification_basis": verification_basis,
                "usage_context": usage_context,
                "evidence_ids": [evidence_id],
                "allowed_surfaces": sorted(set(surfaces)),
                "conflict_group_id": None,
                "reviewed_at": as_of.isoformat(),
                "expires_at": None,
                "supersedes_fact_ids": [],
                "import_lineage": None,
                "notes": None,
            },
        ]
        rewritten = _revalidated(type(document), payload, path)

        evidence = _evidence_naming(documents, (evidence_id,), fact_id)
        restated = _manifest_restating_the_evidence_set(bundle_root, documents, evidence)
        changed = {EVIDENCE_PATH: evidence, MANIFEST_PATH: restated, path: rewritten}
        _write_documents(tree, changed)
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    return OperationOutcome.clean(
        FactAddition(
            draft_name=draft_name,
            fact_id=fact_id,
            document=path.as_posix(),
            owner_gates=_gates(documents, changed),
        )
    )


def import_source(
    bundle_root: Path,
    *,
    draft_name: str,
    source_id: str,
    source_bytes: bytes | None,
) -> OperationOutcome[SourceImport]:
    """Enumerate one owner-approved source into `drafts/<name>/imports/source-ledger.yaml` (§18).

    `source_bytes` is what `--from` carried, or `None` to resolve the source through the root-only
    `local-sources.yaml` sidecar. The enumerator itself still only ever sees bytes — §18's rule that
    the importer must not resolve a personal path is about the *adapter*, and the sidecar is the one
    file designed to hold exactly that path, excluded from every revision and both digests so it
    cannot reach a promoted document.

    **Only the ledger is written.** Candidates and exclusions stay owner-authored, so this cannot
    dispose of a record on the owner's behalf: `build_source_ledger` derives every disposition from
    the candidates and exclusions already in the draft, which is why a re-import of a source the
    owner has since excluded keeps that exclusion instead of resetting it to `review_required`.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        documents = _load(tree)
        spec = _declared_source(documents, source_id)
        ledger = _source_ledger(documents)
        resolved = _source_bytes(bundle_root, spec, source_bytes)
        enumerated = _enumerated(spec, resolved, _approved_scope(ledger, spec))
        rebuilt = _ledger_with(
            ledger, enumerated, _candidate_package(documents), _exclusions(documents)
        )
        changed = rebuilt != ledger
        if changed:
            _write_document(tree, SOURCE_LEDGER_PATH, rebuilt)
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    mine = [row for row in rebuilt.records if row.source_id == source_id]
    return OperationOutcome.clean(
        SourceImport(
            draft_name=draft_name,
            source_id=source_id,
            enumerator_id=enumerated.enumerator_id,
            source_content_digest=enumerated.source_content_digest,
            record_count=len(mine),
            counts={
                disposition.value: sum(1 for row in mine if row.disposition is disposition)
                for disposition in Disposition
            },
            denominator=rebuilt.record_count,
            changed=changed,
        )
    )


def extract_source(
    bundle_root: Path,
    *,
    draft_name: str,
    source_id: str,
    source_bytes: bytes | None,
) -> OperationOutcome[SourceExtraction]:
    """Deterministically extract one source's candidates, re-deriving the ledger and report (§6.5).

    Re-enumerates the source (the ledger stores only its record IDs, not their atomic values), runs
    the seeded `policy/extraction-mappings.yaml` interpreter over it, and writes three documents
    that cannot disagree: `imports/candidates.yaml` (this source's candidates rebuilt per §6.6),
    `imports/source-ledger.yaml` (dispositions re-derived), and
    `imports/extraction-report.yaml` (one closed drain reason per `review_required` record, §6.3a).

    Authoritative per source: every candidate and report entry belonging to this source is replaced,
    and every other source's candidates and entries are untouched. Occurrence lineage survives for a
    candidate ID the rebuild reproduces; a superseded one is not retained
    (`rebuild_source_candidates`).

    The three writes cannot be made atomic (D-137), so a mid-write failure is named
    `PARTIAL_EDIT_APPLIED` by `_write_documents`, deliberately outside the could-not-complete tier a
    retry would refuse.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        documents = _load(tree)
        spec = _declared_source(documents, source_id)
        ledger = _source_ledger(documents)
        catalog = _predicate_catalog(documents)
        mappings = _extraction_mappings(documents)
        existing_candidates = _candidate_package(documents)
        existing_report = _extraction_report(documents)
        exclusions = _exclusions(documents)
        resolved = _source_bytes(bundle_root, spec, source_bytes)
        enumerated = _enumerated(spec, resolved, _approved_scope(ledger, spec))
        mapping = _mapping_for(mappings, enumerated.enumerator_id)
        _checked_mapping(mapping, catalog, enumerated.enumerator_id)

        result = run_extraction(enumerated.records, mapping)
        fresh = _extracted_candidates(enumerated, result.proposals, catalog)

        # Every ID that is or was one of this source's records: the fresh enumeration plus whatever
        # the old ledger still carried, so a record that vanished takes its stale candidates and
        # report entry with it.
        this_source_ids = {record.source_record_id for record in enumerated.records}
        this_source_ids |= {
            row.source_record_id for row in ledger.records if row.source_id == source_id
        }

        rebuilt_candidates = _rebuild_candidates(
            existing_candidates, fresh, source_record_ids=this_source_ids
        )
        rebuilt_ledger = _ledger_with(ledger, enumerated, rebuilt_candidates, exclusions)
        rebuilt_report = _rebuild_report(
            existing_report, result.failures, rebuilt_ledger, this_source_ids
        )

        changed = (
            rebuilt_candidates != existing_candidates
            or rebuilt_ledger != ledger
            or rebuilt_report != existing_report
        )
        if changed:
            # Candidates first (the evidence a disposition derives from), then the ledger that
            # dispositions against them, then the report that explains what is left review_required.
            _write_documents(
                tree,
                {
                    IMPORT_CANDIDATES_PATH: rebuilt_candidates,
                    SOURCE_LEDGER_PATH: rebuilt_ledger,
                    EXTRACTION_REPORT_PATH: rebuilt_report,
                },
            )
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    mine = [row for row in rebuilt_ledger.records if row.source_id == source_id]
    my_ids = {row.source_record_id for row in mine}
    return OperationOutcome.clean(
        SourceExtraction(
            draft_name=draft_name,
            source_id=source_id,
            enumerator_id=enumerated.enumerator_id,
            source_content_digest=enumerated.source_content_digest,
            record_count=len(mine),
            counts={
                disposition.value: sum(1 for row in mine if row.disposition is disposition)
                for disposition in Disposition
            },
            denominator=rebuilt_ledger.record_count,
            report_reasons=_reason_counts(rebuilt_report, my_ids),
            changed=changed,
        )
    )


def promote_candidates(
    bundle_root: Path,
    *,
    draft_name: str,
    source_id: str,
    source_bytes: bytes | None,
    as_of: date,
) -> OperationOutcome[CandidatePromotion]:
    """Promote one source's imported candidates into entities, facts, and skills (§6.8, D-182).

    Deterministic, grounded, and owner-mediated: entities and their facts come from the imported
    candidates; a skill's entity binding comes from a bullet's authored `tech_tags` (the source is
    re-enumerated to recover them, as the candidates do not carry them); and every fact is born
    `unresolved` with no fabricated evidence — the owner's confirm/attest/approve step is what
    promotes and renders.

    One-shot: refuses if the draft already holds entities or skills, because a re-run would clobber
    the owner's edits to what it wrote. `as_of` is passed in, never read from a clock here.

    Writes several documents (entity files, `skills/inventory.yaml`, and — when a promoted skill
    names a category the catalog lacks — `policy/skill-categories.yaml`); the multi-file write
    cannot be atomic (D-137), so a mid-write failure is named `PARTIAL_EDIT_APPLIED`.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        documents = _load(tree)
        spec = _declared_source(documents, source_id)
        ledger = _source_ledger(documents)
        catalog = _predicate_catalog(documents)
        candidates = _candidate_package(documents)
        categories = _skill_categories(documents)
        _refuse_if_already_promoted(documents)
        resolved = _source_bytes(bundle_root, spec, source_bytes)
        enumerated = _enumerated(spec, resolved, _approved_scope(ledger, spec))

        locator_by_record = {
            row.source_record_id: row.normalized_locator
            for row in ledger.records
            if row.source_id == source_id
        }
        source_candidates = [
            candidate
            for candidate in candidates.candidates
            if candidate.source_record_id in locator_by_record
        ]
        try:
            plan = build_promotion(
                candidates=source_candidates,
                locator_by_record=locator_by_record,
                tech_tags_by_bullet_locator=_tech_tags_by_bullet(enumerated),
                catalog=catalog,
                existing_categories=categories,
                source_id=source_id,
                source_content_digest=enumerated.source_content_digest,
                as_of=as_of,
            )
        except PromotionError as exc:
            raise _refusal(
                IssueCode.MODEL_VALIDATION_ERROR,
                f"{source_id} candidates could not be promoted: {exc}",
                path=SKILL_INVENTORY_PATH.as_posix(),
                record_id=source_id,
            ) from exc

        changed = bool(plan.documents)
        if changed:
            _write_documents(tree, plan.documents)
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    return OperationOutcome.clean(
        CandidatePromotion(
            draft_name=draft_name,
            source_id=source_id,
            entity_count=plan.entity_count,
            fact_count=plan.fact_count,
            skill_count=plan.skill_count,
            category_count=plan.category_count,
            changed=changed,
        )
    )


# --------------------------------------------------------------------------------------
# Steps. Each returns its value or raises `_Refused`.
# --------------------------------------------------------------------------------------


def _skill_categories(documents: BundleDocuments) -> SkillCategoryCatalog:
    document = documents.by_path.get(SKILL_CATEGORIES_PATH)
    if not isinstance(document, SkillCategoryCatalog):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {SKILL_CATEGORIES_PATH}; a promoted skill needs a category catalog",
            path=SKILL_CATEGORIES_PATH.as_posix(),
        )
    return document


def _refuse_if_already_promoted(documents: BundleDocuments) -> None:
    """Promotion is one-shot: a non-empty entity or skill set means it already ran (§6.8/D-182).

    Re-running would recreate the same deterministic entity and fact IDs the owner has since edited
    (confirmed a state, attached evidence), clobbering that work — so refuse rather than overwrite.
    """
    for path, document in documents.by_path.items():
        if isinstance(document, EmploymentFactsDocument | ProjectFactsDocument):
            raise _refusal(
                IssueCode.DUPLICATE_RECORD_ID,
                f"{path} already holds a promoted entity; clear the promoted facts and skills to "
                "re-promote (promotion is one-shot so it never clobbers an owner's edits)",
                path=path.as_posix(),
            )
        if isinstance(document, SkillInventoryDocument) and document.skills:
            raise _refusal(
                IssueCode.DUPLICATE_RECORD_ID,
                f"{path} already holds promoted skills; clear the promoted facts and skills to "
                "re-promote (promotion is one-shot so it never clobbers an owner's edits)",
                path=path.as_posix(),
            )


def _tech_tags_by_bullet(enumerated: EnumeratedSource) -> dict[str, tuple[str, ...]]:
    """Each bullet record's authored `tech_tags`, keyed by normalized locator (§6.8 grounding).

    The candidates do not carry `tech_tags` — extraction maps a bullet to an accomplishment string
    — so the source is re-enumerated and the atomic value read here, package-locally (the enumerator
    imports no `tailor`, keeping the import wall intact).
    """
    tags: dict[str, tuple[str, ...]] = {}
    for record in enumerated.records:
        value = record.atomic_value
        if isinstance(value, Mapping) and "tech_tags" in value:
            raw = value["tech_tags"]
            if isinstance(raw, Sequence) and not isinstance(raw, str | bytes):
                tags[record.normalized_locator] = tuple(str(tag) for tag in raw)
    return tags


def _declared_source(documents: BundleDocuments, source_id: str) -> SourceSpec:
    """The source's row in `policy/sources.yaml`, which is what makes it owner-approved.

    Refused rather than invented: the catalog is where an owner states that a source may be read at
    all, so importing one it does not declare would let the command approve its own input.
    """
    catalog = documents.by_path.get(SOURCE_CATALOG_PATH)
    if not isinstance(catalog, SourceCatalog):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {SOURCE_CATALOG_PATH}, so no source is approved for import",
            path=SOURCE_CATALOG_PATH.as_posix(),
        )
    for spec in catalog.sources:
        if spec.source_id == source_id:
            return spec
    raise _refusal(
        IssueCode.BROKEN_REFERENCE,
        f"{source_id} is not declared in {SOURCE_CATALOG_PATH}; add it there first, because the "
        "catalog is where a source becomes one this bundle may read",
        path=SOURCE_CATALOG_PATH.as_posix(),
        record_id=source_id,
    )


def _source_ledger(documents: BundleDocuments) -> SourceLedger:
    document = documents.by_path.get(SOURCE_LEDGER_PATH)
    if not isinstance(document, SourceLedger):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {SOURCE_LEDGER_PATH}, so there is nowhere to enumerate into",
            path=SOURCE_LEDGER_PATH.as_posix(),
        )
    return document


def _candidate_package(documents: BundleDocuments) -> CandidatePackage:
    document = documents.by_path.get(IMPORT_CANDIDATES_PATH)
    if not isinstance(document, CandidatePackage):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {IMPORT_CANDIDATES_PATH}, so no record's disposition can be derived",
            path=IMPORT_CANDIDATES_PATH.as_posix(),
        )
    return document


def _exclusions(documents: BundleDocuments) -> dict[str, ExclusionRecord]:
    document = documents.by_path.get(IMPORT_EXCLUSIONS_PATH)
    if not isinstance(document, ExclusionLedger):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {IMPORT_EXCLUSIONS_PATH}, so no record's disposition can be derived",
            path=IMPORT_EXCLUSIONS_PATH.as_posix(),
        )
    return {record.source_record_id: record for record in document.exclusions}


def _predicate_catalog(documents: BundleDocuments) -> PredicateCatalog:
    document = documents.by_path.get(PREDICATE_CATALOG_PATH)
    if not isinstance(document, PredicateCatalog):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {PREDICATE_CATALOG_PATH}, so extracted values cannot be typed",
            path=PREDICATE_CATALOG_PATH.as_posix(),
        )
    return document


def _extraction_mappings(documents: BundleDocuments) -> ExtractionMappingsDocument:
    document = documents.by_path.get(EXTRACTION_MAPPINGS_PATH)
    if not isinstance(document, ExtractionMappingsDocument):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {EXTRACTION_MAPPINGS_PATH}, so there is no mapping to extract with",
            path=EXTRACTION_MAPPINGS_PATH.as_posix(),
        )
    return document


def _extraction_report(documents: BundleDocuments) -> ExtractionReport:
    document = documents.by_path.get(EXTRACTION_REPORT_PATH)
    if not isinstance(document, ExtractionReport):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {EXTRACTION_REPORT_PATH}, so the drain has no durable carrier",
            path=EXTRACTION_REPORT_PATH.as_posix(),
        )
    return document


def _mapping_for(mappings: ExtractionMappingsDocument, adapter_id: str) -> ExtractionMapping:
    """The seeded mapping for this source's adapter, or the refusal that says none is declared.

    Keyed by adapter id, which is the enumerator id every source of a kind shares, so a source with
    no declared mapping is a gap the seed must fill rather than a per-record surprise.
    """
    resolved = mappings_from_document(mappings).get(adapter_id)
    if resolved is None:
        raise _refusal(
            IssueCode.BROKEN_REFERENCE,
            f"{EXTRACTION_MAPPINGS_PATH} declares no mapping for adapter {adapter_id!r}; "
            "the deterministic lane cannot extract a source whose adapter it does not map",
            path=EXTRACTION_MAPPINGS_PATH.as_posix(),
            record_id=adapter_id,
        )
    return resolved


def _checked_mapping(
    mapping: ExtractionMapping, catalog: PredicateCatalog, adapter_id: str
) -> None:
    """Refuse a seeded mapping that is not a legal member of the seeded catalog, once, before any
    record is read (§6.2a "catalog-checked, once, before extraction").

    `policy/extraction-mappings.yaml` is owner-editable bundle data, so this is the gate that keeps
    a misrouted mapping — a `project` entry's slots naming `employment.*` — from reaching the
    interpreter and landing candidates on an illegal subject, which would surface only at promotion
    as `PREDICATE_SUBJECT_KIND_ILLEGAL`. The violation's own `IssueCode` is typed at the raise site,
    so nothing here classifies a message.

    Predicates this bundle's catalog does not carry are not refused here: a host catalog may be a
    deliberate subset of the one the builtin mapping was written against (D-179), and a rule that
    cannot fire is not this gate's business — typing a proposal refuses it downstream if one ever
    does. Misrouting is enforced regardless.
    """
    try:
        validate_mapping_against_catalog(mapping, catalog, require_known_predicates=False)
    except ExtractionMappingError as exc:
        raise _refusal(
            exc.code,
            f"{EXTRACTION_MAPPINGS_PATH} declares a mapping for adapter {adapter_id!r} that the "
            f"seeded catalog does not admit: {exc}",
            path=EXTRACTION_MAPPINGS_PATH.as_posix(),
            record_id=adapter_id,
        ) from exc


def _extracted_candidates(
    enumerated: EnumeratedSource,
    proposals: Sequence[ProposedCandidate],
    catalog: PredicateCatalog,
) -> CandidatePackage:
    """Type and identify this source's proposals; refuses rather than half-builds, like import."""
    try:
        return build_candidate_package(
            [enumerated],
            proposals,
            predicates=catalog,
            candidates_version=1,
        )
    except CandidateImportError as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{enumerated.source_id} extraction proposals could not be typed: {exc}",
            path=IMPORT_CANDIDATES_PATH.as_posix(),
            record_id=enumerated.source_id,
        ) from exc


def _rebuild_candidates(
    existing: CandidatePackage,
    fresh: CandidatePackage,
    *,
    source_record_ids: set[str],
) -> CandidatePackage:
    try:
        return rebuild_source_candidates(existing, fresh, source_record_ids=source_record_ids)
    except CandidateImportError as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{IMPORT_CANDIDATES_PATH} would not be valid after this extraction: {exc}",
            path=IMPORT_CANDIDATES_PATH.as_posix(),
        ) from exc


def _rebuild_report(
    existing: ExtractionReport,
    failures: Sequence[ExtractionFailure],
    rebuilt_ledger: SourceLedger,
    this_source_ids: set[str],
) -> ExtractionReport:
    """Replace this source's report entries; keep every other source's (§6.3a, §6.6).

    A failure only becomes a report entry when the rebuilt ledger left its record `review_required`:
    a record the owner excluded is `excluded`, and §6.3a forbids a report entry for it, while a
    record that produced a candidate is `imported` and never appears in `failures` at all. Entries
    are sorted by record ID so the document does not depend on extraction order.
    """
    disposition_by_record = {
        row.source_record_id: row.disposition for row in rebuilt_ledger.records
    }
    fresh_entries = [
        {"source_record_id": failure.source_record_id, "reason": failure.reason}
        for failure in failures
        if disposition_by_record.get(failure.source_record_id) is Disposition.REVIEW_REQUIRED
    ]
    kept_entries = [
        {"source_record_id": entry.source_record_id, "reason": entry.reason.value}
        for entry in existing.entries
        if entry.source_record_id not in this_source_ids
    ]
    entries = sorted([*kept_entries, *fresh_entries], key=lambda entry: entry["source_record_id"])
    try:
        return ExtractionReport.model_validate(
            {"report_version": existing.report_version, "entries": entries}
        )
    except ValidationError as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{EXTRACTION_REPORT_PATH} would not be valid after this extraction: "
            f"{exc.error_count()} field error(s)",
            path=EXTRACTION_REPORT_PATH.as_posix(),
        ) from exc


def _reason_counts(report: ExtractionReport, record_ids: set[str]) -> dict[str, int]:
    """This source's report entries by reason, every closed reason present including the zeroes."""
    counts = {reason.value: 0 for reason in ExtractionReportReason}
    for entry in report.entries:
        if entry.source_record_id in record_ids:
            counts[entry.reason.value] += 1
    return counts


def _approved_scope(ledger: SourceLedger, spec: SourceSpec) -> ApprovedScope:
    """The scope this source is approved under — reused from the ledger, never widened here.

    §18: "Widening an approved source's scope needs a new owner approval, because the scope is a
    property of the ledger rather than of the enumerator." So a source already in the ledger keeps
    exactly the scope it carries, and a first import may only derive the one scope that contains no
    owner choice: `complete_file`. A `selected_sections` source's locators ARE the owner's decision
    about what may be read, and deriving them would be this command approving its own input.
    """
    for source in ledger.sources:
        if source.source_id == spec.source_id:
            return source.approved_scope
    binding = SOURCE_KIND_ADAPTERS[spec.source_kind]
    if binding.scope_kind != "complete_file":
        raise _refusal(
            IssueCode.IMPORT_SCOPE_INVALID,
            f"{spec.source_id} is a {spec.source_kind.value} source, which is approved with a "
            f"{binding.scope_kind} scope; author its locators into "
            f"{SOURCE_LEDGER_PATH} first, because which sections may be read is yours to decide",
            path=SOURCE_LEDGER_PATH.as_posix(),
            record_id=spec.source_id,
        )
    return CompleteFileScope(kind="complete_file")


def _source_bytes(bundle_root: Path, spec: SourceSpec, provided: bytes | None) -> bytes:
    """The source document's bytes: what `--from` carried, or what the sidecar resolves.

    The sidecar maps a source to a machine-local *root*, and the document sits beneath it at the
    source's `portable_locator`. Joining them here rather than storing a whole path is what keeps
    the revisioned half portable: `policy/sources.yaml` states where a document sits inside a tree,
    and only the non-revisioned sidecar knows where that tree is on this machine.

    No absolute path reaches a diagnostic from any branch, including the I/O one — `io_reason`
    reports the failure without the filename an `OSError` stringifies with.
    """
    if provided is not None:
        return provided
    root = _local_sources(bundle_root).get(spec.source_id)
    if root is None:
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"{spec.source_id} has no machine-local root: pass --from, or map the source to its "
            "root in local-sources.yaml, which is the file that exists to reopen an original "
            "document and is excluded from every revision",
            path=LOCAL_SOURCES_FILE,
            record_id=spec.source_id,
        )
    path = Path(root).joinpath(*PurePosixPath(spec.portable_locator).parts)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _refusal(
            IssueCode.IO_ERROR,
            f"{spec.source_id} could not be read at its portable locator "
            f"{spec.portable_locator!r} beneath the root local-sources.yaml maps it to: "
            f"{io_reason(exc)}",
            path=LOCAL_SOURCES_FILE,
            record_id=spec.source_id,
        ) from exc


def _local_sources(bundle_root: Path) -> Mapping[str, str]:
    """The sidecar's source-ID to absolute-root mapping, or empty when it is absent.

    Absent is not an error — `init` writes `{}` and a bundle whose sources are always passed with
    `--from` never needs it. A sidecar that will not parse *is* an error, because it is a file this
    machine cannot read at all, and silently treating it as empty would send the operator to
    `--from` for a mapping they had already written.
    """
    path = local_sources_path(bundle_root)
    if not path.exists():
        return {}
    try:
        raw = load_yaml_bytes(path.read_bytes(), logical_path=PurePosixPath(LOCAL_SOURCES_FILE))
    except RestrictedYamlError as exc:
        raise _refusal(exc.code, str(exc), path=LOCAL_SOURCES_FILE) from exc
    except OSError as exc:
        raise _refusal(
            IssueCode.IO_ERROR, f"{LOCAL_SOURCES_FILE}: {io_reason(exc)}", path=LOCAL_SOURCES_FILE
        ) from exc
    try:
        return LocalSourcesSidecar.model_validate(raw).roots
    except ValidationError as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{LOCAL_SOURCES_FILE} is not a source-ID to absolute-root mapping: "
            f"{exc.error_count()} field error(s)",
            path=LOCAL_SOURCES_FILE,
        ) from exc


def _enumerated(spec: SourceSpec, source_bytes: bytes, scope: ApprovedScope) -> EnumeratedSource:
    """Run the adapter. Its refusals are reported, never partially applied.

    `EnumerationError` and `CandidateImportError` both mean the source is not the shape the adapter
    was approved for; a half-enumerated source would be counted against the Gate B denominator
    while describing less than it claims, which is why they raise rather than report.
    """
    try:
        return enumerate_source(spec, source_bytes, scope=scope)
    except (EnumerationError, CandidateImportError) as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{spec.source_id} could not be enumerated: {exc}",
            path=SOURCE_INPUT.as_posix(),
            record_id=spec.source_id,
        ) from exc


def _ledger_with(
    ledger: SourceLedger,
    enumerated: EnumeratedSource,
    package: CandidatePackage,
    exclusions: Mapping[str, ExclusionRecord],
) -> SourceLedger:
    """Splice this source's rows into the ledger, leaving every other source's bytes alone.

    Rebuilt through `build_source_ledger` rather than by editing rows, so the disposition rule has
    one home. The splice keeps the re-imported source at its existing position — replacing its
    block in place rather than appending — because the ledger is a document an owner reads, and a
    re-import that reordered the sources of a 24,000-record bundle would produce a diff nobody can
    review for a change that touched one source.

    The result is validated as a whole, which is what makes the merge safe: `SourceLedger`'s own
    validator requires each source's `source_record_ids` to equal its records in adapter order, so
    a splice that dropped or misordered a row cannot be written.
    """
    try:
        fresh = build_source_ledger(
            [enumerated],
            package,
            exclusions=exclusions,
            ledger_version=ledger.ledger_version,
        )
    except CandidateImportError as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{enumerated.source_id} could not be assembled into a ledger: {exc}",
            path=SOURCE_LEDGER_PATH.as_posix(),
            record_id=enumerated.source_id,
        ) from exc

    sources = [source.model_dump(mode="json") for source in ledger.sources]
    replacement = fresh.sources[0].model_dump(mode="json")
    for position, source in enumerate(sources):
        if source["source_id"] == enumerated.source_id:
            sources[position] = replacement
            break
    else:
        sources.append(replacement)

    records: list[dict[str, Any]] = []
    placed = False
    for row in ledger.records:
        if row.source_id == enumerated.source_id:
            if not placed:
                records.extend(item.model_dump(mode="json") for item in fresh.records)
                placed = True
            continue
        records.append(row.model_dump(mode="json"))
    if not placed:
        records.extend(item.model_dump(mode="json") for item in fresh.records)

    try:
        return SourceLedger.model_validate(
            {
                "ledger_version": ledger.ledger_version,
                "sources": sources,
                "records": records,
            }
        )
    except ValidationError as exc:
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{SOURCE_LEDGER_PATH} would not be valid after this import: "
            f"{exc.error_count()} field error(s)",
            path=SOURCE_LEDGER_PATH.as_posix(),
            record_id=enumerated.source_id,
        ) from exc


def _draft(bundle_root: Path, name: str) -> Path:
    """The named draft directory.

    The **segment** grammar, not the shorter operator-facing one: every name `inventory` lists
    under `drafts/` must be a name these commands accept, including a rebase backup — which is the
    only copy of a draft whose rebase went wrong, and so exactly the tree an owner would be
    authoring into. `paths.draft_root` applies it.
    """
    # Before the draft, because `drafts/<name> does not exist` about a bundle that does not exist
    # sends the owner to `checkout` for a bundle they have not created (D-138). This restates
    # `require_confined_root`'s check rather than calling it, for the same reason `promote` does:
    # these three commands answer before they reach any function that confines the root.
    if not bundle_root.is_dir():
        raise _refusal(
            IssueCode.BUNDLE_NOT_FOUND,
            "there is no bundle at this path, so there is no draft to author into; `init` creates "
            "one, and --bundle names an existing one somewhere else",
        )
    try:
        tree = draft_root(bundle_root, name)
    except BundlePathError as exc:
        raise _refusal(IssueCode.DRAFT_NOT_FOUND, str(exc)) from exc
    if not tree.is_dir():
        raise _refusal(
            IssueCode.DRAFT_NOT_FOUND,
            f"drafts/{name} does not exist; check out a draft before authoring into it",
        )
    return tree


def _load(tree: Path) -> BundleDocuments:
    try:
        return load_documents(tree, mode="draft")
    except ProfileBundleError as exc:
        raise _Refused(parse_error_diagnostics(exc)) from exc


def _parse(raw: bytes, adapter: TypeAdapter[_T], *, logical_path: PurePosixPath) -> _T:
    try:
        payload = load_yaml_bytes(raw, logical_path=logical_path)
    except RestrictedYamlError as exc:
        raise _Refused((diagnostic(exc.code, str(exc), path=logical_path.as_posix()),)) from exc
    try:
        return adapter.validate_python(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{logical_path} is not a valid record: {exc.error_count()} problem(s); first at "
            f"{'.'.join(str(part) for part in first['loc'])!r}: {first['msg']}",
            path=logical_path.as_posix(),
        ) from exc


def _within_capture_limit(capture: bytes, record: AnyEvidence) -> None:
    """§12.2's per-capture cap, checked here rather than left to `write_blob`.

    `write_blob` raises the bare package base class for an oversize capture, which a caller can
    only tell apart from anything else by reading its message. Checking the size against the
    constant `write_blob` reads keeps the refusal typed, and applies it to inline captures too —
    which never reach `write_blob` at all.
    """
    if len(capture) > MAX_CAPTURE_BYTES:
        raise _refusal(
            IssueCode.CAPTURE_TOO_LARGE,
            f"the capture is {len(capture)} bytes, over the {MAX_CAPTURE_BYTES}-byte per-capture "
            "limit; store the excerpt that matters and cite the whole",
            path=EVIDENCE_INPUT.as_posix(),
            record_id=record.evidence_id,
        )


def _scan(capture: bytes, record: AnyEvidence) -> None:
    """The §12.2 secret scan over the real bytes.

    `InvalidUtf8CaptureError` is caught rather than allowed to escape because every allowed media
    type is UTF-8 text, so bytes that will not decode are the operator's file being the wrong thing
    — a finding about their input, not an internal failure.
    """
    try:
        hits = scan_capture(
            capture,
            media_type=record.capture.media_type,
            ruleset_version=CURRENT_RULESET_VERSION,
        )
    except InvalidUtf8CaptureError as exc:
        raise _refusal(
            IssueCode.INVALID_UTF8,
            f"the capture is not valid UTF-8: {exc}",
            path=EVIDENCE_INPUT.as_posix(),
            record_id=record.evidence_id,
        ) from exc
    if not hits:
        return
    # Rule and byte range only. `Diagnostic` forbids the matched text, and this is the one place in
    # the package where that text is definitely a live secret.
    raise _Refused(
        tuple(
            diagnostic(
                IssueCode.SECRET_DETECTED,
                f"the capture matches secret-scan rule {hit.rule_id} at bytes "
                f"{hit.start}-{hit.end}; redact it and capture again — nothing was written",
                path=EVIDENCE_INPUT.as_posix(),
                record_id=record.evidence_id,
                rule_id=hit.rule_id,
                start=hit.start,
                end=hit.end,
            )
            for hit in hits
        )
    )


def _evidence_document(documents: BundleDocuments) -> EvidenceRecordsDocument:
    document = documents.by_path.get(EVIDENCE_PATH)
    if not isinstance(document, EvidenceRecordsDocument):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            f"the draft has no {EVIDENCE_PATH}, so there is nowhere to record this capture",
            path=EVIDENCE_PATH.as_posix(),
        )
    return document


def _fact_position(
    documents: BundleDocuments, fact_id: str
) -> tuple[PurePosixPath, DocumentModel, int, FactRecord]:
    """Where one fact lives: its document, its index within `facts`, and the record itself.

    Asked by type rather than by name for `_documents_citing_back`'s reason — there are twelve
    fact-bearing documents and `FactBearingDocument` exists so this does not become a list that
    goes stale when a thirteenth arrives.

    The document is returned as a `DocumentModel` and the record alongside it, rather than as the
    `FactBearingDocument` the isinstance test proves it is. That base class is not a member of the
    union every writer here takes: narrowing to it discards which concrete document this is, and
    the value could then not be handed back to `_write_documents` at all. Returning the record too
    is what makes that possible without a cast — no caller has to reach through `.facts` on a union
    whose other members do not have it.
    """
    for path, document in documents.items():
        if not isinstance(document, FactBearingDocument):
            continue
        for position, fact in enumerate(document.facts):
            if fact.fact_id == fact_id:
                return (path, document, position, fact)
    raise _refusal(
        IssueCode.BROKEN_REFERENCE,
        f"{fact_id} is not a fact this draft holds; `inspect` lists what it does",
        record_id=fact_id,
    )


def _correctable(fact: FactRecord) -> None:
    """The two states in which filing a successor would assert something the owner did not.

    A basis other than `owner_attested` belongs to the evidence that established it — a document
    read, a repository checked. The owner retyping the wording does not re-establish any of that,
    so a successor inheriting the basis would borrow authority from a record nobody re-read, and
    one silently downgraded to `owner_attested` would drop a verification the operator never asked
    to drop. Neither is this command's call to make.

    An already-superseded record is refused because correcting it would leave two live successors
    of one parent, and "the current value" would stop being a question with an answer.
    """
    if fact.verification_basis is not VerificationBasis.OWNER_ATTESTED:
        raise _refusal(
            IssueCode.VERIFICATION_BASIS_UNSUPPORTED,
            f"{fact.fact_id} is established by {fact.verification_basis.value}, which an owner's "
            "rewording does not re-establish; capture evidence for the new wording and add a fact "
            "citing it",
            record_id=fact.fact_id,
        )
    if fact.verification_state not in EFFECTIVE_STATES:
        raise _refusal(
            IssueCode.FACT_STATE_INCONSISTENT,
            f"{fact.fact_id} is {fact.verification_state.value} and no longer reaches any surface; "
            "correct the record that superseded it instead",
            record_id=fact.fact_id,
        )
    if fact.value.type != "string":
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"{fact.fact_id} holds a {fact.value.type} value, which text cannot express; edit the "
            "draft's YAML directly for a value this command cannot state",
            record_id=fact.fact_id,
        )


def _successor_fact_id(fact_id: str, documents: BundleDocuments) -> str:
    """`<id>.r2`, then `.r3` — the revision counted on the ID rather than searched for.

    Derived from the ID the operator named, so a chain of corrections reads as one lineage in a
    sorted directory listing instead of scattering across unrelated numbers. The collision check is
    still made against the whole draft: the suffix is a convention, and a draft that already holds
    the ID it produces would otherwise get a duplicate that only structural validation catches.
    """
    base, _, tail = fact_id.rpartition(".")
    revision = 2
    if base and tail.startswith("r") and tail[1:].isdigit():
        fact_id, revision = base, int(tail[1:]) + 1
    successor = f"{fact_id}.r{revision}"
    _unused_fact_id(documents, successor)
    return successor


def _unused_fact_id(documents: BundleDocuments, fact_id: str) -> None:
    for path, document in documents.items():
        if not isinstance(document, FactBearingDocument):
            continue
        for fact in document.facts:
            if fact.fact_id == fact_id:
                raise _refusal(
                    IssueCode.DUPLICATE_RECORD_ID,
                    f"{fact_id} is already a fact in this draft; an identifier names one record",
                    path=path.as_posix(),
                    record_id=fact_id,
                )


def _document_owning(
    documents: BundleDocuments, subject_id: str
) -> tuple[PurePosixPath, DocumentModel]:
    """The document that already holds facts about `subject_id`.

    Returned as a `DocumentModel` for `_fact_position`'s reason: the base class the isinstance test
    proves is not a member of the union the writers take.
    """
    for path, document in documents.items():
        if not isinstance(document, FactBearingDocument):
            continue
        if any(fact.subject_id == subject_id for fact in document.facts):
            return (path, document)
    raise _refusal(
        IssueCode.BROKEN_REFERENCE,
        f"no document in this draft holds facts about {subject_id}, so there is nowhere to write "
        "one; promote the entity before adding facts to it",
        record_id=subject_id,
    )


def _evidence_naming(
    documents: BundleDocuments, evidence_ids: Sequence[str], fact_id: str
) -> EvidenceRecordsDocument:
    """`evidence/records.yaml` with each named record supporting `fact_id` (§12).

    The mirror of `_documents_citing_back`, which writes the fact side of the same contract when the
    evidence is what is new. Here the fact is what is new, so the evidence side is the one missing —
    and §12 compares the two directions exactly, so writing only one leaves the draft failing
    `evidence_link_asymmetry` and unapprovable.

    Refusing an ID the draft does not hold is what keeps that promise: a citation of an absent
    record is a broken reference the next validation reports, and writing it would leave the very
    asymmetry this closes.
    """
    existing = _evidence_document(documents)
    held = {record.evidence_id for record in existing.evidence}
    for evidence_id in evidence_ids:
        if evidence_id not in held:
            raise _refusal(
                IssueCode.BROKEN_REFERENCE,
                f"{evidence_id} is not an evidence record this draft holds; capture it with "
                "`add-evidence` before citing it",
                path=EVIDENCE_PATH.as_posix(),
                record_id=evidence_id,
            )

    named = set(evidence_ids)
    payload = existing.model_dump(mode="json")
    for row in payload["evidence"]:
        if row["evidence_id"] not in named:
            continue
        # Sorted for `UniqueSorted`'s reason, and rebuilt from a set so re-offering a link that is
        # already there is a no-op rather than a duplicate refusal.
        row["supports_record_ids"] = sorted({*row["supports_record_ids"], fact_id})
    return EvidenceRecordsDocument.model_validate(payload)


def _revalidated(
    kind: type[DocumentModel], payload: dict[str, Any], path: PurePosixPath
) -> DocumentModel:
    """Rebuild a document from an edited payload, reporting a rejection as the operator's input.

    `edit_fact` builds its successor by copying a record the models already accepted, so only its
    value can be invalid and `StringValue` states that itself. `add_fact` assembles a record from
    twelve separate arguments, any of which the catalog or the models can refuse — an unknown
    predicate, a surface the predicate forbids, a state outside the enum. Letting that escape as a
    `ValidationError` would surface a caller's typo as an internal failure.
    """
    try:
        return kind.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise _refusal(
            IssueCode.MODEL_VALIDATION_ERROR,
            f"the fact is not a valid record: {exc.error_count()} problem(s); first at "
            f"{'.'.join(str(part) for part in first['loc'])!r}: {first['msg']}",
            path=path.as_posix(),
        ) from exc


def _unused_evidence_id(document: EvidenceRecordsDocument, record: AnyEvidence) -> None:
    if any(existing.evidence_id == record.evidence_id for existing in document.evidence):
        raise _refusal(
            IssueCode.DUPLICATE_RECORD_ID,
            f"{record.evidence_id} is already recorded in this draft; an identifier names one "
            "capture, and evidence is only ever added",
            path=EVIDENCE_PATH.as_posix(),
            record_id=record.evidence_id,
        )


def _conflict_documents(
    documents: BundleDocuments,
) -> tuple[ConflictRulings, ConflictGroups]:
    rulings = documents.by_path.get(CONFLICT_RULINGS_PATH)
    groups = documents.by_path.get(CONFLICT_GROUPS_PATH)
    if not isinstance(rulings, ConflictRulings) or not isinstance(groups, ConflictGroups):
        raise _refusal(
            IssueCode.MISSING_REQUIRED_FILE,
            "the draft has no conflict group or ruling document to append this decision to",
            path=CONFLICT_RULINGS_PATH.as_posix(),
        )
    return rulings, groups


def _unused_ruling_id(rulings: ConflictRulings, ruling: RulingRecord) -> None:
    if any(existing.ruling_id == ruling.ruling_id for existing in rulings.rulings):
        raise _refusal(
            IssueCode.DUPLICATE_RECORD_ID,
            f"{ruling.ruling_id} is already recorded in this draft; an identifier names one "
            "decision, and rulings are only ever appended",
            path=CONFLICT_RULINGS_PATH.as_posix(),
            record_id=ruling.ruling_id,
        )


def _ruled_group(groups: ConflictGroups, ruling: RulingRecord) -> ConflictRecord:
    target = next(
        (group for group in groups.conflicts if group.conflict_id == ruling.conflict_id), None
    )
    if target is None:
        raise _Refused(
            (
                diagnostic(
                    IssueCode.BROKEN_REFERENCE,
                    f"{ruling.ruling_id} rules on {ruling.conflict_id}, which this draft does not "
                    "declare",
                    path=CONFLICT_RULINGS_PATH.as_posix(),
                    record_id=ruling.ruling_id,
                    conflict_id=ruling.conflict_id,
                ),
            )
        )
    return target


def _capture_bytes(
    bundle_root: Path, record: AnyEvidence, capture: bytes
) -> tuple[str | None, Literal["written", "reused"] | None]:
    """Bind the record's declared capture to the bytes on the operator's disk.

    The discriminant decides which binding: a blob capture declares a digest and the bytes must
    hash to it, while an inline capture quotes the text and the bytes must normalise to exactly
    that. Neither is inferred from the other — a record whose text was rewritten from the capture
    file would be content the owner never read.
    """
    stated = record.capture
    if stated.kind == "inline":
        if unicodedata.normalize("NFC", capture.decode("utf-8")) != stated.text:
            raise _refusal(
                IssueCode.EVIDENCE_CONTRACT_UNMET,
                "the inline capture the record quotes is not the capture file's text; an inline "
                "record IS its capture, so the two cannot differ",
                path=EVIDENCE_INPUT.as_posix(),
                record_id=record.evidence_id,
            )
        return (None, None)

    try:
        result = write_blob(
            bundle_root,
            capture,
            expected_digest=stated.sha256,
            media_type=stated.media_type,
        )
    except BlobDigestMismatchError as exc:
        raise _Refused(
            (
                diagnostic(
                    IssueCode.BLOB_DIGEST_MISMATCH,
                    f"the capture hashes to sha256:{exc.actual}, not the sha256:{exc.expected} the "
                    "record declares; nothing was stored",
                    path=EVIDENCE_INPUT.as_posix(),
                    record_id=record.evidence_id,
                    expected=exc.expected,
                    actual=exc.actual,
                ),
            )
        ) from exc
    except BundleIoError as exc:
        # Deliberately not `str(exc)`: `blobs.write_blob` builds that message from a stringified
        # `OSError`, which carries the absolute path of the blob store. A diagnostic is rendered
        # into JSON an operator may paste elsewhere.
        raise _refusal(
            IssueCode.IO_ERROR,
            "the capture could not be stored in the bundle's blob store; nothing was written",
            path=EVIDENCE_PATH.as_posix(),
            record_id=record.evidence_id,
        ) from exc
    return (result.digest, result.outcome)


def _documents_citing_back(
    documents: BundleDocuments, record: AnyEvidence
) -> dict[PurePosixPath, DocumentModel]:
    """Every fact/metric document rewritten so the records this capture names cite it back (§12).

    §12 requires the two directions to agree exactly, and `add_evidence` writes only the evidence
    side, so before this existed a capture supporting a fact left the draft failing
    `evidence_link_asymmetry` and the owner had to make the second edit by hand. Writing it here is
    the owner's ruling (D-143): a correct operation must not leave a standing error behind it.

    Three things this reads that a narrower version would miss:

    - **The union of all three relationships**, not `supports` alone.
      `_evidence_links_are_symmetric` compares against `supports | contradicts | contextualizes`,
      so linking only the first leaves the other two reporting the very asymmetry this closes.
    - **Any fact-bearing document**, asked by type rather than by name. There are twelve, and
      `FactBearingDocument` is public precisely so this question does not become a list that goes
      stale when a thirteenth arrives.

    **Only facts and metrics are touched, and no filter here says so** — the lookup below does. They
    are the only kinds carrying `evidence_ids`, and the only records these documents hold: `FactId`
    and `MetricId` are `id_pattern("fact")` and `id_pattern("metric")`, so a fact-bearing document
    holds only `fact.*` and the metrics document only `metric.*`. An earlier version filtered the
    target set by those two prefixes; removing it changed no behaviour under mutation, because it
    could not — a `skill.*` target matches nothing whether or not it was filtered out first. D-115's
    rule applies: a check that cannot fire is deleted rather than left reading as coverage. The
    guarantee is tested where it lands, by the case that captures evidence naming only a skill and a
    claim and asserts no record document is rewritten.

    A target the draft does not hold is left alone: that is a broken reference, validation already
    reports it as one, and citing a record that is not there would not repair it.
    """
    named = {
        target
        for group in (
            record.supports_record_ids,
            record.contradicts_record_ids,
            record.contextualizes_record_ids,
        )
        for target in group
    }
    if not named:
        return {}

    changed: dict[PurePosixPath, DocumentModel] = {}
    field: str
    holder: tuple[BaseModel, ...]
    # `items()` rather than `by_path.items()`: it sorts, and this mapping's order becomes the rename
    # order and the `applied` list of a `PARTIAL_EDIT_APPLIED` diagnostic. Insertion order is only
    # incidentally stable — it comes from `layout.discover_source_files` walking `sorted(rglob)` —
    # and a diagnostic whose order depends on discovery order is what `paths()` exists to prevent.
    for path, document in documents.items():
        if isinstance(document, FactBearingDocument):
            field = "facts"
            holder = document.facts
        elif isinstance(document, MetricRecordsDocument):
            field = "metrics"
            holder = document.metrics
        else:
            continue
        payload = document.model_dump(mode="json")
        rows = payload[field]
        rewritten = False
        for position, item in enumerate(holder):
            if record_id_of(item) not in named:
                continue
            # `evidence_ids` is `UniqueSorted`, which sorts silently and refuses only duplicates —
            # so sorting here is what keeps these bytes equal to what the model would emit, and the
            # set is what stops a re-offered ID being refused as a duplicate. Comparing the rebuilt
            # list against the one already there makes re-capturing the same link a no-op
            # structurally, rather than by a separate "does it already cite this" test that could
            # disagree with the rebuild.
            cited = sorted({*rows[position]["evidence_ids"], record.evidence_id})
            if cited == rows[position]["evidence_ids"]:
                continue
            rows[position] = {**rows[position], "evidence_ids": cited}
            rewritten = True
        if rewritten:
            # Rebuilt through `model_validate` rather than `model_copy`, so every document and
            # record validator runs against the result. `model_copy` would install the tuple
            # unchecked, which is how an unsorted or duplicated citation would reach the disk.
            changed[path] = type(document).model_validate(payload)
    return changed


def _manifest_restating_the_evidence_set(
    bundle_root: Path, before: BundleDocuments, appended: EvidenceRecordsDocument
) -> BundleManifest:
    """The manifest with `evidence_set_digest` recomputed over the evidence set this capture makes.

    `evidence_set_digest` is the one manifest field that is a statement about content, so the writer
    that changes the content owns it — the same rule `drafts._initial_manifest` and `rebase` apply.
    Without it every successful capture leaves the draft failing
    `validation.digest._the_evidence_set_digest_is_recomputed`, which is the code §21 reserves for
    evidence mutated after promotion, and no command repairs it.

    Computed before either document is written so a capture that cannot state a digest refuses with
    the draft untouched. `resolve_conflict` needs no equivalent: `canonical.evidence_set_digest`
    reads the evidence document and the blobs it names, and a ruling changes neither.
    """
    after = BundleDocuments(
        manifest=before.manifest, by_path={**before.by_path, EVIDENCE_PATH: appended}
    )
    try:
        digest = evidence_set_digest(after, FilesystemBlobReader(blobs_dir(bundle_root)))
    except MissingBlobError as exc:
        # The same refusal `rebase` makes for the same reason: a draft whose blob store cannot serve
        # a capture it already cites has no evidence-set digest to state. Recapturing that blob is
        # §6's recovery, and it is a prerequisite of approval anyway.
        raise _refusal(
            IssueCode.MISSING_BLOB,
            f"blob sha256:{exc.bare_digest} is not in this bundle, so the draft cannot state an "
            "evidence-set digest; restore or recapture that evidence first",
            path=EVIDENCE_PATH.as_posix(),
        ) from exc
    return before.manifest.model_copy(update={"evidence_set_digest": digest})


def _gates(
    before: BundleDocuments, changed: Mapping[PurePosixPath, DocumentModel]
) -> tuple[ApprovalDecision, ...]:
    """The owner-gated transitions this change introduced.

    Derived by asking `required_approval_decisions` what the draft-after owes that the draft-before
    did not. That is the same function `validate_history` consults at promotion, so a command
    cannot report a gate the promotion will not require, or miss one it will.
    """
    after = BundleDocuments(manifest=before.manifest, by_path={**before.by_path, **changed})
    return required_approval_decisions(after, before)


def _write_document(tree: Path, logical: PurePosixPath, model: DocumentModel) -> None:
    """Replace one document atomically, through the writer whose output the loader reads back."""
    _write_documents(tree, {logical: model})


def _write_documents(tree: Path, models: Mapping[PurePosixPath, DocumentModel]) -> None:
    """Replace several documents together: stage every one, then rename them all.

    Writing them one at a time is what a caller reads as a single edit but the filesystem does not.
    `add_evidence` changes the evidence document *and* the manifest digest that describes it, and
    `resolve_conflict` changes two conflict documents; if the second write failed, the first was
    already durable and the command reported `could_not_complete` — telling an operator nothing
    happened while leaving exactly the inconsistency the second write existed to prevent.

    It is not one directory's permissions either. `mkstemp` stages beside each destination, so
    `evidence/records.yaml` needs `evidence/` writable while `manifest.yaml` needs the draft root —
    two independent failure domains, which ENOSPC reaches at different moments.

    Staging everything first moves every failure that *can* be avoided before the first rename, so
    an ordinary refusal — a full disk, an unwritable directory — leaves the tree untouched.

    **`os.replace` can still fail, and it is guarded rather than assumed away.** `mkstemp` needs the
    directory writable; the rename additionally needs the existing target unlinkable, so an
    immutable file (`chflags uchg`, `chattr +i`) separates the two and fails only at the rename. The
    first version of this function left that loop bare, which reproduced the very fault it was
    written to fix — the first document durable, the second stale — and reported it worse, as a raw
    `OSError` the CLI translated into "nothing was written". The window cannot be closed, because a
    rename already performed cannot be undone by a process that may not survive to try; it can only
    be **named**, which is what `PARTIAL_EDIT_APPLIED` is for.

    Not the same case as `rebase-draft`'s two renames, and this docstring used to claim it was:
    those rename *directories* and stage no temporary files, so neither the residue below nor a
    half-applied document set is covered by what §21 accepts there.
    """
    staged: list[tuple[Path, Path, PurePosixPath]] = []
    try:
        for logical, model in models.items():
            target = tree / logical
            try:
                raw = document_bytes(model.model_dump(mode="json"), logical_path=logical)
            except ProfileBundleError as exc:
                raise _refusal(
                    IssueCode.INTERNAL_ERROR,
                    f"the updated {logical} could not be emitted as a bundle document",
                    path=logical.as_posix(),
                ) from exc
            try:
                staged.append((_stage_beside(target, raw), target, logical))
            except OSError as exc:
                raise _refusal(
                    IssueCode.IO_ERROR,
                    f"{logical} could not be rewritten: {io_reason(exc)}",
                    path=logical.as_posix(),
                ) from exc
    except BaseException:
        for temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
        raise

    for position, (temporary, target, logical) in enumerate(staged):
        try:
            os.replace(temporary, target)
        except OSError as exc:
            # From `position` rather than `position + 1`: this rename failed, so its own staged file
            # is still on disk too. Leaving them behind is not a cosmetic leak — an undeclared file
            # under the draft makes every later `validate` and authoring command refuse with
            # `unknown_file` before it reads anything, which would hide the half-applied state below
            # behind a dotfile no diagnostic names.
            for leftover, _, _ in staged[position:]:
                leftover.unlink(missing_ok=True)
            if position == 0:
                raise _refusal(
                    IssueCode.IO_ERROR,
                    f"{logical} could not be rewritten: {io_reason(exc)}",
                    path=logical.as_posix(),
                ) from exc
            applied = [name.as_posix() for _, _, name in staged[:position]]
            raise _Refused(
                (
                    diagnostic(
                        IssueCode.PARTIAL_EDIT_APPLIED,
                        f"{logical} could not be rewritten: {io_reason(exc)}. The change is half "
                        f"applied: {', '.join(applied)} was rewritten and this one was not, so "
                        "the draft is inconsistent until you repair it or discard the draft. "
                        "Retrying the same command will refuse, because the part that landed is "
                        "already there",
                        path=logical.as_posix(),
                        applied=applied,
                    ),
                )
            ) from exc


def _atomic_write(target: Path, raw: bytes) -> None:
    """Stage beside the destination, fsync, rename. Raises `OSError`; the caller names the file.

    One definition for both writers: a document rewritten in place could be truncated by a crash,
    and an approval stamp half-written is one `promote` refuses to parse at exactly the moment the
    owner believes they have approved.
    """
    staged = _stage_beside(target, raw)
    try:
        os.replace(staged, target)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _stage_beside(target: Path, raw: bytes) -> Path:
    """Write `raw` to a fsynced temporary file in `target`'s directory and return it, unrenamed.

    Split out of `_atomic_write` so several documents can reach the point of no return together:
    everything that can fail for an ordinary reason — permissions, a full disk — fails here, while
    the rename that follows is the part the filesystem makes atomic. Raises `OSError`; the caller
    names the file, because the path this failed on is not one a diagnostic may carry.
    """
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=AUTHORING_TEMP_PREFIX)
    staged = Path(temporary)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


# --------------------------------------------------------------------------------------
# The owner's approval of a candidate (§13)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalCandidate:
    """What the owner is being asked to approve, computed but not yet stamped.

    Split from the filing so the command layer can put the controlling-terminal question between
    the two without ever holding the serializer. §13 keeps that question at the command layer and
    everything else here.
    """

    draft_name: str
    candidate_digest: str
    stamp_id: str
    decisions: tuple[ApprovalDecision, ...]


@dataclass(frozen=True)
class FiledApproval:
    """One approval stamp, on disk, under the candidate digest it binds."""

    candidate_digest: str
    stamp_id: str
    decisions: tuple[ApprovalDecision, ...]


def approval_candidate(
    bundle_root: Path, *, draft_name: str
) -> OperationOutcome[ApprovalCandidate]:
    """The candidate digest and owner-gated transitions of `drafts/<name>`. Writes nothing.

    Refuses a draft whose parent has moved. The digest such a draft produces is one no promotion
    will ever look for, so a stamp filed for it would be a file with no drain — and `rebase-draft`,
    which is the way forward, changes the digest anyway.
    """
    try:
        tree = _draft(bundle_root, draft_name)
        documents = _load(tree)
        manifest = documents.manifest
        if not isinstance(manifest, DraftManifest):
            raise _refusal(
                IssueCode.DRAFT_MANIFEST_INVALID,
                f"drafts/{draft_name} holds a revision manifest; only a draft can be approved",
            )
        selection = _selected(bundle_root)
        selected_digest = None if selection is None else selection.bundle_digest
        if manifest.parent_bundle_digest != selected_digest:
            raise _refusal(
                IssueCode.STALE_DRAFT_PARENT,
                f"drafts/{draft_name} was checked out of "
                f"{manifest.parent_bundle_digest or 'no revision'} but this bundle now selects "
                f"{selected_digest or 'no revision'}; rebase-draft moves it onto the current one",
            )
        parent = _parent_documents(selection)
        _no_quarantined_capture(bundle_root, documents)
        digest = candidate_content_digest(
            documents,
            FilesystemBlobReader(blobs_dir(bundle_root)),
            None if parent is None else _envelope(parent),
        )
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)
    except ProfileBundleError as exc:
        return outcome_with(None, parse_error_diagnostics(exc))

    revision = 1 if selection is None else selection.revision + 1
    return OperationOutcome.clean(
        ApprovalCandidate(
            draft_name=draft_name,
            candidate_digest=digest,
            # One stamp per promoted revision (§13), numbered by the revision it will become.
            # `build_approval_stamp` uses the tail as the scope that makes every approval ID unique
            # across the ledger, so this is identity rather than decoration.
            stamp_id=f"approval-stamp.{revision:06d}",
            decisions=required_approval_decisions(documents, parent),
        )
    )


def file_approval_stamp(
    bundle_root: Path, *, candidate: ApprovalCandidate, approved_at: datetime
) -> OperationOutcome[FiledApproval]:
    """Write the owner's stamp for `candidate`, atomically, under its digest.

    `approved_at` is passed in for the same reason promotion's `created_at` is: nothing in this
    package reads a clock. Calling this is the act of approving, so the command layer must have
    asked the owner first — there is no check here that it did, because §13 says the durable
    control is the digest binding and the stamp's reviewability, not a guard this package could
    enforce against a process with write permission.
    """
    stamp = build_approval_stamp(
        stamp_id=candidate.stamp_id,
        candidate_digest=candidate.candidate_digest,
        approved_at=approved_at,
        decisions=candidate.decisions,
    )
    path = approval_path(bundle_root, candidate.candidate_digest)
    logical = PurePosixPath(f"approvals/{path.name}")
    try:
        approvals_dir(bundle_root).mkdir(parents=True, exist_ok=True)
        _atomic_write(path, approval_stamp_bytes(stamp, logical_path=logical))
    except OSError as exc:
        return outcome_with(
            None,
            (
                diagnostic(
                    IssueCode.IO_ERROR,
                    f"{logical} could not be written: {io_reason(exc)}",
                    path=logical.as_posix(),
                ),
            ),
        )
    return OperationOutcome.clean(
        FiledApproval(
            candidate_digest=candidate.candidate_digest,
            stamp_id=stamp.approval_stamp_id,
            decisions=candidate.decisions,
        )
    )


def _selected(bundle_root: Path) -> SelectedRevision | None:
    """The selected revision, or `None` for a bundle that has never been promoted.

    Only "there is no `CURRENT`" becomes `None`; every other selection failure is a bundle whose
    selected revision cannot be resolved, and it carries its own typed code.
    """
    try:
        return read_current_once(bundle_root)
    except SelectionError as exc:
        if exc.code is IssueCode.NO_CURRENT_REVISION:
            return None
        raise _Refused((diagnostic(exc.code, str(exc)),)) from exc


def _parent_documents(selection: SelectedRevision | None) -> BundleDocuments | None:
    if selection is None:
        return None
    try:
        return selected_documents(selection)
    except SelectionError as exc:
        raise _Refused((diagnostic(exc.code, str(exc)),)) from exc


def _envelope(parent: BundleDocuments) -> StableManifestEnvelope:
    manifest = parent.manifest
    # `selected_documents` already refuses a draft manifest in a selected revision, so this is a
    # narrowing rather than a second check.
    if not isinstance(manifest, RevisionManifest):  # pragma: no cover
        raise _refusal(
            IssueCode.DRAFT_MANIFEST_INVALID,
            "the selected revision does not carry a revision manifest",
        )
    return manifest.envelope


def _no_quarantined_capture(bundle_root: Path, documents: BundleDocuments) -> None:
    """A capture the draft names that the store cannot produce intact.

    Approving one would bind the owner's decision to bytes nobody can read back, and the candidate
    digest could not be computed from them anyway — `candidate_content_digest` raises, which is the
    shape §21 has no exit code for. §6's recovery path is checkout, recapture, promote.
    """
    referenced = referenced_blob_digests(documents)
    quarantined = quarantined_blobs(bundle_root, referenced)
    if not quarantined:
        return
    raise _Refused(
        tuple(
            diagnostic(
                IssueCode.CORRUPT_BLOB_QUARANTINE,
                f"the draft cites blob sha256:{declared}, which this bundle cannot produce intact "
                f"({reason.value}); recapture the evidence before approving",
                path=EVIDENCE_PATH.as_posix(),
                # An error here rather than its declared blocker tier: this operation's result is
                # an approval, and an approval of unreadable bytes is not a usable one. `checkout`
                # reports the same condition as a blocker because there the draft is still the
                # thing the owner asked for.
                tier="error",
                blob=declared,
                reason=reason.value,
            )
            for declared, reason in quarantined
        )
    )


def _refusal(
    code: IssueCode,
    message: str,
    *,
    path: str | None = None,
    record_id: str | None = None,
) -> _Refused:
    return _Refused((diagnostic(code, message, path=path, record_id=record_id),))


__all__ = [
    "ApprovalCandidate",
    "ConflictResolution",
    "EvidenceAddition",
    "FactAddition",
    "FactEdit",
    "FiledApproval",
    "add_evidence",
    "add_fact",
    "approval_candidate",
    "edit_fact",
    "file_approval_stamp",
    "resolve_conflict",
]
