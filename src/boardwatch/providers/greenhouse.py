"""Greenhouse provider (§3.3, Appendix A; D25 capture-not-surface).

board_url includes content=true&pay_transparency=true in exactly that order —
the string is the http_cache key (D22), so the ordering is load-bearing.
The content field arrives HTML-escaped; it is unescaped once, then
html_to_text() produces body_text. pay_input_ranges is preserved inside
raw_json; salary_* scalars stay None for Greenhouse in v1 (D25).
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth


class GreenhouseProvider:
    name = "greenhouse"

    def board_url(self, slug: str) -> str:
        return (
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
            "?content=true&pay_transparency=true"
        )

    def _health_url(self, slug: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

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
            payload = json.loads(result.content)
            jobs = payload["jobs"]
            if not isinstance(jobs, list):
                raise TypeError("jobs is not a list")
        except (ValueError, KeyError, TypeError) as exc:
            return BoardSnapshot(
                status="failed", postings=[], url=request.url,
                observed_validators=None, error=f"invalid board payload: {exc}",
            )
        postings: list[RawPosting] = []
        errors: list[str] = []
        for job in jobs:
            try:
                postings.append(parse_job(job))
            except Exception as exc:  # per-posting isolation: positive evidence retained
                job_id = job.get("id", "?") if isinstance(job, dict) else "?"
                errors.append(f"job {job_id}: {exc}")
        if errors and not postings and jobs:
            status, error = "failed", f"all {len(jobs)} jobs failed to parse"
            postings = []
        elif errors:
            status = "partial"
            error = f"{len(errors)} of {len(jobs)} jobs failed to parse: " + "; ".join(errors[:3])
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
            result = fetcher.get(self._health_url(slug))
        except FetchFailure as exc:
            return BoardHealth.DEAD if exc.status_code == 404 else BoardHealth.ERROR
        try:
            jobs = json.loads(result.content)["jobs"]
        except (ValueError, KeyError, TypeError):
            return BoardHealth.ERROR
        return BoardHealth.OK if jobs else BoardHealth.EMPTY


def parse_job(job: dict[str, Any]) -> RawPosting:
    posting_id = str(job["id"])
    title = str(job["title"]).strip()
    if not title:
        raise ValueError("empty title")
    locations: list[str] = []
    location = job.get("location") or {}
    if isinstance(location, dict) and location.get("name"):
        locations.append(str(location["name"]))
    for office in job.get("offices") or []:
        name = office.get("name") if isinstance(office, dict) else None
        if name and str(name) not in locations:
            locations.append(str(name))
    departments = job.get("departments") or []
    department = (
        str(departments[0]["name"])
        if departments and isinstance(departments[0], dict) and departments[0].get("name")
        else None
    )
    content = str(job.get("content") or "")
    body_text = html_to_text(html.unescape(content))
    remote_policy: RemotePolicy = (
        "remote" if any("remote" in loc.casefold() for loc in locations) else "unknown"
    )
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=str(job.get("absolute_url") or ""),
        locations=locations,
        department=department,
        remote_policy=remote_policy,
        posted_at=_parse_dt(job.get("first_published")) or _parse_dt(job.get("created_at")),
        updated_at=_parse_dt(job.get("updated_at")),
        body_text=body_text,
        raw_json=job,
    )


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None
