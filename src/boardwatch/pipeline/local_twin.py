"""Record the employer's own posting as a lane copy's application destination (D-689).

A lane posting (LinkedIn, Indeed, the job-apps lane, any provider outside the registry) is often
only a wrapper around a posting the store already holds from the employer's own board. This step
finds that posting with no browser and no model, and records its URL through
`record_application_destination`, so the lead is delivered with a link that can be applied to and
with the requisition key the duplicate holds read (D-654, D-655, D-677).

**The rule (version 1).** All three must hold, and the answer must be unique:

1. *Company.* The lane company's name equals a watched registry-provider company's, by the first
   of: `normalize_company` equality; equality after trailing generic words are removed; the
   name's letters and digits equal the company's slug. A name with fewer than three letters or
   digits never matches.
2. *Title.* `postings.normalized_title` equality, with year tokens dropped.
3. *Place.* Among that company's OPEN postings with that title, exactly one shares a city with
   the lane posting, or is remote when the lane posting is remote. None or several: no write.

**What it refuses.** A lane posting that already names a different requisition in its own URL
(`requisition_key`) is a different opening, whatever its title and city say. A posting that
already has a destination is never touched, so a browser-verified link always wins and a second
run writes nothing.

Measured precision is in D-689: the rule is right for most matches, not all, and a wrong match
puts the employer's other opening behind the same requisition hold as this one.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Row, select

from boardwatch.core.normalize import canonical_location, normalize_company
from boardwatch.lanes.dereference import posting_requisition_key
from boardwatch.providers.registry import PROVIDER_NAMES
from boardwatch.rank.location_data import US_COUNTRY_SEGMENTS, US_STATE_ABBREVS, US_STATE_NAMES
from boardwatch.store.application_destinations import (
    InvalidApplicationDestinationError,
    record_application_destination,
)
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.queries import jobapps_employer_url
from boardwatch.store.tables import application_destinations, companies, postings

EVIDENCE_PREFIX = "local-twin:v1:"

# Words a lane writes after an employer's name and the employer's board does not, or the reverse.
# Trailing only, and only as a second attempt after plain equality found nothing.
_GENERIC_TAIL = frozenset({"company", "group", "solutions", "technologies", "holdings", "labs"})
_MIN_NAME_CHARS = 3
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_YEAR = re.compile(r"\b20\d\d\b")
_WS = re.compile(r"\s+")
_REMOTE = re.compile(r"\bremote\b")
_NOT_A_CITY = US_COUNTRY_SEGMENTS | US_STATE_ABBREVS | {"remote", ""}


@dataclass(frozen=True)
class TwinMatch:
    posting_id: int
    twin_posting_id: int
    url: str
    source_url: str


@dataclass(frozen=True)
class TwinReport:
    """What one pass did. `considered` is lane postings with no destination, not all the ids."""

    considered: int = 0
    company_matched: int = 0
    written: int = 0


def _without_generic_tail(name: str) -> str:
    words = name.split()
    while words and words[-1] in _GENERIC_TAIL:
        words.pop()
    return " ".join(words)


def _long_enough(key: str) -> bool:
    return len(_NON_ALNUM.sub("", key)) >= _MIN_NAME_CHARS


def _title_key(normalized_title: str) -> str:
    return _WS.sub(" ", _YEAR.sub(" ", normalized_title)).strip()


def _segments(location: str) -> list[str]:
    return [segment.strip() for segment in canonical_location(location).split(",")]


def _words(text: str) -> str:
    return _WS.sub(" ", _NON_ALNUM.sub(" ", text.lower())).strip()


def _strings(locations: object) -> list[str]:
    if not isinstance(locations, list):
        return []
    return [item for item in locations if isinstance(item, str)]


def _shares_city(lane_locations: object, board_locations: object) -> bool:
    """Whether a city the lane posting names is one the board posting names.

    The lane side is read strictly: a location's first segment is its city, unless it is a
    country, a state, or a bare name that is also a state ("New York", "Washington"). The board
    side is read loosely, because boards write a place as "US,TX,Austin", "San Jose (CA)" or
    "HQ - New York City": the city must occur as whole words in a segment that is not itself a
    state or a country ("Seattle, Washington" canonicalizes to "seattle, wa", so "Washington,
    DC" is not found in it). A board location that names a different state is another place
    ("Columbus, OH" / "Columbus, GA").
    """
    board = [_segments(item) for item in _strings(board_locations)]
    for item in _strings(lane_locations):
        segments = _segments(item)
        city = segments[0]
        if city in _NOT_A_CITY or (len(segments) == 1 and city in US_STATE_NAMES):
            continue
        state = segments[1] if len(segments) > 1 and segments[1] in US_STATE_ABBREVS else None
        pattern = re.compile(rf"\b{re.escape(_words(city))}\b")
        if not _words(city):
            continue
        for other in board:
            other_state = other[1] if len(other) > 1 and other[1] in US_STATE_ABBREVS else None
            if state is not None and other_state is not None and state != other_state:
                continue
            if any(
                pattern.search(_words(segment)) for segment in other if segment not in _NOT_A_CITY
            ):
                return True
    return False


def _is_remote(remote_policy: str, locations: object) -> bool:
    if remote_policy == "remote":
        return True
    return isinstance(locations, list) and any(
        isinstance(item, str) and _REMOTE.search(item.lower()) for item in locations
    )


class _DirectCompanies:
    """The watched registry-provider companies, indexed the three ways a lane name may match."""

    def __init__(self, rows: Iterable[tuple[int, str, str]]) -> None:
        self._by_name: dict[str, list[int]] = {}
        self._by_trimmed: dict[str, list[int]] = {}
        self._by_slug: dict[str, list[int]] = {}
        for company_id, name, slug in rows:
            key = normalize_company(name)
            self._by_name.setdefault(key, []).append(company_id)
            self._by_trimmed.setdefault(_without_generic_tail(key), []).append(company_id)
            self._by_slug.setdefault(slug.lower(), []).append(company_id)

    def matching(self, lane_name: str) -> tuple[int, ...]:
        key = normalize_company(lane_name)
        attempts: tuple[tuple[str, Mapping[str, list[int]]], ...] = (
            (key, self._by_name),
            (_without_generic_tail(key), self._by_trimmed),
            (_NON_ALNUM.sub("", lane_name.lower()), self._by_slug),
        )
        for candidate, index in attempts:
            if _long_enough(candidate) and candidate in index:
                return tuple(index[candidate])
        return ()


def find_local_twins(
    conn: Connection, posting_ids: Sequence[int], *, exclude_job_ids: Collection[int] = ()
) -> tuple[list[TwinMatch], int, int]:
    """(matches, lane postings considered, of those with a company match). Reads only.

    `exclude_job_ids` are jobs the owner has already applied to. A destination gives a posting
    its twin's requisition key, and an applied requisition holds every copy for good, so a wrong
    match there would hide another opening permanently; an unapplied one drains when its holder
    closes.
    """
    wrappers: list[Row[Any]] = []
    for chunk in id_chunks(sorted(set(posting_ids))):
        wrappers += conn.execute(
            select(
                postings.c.id, postings.c.url, postings.c.normalized_title,
                postings.c.locations_json, postings.c.remote_policy, companies.c.name,
                postings.c.job_id, jobapps_employer_url().label("employer_url"),
            )
            .join(companies, companies.c.id == postings.c.company_id)
            .where(
                postings.c.id.in_(chunk),
                postings.c.status == "open",
                postings.c.url.is_not(None),
                companies.c.provider.not_in(PROVIDER_NAMES),
                ~select(application_destinations.c.posting_id)
                .where(application_destinations.c.posting_id == postings.c.id)
                .exists(),
            )
        ).all()
    wrappers = [row for row in wrappers if row.job_id not in exclude_job_ids]
    if not wrappers:
        return [], 0, 0
    direct = _DirectCompanies(
        (int(row.id), str(row.name), str(row.slug))
        for row in conn.execute(
            select(companies.c.id, companies.c.name, companies.c.slug).where(
                companies.c.watched.is_(True), companies.c.provider.in_(PROVIDER_NAMES)
            )
        )
    )
    company_ids = {row.id: direct.matching(str(row.name)) for row in wrappers}
    wanted = {company_id for ids in company_ids.values() for company_id in ids}
    # One read of the matched employers' open postings, by company, through `ix_postings_corpus`.
    by_company_title: dict[tuple[int, str], list[tuple[int, str, object, str]]] = {}
    for chunk in id_chunks(sorted(wanted)):
        for row in conn.execute(
            select(
                postings.c.id, postings.c.company_id, postings.c.normalized_title,
                postings.c.url, postings.c.locations_json, postings.c.remote_policy,
            ).where(
                postings.c.status == "open",
                postings.c.company_id.in_(chunk),
                postings.c.url.is_not(None),
            )
        ):
            by_company_title.setdefault(
                (int(row.company_id), _title_key(str(row.normalized_title))), []
            ).append((int(row.id), str(row.url), row.locations_json, str(row.remote_policy)))

    matches: list[TwinMatch] = []
    for row in wrappers:
        title = _title_key(str(row.normalized_title))
        remote = _is_remote(str(row.remote_policy), row.locations_json)
        same_place = [
            twin
            for company_id in company_ids[row.id]
            for twin in by_company_title.get((company_id, title), ())
            if _shares_city(row.locations_json, twin[2])
            or (remote and _is_remote(twin[3], twin[2]))
        ]
        if not title or len(same_place) != 1:
            continue
        twin_id, twin_url, _, _ = same_place[0]
        # The lane posting's own URL may already name a requisition. The same one needs no
        # link; a different one is a different opening with the same title in the same city.
        if posting_requisition_key(str(row.url), row.employer_url) is not None:
            continue
        matches.append(TwinMatch(int(row.id), twin_id, twin_url, str(row.url)))
    return matches, len(wrappers), sum(1 for row in wrappers if company_ids[row.id])


def record_local_twins(
    conn: Connection,
    posting_ids: Sequence[int],
    *,
    now: datetime,
    exclude_job_ids: Collection[int] = (),
) -> TwinReport:
    """Write a destination for every lane posting in `posting_ids` with exactly one twin."""
    matches, considered, company_matched = find_local_twins(
        conn, posting_ids, exclude_job_ids=exclude_job_ids
    )
    written = 0
    for match in matches:
        try:
            written += record_application_destination(
                conn,
                posting_id=match.posting_id,
                url=match.url,
                source_url=match.source_url,
                evidence_ref=f"{EVIDENCE_PREFIX}{match.twin_posting_id}",
                verified_at=now,
            )
        except InvalidApplicationDestinationError:
            continue  # the twin's stored URL is not one a destination may hold
    return TwinReport(considered=considered, company_matched=company_matched, written=written)
