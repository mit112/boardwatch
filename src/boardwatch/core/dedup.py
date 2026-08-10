"""Resolve which postings are suppressed as duplicates (P6 design §2–§5).

Pure: no DB, no I/O, no clock. Identities are passed in rather than computed here, because
that is the axis on which the production path (stored rows) and the verification recount
(recomputed rows) differ — see design §6.3.

Precision over recall throughout. Every ambiguous case resolves to "do not suppress": a
leaked duplicate is counted and recoverable, a suppressed real lead is neither.

`exact_quad` is the only kind that reaches a suppression, because resolve_duplicates
iterates SUPPRESSING_KINDS and the catalog lists nothing else. The cross_host election lives
here, is exercised directly by tests, and is currently unreachable from resolve_duplicates.
That is the deferral, not an oversight: design §3.1 records why cross_host may not suppress
(PROGRAM item 1, core/identity.py:3, and a concrete false-suppression counterexample) and
what has to become true before it can. Do not delete it, and do not enable it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boardwatch.core.host_class import classify_host
from boardwatch.core.identity_kinds import SUPPRESSING_KINDS
from boardwatch.core.normalize import normalize_body, normalize_company, normalize_title
from boardwatch.core.posting_identity import (
    IdentityInputs,
    PostingIdentity,
    normalized_locations,
)

_HOST_RANK = {"ats": 0, "unknown": 1, "aggregator": 2}


class MissingSuppressionResolver(ValueError):
    """A kind is marked `suppresses=True` in the catalog but has no resolver here."""

    def __init__(self, name: str) -> None:
        super().__init__(f"suppressing kind has no resolver: {name!r}")
        self.name = name


@dataclass(frozen=True)
class Suppression:
    posting_id: int
    survivor_posting_id: int
    kind: str


def _elect(members: Sequence[IdentityInputs]) -> IdentityInputs:
    """Deterministic survivor: host class, then earliest first_seen_at, then lowest id.

    Score is never a tiebreaker. Scores move when the profile, taxonomy or ranker changes,
    and a survivor that changes identity between runs makes duplicate leakage unmeasurable
    across the 7-day window Gate P6 requires.
    """
    return min(
        members,
        key=lambda m: (_HOST_RANK[classify_host(m.url or "")], m.first_seen_at, m.posting_id),
    )


def _verify_quad(a: IdentityInputs, b: IdentityInputs) -> bool:
    """Re-compare the underlying strings before acting on a hash equality.

    body_text and content_hash are NOT NULL in the schema, so there is no missing-body
    branch. Locations are checked for PRESENCE, not merely for equality, and that is not
    belt-and-braces: `compute_identities` emits no exact_quad without location evidence
    (design §2.1), but this resolver groups **stored** identities, and nothing in the scan
    path rewrites them. `scan/apply.py` refreshes `locations_json` on every observation
    while `identities_complete` only checks that a current-version row EXISTS, never that
    it is fresh. So a stale exact_quad can group two postings that today carry no location
    evidence at all — and two Nones compare EQUAL, which would pass this check and suppress
    on evidence the catalog marks non-suppressing. Requiring presence keeps D-083's rule
    ("no location evidence => no location-bearing suppression") true on the stored path and
    not just the computed one.
    """
    loc_a = normalized_locations(a.locations)
    return (
        a.company_id == b.company_id
        and normalize_title(a.title) == normalize_title(b.title)
        and loc_a is not None
        and loc_a == normalized_locations(b.locations)
        and normalize_body(a.body_text) == normalize_body(b.body_text)
    )


def _verify_cross_host(a: IdentityInputs, b: IdentityInputs) -> bool:
    return (
        normalize_company(a.company_name) == normalize_company(b.company_name)
        and normalize_title(a.title) == normalize_title(b.title)
        and normalized_locations(a.locations) == normalized_locations(b.locations)
    )


def _resolve_exact_quad(
    members: Sequence[IdentityInputs],
) -> tuple[IdentityInputs, list[IdentityInputs]]:
    survivor = _elect(members)
    losers = [m for m in members if m is not survivor and _verify_quad(survivor, m)]
    return survivor, losers


def elect_cross_host_survivor(members: Sequence[IdentityInputs]) -> IdentityInputs | None:
    """The direct-ATS row to keep, or None when the choice is not forced.

    Public and directly tested, but NOT reachable from resolve_duplicates while
    cross_host.suppresses is False — see the module docstring. Keep exactly one ATS row and
    at least one aggregator to drop; anything else (no ATS, two ATS, nothing to drop) is
    ambiguous and elects nothing. `unknown` rows are neither kept nor dropped.
    """
    ats = [m for m in members if classify_host(m.url or "") == "ats"]
    aggregators = [m for m in members if classify_host(m.url or "") == "aggregator"]
    if len(ats) != 1 or not aggregators:
        return None
    return ats[0]


def _resolve_cross_host(
    members: Sequence[IdentityInputs],
) -> tuple[IdentityInputs, list[IdentityInputs]]:
    survivor = elect_cross_host_survivor(members)
    if survivor is None:
        return members[0], []
    losers = [
        m
        for m in members
        if m is not survivor
        and classify_host(m.url or "") == "aggregator"
        and _verify_cross_host(survivor, m)
    ]
    return survivor, losers


# Dispatch table. resolve_duplicates iterates SUPPRESSING_KINDS, which today contains only
# exact_quad, so the cross_host entry is deliberately unreachable — see the module docstring.
_RESOLVERS = {"exact_quad": _resolve_exact_quad, "cross_host": _resolve_cross_host}


def resolve_duplicates(
    rows: Sequence[IdentityInputs],
    identities: Mapping[int, tuple[PostingIdentity, ...]],
) -> tuple[Suppression, ...]:
    by_id = {r.posting_id: r for r in rows}
    suppressed: dict[int, Suppression] = {}
    for spec in SUPPRESSING_KINDS:
        groups: dict[str, list[IdentityInputs]] = defaultdict(list)
        for posting_id, row in sorted(by_id.items()):
            if posting_id in suppressed:
                continue
            for identity in identities.get(posting_id, ()):
                if identity.kind == spec.name:
                    groups[identity.identity_key].append(row)
        for members in groups.values():
            if len(members) < 2:
                continue
            try:
                resolver = _RESOLVERS[spec.name]
            except KeyError:
                # Typed at the raise site, not a bare KeyError surfacing from inside the
                # ranker. Reachable by a one-line catalog edit — flipping `suppresses=True`
                # on content_hash_only or company_title_location names a suppressing kind
                # with no resolver — which is exactly the "a config override reaches it"
                # case that must be handled rather than deferred as unreachable.
                raise MissingSuppressionResolver(spec.name) from None
            survivor, losers = resolver(members)
            for loser in losers:
                suppressed[loser.posting_id] = Suppression(
                    posting_id=loser.posting_id,
                    survivor_posting_id=survivor.posting_id,
                    kind=spec.name,
                )
    return tuple(sorted(suppressed.values(), key=lambda s: s.posting_id))
