"""The owner-initiated writes that are not promotion (design §12, §13, §19).

Three operations: capture an evidence record, rule on a conflict, and file the owner's approval of
a candidate. They live here rather than in the command layer because the command layer is a
translation: everything below decides what happens to the bundle, and nothing here imports
`typer`, reads a clock, or prints.

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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, Literal, TypeVar

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
from boardwatch.profile_bundle.canonical import (
    EVIDENCE_PATH,
    MANIFEST_PATH,
    FilesystemBlobReader,
    MissingBlobError,
    candidate_content_digest,
    evidence_set_digest,
    referenced_blob_digests,
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
from boardwatch.profile_bundle.index import record_id_of
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    DocumentModel,
    EvidenceRecordsDocument,
    FactBearingDocument,
    MetricRecordsDocument,
)
from boardwatch.profile_bundle.models.evidence import AnyEvidence, EvidenceRecord
from boardwatch.profile_bundle.models.history import (
    ConflictGroups,
    ConflictRecord,
    ConflictRulings,
    ConflictState,
    RulingDecision,
    RulingRecord,
)
from boardwatch.profile_bundle.models.manifests import (
    BundleManifest,
    DraftManifest,
    RevisionManifest,
    StableManifestEnvelope,
)
from boardwatch.profile_bundle.paths import (
    approval_path,
    approvals_dir,
    blobs_dir,
    draft_root,
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

#: The names the operator's two input files are reported under. They are not bundle documents, so
#: they have no path inside the tree — and naming the operator's own filesystem path in a
#: diagnostic would put an absolute path into JSON they may paste elsewhere.
EVIDENCE_INPUT: Final = PurePosixPath("--evidence-file")
RULING_INPUT: Final = PurePosixPath("--ruling-file")

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


@dataclass(frozen=True)
class ConflictResolution:
    """What `resolve-conflict` did."""

    draft_name: str
    ruling_id: str
    conflict_id: str
    conflict_state: ConflictState
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


# --------------------------------------------------------------------------------------
# Steps. Each returns its value or raises `_Refused`.
# --------------------------------------------------------------------------------------


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
    "FiledApproval",
    "add_evidence",
    "approval_candidate",
    "file_approval_stamp",
    "resolve_conflict",
]
