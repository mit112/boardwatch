"""The private root sidecar `local-sources.yaml` (design §6).

This file maps logical source IDs to machine-local absolute roots so an owner can deliberately
reopen an original document. It is the one place in the bundle where an absolute path is legitimate,
and it earns that by being outside everything:

- it lives at the bundle ROOT, never inside a revision;
- it is excluded from the revision digest, the evidence-set digest, and the candidate digest;
- it is never exported, and `checkout` never copies it into a draft;
- it carries no professional facts at all.

The shape enforces the last point: a `RootModel[dict[SourceId, AbsolutePath]]` can only ever hold
source-ID keys mapped to path strings, so there is nowhere for a fact, a contact, or a claim to be
smuggled in. That is also why changing this file cannot change any bundle identity — a test proves
it, because the alternative is a private machine path leaking into a content digest that gets
compared across machines.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, RootModel, StringConstraints

from boardwatch.profile_bundle.models.base import SourceId

#: A POSIX absolute path, or a Windows drive-qualified one. Relative roots are refused: a relative
#: root would resolve against whatever the process's working directory happened to be.
AbsolutePath = Annotated[
    str, StringConstraints(pattern=r"^(?:/[^\x00]*|[A-Za-z]:[\\/][^\x00]*)$", min_length=2)
]


class LocalSourcesSidecar(RootModel[dict[SourceId, AbsolutePath]]):
    """Logical source ID -> machine-local absolute root. Nothing else is representable."""

    model_config = ConfigDict(frozen=True)

    @property
    def roots(self) -> dict[str, str]:
        return dict(self.root)

    def resolved_source_ids(self) -> frozenset[str]:
        return frozenset(self.root)


#: The sidecar an `init` writes: present, parseable, and empty. Writing it empty rather than
#: omitting it means "no local originals are mapped" is a state the owner can see, and `inventory`
#: can report a parse failure instead of silently treating an absent file as an empty one.
EMPTY_SIDECAR: LocalSourcesSidecar = LocalSourcesSidecar({})
