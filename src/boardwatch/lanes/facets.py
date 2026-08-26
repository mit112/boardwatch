"""The user's target job titles as lane search facets.

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
change for a user whose targets are nursing roles. This module holds a normalization rule and a
budget, and no titles.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# One facet is one search request, so an uncapped profile is an uncapped request count. Sized to
# clear a realistic profile with headroom rather than to bind one: the live profile lists 14
# target titles. It bounds SEARCH requests only — body GETs stay bounded by the lane's own
# posting budget, so a wider facet set buys a better candidate pool at the same body cost.
MAX_FACETS_PER_RUN = 16

# Runs of anything that is not a letter or digit collapse to one separator. A slash surviving
# into a slug would change which URL is requested -- `/jobs/a/b` is not the role route -- so
# this is a routing invariant, not tidiness.
_SEPARATORS = re.compile(r"[^a-z0-9]+")


def role_facets(target_titles: Sequence[str] | None) -> tuple[str, ...]:
    """`profile.target_titles_json` as at most `MAX_FACETS_PER_RUN` facet slugs.

    First-seen order is preserved, and the cap TRUNCATES in that order rather than sampling: a
    run whose facet set varied between invocations could not be reproduced from the profile that
    produced it.

    A title that normalizes to nothing yields no facet rather than an empty one. An empty slug
    would build the aggregator's UNFACETED listing, which is a different page, so a blank target
    title would silently restore the noise the facet exists to remove while the run reported that
    a facet had been applied.
    """
    facets: list[str] = []
    for title in target_titles or ():
        slug = _SEPARATORS.sub("-", title.lower()).strip("-")
        if slug and slug not in facets:
            facets.append(slug)
        if len(facets) == MAX_FACETS_PER_RUN:
            break
    return tuple(facets)
