"""Boundary models (§3.3, D22). Pydantic v2 frozen models — §6.1 'Pydantic at boundaries'.

ResponseValidators carries response *metadata only*, never bodies (D15).
BoardRequest.url is the exact, canonical http_cache key: query params included,
stable ordering — byte-equality is the cache contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

SnapshotStatus = Literal["complete", "partial", "failed", "unchanged"]
RemotePolicy = Literal["remote", "hybrid", "onsite", "unknown"]


class ResponseValidators(BaseModel):
    model_config = ConfigDict(frozen=True)

    etag: str | None = None
    last_modified: str | None = None


class BoardRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    slug: str
    url: str  # canonical fetch URL == the http_cache key (D22)
    validators: ResponseValidators | None = None
    # provider_posting_ids already stored for this company. Multi-endpoint providers
    # (SmartRecruiters) use this to skip detail fetches for postings already seen.
    # NOT part of the cache key — it never affects `url`.
    known_posting_ids: frozenset[str] = frozenset()
    # Max secondary (per-posting) requests a multi-endpoint provider may make for this
    # board in this scan. Single-request providers ignore it. Also not part of the key.
    detail_budget: int = 50


# The structured fields an observation can declare it is NOT the record of truth for (D-414(a)).
#
# MECHANISM CHOSEN: the observation declares them, and `scan.apply._refreshed_fields` drops
# exactly those columns from the UPDATE. The alternative considered and REJECTED was a precedence
# rule keyed on observation ORIGIN — rank a lane below a provider scan and refuse the lower-ranked
# write. Three reasons, the first decisive:
#
#   1. Fidelity varies WITHIN one lane's single `collect()`. The Indeed lane files a hit under a
#      real provider's `(company_id, provider_posting_id)` when the employer's apply URL
#      dereferences (tier 1) and under its own key when it does not (tier 2). For a tier-2 row
#      that lane is the only observer there will ever be and must keep refreshing every field;
#      for a tier-1 row it is reading someone else's posting through an aggregator's index. A
#      rank attached to the lane cannot tell those apart, so it would either freeze tier-2 rows
#      nothing else will ever refresh or keep clobbering tier-1 rows. hiring.cafe makes the same
#      point from the other side: it re-fetches the employer's own board and hands on the
#      PROVIDER's `RawPosting` verbatim, so ranking it below a board scan would demote data that
#      is not secondhand at all.
#   2. Precedence has to know what wrote the row LAST, and no column carries that. It needs a
#      migration plus a backfill, and every pre-existing row starts at an unknown origin — which
#      must fail open to avoid freezing the corpus, reproducing the defect for exactly the rows
#      that already have it.
#   3. It puts the knowledge in the writer rather than at the construction site. `apply_board`
#      would have to classify by lane name, and a name is a string nobody can typecheck — the
#      thing this repo refuses everywhere else.
#
# Named for `RawPosting`'s OWN fields, never for the columns they land in: an observation knows
# what it saw, not what `scan.apply` writes. `title` therefore carries `normalized_title` with it
# and `salary` carries all four salary columns, so a declaration can never half-refuse a derived
# column and leave a row internally inconsistent.
SecondhandField = Literal[
    "title",
    "url",
    "locations",
    "remote_policy",
    "department",
    "posted_at",
    "updated_at",
    "salary",
    "raw_json",
]


class RawPosting(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_posting_id: str
    title: str
    url: str
    locations: list[str]
    department: str | None = None
    remote_policy: RemotePolicy = "unknown"
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    body_text: str
    raw_json: dict[str, Any]
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    # Structured fields this observation is not the record of truth for (see `SecondhandField`).
    # EMPTY by default, and that default is what keeps every provider scan byte-identical: a
    # provider reads the employer's own board, so a `None` it reports is an OBSERVED absence, not
    # a gap in what it looked at.
    secondhand: frozenset[SecondhandField] = frozenset()


class BoardSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: SnapshotStatus
    postings: list[RawPosting]
    url: str  # echoed from the request (cache key)
    observed_validators: ResponseValidators | None = None
    error: str | None = None
    # The FULL live board inventory when a provider fetched only a subset of details
    # (SmartRecruiters skips known postings). _process_missing prefers this; single-
    # request providers leave it empty and it falls back to the applied postings.
    listed_ids: frozenset[str] = frozenset()
    # Coverage instrument (D-271). None means the board stated no total — NEVER backfill
    # with len(postings); an unfailable ratio is worse than no ratio.
    board_reported_total: int | None = None
    # DISTINCT posting ids the board listed this run — counted off the raw rows, BEFORE the
    # detail budget truncated anything and BEFORE any per-row parse failure dropped one, with
    # id-less rows excluded. All six providers mean exactly this (`providers/base.py`'s
    # count_listed_ids for the four single-request ones, `len(listed_ids)` for SmartRecruiters
    # and Workday); the column is persisted, so a provider meaning something else by it writes
    # a row that can never be corrected. `board_reported_total - board_enumerated` is therefore
    # a LISTING shortfall, never a parse-failure count.
    board_enumerated: int | None = None
    # Listed but not materialised because detail_fetch_budget was exceeded. Typed here so the
    # number stops living only as English inside board_scans.error.
    detail_deferred: int | None = None
    # True when the provider's stated total was a censor value and board_reported_total came
    # from a second, uncapped path. A TYPED flag: never re-derive this by parsing a message.
    board_total_censored: bool | None = None
    # Wall-clock seconds the FETCH took, measured at the one seam every board passes through
    # (`scan/workers.fetch_board_job`). `None` means NOT TIMED, never zero: a lane builds its
    # own snapshots and never goes through that seam, and a run that reports 0.0 for an
    # untimed board would understate the only cost that matters. `board_scans.started_at`
    # cannot answer this — `apply_board` is handed an already-fetched snapshot and stamps
    # `started_at` at the top of the APPLY, so those timestamps sum to seconds across a
    # ~57-minute run and time the DB write alone.
    fetch_seconds: float | None = None

    @model_validator(mode="after")
    def _postings_empty_for_unchanged_and_failed(self) -> BoardSnapshot:
        if self.status in ("unchanged", "failed") and self.postings:
            raise ValueError(f"postings must be empty for status={self.status!r} (D15)")
        return self
