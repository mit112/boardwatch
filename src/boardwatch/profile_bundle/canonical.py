"""Canonical identity for the bundle: documents, evidence set, bundle digest, candidate digest.

This is a **new, private-to-this-subsystem** serializer. It deliberately does not reuse
`eligibility/hashing.py`, `extract/taxonomy.py::_version_of`, `eligibility/catalog.py::_version_of`,
or `tailor/persona.py::_version_of`, and it must never be consolidated with them. Those four feed
stored identities and `policy_version`; they serialise with `ensure_ascii=True` and no Unicode
normalisation, so switching any of them to this form would silently re-key every ledger row that
depends on them. A characterization test pins their current non-ASCII output for that reason.

## The algorithm (design §7), implemented literally

1. Every declared document is parsed and validated first. Identity is computed from *validated
   models*, never from raw bytes, which is what makes YAML formatting and mapping-key order
   irrelevant while keeping list order significant.
2. Evidence records are read only from `evidence/records.yaml`. Every blob capture's **raw bytes**
   are hashed, identical digests deduplicated, and the unique digests sorted. Inline captures
   contribute through the normalised evidence document and get no separate leaf.
3. `[normalized_evidence_records, sorted_unique_blob_digests]` is canonicalised and hashed into
   `manifest.evidence_set_digest`. It excludes the manifest, so there is no digest cycle.
4. Every non-manifest document becomes a leaf keyed `doc:<revision-relative-path>`; every unique
   blob becomes a leaf keyed `blob:sha256:<digest>`. A blob's filesystem path is never an input,
   which is what lets a bundle be relocated for encrypted backup without changing identity.
5. `manifest.bundle_digest` is replaced with the empty-string sentinel and the now-final manifest
   becomes the `doc:manifest.yaml` leaf.
6. The sorted list of `[canonical_key, leaf_digest]` pairs is canonicalised and hashed.

Every leaf digest uses the same lowercase `sha256:<64-hex>` textual form. Nothing is ever framed by
concatenating values with a delimiter: a delimiter that can occur inside a value makes two different
inputs share one framing.

## Why floats are refused rather than rounded

`json.dumps(allow_nan=False)` only stops the non-finite cases. `0.1` has no exact binary form, so
two writers could serialise the same number differently and the bundle digest would depend on which
one wrote it. No model has a float field; a float reaching here means one was added, and the right
response is to fail loudly.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from pydantic import BaseModel

from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.models.documents import (
    BundleDocuments,
    DocumentModel,
    EvidenceRecordsDocument,
)
from boardwatch.profile_bundle.models.imports import (
    ExclusionRecord,
    SourceLedgerRecord,
    SourceLedgerSource,
)
from boardwatch.profile_bundle.models.manifests import (
    DraftManifest,
    RevisionManifest,
    StableManifestEnvelope,
)
from boardwatch.profile_bundle.models.policy import SourceSpec

MANIFEST_PATH = PurePosixPath("manifest.yaml")
EVIDENCE_PATH = PurePosixPath("evidence/records.yaml")
APPROVAL_LEDGER_PATH = PurePosixPath("history/approvals.yaml")
CHANGE_LEDGER_PATH = PurePosixPath("history/changes.yaml")

DOCUMENT_KEY_PREFIX = "doc:"
BLOB_KEY_PREFIX = "blob:"


class CanonicalizationError(ProfileBundleError):
    """A value cannot be canonicalised reproducibly."""


class MissingBlobError(ProfileBundleError):
    """A referenced blob's bytes are unavailable, so identity cannot be computed."""

    def __init__(self, bare_digest: str) -> None:
        super().__init__(f"blob {bare_digest} is missing or unreadable")
        self.bare_digest = bare_digest


class BlobReader(Protocol):
    """Supplies the raw bytes behind a blob capture.

    Identity uses the ACTUAL bytes, not the declared digest, so tampering with a blob changes the
    bundle digest rather than merely failing a separate integrity check.
    """

    def read_bytes(self, bare_digest: str) -> bytes: ...


@dataclass(frozen=True)
class FilesystemBlobReader:
    """Reads `blobs/sha256/<digest>` under a bundle root."""

    blobs_root: Path

    def read_bytes(self, bare_digest: str) -> bytes:
        path = self.blobs_root / bare_digest
        try:
            return path.read_bytes()
        except OSError as exc:
            raise MissingBlobError(bare_digest) from exc


@dataclass(frozen=True)
class MappingBlobReader:
    """An in-memory reader. Used by tests and by promotion's from-disk re-read of a temp tree."""

    blobs: Mapping[str, bytes]

    def read_bytes(self, bare_digest: str) -> bytes:
        try:
            return self.blobs[bare_digest]
        except KeyError as exc:
            raise MissingBlobError(bare_digest) from exc


# --------------------------------------------------------------------------------------
# Canonical serialization
# --------------------------------------------------------------------------------------


def _normalize(value: Any) -> Any:
    """Recursively NFC-normalise strings; refuse floats and non-string mapping keys."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalizationError(
            "a float cannot be canonicalised reproducibly; decimals are carried as strings"
        )
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(
                    f"mapping key {key!r} is not a string; JSON stringifies keys, so a non-string "
                    "key would collide with its own string spelling"
                )
            normalized[unicodedata.normalize("NFC", key)] = _normalize(item)
        return normalized
    if isinstance(value, Sequence):
        return [_normalize(item) for item in value]
    raise CanonicalizationError(f"{type(value).__name__} is not a canonicalisable JSON value")


def canonical_json_bytes(value: object) -> bytes:
    """The one serialization every bundle digest is computed over.

    `ensure_ascii=False` keeps non-ASCII characters as themselves, which is why NFC normalisation is
    required: `é` composed and decomposed are different bytes for the same character, and a bundle
    edited on one platform must not change identity when read on another.
    """
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest_of(value: object) -> str:
    """`sha256:<64-hex>` of `value`'s canonical bytes."""
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalized(model: BaseModel) -> Any:
    """A validated model as canonicalisable JSON data."""
    return model.model_dump(mode="json")


def record_digest(record: BaseModel) -> str:
    """A target-record content digest: the record BEFORE any approval metadata is attached (§7).

    Target records never embed their approval IDs, which is what keeps this binding acyclic — the
    stamp points at the record, and the record's digest does not depend on the stamp.
    """
    return digest_of(normalized(record))


# --------------------------------------------------------------------------------------
# Evidence set (§7 steps 2-3)
# --------------------------------------------------------------------------------------


def _evidence_document(documents: BundleDocuments) -> EvidenceRecordsDocument:
    document = documents.by_path.get(EVIDENCE_PATH)
    if not isinstance(document, EvidenceRecordsDocument):
        raise CanonicalizationError(
            f"{EVIDENCE_PATH} is missing or is not an evidence document; the evidence set is read "
            "from exactly one file"
        )
    return document


def referenced_blob_digests(documents: BundleDocuments) -> tuple[str, ...]:
    """The unique declared blob digests the active evidence document names, sorted."""
    document = _evidence_document(documents)
    return tuple(
        sorted(
            {
                record.capture.sha256
                for record in document.evidence
                if record.capture.kind == "blob"
            }
        )
    )


def evidence_set_digest(documents: BundleDocuments, blobs: BlobReader) -> str:
    """Design §7 steps 2-3. Excludes the manifest, so it introduces no digest cycle."""
    document = _evidence_document(documents)
    records = [normalized(record) for record in document.evidence]
    computed = sorted(
        {
            hashlib.sha256(blobs.read_bytes(declared)).hexdigest()
            for declared in referenced_blob_digests(documents)
        }
    )
    return digest_of([records, computed])


# --------------------------------------------------------------------------------------
# Bundle digest (§7 steps 4-6)
# --------------------------------------------------------------------------------------


def _manifest_with(
    manifest: DraftManifest | RevisionManifest, evidence_digest: str
) -> dict[str, Any]:
    """The manifest as it enters its own leaf: real evidence-set digest, empty bundle digest."""
    payload: dict[str, Any] = normalized(manifest)
    payload["evidence_set_digest"] = evidence_digest
    payload["bundle_digest"] = ""
    return payload


def _document_leaves(
    by_path: Mapping[PurePosixPath, DocumentModel],
) -> dict[str, str]:
    return {
        f"{DOCUMENT_KEY_PREFIX}{path.as_posix()}": digest_of(normalized(document))
        for path, document in by_path.items()
        if path != MANIFEST_PATH
    }


def _blob_leaves(documents: BundleDocuments, blobs: BlobReader) -> dict[str, str]:
    """One leaf per UNIQUE blob. Two evidence records naming one blob include it exactly once."""
    leaves: dict[str, str] = {}
    for declared in referenced_blob_digests(documents):
        computed = hashlib.sha256(blobs.read_bytes(declared)).hexdigest()
        leaves[f"{BLOB_KEY_PREFIX}sha256:{computed}"] = f"sha256:{computed}"
    return leaves


def leaf_index(documents: BundleDocuments, blobs: BlobReader) -> dict[str, str]:
    """Every `[canonical_key, leaf_digest]` pair that the bundle digest is computed over."""
    evidence_digest = evidence_set_digest(documents, blobs)
    leaves = _document_leaves(documents.by_path)
    leaves.update(_blob_leaves(documents, blobs))
    leaves[f"{DOCUMENT_KEY_PREFIX}{MANIFEST_PATH.as_posix()}"] = digest_of(
        _manifest_with(documents.manifest, evidence_digest)
    )
    return leaves


def bundle_digest(documents: BundleDocuments, blobs: BlobReader) -> str:
    """Design §7 step 6: hash the sorted list of two-element `[key, digest]` lists."""
    leaves = leaf_index(documents, blobs)
    return digest_of([[key, leaves[key]] for key in sorted(leaves)])


# --------------------------------------------------------------------------------------
# Candidate content digest (§7)
# --------------------------------------------------------------------------------------


def _candidate_manifest(
    manifest: DraftManifest | RevisionManifest,
    parent: StableManifestEnvelope | None,
    evidence_digest: str,
) -> dict[str, Any]:
    """The precisely defined candidate view of the manifest (§7).

    `state` becomes `draft` and `draft_of_revision` the direct parent's revision, so a promoted
    revision and the draft it came from produce the SAME candidate view — which is what makes the
    approval stamp's binding checkable after promotion.
    """
    payload: dict[str, Any] = normalized(manifest)
    payload["state"] = "draft"
    payload["draft_of_revision"] = None if parent is None else parent.revision
    payload["parent_bundle_digest"] = None if parent is None else parent.bundle_digest
    for derived in ("revision", "created_at", "created_by"):
        payload.pop(derived, None)
    for sentinel in (
        "approved_candidate_digest",
        "approval_stamp_id",
        "change_id",
        "bundle_digest",
    ):
        payload[sentinel] = ""
    payload["evidence_set_digest"] = evidence_digest
    return payload


def _candidate_documents(
    by_path: Mapping[PurePosixPath, DocumentModel],
    *,
    change_prefix: int,
) -> dict[str, Any]:
    """Document leaves for the candidate view.

    `history/approvals.yaml` is omitted entirely — the stamp cannot be inside what it approves —
    and `history/changes.yaml` is retained only through the direct parent's prefix, because the
    promotion-derived change record does not exist yet when the owner approves.
    """
    leaves: dict[str, str] = {}
    for path, document in by_path.items():
        if path in (MANIFEST_PATH, APPROVAL_LEDGER_PATH):
            continue
        if path == CHANGE_LEDGER_PATH:
            payload: dict[str, Any] = normalized(document)
            payload["changes"] = payload["changes"][:change_prefix]
            leaves[f"{DOCUMENT_KEY_PREFIX}{path.as_posix()}"] = digest_of(payload)
            continue
        leaves[f"{DOCUMENT_KEY_PREFIX}{path.as_posix()}"] = digest_of(normalized(document))
    return leaves


def _candidate_digest(
    documents: BundleDocuments,
    blobs: BlobReader,
    parent: StableManifestEnvelope | None,
    *,
    change_prefix: int,
) -> str:
    evidence_digest = evidence_set_digest(documents, blobs)
    leaves = _candidate_documents(documents.by_path, change_prefix=change_prefix)
    leaves.update(_blob_leaves(documents, blobs))
    leaves[f"{DOCUMENT_KEY_PREFIX}{MANIFEST_PATH.as_posix()}"] = digest_of(
        _candidate_manifest(documents.manifest, parent, evidence_digest)
    )
    return digest_of([[key, leaves[key]] for key in sorted(leaves)])


def candidate_content_digest(
    documents: BundleDocuments,
    blobs: BlobReader,
    parent: StableManifestEnvelope | None,
) -> str:
    """The digest an owner approves, computed from a DRAFT.

    A draft's change ledger already holds exactly the parent's prefix — `checkout` copies it and
    nothing appends until promotion — so the full ledger is the prefix.
    """
    change_document = documents.by_path.get(CHANGE_LEDGER_PATH)
    prefix = len(normalized(change_document)["changes"]) if change_document is not None else 0
    return _candidate_digest(documents, blobs, parent, change_prefix=prefix)


def candidate_digest_from_revision(
    documents: BundleDocuments,
    blobs: BlobReader,
    parent: StableManifestEnvelope | None,
) -> str:
    """The same digest recomputed from a PROMOTED revision, by §7's inverse normalization.

    Removes exactly one trailing change record — the one the manifest's `change_id` names — rather
    than "the last one", so a manifest pointing at a different entry is a mismatch instead of a
    silently accepted off-by-one. Validation-only: it never rewrites the revision.
    """
    manifest = documents.manifest
    if not isinstance(manifest, RevisionManifest):
        raise CanonicalizationError(
            "the inverse candidate view applies to a promoted revision, not a draft"
        )
    change_document = documents.by_path.get(CHANGE_LEDGER_PATH)
    if change_document is None:
        raise CanonicalizationError(f"{CHANGE_LEDGER_PATH} is missing")
    changes = normalized(change_document)["changes"]
    if not changes or changes[-1]["change_id"] != manifest.change_id:
        raise CanonicalizationError(
            f"the change ledger's final entry does not match manifest change_id "
            f"{manifest.change_id!r}, so the candidate view cannot be recovered"
        )
    return _candidate_digest(documents, blobs, parent, change_prefix=len(changes) - 1)


# --------------------------------------------------------------------------------------
# Joined target digests for the two owner gates that bind two documents (§13)
# --------------------------------------------------------------------------------------


def source_scope_target_digest(source: SourceSpec, ledger: SourceLedgerSource) -> str:
    """`approve_source_scope`'s target: the canonical two-document source-scope view.

    Joined because the approval covers the complete source policy record *and* the ledger's exact
    scope object; approving either half alone would let the other be widened for free.
    """
    if source.source_id != ledger.source_id:
        raise CanonicalizationError(
            f"source-scope view joins mismatched sources: {source.source_id!r} and "
            f"{ledger.source_id!r}"
        )
    return digest_of({"source": normalized(source), "ledger": normalized(ledger)})


def source_exclusion_target_digest(record: SourceLedgerRecord, exclusion: ExclusionRecord) -> str:
    """`approve_source_record_exclusion`'s target: the ledger record joined with its exclusion."""
    if record.source_record_id != exclusion.source_record_id:
        raise CanonicalizationError(
            f"source-exclusion view joins mismatched records: {record.source_record_id!r} and "
            f"{exclusion.source_record_id!r}"
        )
    return digest_of({"record": normalized(record), "exclusion": normalized(exclusion)})
