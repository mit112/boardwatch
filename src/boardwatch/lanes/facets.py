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
Measured on the live store 2026-08-31 by running THIS module over it, of 957 postings the program
had built a lead for, 26 distinct title spellings recurred at two or more employers, and the eight
best-evidenced (16 delivered postings at 13 employers, down to 3 at 3) were absent from the
profile entirely. Every one of those was a search the lane never made.

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
# target titles. It bounds SEARCH requests only, and body GETs stay bounded by the lane's own
# `lane_posting_budget`.
#
# THAT IS A CEILING, NOT A CONSERVED TOTAL, and this comment used to read as though it were —
# "a wider facet set buys a better candidate pool at the same body cost". Measured on runs
# 134-137, the lane attempted 111-128 bodies against a budget of 300, so it was 172-189 under
# the ceiling every time and a wider facet set buys MORE bodies, not the same ones re-sorted.
# The body half is still bounded by a number the operator set; it is simply not free.
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

# How deep the ranked candidate list is carried past the run's cap. Every candidate costs one
# `LIKE` term in the trial lookup's `WHERE`, so an unbounded list makes that query grow with the
# user's delivered history — the same bound `store.queries.load_dispositions` chunks its `IN`
# list for. Four times the run cap, so pruning has depth to work with: reaching the end of it
# would mean 32 better-evidenced terms were all barren, and the run then buys FEWER facets,
# which is the safe direction and is visible in the funnel's own list of searches.
MAX_MINED_CANDIDATES = 32

# How many postings a mined facet must have been credited with, INSIDE THE WINDOW, before zero
# deliveries from it is evidence rather than small-sample noise. Below it a facet is never pruned
# — no evidence yields no verdict, the same direction the eligibility rules take.
#
# Derived, not chosen. The floor conversion rate is the WEAKEST of the 14 live profile facets:
# 2 leads delivered from 52 credited postings, 3.8%. A facet converting at that floor shows zero
# deliveries across n credited postings with probability 0.962^n — 21% at n=40, 2.1% at n=100,
# 0.3% here. A false prune costs a working search for a whole window, on the exact axis mining
# exists to widen, so this is sized against that and not against reaction speed.
#
# THE COUNT HAS TO BE READ AGAINST THE WINDOW, and a count sized on a shorter one is the trap
# here: the store's 807 facet-credited postings span 5 days and 21 runs, ~2.7 per facet per run,
# so a searched facet accrues ~340 over a 30-day window at that cadence and crosses this in ~55
# runs. Run cadence is the user's, not this module's — at one run a day the same facet may never
# reach it inside the window and is simply never pruned. That direction is deliberate: not
# pruning costs at most `lane_search_pages` requests a run against a hard cap of eight facets,
# while pruning a working term costs leads.
MIN_TRIAL_POSTINGS = 150

# How many of the profile's target titles each company cell is crossed with, and it is ONE. The
# reason is arithmetic, not taste, and it was measured before it was chosen (D-433).
#
# A company cell is a rotating slice of a term-by-company matrix, exactly as a hub net is a slice
# of a term-by-hub one. But where the hub side is seven fixed metros, the company side is the
# store: 1,812 distinct names live, 443 of them watched. Crossing the live profile's 14 target
# titles with all of them is 25,368 cells, and at the measured cadence of 83 runs in 14 days a
# full rotation at 12 cells a run takes **358 days** -- no cell is ever revisited and nothing the
# rotation buys can be read. One term against the watched companies alone is 443 cells, a full
# pass every ~37 runs (~6 days), which is the only shape whose result is readable inside the
# window the measurement was commissioned for.
#
# It is a CEILING on the term axis, not a claim that one title is enough. The other 13 are already
# searched USA-wide by the profile facet path and crossed with the hubs by `hub_nets`; what a
# company cell adds is the EMPLOYER axis, and buying it 14 times over costs 14x for breadth two
# other paths already have.
MAX_COMPANY_FACET_TERMS = 1

# Runs of anything that is not a letter or digit collapse to one separator. A slash surviving
# into a slug would change which URL is requested -- `/jobs/a/b` is not the role route -- so
# this is a routing invariant, not tidiness.
_SEPARATORS = re.compile(r"[^a-z0-9]+")

# Whitespace runs inside a company name, collapsed so two spellings of one employer produce one
# cell. Company names are NOT put through `search_term`: that folds every non-alphanumeric run to
# a space, which turns `AT&T` into `at t` and asks for a company that does not exist. A name is
# the employer's own string and is searched as written.
_WHITESPACE = re.compile(r"\s+")


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


def hub_nets(
    terms: Sequence[str], hubs: Sequence[str], *, rotation_index: int, combos_per_run: int
) -> tuple[tuple[str, str], ...]:
    """The deterministic rotating slice of the term-by-hub matrix for one run.

    A geo net is a term searched AT a hub. The full matrix is every term crossed with every hub,
    which is more searches than one run should buy, so a run takes `combos_per_run` of them and
    the window advances by that many per RUN: `rotation_index * combos_per_run` modulo the matrix
    size. `rotation_index` is the run's own id (see `pipeline/runner.py::_rotation_index`), so the
    stride is one run, never one calendar day.

    **THE CONTRACT, WITH ITS CONDITIONS, because the unconditional version of it was false.**
    Write `m = len(matrix)` and `c = combos_per_run`:

    - `c >= m`: the whole matrix is returned EVERY run. There is no rotation and none is needed.
    - `2c <= m`: consecutive runs are DISJOINT, and the whole matrix is covered in `ceil(m / c)`
      runs with no cell favoured and none starved.
    - `m < 2c`: consecutive runs necessarily OVERLAP in `2c - m` cells -- a window of `c` cells on
      a ring of `m` cannot avoid its own successor once it covers more than half the ring. Cover
      is still complete in `ceil(m / c)` runs; the cost is that some cells are re-bought sooner.

    An earlier version of this docstring asserted disjointness unconditionally. That is true for
    the reference configuration (5 terms x 7 hubs, 12 per run) and false for every matrix under
    `2c` -- at the default `c = 12`, any matrix below 24 cells, which is what a first-time
    operator with four target titles and two hubs actually has. **Size `c` against `m`, or state
    the overlap.**

    **TERMS AND HUBS ARE DEDUPLICATED FIRST, ORDER-PRESERVING, AND THAT IS NOT COSMETIC.**
    `Settings` enforces uniqueness on neither, so a config naming one hub twice put the identical
    `(term, hub)` cell in the matrix twice: the run bought the same search twice, and the slice
    returned fewer DISTINCT cells than `combos_per_run` promises, silently shrinking a run's
    reach in proportion to how often the user repeated themselves. Deduplicating the two INPUTS
    rather than the product is what keeps the matrix rectangular, so the arithmetic above still
    describes it.

    First-seen order is preserved, so the matrix -- and therefore which cells a given run draws --
    is a function of the config as written, not of a set's iteration order.

    `terms` is the profile's DECLARED facets only; mined facets are deliberately not crossed with
    hubs. See `_linkedin_lane` in `pipeline/runner.py`, which owns that boundary and states why.
    """
    if combos_per_run <= 0 or not terms or not hubs:
        return ()
    unique_terms = list(dict.fromkeys(terms))
    unique_hubs = list(dict.fromkeys(hubs))
    matrix = [(term, hub) for term in unique_terms for hub in unique_hubs]
    if combos_per_run >= len(matrix):
        return tuple(matrix)
    start = (rotation_index * combos_per_run) % len(matrix)
    return tuple(matrix[(start + index) % len(matrix)] for index in range(combos_per_run))


def company_term(name: str) -> str:
    """One company name as a phrase safe to quote inside a keyword query, or "" if it holds none.

    An embedded double quote is replaced rather than escaped: the cell wraps the name in quotes to
    make it a phrase, and a name carrying its own quote would terminate that phrase early and turn
    the tail into loose keywords -- a query for a DIFFERENT thing that would still return results,
    which is the failure mode worth spending a line on.

    **A name carrying a PATH is refused outright**, because `companies add` writes
    `name = entry.name if entry else slug` and the shipped registry has 37 entries, so a board
    added by hand is named by its slug -- and a Workday slug is a full composite. The live store
    holds `walmart.wd504.myworkdayjobs.com/walmart/WalmartExternal` as a company NAME, which
    composes a cell no requisition can contain, costs a slot in the rotation, and reports nothing
    about why it found nothing.

    **Only a path, deliberately not `name == slug`.** A review proposed the wider rule; measured
    against the live store it would delete 145 of 453 watched companies, including `Anthropic`,
    `OpenAI`, `Notion`, `Airbnb` and `1Password` -- names that equal their slug because the slug is
    the name. The measured harm is 1 row, and `.` alone cannot be the signal either: `Alarm.com` is
    a real employer. A separator is not evidence; a PATH is.
    """
    cleaned = _WHITESPACE.sub(" ", name.replace('"', " ")).strip()
    return "" if "/" in cleaned else cleaned


def company_nets(
    terms: Sequence[str], companies: Sequence[str], *, rotation_index: int, combos_per_run: int
) -> tuple[str, ...]:
    """The deterministic rotating slice of the term-by-company matrix, as composed keyword strings.

    A company cell is one target title asked AT one named employer -- `"Acme Corp" software
    engineer`. It needs no new URL shape: the guest endpoint already takes `keywords=` and
    `linkedin.search_url` already quotes the term, so a cell is an ordinary facet string and the
    lane does not change. This is the one thing job-apps does that boardwatch did not
    (`job_discovery.py:2438`).

    **The rotation arithmetic is `hub_nets`', deliberately verbatim, and so are its conditions.**
    Write `m = len(matrix)` and `c = combos_per_run`:

    - `c >= m`: the whole matrix every run; no rotation, and none needed.
    - `2c <= m`: consecutive runs are DISJOINT and the matrix is covered in `ceil(m / c)` runs.
    - `m < 2c`: consecutive runs necessarily OVERLAP in `2c - m` cells.

    **Written down rather than inherited, because the RATIO differs by an order of magnitude even
    though the regime does not.** Measured against the live config: hub nets are 14 profile facets
    x 7 hubs = `m = 98` with `c = 33`, and company cells are `m = 443` with `c = 12`. Both satisfy
    `2c <= m`, so both are disjoint -- an earlier draft of this paragraph said hub nets ran
    `c = 33` against `m = 35` and were effectively unrotated, which is `hub_nets`' old FIVE-term
    reference configuration and not what the live profile produces. What actually differs is the
    pass length: 3 runs against 37. The condition here fails only for an operator watching fewer
    than `2c` companies, who is buying the whole set every run anyway.

    **Both inputs are deduplicated, order-preserving, and the product is not** -- the same rule
    `hub_nets` states, so the matrix stays rectangular and the arithmetic above still describes it.
    Companies are deduplicated WITHOUT REGARD TO CASE, which `hub_nets` does not do for hubs: the
    store really holds one employer under two spellings (`stored_slug` exists because of it), and
    two cells differing only in case are one search bought twice.

    `terms` is capped at `MAX_COMPANY_FACET_TERMS`. The cap is applied AFTER deduplication, so a
    profile that repeats its first title does not spend the whole term budget on one spelling.

    The company list comes from the STORE and is passed in, never read here and never written
    down: a module naming employers would fit exactly one user, which is the failure the
    multi-tenancy requirement names first.
    """
    if combos_per_run <= 0 or not terms or not companies:
        return ()
    unique_terms = list(dict.fromkeys(term for term in terms if term))[:MAX_COMPANY_FACET_TERMS]
    unique_companies: dict[str, str] = {}
    for name in companies:
        phrase = company_term(name)
        if phrase:
            unique_companies.setdefault(phrase.casefold(), phrase)
    if not unique_terms or not unique_companies:
        return ()
    matrix = [
        f'"{company}" {term}' for term in unique_terms for company in unique_companies.values()
    ]
    if combos_per_run >= len(matrix):
        return tuple(matrix)
    start = (rotation_index * combos_per_run) % len(matrix)
    return tuple(matrix[(start + index) % len(matrix)] for index in range(combos_per_run))


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
    """Search terms the user's own delivered leads support, best-evidenced first.

    Un-PRUNED on purpose: this is the generation half, and it answers only "what does the user's
    delivered history say the market calls these jobs". Whether a candidate has already been
    tried and found barren is a different question with different evidence, and
    `surviving_mined_facets` asks it. Folding them would make one function that could not report
    which rule dropped a term.

    Cut at `MAX_MINED_CANDIDATES` rather than at the run cap, because the caller has to price
    every candidate it returns and pruning has to have somewhere to go.

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
    return tuple(term for _, _, term in ranked[:MAX_MINED_CANDIDATES])


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
