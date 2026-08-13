"""`projection-manifest.json` — the sidecar carrying one projected résumé's bundle and selection
lineage.

Revision 1 put provenance in YAML comments; `load_resume` (`tailor/load.py`) calls
`yaml.safe_load`, which discards comments, so that provenance never reached the ledger
(`serialize.py`'s own docstring makes the identical point about `Resume` itself). **v1 does not
close stale lineage** — `tailor run` never reads this file, so the sidecar makes staleness
*inspectable*, not *detected*. Slice P5 owns the real fix.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from boardwatch.profile_bundle.models.base import DecimalString

#: Bumped whenever a field is added, removed, or its meaning changes. Nothing reads this yet — v1
#: does not close stale lineage (see the module docstring) — it exists so a future reader can.
MANIFEST_SCHEMA_VERSION = 1


class ProjectionManifest(BaseModel):
    """One projection run's lineage: which bundle, which declaration, which entries survived
    selection, which score each candidate got, and which claim produced which bullet.

    `posting_id` is `None` for a JD-blind Stage 1 manifest (there is no posting yet, so no
    scores either); Stage 2 fills both in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_schema: int
    bundle_revision: str
    bundle_digest: str
    projection_digest: str
    posting_id: int | None
    jd_skills: tuple[str, ...]
    pinned_entry_ids: tuple[str, ...]
    selected_entry_ids: tuple[str, ...]
    #: entry/entity id -> its scorer output, as a `DecimalString` — never a float, for the reason
    #: `declaration.py` and `scoring.py` already state: `profile_bundle.canonical._normalize`
    #: raises on any float, because a score that lands in a lineage artifact must never depend on
    #: floating-point representation.
    scores: tuple[tuple[str, DecimalString], ...]
    #: claim_id -> the bullet_id it produced. `pool._build_entry` currently sets
    #: `bullet_id=claim_id`, so v1's pairs are the identity map; carried explicitly anyway so a
    #: future divergence between the two has somewhere to be recorded rather than assumed away.
    claim_to_bullet: tuple[tuple[str, str], ...]


def manifest_bytes(manifest: ProjectionManifest) -> bytes:
    """The sidecar's own bytes: `projection-manifest.json`, with deterministic key order.

    Plain `json.dumps(..., sort_keys=True)` — deliberately NOT
    `profile_bundle.yaml_writer.document_bytes` (that emits YAML; this sidecar is JSON, per Task
    19's own filename) and NOT `profile_bundle.canonical.canonical_json_bytes` (importing
    `profile_bundle.canonical` from anywhere under `projection/` is walled off repo-wide, with no
    allowlist, because that module's bytes are the bundle's own identity function). Every field on
    this model is already an `int`, a `str`, `str | None`, or a tuple built from those, so
    `model_dump(mode="json")` cannot produce a float, a non-string key, or anything else
    `canonical_json_bytes`'s own refusals exist to catch — reimplementing that refusal here would
    be dead code, the same conclusion `serialize.py` reaches for `Resume`.
    """
    payload = manifest.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


__all__ = ["MANIFEST_SCHEMA_VERSION", "ProjectionManifest", "manifest_bytes"]
