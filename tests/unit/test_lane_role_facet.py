"""lanes.facets: the user's target titles as lane search facets.

The facet exists because a facet-less aggregator search returns the general labour market.
Measured on the live store, 2026-08-26: of 282 open postings the two armed lanes had
acquired, 3 were software roles (1.1%) and 197 were explicitly not (nurse, barista, crew
member, dishwasher). A live probe of the SAME aggregator's role route returned 20 of 20
software roles. The lanes were never rejecting software postings — they were barely
surfacing any.

WHY THE FACET IS DERIVED AND NEVER WRITTEN DOWN. A hardcoded `software engineer` query
would make both lanes fit exactly one user and silently mislead every other. The repo's
multi-tenancy requirement is that what makes it work for a specific person is that person's
own profile data, never new code, so the facet is read from `profile.target_titles_json` —
a field that already exists, that onboarding already gathers, and that the ranker already
scores against. A user targeting nursing roles gets nursing facets from the same code.
"""

from __future__ import annotations

import pytest

from boardwatch.lanes.facets import (
    MAX_COMPANY_FACET_TERMS,
    MAX_FACETS_PER_RUN,
    company_nets,
    hub_nets,
    role_facets,
)


def test_a_target_title_becomes_a_normalized_search_TERM_not_a_url_slug():
    """The facet is a search TERM, and each lane encodes it for its own route.

    Returning a hyphenated slug here would be right for hiring.cafe's path route and WRONG for
    LinkedIn's `keywords=` query: the probe that legitimises that lane made
    `keywords=software%20engineer`, so `keywords=software-engineer` is a request shape this repo
    has never made. Keeping the term canonical and letting each lane encode is what stops one
    lane's URL convention leaking into another's contract.
    """
    assert role_facets(["Software Engineer"]) == ("software engineer",)


def test_punctuation_and_runs_of_separators_collapse_to_single_hyphens():
    """`Full-Stack Engineer / Developer` is one facet, not a path with extra segments.

    A slash surviving into the slug would change which URL is requested — `/jobs/a/b` is
    not the role route — so this is a routing invariant, not cosmetics.
    """
    assert role_facets(["Full-Stack  Engineer / Developer"]) == ("full stack engineer developer",)
    assert role_facets(["C++ Engineer (Backend)"]) == ("c engineer backend",)


def test_titles_differing_only_in_case_or_spacing_cost_one_request_not_two():
    assert role_facets(["Software Engineer", "software  engineer", "SOFTWARE ENGINEER"]) == (
        "software engineer",
    )


def test_first_seen_order_is_preserved_so_the_request_order_is_deterministic():
    """An unordered facet set makes a run's request sequence — and its budget spend —
    depend on set iteration order, which no test could then pin."""
    assert role_facets(["iOS Engineer", "Backend Engineer", "Web Developer"]) == (
        "ios engineer",
        "backend engineer",
        "web developer",
    )


@pytest.mark.parametrize("title", ["", "   ", "!!!", "---", "/"])
def test_a_title_that_normalizes_to_nothing_yields_no_facet(title):
    """An empty slug would build `/jobs/`, which is a DIFFERENT page — the unfaceted
    listing — so a blank target title would silently re-introduce the noise the facet
    exists to remove, while the run reported a facet had been applied."""
    assert role_facets([title]) == ()


def test_no_target_titles_yields_no_facets():
    assert role_facets([]) == ()
    assert role_facets(None) == ()


def test_the_facet_count_is_capped_so_one_profile_cannot_size_a_run():
    """Each facet is one search request. The cap is a ceiling on requests per lane per
    run, in the same spirit as the posting budget, so a profile listing fifty target
    titles cannot turn one lane into a fifty-request crawl."""
    many = [f"Role Number {index}" for index in range(MAX_FACETS_PER_RUN + 7)]
    facets = role_facets(many)
    assert len(facets) == MAX_FACETS_PER_RUN
    # The cap TRUNCATES in profile order rather than sampling: a run whose facet set
    # varied between invocations could not be reproduced from the profile alone.
    assert facets == role_facets(many[:MAX_FACETS_PER_RUN])


def test_hub_nets_rotate_the_full_matrix_in_order_and_wrap():
    """Each run gets a deterministic contiguous slice, including the wrap at the matrix tail."""
    terms = ("alpha", "beta")
    hubs = ("Austin", "Boston", "Chicago")
    matrix = {
        (term, hub) for term in terms for hub in hubs
    }

    day_zero = hub_nets(terms, hubs, rotation_index=0, combos_per_run=4)
    day_one = hub_nets(terms, hubs, rotation_index=1, combos_per_run=4)

    assert day_zero == (
        ("alpha", "Austin"),
        ("alpha", "Boston"),
        ("alpha", "Chicago"),
        ("beta", "Austin"),
    )
    assert day_one == (
        ("beta", "Boston"),
        ("beta", "Chicago"),
        ("alpha", "Austin"),
        ("alpha", "Boston"),
    )
    assert len(set(day_zero)) == len(day_zero)
    assert len(set(day_one)) == len(day_one)
    assert set(day_zero + day_one) == matrix

    # The next rotation is independently reproducible and advances by the same stride.
    assert hub_nets(terms, hubs, rotation_index=2, combos_per_run=4) == (
        ("alpha", "Chicago"),
        ("beta", "Austin"),
        ("beta", "Boston"),
        ("beta", "Chicago"),
    )


def test_hub_nets_return_each_matrix_pair_once_when_the_budget_covers_it():
    terms = ("alpha", "beta")
    hubs = ("Austin", "Boston")

    assert hub_nets(terms, hubs, rotation_index=9, combos_per_run=99) == (
        ("alpha", "Austin"),
        ("alpha", "Boston"),
        ("beta", "Austin"),
        ("beta", "Boston"),
    )


@pytest.mark.parametrize(
    ("terms", "hubs", "combos_per_run"),
    [
        (("alpha",), ("Austin",), 0),
        ((), ("Austin",), 1),
        (("alpha",), (), 1),
    ],
)
def test_hub_nets_are_empty_when_any_required_input_is_empty(terms, hubs, combos_per_run):
    assert hub_nets(terms, hubs, rotation_index=0, combos_per_run=combos_per_run) == ()


def test_hub_nets_are_a_function_of_the_config_AS_WRITTEN_not_of_iteration_order():
    """Replaces a test that called `hub_nets` twice with identical arguments and asserted the
    results matched. **No implementation fails that** -- not the pre-dedup one, not a fixed
    `start=0`, not `return ()` -- and it could not even catch the set-iteration-order bug it
    looked aimed at, because a `set` of strings iterates identically twice in one process.

    The property actually wanted is that the matrix follows the ORDER the config was written in,
    so two orderings of the same hubs must produce DIFFERENT slices. That fails against any
    implementation that canonicalises the inputs through a set.
    """
    forward = hub_nets(("alpha",), ("Austin, TX", "Boston, MA"), rotation_index=0, combos_per_run=1)
    reversed_ = hub_nets(("alpha",), ("Boston, MA", "Austin, TX"), rotation_index=0, combos_per_run=1)

    assert forward == (("alpha", "Austin, TX"),)
    assert reversed_ == (("alpha", "Boston, MA"),)


def test_a_hub_named_twice_does_not_buy_the_same_search_twice():
    """The regression guard for a config that repeats itself.

    `Settings` enforces uniqueness on neither terms nor hubs, so before the inputs were
    deduplicated the identical `(term, hub)` cell sat in the matrix twice: the run paid for the
    same request twice, and the slice returned FEWER DISTINCT cells than `combos_per_run`
    promises -- a run's reach shrank in proportion to how often the user repeated a hub, silently
    and with nothing in the report to show it.
    """
    duplicated = hub_nets(
        ("alpha", "alpha"),
        ("Austin, TX", "Boston, MA", "Austin, TX"),
        rotation_index=0,
        combos_per_run=99,
    )

    assert duplicated == (("alpha", "Austin, TX"), ("alpha", "Boston, MA"))
    assert len(set(duplicated)) == len(duplicated)


def test_deduplication_preserves_first_seen_order_so_the_matrix_is_the_config_as_written():
    """Order matters because it decides which cells a given day draws. A set would make the
    slice depend on hash iteration order rather than on what the user wrote."""
    assert hub_nets(
        ("beta", "alpha", "beta"),
        ("Boston, MA", "Austin, TX", "Boston, MA"),
        rotation_index=0,
        combos_per_run=99,
    ) == (
        ("beta", "Boston, MA"),
        ("beta", "Austin, TX"),
        ("alpha", "Boston, MA"),
        ("alpha", "Austin, TX"),
    )


def test_a_run_never_spends_two_of_its_combos_on_one_search():
    """The consequence the dedup exists to prevent, stated as the property that costs money.

    A run buys `combos_per_run` REQUESTS. Every cell the slice repeats is a request spent
    fetching a page this run has already fetched, so the returned slice must never contain the
    same `(term, hub)` twice no matter how the config repeats itself. Asserted as
    `len(set(...)) == len(...)` rather than against an expected tuple, because that is the
    invariant itself and it holds for every input rather than for the one that was written down.
    """
    for terms, hubs, combos in (
        (("alpha",), ("Austin, TX", "Austin, TX"), 2),
        (("alpha", "alpha"), ("Austin, TX",), 2),
        (("alpha", "beta", "alpha"), ("Austin, TX", "Boston, MA", "Austin, TX"), 5),
    ):
        for rotation_index in range(8):
            slice_ = hub_nets(
                terms, hubs, rotation_index=rotation_index, combos_per_run=combos
            )
            assert len(set(slice_)) == len(slice_), (terms, hubs, combos, rotation_index)


def test_consecutive_runs_are_disjoint_ONLY_when_the_matrix_is_at_least_twice_the_slice():
    """The condition the contract used to omit, asserted from both sides.

    A window of `c` cells on a ring of `m` cannot avoid its own successor once `2c > m` --
    pigeonhole. The old docstring, the CHANGELOG and D-411 all claimed disjointness
    unconditionally; it holds for the reference config (5 terms x 7 hubs, 12 per run) and fails
    for every matrix under `2c`, which at the default `c = 12` is any matrix below 24 cells --
    what an operator with four target titles and two hubs actually has.
    """
    # 2c <= m: disjoint, and two runs cover the matrix exactly.
    terms, hubs = ("a", "b", "c", "d"), ("H1", "H2")          # m = 8
    first = hub_nets(terms, hubs, rotation_index=0, combos_per_run=4)
    second = hub_nets(terms, hubs, rotation_index=1, combos_per_run=4)
    assert set(first) & set(second) == set()
    assert set(first) | set(second) == {(t, h) for t in terms for h in hubs}

    # m < 2c: overlap is FORCED, and is exactly 2c - m cells.
    over_first = hub_nets(terms, hubs, rotation_index=0, combos_per_run=6)
    over_second = hub_nets(terms, hubs, rotation_index=1, combos_per_run=6)
    assert len(set(over_first) & set(over_second)) == 2 * 6 - 8

    # c >= m: the whole matrix every run, and the rotation index cannot change it.
    whole = {hub_nets(terms, hubs, rotation_index=r, combos_per_run=8) for r in range(5)}
    assert len(whole) == 1


def test_a_run_counter_advances_the_window_even_when_two_runs_share_a_day():
    """Why the index is the run id and not the calendar date. Two runs on one day used to draw
    the IDENTICAL slice and the second paid full price for cells the first had just fetched --
    and runs here are on demand, so several a day is the normal case during a session."""
    terms, hubs = ("a", "b", "c"), ("H1", "H2")               # m = 6
    consecutive = [hub_nets(terms, hubs, rotation_index=r, combos_per_run=2) for r in (7, 8, 9)]

    assert len({c for c in consecutive}) == 3
    assert set().union(*(set(c) for c in consecutive)) == {(t, h) for t in terms for h in hubs}


# ------------------------------------------------------- per-company cells (Track 2, D-433)


def test_a_company_cell_is_the_employers_name_QUOTED_beside_exactly_one_term():
    """The cell shape, and the term cap that makes the rotation finite.

    `"Acme Corp" software engineer` is what job-apps issues (`job_discovery.py:2438`) and it is an
    ordinary keyword string: `linkedin.search_urls` quotes it into `keywords=`, so no new URL
    builder exists anywhere for this.

    **The second target title is the control.** Without `MAX_COMPANY_FACET_TERMS` this returns two
    cells for one employer, which is the 25,368-cell matrix whose rotation takes 358 days — the
    shape measurement refuted. The company is asked about once, not once per title.
    """
    cells = company_nets(
        ("software engineer", "data scientist"),
        ("Acme Corp",),
        rotation_index=0,
        combos_per_run=99,
    )
    assert cells == ('"Acme Corp" software engineer',)
    assert MAX_COMPANY_FACET_TERMS == 1
    assert not any("data scientist" in cell for cell in cells)


def test_the_quotes_are_around_the_COMPANY_and_not_the_whole_cell():
    """A phrase quote around the employer keeps `Acme Corp` from matching `Acme` and `Corp`
    separately; a quote around the whole cell would demand the title be part of the company's
    name and match nothing. Asserted on the exact string because the difference is two characters
    and both spellings look right at a glance."""
    (cell,) = company_nets(("software engineer",), ("Acme Corp",), rotation_index=0, combos_per_run=1)
    assert cell.startswith('"Acme Corp"')
    assert cell.endswith(" software engineer")
    assert cell.count('"') == 2


def test_two_spellings_of_ONE_employer_are_one_cell_and_two_employers_stay_two():
    """Companies deduplicate WITHOUT REGARD TO CASE, which the hub axis does not do.

    The store really holds one board under two casings — `stored_slug` exists because
    `ashby:Lightfield` and `ashby:lightfield` were one board with one set of postings — so two
    cells differing only in case are one search bought twice, and the slice would return fewer
    DISTINCT cells than `combos_per_run` promises.

    The third company is the control: an implementation that deduplicated too eagerly, or that
    folded on a prefix, collapses it too and the count still reads 2.
    """
    cells = company_nets(
        ("software engineer",),
        ("Acme Corp", "ACME CORP", "Acme Corporation"),
        rotation_index=0,
        combos_per_run=99,
    )
    assert cells == (
        '"Acme Corp" software engineer',
        '"Acme Corporation" software engineer',
    ), "first-seen spelling must survive, and a different employer must not be folded in"


def test_a_company_name_carrying_a_double_quote_cannot_break_the_phrase():
    """An employer name is arbitrary user/store data, and an embedded quote would terminate the
    phrase early and turn the tail into loose keywords — a query for a DIFFERENT thing that still
    returns results, which is why this is worth a test rather than a comment."""
    (cell,) = company_nets(
        ("software engineer",), ('Acme "The Real" Corp',), rotation_index=0, combos_per_run=1
    )
    assert cell.count('"') == 2
    assert cell == '"Acme The Real Corp" software engineer'


def test_a_company_name_that_is_really_a_PATH_yields_no_cell_but_a_dotted_name_still_does():
    """`companies add` writes `name = entry.name if entry else slug` and the shipped registry has
    37 entries, so a hand-added board is named by its slug — and a Workday slug is a full
    composite. The live store really holds this one.

    **The second and third arms are the control, and they are why the rule is a PATH and not a
    separator.** A review proposed refusing any name equal to its slug; measured, that deletes 145
    of 453 watched companies including `Anthropic` and `OpenAI`, whose slug IS their name. And
    `Alarm.com` is a real employer, so a dot cannot be the signal either.
    """
    cells = company_nets(
        ("software engineer",),
        (
            "walmart.wd504.myworkdayjobs.com/walmart/WalmartExternal",
            "Alarm.com",
            "Anthropic",
        ),
        rotation_index=0,
        combos_per_run=99,
    )
    assert cells == ('"Alarm.com" software engineer', '"Anthropic" software engineer')


@pytest.mark.parametrize(
    ("terms", "companies", "combos_per_run"),
    [
        (("software engineer",), ("Acme",), 0),
        ((), ("Acme",), 12),
        (("software engineer",), (), 12),
        (("",), ("Acme",), 12),
        (("software engineer",), ("   ",), 12),
    ],
    ids=["off-switch", "no-terms", "no-companies", "blank-term", "blank-company"],
)
def test_company_cells_are_empty_when_any_required_input_is_empty(terms, companies, combos_per_run):
    """0 is the OFF switch and is the shipped default, so this is the path every existing run
    takes. A blank term or a blank company name yields no cell rather than an empty one: an empty
    `keywords=` builds LinkedIn's UNFACETED listing, a different page entirely, and the run would
    report a cell it never asked for."""
    assert company_nets(terms, companies, rotation_index=0, combos_per_run=combos_per_run) == ()


def test_company_cells_rotate_disjointly_and_cover_the_ring():
    """The rotation contract, at the end of the range the LIVE sizing actually sits in.

    `hub_nets` runs `c = 33` against `m = 35` — effectively no rotation. Company cells run
    `c = 12` against `m = 443`, so `2c <= m` holds with room and consecutive runs must be
    disjoint. Both arms of the condition are asserted, and the whole ring is covered in
    `ceil(m / c)` runs rather than merely touched.
    """
    companies = tuple(f"Company {i}" for i in range(8))       # m = 8, c = 4  ->  2c == m
    first = company_nets(("swe",), companies, rotation_index=0, combos_per_run=4)
    second = company_nets(("swe",), companies, rotation_index=1, combos_per_run=4)
    assert len(set(first)) == 4 and len(set(second)) == 4
    assert set(first) & set(second) == set()
    assert set(first) | set(second) == {f'"{c}" swe' for c in companies}

    # m < 2c: overlap is FORCED and is exactly 2c - m cells, the same pigeonhole as the hub axis.
    over = [company_nets(("swe",), companies, rotation_index=r, combos_per_run=6) for r in (0, 1)]
    assert len(set(over[0]) & set(over[1])) == 2 * 6 - 8

    # c >= m: the whole ring every run, and the rotation index cannot change it.
    assert len({company_nets(("swe",), companies, rotation_index=r, combos_per_run=8)
                for r in range(5)}) == 1


def test_a_run_counter_advances_the_company_window_even_when_two_runs_share_a_day():
    """`rotation_index` is the run id, not the date — runs here are on demand and several a day
    is the normal case, so a date-keyed window would make the second run of a day pay full price
    for cells the first had just fetched."""
    companies = tuple(f"Company {i}" for i in range(6))
    consecutive = [
        company_nets(("swe",), companies, rotation_index=r, combos_per_run=2) for r in (7, 8, 9)
    ]
    assert len(set(consecutive)) == 3
    assert set().union(*(set(c) for c in consecutive)) == {f'"{c}" swe' for c in companies}


def test_the_company_ring_is_a_function_of_the_list_AS_GIVEN_not_of_a_sets_iteration_order():
    """Deduplicating through a `set` would make the ring — and therefore which cells a given run
    draws — depend on hash order, so one run could not be reproduced from the store that produced
    it. First-seen order, both axes, exactly as `hub_nets` promises."""
    companies = ("Zeta", "Alpha", "Zeta", "Mu")
    assert company_nets(("swe",), companies, rotation_index=0, combos_per_run=99) == (
        '"Zeta" swe', '"Alpha" swe', '"Mu" swe',
    )
