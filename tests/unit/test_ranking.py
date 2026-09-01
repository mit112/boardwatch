from datetime import datetime, timedelta
from pathlib import Path

import pytest

from boardwatch.core.settings import RankWeights, Settings
from boardwatch.rank.explain import explain, why_summary
from boardwatch.rank.heuristic import (
    ProfileView,
    location_fit,
    passes_hard_filters,
    recency,
    score_posting,
    skill_coverage,
    title_match,
)

NOW = datetime(2026, 6, 11, 12, 0, 0)


def _profile(**overrides: object) -> ProfileView:
    base: dict[str, object] = {
        "skills": frozenset({"Python", "Go", "PostgreSQL"}),
        "target_titles": ("Backend Engineer",),
        "exclude_titles": (),
        "locations": ("New York",),
        "remote_only": False,
    }
    base.update(overrides)
    return ProfileView(**base)  # type: ignore[arg-type]


class TestTitleMatch:
    """§11 sign-off: max over targets of token_set_ratio(posting, target,
    processor=default_process) / 100."""

    def test_reordered_tokens_score_exactly_one(self) -> None:
        assert title_match("Software Engineer, Backend", ("Backend Software Engineer",)) == 1.0

    def test_default_process_strips_punctuation_and_case(self) -> None:
        assert title_match("SR. SOFTWARE ENGINEER (BACKEND)", ("sr software engineer backend",)) == 1.0

    def test_token_subset_scores_one_documented(self) -> None:
        # token_set_ratio gives 100 when one title's tokens are a subset of the
        # other's — documented behavior, not a bug.
        assert title_match("Senior Backend Engineer", ("Backend Engineer",)) == 1.0

    def test_max_over_multiple_targets(self) -> None:
        assert title_match("Backend Engineer", ("Data Scientist", "Backend Engineer")) == 1.0

    def test_unrelated_title_scores_low_but_in_range(self) -> None:
        score = title_match("Marketing Manager", ("Backend Engineer",))
        assert score is not None
        assert 0.0 <= score < 0.8

    def test_empty_target_list_is_undefined(self) -> None:
        assert title_match("Backend Engineer", ()) is None

    def test_generic_only_shared_token_scores_zero(self) -> None:
        # P12 daily-driver finding: a posting that shares only a generic filler
        # token ("engineer") with every target is NOT a title match — token_set_ratio
        # would otherwise hand "Field Service Engineer" ~0.80 off the lone "Engineer".
        assert (
            title_match(
                "Field Service Engineer", ("Software Engineer", "Backend Engineer")
            )
            == 0.0
        )
        assert title_match("Control Systems Engineer", ("Software Engineer",)) == 0.0

    def test_meaningful_shared_token_still_matches(self) -> None:
        # A real domain token ("software") survives the guard and scores high even
        # when the posting carries extra tokens.
        assert title_match("Software Engineer, Money Movement", ("Software Engineer",)) == 1.0
        assert title_match("Forward Deployed Software Engineer", ("Software Engineer",)) == 1.0


class TestSkillCoverage:
    def test_uniform_coverage_fraction(self) -> None:
        value, covered, total = skill_coverage(
            frozenset({"Python", "Go", "PostgreSQL"}), {"Python", "Go", "Kubernetes"}
        )
        assert value == pytest.approx(2 / 3)
        assert (covered, total) == (2, 3)

    def test_posting_without_skills_is_undefined(self) -> None:
        # The FUNCTION's contract is unchanged by the imputation: the component really is
        # undefined here. score_posting() is where the neutral assumption is applied and
        # stated, so `show`/`why` can name it as an assumption rather than a measurement.
        value, _, _ = skill_coverage(frozenset({"Python"}), set())
        assert value is None  # neutral, never a punitive 0 or a free 1 (§3.6)

    def test_profile_without_skills_is_undefined(self) -> None:
        value, _, _ = skill_coverage(frozenset(), {"Python"})
        assert value is None


class TestRecency:
    def test_half_life_pinned(self) -> None:
        assert recency(NOW, NOW, 14.0) == pytest.approx(1.0)
        assert recency(NOW - timedelta(days=14), NOW, 14.0) == pytest.approx(0.5)
        assert recency(NOW - timedelta(days=28), NOW, 14.0) == pytest.approx(0.25)

    def test_missing_posted_at_is_undefined(self) -> None:
        assert recency(None, NOW, 14.0) is None


class TestLocationFit:
    def test_exact_remote_ok_mismatch(self) -> None:
        profile = _profile()
        assert location_fit(["New York, NY"], "unknown", profile) == 1.0
        assert location_fit(["San Francisco"], "remote", profile) == 0.5
        assert location_fit(["San Francisco"], "unknown", profile) == 0.0

    def test_no_preferences_is_undefined(self) -> None:
        profile = _profile(locations=(), remote_only=False)
        assert location_fit(["Anywhere"], "unknown", profile) is None

    def test_remote_only_takes_precedence(self) -> None:
        profile = _profile(remote_only=True)
        assert location_fit(["New York, NY"], "remote", profile) == 1.0
        assert location_fit(["New York, NY"], "unknown", profile) == 0.0


class TestZeroSkillImputation:
    """§3.6 says the zero-skill case is 'neutral, never a punitive 0 or free 1'.

    Renormalizing the component away satisfied only the first half: it is arithmetically
    identical to imputing the weighted MEAN of the surviving components (~0.96 on the rows
    that matter), which is the free 1 the rule forbids — 29 of 80 eligible zero-skill rows
    scored exactly 1.000. Imputing a neutral prior enforces §3.6 rather than reopening it.
    """

    def test_posting_without_skills_takes_the_neutral_prior(self) -> None:
        score = score_posting(
            _profile(), set(), "Backend Engineer", NOW, ["New York"], "unknown",
            RankWeights(), NOW,
        )
        assert score.components["skill_coverage"].value == pytest.approx(0.50)
        # coverage 0.50x0.50 + title 0.25 + recency 0.15 + location 0.10, over weight 1.0
        assert score.total == pytest.approx(0.75)

    def test_the_inversion_is_fixed(self) -> None:
        # THE defect this change exists to fix. Before imputation a posting with NO
        # recognized skills outscored a posting matching 7 of 8 (0.9586 vs 0.9168),
        # because dropping half the weight handed it to whatever else scored well.
        # Dropping a component is not neutral; it is a promotion.
        seven_of_eight = _profile(
            skills=frozenset({"Python", "Go", "PostgreSQL", "Redis", "Kafka", "AWS", "Docker"}),
            remote_only=True,
        )
        posted = NOW - timedelta(days=3)
        args = ("Backend Engineer", posted, ["Anywhere"], "remote", RankWeights(), NOW)
        zero_skill = score_posting(seven_of_eight, set(), *args)
        seven = score_posting(
            seven_of_eight,
            {"Python", "Go", "PostgreSQL", "Redis", "Kafka", "AWS", "Docker", "Rust"},
            *args,
        )
        assert zero_skill.total == pytest.approx(0.7293, abs=5e-5)
        # 7 of 8 shrinks to (7 + 0.50)/9 = 0.8333, not the raw 0.875 — the pseudo-count
        # applies here too. The inversion this class exists to pin is unaffected: the
        # zero-skill row still takes the prior, which is below any real majority match.
        assert seven.total == pytest.approx(0.8960, abs=5e-5)
        assert zero_skill.total < seven.total  # the inversion, pinned

    def test_prior_is_configurable_and_zero_is_not_the_default(self) -> None:
        args = (_profile(), set(), "Backend Engineer", NOW, ["New York"], "unknown")
        punitive = score_posting(*args, RankWeights(), NOW, 14.0, 0.0)
        assert punitive.components["skill_coverage"].value == 0.0
        # A punitive 0 is explicitly rejected by §3.6 — it would swing this population from
        # advantaged straight to buried. Guard against it silently becoming the default.
        assert score_posting(*args, RankWeights(), NOW).total != punitive.total
        assert Settings(data_dir=Path("d"), config_dir=Path("c")).zero_skill_coverage_prior == 0.50

    def test_all_zero_weights_score_zero_instead_of_crashing(self) -> None:
        """`weight_sum <= 0.0` is reachable from a LEGAL config, and nothing pinned it.

        `RankWeights` declares every weight `ge=0.0` with no "at least one must be positive"
        rule, and `boardwatch config` sets each one individually — so all four at 0.0 is a
        configuration a user can actually reach. Dropping `weight_sum <= 0.0` from the guard
        leaves the whole ranking suite green, yet the else-branch then divides by that sum:

            with the guard     -> total == 0.0
            without the guard  -> ZeroDivisionError: float division by zero

        The 0.0 is "no ranking signals" (plan deviation 7), which is the documented behaviour
        this pins. Ranking runs for every posting on every unattended night, so the crash would
        be per-run and total rather than partial.
        """
        zero = RankWeights(skill_coverage=0.0, title_match=0.0, recency=0.0, location_fit=0.0)
        args = (_profile(), {"Python"}, "Backend Engineer", NOW, ["New York"], "unknown")

        score = score_posting(*args, zero, NOW)

        assert score.total == 0.0
        # Guard: a non-zero weight set on the SAME inputs must score differently, or the
        # assertion above would hold for a scorer that always returned 0.
        assert score_posting(*args, RankWeights(), NOW).total != 0.0

    def test_why_line_stays_one_line_and_names_the_assumption(self) -> None:
        score = score_posting(
            _profile(), set(), "Backend Engineer", NOW - timedelta(days=2), ["New York"],
            "unknown", RankWeights(), NOW,
        )
        why = why_summary(score, NOW - timedelta(days=2), NOW)
        # Never "covers 0/0 skills": that would read as a measurement, not an assumption.
        assert why == "coverage assumed 0.50 · title · 2d"
        assert "\n" not in why


class TestCoverageShrinksTowardThePrior:
    """A coverage ratio is only as good as its denominator, and the denominator is whatever
    the taxonomy recognised in one JD.

    Measured over run 137's deliverable pool — the 5,029 open postings that cleared every
    quarantine and were not held by the ledger — 16 of the top 100 by score were postings the
    taxonomy read <=2 terms from, among them "Technical Product Owner (F/H)", "Global
    Financial Crimes - Compliance Testing, AVP" and "Enterprise Mobility Engineer". Each
    matched its single recognised term and so scored 1.00 on the component carrying half the
    weight. `taxonomy.yaml` records the same finding from the data side (four generic terms
    deleted because each, "as a posting's SOLE recognized skill ... degenerated
    skill_coverage to 1.0 on ops/finance roles"), which fixes three postings and leaves the
    next term to do it again.

    Weights below are written as LITERALS rather than `RankWeights()`: an assertion that reads
    the same defaults the scorer reads would still pass if both moved together.
    """

    def test_one_matched_term_out_of_one_is_not_a_perfect_fit(self) -> None:
        weights = RankWeights(
            skill_coverage=0.50, title_match=0.25, recency=0.15, location_fit=0.10
        )
        score = score_posting(
            _profile(skills=frozenset({"Python"})), {"Python"}, "Backend Engineer", NOW,
            ["New York"], "unknown", weights, NOW,
        )
        # (1 + 1.0 x 0.50) / (1 + 1.0). NOT 1.00.
        assert score.components["skill_coverage"].value == pytest.approx(0.75)
        assert score.covered == 1 and score.posting_skill_count == 1  # the evidence is intact

    def test_a_rich_posting_is_left_essentially_alone(self) -> None:
        """The claim that makes this a fix and not a re-weighting: it moves the thin end only."""
        weights = RankWeights(
            skill_coverage=0.50, title_match=0.25, recency=0.15, location_fit=0.10
        )
        profile_skills = frozenset(f"S{i:02d}" for i in range(1, 15))  # 14 skills
        posting_skills = {f"S{i:02d}" for i in range(1, 28)}  # 27 terms, 14 of them matched
        score = score_posting(
            _profile(skills=profile_skills), posting_skills, "Backend Engineer", NOW,
            ["New York"], "unknown", weights, NOW,
        )
        # (14 + 0.50) / 28 = 0.517857, against a raw 14/27 = 0.518519: a move of 0.00066.
        assert score.components["skill_coverage"].value == pytest.approx(0.517857, abs=5e-7)
        assert abs(score.components["skill_coverage"].value - 0.518519) < 0.001

    def test_a_one_term_posting_no_longer_outranks_a_richly_matched_one(self) -> None:
        """The ORDERING this change exists to fix.

        Both postings are posted now and sit in the same city, so recency and location_fit are
        identical and only coverage and title separate them. The thin one's title is barely a
        match (0.3077) and the rich one's is exact, and the thin one still won.
        """
        weights = RankWeights(
            skill_coverage=0.50, title_match=0.25, recency=0.15, location_fit=0.10
        )
        profile = _profile(skills=frozenset(f"S{i:02d}" for i in range(1, 15)))
        common = (NOW, ["New York"], "unknown", weights, NOW)
        thin = score_posting(profile, {"S01"}, "Technical Product Owner", *common)
        rich = score_posting(
            profile, {f"S{i:02d}" for i in range(1, 28)}, "Backend Engineer", *common
        )
        assert thin.total < rich.total
        assert thin.total == pytest.approx(0.701923, abs=5e-7)
        assert rich.total == pytest.approx(0.758929, abs=5e-7)

        # And the SAME call against the pre-change scorer, which is exactly
        # `coverage_pseudo_count=0.0`: the raw ratio, and the inversion is back.
        raw_thin = score_posting(profile, {"S01"}, "Technical Product Owner", *common, 14.0,
                                 0.50, 0.0)
        raw_rich = score_posting(
            profile, {f"S{i:02d}" for i in range(1, 28)}, "Backend Engineer", *common, 14.0,
            0.50, 0.0,
        )
        assert raw_thin.components["skill_coverage"].value == 1.0
        assert raw_thin.total > raw_rich.total  # the defect, pinned so the fix cannot lapse

    def test_the_pseudo_count_reduces_to_the_zero_skill_prior(self) -> None:
        """At skill_count=0 the formula IS the imputation, so the two rules cannot drift.

        Left as two branches in the source because `skill_coverage()` returns undefined when
        EITHER side is empty, and a profile with no skills must keep renormalizing rather than
        take a fabricated number — but the values must agree where they overlap.
        """
        weights = RankWeights(
            skill_coverage=0.50, title_match=0.25, recency=0.15, location_fit=0.10
        )
        imputed = score_posting(
            _profile(), set(), "Backend Engineer", NOW, ["New York"], "unknown", weights, NOW,
        )
        assert imputed.components["skill_coverage"].value == pytest.approx(0.50)
        # (0 + 1.0 x 0.50) / (0 + 1.0) == 0.50, the same number by the other route.
        assert (0 + 1.0 * 0.50) / (0 + 1.0) == 0.50


class TestRenormalization:
    def test_renormalized_weighted_mix(self) -> None:
        score = score_posting(
            _profile(skills=frozenset()), {"Python"}, "Backend Engineer",
            NOW - timedelta(days=14), ["San Francisco"], "unknown",
            RankWeights(), NOW,
        )
        # title 1.0x0.25 + recency 0.5x0.15 + location 0.0x0.10 over weight 0.50
        assert score.total == pytest.approx((0.25 + 0.075 + 0.0) / 0.50)

    def test_all_undefined_scores_zero(self) -> None:
        profile = _profile(skills=frozenset(), target_titles=(), locations=())
        score = score_posting(
            profile, set(), "Backend Engineer", None, [], "unknown", RankWeights(), NOW
        )
        assert score.total == 0.0

    def test_weight_changes_take_effect_at_call_time(self) -> None:
        # coverage 2/3 and recency 0.5**(7/14) differ from the other components,
        # so reweighting must change the total (an all-1.0 setup would be
        # renormalization-invariant and mask caching bugs).
        args = (
            _profile(), {"Python", "Go", "Kubernetes"}, "Backend Engineer",
            NOW - timedelta(days=7), ["New York"], "unknown",
        )
        default = score_posting(*args, RankWeights(), NOW)
        skewed = score_posting(
            *args,
            RankWeights(skill_coverage=0.97, title_match=0.01, recency=0.01, location_fit=0.01),
            NOW,
        )
        assert default.total != skewed.total  # no caching, no invalidation machinery (D17)

    def test_profile_without_skills_renormalizes_at_score_level(self) -> None:
        profile = _profile(skills=frozenset())
        score = score_posting(
            profile, {"Python", "Go"}, "Backend Engineer", NOW, ["New York"], "unknown",
            RankWeights(), NOW,
        )
        assert score.components["skill_coverage"].value is None
        assert score.total == pytest.approx(1.0)  # title, recency, location all 1.0

    def test_empty_target_titles_renormalize_at_score_level(self) -> None:
        profile = _profile(target_titles=())
        score = score_posting(
            profile, {"Python", "Go", "Kubernetes"}, "Anything", NOW, ["New York"], "unknown",
            RankWeights(), NOW,
        )
        assert score.components["title_match"].value is None
        # coverage (2+0.50)/(3+1)x0.50 + recency 1.0x0.15 + location 1.0x0.10, over weight 0.75
        assert score.total == pytest.approx((0.625 * 0.50 + 0.15 + 0.10) / 0.75)


class TestHardFilters:
    def test_exclude_title_veto_exact_substring_case_folded(self) -> None:
        profile = _profile(exclude_titles=("staff",))
        assert passes_hard_filters("Staff Software Engineer", ["NY"], "unknown", profile, "soft") is False
        assert passes_hard_filters("Senior Software Engineer", ["NY"], "unknown", profile, "soft") is True

    def test_hard_location_mode_drops_non_us_keeps_us_and_unknown(self) -> None:
        # D-251: hard mode is a US-only gate. A confirmed non-US posting drops; US is kept even
        # when it matches no profile location; an unclassifiable location is kept (fail-open,
        # Mit's ruling — never silently delete a real US role behind a weak location string).
        profile = _profile()
        assert passes_hard_filters("Backend Engineer", ["London, United Kingdom"], "unknown", profile, "hard") is False
        assert passes_hard_filters("Backend Engineer", ["San Francisco"], "unknown", profile, "hard") is True
        assert passes_hard_filters("Backend Engineer", ["New York, NY"], "unknown", profile, "hard") is True
        assert passes_hard_filters("Backend Engineer", ["Americas"], "unknown", profile, "hard") is True
        # soft mode never vetoes on location, non-US included
        assert passes_hard_filters("Backend Engineer", ["London, United Kingdom"], "unknown", profile, "soft") is True

    def test_hard_mode_drops_a_non_us_ad_convention_when_the_location_cannot_decide(self) -> None:
        # The GE HealthCare DACH postings: locations_json is exactly ["Remote"], so no location
        # catalog can ever reach them. The German title decides instead.
        profile = _profile()
        german = "Applikationsspezialist/in Molekulare Bildgebung DACH (w/m/d)"
        assert passes_hard_filters(german, ["Remote"], "remote", profile, "hard") is False
        assert passes_hard_filters(german, ["Buc"], "unknown", profile, "hard") is False
        # An English title in the same unclassifiable location is still KEPT — fail-open holds
        # for everything the ad-convention rule does not positively recognise.
        assert passes_hard_filters("Backend Engineer", ["Remote"], "remote", profile, "hard") is True

    def test_a_confirmed_us_location_outranks_a_non_us_ad_convention(self) -> None:
        # Belt and braces on the fail-safe direction: the ad marker only fires where the
        # location has NOT confirmed US, so a US-located posting with a German title is kept.
        # Zero such postings were observed in 28,287 open postings; this pins the direction.
        profile = _profile()
        german = "Software Entwickler (m/w/d)"
        assert passes_hard_filters(german, ["Austin, TX"], "unknown", profile, "hard") is True
        assert passes_hard_filters(german, ["US"], "unknown", profile, "hard") is True

    def test_soft_mode_never_vetoes_on_an_ad_convention(self) -> None:
        profile = _profile()
        german = "Applikationsspezialist/in Molekulare Bildgebung DACH (w/m/d)"
        assert passes_hard_filters(german, ["Remote"], "remote", profile, "soft") is True

    def test_hard_mode_with_remote_only(self) -> None:
        profile = _profile(remote_only=True)
        assert passes_hard_filters("Backend Engineer", ["NY"], "unknown", profile, "hard") is False
        assert passes_hard_filters("Backend Engineer", ["NY"], "remote", profile, "hard") is True


class TestExplain:
    def test_breakdown_rows_and_why_summary(self) -> None:
        score = score_posting(
            _profile(), {"Python", "Go", "Kubernetes"}, "Backend Engineer",
            NOW - timedelta(days=2), ["New York, NY"], "unknown", RankWeights(), NOW,
        )
        rows = explain(score)
        assert [r.component for r in rows] == [
            "skill_coverage", "title_match", "recency", "location_fit"
        ]
        coverage_row = rows[0]
        # The detail names BOTH the evidence and the shrinkage, because `raw` is no longer
        # covered/skill_count: a row reading "covers 2/3 skills" beside raw=0.625 would be an
        # explanation contradicting the number it explains.
        assert coverage_row.detail == (
            "covers 2/3 skills, shrunk toward 0.50 on 3 term(s) of evidence"
        )
        assert coverage_row.weighted == pytest.approx(0.625 * 0.50)
        # The one-line `why` still reports the raw counts, which are the measurement; the
        # shrinkage is an assumption about them and belongs in the breakdown, not the summary.
        assert why_summary(score, NOW - timedelta(days=2), NOW) == "covers 2/3 skills · title · 2d"

    def test_no_skills_message_names_the_assumed_value(self) -> None:
        score = score_posting(
            _profile(), set(), "Backend Engineer", NOW, ["New York"], "unknown",
            RankWeights(), NOW,
        )
        assert score.components["skill_coverage"].detail == (
            "no recognized skills in this posting — coverage assumed neutral (0.50)"
        )

    def test_no_skills_on_either_side_is_still_undefined(self) -> None:
        score = score_posting(
            _profile(skills=frozenset()), set(), "Backend Engineer", NOW, ["New York"],
            "unknown", RankWeights(), NOW,
        )
        assert score.components["skill_coverage"].value is None
        assert score.components["skill_coverage"].detail == "no recognized skills in this posting"


class TestHardFilterWordBoundaries:
    """`exclude_titles` vetoes on WORD boundaries, not substrings.

    Substring containment was the original rule and it silently deleted real jobs. Measured
    over 26,997 live open postings: `Sr` fired inside "Israel" and "SRE", `Staff` fired inside
    "Member of Technical Staff", and `III` could never fire at all because every title carrying
    it also carries `II`, which is tested first. 100 postings were dropped that no other gate
    in the repo would drop on the merits.

    Word boundaries are strictly narrower than containment, so this rule can only ever drop
    FEWER postings than before. `test_veto_is_monotonically_narrower` pins that direction.
    """

    def test_sr_does_not_fire_inside_israel(self) -> None:
        profile = _profile(exclude_titles=("Sr",))
        title = "Software Engineer - Figma Weave (Tel Aviv, Israel)"
        assert passes_hard_filters(title, ["Tel Aviv"], "unknown", profile, "soft") is True

    def test_sr_does_not_fire_inside_sre(self) -> None:
        profile = _profile(exclude_titles=("Sr",))
        assert (
            passes_hard_filters("SRE/Dev Ops Engineer", ["NY"], "unknown", profile, "soft") is True
        )

    def test_sr_still_vetoes_a_real_abbreviation(self) -> None:
        profile = _profile(exclude_titles=("Sr",))
        assert (
            passes_hard_filters("Sr. Software Engineer", ["NY"], "unknown", profile, "soft")
            is False
        )

    def test_roman_three_is_reachable_and_does_not_catch_two(self) -> None:
        """`III` was dead code under containment. It must fire, and only on itself."""
        profile = _profile(exclude_titles=("III",))
        assert (
            passes_hard_filters("Software Engineer III", ["NY"], "unknown", profile, "soft")
            is False
        )
        assert (
            passes_hard_filters("Software Engineer II", ["NY"], "unknown", profile, "soft") is True
        )

    def test_two_does_not_catch_three(self) -> None:
        profile = _profile(exclude_titles=("II",))
        assert (
            passes_hard_filters("Software Engineer II", ["NY"], "unknown", profile, "soft") is False
        )
        assert (
            passes_hard_filters("Software Engineer III", ["NY"], "unknown", profile, "soft") is True
        )

    def test_staff_does_not_fire_inside_member_of_technical_staff(self) -> None:
        """90 real software postings turned on this one phrase."""
        profile = _profile(exclude_titles=("Staff",))
        for title in (
            "Member of Technical Staff",
            "Member of Technical Staff (Software Engineer)",
            "Member of Technical Staff, MLE",
            "Members of Technical Staff",
        ):
            assert passes_hard_filters(title, ["NY"], "unknown", profile, "soft") is True, title

    def test_staff_still_vetoes_real_seniority(self) -> None:
        profile = _profile(exclude_titles=("Staff",))
        assert (
            passes_hard_filters("Staff Software Engineer", ["NY"], "unknown", profile, "soft")
            is False
        )

    def test_a_senior_word_outside_the_masked_phrase_still_vetoes(self) -> None:
        """Only the phrase is masked, never the whole title."""
        profile = _profile(exclude_titles=("Sr",))
        title = "Sr. Member of Technical Staff"
        assert passes_hard_filters(title, ["NY"], "unknown", profile, "soft") is False

    def test_multi_word_exclusions_still_match_as_phrases(self) -> None:
        profile = _profile(exclude_titles=("Field Service Engineer",))
        assert (
            passes_hard_filters("Field Service Engineer", ["NY"], "unknown", profile, "soft")
            is False
        )
        assert passes_hard_filters("Field Engineer", ["NY"], "unknown", profile, "soft") is True

    def test_veto_is_monotonically_narrower(self) -> None:
        """The new rule may never veto a title the substring rule let through."""
        excludes = (
            "Senior",
            "Sr",
            "Staff",
            "Principal",
            "Lead",
            "Manager",
            "Director",
            "II",
            "III",
            "Field Service Engineer",
            "Sales Engineer",
        )
        profile = _profile(exclude_titles=excludes)
        titles = (
            "Software Engineer",
            "Senior Software Engineer",
            "Sr. Backend Engineer",
            "Staff Software Engineer",
            "Member of Technical Staff",
            "SRE/Dev Ops Engineer",
            "Software Engineer II",
            "Software Engineer III",
            "Engineering Manager",
            "Software Engineer - Figma Weave (Tel Aviv, Israel)",
            "Sales Engineer",
            "Leadership Development Program",
            "Field Service Engineer",
        )
        for title in titles:
            folded = title.casefold()
            substring_vetoed = any(e.casefold() in folded for e in excludes)
            now_passes = passes_hard_filters(title, ["NY"], "unknown", profile, "soft")
            if not substring_vetoed:
                assert now_passes is True, f"newly vetoed, must not be: {title}"
