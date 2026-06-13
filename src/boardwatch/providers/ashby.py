"""Ashby provider (§3.3, Appendix A). The only v1 writer of salary_* scalars
(D19/D25: structured provider fields only, display-only).

api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true returns
{"jobs": [...]} with descriptionHtml (→ html_to_text, the Greenhouse path) and
structured compensation. Responses reach Ramp-scale 1.7 MB; D26 permits an
ordinary single-pass parse, gated by a subprocess tracemalloc ≤ 64 MiB ceiling.

Compensation contract (round 1 finding 5): salary_* scalars are written iff a
posting carries exactly ONE compensation range in a single currency with a
recognized interval; the interval normalizes to {year|month|week|day|hour};
a one-sided range maps the present side; multiple ranges/tiers, non-monetary
components, or unrecognized intervals leave ALL scalars NULL, raw_json intact.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.html_text import html_to_text
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure

_INTERVALS = {
    "1 YEAR": "year",
    "1 MONTH": "month",
    "1 WEEK": "week",
    "1 DAY": "day",
    "1 HOUR": "hour",
}


class AshbyProvider:
    name = "ashby"

    def board_url(self, slug: str) -> str:
        return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"

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
        snapshot = self.parse_payload(result.content, url=request.url)
        return snapshot.model_copy(update={"observed_validators": result.observed_validators})

    def parse_payload(self, content: bytes, *, url: str) -> BoardSnapshot:
        """The complete decode → BoardSnapshot path (shared by fetch_board and the
        D26 huge-board subprocess probe; observed_validators is set by the caller)."""
        try:
            payload = json.loads(content)
            jobs = payload["jobs"]
            if not isinstance(jobs, list):
                raise TypeError("jobs is not a list")
        except (ValueError, KeyError, TypeError) as exc:
            return BoardSnapshot(
                status="failed", postings=[], url=url,
                observed_validators=None, error=f"invalid board payload: {exc}",
            )
        postings: list[RawPosting] = []
        errors: list[str] = []
        for job in jobs:
            try:
                postings.append(parse_job(job))
            except Exception as exc:  # per-posting isolation
                job_id = job.get("id", "?") if isinstance(job, dict) else "?"
                errors.append(f"job {job_id}: {exc}")
        if errors and not postings and jobs:
            status, error = "failed", f"all {len(jobs)} jobs failed to parse"
        elif errors:
            status = "partial"
            error = f"{len(errors)} of {len(jobs)} jobs failed to parse: " + "; ".join(errors[:3])
        else:
            status, error = "complete", None
        return BoardSnapshot(
            status=status,
            postings=postings, url=url, observed_validators=None, error=error,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        try:
            result = fetcher.get(self.board_url(slug))
        except FetchFailure as exc:
            return health_from_failure(exc)
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
    if job.get("location"):
        locations.append(str(job["location"]))
    for sec in job.get("secondaryLocations") or []:
        name = sec.get("location") if isinstance(sec, dict) else None
        if name and str(name) not in locations:
            locations.append(str(name))
    department = str(job["department"]) if job.get("department") else None
    body_text = html_to_text(str(job.get("descriptionHtml") or ""))
    is_remote = job.get("isRemote") is True  # structured boolean, not text mining (deviation 4)
    remote_policy: RemotePolicy = (
        "remote"
        if is_remote or any("remote" in loc.casefold() for loc in locations)
        else "unknown"
    )
    salary = _map_compensation(job.get("compensation"))
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=str(job.get("jobUrl") or ""),
        locations=locations,
        department=department,
        remote_policy=remote_policy,
        posted_at=_parse_dt(job.get("publishedAt")),
        updated_at=None,
        body_text=body_text,
        raw_json=job,
        **salary,
    )


def _map_compensation(comp: Any) -> dict[str, Any]:
    # Contract: scalars written IFF the posting carries EXACTLY ONE compensation range
    # in a single currency with a recognized interval. Field names are deviation-5-pinned
    # (compensationTiers[].components[].{compensationType, interval, currencyCode,
    # minValue, maxValue}) — no unpinned aliases. A salary range accompanied by ANY other
    # component (equity, bonus, …) is NOT "exactly one range" → all scalars NULL.
    null = {"salary_min": None, "salary_max": None, "salary_currency": None, "salary_period": None}
    if not isinstance(comp, dict):
        return null
    tiers = comp.get("compensationTiers") or []
    if len(tiers) != 1 or not isinstance(tiers[0], dict):
        return null  # multiple tiers (or none) → NULL
    components = tiers[0].get("components") or []
    if len(components) != 1 or not isinstance(components[0], dict):
        return null  # zero, or salary-plus-non-monetary, or multiple ranges → NULL
    component = components[0]
    if str(component.get("compensationType", "")).lower() != "salary":
        return null  # the sole component is non-monetary → NULL
    period = _INTERVALS.get(str(component.get("interval", "")).upper())
    currency = component.get("currencyCode")
    if period is None or not currency:
        return null  # unrecognized interval or missing currency → NULL
    min_value = component.get("minValue")
    max_value = component.get("maxValue")
    if min_value is None and max_value is None:
        return null
    return {
        "salary_min": float(min_value) if min_value is not None else None,
        "salary_max": float(max_value) if max_value is not None else None,
        "salary_currency": str(currency),
        "salary_period": period,
    }


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None
