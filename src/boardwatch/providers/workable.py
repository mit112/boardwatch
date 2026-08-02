"""Workable provider (live-verified 2026-08-01).

apply.workable.com/api/v1/widget/accounts/{slug}?details=true returns the whole
board in ONE request; ?details=true is what inlines each job's `description`
(HTML — html_to_text() IS on this path). Workable sends NO ETag and NO
Last-Modified, so a 304 is never possible and every scan refetches the board;
this is acceptable because a board is a single request.

Two URL shapes share apply.workable.com: /{org}/j/{shortcode} (org first) and the
bare shortlink /j/{shortcode} (no org). slug_from_path rejects the latter — it
302s to the org form, but board-URL parsing is pure string work with no network.
`slug_help` supplies the canonical-form message board_urls raises for a shortlink,
as a plain string so this module never imports board_urls (which would cycle).
jobs.workable.com is deliberately NOT a board host: /view/{id}/... carries no org
segment at all, so it could only ever yield a bad slug.

Identity is `shortcode`, never `id`. There is no update timestamp on any job, so
updated_at is always None. published_on is DATE-ONLY and becomes UTC midnight.
Salary is never mined (D19).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure


class WorkableProvider:
    name = "workable"
    board_hosts: tuple[str, ...] = ("apply.workable.com",)
    slug_help = (
        "Workable shortlinks (apply.workable.com/j/{code}) omit the org; paste "
        "apply.workable.com/{org}/j/{code} or use workable:{org}."
    )

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        """None for the bare shortlink form (/j/{shortcode}), which carries no org."""
        if parts[0] == "j":
            return None
        return parts[0]

    def board_url(self, slug: str) -> str:
        return f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"

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
            if not isinstance(payload, dict):
                raise TypeError("Workable payload is not an object")
            jobs = payload["jobs"]
            if not isinstance(jobs, list):
                raise TypeError("Workable 'jobs' is not a list")
        except (ValueError, KeyError, TypeError) as exc:
            return BoardSnapshot(
                status="failed", postings=[], url=request.url,
                observed_validators=None, error=f"invalid board payload: {exc}",
            )
        postings: list[RawPosting] = []
        errors: list[str] = []
        for job in jobs:
            if not isinstance(job, dict):
                errors.append("job entry is not an object")
                continue
            try:
                postings.append(parse_job(job))
            except Exception as exc:  # per-posting isolation
                errors.append(f"job {job.get('shortcode', '?')}: {exc}")
        if errors and not postings and jobs:
            return BoardSnapshot(
                status="failed", postings=[], url=request.url,
                observed_validators=None, error=f"all {len(jobs)} jobs failed to parse",
            )
        if errors:
            status, error = "partial", (
                f"{len(errors)} of {len(jobs)} jobs failed to parse: " + "; ".join(errors[:3])
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
            return health_from_failure(exc)
        try:
            payload = json.loads(result.content)
            jobs = payload["jobs"]
            if not isinstance(jobs, list):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            return BoardHealth.ERROR
        return BoardHealth.OK if jobs else BoardHealth.EMPTY


def parse_job(job: dict[str, Any]) -> RawPosting:
    posting_id = str(job["shortcode"])
    title = str(job["title"]).strip()
    if not title:
        raise ValueError("empty title")
    department_raw = job.get("department")
    department = str(department_raw) if department_raw else None
    remote_policy: RemotePolicy = "remote" if job.get("telecommuting") else "unknown"
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=str(job.get("url") or job.get("shortlink") or ""),
        locations=_locations(job),
        department=department,
        remote_policy=remote_policy,
        posted_at=_date_only_to_naive_utc(job.get("published_on")),
        updated_at=None,  # Workable exposes no update timestamp
        body_text=html_to_text(str(job.get("description") or "")),
        raw_json=job,
    )


def _locations(job: dict[str, Any]) -> list[str]:
    """Structured `locations` first (inner key is `region`, NOT `state`), then the
    flat top-level city/state/country fallback. De-duped, order preserved."""
    out: list[str] = []
    entries = job.get("locations")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            parts = [entry.get("city"), entry.get("region"), entry.get("country")]
            label = ", ".join(str(p) for p in parts if p)
            if label and label not in out:
                out.append(label)
    if not out:
        parts = [job.get("city"), job.get("state"), job.get("country")]
        label = ", ".join(str(p) for p in parts if p)
        if label:
            out.append(label)
    return out


def _date_only_to_naive_utc(value: Any) -> datetime | None:
    """published_on is date-only ("2026-03-30"); interpret as UTC midnight."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
    return to_naive_utc(parsed)
