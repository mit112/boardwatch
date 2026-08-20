"""Title role gate (P13, M2).

The ordering assertions are the point of this file. The deny patterns guard themselves
with `(?!.*\\bsoftware\\b)`, which only sees text to the RIGHT of the match, so a
denies-first gate vetoes "Software Quality Engineer" (it matches `quality engineer`,
looks right, and finds no "software" because the word is on the LEFT). 16 real software
titles were buried that way in the measured prototype. Rescue-first fixes all 16, and
these tests pin that ordering so it cannot silently regress.
"""

import pytest

from boardwatch.rank.role_gate import role_verdict

# Live false positives the gate exists to demote — all three surfaced in a real `top` run.
NOT_SWE_TITLES = [
    "Deal Strategist",
    "Asset Tracking Technician",
    "On Shift (IOS) Technology Development Engineer – Night Shift 6",
]

# Real software titles. A `not_swe` here is the exact failure mode — a silently hidden job.
NEVER_NOT_SWE_TITLES = [
    "Software Engineer I, Backend (Collections)",
    "Forward Deployed Software Engineer",  # a real protected zero-skill row
    "DevOps Engineer",
    "Machine Learning Engineer",
    "Software Quality Engineer",
    "Software Engineer II, Warehouse Automation",
    "Data Warehouse Engineer",
    "Site Reliability Engineer (Night Shift)",
    "Kernel Driver Engineer",
]


class TestVerdicts:
    @pytest.mark.parametrize("title", NOT_SWE_TITLES)
    def test_noise_titles_are_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert reason  # never silent: the veto always names what it matched

    @pytest.mark.parametrize("title", NEVER_NOT_SWE_TITLES)
    def test_software_titles_are_never_vetoed(self, title: str) -> None:
        # `swe` or `uncertain` both pass: `uncertain` falls through to scoring unchanged,
        # which is why the gate retains 100% of the protected population.
        assert role_verdict(title)[0] != "not_swe"

    def test_uncertain_is_reachable_and_reasoned(self) -> None:
        verdict, reason = role_verdict("Data Warehouse Engineer")
        assert verdict == "uncertain"
        assert reason == "no role signal in title"


class TestOrdering:
    """Rescue runs BEFORE denies. Each of these matches a deny pattern textually."""

    def test_software_test_engineer_is_swe(self) -> None:
        # Matches `(test|validation|verification|quality) engineer`, whose trailing
        # lookahead cannot see the "Software" to its left. Rescue-first is what saves it.
        assert role_verdict("Software Test Engineer")[0] == "swe"

    def test_software_quality_engineer_is_swe(self) -> None:
        assert role_verdict("Software Quality Engineer")[0] == "swe"

    def test_night_shift_deny_loses_to_the_rescue(self) -> None:
        # "(night|day|swing|weekend) shift" is a hard deny; `site reliability` rescues first.
        assert role_verdict("Site Reliability Engineer (Night Shift)")[0] == "swe"
        # ...and with no software signal, the same deny still fires.
        assert role_verdict("Production Associate – Night Shift")[0] == "not_swe"

    def test_soft_denies_are_skipped_when_the_title_signals_software(self) -> None:
        # `consultant(?!.*software)` is a SOFT deny: it applies only to titles with no
        # software signal at all, so a signal-matched title is never reached by it.
        assert role_verdict("Consultant")[0] == "not_swe"
        assert role_verdict("Machine Learning Engineer, Consultant Tools")[0] == "swe"


class TestPrecisionAdditions:
    """Consistency gaps closed (D-252): the gate denied 'Solutions Engineer' but not
    'Solutions Architect', denied 'field support engineer' but not 'technical support
    engineer', and let sales 'Development Representative' through. All are pre-sales / support /
    sales by definition, and all sit in the SOFT deny lane, so a real software title with a
    signal or a rescue is never reached by them."""

    @pytest.mark.parametrize(
        "title",
        [
            "Solutions Architect",
            "Enterprise Solutions Architect",
            "AI Solutions Architect",
            "Pre-Sales Architect",
            "Sales Development Representative",
            "Business Development Representative",
            "Partner Development Manager",
            "Technical Support Engineer",
            "Customer Support Engineer",
            "IT Support Engineer",
        ],
    )
    def test_presales_support_sales_titles_are_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] == "not_swe"

    @pytest.mark.parametrize(
        "title",
        [
            "Software Architect",  # rescued before any deny
            "Backend Software Engineer",
            "Software Development Manager",  # 'software development' is a signal
            "Software Support Engineer",  # rescued: software-first
            "Developer Support Engineer",  # spared: not a customer/technical support role
            "Support Engineer",  # bare, ambiguous — stays uncertain, not vetoed
        ],
    )
    def test_real_or_ambiguous_software_titles_are_not_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"

    def test_sw_engineer_abbreviation_is_software(self) -> None:
        # "SW Engineer" is unambiguously software; "SW" alone (=southwest) is not added.
        assert role_verdict("SW Engineer")[0] == "swe"


class TestNarrowedPatterns:
    """Patterns the audit dropped or narrowed stay dropped, and what they were dropped
    FOR still gets vetoed by the rest of the list."""

    @pytest.mark.parametrize(
        "title", ["Engineer, Retail Systems", "Backend Engineer, Manufacturing Cloud"]
    )
    def test_dropped_bare_domain_nouns_no_longer_veto(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"

    @pytest.mark.parametrize(
        "title",
        [
            "Retail Sales Associate",
            "Warehouse Operations",
            "Truck Driver",
            "Financial Controller",
            "Research Fellow",
        ],
    )
    def test_the_noise_those_patterns_caught_is_still_caught(self, title: str) -> None:
        assert role_verdict(title)[0] == "not_swe"


class TestAuditability:
    def test_reason_names_the_matched_title_text(self) -> None:
        # Mit's stated fear is a gate that silently hides a real job. The reason has to be
        # checkable against the posting, so it quotes the text that decided the verdict.
        _, reason = role_verdict("Asset Tracking Technician")
        assert 'matched "Technician"' in reason

    @pytest.mark.parametrize(
        "title", NOT_SWE_TITLES + NEVER_NOT_SWE_TITLES + ["Data Warehouse Engineer"]
    )
    def test_every_reason_is_one_line(self, title: str) -> None:
        assert "\n" not in role_verdict(title)[1]


class TestLiveRunNarrowings:
    """Two patterns whose ONLY veto across 7,745 live postings was a real software job.
    Same marginal-veto criterion the original pattern audit used."""

    @pytest.mark.parametrize(
        "title", ["iOS Tooling Engineer", "Consultant Developer (Kotlin + Java) Hybrid position"]
    )
    def test_live_false_positives_are_released(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"

    @pytest.mark.parametrize("title", ["Tooling Technician", "Solutions Consultant, Mid-Market"])
    def test_the_manufacturing_and_gtm_readings_are_still_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] == "not_swe"


class TestCoordinatorDeny:
    """A bare `… Coordinator` with no engineering noun is not a software role (D-245).

    Measured 2026-08-19 over 26,997 live open postings: 135 postings / 125 distinct titles
    flip `uncertain` -> `not_swe`, and ZERO `swe`-classified titles contain `coordinator`,
    so the deny cannot bury a software job.
    """

    @pytest.mark.parametrize("title", [
        "Disaster Response Coordinator",          # the D-245 lead
        "Talent Coordinator",
        "Workplace Coordinator",
        "People Ops Coordinator",
        "Coordinator, Content Operations",
    ])
    def test_bare_coordinator_is_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert "coordinator" in reason.lower()

    @pytest.mark.parametrize("title", [
        # The _NOENG guard spares anything carrying an engineering noun anywhere.
        "Administrative Coordinator - College of Engineering - Information Networking Institute",
        "Student Program Coordinator, Engineering Student Success Center",
        # A real software title must never reach the soft denies at all.
        "Software Engineer, Release Coordinator Tooling",
    ])
    def test_engineering_titles_are_never_vetoed_by_the_coordinator_deny(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"


class TestManagerDirectorDeny:
    """A bare `... Manager` / `... Director` with no engineering noun is not a software role.

    Owner decision (2026-08-20): hard-exclude non-engineering management. The `_NOENG`
    anchored guard spares any title carrying engineer/engineering/developer/architect/
    programmer/swe/sde/sdet, so engineering managers and directors are never vetoed. The
    pattern sits in the SOFT lane, so a rescued or signalled software title never reaches it.
    """

    @pytest.mark.parametrize("title", [
        "Director of Operations",
        "General Manager",
        "Regional Manager",
        "Delivery Manager",
        "Technical Director",
    ])
    def test_non_engineering_managers_and_directors_are_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert "manager" in reason.lower() or "director" in reason.lower()

    @pytest.mark.parametrize("title", [
        "Engineering Manager",            # carries an engineering noun -> spared
        "Software Engineering Manager",   # rescued software-first
        "Director of Engineering",        # carries an engineering noun -> spared
        "Software Development Manager",   # 'software development' rescues before any deny
    ])
    def test_engineering_managers_and_directors_are_never_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"


class TestDataRolesOutOfScope:
    """Data Scientist / Data Analyst are out of scope (owner decision, 2026-08-20): they are
    not software-engineering roles. Data *engineering* stays in scope -- the deny needs the
    literal `scientist`/`analyst` token, so it cannot touch a `... Engineer` title.
    """

    @pytest.mark.parametrize("title", [
        "Data Scientist",
        "Senior Data Scientist",
        "Data Analyst",
        "Lead Data Analyst",
    ])
    def test_data_science_and_analyst_titles_are_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert reason  # never silent: the veto names what it matched

    @pytest.mark.parametrize("title", [
        "Data Engineer",
        "Data Platform Engineer",
        "Machine Learning Engineer",
        "Data Warehouse Engineer",  # no signal -> stays uncertain, still not vetoed
    ])
    def test_data_engineering_titles_are_never_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"
