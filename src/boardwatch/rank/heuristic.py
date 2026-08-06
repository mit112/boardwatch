"""On-demand ranking (§3.7, D17): nothing persisted, no IDF; weights are read
from config at call time, so changing weights/taxonomy/profile simply changes
the next output — invalidation is a non-problem by construction.

title_match (§11 sign-off): max over target titles of
rapidfuzz.fuzz.token_set_ratio(posting_title, target, processor=default_process) / 100,
with a generic-token guard (P12 daily-driver finding): a target whose only shared
tokens with the posting are generic filler ("engineer"/"developer"/seniority/numerals)
is skipped, so "Field Service Engineer" no longer inherits ~0.80 off the lone "Engineer"
token. skill_coverage() itself is untouched, so genuine SWE postings whose skills the
taxonomy missed are still never punished.
The exclude-title hard veto is separate from scoring: exact-substring,
case-folded. Undefined components renormalize over the remaining weights
(§3.6; undefined triggers per plan deviation 7) — with one exception: a posting with no
recognized skills at all takes a neutral imputed coverage instead, because renormalizing
that component away is a promotion rather than a neutral act (see score_posting).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from boardwatch.core.settings import RankWeights


@dataclass(frozen=True)
class ProfileView:
    skills: frozenset[str]
    target_titles: tuple[str, ...]
    exclude_titles: tuple[str, ...]
    locations: tuple[str, ...]
    remote_only: bool


def profile_view_from_row(row: object) -> ProfileView:
    return ProfileView(
        skills=frozenset(getattr(row, "skills_json", None) or []),
        target_titles=tuple(getattr(row, "target_titles_json", None) or []),
        exclude_titles=tuple(getattr(row, "exclude_titles_json", None) or []),
        locations=tuple(getattr(row, "locations_json", None) or []),
        remote_only=bool(getattr(row, "remote_only", False)),
    )


@dataclass(frozen=True)
class Component:
    value: float | None  # None == undefined -> renormalized away
    weight: float
    detail: str


@dataclass(frozen=True)
class Score:
    total: float
    components: dict[str, Component]
    covered: int
    posting_skill_count: int


# Filler tokens common to nearly every engineering title; a match on these alone
# (e.g. "Field Service Engineer" vs "Software Engineer") is not a real title match.
GENERIC_TITLE_TOKENS = frozenset(
    {
        "engineer",
        "developer",
        "senior",
        "sr",
        "staff",
        "principal",
        "lead",
        "junior",
        "jr",
        "associate",
        "new",
        "grad",
        "i",
        "ii",
        "iii",
        "iv",
        "1",
        "2",
        "3",
        "4",
    }
)


def title_match(posting_title: str, target_titles: Sequence[str]) -> float | None:
    if not target_titles:
        return None  # undefined -> renormalize (consistent with the zero-skill rule)
    posting_tokens = set(default_process(posting_title).split())
    best = 0.0
    for target in target_titles:
        shared = posting_tokens & set(default_process(target).split())
        # Shares tokens with this target, but all of them are generic filler:
        # skip its (otherwise generous) token_set_ratio. Targets that share a
        # meaningful token, or share nothing at all, still score by fuzzy ratio.
        if shared and not (shared - GENERIC_TITLE_TOKENS):
            continue
        ratio = fuzz.token_set_ratio(posting_title, target, processor=default_process)
        best = max(best, ratio / 100.0)
    return best


def skill_coverage(
    profile_skills: frozenset[str], posting_skills: set[str]
) -> tuple[float | None, int, int]:
    if not posting_skills or not profile_skills:
        return None, 0, len(posting_skills)
    covered = len(profile_skills & posting_skills)
    return covered / len(posting_skills), covered, len(posting_skills)


def recency(posted_at: datetime | None, now: datetime, half_life_days: float) -> float | None:
    if posted_at is None:
        return None
    age_days = max((now - posted_at).total_seconds() / 86400.0, 0.0)
    return math.exp(-math.log(2.0) * age_days / half_life_days)


def location_fit(
    posting_locations: Sequence[str], remote_policy: str, profile: ProfileView
) -> float | None:
    if not profile.locations and not profile.remote_only:
        return None
    if profile.remote_only:  # remote-only preference takes precedence
        return 1.0 if remote_policy == "remote" else 0.0
    folded = [loc.casefold() for loc in posting_locations]
    for want in profile.locations:
        w = want.casefold()
        if any(w in loc or loc in w for loc in folded):
            return 1.0
    if remote_policy == "remote":
        return 0.5
    return 0.0


def passes_hard_filters(
    posting_title: str,
    posting_locations: Sequence[str],
    remote_policy: str,
    profile: ProfileView,
    location_filter_mode: str,
) -> bool:
    folded_title = posting_title.casefold()
    for excluded in profile.exclude_titles:
        if excluded.casefold() in folded_title:  # exact-substring, case-folded veto (§6.1)
            return False
    if location_filter_mode == "hard":
        fit = location_fit(posting_locations, remote_policy, profile)
        if fit == 0.0:
            return False
    return True


def score_posting(
    profile: ProfileView,
    posting_skills: set[str],
    posting_title: str,
    posted_at: datetime | None,
    posting_locations: Sequence[str],
    remote_policy: str,
    weights: RankWeights,
    now: datetime,
    half_life_days: float = 14.0,
    zero_skill_prior: float = 0.50,
) -> Score:
    coverage_value, covered, skill_count = skill_coverage(profile.skills, posting_skills)
    if coverage_value is not None:
        coverage_detail = f"covers {covered}/{skill_count} skills"
    elif not posting_skills and profile.skills:
        # Impute rather than renormalize (§3.6). Renormalizing is arithmetically identical
        # to imputing the weighted mean of the surviving components — a promotion, not a
        # neutral act, whenever coverage would have scored below that mean. A neutral prior
        # is what "never a punitive 0 or free 1" actually asks for. skill_coverage() itself
        # is unchanged: the component is undefined, and this is the ranker's stated
        # assumption about it.
        coverage_value = zero_skill_prior
        coverage_detail = (
            "no recognized skills in this posting — "
            f"coverage assumed neutral ({zero_skill_prior:.2f})"
        )
    elif not posting_skills:
        # Nothing on EITHER side: there is no comparison to be neutral about, so this
        # renormalizes and a profile with no other signals still reads "no ranking
        # signals" (plan deviation 7) rather than a flat prior on every posting.
        coverage_detail = "no recognized skills in this posting"
    else:
        # Profile-side emptiness keeps renormalizing, per §3.6's own wording.
        coverage_detail = "no recognized skills in your profile"
    title_value = title_match(posting_title, profile.target_titles)
    recency_value = recency(posted_at, now, half_life_days)
    location_value = location_fit(posting_locations, remote_policy, profile)
    components = {
        "skill_coverage": Component(coverage_value, weights.skill_coverage, coverage_detail),
        "title_match": Component(
            title_value,
            weights.title_match,
            "best fuzzy match over target titles"
            if title_value is not None
            else "no target titles set",
        ),
        "recency": Component(
            recency_value,
            weights.recency,
            f"exp decay, half-life {half_life_days:g}d"
            if recency_value is not None
            else "posting date unknown",
        ),
        "location_fit": Component(
            location_value,
            weights.location_fit,
            "exact / remote-OK / mismatch -> 1 / 0.5 / 0"
            if location_value is not None
            else "no location preferences set",
        ),
    }
    defined = [c for c in components.values() if c.value is not None]
    weight_sum = sum(c.weight for c in defined)
    if not defined or weight_sum <= 0.0:
        total = 0.0  # "no ranking signals" (plan deviation 7)
    else:
        total = sum(c.value * c.weight for c in defined if c.value is not None) / weight_sum
    return Score(
        total=total, components=components, covered=covered, posting_skill_count=skill_count
    )
