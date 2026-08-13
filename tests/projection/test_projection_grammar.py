"""The closed placeholder grammar and the ten-arm value renderer."""

from __future__ import annotations

from datetime import date

import pytest

from boardwatch.profile_bundle.models.base import Surface, VerificationState
from boardwatch.profile_bundle.models.facts import (
    BooleanValue,
    DateRangeValue,
    DateValue,
    DecimalValue,
    FactValueKind,
    IntegerValue,
    SkillRefValue,
    StringListValue,
    StringValue,
    UrlValue,
    YearMonthValue,
)
from boardwatch.profile_bundle.models.skills import SkillRecord
from boardwatch.projection.errors import ProjectionError, ProjectionIssue
from boardwatch.projection.grammar import ADMITTED_KINDS, render_skill, render_value

#: One case per admitted kind. Also feeds the coverage-derivation test below, so the parametrize
#: list and the "did we actually cover ten arms" check read the same fixtures rather than two
#: hand-typed lists that can silently drift apart.
ADMITTED_CASES: list[tuple[object, str]] = [
    (StringValue(type="string", value="Example Labs"), "Example Labs"),
    (UrlValue(type="url", value="https://example.com/x"), "https://example.com/x"),
    (DecimalValue(type="decimal", value="8.5"), "8.5"),
    (IntegerValue(type="integer", value=12), "12"),
    (YearMonthValue(type="year_month", value="2026-02"), "2026-02"),
    (DateValue(type="date", value=date(2026, 2, 1)), "2026-02-01"),
    (
        DateRangeValue(type="date_range", start=date(2025, 2, 1), end=date(2026, 1, 31)),
        "2025-02-01 – 2026-01-31",
    ),
]

#: One case per unadmitted kind. Same rationale as `ADMITTED_CASES`.
REFUSED_CASES: list[object] = [
    BooleanValue(type="boolean", value=True),
    StringListValue(type="string_list", values=("a", "b")),
    SkillRefValue(type="skill_ref", skill_id="skill.example-language"),
]


def test_the_renderer_covers_every_kind_the_enum_declares() -> None:
    """Derived from `FactValueKind`, never restated. An eleventh member added to the bundle
    must fail here rather than fall through to an unrendered placeholder — this repo's own
    rule: a derived check must read the emitter's constants."""
    declared = set(FactValueKind)
    assert len(declared) == 10, "the bundle's value union changed; revisit the render table"
    handled = ADMITTED_KINDS | {
        FactValueKind.BOOLEAN,
        FactValueKind.STRING_LIST,
        FactValueKind.SKILL_REF,
    }
    assert handled == declared


def test_the_two_case_lists_together_exercise_every_kind_exactly_once() -> None:
    """Non-vacuity for the parametrized tests below: prove the fixtures that actually get
    collected as pytest parameters — not a separately hand-typed set — cover the full ten-member
    enum, one kind apiece. A parametrization silently covering 7 of 10 is precisely the failure
    mode this repo has been bitten by before, so this reads the collection's own source lists."""
    admitted_kinds = [FactValueKind(v.type) for v, _ in ADMITTED_CASES]  # type: ignore[attr-defined]
    refused_kinds = [FactValueKind(v.type) for v in REFUSED_CASES]  # type: ignore[attr-defined]
    assert len(admitted_kinds) == 7
    assert len(refused_kinds) == 3
    all_kinds = admitted_kinds + refused_kinds
    assert len(all_kinds) == 10, "expected exactly ten parametrized cases, one per FactValueKind"
    assert len(set(all_kinds)) == 10, "a kind was covered twice while another was missed"
    assert set(all_kinds) == set(FactValueKind)


@pytest.mark.parametrize(("value", "expected"), ADMITTED_CASES)
def test_each_admitted_kind_has_exactly_one_rendering(value: object, expected: str) -> None:
    assert render_value(value, open_range_label="Present", where="w") == expected  # type: ignore[arg-type]


def test_an_open_range_renders_the_owners_own_word() -> None:
    """`DateRangeValue` has no display member, so this convention is projection-owned. The word
    is the owner's; the ISO formatting is ours."""
    value = DateRangeValue(type="date_range", start=date(2025, 2, 1), end=None)
    assert render_value(value, open_range_label="Present", where="w") == "2025-02-01 – Present"
    assert render_value(value, open_range_label="Current", where="w") == "2025-02-01 – Current"


@pytest.mark.parametrize("value", REFUSED_CASES)
def test_an_unadmitted_kind_is_fatal(value: object) -> None:
    """A list or a boolean on a résumé line is authoring, not projection."""
    with pytest.raises(ProjectionError) as exc:
        render_value(value, open_range_label="Present", where="projection.yaml: entry.x")  # type: ignore[arg-type]
    assert exc.value.violation.issue is ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED


def test_render_skill_returns_the_canonical_name() -> None:
    """`render_skill` had no direct assertion — it was only implicitly touched via `SKILL_REF`'s
    refusal path through `render_value`, which never actually calls it. Exercise it directly."""
    skill = SkillRecord(
        skill_id="skill.example-language",
        canonical_name="Example Language",
        category="language",
        supporting_fact_ids=("fact.example-1",),
        verification_state=VerificationState.VERIFIED,
        allowed_surfaces=(Surface.RESUME,),
    )
    assert render_skill(skill) == "Example Language"
