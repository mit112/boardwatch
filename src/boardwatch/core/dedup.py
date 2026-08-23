"""Resolve which postings are suppressed as duplicates (P6 design §2–§5).

Pure: no DB, no I/O, no clock. Identities are passed in rather than computed here, because
that is the axis on which the production path (stored rows) and the verification recount
(recomputed rows) differ — see design §6.3.

Precision over recall throughout. Every ambiguous case resolves to "do not suppress": a
leaked duplicate is counted and recoverable, a suppressed real lead is neither.

`resolve_duplicates` iterates SUPPRESSING_KINDS in rank order, so a posting suppressed by a
stronger kind is never re-examined by a weaker one. Two kinds reach a suppression today:
`exact_quad` and, since D-294, `company_title_location`.

`company_title_location` does NOT merge — see identity_kinds.MERGING_KINDS. It is the
weaker claim ("the same role at the same place") and its key carries no body evidence, so
the two postings under it may legitimately be two different openings. The owner accepted
that cost against a measured 1,597 redundant open postings (4.76%) whose members all carry
distinct `exact_quad` keys and which therefore reached leads twice. Callers that PERSIST a
grouping must filter to MERGING_KINDS first; the ranker's read path does not.

The cross_host election lives here, is exercised directly by tests, and is currently
unreachable from resolve_duplicates. That is the deferral, not an oversight: design §3.1
records why cross_host may not suppress (PROGRAM item 1, core/identity.py:3, and a concrete
false-suppression counterexample) and what has to become true before it can. Do not delete
it, and do not enable it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boardwatch.core.host_class import classify_host
from boardwatch.core.identity_kinds import MERGING_KIND_NAMES, SUPPRESSING_KINDS
from boardwatch.core.normalize import normalize_company, normalize_title
from boardwatch.core.posting_identity import (
    IdentityInputs,
    PostingIdentity,
    body_evidence,
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

    Locations AND body are checked for PRESENCE, not merely for equality, and that is not
    belt-and-braces: `compute_identities` emits no exact_quad without either (design §2.1;
    §4.3 of the JD-acquisition spec), but this resolver groups **stored** identities, and
    nothing in the scan path rewrites them. `scan/apply.py` refreshes `locations_json` and
    `body_text` on every observation while `identities_complete` only checks that a
    current-version row EXISTS, never that it is fresh. So a stale exact_quad can group two
    postings that today carry no evidence at all — and two absent values compare EQUAL,
    which would pass this check and suppress on evidence the catalog marks non-suppressing.

    body_text and content_hash being NOT NULL does not close this: NOT NULL is not
    non-empty. A stub stores "" or whitespace, `content_hash` folds every stub to the
    SHA-256 of the empty string, and `"" == ""` passes — so before the presence check, two
    genuinely different body-less postings at one company sharing a normalized title and
    locations suppressed each other with this verifier agreeing.

    Requiring presence keeps D-083's rule ("no location evidence => no location-bearing
    suppression") and its body counterpart true on the stored path, not just the computed
    one. It also retires the stale rows without an IDENTITY_ALGORITHM_VERSION bump: they
    stop being actionable here, and `write_identities` drops each one as an unwanted kind
    the next time that posting's identities are written.
    """
    loc_a = normalized_locations(a.locations)
    body_a = body_evidence(a.body_text)
    return (
        a.company_id == b.company_id
        and normalize_title(a.title) == normalize_title(b.title)
        and loc_a is not None
        and loc_a == normalized_locations(b.locations)
        and body_a is not None
        and body_a == body_evidence(b.body_text)
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


def _verify_company_title_location(a: IdentityInputs, b: IdentityInputs) -> bool:
    """Re-compare the strings behind a company_title_location hash before acting on it.

    The `exact_quad` verifier's reasoning applies here minus the body clause, and the
    location PRESENCE check is the load-bearing half. `compute_identities` emits no
    company_title_location without locations (design §2.1), but this resolver groups STORED
    identities and `scan/apply.py` refreshes `locations_json` without rewriting them, so a
    stale key can group two postings that today carry no location evidence at all — and two
    absent values compare EQUAL. `normalized_locations` returns None for absence rather than
    "[]" precisely so that case is representable; requiring non-None is what keeps D-083's
    rule ("no location evidence => no location-bearing suppression") true on the stored path.

    The body is deliberately NOT compared. Comparing it would reconstruct `exact_quad` and
    this kind would suppress nothing that exact_quad had not already taken.
    """
    loc_a = normalized_locations(a.locations)
    return (
        a.company_id == b.company_id
        and normalize_title(a.title) == normalize_title(b.title)
        and loc_a is not None
        and loc_a == normalized_locations(b.locations)
    )


def _resolve_company_title_location(
    members: Sequence[IdentityInputs],
) -> tuple[IdentityInputs, list[IdentityInputs]]:
    survivor = _elect(members)
    losers = [
        m for m in members if m is not survivor and _verify_company_title_location(survivor, m)
    ]
    return survivor, losers


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


# Dispatch table. resolve_duplicates iterates SUPPRESSING_KINDS — exact_quad and
# company_title_location — so the cross_host entry is deliberately unreachable; see the
# module docstring.
_RESOLVERS = {
    "exact_quad": _resolve_exact_quad,
    "company_title_location": _resolve_company_title_location,
    "cross_host": _resolve_cross_host,
}


def mergeable_suppressions(
    suppressions: Sequence[Suppression],
) -> dict[str, tuple[Suppression, ...]]:
    """Suppressions a caller may PERSIST as a job merge, grouped by kind.

    Every caller that writes `postings.job_id` goes through this rather than through
    `resolve_duplicates` directly. Before D-294 there was one suppressing kind and it was
    also the only merging one, so both merge sites passed `identity_kind="exact_quad"` as a
    literal. The moment a second kind suppresses, that literal becomes a lie AND the weaker
    kind silently gains the power to rewrite job anchors — which is not what was ruled.

    The grouping is by kind rather than a flat list because `apply_merges` stamps ONE
    `method` per batch onto the append-only `job_grouping_events` row; a flat list would have
    to invent a stamp for a mixed batch.
    """
    grouped: dict[str, list[Suppression]] = {}
    for suppression in suppressions:
        if suppression.kind in MERGING_KIND_NAMES:
            grouped.setdefault(suppression.kind, []).append(suppression)
    return {kind: tuple(items) for kind, items in grouped.items()}


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
