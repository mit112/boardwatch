"""Company discovery from the two public GitHub new-grad lists (D-291).

Contract pinned 2026-08-24 in `docs/superpowers/research/2026-08-24-github-lists-contract.md`.
Two requests, and no others:

    GET https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json
    GET https://raw.githubusercontent.com/vanshb03/New-Grad-2027/dev/.github/scripts/listings.json

No token, no key, no cookie, no TLS bypass, no app impersonation.

THIS IS NOT A `Lane`, and the difference is structural rather than a naming preference. A lane
returns `LaneResult` -- postings plus an `AcquisitionTally` -- and this source has neither. No field
in any of the 34,958 records carries a job description, so there is no body to acquire; and
`lanes.dereference.parse_posting_target` covers four of the six providers, so a POSTING identity
cannot even be recovered for the workday and smartrecruiters records, which are 1,136 of the 1,991
in scope. What the records do carry is a board URL, which `core.board_urls.parse_board_target`
resolves for all six. So the deliverable is `(provider, slug)` COMPANIES and the postings are
thrown away. It is deliberately absent from `pipeline.runner.LANE_FACTORIES`: the pipeline would
call `collect(fetcher, admits)` on it every run, and there is nothing for that to return.

IT WRITES NOTHING TO THE STORE. The owner's ruling (D-291 build, decision 2) is that a human sits
between a public list and what the machine watches, because a bad slug becomes a permanently
failing board and there is no quarantine and no backoff for one today -- and this corpus contains a
live example, `boards.greenhouse.io/embed/job_app?token=<n>`, which parses to the board `embed`.
So this module emits a registry-format candidate file and `companies import` -- unchanged, and
still the only sanctioned watched-write -- executes the file a human read.

THE CAP LIVES HERE, on the emitter, and that placement is the substantive half of the design.
`lane_new_companies_per_run` is consulted in exactly one place, `pipeline/runner.py`'s
`CompanyBudget(...)`, on the UNWATCHED lane path -- nothing scans an unwatched board, because
`get_watched_companies` filters `watched.is_(True)` and is the only source of the scan's company
rows. The two writes that do set `watched=True`, `companies add` and `companies import`, have no cap
at all. Two placements were rejected. Capping `companies import` changes existing behaviour for
every user and needs a bypass flag for the ordinary case of importing a file you wrote yourself.
Adding a defaulted `watched=` to `upsert_watch` is already refused in `upsert_lane_company`'s own
docstring, and for the reason stated there: it would silently backfill every existing caller with a
value none of them chose. Capping the EMITTER changes nothing that exists, and puts the cap where
the provider cost model is already known.

THE RAMP IS STRATIFIED BY PROVIDER because the cost of a first exposure is not uniform. Five of the
six serve every board from ONE host, and `Fetcher` holds a per-host lock for each request's full
duration plus a >=1.0s pace, so boards on one provider serialize against each other and no worker
count compresses it. Only workday and smartrecruiters additionally spend `detail_fetch_budget` on a
per-posting GET, and boardwatch watches ZERO smartrecruiters boards today, so that path has never
run at scale. Cheapest first therefore means: the four inline-body providers, then workday, then
smartrecruiters last.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import zip_longest
from typing import Any

import yaml

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.politeness import Fetcher
from boardwatch.lanes.admission import CompanyBudget

SOURCE_NAME = "github_lists"

_LISTINGS_URL = "https://raw.githubusercontent.com/{repo}/dev/.github/scripts/listings.json"

# The owner's ruling is the NEW-GRAD pair. The two internship lists in the same family
# (`SimplifyJobs/Summer2026-Internships`, `vanshb03/Summer2027-Internships`) are 15,003 further
# records and 366 further boards, and widening to them is a separate decision, not a flag.
LIST_REPOS: tuple[str, ...] = ("SimplifyJobs/New-Grad-Positions", "vanshb03/New-Grad-2027")

LIST_URLS: tuple[tuple[str, str], ...] = tuple(
    (repo, _LISTINGS_URL.format(repo=repo)) for repo in LIST_REPOS
)

# COST TIERS, cheapest first, and the tier boundaries are what the ramp is about. A tier is a set
# of providers whose first-exposure cost is the same order of magnitude, so ordering WITHIN one is
# free -- and the batch is therefore spread round-robin across a tier's providers rather than
# draining one at a time. Two things that buys, both real: `Fetcher` holds a per-host lock for each
# request's full duration and five of the six providers serve every board from one host, so ten
# boards on one provider are ten SERIAL requests where ten across four providers are not; and
# workable, which boardwatch watches ZERO of today, would otherwise not be exercised until
# greenhouse's 147, lever's 62 and ashby's 167 were exhausted -- some 38 invocations of an
# unproven adapter's absence.
PROVIDER_TIERS: tuple[tuple[str, ...], ...] = (
    # Body inline with the listing: about one request per board.
    ("greenhouse", "lever", "ashby", "workable"),
    # Spends `detail_fetch_budget` on a per-posting GET for every unseen posting.
    ("workday",),
    # The same, and boardwatch watches none of them, so a first exposure here is the one cost this
    # repo has never measured. Last, and slowest, by the owner's ruling.
    ("smartrecruiters",),
)

PROVIDER_PRIORITY: tuple[str, ...] = tuple(
    provider for tier in PROVIDER_TIERS for provider in tier
)


class ListPayloadError(ValueError):
    """A listings response that is not the recorded bare JSON array.

    Distinct from `FetchFailure`, which the fetcher already raises for a transport or status
    failure. Raised rather than returning an empty list, because an empty list reaches the caller
    as "the list is empty today" -- and the whole file is one array, so anything else means the
    contract moved or something answered in its place. Both are things the operator has to see.
    """


class UnrankedProvider(ValueError):
    """A provider `parse_board_target` returned that the ramp has no cost ranking for.

    Raised at the ranking site rather than sorted quietly to the end. A seventh provider's
    first-exposure cost is unknown, and admitting it under the cap without placing it
    deliberately is how a ramp designed around a cost model stops respecting one.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"provider {provider!r} has no ramp ranking; add it to PROVIDER_PRIORITY at the "
            "position its first-exposure cost justifies"
        )
        self.provider = provider


@dataclass(frozen=True)
class RecordCensus:
    """Every record read, in exactly one bucket. Nothing is dropped silently.

    The four non-`matched` buckets are not failures in equal measure and are kept apart because a
    reader needs the difference: `inactive` is the owner's scope filter doing its job,
    `unparseable_url` is a host no provider here serves (47% of the corpus, and the reason a
    discovery source exists at all), and `no_url` is a defect in the source list.
    """

    records: int = 0
    inactive: int = 0
    no_url: int = 0
    unparseable_url: int = 0
    matched: int = 0

    @property
    def partitions(self) -> bool:
        return self.records == self.inactive + self.no_url + self.unparseable_url + self.matched


@dataclass(frozen=True)
class BoardCandidate:
    """One board a human is being asked to approve, with the evidence for it.

    `evidence_url` is the posting URL the target was parsed from, and it is not decoration: it is
    the only thing that makes a bad slug refusable at a glance. `greenhouse:embed` beside
    `.../embed/job_app?token=6099883` is obviously ATS chrome; `greenhouse:embed` beside an
    employer name is not.

    `records` is how many active records named this board. 627 of 926 live boards rest on exactly
    one, so a low count is the normal case rather than a warning -- but it is the only evidence
    of the slug that exists, so the reviewer gets to see it.
    """

    provider: str
    slug: str
    name: str
    evidence_url: str
    records: int


@dataclass(frozen=True)
class Discovery:
    census: RecordCensus
    # Distinct on `(provider, slug)`, in ramp order: cheapest provider first, then by slug so a
    # re-run before the file is imported emits the same batch.
    candidates: tuple[BoardCandidate, ...]


@dataclass(frozen=True)
class Selection:
    admitted: tuple[BoardCandidate, ...]
    refused: tuple[BoardCandidate, ...]
    already_known: tuple[BoardCandidate, ...]


# (provider, slug) -> is this company already stored, watched or not. The caller supplies it: the
# question needs a store connection, and `CompanyBudget` says in its own docstring that it cannot
# answer it. It must be `company_exists` and NOT the watched-only lookup -- a lane-discovered
# company is stored unwatched and would read as new forever, spending every cap slot on a company
# already stored.
KnownCompany = Callable[[str, str], bool]


def read_listings(content: bytes) -> list[dict[str, Any]]:
    """The recorded bare JSON array, non-record elements dropped.

    Contract §3: every root is an array with no envelope key, in all four sources.
    """
    try:
        payload = json.loads(content)
    except ValueError as exc:
        raise ListPayloadError(f"listings payload is not JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ListPayloadError(
            f"listings payload is {type(payload).__name__}, not the recorded bare array"
        )
    return [record for record in payload if isinstance(record, dict)]


def fetch_listings(fetcher: Fetcher) -> dict[str, list[dict[str, Any]]]:
    """One GET per in-scope repo, keyed by repo so a census can name its source.

    A failure propagates. This is a human-invoked command, not an additive pipeline stage, so a
    half-read corpus must not be reported as a smaller list -- the difference between "the list
    shrank" and "one request failed" is the whole diagnostic value.
    """
    return {repo: read_listings(fetcher.get(url).content) for repo, url in LIST_URLS}


def discover(sources: Mapping[str, Sequence[Mapping[str, Any]]]) -> Discovery:
    """Records -> distinct boards, in ramp order, with a census of everything read."""
    records = inactive = no_url = unparseable = matched = 0
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for rows in sources.values():
        for row in rows:
            records += 1
            # `is not True` rather than falsiness: the field is a real bool on 100% of records, so
            # a truthy string like "yes" would be the contract moving, not an active posting.
            if row.get("active") is not True:
                inactive += 1
                continue
            url = row.get("url")
            if not isinstance(url, str) or not url.strip():
                # Zero live records. Kept because `parse_board_target` takes a str and a missing
                # key would abort the whole discovery on an AttributeError, and because absence in
                # today's corpus means inert, not safe.
                no_url += 1
                continue
            try:
                provider, slug = parse_board_target(url)
            except UnknownBoardURL:
                # The ordinary case for 47% of records, not an error path: they sit on hosts no
                # provider here serves, which is what a discovery source is for. The 7 malformed
                # single-slash URLs land here too, and correctly -- an empty host is not a board.
                unparseable += 1
                continue
            matched += 1
            # Stripped: 114 live records are padded, and `scan/apply.py` feeds `companies.name`
            # into the `cross_host` posting identity, so a padded name silently re-keys every
            # identity written under it. Falls back to the slug rather than to a blank, because
            # `CompanyEntry.name` is required and a blank one is not reviewable.
            name = str(row.get("company_name") or "").strip() or slug
            grouped.setdefault((provider, slug), []).append((name, url))

    return Discovery(
        census=RecordCensus(
            records=records, inactive=inactive, no_url=no_url,
            unparseable_url=unparseable, matched=matched,
        ),
        candidates=tuple(
            BoardCandidate(
                provider=provider, slug=slug,
                # The first record that named this board. Every record in the group resolved to
                # one `(provider, slug)`, so they describe one employer's board.
                name=grouped[(provider, slug)][0][0],
                evidence_url=grouped[(provider, slug)][0][1],
                records=len(grouped[(provider, slug)]),
            )
            for provider, slug in ramp_order(grouped)
        ),
    )


def ramp_order(boards: Mapping[tuple[str, str], Any]) -> list[tuple[str, str]]:
    """`(provider, slug)` keys in admission order: tier by tier, round-robin inside a tier.

    Deterministic -- slug-sorted within each provider -- so re-running before the emitted file is
    imported produces the same batch rather than a different ten.
    """
    by_provider: dict[str, list[tuple[str, str]]] = {}
    for provider, slug in boards:
        if provider not in PROVIDER_PRIORITY:
            raise UnrankedProvider(provider)
        by_provider.setdefault(provider, []).append((provider, slug))
    ordered: list[tuple[str, str]] = []
    for tier in PROVIDER_TIERS:
        queues = [sorted(by_provider.get(provider, []), key=_by_slug) for provider in tier]
        for row in zip_longest(*queues):
            ordered.extend(key for key in row if key is not None)
    return ordered


def _by_slug(key: tuple[str, str]) -> str:
    return key[1]


def select(
    discovery: Discovery, *, is_known: KnownCompany, budget: CompanyBudget
) -> Selection:
    """Split the candidates three ways under the cap, in ramp order.

    An already-stored company is FREE and is charged nothing, which is the same rule
    `pipeline/runner.py`'s lane admission applies and for the same reason: charging it would spend
    every slot on companies already held and reach would never widen, while the refusal list
    looked exactly like a normal capped run.
    """
    admitted: list[BoardCandidate] = []
    refused: list[BoardCandidate] = []
    already_known: list[BoardCandidate] = []
    for candidate in discovery.candidates:
        if is_known(candidate.provider, candidate.slug):
            already_known.append(candidate)
        elif budget.admit(candidate.provider, candidate.slug):
            admitted.append(candidate)
        else:
            refused.append(candidate)
    return Selection(
        admitted=tuple(admitted), refused=tuple(refused), already_known=tuple(already_known)
    )


def candidate_document(
    selection: Selection, *, census: RecordCensus, generated_on: date
) -> str:
    """The registry-format file `companies import` accepts, behind a reviewable header.

    The header is comments, which `yaml.safe_load` ignores, and that is the only place the
    provenance can go: `CompanyEntry` sets `extra="forbid"`, so a `source_list` field on each
    entry would fail the very validator the file has to pass. It is not optional decoration --
    the owner reviews this file away from the terminal that produced it, so what it excluded has
    to travel with it.
    """
    payload = {
        "companies": [
            {"name": c.name, "provider": c.provider, "slug": c.slug, "tags": []}
            for c in selection.admitted
        ]
    }
    # `safe_dump` quotes any scalar whose plain form would resolve to something else, so a board
    # named `no`, `123` or `~` survives the round trip through `safe_load`. `allow_unicode` keeps
    # an accented employer name legible instead of escaped; the parsed value is the same either way.
    body: str = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return _header(selection, census, generated_on) + body


def _header(selection: Selection, census: RecordCensus, generated_on: date) -> str:
    total = len(selection.admitted) + len(selection.refused) + len(selection.already_known)
    lines = [
        "# boardwatch companies discover - candidate company boards, for review before import",
        "#",
        f"# generated {generated_on.isoformat()} from two public lists, read but not "
        "redistributed:",
    ]
    lines += [f"#   {repo}  {url}" for repo, url in LIST_URLS]
    lines += [
        "#",
        f"# records read {census.records} | inactive {census.inactive} "
        f"| no usable url {census.no_url} | host not served {census.unparseable_url} "
        f"| matched {census.matched}",
        f"# distinct boards {total} | already stored {len(selection.already_known)} "
        f"| admitted {len(selection.admitted)} | held back by the cap {len(selection.refused)}",
        "#",
    ]
    if selection.refused:
        held = ", ".join(
            f"{provider} {count}" for provider, count in _by_provider(selection.refused)
        )
        lines += [
            f"# HELD BACK BY THE CAP: {held}",
            "# Cheapest provider first; workday and smartrecruiters spend a per-posting detail",
            "# budget on a first scan, so they ramp last. Import this file, then re-run",
            "# `boardwatch companies discover` for the next batch.",
            "#",
        ]
    if selection.admitted:
        lines.append("# Check each evidence URL names a real employer board and not ATS chrome:")
        lines += [
            f"#   {c.provider}:{c.slug} | {c.name} | {c.records} record(s) | {c.evidence_url}"
            for c in selection.admitted
        ]
    else:
        lines.append("# No new boards. Nothing to import.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _by_provider(candidates: Sequence[BoardCandidate]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.provider] = counts.get(candidate.provider, 0) + 1
    return [(provider, counts[provider]) for provider in PROVIDER_PRIORITY if provider in counts]
