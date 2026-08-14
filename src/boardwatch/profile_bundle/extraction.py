"""Deterministic extraction: read enumerated records through the declarative mapping and propose
candidates (Gate B, Slice B).

The mapping lives in the bundle as data (D-172, D-174); this module is the interpreter that reads
it. It imports no `boardwatch.store` module and holds no I/O — it turns records plus a mapping into
`ProposedCandidate`s (which the existing `build_candidate_package` (`imports.py`) then types and
identifies) plus per-record `ExtractionFailure`s (the durable drain, §6.3a).

The interface is the closed operation set O1–O6 of design §6.2a. Two rule shapes draw on it:

* a **literal rule** (`ExtractionRule`) carries its own predicate/value/display (O1, O2a, O3a, O4,
  O5) — the whole of `header/1` and the skill items;
* a **model-routed rule** (`ModelRoutedRule`) carries `kind_source` + `emits_group` and resolves its
  predicate and value through the one `entry_kind_model` object (O2b), so metadata and bullets route
  through exactly one place and a `project` entry can never land an `employment.*` predicate.

`import boardwatch.tailor.*` is deliberately absent: entry metadata reaches this layer already
dumped to a plain `dict` by the enumerator, so the interpreter reads fields off `atomic_value`
rather than the `tailor` models, which keeps it inside the profile_bundle import wall.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from boardwatch.profile_bundle.enumerators import EnumeratedSourceRecord
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.imports import ProposedCandidate
from boardwatch.profile_bundle.models.facts import (
    DateRangeValue,
    FactValue,
    SkillRefValue,
    StringValue,
    YearMonthValue,
)
from boardwatch.profile_bundle.models.policy import PredicateCatalog

# --- the closed drain reasons (§6.3a). Kept as literals here so the interpreter needs no import of
# the report document model; the CLI maps these onto `ExtractionReportReason`, whose values match. -
NO_MAPPING_FOR_LOCATOR = "no_mapping_for_locator"
UNSUPPORTED_ENTRY_KIND = "unsupported_entry_kind"
SPAN_NOT_GROUNDED = "span_not_grounded"
VALUE_NOT_TYPEABLE = "value_not_typeable"
FREE_TEXT_DEFERRED = "free_text_deferred"
NO_PREDICATE_EXISTS = "no_predicate_exists"

#: The closed drain reasons as a set, so a deferral's declared reason is checked against the
#: emitter's own constants rather than a restatement of them.
DRAIN_REASONS: frozenset[str] = frozenset(
    {
        NO_MAPPING_FOR_LOCATOR,
        UNSUPPORTED_ENTRY_KIND,
        SPAN_NOT_GROUNDED,
        VALUE_NOT_TYPEABLE,
        FREE_TEXT_DEFERRED,
        NO_PREDICATE_EXISTS,
    }
)

#: The closed vocabularies a mapping's non-predicate fields draw on. They are the interpreter's own
#: `_build_value` / `_resolve_kind` / slot-routing branches, so a mapping naming anything outside
#: them is refused up front instead of reaching a `NotImplementedError` or a bare `KeyError`.
VALUE_TYPES: frozenset[str] = frozenset({"string", "skill_ref", "year_month", "date_range"})
SLOT_GROUPS: frozenset[str] = frozenset({"metadata", "contribution"})
KIND_SOURCES: frozenset[str] = frozenset({"self", "condition"})
VALUE_SELECTORS: frozenset[str] = frozenset({"range_start", "range_end"})


class ExtractionMappingError(Exception):
    """A mapping that cannot be a legal member of its adapter/catalog — a build/validation error,
    never a per-record runtime surprise (§6.2a "catalog-checked, once, before extraction").

    Carries the `IssueCode` its violation *is*, typed at the raise site, so a caller renders a
    diagnostic without classifying the message text.
    """

    def __init__(self, message: str, *, code: IssueCode) -> None:
        super().__init__(message)
        self.code = code


class _ValueNotTypeable(Exception):
    """The named field will not construct the declared value kind — a per-record
    `value_not_typeable` drain reason, never a raised failure that aborts the run."""


@dataclass(frozen=True)
class ExtractionRule:
    """One literal mapping rule (O1 + O2a + O3a + O4 + O5, §6.2a).

    `value_from` / `display_from` name a field of the record's `atomic_value`, or `.` for a scalar
    record. `predicate` is a catalog id supplied directly — the whole predicate, no model routing.
    """

    locator_pattern: str
    predicate: str
    value_from: str
    value_type: str
    display_from: str


@dataclass(frozen=True)
class Slot:
    """One fully specified emission of an entry-kind model (§6.2a).

    `value_from` is a field name, `.` for a scalar, or a **priority list** (O3c coalesce, first
    non-null wins). `value_selector` (O3b) selects a component of a parsed range. `display_from`
    names the field the span must occur in, or `chosen` (the coalesce field that gave the value).
    """

    group: str  # "metadata" | "contribution"
    value_from: str | tuple[str, ...]
    value_type: str
    predicate: str
    display_from: str
    value_selector: str | None = None


@dataclass(frozen=True)
class EntryKindSpec:
    """One entry kind's subject kind and its slots. A kind absent from the model has no subject
    kind, so its metadata and bullets both resolve to `unsupported_entry_kind` (§6.3a)."""

    subject_kind: str
    slots: tuple[Slot, ...]


@dataclass(frozen=True)
class ModelRoutedRule:
    """A rule whose predicate and value come from the `entry_kind_model` (O2b), not from itself.

    `kind_source` is `self` (read `atomic_value.kind`, the metadata record) or `condition` (look up
    the parent entry's kind, the bullet record — O6). `emits_group` filters the resolved kind's
    slots to `metadata` or `contribution`.
    """

    locator_pattern: str
    kind_source: str  # "self" | "condition"
    emits_group: str  # "metadata" | "contribution"


@dataclass(frozen=True)
class Deferral:
    """A locator that deliberately matches no producing rule and carries a *specific* drain reason
    instead of the generic `no_mapping_for_locator`: `header/2` (the email) is
    `no_predicate_exists`, `education/*` is `free_text_deferred` (the agent lane, §8)."""

    locator_pattern: str
    reason: str


@dataclass(frozen=True)
class ExtractionMapping:
    """The whole deterministic mapping for one adapter (design §6.2/§6.2a)."""

    literal_rules: tuple[ExtractionRule, ...] = ()
    model_routed_rules: tuple[ModelRoutedRule, ...] = ()
    entry_kind_model: Mapping[str, EntryKindSpec] = field(default_factory=dict)
    deferrals: tuple[Deferral, ...] = ()


@dataclass(frozen=True)
class ExtractionFailure:
    """Why one source record produced no candidate — one closed drain reason per record (§6.3a)."""

    source_record_id: str
    reason: str


@dataclass(frozen=True)
class ExtractionResult:
    """Every candidate the mapping proposes, and the drain reason for every record that produced
    none. A record that produced at least one candidate never appears in `failures`."""

    proposals: tuple[ProposedCandidate, ...]
    failures: tuple[ExtractionFailure, ...]


# --------------------------------------------------------------------------------------------------
# Value construction (O4), and the résumé `dates` grammar (a §9 plan task, string-level only).
# --------------------------------------------------------------------------------------------------

_SKILL_ID_NON_SLUG = re.compile(r"[^a-z0-9]+")

#: The résumé `dates` separator is ` -- ` (the LaTeX en-dash spelling the live resume.yaml uses);
#: unicode en/em dashes are accepted for robustness. A single hyphen is deliberately NOT a separator
#: — it never appears inside `Mon YYYY`, but splitting on it would be a needless ambiguity.
_DATES_SEPARATOR = re.compile(r"\s*(?:--|[–—])\s*")
_MONTH_ABBR_TO_NUM: Mapping[str, int] = {
    abbr.lower(): num for num, abbr in enumerate(calendar.month_abbr) if abbr
}
_OPEN_END_TOKENS = frozenset({"present", "current", "now"})


def _derive_skill_id(item: str) -> str:
    """A deterministic, human-readable `skill.<slug>` id from a skill item string.

    Lossy on purpose — `C++` and `C#` both slug to `skill.c` — because identity is content-addressed
    and the verbatim item is preserved as `original_display_value`, so the real name is never lost,
    and referential validation of the id against the inventory is the promotion slice's job (§6.4),
    not this layer's. An item with no alphanumeric content yields no id — a `value_not_typeable`.
    """
    slug = _SKILL_ID_NON_SLUG.sub("-", item.lower()).strip("-")
    if not slug:
        raise _ValueNotTypeable(f"skill item {item!r} has no alphanumeric content to derive an id")
    return f"skill.{slug}"


def _parse_year_month(token: str) -> str:
    """`Mon YYYY` → a `YYYY-MM` string, or `_ValueNotTypeable`.

    The grammar is deliberately narrow: exactly a three-or-more-letter month name (abbreviated or
    full, case-insensitive) and a four-digit year. Anything else is a résumé the deterministic lane
    should not silently coerce.
    """
    parts = token.split()
    if len(parts) != 2:
        raise _ValueNotTypeable(f"date token {token!r} is not `Mon YYYY`")
    name, year = parts
    month = _MONTH_ABBR_TO_NUM.get(name[:3].lower())
    if month is None or not year.isdigit() or len(year) != 4:
        raise _ValueNotTypeable(f"date token {token!r} is not `Mon YYYY`")
    return f"{int(year):04d}-{month:02d}"


def _parse_dates(text: str) -> tuple[str, str | None]:
    """A résumé `dates` string → `(start_year_month, end_year_month_or_None)`.

    An open end (`Present`) yields `None` — a legitimately absent component, not a malformed one, so
    a `range_end` slot over it produces no candidate rather than `value_not_typeable`.
    """
    sides = _DATES_SEPARATOR.split(text.strip())
    if len(sides) != 2:
        raise _ValueNotTypeable(f"dates {text!r} is not a two-sided `start -- end` range")
    start = _parse_year_month(sides[0])
    end = None if sides[1].strip().lower() in _OPEN_END_TOKENS else _parse_year_month(sides[1])
    return start, end


def _year_month_to_date(year_month: str) -> date:
    year, month = year_month.split("-")
    return date(int(year), int(month), 1)


def _build_value(
    value_type: str, raw: object, *, value_selector: str | None = None
) -> FactValue | None:
    """Construct the typed value (O4), or `None` when the selected component is legitimately absent.

    Raises `_ValueNotTypeable` when construction genuinely fails (a garbled date, a skill with no
    alphanumerics); the caller turns that into a `value_not_typeable` drain reason.
    """
    if value_type == "string":
        return StringValue(type="string", value=str(raw))
    if value_type == "skill_ref":
        return SkillRefValue(type="skill_ref", skill_id=_derive_skill_id(str(raw)))
    if value_type == "year_month":
        start, end = _parse_dates(str(raw))
        component = start if value_selector == "range_start" else end
        if component is None:
            return None
        return YearMonthValue(type="year_month", value=component)
    if value_type == "date_range":
        start, end = _parse_dates(str(raw))
        return DateRangeValue(
            type="date_range",
            start=_year_month_to_date(start),
            end=_year_month_to_date(end) if end is not None else None,
        )
    raise NotImplementedError(f"value_type {value_type!r} is not built")


# --------------------------------------------------------------------------------------------------
# Field access and locator matching (O1, O3a/O3c).
# --------------------------------------------------------------------------------------------------


def _field_value(atomic_value: object, name: str) -> object:
    """The named field of `atomic_value`, or `None` if absent/null. `.` is the scalar itself."""
    if name == ".":
        return atomic_value
    if isinstance(atomic_value, Mapping):
        return atomic_value.get(name)
    raise KeyError(name)


def _select_value(atomic_value: object, value_from: str | tuple[str, ...]) -> tuple[object, str]:
    """The raw value and the field it came from (O3a, or O3c coalesce — first non-null wins).

    Returns `(None, "")` when every candidate field is null/absent, which the caller reads as "no
    candidate", never as an error.
    """
    fields = value_from if isinstance(value_from, tuple) else (value_from,)
    for name in fields:
        value = _field_value(atomic_value, name)
        if value is not None and str(value) != "":
            return value, name
    return None, ""


def locator_matches(pattern: str, locator: str) -> bool:
    """Whether a segment-wise `pattern` matches a `normalized_locator`.

    Each pattern segment is either `*` (matches any one segment) or a literal (matches that segment
    exactly). Literal non-head segments are legal and load-bearing: `header/1` selects the
    professional name and does not match `header/2`, the email (§6.2a). A regex over locators would
    be a second grammar that drifts from the emitter, so there is none.
    """
    pattern_segments = pattern.split("/")
    locator_segments = locator.split("/")
    if len(pattern_segments) != len(locator_segments):
        return False
    return all(
        p == "*" or p == actual
        for p, actual in zip(pattern_segments, locator_segments, strict=True)
    )


def _literal_specificity(pattern: str) -> int:
    """How many segments of `pattern` are literals — the more-specific rule wins a predicate tie."""
    return sum(1 for segment in pattern.split("/") if segment != "*")


# --------------------------------------------------------------------------------------------------
# Emission (the interpreter core).
# --------------------------------------------------------------------------------------------------


def _emit(
    record: EnumeratedSourceRecord,
    predicate: str,
    value_from: str | tuple[str, ...],
    value_type: str,
    display_from: str,
    value_selector: str | None,
) -> ProposedCandidate | str | None:
    """One emission attempt. Returns a candidate, a drain reason (a `str`), or `None` (no candidate
    — a null field, or a legitimately-absent range component)."""
    raw, chosen_field = _select_value(record.atomic_value, value_from)
    if raw is None:
        return None
    try:
        value = _build_value(value_type, raw, value_selector=value_selector)
    except _ValueNotTypeable:
        return VALUE_NOT_TYPEABLE
    if value is None:
        return None

    display_field = chosen_field if display_from == "chosen" else display_from
    grounding_source = _field_value(record.atomic_value, display_field)
    if grounding_source is None:
        return SPAN_NOT_GROUNDED
    display = str(grounding_source)
    # The display value is the raw authored text of the field the span must occur in — for O3b this
    # is the whole `dates` string, not the parsed component, so a project's start/end candidates
    # share a display yet keep distinct candidate_ids off their differing typed values (§6.2a).
    if display == "":
        return SPAN_NOT_GROUNDED
    return ProposedCandidate(
        source_record_id=record.source_record_id,
        predicate=predicate,
        value=value,
        original_display_value=display,
    )


def _resolve_kind(
    rule: ModelRoutedRule,
    record: EnumeratedSourceRecord,
    by_locator: Mapping[str, EnumeratedSourceRecord],
) -> str | None:
    """The entry kind a model-routed rule resolves against, or `None` if unresolvable.

    `self` reads `atomic_value.kind`. `condition` (O6) looks up the parent entry's metadata record —
    a bullet locator `entries/<id>/bullets/<id>` yields its parent `entries/<id>/metadata` by
    dropping the `bullets/<id>` tail; metadata is emitted before any bullet, so the parent resolves.
    """
    if rule.kind_source == "self":
        kind = _field_value(record.atomic_value, "kind")
        return str(kind) if kind is not None else None
    if rule.kind_source == "condition":
        segments = record.normalized_locator.split("/")
        if len(segments) != 4 or segments[0] != "entries" or segments[2] != "bullets":
            return None
        parent = by_locator.get(f"{segments[0]}/{segments[1]}/metadata")
        if parent is None:
            return None
        kind = _field_value(parent.atomic_value, "kind")
        return str(kind) if kind is not None else None
    raise ExtractionMappingError(
        f"unknown kind_source {rule.kind_source!r}", code=IssueCode.MODEL_VALIDATION_ERROR
    )


def run_extraction(
    records: Sequence[EnumeratedSourceRecord], mapping: ExtractionMapping
) -> ExtractionResult:
    """Every candidate the mapping proposes over the records, plus the drain reason for each record
    that produced none (§6.2a, §6.3a). Record-then-rule order.

    A record may match several rules producing different candidates (multi-output emission). A
    record that matches no producing rule takes its most specific deferral reason, else
    `no_mapping_for_locator`. A record that matched a rule but produced nothing takes the reason
    that rule reported (`unsupported_entry_kind`, `value_not_typeable`, `span_not_grounded`).
    """
    by_locator = {record.normalized_locator: record for record in records}
    proposals: list[ProposedCandidate] = []
    failures: list[ExtractionFailure] = []

    for record in records:
        produced: list[ProposedCandidate] = []
        reason: str | None = None
        matched_a_rule = False

        for literal in mapping.literal_rules:
            if not locator_matches(literal.locator_pattern, record.normalized_locator):
                continue
            matched_a_rule = True
            outcome = _emit(
                record,
                literal.predicate,
                literal.value_from,
                literal.value_type,
                literal.display_from,
                None,
            )
            if isinstance(outcome, ProposedCandidate):
                produced.append(outcome)
            elif isinstance(outcome, str):
                reason = outcome

        for routed in mapping.model_routed_rules:
            if not locator_matches(routed.locator_pattern, record.normalized_locator):
                continue
            matched_a_rule = True
            kind = _resolve_kind(routed, record, by_locator)
            spec = mapping.entry_kind_model.get(kind) if kind is not None else None
            if spec is None:
                reason = UNSUPPORTED_ENTRY_KIND
                continue
            for slot in spec.slots:
                if slot.group != routed.emits_group:
                    continue
                outcome = _emit(
                    record,
                    slot.predicate,
                    slot.value_from,
                    slot.value_type,
                    slot.display_from,
                    slot.value_selector,
                )
                if isinstance(outcome, ProposedCandidate):
                    produced.append(outcome)
                elif isinstance(outcome, str):
                    reason = outcome

        if not matched_a_rule:
            reason = _deferral_reason(mapping, record.normalized_locator)

        proposals.extend(produced)
        if not produced:
            failures.append(
                ExtractionFailure(record.source_record_id, reason or NO_MAPPING_FOR_LOCATOR)
            )

    return ExtractionResult(tuple(proposals), tuple(failures))


def _deferral_reason(mapping: ExtractionMapping, locator: str) -> str:
    for deferral in mapping.deferrals:
        if locator_matches(deferral.locator_pattern, locator):
            return deferral.reason
    return NO_MAPPING_FOR_LOCATOR


def named_predicates(mapping: ExtractionMapping) -> frozenset[str]:
    """Every catalog predicate id the mapping's producing rules name — literal rules and every
    `entry_kind_model` slot. Deferrals name no predicate. This is the reachability half of §5.2
    invariant 4: a catalog predicate is reachable iff it appears here for some builtin mapping.
    """
    predicates = {rule.predicate for rule in mapping.literal_rules}
    for spec in mapping.entry_kind_model.values():
        predicates.update(slot.predicate for slot in spec.slots)
    return frozenset(predicates)


def validate_mapping_against_catalog(
    mapping: ExtractionMapping,
    catalog: PredicateCatalog,
    *,
    require_known_predicates: bool = True,
) -> None:
    """Refuse a mapping that cannot be a legal member of the seeded catalog — once, before any
    extraction runs (§6.2a). This is what turns the revision-5 misrouting (a `project` entry's facts
    landing on `employment.*`) into a caught *class* rather than a per-entry
    `PREDICATE_SUBJECT_KIND_ILLEGAL` discovered at promotion.

    Every literal predicate must exist in the catalog. Every model slot's predicate must exist AND
    its `legal_subject_kinds` must admit that entry kind's subject kind. Two slots of one kind's one
    group, or two literal rules with the same pattern, emitting the same predicate is an ambiguous
    mapping the author must resolve (§6.2a).

    Every non-predicate field is checked against its closed vocabulary too, because the mapping is
    owner-editable bundle data: an unknown `value_type` or `kind_source` that reached the
    interpreter would surface as an unhandled `NotImplementedError` or `ExtractionMappingError`
    mid-run rather than as a refusal before any record is read.

    `require_known_predicates=False` relaxes exactly one arm, for the host-bundle check: a catalog
    may legitimately be a *subset* of the one a builtin mapping was written against (the example
    bundle's is, deliberately — D-179), and a rule naming a predicate that catalog does not carry
    simply cannot fire there. Such a rule is skipped rather than refused; if a record does reach it,
    typing the proposal against the catalog refuses downstream. The misrouting arm — a predicate the
    catalog *does* carry, on a subject kind it does not admit — is enforced either way, because that
    is the guarantee §6.2a exists to make.
    """
    by_id = catalog.by_id

    for rule in mapping.literal_rules:
        if rule.predicate not in by_id:
            if not require_known_predicates:
                continue
            raise ExtractionMappingError(
                f"literal rule names unknown predicate {rule.predicate!r}",
                code=IssueCode.UNKNOWN_PREDICATE,
            )
        if rule.value_type not in VALUE_TYPES:
            raise ExtractionMappingError(
                f"literal rule names unknown value_type {rule.value_type!r} "
                f"(known: {sorted(VALUE_TYPES)})",
                code=IssueCode.MODEL_VALIDATION_ERROR,
            )
    literal_by_predicate: dict[tuple[str, str], int] = {}
    for rule in mapping.literal_rules:
        key = (rule.locator_pattern, rule.predicate)
        literal_by_predicate[key] = literal_by_predicate.get(key, 0) + 1
        if literal_by_predicate[key] > 1:
            raise ExtractionMappingError(
                f"two literal rules emit {rule.predicate!r} for {rule.locator_pattern!r}",
                code=IssueCode.MODEL_VALIDATION_ERROR,
            )

    for routed in mapping.model_routed_rules:
        if routed.kind_source not in KIND_SOURCES:
            raise ExtractionMappingError(
                f"model-routed rule names unknown kind_source {routed.kind_source!r} "
                f"(known: {sorted(KIND_SOURCES)})",
                code=IssueCode.MODEL_VALIDATION_ERROR,
            )
        if routed.emits_group not in SLOT_GROUPS:
            raise ExtractionMappingError(
                f"model-routed rule names unknown emits_group {routed.emits_group!r} "
                f"(known: {sorted(SLOT_GROUPS)})",
                code=IssueCode.MODEL_VALIDATION_ERROR,
            )

    for deferral in mapping.deferrals:
        if deferral.reason not in DRAIN_REASONS:
            raise ExtractionMappingError(
                f"deferral for {deferral.locator_pattern!r} names unknown reason "
                f"{deferral.reason!r} (known: {sorted(DRAIN_REASONS)})",
                code=IssueCode.MODEL_VALIDATION_ERROR,
            )

    for kind_name, spec in mapping.entry_kind_model.items():
        seen_in_group: dict[str, set[str]] = {}
        for slot in spec.slots:
            predicate = by_id.get(slot.predicate)
            if predicate is None and require_known_predicates:
                raise ExtractionMappingError(
                    f"entry kind {kind_name!r} slot names unknown predicate {slot.predicate!r}",
                    code=IssueCode.UNKNOWN_PREDICATE,
                )
            if predicate is not None:
                admitted = {kind.value for kind in predicate.legal_subject_kinds}
                if spec.subject_kind not in admitted:
                    raise ExtractionMappingError(
                        f"{slot.predicate!r} does not admit subject kind {spec.subject_kind!r} "
                        f"(entry kind {kind_name!r}); its legal subjects are {sorted(admitted)}",
                        code=IssueCode.PREDICATE_SUBJECT_KIND_ILLEGAL,
                    )
            if slot.value_type not in VALUE_TYPES:
                raise ExtractionMappingError(
                    f"entry kind {kind_name!r} slot names unknown value_type "
                    f"{slot.value_type!r} (known: {sorted(VALUE_TYPES)})",
                    code=IssueCode.MODEL_VALIDATION_ERROR,
                )
            if slot.group not in SLOT_GROUPS:
                raise ExtractionMappingError(
                    f"entry kind {kind_name!r} slot names unknown group {slot.group!r} "
                    f"(known: {sorted(SLOT_GROUPS)})",
                    code=IssueCode.MODEL_VALIDATION_ERROR,
                )
            if slot.value_selector is not None and slot.value_selector not in VALUE_SELECTORS:
                raise ExtractionMappingError(
                    f"entry kind {kind_name!r} slot names unknown value_selector "
                    f"{slot.value_selector!r} (known: {sorted(VALUE_SELECTORS)})",
                    code=IssueCode.MODEL_VALIDATION_ERROR,
                )
            group = seen_in_group.setdefault(slot.group, set())
            if slot.predicate in group:
                raise ExtractionMappingError(
                    f"entry kind {kind_name!r} group {slot.group!r} emits {slot.predicate!r} twice",
                    code=IssueCode.MODEL_VALIDATION_ERROR,
                )
            group.add(slot.predicate)


def extract_proposals(
    records: Sequence[EnumeratedSourceRecord], rules: Sequence[ExtractionRule]
) -> list[ProposedCandidate]:
    """Every candidate a set of **literal** rules proposes — the primitive the easy buckets use.

    A thin wrapper over `run_extraction` with a literal-only mapping, so both share one emission
    path; the drain reasons are dropped because a literal-only caller wants the candidates alone.
    """
    result = run_extraction(records, ExtractionMapping(literal_rules=tuple(rules)))
    return list(result.proposals)
