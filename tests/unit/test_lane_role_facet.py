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

from boardwatch.lanes.facets import MAX_FACETS_PER_RUN, role_facets


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
