"""Adding one evidence record and one owner ruling to a draft (design §12, §13, §19).

These are the only two Gate A operations that put new owner content into a draft, and both append
to documents promotion later checks as prefixes. They live here rather than in the command layer
because the command layer is a translation: everything below decides what happens to the bundle,
and nothing here imports `typer`, reads a clock, or prints.

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
from pathlib import Path, PurePosixPath
from typing import Final, Literal, TypeVar

from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.approvals import ApprovalDecision, required_approval_decisions
from boardwatch.profile_bundle.blobs import (
    MAX_CAPTURE_BYTES,
    BlobDigestMismatchError,
    write_blob,
)
from boardwatch.profile_bundle.canonical import EVIDENCE_PATH
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
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    DocumentModel,
    EvidenceRecordsDocument,
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
from boardwatch.profile_bundle.paths import draft_root
from boardwatch.profile_bundle.secret_scan import (
    CURRENT_RULESET_VERSION,
    InvalidUtf8CaptureError,
    scan_capture,
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

_STAGING_PREFIX: Final = ".tmp-authoring-"

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
        _write_document(tree, EVIDENCE_PATH, appended)
    except _Refused as refusal:
        return outcome_with(None, refusal.diagnostics)

    return OperationOutcome.clean(
        EvidenceAddition(
            draft_name=draft_name,
            evidence_id=record.evidence_id,
            capture_kind=record.capture.kind,
            blob_digest=blob_digest,
            blob_outcome=blob_outcome,
            owner_gates=_gates(documents, {EVIDENCE_PATH: appended}),
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
                    (
                        updated if group.conflict_id == target.conflict_id else group
                    ).model_dump(mode="json")
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
        _write_document(tree, CONFLICT_RULINGS_PATH, new_rulings)
        _write_document(tree, CONFLICT_GROUPS_PATH, new_groups)
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


def _parse(
    raw: bytes, adapter: TypeAdapter[_T], *, logical_path: PurePosixPath
) -> _T:
    try:
        payload = load_yaml_bytes(raw, logical_path=logical_path)
    except RestrictedYamlError as exc:
        raise _Refused(
            (diagnostic(exc.code, str(exc), path=logical_path.as_posix()),)
        ) from exc
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
        handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=_STAGING_PREFIX)
        staged = Path(temporary)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, target)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise _refusal(
            IssueCode.IO_ERROR,
            f"{logical} could not be rewritten: {io_reason(exc)}",
            path=logical.as_posix(),
        ) from exc


def _refusal(
    code: IssueCode,
    message: str,
    *,
    path: str | None = None,
    record_id: str | None = None,
) -> _Refused:
    return _Refused((diagnostic(code, message, path=path, record_id=record_id),))


__all__ = [
    "ConflictResolution",
    "EvidenceAddition",
    "add_evidence",
    "resolve_conflict",
]
