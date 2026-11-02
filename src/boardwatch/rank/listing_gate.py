"""The ranker's own title and location vetoes, asked of a listing before any detail fetch (D-663).

No rule lives here. A posting this rejects is one `top` would reject from the same fields, so what
it saves is the fetch and the row, never a lead. Fail-open by construction: both vetoes keep what
they cannot read, and a missing taxonomy abstains.
"""

from __future__ import annotations

from collections.abc import Sequence

from boardwatch.core.models import ListingGate
from boardwatch.rank.heuristic import ProfileView, hard_filter_verdict
from boardwatch.rank.role_gate import taxonomy_role_verdict
from boardwatch.rank.role_taxonomy import RoleTaxonomy


def build_listing_gate(
    profile: ProfileView, taxonomy: RoleTaxonomy | None, location_filter_mode: str
) -> ListingGate:
    def gate(title: str, locations: Sequence[str], remote_policy: str) -> str | None:
        if not title:
            return None
        veto = hard_filter_verdict(title, locations, remote_policy, profile, location_filter_mode)
        # Two vetoes rule on what a listing may have left out, and only the detail can state it: a
        # remote policy, and a location, since a foreign ad marker fires only on one it cannot read.
        needs_the_detail = veto is not None and (
            veto.clause == "foreign_ad_marker"
            or (veto.clause == "remote_only" and remote_policy == "unknown")
        )
        if veto is not None and not needs_the_detail:
            return veto.clause
        role, _ = taxonomy_role_verdict(title, taxonomy)
        return "out_of_field" if role == "out_of_field" else None

    return gate
