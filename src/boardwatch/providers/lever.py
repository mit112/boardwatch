"""Lever provider (§3.3, Appendix A live-verified 2026-06-10).

api.lever.co/v0/postings/{slug}?mode=json returns a JSON ARRAY of postings
(not an object). Bodies are plain text in descriptionPlain/additionalPlain —
html_to_text() is NOT on this path. createdAt is epoch MILLISECONDS. Salary
text may appear in additionalPlain and is NEVER mined (D19): Lever writes no
salary_* columns. Dead board = 404 {"ok":false,"error":"Document not found"};
empty-but-live = 200 [].
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure


class LeverProvider:
    name = "lever"

    def board_url(self, slug: str) -> str:
        return f"https://api.lever.co/v0/postings/{slug}?mode=json"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            result = fetcher.get(request.url, validators=request.validators)
        except FetchFailure as exc:
            return BoardSnapshot(
                status="failed", postings=[], url=request.url,
                observed_validators=None, error=str(exc),
            )
        if result.not_modified:
            return BoardSnapshot(
                status="unchanged", postings=[], url=request.url,
                observed_validators=None, error=None,
            )
        try:
            raw_postings = json.loads(result.content)
            if not isinstance(raw_postings, list):
                raise TypeError("Lever board payload is not a JSON array")
        except (ValueError, TypeError) as exc:
            return BoardSnapshot(
                status="failed", postings=[], url=request.url,
                observed_validators=None, error=f"invalid board payload: {exc}",
            )
        postings: list[RawPosting] = []
        errors: list[str] = []
        for raw in raw_postings:
            try:
                postings.append(parse_posting(raw))
            except Exception as exc:  # per-posting isolation: positive evidence retained
                pid = raw.get("id", "?") if isinstance(raw, dict) else "?"
                errors.append(f"posting {pid}: {exc}")
        if errors and not postings and raw_postings:
            status, error = "failed", f"all {len(raw_postings)} postings failed to parse"
        elif errors:
            status = "partial"
            error = (
                f"{len(errors)} of {len(raw_postings)} postings failed to parse: "
                + "; ".join(errors[:3])
            )
        else:
            status, error = "complete", None
        return BoardSnapshot(
            status=status,
            postings=postings,
            url=request.url,
            observed_validators=result.observed_validators,
            error=error,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        try:
            result = fetcher.get(self.board_url(slug))
        except FetchFailure as exc:
            return health_from_failure(exc)  # transport -> UNREACHABLE, 404 -> DEAD, else ERROR
        try:
            postings = json.loads(result.content)
            if not isinstance(postings, list):
                raise TypeError
        except (ValueError, TypeError):
            return BoardHealth.ERROR
        return BoardHealth.OK if postings else BoardHealth.EMPTY


def parse_posting(raw: dict[str, Any]) -> RawPosting:
    posting_id = str(raw["id"])
    title = str(raw["text"]).strip()
    if not title:
        raise ValueError("empty title")
    categories = raw.get("categories") or {}
    all_locations = categories.get("allLocations")
    if isinstance(all_locations, list) and all_locations:
        locations = [str(loc) for loc in all_locations if loc]
    elif categories.get("location"):
        locations = [str(categories["location"])]
    else:
        locations = []
    team = categories.get("team")
    department = str(team) if team else None
    body_text = "\n\n".join(
        part for part in (raw.get("descriptionPlain"), raw.get("additionalPlain")) if part
    )
    remote_policy: RemotePolicy = (
        "remote" if any("remote" in loc.casefold() for loc in locations) else "unknown"
    )
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=str(raw.get("hostedUrl") or ""),
        locations=locations,
        department=department,
        remote_policy=remote_policy,
        posted_at=_epoch_ms_to_naive_utc(raw.get("createdAt")),
        updated_at=_epoch_ms_to_naive_utc(raw.get("updatedAt")),
        body_text=body_text,
        raw_json=raw,
    )


def _epoch_ms_to_naive_utc(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)):
        return None
    return to_naive_utc(datetime.fromtimestamp(value / 1000, tz=UTC))
