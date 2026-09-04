"""Typed resolution of one detection against the user's claim-typed facts.

Resolvers self-register by family id at their own definition site, so no module here holds
a collection literal (D-P2-4). The decorator's arguments are a call, not a declaration, and
R9 never descends into a FunctionDef, so the registration is invisible to it.

Each resolver DECLARES its input fields statically (D-P2-23). Declaration is by resolver,
never by whether a prior run emitted support from that field: the alternative meant that an
OR-alternative which found no usable evidence excluded a field from the hash, so a user who
then edited that field never triggered the re-evaluation that would have used it.

The semantics are ported verbatim from the reviewed prototype `.agent/p2-catalog/proto.py`;
where the plan's prose and the prototype disagreed on a case, the prototype won.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from boardwatch.eligibility.catalog import FamilySpec, PatternSpec, RulesCatalog
from boardwatch.eligibility.detect import Detection
from boardwatch.eligibility.facts import ClearanceFact, Facts
from boardwatch.store.eligibility import SupportItem

MET = "met"
UNMET = "unmet"
UNKNOWN = "unknown"

# support_kind has NO CHECK constraint in the schema, so the vocabulary is constrained here
# or it drifts silently (spec trap 5). These resolvers read declared facts only.
DECLARED_FACT = "declared_fact"


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Resolution:
    disposition: str
    rationale: str
    support: tuple[SupportItem, ...] = ()


ResolverFn = Callable[[Detection, Facts, FamilySpec], Resolution]


@dataclass(frozen=True)
class ResolverEntry:
    function: ResolverFn
    inputs: tuple[str, ...]


_REGISTRY: dict[str, ResolverEntry] = {}


def resolver(family_id: str, *, inputs: tuple[str, ...]) -> Callable[[ResolverFn], ResolverFn]:
    def register(function: ResolverFn) -> ResolverFn:
        if family_id in _REGISTRY:
            raise RegistryError(f"two resolvers registered for family {family_id!r}")
        _REGISTRY[family_id] = ResolverEntry(function=function, inputs=inputs)
        return function

    return register


def registry() -> dict[str, ResolverEntry]:
    return dict(_REGISTRY)


def declared_fields() -> dict[str, tuple[str, ...]]:
    return {family_id: entry.inputs for family_id, entry in _REGISTRY.items()}


def verify_registry(
    catalog: RulesCatalog, entries: Mapping[str, ResolverEntry], facts_model: type[Facts]
) -> None:
    """Both directions, plus the catalog-to-model direction.

    A one-directional check is precisely how P0-4 nearly shipped a gate with an
    unregistered rule and passing unit tests. Taking the registry as a parameter keeps
    both directions ordinary unit tests rather than import-time monkeypatching.
    """
    declared = {family.id for family in catalog.families}
    registered = set(entries)
    # `for x in sorted(...): raise` executes at most once and reads as a bug. A walrus plus one
    # raise reports EVERY offender in the message, which is what a user editing an override needs.
    if missing := sorted(declared - registered):
        raise RegistryError(f"catalog families have no resolver: {', '.join(missing)}")
    if extra := sorted(registered - declared):
        raise RegistryError(
            f"resolvers name families the catalog does not declare: {', '.join(extra)}"
        )
    for family in catalog.families:
        if family.fact not in facts_model.model_fields:
            raise RegistryError(
                f"catalog family {family.id!r} declares fact {family.fact!r}, which is not a "
                f"field on {facts_model.__name__}"
            )
        for name in entries[family.id].inputs:
            if name not in facts_model.model_fields:
                raise RegistryError(
                    f"resolver {family.id!r} declares input {name!r}, which is not a field on "
                    f"{facts_model.__name__}"
                )


def resolve(detection: Detection, facts: Facts, family: FamilySpec) -> Resolution:
    entry = _REGISTRY.get(detection.family)
    if entry is None:
        raise RegistryError(f"no resolver for family {detection.family!r}")
    return entry.function(detection, facts, family)


def _fact_support(field: str, value: object) -> tuple[SupportItem, ...]:
    """For a declared fact the quote is the canonical rendering of the VALUE."""
    return (
        SupportItem(
            profile_locator={"field": f"facts.{field}"},
            evidence_quote=str(value),
            support_kind=DECLARED_FACT,
        ),
    )


def _named_jurisdiction(detection: Detection) -> str | None:
    """The jurisdiction this detection's sentence scopes itself to, if it names one.

    Captured from the text ("For roles based in Canada, ...") rather than declared on the
    pattern, so one sponsorship sentence shape covers every jurisdiction. Falls back to the
    pattern's declared jurisdiction when nothing was captured, which keeps a jurisdiction-
    FREE pattern behaving exactly as before.
    """
    pattern = detection.pattern
    surface = detection.values.get("juris_pre") or detection.values.get("juris_post")
    if surface is None:
        return pattern.jurisdiction
    return pattern.jurisdiction_map.get(re.sub(r"[^a-z]", "", surface.casefold()), "other")


@resolver("work_auth", inputs=("work_authorization",))
def _resolve_work_auth(detection: Detection, facts: Facts, family: FamilySpec) -> Resolution:
    wa = facts.work_authorization
    if wa is None:
        return Resolution(UNKNOWN, "no work authorization declared")
    status, juris = wa.status, wa.jurisdiction
    # "other" is a catch-all, not an identity, so other == other must NOT count as equality:
    # that would return `met` for a Brazilian citizen on an Australian posting.
    if status in (None, "prefer_not_to_say") or juris in (None, "unspecified", "other"):
        return Resolution(UNKNOWN, "status or jurisdiction not declared or not identifying")
    pattern = detection.pattern
    support = _fact_support("work_authorization.status", status)
    if pattern.implies in ("sponsorship_available", "sponsorship_unavailable"):
        # Jurisdiction equality is tested on BOTH branches and BEFORE any status test: a
        # statement about another country decides nothing here, in either direction.
        scoped_to = _named_jurisdiction(detection)
        if scoped_to is not None and scoped_to != juris:
            return Resolution(UNKNOWN, f"requirement names {scoped_to}, fact states {juris}")
        if pattern.implies == "sponsorship_available":
            # P2a: the explicit bit is authoritative here too, mirroring the unavailable
            # branch below. Without it, an ead_or_similar holder who declares a need was
            # forced to UNKNOWN on a posting that OFFERS sponsorship -- the one case this
            # rule exists to CLEAR. Bit absent falls back to the status inference unchanged.
            if wa.needs_sponsorship is not None:
                bit_support = _fact_support(
                    "work_authorization.needs_sponsorship", wa.needs_sponsorship
                )
                if wa.needs_sponsorship:
                    return Resolution(MET, "sponsorship is offered", bit_support)
                return Resolution(UNKNOWN, "nothing to decide: no sponsorship needed")
            if status == "needs_sponsorship":
                return Resolution(MET, "sponsorship is offered", support)
            return Resolution(UNKNOWN, "nothing to decide: no sponsorship needed")
        # P2a: the explicit bit, when declared, is authoritative here and bypasses the
        # status-based inference below — it is precisely what lets an ead_or_similar holder
        # be DECIDED instead of forced to UNKNOWN. Scoped to this sponsorship branch only:
        # it is read nowhere else in this function, so it can never satisfy a citizenship or
        # authorization requirement (the CRITICAL SAFETY property in facts.py:3-6).
        if wa.needs_sponsorship is not None:
            bit_support = _fact_support(
                "work_authorization.needs_sponsorship", wa.needs_sponsorship
            )
            if wa.needs_sponsorship:
                return Resolution(
                    UNMET, "sponsorship is required but not offered", bit_support
                )
            return Resolution(MET, "does not need sponsorship", bit_support)
        if status == "needs_sponsorship":
            return Resolution(UNMET, "sponsorship is required but not offered", support)
        # A jurisdiction-free "no sponsorship" restriction that decides UNMET above without
        # knowing the posting's jurisdiction is exactly strong enough to decide the other way
        # for someone who needs none: leaving it unknown rendered `uncertain` for a citizen it
        # cannot possibly block (prototype finding 50). ead_or_similar is the one status that
        # must not be collapsed here: an F-1 OPT holder is precisely who "we do not sponsor"
        # ends the runway for, and the fact model cannot tell them from an asylee who needs
        # nothing, so it is genuinely undecidable — unless the bit above already answered it.
        if status == "ead_or_similar":
            return Resolution(
                UNKNOWN, "authorization is conditional; a sponsorship need cannot be ruled out"
            )
        return Resolution(MET, "no sponsorship needed", support)
    if pattern.jurisdiction != juris:
        return Resolution(UNKNOWN, f"requirement names {pattern.jurisdiction}, fact states {juris}")
    if pattern.implies == "authorization_required":
        if status in ("citizen", "permanent_resident", "ead_or_similar"):
            return Resolution(MET, "authorized", support)
        return Resolution(UNMET, "not authorized", support)
    # Both citizenship branches decide on STATUS alone, and `ead_or_similar` is no exception
    # (D-322). The catalog's five status choices are mutually exclusive (rules.yaml:86), so a
    # declared `ead_or_similar` states the applicant is neither a citizen nor an LPR -- the
    # same ground on which `permanent_resident` already resolves UNMET against a citizenship
    # requirement. Parking it at UNKNOWN was an OVERSHOOT of the D-P2-11 fix: that fix removed
    # a backwards `met` reached through the needs_sponsorship BOOLEAN, and stopping at UNKNOWN
    # was safe but undecided. The two rules abstained on 100% of their rows -- 591 per run --
    # so neither could ever fire, which is a monitoring failure and not conservatism.
    # The bit stays out of both branches, so `met` remains unreachable here for an EAD holder
    # (the CRITICAL SAFETY property in facts.py:3-6). Undeclared still abstains: `None` and
    # `prefer_not_to_say` returned UNKNOWN at the top of this function.
    if pattern.implies == "citizen_or_lpr_required":
        if status in ("citizen", "permanent_resident"):
            return Resolution(MET, "citizen or permanent resident", support)
        return Resolution(UNMET, "neither citizen nor permanent resident", support)
    if pattern.implies == "citizenship_required":
        if status == "citizen":
            return Resolution(MET, "citizen", support)
        return Resolution(UNMET, "not a citizen", support)
    return Resolution(UNKNOWN, "unhandled work_auth requirement")


# Both are a duration scoped to something NARROWER than the whole career -- a skill, or an
# activity -- so both decide only in the direction the total forces. They are two vocabulary
# values rather than one because `engine.evaluate` collects exclusive-group presence
# document-wide, so only `scoped_years_minimum` may sit in that group.
_SCOPED_YEARS = frozenset({"scoped_years_minimum", "activity_years_minimum"})


def _is_near_miss(need: float, family: FamilySpec, pattern: PatternSpec) -> bool:
    """Is this bar low enough that a miss says nothing reliable about the candidate?

    The reject pile is never inspected, so a wrong `unmet` on an early-career bar is
    invisible by construction -- there is no outcome loop that could ever contradict it.
    Against that asymmetry a 2-3 year bar is not evidence of ineligibility: internships,
    co-ops and course projects routinely clear one, and `total_years_experience` is a single
    integer that cannot represent any of them.

    This is applied at the RESOLVER, using the threshold this row captured, and that
    placement is load-bearing. The two catalog-level alternatives are both wrong here:

    * `abstain_by` is DOCUMENT-scoped (`detect._suppressed`, `inside_span=True`), so a
      low-bar regex would also cancel a genuine "10 years required" elsewhere in the same
      posting. The band must be per-ROW, and only the resolver sees a row's own `need`.
    * Flipping the family to `preference` severity cannot express a threshold at all
      (`catalog.py` resolves severity per FAMILY) and would remove the row from
      `engine.blocking()` entirely, so the verdict falls through to `eligible` -- asserting
      the candidate qualifies. `unknown` is caught by `blocking(UNKNOWN)` first and yields
      `uncertain`, so the band can never manufacture an `eligible`.

    Scoped to `required` rows ALONE. The band exists to stop a REJECTION, and only a
    `required` row can produce one (`engine.blocking()` tests `requiredness == "required"`).
    Applied to a `preferred` row it would change nothing about the verdict and would only
    blur the evidence chain -- "you are under a stated preference" is a true and useful row,
    and rewriting it to `unknown` discards a fact for no gain.

    A ceiling of `0` disables the band, which is every family but this one.

    **Two consequences, recorded because neither is visible from the call site.** (1) On the
    scoped/activity branch an in-band bar now returns `UNKNOWN` in BOTH directions, so
    `total_years_experience` stops influencing those rows at all and that value class can no
    longer fire — the shape this module treats as a monitoring failure elsewhere. It is correct
    here (the abstain direction is the safe one) but it means the abstain RATE on
    `experience_years` rises by design; only `fully_abstaining` means a rule is broken.
    (2) `eligibility/extract_llm.py` carries a SECOND years adjudication that this band does not
    cover, so its advisory rows will disagree with the deterministic lane on the same 2-3 year
    bars. That one is advisory-only and capped below `ineligible`, so it cannot re-reject a
    near-miss posting; it is a divergence to know about, not a hole.
    """
    ceiling = family.near_miss_years_ceiling
    return ceiling > 0 and need <= ceiling and pattern.requiredness == "required"


#: Months per year. The one place the conversion is spelled, so a bar stated in months and a
#: bar stated in years are compared on the same axis rather than in two places that can drift.
_MONTHS_PER_YEAR = 12


def _need_in_years(detection: Detection) -> float:
    """The bar this row captured, in years, whatever unit the posting stated it in.

    `years_alt`/`months_alt` are the same magnitude captured by a pattern's SECOND
    alternative: one regex cannot name the same group twice, and a hedge can sit either side
    of the number. The UNIT is the group's identity rather than a separate catalog field, so
    a pattern physically cannot declare one unit and capture the other.

    Months are converted here rather than compared as months, because the near-miss band and
    every existing reason string are stated in years. The conversion is deliberately NOT
    `int(months / 12)`: that reads an 18-month bar as a 12-month one and CLEARS it.
    """
    values = detection.values
    months = values.get("months") or values.get("months_alt")
    if months is not None:
        return int(months) / _MONTHS_PER_YEAR
    return float(values.get("years") or values["years_alt"])


def _bar(need: float) -> str:
    """Render a bar for a reason string: `5`, not `5.0`, and `1.5` for an 18-month bar.

    Keeps every years-stated reason byte-identical to what it was before months existed.
    """
    return str(int(need)) if need == int(need) else f"{need:g}"


@resolver("experience_years", inputs=("total_years_experience",))
def _resolve_experience_years(
    detection: Detection, facts: Facts, family: FamilySpec
) -> Resolution:
    pattern = detection.pattern
    total = facts.total_years_experience
    if total is None:
        return Resolution(UNKNOWN, "total years of experience not declared")
    need = _need_in_years(detection)
    support = _fact_support("total_years_experience", total)
    if pattern.implies in _SCOPED_YEARS:
        # ONE direction is forced without any per-skill data: a duration scoped to a single
        # skill cannot exceed the career it sits inside, so `total < need` is unmet. The
        # other direction is not forced -- `total >= need` says nothing about THIS skill,
        # and a `met` there would be a wrong clear, the worst failure this design can
        # produce -- so it keeps abstaining. Abstaining in BOTH directions is what let a
        # 1-year profile read `eligible` against "Minimum of 12 years of experience in
        # software development"; this is the highest-volume pattern in the family.
        if total < need:
            if _is_near_miss(need, family, pattern):
                return Resolution(
                    UNKNOWN, f"{total} total < {_bar(need)} scoped to a skill, within the "
                    f"{family.near_miss_years_ceiling}-year near-miss band", support,
                )
            return Resolution(UNMET, f"{total} total < {_bar(need)} scoped to a skill", support)
        return Resolution(
            UNKNOWN, "requirement is scoped to a skill; no per-skill durations stored"
        )
    if total >= need:
        return Resolution(MET, f"{total} >= {_bar(need)}", support)
    if _is_near_miss(need, family, pattern):
        return Resolution(
            UNKNOWN, f"{total} < {_bar(need)}, within the "
            f"{family.near_miss_years_ceiling}-year near-miss band", support,
        )
    return Resolution(UNMET, f"{total} < {_bar(need)}", support)


def _incoherent_clearance(clearance: ClearanceFact) -> str | None:
    """Cross-field coherence, checked BEFORE any clearance comparison.

    A fact that cannot describe a real person must fail closed rather than be compared
    against: an ACTIVE clearance at level `none` is not a clearance, and `state: none` with a
    level or an access is a half-filled form. Comparing either produced a wrong `met` on a
    real gate, so a malformed fact abstains.
    """
    state, level = clearance.state, clearance.level
    if state in ("active", "current") and level == "none":
        return "clearance fact is incoherent: active state at level none"
    if state == "none" and (
        level not in (None, "none", "unspecified") or bool(clearance.accesses)
    ):
        return "clearance fact is incoherent: no clearance held but a level or access is named"
    return None


@resolver("clearance", inputs=("security_clearance",))
def _resolve_clearance(detection: Detection, facts: Facts, family: FamilySpec) -> Resolution:
    pattern = detection.pattern
    sc = facts.security_clearance
    if sc is not None:
        bad = _incoherent_clearance(sc)
        if bad is not None:
            return Resolution(UNKNOWN, bad)
    if pattern.implies == "clearable_required":
        # Decided by the declared obtainability bit ALONE. The held clearance answers a
        # different question and reading it here inverts the verdict in both directions, so
        # this branch sits above every level, state and access comparison below and reads
        # nothing but the bit. The coherence check above still applies: a half-filled form
        # is not trusted for `met`, which is the wrong clear this family exists to avoid.
        if sc is None or sc.obtainable is None:
            return Resolution(
                UNKNOWN, "missing_profile_field:security_clearance.obtainable"
            )
        support = _fact_support("security_clearance.obtainable", sc.obtainable)
        if sc.obtainable:
            return Resolution(MET, "can obtain a clearance after hire", support)
        return Resolution(UNMET, "cannot obtain a clearance after hire", support)
    if pattern.implies == "clearance_preferred":
        # Decided from the SAME declared state the levelled rules read. A preference is not
        # undecidable: a profile that declares `state: none` has answered "do you hold a
        # clearance?", and the keystone reserves ABSTAIN for a field that is missing or
        # unresolvable -- not for a resolved field whose answer happens to be `no`. The old
        # unconditional abstain made this rule 100%-abstain for every user who holds nothing,
        # which is a monitoring failure, not conservatism: it is dead weight in the abstain
        # report that hides the rules which genuinely cannot resolve.
        #
        # The row cannot veto under ANY policy, including an all-`blocker` one: the catalog
        # fixes this pattern at `requiredness: preferred`, and engine.evaluate's `blocking()`
        # counts only `required` rows. So the disposition is evidence, never a gate.
        if sc is None or sc.state is None:
            return Resolution(UNKNOWN, "missing_profile_field:security_clearance.state")
        support = _fact_support("security_clearance.level", sc.level)
        if sc.state in ("active", "current"):
            return Resolution(MET, "holds an active clearance", support)
        if sc.state == "none":
            return Resolution(UNMET, "holds no clearance", support)
        return Resolution(UNKNOWN, f"clearance state is {sc.state!r}")
    if sc is None:
        return Resolution(UNKNOWN, "no clearance declared")
    support = _fact_support("security_clearance.level", sc.level)
    state = sc.state
    if state == "none":
        return Resolution(UNMET, "holds no clearance", support)
    if state not in ("active", "current"):
        return Resolution(UNKNOWN, f"clearance state is {state!r}")
    # Accesses are decided FIRST, because an access requirement can stand alone: "a current
    # polygraph is required" names an access and no level, and a poly holder is decidably met.
    held_accesses = set(sc.accesses or ())
    if not set(pattern.required_accesses) <= held_accesses:
        return Resolution(UNKNOWN, "required access not held")
    if pattern.required_level in (None, "unspecified"):
        if pattern.required_accesses:
            return Resolution(MET, "every required access is held", support)
        # No level named: holding ANY active clearance satisfies it, but the HELD fact still
        # has to name a clearance-issuing scheme and a real level.
        if sc.scheme not in ("us_dod", "us_doe"):
            return Resolution(UNKNOWN, f"held scheme {sc.scheme!r} names no clearance")
        if sc.level in (None, "none", "unspecified"):
            return Resolution(UNKNOWN, "held clearance names no level")
        return Resolution(MET, "holds an active clearance and no level was named", support)
    if pattern.required_scheme == "unspecified" or sc.scheme != pattern.required_scheme:
        return Resolution(UNKNOWN, "different or unnamed clearance scheme")
    held_level = sc.level
    if held_level == pattern.required_level:
        return Resolution(MET, "exact level match", support)
    for rel in family.superset_relations:
        if (
            rel["scheme"] == pattern.required_scheme
            and rel["holds_level"] == held_level
            and rel["satisfies_level"] == pattern.required_level
        ):
            return Resolution(MET, "reviewed superset relation", support)
    return Resolution(UNKNOWN, "no reviewed relation between held and required level")


@resolver("contract_not_fte", inputs=("employment_type_preference",))
def _resolve_contract_not_fte(
    detection: Detection, facts: Facts, family: FamilySpec
) -> Resolution:
    """The posting DECLARES an employment type; the fact states which types are acceptable.

    Unlike every other family this one is symmetric: `fte_role` is not the absence of a
    contract declaration but its own detectable claim, so a `contract_only` candidate is
    decidably `unmet` on a permanent FTE posting. Without that arm the family would be a
    one-way filter and `contract_only` would be an unreachable choice.
    """
    stated = facts.employment_type_preference
    if stated in (None, "prefer_not_to_say"):
        return Resolution(UNKNOWN, "no employment-type preference declared")
    support = _fact_support("employment_type_preference", stated)
    if detection.pattern.implies == "fte_role":
        if stated == "contract_only":
            return Resolution(UNMET, "posting is permanent employment, contract only", support)
        return Resolution(MET, "posting is permanent employment", support)
    if stated == "fte_only":
        return Resolution(UNMET, "posting is not permanent employment", support)
    return Resolution(MET, "non-permanent employment is acceptable", support)


#: The twelve month names as ONE STRING, split on use. A dict literal here trips
#: generalization R9 ("non-empty collection default") — correctly: a collection of strings
#: sitting at module scope is exactly the shape a user's own values would take, and the rule
#: cannot tell a calendar from a preference. It is also deliberately NOT `calendar.month_name`,
#: which is locale-sensitive: a JD says "December" whatever locale the process runs under, and
#: a parser that stopped matching under a different `LC_TIME` would fail silently toward a
#: wrong bound.
_MONTH_NAMES = (
    "january february march april may june "
    "july august september october november december"
)

#: The shortest prefix that still names one month. `ju` is ambiguous (june/july), so three is
#: the floor; `sept` and `sep` both resolve, which is what live postings actually write.
_MONTH_PREFIX_MIN = 3


def _month_ordinal(name: str) -> int | None:
    """1-12 for a month name or unambiguous prefix, else None.

    None is a real answer and the caller ABSTAINS on it: a month this cannot read must not
    be resolved to a bound and then decided against.
    """
    token = name.strip().lower().rstrip(".")
    if len(token) < _MONTH_PREFIX_MIN:
        return None
    matches = [
        index
        for index, month in enumerate(_MONTH_NAMES.split(), start=1)
        if month.startswith(token)
    ]
    return matches[0] if len(matches) == 1 else None


def _yyyymm(month: str, year: str) -> int | None:
    """`("December", "2026")` -> 202612, or None when the month cannot be read."""
    ordinal = _month_ordinal(month)
    if ordinal is None:
        return None
    return int(year) * 100 + ordinal


@resolver("student_status", inputs=("education_timing",))
def _resolve_student_status(
    detection: Detection, facts: Facts, family: FamilySpec
) -> Resolution:
    """Student status and graduating cohort, against a posting that gates on either.

    Two members answering different questions, so the branches share no state. Both abstain
    on an absent bit rather than inferring it from the other: a graduate is not necessarily
    outside a window, and someone inside a window is not necessarily still enrolled, so
    either inference produces the backwards `met` the keystone forbids.

    **Nothing here reads the clock.** The window is compared against a DECLARED graduation
    date, never against today, so identical facts give an identical verdict on any day and
    `build_identity` remains a complete description of the inputs.
    """
    timing = facts.education_timing
    if timing is None:
        return Resolution(UNKNOWN, "no education timing declared")
    implies = detection.pattern.implies
    if implies == "current_enrollment_required":
        if timing.currently_enrolled is None:
            return Resolution(UNKNOWN, "enrolment status not declared")
        support = _fact_support("education_timing.currently_enrolled", timing.currently_enrolled)
        if timing.currently_enrolled:
            return Resolution(MET, "currently enrolled", support)
        return Resolution(
            UNMET, "posting requires current enrolment; not currently enrolled", support
        )
    # graduation_window_required
    if timing.graduation_yyyymm is None:
        return Resolution(UNKNOWN, "graduation date not declared")
    low = _yyyymm(detection.values["from_month"], detection.values["from_year"])
    high = _yyyymm(detection.values["to_month"], detection.values["to_year"])
    if low is None or high is None:
        return Resolution(UNKNOWN, "the stated window names a month this catalog cannot read")
    if low > high:
        # A posting that states its window backwards is not a window this can decide against.
        return Resolution(UNKNOWN, "the stated window is inverted")
    support = _fact_support("education_timing.graduation_yyyymm", timing.graduation_yyyymm)
    if low <= timing.graduation_yyyymm <= high:
        return Resolution(
            MET, f"graduation {timing.graduation_yyyymm} within {low}-{high}", support
        )
    return Resolution(
        UNMET, f"graduation {timing.graduation_yyyymm} outside the required {low}-{high}", support
    )


@resolver("internship", inputs=("internship_preference",))
def _resolve_internship(detection: Detection, facts: Facts, family: FamilySpec) -> Resolution:
    """Whether the user wants internships, against a posting that declares itself one.

    There is deliberately no inverse arm here, unlike contract_not_fte: "this posting is not
    an internship" is the unmarked case and needs no pattern, so a user who WANTS an
    internship is simply `met` on the ones detected and silent elsewhere.
    """
    stated = facts.internship_preference
    if stated in (None, "prefer_not_to_say"):
        return Resolution(UNKNOWN, "no internship preference declared")
    support = _fact_support("internship_preference", stated)
    if stated == "exclude":
        return Resolution(UNMET, "posting is an internship, which is excluded", support)
    return Resolution(MET, "internships are acceptable", support)


def _named_study_fields(text: str, family: FamilySpec) -> frozenset[str]:
    """The catalogued fields of study this JD phrase NAMES.

    Empty means the phrase named nothing the catalog knows, which is an out-of-catalog
    failure and never a new bucket: an unrecognised field cannot be compared, so it can
    neither clear nor block.
    """
    return frozenset(
        spec.id
        for spec in family.fields_of_study
        if any(rx.search(text) for rx in spec.surfaces)
    )


def _resolve_field_of_study(
    detection: Detection, facts: Facts, family: FamilySpec
) -> Resolution:
    """The declared field of study against the field the posting names.

    `unmet` is reached in exactly one situation: the posting names a CLOSED set of catalogued
    fields, the declared field is neither in it nor reviewed-related to anything in it, and
    the posting offers no relatedness escape. Every other shape abstains, because a wrong
    `met` here tells a job seeker an unrelated degree qualifies and a wrong `unmet` deletes a
    job they could have had -- and only the first is unrecoverable for them.

    Relatedness needs BOTH halves: the catalog's reviewed partition says two fields are
    interchangeable, and the posting's own escape says it will accept an interchangeable one.
    "Must have a Computer Science degree" means Computer Science, and the catalog has no
    standing to overrule it.
    """
    declared = facts.field_of_study
    if declared is None or declared not in {spec.id for spec in family.fields_of_study}:
        # Absent, or a value this catalog does not declare. Both are unresolvable profile
        # values, so both abstain in both directions (the keystone).
        return Resolution(UNKNOWN, "missing_profile_field:field_of_study")
    text = detection.values.get("study_field") or detection.values.get("study_field_alt")
    if not text:
        return Resolution(UNKNOWN, "the posting's field of study was not captured")
    named = _named_study_fields(text, family)
    if not named:
        return Resolution(UNKNOWN, "the posting names no catalogued field of study")
    support = _fact_support("field_of_study", declared)
    if declared in named:
        return Resolution(MET, f"the posting names {declared}", support)
    escapes = any(rx.search(text) for rx in family.related_field_escapes)
    # The partition is disjoint, so at most one group holds the declared field and `next`
    # needs no tie-break.
    related = next(
        (group for group in family.related_fields_of_study if declared in group), frozenset()
    )
    if related & named:
        if escapes:
            return Resolution(MET, "a reviewed-related field the posting accepts", support)
        return Resolution(
            UNKNOWN, "the posting names a specific field this one is only related to"
        )
    if escapes:
        return Resolution(
            UNKNOWN, "the posting accepts related fields, and no reviewed relation applies"
        )
    return Resolution(UNMET, f"the posting requires {'/'.join(sorted(named))}", support)


@resolver("degree", inputs=("highest_degree", "total_years_experience", "field_of_study"))
def _resolve_degree(detection: Detection, facts: Facts, family: FamilySpec) -> Resolution:
    pattern = detection.pattern
    attained = facts.highest_degree
    if attained in (None, "prefer_not_to_say"):
        return Resolution(UNKNOWN, "highest degree not declared")
    rank = family.ranks.get(str(attained))
    if rank is None:
        return Resolution(UNKNOWN, "attained degree has no rank")
    support = _fact_support("highest_degree", attained)
    # A COORDINATED level list ("A Bachelor's or Master's degree is required.") names two
    # acceptable levels and the posting accepts EITHER, so the bar is the LOWEST it names. The
    # catalog captures the coordinand's RANK in a group named coord_rank<N>_<slot> so the level
    # VOCABULARY stays in rules.yaml.
    bar = pattern.required_rank
    for gname in detection.values:
        if gname.startswith("coord_rank"):
            named = int(gname[len("coord_rank"):].split("_")[0])
            bar = named if bar is None else min(bar, named)
    if pattern.implies == "degree_required_with_field":
        # Rank FIRST, and it stays decidable on its own: no field can rescue a missing degree,
        # so the field comparison only ever runs on a rank that already clears the bar.
        if bar is not None and rank < bar:
            return Resolution(UNMET, f"rank {rank} < {bar}", support)
        return _resolve_field_of_study(detection, facts, family)
    if bar is None:
        if rank == 0:
            return Resolution(UNMET, "no degree completed", support)
        if pattern.implies == "degree_required":
            # A degree is REQUIRED with no level named (any_degree_required): any completed
            # degree satisfies it. It is the only `degree_required` pattern that reaches an
            # unleveled bar, so the MET line below (which needs a numeric bar) never fires
            # for it -- without this it could never resolve MET for a degree-holder.
            return Resolution(MET, "holds a degree; no level required", support)
        return Resolution(UNKNOWN, "requirement names no degree level")
    if rank >= bar:
        return Resolution(MET, f"rank {rank} >= {bar}", support)
    if pattern.implies in ("degree_required_or_equivalent", "degree_preferred_or_equivalent"):
        # A degree OR a domain-scoped experience alternative is not a total-years bar, and the
        # profile stores no per-domain durations, so a scoped escape abstains exactly as
        # scoped_years_minimum does. Detection still fires: the sentence IS a degree
        # requirement, and dropping it would return `eligible` by silence, the worse direction.
        if detection.values.get("equivalent_scope"):
            return Resolution(
                UNKNOWN,
                "the alternative to the degree is scoped to a domain the profile does not record",
            )
        eq = detection.values.get("equivalent_years")
        total = facts.total_years_experience
        if eq and total is not None:
            eq_support = _fact_support("total_years_experience", total)
            if total >= int(eq):
                return Resolution(MET, f"{total} >= {eq} equivalent years", eq_support)
            return Resolution(UNMET, f"{total} < {eq} equivalent years", eq_support)
        return Resolution(UNKNOWN, "alternative to the degree is not measurable")
    return Resolution(UNMET, f"rank {rank} < {bar}", support)
