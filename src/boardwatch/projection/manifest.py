"""`projection-manifest.json` — the sidecar carrying one projected résumé's bundle and selection
lineage.

Revision 1 put provenance in YAML comments; `load_resume` (`tailor/load.py`) calls
`yaml.safe_load`, which discards comments, so that provenance never reached the ledger
(`serialize.py`'s own docstring makes the identical point about `Resume` itself).

v2 adds **transformation identity** beside the bundle lineage v1 already carried. Which bundle
produced a résumé is not which rules produced it: `select` scores through the taxonomy and the
equivalence table and persona application reads the registry, so two runs that disagree because
the taxonomy moved are indistinguishable from each other under v1's fields alone. v2 records the
scorer id, those three versions, the run's `as_of`, the posting VERSION selection ran against,
and both hashes of the résumé bytes that were written beside this file.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from boardwatch.profile_bundle.models.base import DecimalString

#: Bumped whenever a field is added, removed, or its meaning changes. v2 added the eight
#: transformation- and document-identity fields (see the module docstring).
MANIFEST_SCHEMA_VERSION = 2


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
    #: each rendered bullet's source id -> the bullet_id it produced. `pool._build_entry` sets
    #: `bullet_id=claim_id` for a `claims`-derived bullet and `bullet_id=fact.fact_id` for a
    #: `bullet_predicates`-derived one (D-188), so v1's pairs are the identity map; carried
    #: explicitly anyway so a future divergence between the two has somewhere to be recorded rather
    #: than assumed away.
    claim_to_bullet: tuple[tuple[str, str], ...]
    #: The posting VERSION selection actually ran against, not merely the posting. `run_tailor`
    #: re-reads the current version independently, so without this a résumé selected against
    #: version A can be tailored against version B with nothing recording the divergence.
    posting_version_id: int
    #: -- transformation identity: which RULES produced this résumé -----------------------
    #: The run's `as_of`, ISO-formatted. Date effectiveness decides which facts are eligible at
    #: all, so two runs a day apart over an unchanged bundle can legitimately differ.
    as_of: str
    scorer_id: str
    taxonomy_version: str
    equivalence_version: str
    persona_registry_version: str
    #: -- document identity: two hashes, never one -----------------------------------------
    #: Over the raw bytes written to `resume.projected.yaml`; catches a swapped file.
    resume_sha256: str
    #: Over the parsed model (`Resume.model_dump_json()`), the identity `reports/tailor.py`
    #: already uses for a master; catches two documents that serialise alike under a different
    #: loader version. Neither hash subsumes the other — `core/lineage.py` states the same.
    resume_model_sha256: str


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
