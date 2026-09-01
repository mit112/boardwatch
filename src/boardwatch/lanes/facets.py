"""The user's target job titles as lane search facets, and the ones mined from her own outcomes.

WHY A LANE NEEDS A FACET AT ALL. An aggregator search with no role filter returns the general
labour market, not the user's market. Measured on the live store on 2026-08-26, of the 282 open
postings the two armed lanes had acquired, 3 were software roles and 197 were explicitly not
(nurse, barista, crew member, dishwasher, delivery driver). The downstream role gate was working
exactly as designed and was not the problem: the lanes were not rejecting software postings, they
were barely surfacing any. A probe of the same aggregator's role route returned 20 of 20 software
roles. The fix belongs upstream, in what is asked for, and this module is that ask.

WHY IT IS DERIVED AND NEVER WRITTEN DOWN. Baking `software engineer` into a lane would make both
lanes fit exactly one user and silently mislead every other one — the failure the multi-tenancy
requirement names first, and the reason both lane contracts deferred the facet rather than
guessing at it. So the facet is read from `profile.target_titles_json`: a field onboarding already
gathers, that `rank.heuristic.title_match` already scores against, and that carries no code
change for a user whose targets are nursing roles. This module holds normalization rules and
budgets, and no titles.

WHY A PROFILE'S TITLES ARE NOT THE WHOLE ASK. A stated target title set is what the user could
write down before running anything; it is not what the market calls the jobs she actually wants.
Measured on the live store 2026-08-31, of 957 postings the program had built a lead for, only 26
distinct title spellings recurred at two or more employers, and the largest — `software
development engineer` (10 postings, 4 employers) and `junior software engineer` (13 postings, 5
employers) — were absent from the profile entirely. Every one of those searches was a query the
lane never made.

So the second source of facets is the user's OWN DELIVERED OUTCOMES: the titles of postings this
program built a lead for. That is still not a title written into code — it is the same
`title` column any employer wrote, selected by the user's own pipeline, and a nurse running
boardwatch mines nursing titles from it by exactly this path. The generation rule is stricter
than the prior art's ("keep a term that correlates with >=1 built posting"): a term must have
been delivered at `MIN_DELIVERED_COMPANIES` distinct employers, which is what separates a
market-wide title from one employer's house style.

MINING IS EVIDENCE-GATED, SO A NEW STORE MINES NOTHING. With no built leads there are no
candidates and the lane asks exactly what it asked before. That is the honest failure direction:
a miner with no evidence abstains rather than inventing a role query.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

# One facet is one search request, so an uncapped profile is an uncapped request count. Sized to
# clear a realistic profile with headroom rather than to bind one: the live profile lists 14
# target titles. It bounds SEARCH requests only — body GETs stay bounded by the lane's own
# posting budget, so a wider facet set buys a better candidate pool at the same body cost.
#
# This caps the PROFILE's facets alone. Mined facets carry their own, separate budget below, so
# that a mined term can never displace a title the user actually asked for.
MAX_FACETS_PER_RUN = 16

# The mined facets' own ceiling, and the whole added request cost of mining. One mined facet
# costs up to `lane_search_pages` search GETs, so at the live setting of 5 pages this is <=40
# extra search requests per run — ~40 s against a lane measured at ~198 requests / ~4.1 min on
# runs 134-137. Body GETs are NOT additional budget: they come out of `lane_posting_budget`,
# which those same four runs left 172-189 unspent every time.
MAX_MINED_FACETS_PER_RUN = 8

# How far back a delivered lead still counts as evidence, and how far back a facet's trial
# record counts against it. A window rather than an all-time count is the drain both halves owe:
# a term the user has moved on from ages out of the candidate pool on its own, and a facet
# pruned for converting nothing becomes eligible again once the trials that condemned it age
# out. Neither state is permanent, and neither needs a second mechanism to release it.
MINED_FACET_WINDOW_DAYS = 30

# A candidate must be a title the MARKET repeats, not one employer's house style. Measured on
# the live store, requiring two employers is what excludes `servicenow developer` (10 delivered
# postings, all at 1 employer) and `jr python developer` (4 postings, 1 employer) while keeping
# `full stack software engineer` (9 postings, 9 employers).
#
# ONE threshold, on employers, and deliberately not a second one on postings. Every posting has
# exactly one company, so distinct employers can never exceed distinct postings: a posting floor
# at or below this number could refuse nothing this one admits. A second constant that cannot
# change an outcome is a knob a reader would reasonably believe in.
MIN_DELIVERED_COMPANIES = 2

# A ceiling on how long a mined term may be. The profile's titles are the user's own words and
# are trusted at any length; a mined term is an EMPLOYER's words, arbitrary in length and free to
# carry requisition junk, so the two are not held to the same standard. An over-long term is not
# dangerous, only useless — it matches nothing — but a facet that matches nothing still costs a
# request.
MAX_MINED_FACET_WORDS = 5

# How many postings a mined facet must have been credited with, inside the window, before zero
# deliveries from it is evidence rather than small-sample noise. Measured on the live store's own
# 807 facet-credited postings: the WEAKEST of the 14 profile facets still delivered 2 leads from
# 52 credited postings, so at that floor rate a facet with 40 credited postings and none
# delivered is a genuinely different animal, not an unlucky one. Below this threshold a facet is
# never pruned — no evidence yields no verdict, the same direction the eligibility rules take.
MIN_TRIAL_POSTINGS = 40

# Runs of anything that is not a letter or digit collapse to one separator. A slash surviving
# into a slug would change which URL is requested -- `/jobs/a/b` is not the role route -- so
# this is a routing invariant, not tidiness.
_SEPARATORS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class DeliveredPosting:
    """One posting the program built a lead for: its RAW title, and what it is one of.

    The raw title, never `postings.normalized_title`. That column is an IDENTITY normalizer and
    folds `+` to ` plus ` and `#` to ` sharp ` on purpose (`core.normalize`, D-p6.2), so mining
    it would turn a `Software Engineer - C++` lead into the search term `software engineer c plus
    plus` — a query no employer's posting contains. Six of the live store's 957 built postings
    carry one of those two characters, and 590 open postings do.

    `posting_id` and `company_id` are counted DISTINCTLY rather than summed, because one
    requisition listed in five cities is one piece of evidence about a title, not five.
    """

    title: str
    posting_id: int
    company_id: int


@dataclass(frozen=True)
class FacetTrial:
    """What one term has actually bought as a search facet, inside the window.

    `credited` is the postings whose acquisition was attributed to this facet's search page;
    `delivered` is how many of those the program went on to build a lead for. Both are counted
    from the store's own `posting_version_sources` provenance, never from a lane's self-report:
    a component's own tally cannot verify itself.
    """

    credited: int
    delivered: int


def search_term(title: str) -> str:
    """One job title as a canonical search TERM, or "" if it holds nothing searchable.

    The single normalization rule both facet sources share. A profile title and a delivered
    posting's title have to fold identically or the exclusion in `mined_facet_candidates` would
    let a facet the profile already asks for through under a different spelling, and the run
    would pay twice for one search.
    """
    return _SEPARATORS.sub(" ", title.lower()).strip()


def role_facets(target_titles: Sequence[str] | None) -> tuple[str, ...]:
    """`profile.target_titles_json` as at most `MAX_FACETS_PER_RUN` canonical search terms.

    First-seen order is preserved, and the cap TRUNCATES in that order rather than sampling: a
    run whose facet set varied between invocations could not be reproduced from the profile that
    produced it.

    A title that normalizes to nothing yields no facet rather than an empty one. An empty term
    would build the aggregator's UNFACETED listing, which is a different page, so a blank target
    title would silently restore the noise the facet exists to remove while the run reported that
    a facet had been applied.
    """
    facets: list[str] = []
    for title in target_titles or ():
        term = search_term(title)
        if term and term not in facets:
            facets.append(term)
        if len(facets) == MAX_FACETS_PER_RUN:
            break
    return tuple(facets)


def _word_key(term: str) -> tuple[str, ...]:
    """A term's words, sorted — the identity two spellings of one query share.

    `full stack software engineer` and `software engineer full stack` are one ask of a keyword
    search, and the live store delivered leads under both. Grouping them costs one facet instead
    of two. It also closes an exclusion hole that matters more: without it, a delivered
    `Software Engineer, Associate` would be mined as a brand-new facet even though the profile
    already lists `Associate Software Engineer`, and the run would buy the same search twice.
    """
    return tuple(sorted(term.split()))


def mined_facet_candidates(
    delivered: Iterable[DeliveredPosting], role_facet_terms: Sequence[str]
) -> tuple[str, ...]:
    """Search terms the user's own delivered leads support, best-evidenced first, UNCAPPED.

    Uncapped and un-pruned on purpose: this is the generation half, and it answers only "what
    does the user's delivered history say the market calls these jobs". Whether a candidate has
    already been tried and found barren is a different question with different evidence, and
    `surviving_mined_facets` asks it. Folding them would make one function that could not report
    which rule dropped a term.

    A term the profile already asks for is excluded on the WORD KEY, not the spelling, so a
    permuted duplicate cannot slip past. Ordering is (postings, employers, term) descending,
    descending, ascending — fully determined by the data, so two runs over one store produce one
    facet list and the run is reproducible from the store that produced it.
    """
    excluded = {_word_key(term) for term in role_facet_terms}
    postings: dict[tuple[str, ...], set[int]] = {}
    companies: dict[tuple[str, ...], set[int]] = {}
    # Spelling -> distinct postings, per group, so the surviving term is the one the market
    # writes most often rather than whichever row the store happened to return first. A sorted
    # word key is not a query: `associate engineer software` is not what anyone searches for.
    spellings: dict[tuple[str, ...], dict[str, set[int]]] = {}
    for posting in delivered:
        term = search_term(posting.title)
        if not term or len(term.split()) > MAX_MINED_FACET_WORDS:
            continue
        key = _word_key(term)
        if key in excluded:
            continue
        postings.setdefault(key, set()).add(posting.posting_id)
        companies.setdefault(key, set()).add(posting.company_id)
        spellings.setdefault(key, {}).setdefault(term, set()).add(posting.posting_id)

    ranked: list[tuple[int, int, str]] = []
    for key, posting_ids in postings.items():
        if len(companies[key]) < MIN_DELIVERED_COMPANIES:
            continue
        best = min(spellings[key].items(), key=lambda item: (-len(item[1]), item[0]))[0]
        ranked.append((len(posting_ids), len(companies[key]), best))
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return tuple(term for _, _, term in ranked)


def surviving_mined_facets(
    candidates: Sequence[str], trials: Mapping[str, FacetTrial]
) -> tuple[str, ...]:
    """The candidates worth a request this run: barren ones dropped, then capped.

    This is the prospective half of the loop, and the reason mining cannot run away with the
    request budget. A candidate's rank comes from leads delivered across EVERY source, so a term
    that this lane's search never converts keeps its rank forever on other sources' evidence —
    ranking alone is not pruning, and without this a barren facet would be bought every run for
    as long as the title kept being delivered elsewhere.

    A candidate with no trial record, or with too few credited postings to judge, is KEPT. That
    is the same direction the eligibility rules take with a missing fact: absence of evidence is
    not evidence, and a facet dropped on its first quiet run could never earn its way back.
    """
    kept: list[str] = []
    for term in candidates:
        trial = trials.get(term)
        if trial is not None and trial.credited >= MIN_TRIAL_POSTINGS and trial.delivered == 0:
            continue
        kept.append(term)
        if len(kept) == MAX_MINED_FACETS_PER_RUN:
            break
    return tuple(kept)


@dataclass(frozen=True)
class LaneFacets:
    """The two facet sources a run resolved, kept apart all the way to the registration site.

    Apart rather than concatenated because they are not interchangeable: the profile's titles are
    what the user asked for and every faceted lane gets them, while mined terms are this repo's
    inference and are handed only to the lane whose conversion record justified them. A single
    merged tuple would silently spend another lane's request budget on the inference.
    """

    profile: tuple[str, ...] = ()
    mined: tuple[str, ...] = ()
