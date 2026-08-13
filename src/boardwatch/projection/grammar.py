"""The closed placeholder grammar, and the one rendering each admitted fact value gets.

Rendering is projection-owned and specified HERE rather than deferred, because the alternative is
that whoever implements it invents `2025-02-01 – Present` versus `Feb 2025 – Present` and a golden
test blesses whichever convention they happened to pick.

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
from typing import Any

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
_PREDICATE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
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
        return value.value
    if isinstance(value, DateValue):
        return value.value.isoformat()
    if isinstance(value, DateRangeValue):
        end = value.end.isoformat() if value.end is not None else open_range_label
        return f"{value.start.isoformat()}{RANGE_SEPARATOR}{end}"
    raise_violation(
        ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED,
        f"a {value.type!r} value cannot be rendered on a résumé line; admitted kinds are "
        f"{sorted(k.value for k in ADMITTED_KINDS)}",
        where=where,
    )


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
            return str(getattr(resolved, "value", resolved))
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
