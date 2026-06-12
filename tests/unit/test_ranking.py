from datetime import datetime, timedelta

import pytest

from boardwatch.core.settings import RankWeights
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


class TestSkillCoverage:
    def test_uniform_coverage_fraction(self) -> None:
        value, covered, total = skill_coverage(
            frozenset({"Python", "Go", "PostgreSQL"}), {"Python", "Go", "Kubernetes"}
        )
        assert value == pytest.approx(2 / 3)
        assert (covered, total) == (2, 3)

    def test_posting_without_skills_is_undefined(self) -> None:
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


class TestRenormalization:
    def test_posting_without_skills_renormalizes(self) -> None:
        score = score_posting(
            _profile(), set(), "Backend Engineer", NOW, ["New York"], "unknown",
            RankWeights(), NOW,
        )
        # defined: title (1.0 x 0.25), recency (1.0 x 0.15), location (1.0 x 0.10)
        assert score.total == pytest.approx(1.0)
        assert score.components["skill_coverage"].value is None

    def test_renormalized_weighted_mix(self) -> None:
        score = score_posting(
            _profile(), set(), "Backend Engineer",
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
        # coverage (2/3)x0.50 + recency 1.0x0.15 + location 1.0x0.10, over weight 0.75
        assert score.total == pytest.approx(((2 / 3) * 0.50 + 0.15 + 0.10) / 0.75)


class TestHardFilters:
    def test_exclude_title_veto_exact_substring_case_folded(self) -> None:
        profile = _profile(exclude_titles=("staff",))
        assert passes_hard_filters("Staff Software Engineer", ["NY"], "unknown", profile, "soft") is False
        assert passes_hard_filters("Senior Software Engineer", ["NY"], "unknown", profile, "soft") is True

    def test_hard_location_mode_drops_mismatches(self) -> None:
        profile = _profile()
        assert passes_hard_filters("Backend Engineer", ["San Francisco"], "unknown", profile, "hard") is False
        assert passes_hard_filters("Backend Engineer", ["San Francisco"], "unknown", profile, "soft") is True
        assert passes_hard_filters("Backend Engineer", ["New York, NY"], "unknown", profile, "hard") is True

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
        assert coverage_row.detail == "covers 2/3 skills"
        assert coverage_row.weighted == pytest.approx((2 / 3) * 0.50)
        assert why_summary(score, NOW - timedelta(days=2), NOW) == "covers 2/3 skills · title · 2d"

    def test_no_skills_message_path(self) -> None:
        score = score_posting(
            _profile(), set(), "Backend Engineer", NOW, ["New York"], "unknown",
            RankWeights(), NOW,
        )
        assert score.components["skill_coverage"].detail == "no recognized skills in this posting"
