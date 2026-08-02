"""SmartRecruiters provider (live-verified 2026-08-01).

The FIRST multi-endpoint provider. api.smartrecruiters.com/v1/companies/{slug}/postings
returns metadata ONLY — no descriptions — so each posting needs a second request to
/postings/{id} for jobAd.sections. `limit` clamps server-side to 100; pagination is
offset/limit/totalFound.

Four properties drive this design:

1. DEAD IS UNREACHABLE. An unknown org returns 200 with totalFound:0, byte-identical
   to a real empty board; the public careers host also 200s for garbage. A typo is
   therefore indistinguishable from an empty board, and healthcheck can only ever
   return OK/EMPTY/ERROR/UNREACHABLE. `companies add` warns about this explicitly.
2. DETAIL FETCHES ARE BOUNDED AND SKIPPED. Per-host pacing defaults to 1s and every
   SmartRecruiters board shares one host lock, so we fetch details only for postings
   NOT in request.known_posting_ids, capped by request.detail_budget. Consequence:
   bodies are fetched once and never refreshed. That loses nothing real — the list
   ETag cannot detect description-only edits anyway, because the list carries none.
3. SUBSET DETAILS, FULL INVENTORY. Because we skip known postings, snapshot.postings
   is only the newly-fetched subset. snapshot.listed_ids carries the FULL live board
   (every listed id minus any a detail confirmed inactive) so apply_board does not
   treat known postings as missing and close them (see scan/apply.py _process_missing).
4. SLUGS ARE CASE-INSENSITIVE. normalize_slug lowercases (applied to BOTH the
   provider:slug and pasted-URL forms in core.board_urls) so `Visa` and `visa`
   cannot become two companies rows watching one board under UNIQUE(provider, slug).
   The host serves ONE URL shape, so no slug_from_path is needed.

companyDescription is deliberately EXCLUDED from body_text: it is identical boilerplate
across a company's whole board and would pollute content_hash (revision detection).
Empty sections yield an empty body_text — observed on live active postings, not an error.
`fetch_board` must never raise: every JSON level is validated as dict/list before use.
Salary is never mined (D19).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, RemotePolicy
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.providers.base import BoardHealth, health_from_failure

_PAGE_LIMIT = 100  # server-side maximum; a larger request is silently clamped
_BODY_SECTIONS = ("jobDescription", "qualifications", "additionalInformation")


def _failed(url: str, error: str) -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=url, observed_validators=None, error=error,
    )


def _json_object(content: bytes) -> dict[str, Any] | None:
    """Parsed JSON iff it is an object, else None. Never raises."""
    try:
        obj = json.loads(content)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


class SmartRecruitersProvider:
    name = "smartrecruiters"
    board_hosts: tuple[str, ...] = ("jobs.smartrecruiters.com",)

    @staticmethod
    def normalize_slug(slug: str) -> str:
        return slug.lower()

    def board_url(self, slug: str) -> str:
        return (
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            f"?limit={_PAGE_LIMIT}&offset=0"
        )

    def _page_url(self, slug: str, offset: int) -> str:
        return (
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            f"?limit={_PAGE_LIMIT}&offset={offset}"
        )

    def _detail_url(self, slug: str, posting_id: str) -> str:
        return f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        try:
            result = fetcher.get(request.url, validators=request.validators)
        except FetchFailure as exc:
            return _failed(request.url, str(exc))
        if result.not_modified:
            return BoardSnapshot(
                status="unchanged", postings=[], url=request.url,
                observed_validators=None, error=None,
            )

        payload = _json_object(result.content)
        if payload is None or not isinstance(payload.get("content"), list):
            return _failed(request.url, "invalid board payload: missing 'content' list")
        try:
            total = int(payload["totalFound"])
        except (KeyError, TypeError, ValueError):
            return _failed(request.url, "invalid board payload: missing 'totalFound'")
        listed: list[dict[str, Any]] = [e for e in payload["content"] if isinstance(e, dict)]

        errors: list[str] = []
        offset = _PAGE_LIMIT
        while len(listed) < total and offset < total:
            try:
                page = fetcher.get(self._page_url(request.slug, offset))
            except FetchFailure as exc:
                errors.append(f"page at offset {offset}: {exc}")
                break
            page_obj = _json_object(page.content)
            if page_obj is None or not isinstance(page_obj.get("content"), list):
                errors.append(f"page at offset {offset}: invalid payload")
                break
            listed.extend(e for e in page_obj["content"] if isinstance(e, dict))
            offset += _PAGE_LIMIT

        listed_ids = {str(e["id"]) for e in listed if e.get("id") is not None}

        budget = request.detail_budget
        unseen = [e for e in listed if str(e.get("id")) not in request.known_posting_ids]
        if len(unseen) > budget:
            errors.append(
                f"detail budget of {budget} exceeded ({len(unseen)} unseen postings); "
                "raise detail_fetch_budget or rescan"
            )
            unseen = unseen[:budget]

        postings: list[RawPosting] = []
        detail_failures = 0
        inactive_ids: set[str] = set()
        for entry in unseen:
            posting_id = str(entry.get("id"))
            try:
                detail_res = fetcher.get(self._detail_url(request.slug, posting_id))
            except FetchFailure as exc:
                detail_failures += 1
                errors.append(f"posting {posting_id} detail: {exc}")
                continue
            detail = _json_object(detail_res.content)
            if detail is None:
                detail_failures += 1
                errors.append(f"posting {posting_id} detail: malformed payload")
                continue
            if detail.get("active") is False:
                inactive_ids.add(posting_id)
                continue
            try:
                postings.append(parse_posting(entry, detail))
            except Exception as exc:  # per-posting isolation
                errors.append(f"posting {posting_id}: {exc}")

        if unseen and detail_failures == len(unseen):
            return _failed(request.url, f"all {len(unseen)} detail fetches failed")

        # The live inventory for _process_missing (C1): every listed id minus those a
        # detail confirmed inactive. Known/skipped ids stay in it so they are not closed.
        board_ids = frozenset(listed_ids - inactive_ids)
        if errors:
            status, error = "partial", f"{len(errors)} issue(s): " + "; ".join(errors[:3])
        else:
            status, error = "complete", None
        return BoardSnapshot(
            status=status,
            postings=postings,
            url=request.url,
            observed_validators=result.observed_validators,
            error=error,
            listed_ids=board_ids,
        )

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth:
        """NOTE: DEAD is unreachable here — an unknown org returns 200/totalFound:0."""
        try:
            result = fetcher.get(self.board_url(slug))
        except FetchFailure as exc:
            return health_from_failure(exc)
        payload = _json_object(result.content)
        if payload is None or not isinstance(payload.get("content"), list):
            return BoardHealth.ERROR
        return BoardHealth.OK if payload["content"] else BoardHealth.EMPTY


def parse_posting(listed: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    posting_id = str(listed["id"])
    title = str(listed.get("name") or detail.get("name") or "").strip()
    if not title:
        raise ValueError("empty title")
    location = detail.get("location") or listed.get("location") or {}
    department = (listed.get("department") or {}).get("label")
    identifier = str((listed.get("company") or {}).get("identifier") or "")
    url = str(
        detail.get("postingUrl")
        or f"https://jobs.smartrecruiters.com/{identifier}/{posting_id}"
    )
    return RawPosting(
        provider_posting_id=posting_id,
        title=title,
        url=url,
        locations=_locations(location),
        department=str(department) if department else None,
        remote_policy=_remote_policy(location),
        posted_at=_iso_to_naive_utc(listed.get("releasedDate") or detail.get("releasedDate")),
        updated_at=None,  # no update field observed on either endpoint
        body_text=_body_text(detail),
        raw_json={"listed": listed, "detail": detail},
    )


def _body_text(detail: dict[str, Any]) -> str:
    """jobDescription + qualifications + additionalInformation, in that fixed order.
    companyDescription is EXCLUDED (boilerplate; would pollute content_hash)."""
    sections = (detail.get("jobAd") or {}).get("sections") or {}
    parts: list[str] = []
    for key in _BODY_SECTIONS:
        text = str((sections.get(key) or {}).get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _locations(location: dict[str, Any]) -> list[str]:
    full = location.get("fullLocation")
    if full:
        return [str(full)]
    parts = [location.get("city"), location.get("region"), location.get("country")]
    label = ", ".join(str(p) for p in parts if p)
    return [label] if label else []


def _remote_policy(location: dict[str, Any]) -> RemotePolicy:
    """SmartRecruiters exposes remote and hybrid as separate booleans."""
    if location.get("remote"):
        return "remote"
    if location.get("hybrid"):
        return "hybrid"
    return "unknown"


def _iso_to_naive_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None
