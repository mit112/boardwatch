"""The ONE trusted boundary that turns snapshots into hashes.

Task 2 landed the canonical form; task 4 adds the three hashes on top of it. The canonical
form is the shape extract/taxonomy.py:95-103 already uses: sorted keys, compact separators.
Formatting and mapping key order never matter; content always does, including an explicit
null, which must not collide with a missing key.

`build_identity` derives all three hashes from snapshots that ARE their hashed payloads,
byte for byte (D-P2-14), and `verify_identity` refuses any row whose snapshot does not
reproduce its own hash. That closes the hazard in _get_or_create_input, which dedupes on
the caller's fingerprint alone and keeps the FIRST snapshot: two different snapshots can no
longer share a fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.facts import Facts, Policy, facts_payload


def _require_string_keys(payload: object) -> None:
    """Refuse a non-string mapping key anywhere in the payload.

    JSON stringifies keys, so `{1: x}` and `{"1": x}` canonicalise identically and two
    distinct snapshots could share a hash. Every real snapshot key is already a string;
    this fails the ambiguous input closed at the boundary rather than trusting it, the
    same concern the string-vs-number value test pins one level down.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise TypeError(f"canonical form requires string mapping keys, got {key!r}")
            _require_string_keys(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _require_string_keys(item)


def canonical(payload: object) -> str:
    """Sorted-key compact JSON. The single serialisation used for every hash."""
    _require_string_keys(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def digest(payload: object) -> str:
    """SHA-256 hex of the canonical form."""
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


class IdentityMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class InputIdentity:
    """All three hashes plus the exact payloads they were computed from.

    The snapshots ARE the hashed payloads, byte for byte (D-P2-14). Deriving the
    fingerprint from the snapshots also closes the hazard in _get_or_create_input, which
    dedupes on the caller's fingerprint alone and keeps the FIRST snapshot: two different
    snapshots can no longer share a fingerprint.
    """

    profile_hash: str
    profile_snapshot: dict[str, object]
    rules_hash: str
    rules_snapshot: dict[str, object]
    input_fingerprint: str


def build_identity(
    *,
    posting_version_id: int,
    facts: Facts,
    policy: Policy,
    catalog: RulesCatalog,
    declared_fields: Mapping[str, tuple[str, ...]],
) -> InputIdentity:
    materialised = catalog.materialised_policy(policy)
    payload = facts_payload(facts)
    enabled: set[str] = set()
    for family_id, severity in materialised.items():
        if severity != "ignore":
            enabled.update(declared_fields.get(family_id, ()))
    fields: dict[str, object] = {name: payload.get(name) for name in sorted(enabled)}
    # career_field gates field-tier families in the ENGINE, so no resolver declares it and it
    # would never enter `enabled`. Include it UNCONDITIONALLY: over-inclusion only ever adds
    # fingerprint sensitivity (safe), and the CATALOG_REVISION 1->2 bump re-keys everyone once
    # regardless. Omitting it is the stale-verdict class this discipline exists to prevent.
    fields["career_field"] = payload.get("career_field")
    profile_snapshot: dict[str, object] = {"fields": fields}
    # `catalog.source` ("bundled" | "override") is deliberately NOT hashed: catalog_version
    # is a sha256 over the whole parsed document, so identical content already yields an
    # identical version, and hashing provenance alongside it re-keyed the entire corpus the
    # moment a user copied the bundled rules.yaml into their config dir unchanged. A verdict
    # depends on what the rules SAY, never on which file they were read from.
    rules_snapshot: dict[str, object] = {
        "catalog_version": catalog.version,
        "policy": materialised,
    }
    # The per-user near-miss ceilings, DIFFERING-ONLY and only when there are any. Unlike
    # `policy` above this is not materialised in full, and the asymmetry is deliberate:
    # writing every family's ceiling would add the key to every tenant's snapshot and re-key
    # the entire ledger — plus every fixture pinned on today's hashes — for a feature nobody
    # had used. Stating a family's declared ceiling therefore hashes identically to stating
    # nothing (D-P2-2: never two fingerprints for one behaviour), and only a value that
    # actually changes a verdict moves `rules_hash`.
    ceilings = catalog.effective_ceilings(policy)
    differing = {
        family.id: ceilings[family.id]
        for family in catalog.families
        if ceilings[family.id] != family.near_miss_years_ceiling
    }
    if differing:
        rules_snapshot["near_miss_years_ceilings"] = differing
    profile_hash = digest(profile_snapshot)
    rules_hash = digest(rules_snapshot)
    return InputIdentity(
        profile_hash=profile_hash,
        profile_snapshot=profile_snapshot,
        rules_hash=rules_hash,
        rules_snapshot=rules_snapshot,
        input_fingerprint=digest(
            {
                "posting_version_id": posting_version_id,
                "profile_hash": profile_hash,
                "rules_hash": rules_hash,
            }
        ),
    )


def verify_identity(identity: InputIdentity, *, posting_version_id: int) -> None:
    """Recompute all three hashes from the snapshots and refuse any mismatch.

    Called before every ledger write. The four eligibility tables carry BEFORE
    UPDATE/DELETE RAISE(ABORT) triggers, so a bad row can only ever be superseded, never
    corrected. There is no backfill path, which is why this check is not optional.
    """
    if digest(identity.profile_snapshot) != identity.profile_hash:
        raise IdentityMismatchError(
            "profile snapshot does not reproduce its own profile_hash"
        )
    if digest(identity.rules_snapshot) != identity.rules_hash:
        raise IdentityMismatchError("rules snapshot does not reproduce its own rules_hash")
    expected = digest(
        {
            "posting_version_id": posting_version_id,
            "profile_hash": identity.profile_hash,
            "rules_hash": identity.rules_hash,
        }
    )
    if expected != identity.input_fingerprint:
        raise IdentityMismatchError(
            f"input fingerprint does not match posting version {posting_version_id}"
        )
