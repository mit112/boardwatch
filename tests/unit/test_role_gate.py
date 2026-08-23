"""Title role gate (P13, M2).

The ordering assertions are the point of this file. The deny patterns guard themselves
with `(?!.*\\bsoftware\\b)`, which only sees text to the RIGHT of the match, so a
denies-first gate vetoes "Software Quality Engineer" (it matches `quality engineer`,
looks right, and finds no "software" because the word is on the LEFT). 16 real software
titles were buried that way in the measured prototype. Rescue-first fixes all 16, and
these tests pin that ordering so it cannot silently regress.
"""

import re

import pytest

from boardwatch.rank import role_gate
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


class TestBusinessOpsDeny:
    """Non-software business / ops / admin / pricing surfaces that leaked into run 63's ranked
    pool (owner decision, 2026-08-20). All SOFT-lane, so a rescued or signalled software title
    is never reached; the engineer-guard spares a real IC variant like 'Business Operations
    Engineer' where one plausibly exists.
    """

    @pytest.mark.parametrize("title", [
        "Strategy & Ops, Enterprise",
        "Strategy and Operations",
        "Business Operations Associate",
        "Business Partner Analyst",
        "Stock Plan Administrator",
        "Trucking Pricing Associate",
        "Pricing Analyst",
    ])
    def test_business_ops_titles_are_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert reason  # never silent

    @pytest.mark.parametrize("title", [
        "Software Engineer, Pricing Platform",   # rescued software-first
        "Business Operations Engineer",          # engineer-guarded -> not vetoed
        "Platform Engineer, Business Systems",   # signalled software
        "Software Engineer, Strategy Tools",     # rescued
    ])
    def test_real_software_titles_are_not_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"


class TestBareLeadDeny:
    """A bare `... Lead` / `Lead, ...` with no engineering noun is not a software role.

    Run 65 regression (2026-08-20): the precision pass removed bare `Lead` from the operator's
    `exclude_titles` (it over-vetoed product nouns) and compensated the parallel `Manager` /
    `Director` removal with the `_NOENG` management deny above -- but `Lead` was left with no
    gate, so business / ops "Lead" titles (Technical Account Management, Programs Operations,
    Insights) passed both stages and crowded real software roles out under the top-N cap. `lead`
    is the exact mirror of the manager/director deny: the `_NOENG` anchor spares any title
    carrying an engineering noun, and the SOFT lane keeps a rescued or signalled software title
    out of reach.
    """

    @pytest.mark.parametrize("title", [
        "Lead, Technical Account Management (SMB Merchants)",  # run-65 leak
        "Programs Operations Lead, Growth Levers",             # run-65 leak
        "Insights Lead, Instacart Business",                   # run-65 leak
        "Product Lead",
    ])
    def test_non_engineering_lead_titles_are_vetoed(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe"
        assert "lead" in reason.lower()

    @pytest.mark.parametrize("title", [
        "Lead Software Engineer",                     # rescued software-first
        "Lead Engineer",                              # carries an engineering noun -> spared
        "Engineering Lead",                           # carries an engineering noun -> spared
        "Software Engineer, Lead Scoring Platform",   # product noun 'Lead' -> rescued
    ])
    def test_engineering_lead_titles_are_never_vetoed(self, title: str) -> None:
        assert role_verdict(title)[0] != "not_swe"


class TestOwnerRulingNonSoftwareFamilies:
    """Ruling 1 (D-294): deny the non-software title families that dominate the shortlist.

    Measured before the change: 51.1% of everything clearing every other filter carried no
    software signal at all. These are the families it was made of.
    """

    @pytest.mark.parametrize(
        "title",
        [
            # Retail floor and store operations.
            "General Merchandise Team Leader",
            "Service & Engagement Team Leader",
            "Assets Protection Specialist",
            "Fulfillment Specialist",
            "Mobile Associate, Store-in-Store",
            "Sr Mobile Expert",
            # Food service.
            "Food & Beverage Team Leader",
            "Kitchen Operations Associate, DashMart",
            # People, admin and finance surfaces.
            "Human Resource Expert",
            "Administrative Coordinator",
            "Accounts Payable Specialist",
            "Strategic Finance Manager",
            # Clinical.
            "Patient Journey Partner",
            "Clinical Operations Manager",
            # Silicon: chip design, fab process and test.
            "ASIC Design Engineer",
            "CPU Physical Design Engineer",
            "Analog Circuit Design Engineer",
            "Senior CPU RTL Design Engineer",
            "Packaging Module Development Engineer",
            "Process Integration Development Engineer",
            "Package Failure Analysis Engineer",
            "ATE Test Development Engineer",
            "Shift Yield Defect Metrology Engineer",
            "Manufacturing Operator 1",
            # Telecom outside plant and cell sites.
            "Cell Site Engineer",
            "Outside Plant Engineer",
            # Technical marketing is marketing.
            "Technical Marketing Engineer",
        ],
    )
    def test_family_titles_are_denied(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe", (title, reason)

    @pytest.mark.parametrize(
        "title",
        [
            # A guarded business/commerce surface must not bury the software team that owns
            # it. Order management, AP/AR and revenue operations are literal product-team
            # names at Shopify, Ramp, Coupa and Stripe.
            "Engineer, Order Management Platform",
            "Order Management Engineer",
            "Engineer, Accounts Payable Platform",
            "Engineer, Revenue Operations",
            "Administrative Specialist, School of Engineering",
            "Finance Manager, Engineering",
            # Health-tech product areas. These went into the SOFT lane precisely so a
            # signalled software title skips them.
            "Senior Data Engineer, Patient Experience",
            "ML Engineer, Patient Experience",
            "Data Engineer, Clinical Operations",
            "Platform Engineer, Clinical Operations",
            "Software Engineer, Patient Experience",
        ],
    )
    def test_software_titles_on_those_surfaces_survive(self, title: str) -> None:
        """`!= "not_swe"` and not `== "swe"` on purpose, and the difference is real.

        Most of these land on `uncertain`, not `swe`: `_TITLE_SWE_SIGNAL` requires an
        adjacency, so a bare `Engineer` head noun beside a business noun is not a positive
        software signal. `uncertain` still passes through to scoring, which is the property
        under test — the guard must stop the veto, not manufacture a signal.
        """
        verdict, reason = role_verdict(title)
        assert verdict != "not_swe", (title, reason)


class TestOwnerRulingTeamLeader:
    """Ruling 2 (D-294): `Team Leader` is retail/ops, and blocking it must not cost a real
    software lead.

    The measurement that forced the SHAPE of this: five retail rows were classified `swe`
    because a store's checkout area is called the FRONT END and the bare token rescued them.
    The fix is in the rescue, not in a stage that outranks it — a deny evaluated before the
    rescue is reachable by every software title.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "Team Leader",
            "Closing Team Leader",
            "Beauty Team Leader",
            "Inbound Operations Team Leader",
            "Small Format Team Leader",
            # The rows that motivated the ruling: rescued on the bare `Front End` token before
            # the fix. Note they are denied by the pre-existing anchored `manager` deny once
            # the false rescue stops shielding them, NOT by the `team leader` pattern above --
            # which is why fixing the rescue was the right place and a pre-rescue lane was not.
            "Executive Team Leader Service & Engagement (Assistant Manager Front End)",
            "Executive Team Leader Service & Engagement (Assistant Manager Front End)- Cypress",
        ],
    )
    def test_retail_team_leaders_are_denied(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict == "not_swe", (title, reason)

    @pytest.mark.parametrize(
        "title",
        [
            # A head noun `_NOENG` can see.
            "Engineering Team Leader",
            "Software Team Leader",
            "Team Leader, Software Engineering",
            # ...and the SURFACE words it cannot: these carry no engineer/developer token, so
            # `_NOENG` alone would let the deny fire on a real software lead.
            "Backend Team Leader",
            "Team Leader, Backend",
            "Frontend Team Leader",
            "Full Stack Team Leader",
            "DevOps Team Leader",
            "SRE Team Leader",
            "Site Reliability Team Leader",
            "Team Leader - Data Platform",
            "Team Leader Machine Learning",
            "QA Automation Team Leader",
            "Web Development Team Leader",
        ],
    )
    def test_software_team_leaders_are_never_denied(self, title: str) -> None:
        verdict, reason = role_verdict(title)
        assert verdict != "not_swe", (title, reason)

    def test_front_end_still_rescues_a_real_front_end_role(self) -> None:
        for title in (
            "Front End Engineer",
            "Frontend Developer",
            "Front-End Software Engineer",
            "Full Stack Java Developer - Vice President",
            "Senior Backend Java Engineer - Aladdin Engineering, Vice President",
            "AI/ML Agent Engineer - Front-End Focus",
        ):
            assert role_verdict(title)[0] == "swe", title


class TestGuardedPatternsGuardEveryBranch:
    """An anchored PREFIX guard applied to a top-level alternation guards only the first branch.

    `_NOENG + r"\bA\b|\bB\b"` parses as `(guard.*A)|(B)`, so B is unguarded and can veto an
    engineering title from the left — the exact failure the guard exists to prevent. This is a
    property of every prefix-guarded pattern in the module, so it is asserted structurally
    rather than by naming titles one at a time.

    SCOPE, stated because a check whose reach is overestimated is worse than none: this covers
    `^(?!...)` PREFIX guards only. The mirror shape — a TRAILING `(?!...)` that binds to the last
    branch instead of all of them — exists at the `fellow`/`fellowship`/`postdoc` pattern in
    `_DENY_BUSINESS_HARD` and is NOT covered here. That one is pre-existing, its practical
    exposure is "Engineering Fellowship" (the rescue already protects "Software Engineering
    …"), and changing a shipped deny pattern's semantics needs its own ruling — recorded in
    D-294 rather than fixed in passing.
    """

    @staticmethod
    def _top_level_alternation_after_guard(pattern: str) -> bool:
        """Does a prefix-guarded pattern have a `|` outside every group?

        Character classes and escaped parens are stripped first. Counting raw `(` and `)` gets
        both wrong: `[)]` is a literal paren that would unbalance the depth counter and hide a
        real unguarded branch, and `[|]` is a literal pipe that would be reported as one.
        """
        if not pattern.startswith("^(?!"):
            return False
        body = pattern[pattern.index(").*") + 3 :]
        body = re.sub(r"\\.", "", body)  # drop escapes, so `\(` and `\|` are not read as syntax
        body = re.sub(r"\[[^]]*]", "", body)  # drop character classes wholesale
        depth = 0
        for char in body:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "|" and depth == 0:
                return True
        return False

    def test_no_prefix_guarded_pattern_has_an_unguarded_alternative(self) -> None:
        offenders = [
            pattern.pattern
            for pattern in (*role_gate._DENY_HARD, *role_gate._DENY_SOFT)
            if self._top_level_alternation_after_guard(pattern.pattern)
        ]
        assert offenders == []

    def test_the_detector_catches_the_bug_it_is_looking_for(self) -> None:
        """A structural check that cannot fire is decoration. These are its known positives."""
        detect = self._top_level_alternation_after_guard
        assert detect(role_gate._NOENG + r"\bfoo\b|\bbar\b") is True
        # ...and it is not fooled by a literal paren or a literal pipe.
        assert detect(role_gate._NOENG + r"\bfoo[)]\b|\bengineer\s+bar\b") is True
        assert detect(role_gate._NOENG + r"\bfoo[|]bar\b") is False
        assert detect(role_gate._NOENG + r"\bfoo\(x\|y\)bar\b") is False
        assert detect(role_gate._NOENG + r"\b(?:foo|bar)\b") is False
        assert detect(r"\bunguarded\b|\banything\b") is False  # no prefix guard at all
