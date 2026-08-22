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
    # Distinct posting ids we LISTED this run, before the detail budget truncated anything.
    board_enumerated: int | None = None
    # Listed but not materialised because detail_fetch_budget was exceeded. Typed here so the
    # number stops living only as English inside board_scans.error.
    detail_deferred: int | None = None
    # True when the provider's stated total was a censor value and board_reported_total came
    # from a second, uncapped path. A TYPED flag: never re-derive this by parsing a message.
    board_total_censored: bool | None = None

    @model_validator(mode="after")
    def _postings_empty_for_unchanged_and_failed(self) -> BoardSnapshot:
        if self.status in ("unchanged", "failed") and self.postings:
            raise ValueError(f"postings must be empty for status={self.status!r} (D15)")
        return self
