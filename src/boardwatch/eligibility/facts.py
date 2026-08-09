"""Typed boundary models for the user's eligibility facts and severity policy.

Facts are CLAIM-TYPED, never bare booleans (D-P2-11): a boolean
`needs_sponsorship=False` wrongly satisfies "US citizens or green card holders only"
for an EAD holder, and a boolean `has_clearance=True` wrongly satisfies "active
TS/SCI". Both are backwards `met` verdicts, the worst failure this design can produce.

Every value is optional and every parse failure yields the absent value rather than a
guess, so a resolver can only ever see a value that means what it says (D-P2-15). The
vocabularies themselves live in the catalog, not here (D-P2-4); this module owns TYPES.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

PolicyChoice = Literal["blocker", "preference", "ignore"]


class WorkAuthFact(BaseModel):
    """Work authorization is STRUCTURED, and `met` requires jurisdiction EQUALITY
    (D-P2-19). A scalar status was jurisdiction-blind: a Canadian citizen storing
    `citizen` satisfied "must be a US citizen"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str | None = None
    jurisdiction: str | None = None
    # P2a. Orthogonal to `status`: `ead_or_similar` alone cannot say whether sponsorship is
    # needed, which forced that status to UNKNOWN against a sponsorship restriction (D-P2-11
    # applies here too — the bit ONLY ever answers the sponsorship question, never
    # citizenship). Absent means "not declared"; the resolver then falls back to the
    # status-based inference exactly as before this field existed.
    needs_sponsorship: bool | None = None


class ClearanceFact(BaseModel):
    """Clearance has NO total order (D-P2-20). The parts are recorded separately so a
    resolver can require an exact match or a catalog-declared reviewed superset, and
    can never rank an active TS above a TS/SCI requirement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme: str | None = None
    level: str | None = None
    state: str | None = None
    accesses: tuple[str, ...] = ()


class Facts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    work_authorization: WorkAuthFact | None = None
    # StrictInt, not int: pydantic coerces a stored boolean True->1 / False->0, which is a
    # GUESS that resolves `unmet` where the fact should be absent (D-P2-15). Strict rejects
    # a bool (and a numeric string), so parse_facts fails it closed to absent.
    total_years_experience: StrictInt | None = None
    security_clearance: ClearanceFact | None = None
    highest_degree: str | None = None
    # P9. Both are PREFERENCES over the posting's employment type, not credentials, so a
    # missing value means "not stated" and abstains rather than defaulting to a stance. Kept
    # as `str | None` and validated against the catalog's declared choices at the CLI
    # boundary (eligibility_cmd._coerce), the same way `highest_degree` is: the choice
    # vocabulary belongs to the catalog, never to this module (D-P2-4).
    employment_type_preference: str | None = None
    internship_preference: str | None = None
    # P2 item 4. The profile's career field, gating field-tier families in the engine (never a
    # resolver input, so it is hashed EXPLICITLY in build_identity, not via declared_fields).
    # Validated against catalog.career_fields at the engine (authoritative) and the CLI
    # (friendly), never in this type — the vocabulary belongs to the catalog (D-P2-4).
    career_field: str | None = None


class Policy(BaseModel):
    """Severity is USER-OWNED (D-P2-1). Only `blocker` can yield `ineligible`.

    An absent family means "use the catalog's declared default"; the full map is
    MATERIALISED from those defaults before hashing (D-P2-2), so an empty map and a
    materialised map cannot be two fingerprints for identical behaviour.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    families: dict[str, PolicyChoice] = Field(default_factory=dict)


def parse_facts(raw: object) -> Facts:
    """Stored JSON to Facts, failing closed to absent on anything unexpected."""
    if not isinstance(raw, dict):
        return Facts()
    try:
        return Facts.model_validate(raw)
    except ValidationError:
        return Facts()


def parse_policy(raw: object) -> Policy:
    """Stored JSON to Policy, failing closed to no overrides on anything unexpected."""
    if not isinstance(raw, dict):
        return Policy()
    try:
        return Policy.model_validate(raw)
    except ValidationError:
        return Policy()


def facts_payload(facts: Facts) -> dict[str, object]:
    """A JSON-ready dict with an explicit null for every absent value.

    Absent values are serialised as null rather than dropped: a vanishing key changes
    the hashed payload, which would make "fact not set" and "fact set then cleared"
    two different fingerprints for the same behaviour.
    """
    return facts.model_dump(mode="json")
