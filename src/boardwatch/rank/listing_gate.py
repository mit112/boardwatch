"""The ranker's own title and location vetoes, asked of a listing before any detail fetch (D-663).

No rule lives here. A posting this rejects is one `top` would reject from the same fields, so what
it saves is the fetch and the row, never a lead. Fail-open by construction: both vetoes keep what
they cannot read, and a missing taxonomy abstains.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from boardwatch.core.models import ListingGate
from boardwatch.eligibility.engine import digest_of_sources
from boardwatch.rank.heuristic import ProfileView, hard_filter_verdict
from boardwatch.rank.role_gate import taxonomy_role_verdict
from boardwatch.rank.role_taxonomy import RoleTaxonomy, role_taxonomy_digest

#: The key of a scan that ran with no gate: the setting off, no profile, or a taxonomy that would
#: not load. Not a digest, so no armed gate's key can equal it.
LISTING_GATE_OFF_KEY = "listing-gate-off"


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


def listing_gate_key(
    profile: ProfileView, taxonomy: RoleTaxonomy | None, location_filter_mode: str
) -> str:
    """A digest of everything `build_listing_gate` is built from, so two gates share a key only
    when they rule identically on every listing.

    The WHOLE profile view, not only the fields the two vetoes read today: a field left out is a
    gate change this key cannot see, and an extra field costs at most one unneeded full read.
    The gate's own code is in it too, every module of `rank/`, whose vetoes the gate runs: a
    release that relaxes a veto must not reuse a validator learned under the stricter one.
    T353's scan manifest and T355's validator binding both use this one function (and T339's
    `gate_key` is to).
    """
    view = asdict(profile)
    view["skills"] = sorted(profile.skills)
    payload = {
        "code": _gate_code_digest(),
        "profile": view,
        "taxonomy": role_taxonomy_digest(taxonomy),
        "location_filter_mode": location_filter_mode,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=1)
def _gate_code_digest() -> str:
    """A digest of `rank/`, through the same `digest_of_sources` as the scan-code digest, so a
    comment or formatting edit does not change it."""
    files = sorted(Path(__file__).resolve().parent.glob("*.py"))
    return digest_of_sources([path.read_text(encoding="utf-8") for path in files])
