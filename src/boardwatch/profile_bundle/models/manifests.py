"""Draft and revision manifests (design §7, §19).

A draft and a promoted revision are *different shapes*, discriminated on `state`, not one shape with
optional fields. That matters because the promotion-derived fields — `revision`, `created_at`,
`created_by` — are exactly the ones an agent must not be able to author. If they were optional on
one model, a draft could arrive carrying `revision: 7` and promotion would have to remember to
ignore it. Here it cannot parse.

The draft's sentinels (`bundle_digest: ""`, `approved_candidate_digest: ""`,
`approval_stamp_id: ""`, `change_id: ""`) are `Literal[""]` for the same reason: an empty string
is a *declared* "not yet",
and a draft that guessed a digest would fail to parse rather than fail to match later.

`StableManifestEnvelope` is the small subset ancestor traversal reads. §7 is explicit that walking
history "reads a stable manifest envelope" and does not reparse ancestor domain models or recompute
their bytes, so the envelope exists as its own type to make that boundary hard to cross by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from boardwatch.profile_bundle.models.base import (
    ApprovalStampId,
    ChangeId,
    ProfileId,
    Sha256Digest,
    StrictModel,
    UtcTimestamp,
)
from boardwatch.profile_bundle.models.history import Actor

#: The reserved sentinel a draft carries where a promoted revision carries a real value.
UNSET_SENTINEL = ""


class _ManifestBase(StrictModel):
    """The catalog-version envelope both states share.

    Every catalog gets its own version because they move independently: adding a skill category must
    change the bundle digest without implying that the predicate contracts changed.
    """

    schema_version: PositiveInt
    profile_id: ProfileId
    evidence_set_digest: Sha256Digest
    predicate_catalog_version: PositiveInt
    unit_catalog_version: PositiveInt
    relation_catalog_version: PositiveInt
    skill_category_catalog_version: PositiveInt
    assertion_tag_catalog_version: PositiveInt
    secret_scan_ruleset_version: PositiveInt


class DraftManifest(_ManifestBase):
    """A writable draft. Has no `revision`, `created_at`, or `created_by` — promotion derives them.

    `draft_of_revision` and `parent_bundle_digest` are null together for the revision-1 draft `init`
    creates, and non-null together for every `checkout`. A half-set pair would make "is this
    parentless?" answerable two ways.
    """

    state: Literal["draft"]
    draft_of_revision: NonNegativeInt | None
    parent_bundle_digest: Sha256Digest | None
    bundle_digest: Literal[""]
    approved_candidate_digest: Literal[""]
    approval_stamp_id: Literal[""]
    change_id: Literal[""]

    @model_validator(mode="after")
    def _parentage_is_all_or_nothing(self) -> DraftManifest:
        if (self.draft_of_revision is None) != (self.parent_bundle_digest is None):
            raise ValueError(
                "draft_of_revision and parent_bundle_digest must both be null (a revision-1 draft) "
                "or both be set (a checkout)"
            )
        if self.draft_of_revision is not None and self.draft_of_revision < 1:
            raise ValueError("draft_of_revision names an existing revision, so it is at least 1")
        return self


class RevisionManifest(_ManifestBase):
    """One immutable promoted revision (§7).

    `parent_bundle_digest` is required after revision 1, which is what makes local history explicit
    without depending on Git. Revision directories are named by `bundle_digest`; the revision NUMBER
    never appears in a directory name, so two torn attempts at the same content cannot reserve two
    numbered slots.
    """

    state: Literal["revision"]
    revision: PositiveInt
    parent_bundle_digest: Sha256Digest | None
    bundle_digest: Sha256Digest
    created_at: UtcTimestamp
    created_by: Actor
    change_id: ChangeId
    approved_candidate_digest: Sha256Digest
    approval_stamp_id: ApprovalStampId

    @model_validator(mode="after")
    def _only_revision_one_is_parentless(self) -> RevisionManifest:
        if self.revision == 1 and self.parent_bundle_digest is not None:
            raise ValueError("revision 1 cannot name a parent bundle digest")
        if self.revision > 1 and self.parent_bundle_digest is None:
            raise ValueError(
                f"revision {self.revision} must name its parent bundle digest; without it local "
                "history is unverifiable"
            )
        return self

    @property
    def envelope(self) -> StableManifestEnvelope:
        return StableManifestEnvelope(
            schema_version=self.schema_version,
            profile_id=self.profile_id,
            revision=self.revision,
            parent_bundle_digest=self.parent_bundle_digest,
            bundle_digest=self.bundle_digest,
        )


BundleManifest = Annotated[DraftManifest | RevisionManifest, Field(discriminator="state")]


@dataclass(frozen=True)
class StableManifestEnvelope:
    """The only part of an ancestor manifest that history traversal reads (§7).

    Deliberately not a Pydantic model: it is never authored, only projected from an
    already-validated manifest, and giving it a parser would invite someone to build an envelope
    from raw YAML and skip the manifest's own checks.
    """

    schema_version: int
    profile_id: str
    revision: int
    parent_bundle_digest: str | None
    bundle_digest: str
