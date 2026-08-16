"""The closed placeholder grammar and the ten-arm value renderer."""

from __future__ import annotations

from datetime import date

import pytest

from boardwatch.profile_bundle.models.base import (
    Surface,
    UsageContext,
    VerificationBasis,
    VerificationState,
)
from boardwatch.profile_bundle.models.facts import (
    BooleanValue,
    DateRangeValue,
    DateValue,
    DecimalValue,
    FactRecord,
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
from boardwatch.projection.grammar import (
    ADMITTED_KINDS,
    RANGE_ENDPOINT_KINDS,
    format_month_year,
    render_declared_range,
    render_skill,
    render_value,
)

#: One case per admitted kind. Also feeds the coverage-derivation test below, so the parametrize
#: list and the "did we actually cover ten arms" check read the same fixtures rather than two
#: hand-typed lists that can silently drift apart.
ADMITTED_CASES: list[tuple[object, str]] = [
    (StringValue(type="string", value="Example Labs"), "Example Labs"),
    (UrlValue(type="url", value="https://example.com/x"), "https://example.com/x"),
    (DecimalValue(type="decimal", value="8.5"), "8.5"),
    (IntegerValue(type="integer", value=12), "12"),
    (YearMonthValue(type="year_month", value="2026-02"), "Feb 2026"),
    # `date` alone stays ISO: no catalog predicate carries one, so it has no résumé convention.
    (DateValue(type="date", value=date(2026, 2, 1)), "2026-02-01"),
    (
        DateRangeValue(type="date_range", start=date(2025, 2, 1), end=date(2026, 1, 31)),
        "Feb 2025 – Jan 2026",
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
    is the owner's; the month formatting is ours."""
    value = DateRangeValue(type="date_range", start=date(2025, 2, 1), end=None)
    assert render_value(value, open_range_label="Present", where="w") == "Feb 2025 – Present"
    assert render_value(value, open_range_label="Current", where="w") == "Feb 2025 – Current"


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


# --- month-precision rendering (D-200's owed formatter) -----------------------------------

#: The twelve abbreviations written out INDEPENDENTLY of `grammar._MONTH_ABBREVIATIONS`. Pinning
#: against the module's own constant would be a test that agrees with itself; this is the outside
#: fact — English three-letter month abbreviations — restated so a typo in either one fails.
_EXPECTED_MONTHS = [
    (1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr"), (5, "May"), (6, "Jun"),
    (7, "Jul"), (8, "Aug"), (9, "Sep"), (10, "Oct"), (11, "Nov"), (12, "Dec"),
]  # fmt: skip


@pytest.mark.parametrize(("month", "abbreviation"), _EXPECTED_MONTHS)
def test_every_month_renders_its_english_abbreviation(month: int, abbreviation: str) -> None:
    """All twelve, because an off-by-one in the `[month - 1]` index would still pass a test that
    only checked one month, and would silently print the wrong month onto a real application."""
    assert format_month_year(2025, month) == f"{abbreviation} 2025"


def test_the_year_is_rendered_in_full_not_abbreviated() -> None:
    """`Oct 25` would be ambiguous between 2025 and a day-of-month."""
    assert format_month_year(2025, 10) == "Oct 2025"
    assert format_month_year(1999, 1) == "Jan 1999"


def _year_month_fact(fact_id: str, predicate: str, value: str) -> FactRecord:
    return FactRecord(
        fact_id=fact_id,
        subject_id="project.example",
        predicate=predicate,
        value=YearMonthValue(type="year_month", value=value),
        verification_state=VerificationState.OWNER_CONFIRMED,
        verification_basis=VerificationBasis.OWNER_ATTESTED,
        usage_context=UsageContext.PERSONAL_PROJECT,
        evidence_ids=(),
        allowed_surfaces=(Surface.RESUME,),
        conflict_group_id=None,
        reviewed_at=date(2026, 1, 1),
        expires_at=None,
        supersedes_fact_ids=(),
        import_lineage=None,
        notes=None,
    )


def test_a_declared_range_joins_two_facts_with_the_one_separator() -> None:
    """The pair shape (`project.start_date` + `project.end_date`) renders identically to the
    single `date_range` shape — same separator, same month precision — so which fact shape the
    catalog happens to use for an entity is invisible on the page."""
    out = render_declared_range(
        _year_month_fact("fact.a", "project.start_date", "2023-09"),
        _year_month_fact("fact.b", "project.end_date", "2023-12"),
        open_range_label="Present",
        where="w",
    )
    assert out == "Sep 2023 – Dec 2023"


def test_a_declared_range_with_no_end_renders_the_owners_own_word() -> None:
    """An OMITTED end is the owner declaring the range open — the case a two-placeholder template
    cannot express at all, because a missing end fact is a fatal unresolved placeholder."""
    start = _year_month_fact("fact.a", "project.start_date", "2026-06")
    assert (
        render_declared_range(start, None, open_range_label="Present", where="w")
        == "Jun 2026 – Present"
    )
    assert (
        render_declared_range(start, None, open_range_label="Current", where="w")
        == "Jun 2026 – Current"
    )


def test_a_declared_range_endpoint_that_is_itself_a_range_is_fatal() -> None:
    """Nesting a range inside a range would print "Oct 2025 – Present – Mar 2026". Refused at the
    endpoint rather than rendered, because the owner reads this line in the approval preview and a
    plausible-looking wrong string is exactly what a preview fails to catch."""
    nested = FactRecord(
        fact_id="fact.nested",
        subject_id="employment.example",
        predicate="employment.date_range",
        value=DateRangeValue(type="date_range", start=date(2025, 10, 1), end=None),
        verification_state=VerificationState.OWNER_CONFIRMED,
        verification_basis=VerificationBasis.OWNER_ATTESTED,
        usage_context=UsageContext.PROFESSIONAL,
        evidence_ids=(),
        allowed_surfaces=(Surface.RESUME,),
        conflict_group_id=None,
        reviewed_at=date(2026, 1, 1),
        expires_at=None,
        supersedes_fact_ids=(),
        import_lineage=None,
        notes=None,
    )
    with pytest.raises(ProjectionError) as exc:
        render_declared_range(nested, None, open_range_label="Present", where="w")
    assert exc.value.violation.issue is ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED


def test_the_admitted_endpoint_kinds_are_exactly_what_the_catalog_pairs_carry() -> None:
    """`RANGE_ENDPOINT_KINDS` is narrower than `ADMITTED_KINDS` on purpose: a range half has to be
    a point in time, and the catalog's only paired date predicates are `year_month`."""
    assert RANGE_ENDPOINT_KINDS == {FactValueKind.YEAR_MONTH}
    assert RANGE_ENDPOINT_KINDS < ADMITTED_KINDS
