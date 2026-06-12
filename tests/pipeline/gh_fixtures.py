"""Snapshot builders over the recorded Greenhouse fixture corpus.

State tests run on fixture-derived inventories (issue #7 acceptance);
controlled mutations (changed bodies, dropped jobs, new ids) are made on
deep copies of real recorded jobs.
"""

from __future__ import annotations

import copy
import html
import json
from pathlib import Path
from typing import Any

from boardwatch.core.models import BoardSnapshot, ResponseValidators
from boardwatch.providers.greenhouse import GreenhouseProvider, parse_job

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "greenhouse"
BOARD_URL = GreenhouseProvider().board_url("acme")


def gh_jobs() -> list[dict[str, Any]]:
    payload = json.loads((FIXTURES / "normal.json").read_text(encoding="utf-8"))
    return copy.deepcopy(list(payload["jobs"]))


def set_body(job: dict[str, Any], html_body: str) -> dict[str, Any]:
    job["content"] = html.escape(html_body)  # Greenhouse ships escaped HTML
    return job


def clone_with_id(job: dict[str, Any], new_id: int) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone["id"] = new_id
    return clone


def snapshot_for(
    jobs: list[dict[str, Any]],
    status: str = "complete",
    validators: ResponseValidators | None = None,
    error: str | None = None,
) -> BoardSnapshot:
    return BoardSnapshot(
        status=status,  # type: ignore[arg-type]
        postings=[parse_job(job) for job in jobs],
        url=BOARD_URL,
        observed_validators=validators,
        error=error,
    )


def failed_snapshot(error: str = "HTTP 503 after retries") -> BoardSnapshot:
    return BoardSnapshot(
        status="failed", postings=[], url=BOARD_URL, observed_validators=None, error=error
    )


def unchanged_snapshot() -> BoardSnapshot:
    return BoardSnapshot(
        status="unchanged", postings=[], url=BOARD_URL, observed_validators=None, error=None
    )
