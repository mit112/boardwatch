"""One projected résumé's lineage, in a module neither the tailor nor the bundle may not import.

Deliberately in `boardwatch.core`: `reports.tailor` consumes this type, and `reports.tailor` is
inside the closure `tests/profile_bundle/test_profile_bundle_tailor_isolation.py` walks. A type
defined in `boardwatch.projection` would drag `boardwatch.profile_bundle` into that closure and
break the wall. `core` imports neither, and a test above pins that it stays that way.

Two hashes, not one. `resume_sha256` is over the raw projected bytes; `resume_model_sha256` is over
the parsed model, matching the identity `reports/tailor.py` already uses for a master
(`_sha(master.model_dump_json())`). Byte identity catches a swapped file; model identity catches two
different documents that serialise to the same bytes under a different loader version. Neither
subsumes the other.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ResumeSourceLineage:
    """Where a tailored résumé's master came from, when the master was projected rather than
    authored. Every field is part of either document identity or transformation identity; see the
    design's §4.3 for why transformation identity is not optional."""

    kind: Literal["projection"]
    bundle_revision: str
    bundle_digest: str
    projection_digest: str
    posting_version_id: int
    as_of: str
    scorer_id: str
    taxonomy_version: str
    equivalence_version: str
    persona_registry_version: str
    resume_sha256: str
    resume_model_sha256: str
    manifest_schema: int

    def as_meta(self) -> dict[str, str | int]:
        """Flat, prefixed keys for an artifact's `meta_json`. Prefixed because the row already
        carries unprefixed tailoring keys and a bare `as_of` there would be ambiguous."""
        return {
            f"projection_{field.name}": getattr(self, field.name)
            for field in dataclasses.fields(self)
        }
