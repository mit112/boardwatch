"""Record-level comparison and three-way merge of two parsed logical trees (design §6, §17).

A rebase asks one question — *did the owner and the newly promoted revision change the same
thing?* — and the answer is only useful at record granularity. Two edits to one file are routine:
`skills/inventory.yaml` holds every skill, so a draft that adds one and a revision that renames
another have not collided. Two edits to one **record** are a genuine conflict nobody but the owner
can resolve.

## Identity is reused, never re-derived

Record identity comes from `index.record_id_of` and record content from `canonical.record_digest`.
Neither is restated here. A second notion of "the same record" is exactly the defect class this
subsystem has already paid for: the moment two modules disagree about which field names a record,
one of them reports a clean merge over a collision.

## History is appended to, never merged record by record

The change ledger, the approval ledger and the owner rulings are append-only (§17, §13). A
record-wise merge cannot express that: it would read "the draft no longer lists revision 1's
approval stamp" as a deletion and install a draft whose provenance nothing produced. Those three
sequences are merged as sequences — the selected revision's entries first, ours appended after —
and any draft-side removal or rewrite of an inherited entry is a refusal.

## Merging is field-wise, and refuses rather than guesses

`merge_document` is an ordinary three-way merge over a document's declared fields: a side that did
not change a field yields to the side that did, and a field both sides changed identically is not a
conflict. Only when both sides changed one field *differently* does record identity come into play,
and only for fields that hold addressable records — a tuple of catalog rows or a scalar version
number has no identity to merge by, so it raises. Guessing there would silently drop one operator's
edit; a refusal costs them one command.

The record merge re-checks per record what the caller already checked globally. That looks
redundant and is not: `ExclusionRecord` and `SourceLedgerSource` carry ID fields but are
deliberately *not* in the global index (§18 keys them by the record they describe), so a
both-sides edit to one of them reaches here having passed the global overlap check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from boardwatch.profile_bundle.canonical import record_digest
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.index import Collision, build_index, record_id_of
from boardwatch.profile_bundle.models.documents import BundleDocuments, DocumentModel
from boardwatch.profile_bundle.models.history import (
    ApprovalLedger,
    ChangeLedger,
    ConflictRulings,
)

#: Stands for "this had no value in the base tree". A dedicated sentinel rather than `None`,
#: because `None` is a legitimate value for several fields and a merge that confused the two would
#: treat "absent" as "explicitly null".
NO_BASE: Final = object()

#: `DocumentMergeConflict.field` for a refusal that belongs to the document as a whole rather than
#: to one of its fields. Named so `rebase` can report it without matching on a bare string.
_WHOLE_DOCUMENT: Final = "<document>"

#: The append-only sequences (§17's two history ledgers, §13's owner rulings) and the field that
#: holds each one. Keyed by model class rather than by logical path because the class is what the
#: merge is handed, and `layout.owner_for_path` already makes the class a function of the path — so
#: keying on it cannot disagree with the loader about which document this is.
_APPEND_ONLY_SEQUENCES: Final[Mapping[type[BaseModel], str]] = {
    ChangeLedger: "changes",
    ApprovalLedger: "approvals",
    ConflictRulings: "rulings",
}


@dataclass(frozen=True)
class RecordDiff:
    """Which records changed between two trees, by stable ID."""

    added: frozenset[str]
    removed: frozenset[str]
    changed: frozenset[str]

    @property
    def touched(self) -> frozenset[str]:
        """Every ID whose presence or content differs. The set a rebase intersects."""
        return self.added | self.removed | self.changed


class DocumentMergeConflict(ProfileBundleError):
    """Two independent edits to one document that record identity cannot separate.

    Carries the field it failed on so the refusal can name it. `record_id` is set when the
    collision is a specific record and left `None` when the field has no addressable records at
    all, which is the difference between "you both edited this fact" and "you both bumped this
    catalog version".
    """

    def __init__(self, field: str, message: str, *, record_id: str | None = None) -> None:
        super().__init__(message)
        self.field = field
        self.record_id = record_id


class RecordIdCollision(ProfileBundleError):
    """One record ID claimed by two records in a single tree.

    Typed and raised rather than returned because the alternative is a caller that forgets: the
    index's own answer for a shadowed ID is silently partial, and a rebase that merged over it
    would delete one of the two records with nothing to report.
    """

    def __init__(self, collisions: tuple[Collision, ...]) -> None:
        super().__init__(
            "; ".join(
                f"{collision.record_id} is defined in both {collision.first_path} and "
                f"{collision.second_path}"
                for collision in collisions
            )
        )
        self.collisions = collisions


def record_contents(documents: BundleDocuments) -> Mapping[str, str]:
    """Every addressable record in one tree, as ID -> content digest.

    Exposed because a parentless draft has no base tree to diff against, and its caller needs the
    same ID set that `diff_records` would have called `added` — computed by this function rather
    than by a second walk of the index.

    Raises `RecordIdCollision` when one ID is claimed twice. `build_index` keeps the first record
    and collects the rest, which is right for a validation report and wrong for every question this
    module answers: the shadowed record's content is absent from the mapping, so a change to it is
    invisible to `diff_records`, and a merge would then collapse the two into one.
    """
    index = build_index(documents)
    if index.collisions:
        raise RecordIdCollision(index.collisions)
    return {
        identifier: record_digest(record) for identifier, record in index.records.items()
    }


def diff_records(base: BundleDocuments, changed: BundleDocuments) -> RecordDiff:
    """Which records `changed` adds, removes, or rewrites relative to `base`.

    Content comparison is by canonical record digest, not by YAML bytes: reformatting a document,
    reordering its mapping keys, or re-emitting it through a different writer must not read as an
    edit, or every rebase after a re-serialisation would report a conflict with itself.
    """
    before = record_contents(base)
    after = record_contents(changed)
    return RecordDiff(
        added=frozenset(after) - frozenset(before),
        removed=frozenset(before) - frozenset(after),
        changed=frozenset(
            identifier
            for identifier in frozenset(before) & frozenset(after)
            if before[identifier] != after[identifier]
        ),
    )


def merge_document(
    base: DocumentModel | None, ours: DocumentModel, theirs: DocumentModel
) -> DocumentModel:
    """Three-way merge of one logical document, resolved per record where both sides moved.

    `base` is `None` for a document neither tree inherited — a parentless draft, or a file both
    sides created. Record tuples then merge against an empty base, which is exactly right: every
    record on both sides is an addition, and additions of *different* records do not collide.

    The result is built through `model_validate`, not `model_copy`, so every document-level
    invariant the wrapper declares — unique ordering, claim-type ownership, contacts belonging to
    the one person — is re-checked on the merged value rather than assumed from its parts. Two sides
    that are each valid can merge into a document that is not, so that re-check is a *refusal* the
    caller must handle: it is translated into `DocumentMergeConflict` here, at the raise site, so no
    caller has to recognise a `pydantic.ValidationError` escaping a merge.
    """
    if type(ours) is not type(theirs):
        raise DocumentMergeConflict(
            "<document>",
            f"one path holds a {type(ours).__name__} in the draft and a {type(theirs).__name__} in "
            "the selected revision; a merge would have to invent which one it is",
        )
    append_only = _APPEND_ONLY_SEQUENCES.get(type(theirs))
    merged: dict[str, Any] = {}
    for name in type(theirs).model_fields:
        if name == append_only:
            merged[name] = _merge_append_only(
                name,
                () if base is None else getattr(base, name),
                getattr(ours, name),
                getattr(theirs, name),
            )
            continue
        merged[name] = merge_values(
            name,
            NO_BASE if base is None else getattr(base, name),
            getattr(ours, name),
            getattr(theirs, name),
        )
    try:
        return type(theirs).model_validate(merged)
    except ValidationError as exc:
        raise DocumentMergeConflict(
            _WHOLE_DOCUMENT,
            "both sides are valid on their own but the merged document is not: "
            + "; ".join(error["msg"] for error in exc.errors()),
        ) from exc


def merge_values(name: str, base: Any, ours: Any, theirs: Any) -> Any:
    """One field's three-way resolution, shared by `merge_document` and the rebased manifest.

    Public because a manifest cannot go through `merge_document` — a draft and a revision are
    different models by design (§7) — and a second copy of this rule in the rebase would be a
    second definition of what "both sides changed it" means.
    """
    if ours == theirs:
        return ours
    if base is not NO_BASE and ours == base:
        return theirs
    if base is not NO_BASE and theirs == base:
        return ours
    if _record_ids(ours) is not None and _record_ids(theirs) is not None:
        return _merge_records(name, () if base is NO_BASE else base, ours, theirs)
    raise DocumentMergeConflict(
        name,
        f"{name} was changed differently on both sides and holds no addressable records, so there "
        "is no identity to merge it by",
    )


def _record_ids(value: Any) -> list[str] | None:
    """The stable IDs of a tuple of records, or `None` if `value` is not one.

    A tuple of catalog rows (`PredicateSpec`, `UnitSpec`, …) returns `None` because `record_id_of`
    refuses it — the same refusal the index relies on to keep catalog rows out of the record space.
    """
    if not isinstance(value, tuple):
        return None
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, BaseModel):
            return None
        try:
            identifiers.append(record_id_of(item))
        except TypeError:
            return None
    return identifiers


def _by_id(records: Sequence[BaseModel]) -> dict[str, BaseModel]:
    return {record_id_of(record): record for record in records}


def _merge_append_only(
    name: str,
    base: Sequence[BaseModel],
    ours: Sequence[BaseModel],
    theirs: Sequence[BaseModel],
) -> tuple[BaseModel, ...]:
    """Their sequence, then our additions. Nothing the base already had may move or disappear.

    §17 and §13 make these three documents append-only, and `_merge_records` cannot express that: it
    resolves each record on its own, so "removed by us, untouched by them" reads as a deletion and
    silently drops an approval stamp or a ruling the selected revision carries. History is not a set
    of independently editable records — the selected revision's sequence has to survive as a prefix,
    or the rebased draft claims a provenance nothing produced.

    Rewriting an entry the base already had is refused for the same reason, in the same breath: the
    alternatives are to keep the rewrite (which breaks the prefix) or to take the revision's copy
    (which silently discards an owner edit), and only the owner can choose between them.
    """
    base_by = _by_id(base)
    ours_by = _by_id(ours)
    theirs_by = _by_id(theirs)
    for identifier, inherited in base_by.items():
        our_record = ours_by.get(identifier)
        if our_record is None:
            raise DocumentMergeConflict(
                name,
                f"{identifier} was dropped from an append-only sequence by the draft while the "
                "selected revision still carries it; history is appended to, never rewritten",
                record_id=identifier,
            )
        if our_record != inherited and our_record != theirs_by.get(identifier):
            raise DocumentMergeConflict(
                name,
                f"{identifier} was rewritten by the draft in an append-only sequence; history is "
                "appended to, never rewritten",
                record_id=identifier,
            )
    merged = list(theirs)
    for record in ours:
        identifier = record_id_of(record)
        if identifier in base_by:
            continue
        their_record = theirs_by.get(identifier)
        if their_record is None:
            merged.append(record)
        elif their_record != record:
            raise DocumentMergeConflict(
                name,
                f"{identifier} was appended with different contents by the draft and by the "
                "selected revision",
                record_id=identifier,
            )
    return tuple(merged)


def _merge_records(
    name: str,
    base: Sequence[BaseModel],
    ours: Sequence[BaseModel],
    theirs: Sequence[BaseModel],
) -> tuple[BaseModel, ...]:
    """Apply our record-level delta onto their sequence, keeping their order.

    Their order is the spine because they are the newly selected revision and the draft is being
    moved onto it; our additions land after it, in our own order. Order is significant to the
    bundle digest, so it has to be decided once and deterministically rather than by whichever
    dict happened to be iterated first.
    """
    base_by = _by_id(base)
    ours_by = _by_id(ours)
    theirs_by = _by_id(theirs)
    merged: list[BaseModel] = []

    for record in theirs:
        identifier = record_id_of(record)
        base_record = base_by.get(identifier)
        our_record = ours_by.get(identifier)
        if our_record is None:
            if identifier in base_by:
                if record != base_record:
                    raise DocumentMergeConflict(
                        name,
                        f"{identifier} was removed by the draft and changed by the selected "
                        "revision",
                        record_id=identifier,
                    )
                continue  # removed by us, untouched by them
            merged.append(record)
            continue
        ours_moved = our_record != base_record
        theirs_moved = record != base_record
        if ours_moved and theirs_moved and our_record != record:
            raise DocumentMergeConflict(
                name,
                f"{identifier} was changed by the draft and by the selected revision",
                record_id=identifier,
            )
        merged.append(our_record if ours_moved else record)

    merged.extend(
        record
        for record in ours
        if record_id_of(record) not in base_by and record_id_of(record) not in theirs_by
    )
    return tuple(merged)


__all__ = [
    "NO_BASE",
    "DocumentMergeConflict",
    "RecordDiff",
    "RecordIdCollision",
    "diff_records",
    "merge_document",
    "merge_values",
    "record_contents",
]
