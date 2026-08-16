"""The closed placeholder grammar, and the one rendering each admitted fact value gets.

Rendering is projection-owned and specified HERE rather than deferred, because the alternative is
that whoever implements it invents `2025-02-01 – Present` versus `Feb 2025 – Present` and a golden
test blesses whichever convention they happened to pick.

**The convention is month precision: `Oct 2025`, `Feb 2025 – Jan 2026`, `Oct 2025 – Present`.**
The first cut of this module rendered dates as raw ISO, which is why `projection.yaml` carried
hand-typed date literals instead of fact references — nobody wants `2025-10-01` on a résumé, so
the one field that could not be fact-grounded was the one every entry needed. D-200 recorded the
month formatter as owed and did not build it; this is that formatter. It is ours to choose:
the spec's §4.1 rule is that date *formatting* is not authoring, while the word for "still going"
(`open_range_label`) is the owner's and has no default.

There is no uniform accessor on `FactValue`: seven of ten arms expose `.value`, `string_list`
exposes `.values`, `skill_ref` exposes `.skill_id`, and `date_range` exposes `.start`/`.end`. So
this dispatches on type, and a test derives the arm set from `FactValueKind` so an eleventh member
cannot slip through as an unrendered placeholder.

Note on `UrlValue.value`: in this bundle, `profile_bundle.models.base.HttpUrl` is a
`StringConstraints`-annotated plain `str` (regex-anchored to `http`/`https`), not pydantic's own
`HttpUrl` type. Pydantic performs no normalisation on a constrained `str` field, so there is no
trailing-slash rewrite to guard against here; the URL arm renders the value verbatim, identically
to the string arm. Pinned by `test_each_admitted_kind_has_exactly_one_rendering`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, get_args

from boardwatch.profile_bundle.models.base import PredicateId
from boardwatch.profile_bundle.models.facts import (
    DateRangeValue,
    DateValue,
    DecimalValue,
    FactRecord,
    FactValue,
    FactValueKind,
    IntegerValue,
    StringValue,
    UrlValue,
    YearMonthValue,
)
from boardwatch.profile_bundle.models.skills import SkillRecord
from boardwatch.projection.errors import ProjectionIssue, raise_violation

#: The en-dash separator for a date range. One convention, one place.
RANGE_SEPARATOR = " – "

#: English month abbreviations, indexed at `[month - 1]`. Deliberately NOT `strftime("%b")`:
#: that is locale-dependent, so the same bundle would render "Oct", "oct." or "Okt" onto a résumé
#: depending on `LC_TIME`. boardwatch runs on its user's own machine, whoever that user is, so a
#: rendering that reaches a live job application has to be locale-independent by construction
#: rather than by whatever the environment happens to be set to.
_MONTH_ABBREVIATIONS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip

#: The kinds admitted as an ENDPOINT of a declared two-fact range (`DateRangeDeclaration`).
#: Only `year_month`, because that is exactly what the catalog's paired date predicates carry
#: (`project.start_date`/`end_date`, `education.start_date`/`end_date` — the only four predicates
#: whose `legal_value_types` is `year_month`). `date_range` is excluded on purpose: an endpoint
#: that is itself a range would nest one inside another and print "Oct 2025 – Present – Mar 2026".
RANGE_ENDPOINT_KINDS: frozenset[FactValueKind] = frozenset({FactValueKind.YEAR_MONTH})


def format_month_year(year: int, month: int) -> str:
    """`(2025, 10)` → `"Oct 2025"`. The one month-precision rendering, used by every date arm.

    Month precision is the résumé convention, and it is why this discards a `date`'s day: the
    bundle stores `employment.date_range` as full dates with day `01` standing in for "that
    month", so printing `2025-10-01` would show a precision the fact never actually had.
    """
    return f"{_MONTH_ABBREVIATIONS[month - 1]} {year}"


def _month_year_of(value: YearMonthValue) -> str:
    # `YearMonth` is regex-pinned to `YYYY-MM` on the model, so this split cannot fail.
    year, month = value.value.split("-")
    return format_month_year(int(year), int(month))


#: Kinds a template may carry. `boolean`, `string_list` and `skill_ref` are excluded: a list or a
#: boolean on a résumé line is authoring, not projection.
ADMITTED_KINDS: frozenset[FactValueKind] = frozenset(
    {
        FactValueKind.STRING,
        FactValueKind.INTEGER,
        FactValueKind.DECIMAL,
        FactValueKind.DATE,
        FactValueKind.YEAR_MONTH,
        FactValueKind.DATE_RANGE,
        FactValueKind.URL,
    }
)

#: `{predicate}` or `{@field}`. Nothing else is admitted.
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
#: The same pattern `PredicateId` enforces on-model (`profile_bundle/models/base.py`), derived via
#: `get_args` rather than restated — a hand-copied pattern would keep enforcing a stale rule with
#: nothing to catch the drift if `PredicateId` is ever revised.
_PREDICATE_RE = re.compile(get_args(PredicateId)[1].pattern)
_FIELD_RE = re.compile(r"^@([a-z][a-z0-9_]*)$")

#: Entity display fields the `{@…}` namespace admits. `status` is NOT universal — `PersonEntity`
#: has none — so resolution checks the instance, not this set alone.
_DISPLAY_FIELDS: frozenset[str] = frozenset({"display_name", "status"})


def render_value(value: FactValue, *, open_range_label: str, where: str) -> str:
    """One rendering per admitted kind. An unadmitted kind is fatal, never a best effort."""
    if isinstance(value, StringValue | UrlValue):
        return value.value
    if isinstance(value, DecimalValue):
        # The model stores a DecimalString, so this is already exact — no rounding, no unit.
        return value.value
    if isinstance(value, IntegerValue):
        # NOT verbatim: the loader normalises, so a legal `+12` input arrives here as 12.
        return str(value.value)
    if isinstance(value, YearMonthValue):
        return _month_year_of(value)
    if isinstance(value, DateValue):
        # Stays ISO. `date` is day-precision and no catalog predicate carries one today, so
        # giving it a month-precision rendering would be inventing a convention for a case that
        # does not exist; `year_month` and `date_range` moved because both DO reach a résumé.
        return value.value.isoformat()
    if isinstance(value, DateRangeValue):
        end = (
            format_month_year(value.end.year, value.end.month)
            if value.end is not None
            else open_range_label
        )
        start = format_month_year(value.start.year, value.start.month)
        return f"{start}{RANGE_SEPARATOR}{end}"
    raise_violation(
        ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED,
        f"a {value.type!r} value cannot be rendered on a résumé line; admitted kinds are "
        f"{sorted(k.value for k in ADMITTED_KINDS)}",
        where=where,
    )


def render_declared_range(
    start: FactRecord,
    end: FactRecord | None,
    *,
    open_range_label: str,
    where: str,
) -> str:
    """Assemble a range from the TWO facts the catalog uses for projects and education.

    `employment.date_range` carries both halves in ONE `DateRangeValue`, but `project.*` and
    `education.*` carry a `year_month` PAIR instead, and that split is deliberate — D-177 finding
    3: `YearMonthValue` holds a single scalar, so one extraction rule cannot yield start and end
    from one source field. The spec's §4.1 answer was for the owner to write
    `'{project.start_date} – {project.end_date}'`, which has two defects this fixes: it retypes
    the separator on every entry, and — because an unresolved placeholder is fatal — it cannot
    express an open range **at all**, so a project still running has no renderable form.

    Same convention as the `DateRangeValue` arm, applied to the pair: `RANGE_SEPARATOR` between
    the halves, `open_range_label` when there is no end. `end is None` here means the DECLARATION
    omitted it — the owner saying "still going". A named end whose fact is missing never reaches
    this function; the caller keeps that distinction, because the absence of a fact is not the
    owner declaring a range open, and printing "Present" over a role that ended would fabricate.
    """
    rendered_start = _range_endpoint(start, where=where)
    if end is None:
        return f"{rendered_start}{RANGE_SEPARATOR}{open_range_label}"
    return f"{rendered_start}{RANGE_SEPARATOR}{_range_endpoint(end, where=where)}"


def _range_endpoint(fact: FactRecord, *, where: str) -> str:
    value = fact.value
    if not isinstance(value, YearMonthValue):
        raise_violation(
            ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED,
            f"fact {fact.fact_id!r} is a {value.type!r}, which cannot be one END of a declared "
            f"date range; admitted endpoints are "
            f"{sorted(k.value for k in RANGE_ENDPOINT_KINDS)}",
            where=where,
        )
    return _month_year_of(value)


def render_skill(skill: SkillRecord) -> str:
    """A skill id becomes its canonical name.

    The spec's `projection.yaml` declares `skills:` as bundle IDs while `tailor.model.SkillGroup`
    carries `items: list[str]` of rendered text; this is the mapping between them, and it was
    unspecified.
    """
    return skill.canonical_name


def resolve_template(
    template: str,
    *,
    entity: Any,
    facts_by_predicate: Mapping[str, FactRecord],
    open_range_label: str,
    where: str,
) -> str:
    """Substitute fact values and entity display fields. Everything else is the owner's own text.

    Unresolved is FATAL. A blank substitution would put a half-built line on a résumé, and the
    projected document becomes Tier A's ground truth — a gap introduced here is not caught
    downstream, it becomes the truth.
    """

    def one(match: re.Match[str]) -> str:
        token = match.group(1)
        field = _FIELD_RE.match(token)
        if field is not None:
            name = field.group(1)
            if name not in _DISPLAY_FIELDS:
                raise_violation(
                    ProjectionIssue.MALFORMED_PLACEHOLDER,
                    f"{{@{name}}} is not an entity display field; admitted: "
                    f"{sorted(_DISPLAY_FIELDS)}",
                    where=where,
                )
            resolved = getattr(entity, name, None)
            if resolved is None:
                raise_violation(
                    ProjectionIssue.UNRESOLVED_PLACEHOLDER,
                    f"{{@{name}}} does not resolve on a "
                    f"{getattr(entity, 'entity_type', 'unknown')!r} entity; `status` in "
                    "particular is absent on `person` by design",
                    where=where,
                )
            # Every genuine `@`-field value is either a plain `str` (`display_name`) or a
            # `StrEnum` member (`status`), and `StrEnum.__str__` already returns the bare value —
            # not `ClassName.MEMBER`. A `.value` unwrap changes nothing for either shape, so there
            # is nothing here for one to defend against; `str(resolved)` alone is the whole thing.
            return str(resolved)
        if _PREDICATE_RE.match(token) is None:
            raise_violation(
                ProjectionIssue.MALFORMED_PLACEHOLDER,
                f"{{{token}}} is neither a predicate nor an @display field",
                where=where,
            )
        fact = facts_by_predicate.get(token)
        if fact is None:
            raise_violation(
                ProjectionIssue.UNRESOLVED_PLACEHOLDER,
                f"no résumé-surfaced, effective fact with predicate {token!r} on this entity",
                where=where,
            )
        return render_value(fact.value, open_range_label=open_range_label, where=where)

    return _PLACEHOLDER_RE.sub(one, template)
