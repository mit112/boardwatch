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

skill_coverage is a RATIO, so it is only as trustworthy as its denominator, and the
denominator is whatever the taxonomy happened to recognise in one JD. `score_posting`
therefore shrinks it toward the same neutral prior by a pseudo-count before weighting it:
one matched term out of one recognised term is not a 1.00 fit, it is one observation.
Measured over the live deliverable pool, that ratio is the ranker's single largest source of
false positives at the head of the slate (see score_posting).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Literal

from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from boardwatch.core.settings import RankWeights
from boardwatch.rank.foreign_ad_gate import has_non_us_ad_marker
from boardwatch.rank.location_gate import classify_location
from boardwatch.rank.seniority_gate import mask_non_seniority_phrases


@dataclass(frozen=True)
class ProfileView:
    skills: frozenset[str]
    target_titles: tuple[str, ...]
    exclude_titles: tuple[str, ...]
    locations: tuple[str, ...]
    remote_only: bool
    # D-246. `notify` consumes ProfileView too, which is what makes wiring the second filter
    # chain cheap. Falls back to "any" (inert) so a row predating the migration is safe.
    target_seniority_band: str = "any"


def profile_view_from_row(row: object) -> ProfileView:
    return ProfileView(
        skills=frozenset(getattr(row, "skills_json", None) or []),
        target_titles=tuple(getattr(row, "target_titles_json", None) or []),
        exclude_titles=tuple(getattr(row, "exclude_titles_json", None) or []),
        locations=tuple(getattr(row, "locations_json", None) or []),
        remote_only=bool(getattr(row, "remote_only", False)),
        target_seniority_band=str(getattr(row, "target_seniority_band", None) or "any"),
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


@lru_cache(maxsize=256)
def _exclusion_pattern(excluded: str) -> re.Pattern[str]:
    """Compile one user exclusion into a case-insensitive, word-bounded matcher.

    `(?<!\\w)` / `(?!\\w)` rather than `\\b` because the exclusion is arbitrary user text: a
    profile carrying `Sr.` or `(contract)` starts or ends on a non-word character, where `\\b`
    asserts the opposite of what is wanted. Cached because `exclude_titles` is a short, stable
    list re-tested against every posting in the corpus — 26,997 times per run.
    """
    return re.compile(rf"(?<!\w){re.escape(excluded.strip())}(?!\w)", re.IGNORECASE)


# Closed catalog. `hidden_hard_filter` deliberately stays ONE bucket (D-251, D-264: a new
# bucket has >=27 hand-maintained mirror sites), so the clause rides on the ROW instead --
# which is what lets `top --include-hard-filter` say why without moving any mirror site.
HardFilterClause = Literal[
    "excluded_title",
    "remote_only",
    "non_us_location",
    "foreign_ad_marker",
]


@dataclass(frozen=True)
class HardFilterVeto:
    clause: HardFilterClause
    # The text that decided it: the profile entry that matched, or the location that
    # classified non-US. Never a rendered sentence -- callers format, this reports.
    detail: str


def hard_filter_verdict(
    posting_title: str,
    posting_locations: Sequence[str],
    remote_policy: str,
    profile: ProfileView,
    location_filter_mode: str,
) -> HardFilterVeto | None:
    """The veto that fired, or None if the posting cleared every clause.

    `passes_hard_filters` is a wrapper over this, so the bool and the reason can never
    disagree about the same title -- the failure mode that made the 2026-08-06 "100%
    exclude_titles" split survive 16 days after the config that produced it changed.
    """
    # Word-boundary veto (§6.1), NOT substring containment. Containment was the original rule
    # and it deleted real jobs in three ways, measured over 26,997 live open postings: `Sr` fired
    # inside "Israel" and "SRE" (10 postings), `Staff` fired inside "Member of Technical Staff"
    # (90), and `III` was unreachable because every title carrying it also carries `II`, which is
    # tested first. Those 100 are drops no other gate in this package would make on the merits.
    #
    # The phrase mask runs BEFORE matching, the same rescue-first ordering `role_gate` uses.
    # Without it `seniority_gate` and this function contradict each other on the same string:
    # the mask that package added to save MTS titles never got to run, because this veto is
    # upstream of both other gates (`top_cmd` calls it first).
    #
    # Both changes are strictly NARROWING — a word-boundary match is a subset of a containment
    # match, and masking only removes candidate text — so this can never veto a title the old
    # rule admitted. `test_veto_is_monotonically_narrower` pins that direction.
    #
    # Known limitation: a user who deliberately excludes "Member of Technical Staff" is defeated
    # by the mask. Left standing because the phrase is a POSITIVE software signal in `role_gate`,
    # so excluding it is self-contradicting; revisit if a real profile ever wants it.
    masked_title = mask_non_seniority_phrases(posting_title)
    for excluded in profile.exclude_titles:
        if _exclusion_pattern(excluded).search(masked_title):
            return HardFilterVeto("excluded_title", excluded)
    if location_filter_mode == "hard":
        # A remote-only profile keeps its non-remote veto (unchanged).
        if profile.remote_only and remote_policy != "remote":
            return HardFilterVeto("remote_only", f"remote_policy={remote_policy!r}")
        # US-only hard gate (D-251, Mit's visa requirement). `classify_location` is a positive
        # US allowlist, not a non-US denylist: it drops only a CONFIRMED non-US posting and
        # keeps both US and anything it cannot resolve — fail-open, so a real US role whose
        # location string is a bare "Remote" or an office nickname is never silently deleted
        # (Mit's ruling). `location_fit` above stays the SOFT scorer; this is the hard veto.
        location = classify_location(posting_locations)
        if location == "non_us":
            return HardFilterVeto("non_us_location", "; ".join(posting_locations))
        # Second axis: a place catalog can only drop a city it has already heard of, and three
        # postings name no place at all (`locations_json == ["Remote"]`). A German or French
        # job ad is not a US role whatever city it names. Gated on `!= "us"` so a CONFIRMED US
        # location always wins — the fail-safe direction, even though 0 such postings exist.
        if location != "us" and has_non_us_ad_marker(posting_title):
            # `has_non_us_ad_marker` answers yes/no, not which convention, so the title IS
            # the evidence here. Enough for the drain: the operator reads the title and sees it.
            return HardFilterVeto("foreign_ad_marker", posting_title)
    return None


def passes_hard_filters(
    posting_title: str,
    posting_locations: Sequence[str],
    remote_policy: str,
    profile: ProfileView,
    location_filter_mode: str,
) -> bool:
    return (
        hard_filter_verdict(
            posting_title, posting_locations, remote_policy, profile, location_filter_mode
        )
        is None
    )


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
    coverage_pseudo_count: float = 1.0,
) -> Score:
    coverage_value, covered, skill_count = skill_coverage(profile.skills, posting_skills)
    if coverage_value is not None:
        # Shrink the ratio toward the neutral prior by how much evidence it rests on. The raw
        # ratio treats "1 of 1 recognised term matched" and "14 of 27 matched" as comparable
        # estimates of fit, and the first one wins: it reads 1.00 on the component carrying
        # HALF the weight, from a sample of size one. Measured over the 5,029-posting
        # deliverable pool of run 137, that put 16 postings with <=2 recognised terms into the
        # top 100 — "Technical Product Owner (F/H)", "Global Financial Crimes — Compliance
        # Testing, AVP", "Enterprise Mobility Engineer" — and it is the same failure
        # taxonomy.yaml already tried to fix from the data side by deleting four generic
        # terms, which only moves the problem to whichever term is next.
        #
        # A pseudo-count is the smallest expression of that: at skill_count=0 it reduces
        # exactly to zero_skill_prior (the imputation below), and by skill_count=27 it moves
        # the value by <0.001, so it changes the thin end and leaves the rich end alone.
        # It is NOT a filter — every posting keeps a defined coverage and its own evidence
        # chain; only the ORDER changes.
        coverage_value = (covered + coverage_pseudo_count * zero_skill_prior) / (
            skill_count + coverage_pseudo_count
        )
        coverage_detail = (
            f"covers {covered}/{skill_count} skills"
            if coverage_pseudo_count <= 0.0
            else f"covers {covered}/{skill_count} skills, shrunk toward "
            f"{zero_skill_prior:.2f} on {skill_count} term(s) of evidence"
        )
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
