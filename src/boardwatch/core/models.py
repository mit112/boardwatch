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

    @model_validator(mode="after")
    def _postings_empty_for_unchanged_and_failed(self) -> BoardSnapshot:
        if self.status in ("unchanged", "failed") and self.postings:
            raise ValueError(f"postings must be empty for status={self.status!r} (D15)")
        return self
