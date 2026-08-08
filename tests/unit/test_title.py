from __future__ import annotations

from boardwatch.tailor.persona import Persona
from boardwatch.tailor.title import resolve_title, strip_seniority

_SENIORITY = (
    "distinguished",
    "principal",
    "staff",
    "senior",
    "sr",
    "sr.",
    "lead",
    "ii",
    "iii",
    "iv",
    "v",
)


# --- strip_seniority -----------------------------------------------------------------


def test_sr_stripped_but_sre_intact() -> None:
    assert strip_seniority("Sr Backend Engineer") == "Backend Engineer"
    # SRE must survive — 'Sr' is not a sub-token of 'SRE'.
    assert strip_seniority("SRE") == "SRE"
    assert strip_seniority("Israel Site Reliability") == "Israel Site Reliability"


def test_lead_stripped_but_leader_and_leadership_intact() -> None:
    assert strip_seniority("Lead Engineer") == "Engineer"
    assert strip_seniority("Team Leader") == "Team Leader"
    assert strip_seniority("Engineering Leadership") == "Engineering Leadership"


def test_roman_three_stripped_whole_not_partially() -> None:
    # 'Engineer III' -> 'Engineer'; III is stripped as a whole, never leaving a partial 'I'/'II'.
    assert strip_seniority("Engineer III") == "Engineer"
    assert strip_seniority("Engineer II") == "Engineer"


def test_multiple_seniority_tokens_all_stripped() -> None:
    assert strip_seniority("Senior Staff Backend Engineer") == "Backend Engineer"


def test_no_seniority_unchanged() -> None:
    assert strip_seniority("Backend Engineer") == "Backend Engineer"
    assert strip_seniority("Data Engineer") == "Data Engineer"


def test_sr_with_period_stripped() -> None:
    assert strip_seniority("Sr. iOS Engineer") == "iOS Engineer"


def test_output_never_contains_a_seniority_token() -> None:
    for title in (
        "Senior iOS Engineer",
        "Principal Staff Security Engineer II",
        "Distinguished Backend Engineer III",
        "Sr. Lead Data Engineer",
    ):
        out = strip_seniority(title).lower().split()
        assert not (set(out) & set(_SENIORITY))


# --- resolve_title -------------------------------------------------------------------


def _persona(title: str, families: tuple[str, ...]) -> Persona:
    return Persona(
        id="p",
        title=title,
        default=True,
        role_families=families,
        skill_group_order=(),
        entries=None,
    )


def test_in_family_senior_title_yields_stripped_headline() -> None:
    ios = _persona("iOS Engineer", ("mobile",))
    assert resolve_title("Senior iOS Engineer", ios) == "iOS Engineer"


def test_out_of_family_falls_back_to_persona_title() -> None:
    # A backend persona given a mobile JD title: the stripped 'iOS Engineer' classifies as
    # mobile, not in the persona's families, so fall back to the persona base title.
    backend = _persona("Software Engineer", ("backend",))
    assert resolve_title("Senior iOS Engineer", backend) == "Software Engineer"


def test_empty_jd_title_falls_back_to_persona_title() -> None:
    p = _persona("Software Engineer", ("general_swe",))
    assert resolve_title("", p) == "Software Engineer"
    assert resolve_title("   ", p) == "Software Engineer"


def test_resolved_title_never_contains_a_seniority_token() -> None:
    ios = _persona("iOS Engineer", ("mobile",))
    out = resolve_title("Senior Staff iOS Engineer", ios).lower().split()
    assert not (set(out) & set(_SENIORITY))
