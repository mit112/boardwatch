"""T235: a heading-hedged bar is carried, not dropped, and a spaced `Nice to Have` heading governs.

- A bar only its hedge HEADING hedges was dropped whenever its `hedged_as` twin is not a carrier, on the
  assumption that the twin's own wording reads the heading form. `clearance_preferred` cannot read
  "Preferred Qualifications:\\n- Ability to obtain a Secret clearance", so the clearance bar left no row
  at all; after T173d round 2 a cue BEFORE the bar no longer lifts the hedge, which is how pv 137945 and
  177834 lost theirs ("U.S. Citizenship required with the ability to obtain and maintain a government
  security clearance"). The bar is now carried as its twin when the heading states a preference; a row
  the twin wrote over the same bar absorbs it, and a heading whose only hedge is a negation still drops.
- `Nice to Have / Bonus` and `Nice to Have Skills:` failed `_looks_like_header` on the lowercase `to`,
  where the hyphenated twin passed; the spaced form now reads as the hyphenated one.

Not built (0 store instances, pinned as controls): an item-initial `Must be ...` whose bar it does not
bind, and the adjectival `Mandatory 5 years` as an item's own mandate. The near-miss band is off.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.detect import _looks_like_header
from boardwatch.eligibility.engine import evaluate
from boardwatch.eligibility.facts import Facts, Policy

POLICY = Policy(
    families={
        "work_auth": "blocker", "experience_years": "blocker",
        "clearance": "blocker", "degree": "blocker",
    },
    near_miss_years_ceilings={"experience_years": 0},
)
FACTS = Facts(total_years_experience=1, highest_degree="bachelor")


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return load_rules(Path(tmp_path_factory.mktemp("no-override")))


def _read(body: str, catalog) -> tuple[str, list[tuple[str, str, str, str]]]:  # type: ignore[no-untyped-def]
    result = evaluate(body, FACTS, POLICY, catalog)
    return result.verdict, sorted(
        (r.rule_id.split(":")[1], r.requiredness, r.disposition, body[slice(*r.jd_locator["span"])])
        for r in result.requirements
    )


CARRIED = [
    pytest.param(
        "Preferred Qualifications\nU.S. Citizenship required with the ability to obtain and maintain a "
        "government security clearance",
        ("uncertain", [
            ("clearance_preferred", "preferred", "unknown",
             "ability to obtain and maintain a government security clearance"),
            ("us_citizen_required", "required", "unknown", "U.S. Citizenship required"),
            ("us_citizen_standalone_required", "required", "unknown", "U.S. Citizenship required with"),
        ]),
        id="a-cue-before-the-bar",  # pv 137945
    ),
    pytest.param(
        "Preferred Qualifications:\nUS Citizenship is required with an ability to obtain and maintain a "
        "government security clearance.",
        ("uncertain", [
            ("clearance_preferred", "preferred", "unknown",
             "ability to obtain and maintain a government security clearance"),
            ("us_citizen_required", "required", "unknown", "US Citizenship is required"),
        ]),
        id="a-cue-before-the-bar-with-a-copula",  # pv 177834
    ),
    pytest.param(
        "Preferred Qualifications:\n- Ability to obtain a Secret clearance",
        ("eligible", [("clearance_preferred", "preferred", "unknown", "Ability to obtain a Secret clearance")]),
        id="a-bare-clearable-bar",
    ),
    pytest.param(
        "Preferred:\n- Eligible for a Secret security clearance",
        ("eligible", [("clearance_preferred", "preferred", "unknown",
                       "Eligible for a Secret security clearance")]),
        id="the-leveled-sibling",
    ),
    pytest.param(
        "Preferred Qualifications:\n- Experience: 5 years",
        ("eligible", [("total_years_preferred", "preferred", "unmet", "Experience: 5 years")]),
        id="a-labeled-years-bar",
    ),
    pytest.param(
        "Preferred:\n- Bachelor's degree or equivalent experience",
        ("eligible", [("bachelor_or_equivalent_preferred", "preferred", "met",
                       "Bachelor's degree or equivalent")]),
        id="a-degree-bar",
    ),
]


@pytest.mark.parametrize(("body", "expected"), CARRIED)
def test_a_heading_hedged_bar_is_carried_as_its_twin(body: str, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == expected


ONE_ROW = [
    pytest.param(
        "Preferred Qualifications:\n- Security clearance preferred",
        [("clearance_preferred", "preferred", "unknown", "Security clearance preferred")],
        id="clearance-twin-reads-it-itself",
    ),
    pytest.param(
        "Preferred Qualifications:\n- 5+ years of experience",
        [("total_years_preferred", "preferred", "unmet", "5+ years of experience")],
        id="years-twin-reads-the-heading-view",
    ),
    pytest.param(
        "Preferred Qualifications:\n- 3-5 years of experience",
        [("range_years_preferred", "preferred", "unmet", "3-5 years of experience")],
        id="range-twin-reads-the-heading-view",
    ),
]


@pytest.mark.parametrize(("body", "rows"), ONE_ROW)
def test_a_row_the_twin_wrote_absorbs_the_carried_one(body: str, rows, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == ("eligible", rows)


def test_a_mandate_heading_still_binds(catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read("Required Qualifications:\n- Ability to obtain a Secret clearance", catalog) == (
        "uncertain", [
            ("clearable_leveled_required", "required", "unknown", "Ability to obtain a Secret clearance"),
            ("clearable_required", "required", "unknown", "Ability to obtain a Secret clearance"),
        ],
    )


def test_a_negation_heading_is_no_preference_and_still_drops(catalog) -> None:  # type: ignore[no-untyped-def]
    """`not required` is in the leveled pattern's hedge list, not in its preference vocabulary."""
    assert _read("Not Required:\n- Eligible for a Secret security clearance", catalog) == ("uncertain", [])


@pytest.mark.parametrize(
    "heading",
    ["Nice to Have / Bonus", "Nice to Have Skills:", "Nice To Have Qualifications", "Nice to Have's"],
)
def test_a_spaced_nice_to_have_heading_governs_its_list(heading: str, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(f"{heading}\n- 5+ years of experience in audit", catalog) == (
        "eligible", [("scoped_years_preferred", "preferred", "unmet", "5+ years of experience in")],
    )


@pytest.mark.parametrize(
    "heading",
    ["Nice to Have / Bonus", "Nice to Have Skills:", "Nice to have skills:", "Nice to Haves:",
     "Nice to have:", "NICE TO HAVE"],
)
def test_the_spaced_heading_reads_as_its_hyphenated_twin(heading: str, catalog) -> None:  # type: ignore[no-untyped-def]
    hyphenated = "-".join(heading.split(" ", 2)[:2]) + "-" + heading.split(" ", 2)[2]
    assert _looks_like_header(heading) == _looks_like_header(hyphenated)
    item = "\n- 5+ years of experience in audit"
    assert _read(heading + item, catalog)[0] == _read(hyphenated + item, catalog)[0]


@pytest.mark.parametrize(
    "line",
    ["Nice to have experience with Kafka.", "Nice to have: Databricks Certification",
     "Experience with Nice to Have features is required."],
)
def test_a_nice_to_have_content_line_is_no_heading(line: str) -> None:
    assert not _looks_like_header(line)


def test_a_nice_to_have_item_under_requirements_governs_nothing(catalog) -> None:  # type: ignore[no-untyped-def]
    body = "Requirements:\n- Nice to have experience with Kafka.\n- 5+ years of experience in audit"
    assert _read(body, catalog) == (
        "ineligible", [("scoped_years_minimum", "required", "unmet", "5+ years of experience in")],
    )


# Not built, 0 store instances each (batch 8's census): pinned so a change shows.
CONTROLS = [
    pytest.param(
        "Preferred:\n- Must be comfortable mentoring candidates with 5 years of experience in audit",
        ("ineligible", [("scoped_years_minimum", "required", "unmet", "5 years of experience in")]),
        id="must-be-lifts-a-bar-it-does-not-bind",
    ),
    pytest.param(
        "Preferred:\n- Must be able to obtain a Public Trust Clearance",
        ("uncertain", [
            ("clearable_leveled_required", "required", "unknown", "able to obtain a Public Trust Clearance"),
            ("clearable_required", "required", "unknown", "able to obtain a Public Trust"),
        ]),
        id="must-be-binds-its-own-bar",  # pv 126981, one of 6 store instances
    ),
    pytest.param(
        "Preferred:\n- Mandatory 5 years of experience in audit",
        ("eligible", [("scoped_years_preferred", "preferred", "unmet", "5 years of experience in")]),
        id="adjectival-mandatory-is-no-cue",
    ),
]


@pytest.mark.parametrize(("body", "expected"), CONTROLS)
def test_unbuilt_item_mandate_shapes_keep_their_reading(body: str, expected, catalog) -> None:  # type: ignore[no-untyped-def]
    assert _read(body, catalog) == expected


def test_a_lowercase_nice_to_have_label_is_still_a_heading() -> None:
    """`_QUAL_HEADER` reads the spaced label whatever its case, before the hyphenated reading."""
    assert _looks_like_header("nice to have:")


def test_a_sibling_that_read_the_bar_absorbs_the_heading_carried_row(catalog) -> None:  # type: ignore[no-untyped-def]
    """The leveled sibling is hedged by `Bonus`, its twin is not: the twin's required row decides the
    bar, and no preference is written beside it (heading case h42)."""
    body = "Bonus Points:\n- Ability to obtain security clearance if required."
    assert [r[0] for r in _read(body, catalog)[1]] == ["clearable_required", "generic_clearance_required"]
