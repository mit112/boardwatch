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
    # Orthogonal to every field above, the same way `needs_sponsorship` is orthogonal to
    # `status`: what a person HOLDS cannot answer what they can OBTAIN. An F-1 holder holds
    # nothing and can obtain nothing (a US clearance needs citizenship); a Secret holder may
    # still be barred from an upgrade. Inferring either direction from the held clearance
    # inverts both, so obtain-after-hire is its own declared bit and an absent value abstains.
    obtainable: bool | None = None


class EducationTimingFact(BaseModel):
    """Student status and graduating cohort, STRUCTURED for the same reason work auth is:
    the two bits answer different questions and neither can be inferred from the other.

    `currently_enrolled` answers "must be actively enrolled"; `graduation_yyyymm` answers
    "graduation date between December 2026 and May 2027". A graduate is not necessarily
    outside a window, and someone inside a window is not necessarily still enrolled, so
    inferring either from the other produces the backwards `met` this design forbids.

    **NEITHER IS DERIVED FROM THE CURRENT DATE, deliberately.** A resolver that compared a
    stored graduation date against `utcnow()` would return different verdicts for identical
    facts on different days, and `build_identity` hashes the facts, not the clock -- so the
    ledger could not tell a real re-evaluation from the calendar moving. Both bits are
    declared, never computed.

    `graduation_yyyymm` is an INT in `YYYYMM` form (August 2025 is 202508) rather than a date:
    the catalog's field types are bool/int/choice/choice_set and there is no date type, so a
    real date would need a new type in `catalog._FIELD_TYPES` and a new `_coerce` branch --
    shared type-system code -- to buy an ordering that a zero-padded int already gives.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    currently_enrolled: bool | None = None
    graduation_yyyymm: StrictInt | None = None


class Facts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    work_authorization: WorkAuthFact | None = None
    # StrictInt, not int: pydantic coerces a stored boolean True->1 / False->0, which is a
    # GUESS that resolves `unmet` where the fact should be absent (D-P2-15). Strict rejects
    # a bool (and a numeric string), so parse_facts fails it closed to absent.
    total_years_experience: StrictInt | None = None
    security_clearance: ClearanceFact | None = None
    highest_degree: str | None = None
    # The field the HIGHEST degree is in, so it pairs with `highest_degree` above and needs no
    # second rank. `str | None`, validated against the catalog's declared study fields at the
    # resolver (authoritative) and the CLI (friendly), exactly as `highest_degree` is: the
    # vocabulary belongs to the catalog, never to this module (D-P2-4). A value the catalog
    # does not declare is unresolvable, not a new bucket, so the resolver abstains on it.
    field_of_study: str | None = None
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
    # P10. Student status and graduating cohort. Structured because the two bits are
    # orthogonal; see EducationTimingFact. Absent means "not declared" and the resolver
    # abstains, exactly as every other profile-tier fact does.
    education_timing: EducationTimingFact | None = None
    career_field: str | None = None


class Policy(BaseModel):
    """Severity is USER-OWNED (D-P2-1). Only `blocker` can yield `ineligible`.

    An absent family means "use the catalog's declared default"; the full map is
    MATERIALISED from those defaults before hashing (D-P2-2), so an empty map and a
    materialised map cannot be two fingerprints for identical behaviour.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    families: dict[str, PolicyChoice] = Field(default_factory=dict)


class ProfileRowInvalid(ValueError):
    """A stored profile column holds something that is not a valid document.

    NOT the same as absent. An unset column is legitimate — a fresh install, a schema
    upgraded before the facts were entered — and reads as the empty model. A column that
    holds a MALFORMED document is a defect, and failing it closed to the empty model is
    a CLEARING failure, not a conservative one: an empty `Policy` materialises the
    catalog defaults, where only `work_auth` is a `blocker` and the other five families
    fall back to `preference`, a severity that can never yield `ineligible` (D-P2-1). The
    run would then report success while clearing postings the user's own policy rejects.
    """

    def __init__(self, column: str, reason: str) -> None:
        self.column = column
        self.reason = reason
        super().__init__(f"{column}: {reason}")


def _reason(exc: ValidationError) -> str:
    """The pydantic errors as one line, naming every offending key.

    `str(exc)` is multi-line and repeats the model name; the operator needs the key they
    have to edit, which is the `loc`.
    """
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
        for error in exc.errors()
    )


def parse_facts(raw: object) -> Facts:
    """Stored JSON to Facts. Absent reads as absent; malformed is REFUSED."""
    if raw is None:
        return Facts()
    if not isinstance(raw, dict):
        raise ProfileRowInvalid(
            "eligibility_facts_json", f"expected a JSON object, got {type(raw).__name__}"
        )
    try:
        return Facts.model_validate(raw)
    except ValidationError as exc:
        raise ProfileRowInvalid("eligibility_facts_json", _reason(exc)) from exc


def parse_policy(raw: object) -> Policy:
    """Stored JSON to Policy. Absent reads as no overrides; malformed is REFUSED."""
    if raw is None:
        return Policy()
    if not isinstance(raw, dict):
        raise ProfileRowInvalid(
            "eligibility_policy_json", f"expected a JSON object, got {type(raw).__name__}"
        )
    try:
        return Policy.model_validate(raw)
    except ValidationError as exc:
        raise ProfileRowInvalid("eligibility_policy_json", _reason(exc)) from exc


def facts_payload(facts: Facts) -> dict[str, object]:
    """A JSON-ready dict with an explicit null for every absent value.

    Absent values are serialised as null rather than dropped: a vanishing key changes
    the hashed payload, which would make "fact not set" and "fact set then cleared"
    two different fingerprints for the same behaviour.
    """
    return facts.model_dump(mode="json")
