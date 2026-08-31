"""Ingest job-apps' daily discovery output as a lane (D-385).

job-apps reaches postings boardwatch does not. Measured against the live store on 2026-08-31:
of its 189 direct-apply records, **160 are absent from this store by URL**, and 103 of its 149
employers are unknown here by name. 126 of those 189 -- two thirds -- arrived through job-apps'
hiring.cafe acquisition, which is exactly the reach boardwatch's OWN hiring.cafe lane cannot get
while it is taking 14 facet refusals per run. Routing around a lane that is down is this lane's
largest single contribution, not a side effect.

A LANE and not a seventh provider, for the reasons `lanes/base.py` states: the provider registry
is a closed six-member catalog asserted by set EQUALITY, and fixture rule R13 wants a pinned
fixture dir per registered provider in both directions. A lane returns the same `BoardSnapshot`
and inherits every persistence, identity and dedup invariant rather than restating them.

**job-apps contributes DISCOVERY; boardwatch keeps every DECISION.** No field this module reads
carries job-apps' judgement, and that is enforced by reading a WHITELIST -- `canonical`,
`posting_id`, `primary_acquisition`, `cohort_date`, `schema_version` -- rather than by skipping a
blacklist, because the leak paths here are easy to absorb by accident. Deliberately unread:
`dispositions[]` (stage / outcome / reason / artifact_path) and `observations[]` (employer
verification, target flags, query kind). Deliberately stripped: the authored JD header, which
carries `Template:`, `Fit: N/100` and `Target:` lines and has already leaked into one supposedly
blind audit set. Deliberately not walked: `_skipped/<reason>/`, whose DIRECTORY NAMES
(`posting_closed`, `eligibility_review`, `non_swe_role`, `senior_title`) are job-apps' verdicts
in path form -- an ingester that recursed would inherit them silently. Two systems' verdicts in
one queue is the second opinion `_review` exists to prevent.

## Why this lane never reports a benign zero

The source is a directory, so the failure this lane must not have is the one an operator cannot
see: a renamed or moved queue, or a layout change, yielding an empty `LaneResult` that reads
exactly like a quiet feed. It cannot be distinguished by posting count, because job-apps has
hard ZERO-cohort days on weekends -- so "no fresh records today" is normal and carries no signal.

Two things close that hole, and neither is new machinery:

* The whole tree is read every run, never just today's cohort. The tree holds ~737 records on a
  weekend as on a weekday, so `attempted` is stable by construction and a structural break is
  the only thing that can drive it to zero.
* A source that is absent, unreadable, or holds no record at all raises `JobAppsSourceError`,
  which `_run_lanes` catches PER LANE into `summary.errors`. A lane may never fail the run, and
  this one does not; it fails LOUDLY instead of returning zeros. Where the source is intact but
  no body could be recovered from it, the existing `AcquisitionTally.is_silent_outage` already
  says so, and it is already carried into the funnel and printed by `run`.

Per-record problems are counted, never raised: one malformed JD must not take the other 188 with
it.

## What this lane does NOT fix

Lane snapshots are always `partial`, so `_process_missing` never runs and a lane posting cannot
close by enumeration (D-314). Ingesting here therefore adds postings that only the death probe
and the zero-signal veto can ever retire. That is a known standing cost, recorded rather than
worked around: job-apps itself has 466 records under `_skipped/posting_closed`, so the closure
rate on this population is not small.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.models import RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.lanes.base import (
    CompanyAdmission,
    LaneCompanySnapshot,
    LaneResult,
    lane_snapshot,
)
from boardwatch.lanes.dereference import UnresolvablePostingURL, parse_posting_target
from boardwatch.lanes.outcomes import AcquisitionTally

LANE_NAME = "jobapps"

# The provider string for a record whose URL this repo cannot dereference. Non-catalog by
# design: `upsert_lane_company` writes `watched=False`, so the scan coordinator's
# unknown-provider branch never fires for it.
LANE_PROVIDER = "jobapps"

_RECORD_NAME = "discovery_record.json"
_JD_NAME = "job_description.txt"

# Pinned so a source-format change FAILS rather than being read under the old assumptions. All
# 737 live records carry 2; a record at any other version is counted and skipped, because the
# field positions this module reads may have moved.
SUPPORTED_SCHEMA_VERSION = 2

# Skipped BY NAME, and the reason is the whole point: these two hold job-apps' own dispositions
# as directory names. `_applied` is a separate ingestion concern (marking a lead applied) with a
# separate design; it is not discovery and does not belong here.
_SKIP_DIRS = frozenset({"_applied", "_skipped"})

# job-apps' authored header sits above every JD body, and the separator is a THREE-line sandwich
# -- byte-identical in 930 of 930 sampled files. Parsing on the single rule line would match the
# first of the three and keep two lines of header.
_SEPARATOR = "=" * 80
_HEADER_MARKER = f"{_SEPARATOR}\nJOB DESCRIPTION\n{_SEPARATOR}"

# `primary_acquisition` values whose `direct_url` is a real apply page. Measured: these yield a
# direct-apply URL 100% of the time, while `linkedin`, `indeed` and `jobright` yield one 0% of
# the time -- 74.9% of all records are aggregator pages with no reachable posting behind them.
# A closed set, so a NEW acquisition source is skipped-and-counted rather than silently trusted.
_DIRECT_APPLY_SOURCES = frozenset(
    {"hiringcafe", "simplify", "speedyapply", "zapply", "hn", "vanshb03"}
)
_DIRECT_APPLY_SUFFIX = "_api"


class JobAppsSourceError(ValueError):
    """The source tree is absent, unreadable, or holds no discovery record at all.

    Raised rather than returned as an empty result, so `_run_lanes` reports it into
    `summary.errors` instead of the run recording a zero nobody can tell from a quiet feed.
    """


@dataclass(frozen=True)
class _Record:
    """One discovery record, reduced to the fields this module is allowed to read."""

    posting_id: str
    company: str
    title: str
    direct_url: str
    location: str
    primary_acquisition: str
    cohort_date: str | None
    # Where it was read from. Travels with the record so the body read needs no lookup table and
    # `collect` keeps no state between calls.
    folder: Path


@dataclass(frozen=True)
class _Identity:
    provider: str
    slug: str
    posting_ref: str


def is_direct_apply(primary_acquisition: str) -> bool:
    """Does this acquisition source yield a real apply URL?

    Named and exported because it is the single filter that decides reach: it admits 189 of 737
    live records. Getting it wrong in the permissive direction ingests aggregator landing pages
    the user cannot apply from.
    """
    return (
        primary_acquisition in _DIRECT_APPLY_SOURCES
        or primary_acquisition.endswith(_DIRECT_APPLY_SUFFIX)
    )


def strip_header(text: str) -> str | None:
    """The JD body alone, or None when job-apps' header separator is absent.

    Fails CLOSED -- None, never the original text. A pass-through is what leaked `Template:`,
    `Fit: 40/100` and `Target: Yes (curated H-1B sponsor)` into a blind audit set and forced a
    re-judge. None is counted as `extracted_empty` at the call site, so a format change shows up
    as a body count that collapses rather than as verdicts entering the corpus.
    """
    index = text.find(_HEADER_MARKER)
    if index < 0:
        return None
    return text[index + len(_HEADER_MARKER) :].lstrip("\n")


def posting_identity(record: _Record) -> _Identity:
    """`(provider, slug, posting_ref)` for one record, preferring this repo's own dereference.

    A three-tier ladder, and the two upper tiers are worth their lines because they make a
    job-apps find CONVERGE with a board scan instead of sitting beside it under a parallel
    company row. Measured over the 189 usable records: 14 resolve as postings, 54 more resolve
    at board level, 121 reach the lane namespace.

    1. `parse_posting_target` -- a real provider, slug and posting reference. This is the same
       convergence `lanes/hiringcafe.py` seeks through `apply_url`.
    2. `parse_board_target` -- a recognised board whose URL carries no posting reference this
       repo can evidence. The company still converges; only the reference falls back.
    3. The lane namespace, keyed on the employer's name. Name-keyed undercounts slightly (two
       spellings of one employer become two unwatched rows), which is cosmetic: nothing
       downstream of the scan filters on `watched`, and posting identity is decided by
       `scan/apply.py` from name, title and URL rather than by this slug.

    `posting_id` is job-apps' own stable `pst_<hex>`, present on 737 of 737 records, and it is
    the fallback reference in tiers 2 and 3 rather than the URL: a reference has to be stable
    per posting, and a URL with a tracking query is not.
    """
    try:
        target = parse_posting_target(record.direct_url)
    except (UnknownBoardURL, UnresolvablePostingURL):
        pass
    else:
        return _Identity(target.provider, target.slug, target.posting_ref)
    try:
        provider, slug = parse_board_target(record.direct_url)
    except UnknownBoardURL:
        pass
    else:
        return _Identity(provider, slug, record.posting_id)
    return _Identity(LANE_PROVIDER, _name_slug(record.company), record.posting_id)


def _name_slug(company: str) -> str:
    """A stable slug from an employer's display name.

    Lower-cased and reduced to `[a-z0-9-]`, so the same employer reaches one row whatever the
    source's spacing and punctuation. Never blank: `upsert_lane_company` keys on
    `UNIQUE(provider, slug)`, and a blank would collapse every unnameable employer into one row.
    """
    kept = [character if character.isalnum() else "-" for character in company.strip().lower()]
    slug = "".join(kept).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "unnamed"


def _locations(location: str) -> list[str]:
    """`canonical.location` split into the segments the location gate reads.

    Split on `;` ONLY. The comma is a within-segment separator here -- "Remote, Canada" is one
    location, not two -- and splitting on it would hand `classify_location` the fragment
    "Canada" alongside "Remote" and lose which country the posting is actually in.
    """
    return [segment.strip() for segment in location.split(";") if segment.strip()]


def _raw_posting(identity: _Identity, record: _Record, *, body_text: str) -> RawPosting:
    """The posting, carrying job-apps' provenance and none of its judgement.

    `raw_json` holds the whitelist and NOT the whole record, which is the one place this lane
    must depart from `lanes/hiringcafe.py`'s `{"hit": hit}`: a job-apps record's unread fields
    are its dispositions and observations, so persisting the record verbatim would write
    job-apps' verdicts into this store even though nothing reads them today.

    `posted_at` stays None deliberately. `cohort_date` is the day job-apps DISCOVERED the
    posting, not the day it was posted, and the ranker is recency-dominated -- feeding a
    discovery date in as a posting date would let a re-ingested five-month-old record outrank a
    genuinely fresh one. `first_seen_at`, which the store sets itself, is the honest answer to
    when boardwatch became aware of this posting.
    """
    return RawPosting(
        provider_posting_id=identity.posting_ref,
        title=record.title,
        # The employer's own apply page -- what the user clicks, and in the tier-1 convergence
        # case the same URL the provider itself would have recorded.
        url=record.direct_url,
        locations=_locations(record.location),
        body_text=body_text,
        raw_json={
            "jobapps": {
                "posting_id": record.posting_id,
                "primary_acquisition": record.primary_acquisition,
                "cohort_date": record.cohort_date,
                "schema_version": SUPPORTED_SCHEMA_VERSION,
                "canonical": {
                    "company": record.company,
                    "title": record.title,
                    "direct_url": record.direct_url,
                    "location": record.location,
                },
            }
        },
    )


def _read_record(folder: Path) -> _Record | None:
    """One folder's record, or None when it is unreadable or not at the supported version."""
    try:
        payload: Any = json.loads((folder / _RECORD_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        return None
    canonical = payload.get("canonical")
    if not isinstance(canonical, dict):
        return None
    posting_id = str(payload.get("posting_id") or "").strip()
    company = str(canonical.get("company") or "").strip()
    title = str(canonical.get("title") or "").strip()
    direct_url = str(canonical.get("direct_url") or "").strip()
    if not (posting_id and company and title and direct_url):
        return None
    cohort = payload.get("cohort_date")
    return _Record(
        posting_id=posting_id,
        company=company,
        title=title,
        direct_url=direct_url,
        location=str(canonical.get("location") or "").strip(),
        primary_acquisition=str(payload.get("primary_acquisition") or "").strip(),
        cohort_date=str(cohort) if cohort else None,
        folder=folder,
    )


class JobAppsLane:
    """Reads job-apps' discovery tree from disk. Makes no requests."""

    name = LANE_NAME

    def __init__(self, source_dir: Path | None) -> None:
        self._source_dir = source_dir

    def collect(self, fetcher: Fetcher, admits: CompanyAdmission) -> LaneResult:
        """Every direct-apply record in the tree, grouped by the company identity it resolves to.

        `fetcher` is accepted and unused: the bodies are already on disk, and this lane opens no
        socket. Keeping the protocol's signature is what lets it register in `LANE_FACTORIES`
        beside the two network lanes with no change to the stage that drives them.

        `lane_posting_budget` is deliberately NOT charged. That knob is a ceiling on JD-body
        GETs, and there are none here -- charging it would throttle a free local read to 60 of
        189 records for no saving. Ingestion is still bounded where boundedness matters: the
        per-run NEW-company cap (`lane_new_companies_per_run`) admits new employers gradually,
        and the delivery cap bounds what reaches the operator.

        `search_pages` is empty, which is honest -- there is no search and nothing paginated.
        """
        del fetcher  # on disk; see the docstring
        records = self._records()
        tally = AcquisitionTally()

        grouped: dict[tuple[str, str], list[tuple[_Identity, _Record]]] = {}
        names: dict[tuple[str, str], str] = {}
        seen_posting_ids: set[str] = set()
        # Keyed on what the STORE keys on, which is not job-apps' id. `apply.py` snapshots
        # `existing` once before its loop and never re-reads it, so two postings carrying one
        # `provider_posting_id` both take the INSERT branch and the second violates
        # UNIQUE(company_id, provider_posting_id) -- inside `apply_board`'s single transaction,
        # which rolls the whole board back, escapes to the lane stage's handler, and discards
        # every later company AND the tally that would have explained it. An ATS enumerates a
        # board once and may assume distinct ids; an AGGREGATOR may not, and job-apps aggregates
        # aggregators, so two of its records (different `posting_id`, found through hiring.cafe
        # and simplify) can dereference to ONE posting through the same `direct_url`. That
        # convergence is the POINT of the identity ladder, which is exactly why it has to be
        # deduplicated here. Zero collisions in the live tree today -- the hazard is structural,
        # not hypothetical, and `lanes/hiringcafe.py` records the same one.
        seen_identities: set[tuple[str, str, str]] = set()
        for record in records:
            if not is_direct_apply(record.primary_acquisition):
                # Seen, and no acquisition attempted: the URL is an aggregator landing page with
                # no posting behind it. Counted, because a silent drop is indistinguishable from
                # a record the lane never saw.
                tally.record("not_attemptable")
                continue
            if record.posting_id in seen_posting_ids:
                # One duplicated `posting_id` exists in the live tree. Same bucket, same reason.
                tally.record("not_attemptable")
                continue
            seen_posting_ids.add(record.posting_id)
            identity = posting_identity(record)
            resolved = (identity.provider, identity.slug, identity.posting_ref)
            if resolved in seen_identities:
                # A second record resolving to a posting this run already took. Same bucket, and
                # dropping it is what keeps `apply_board` from aborting the stage.
                tally.record("not_attemptable")
                continue
            seen_identities.add(resolved)
            key = (identity.provider, identity.slug)
            grouped.setdefault(key, []).append((identity, record))
            # First spelling wins, matching `upsert_lane_company`, which touches nothing on
            # conflict: a later record cannot rename an employer already stored.
            names.setdefault(key, record.company)

        snapshots: list[LaneCompanySnapshot] = []
        for (provider, slug), entries in grouped.items():
            if not admits(provider, slug):
                # Asked exactly once per distinct identity, as the protocol requires. Nothing is
                # tallied for a refusal -- `admission.CompanyBudget.refused` names them.
                continue
            postings: list[RawPosting] = []
            for identity, record in entries:
                body = self._body(record)
                if body is None:
                    tally.record("extracted_empty")
                    continue
                tally.record("body_inline")
                postings.append(_raw_posting(identity, record, body_text=body))
            if postings:
                snapshots.append(
                    LaneCompanySnapshot(
                        provider=provider,
                        slug=slug,
                        name=names[(provider, slug)],
                        # The source is a directory, so the "URL" this company was found at is
                        # the tree itself. `board_scans` wants the place the claim came from,
                        # and inventing an http URL for a local read would name a request that
                        # was never made.
                        snapshot=lane_snapshot(postings, self._source_url()),
                    )
                )
        return LaneResult(snapshots=tuple(snapshots), tally=tally)

    def _records(self) -> list[_Record]:
        """Every readable record in the tree, or `JobAppsSourceError` if the tree is not there.

        Two levels deep and never recursive: `<queue>/<ATS>/<posting folder>/`. Recursing would
        reach `_skipped/<reason>/`, whose directory names are job-apps' verdicts.
        """
        root = self._source_dir
        if root is None:
            raise JobAppsSourceError(
                "no source directory configured; set `jobapps_discovery_dir` or take "
                f"{LANE_NAME!r} out of `lanes_enabled`"
            )
        if not root.is_dir():
            raise JobAppsSourceError(f"source directory is absent or not a directory: {root}")
        records: list[_Record] = []
        # Counted separately so the two structural causes do not share one message. "The queue
        # moved" and "job-apps bumped its record format" both end with zero usable records and
        # want completely different fixes; a single line reading "no readable record" is the
        # difference between a five-minute and a fifty-minute diagnosis on return.
        candidates = 0
        try:
            groups = sorted(entry for entry in root.iterdir() if entry.is_dir())
        except OSError as error:
            raise JobAppsSourceError(f"source directory is unreadable: {root}: {error}") from error
        for group in groups:
            if group.name in _SKIP_DIRS:
                continue
            try:
                folders = sorted(entry for entry in group.iterdir() if entry.is_dir())
            except OSError:
                continue
            for folder in folders:
                if not (folder / _RECORD_NAME).is_file():
                    continue
                candidates += 1
                record = _read_record(folder)
                if record is not None:
                    records.append(record)
        if not records:
            if candidates:
                raise JobAppsSourceError(
                    f"found {candidates} discovery record(s) under {root}, none readable at "
                    f"schema version {SUPPORTED_SCHEMA_VERSION} -- job-apps' record format has "
                    f"probably moved, so this lane needs updating rather than reconfiguring"
                )
            raise JobAppsSourceError(
                f"no discovery record anywhere under {root} -- the source directory is probably "
                f"not job-apps' queue, or the queue has moved"
            )
        return records

    def _body(self, record: _Record) -> str | None:
        try:
            text = (record.folder / _JD_NAME).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        body = strip_header(text)
        if body is None or not body.strip():
            return None
        return body

    def _source_url(self) -> str:
        return f"file://{self._source_dir}"
