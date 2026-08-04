"""Per-provider state-suite harness (issue #18). Each ProviderCase wraps a
provider's recorded fixtures and its REAL parser; mutations (g = body field,
m = metadata field, h = crash injection) are made in the provider-shaped body
and flow respx -> provider parser -> coordinator/apply, never from hand-built
RawPostings (round 1 finding 4; mutation map per round 2 finding 2 — content_hash
is body-only, D25)."""

from __future__ import annotations

import copy
import html
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boardwatch.core.models import BoardSnapshot, RawPosting, ResponseValidators
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.ashby import parse_job as ashby_parse
from boardwatch.providers.base import Provider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.greenhouse import parse_job as gh_parse
from boardwatch.providers.lever import LeverProvider
from boardwatch.providers.lever import parse_posting as lever_parse
from boardwatch.providers.workable import WorkableProvider
from boardwatch.providers.workable import parse_job as workable_parse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# SmartRecruiters and Workday are DELIBERATELY excluded from ALL_CASES. This harness models a
# single-payload board (one mocked URL, a one-argument parser). SmartRecruiters is
# multi-endpoint (paginated list + one detail fetch per unseen posting, a two-argument
# parse_posting(listed, detail)) and its apply-layer behavior depends on
# BoardSnapshot.listed_ids. Workday is all of that AND a POST whose pages share one URL and
# differ only in the request body, so `respx` cannot key its pages by URL at all. They are
# covered by tests/contract/test_smartrecruiters.py and tests/contract/test_workday.py
# (every fetch branch) and tests/pipeline/test_apply_listed_ids.py (the inventory path).


@dataclass
class ProviderCase:
    name: str
    provider: Provider
    parse: Callable[[dict[str, Any]], RawPosting]
    envelope: str  # "array" (Lever) | "jobs" (Greenhouse, Ashby, Workable)
    title_key: str
    slug: str = "acme"
    id_key: str = "id"

    # ---- response shaping ----
    def board_url(self) -> str:
        return self.provider.board_url(self.slug)

    def jobs(self) -> list[dict[str, Any]]:
        raw = json.loads((FIXTURES / self.name / "normal.json").read_text(encoding="utf-8"))
        payload = raw if self.envelope == "array" else raw["jobs"]
        return copy.deepcopy(list(payload))

    def wrap(self, jobs: list[dict[str, Any]]) -> bytes:
        body: Any = jobs if self.envelope == "array" else {"jobs": jobs}
        return json.dumps(body).encode()

    def empty_body(self) -> bytes:
        return self.wrap([])

    # ---- mutations (the g/h/m contract) ----
    def set_body(self, job: dict[str, Any], text: str) -> dict[str, Any]:
        if self.name == "greenhouse":
            job["content"] = html.escape(f"<p>{text}</p>")  # Greenhouse ships escaped HTML
        elif self.name == "lever":
            job["descriptionPlain"] = text  # plain text, no HTML path
            job["additionalPlain"] = ""
        elif self.name == "workable":
            job["description"] = f"<p>{text}</p>"  # HTML — html_to_text yields text
        else:  # ashby
            job["descriptionHtml"] = f"<p>{text}</p>"
        return job

    def set_title(self, job: dict[str, Any], suffix: str) -> dict[str, Any]:
        job[self.title_key] = str(job[self.title_key]) + suffix
        return job

    def set_metadata(self, job: dict[str, Any], variant: int = 1) -> dict[str, Any]:
        # a metadata-only change (round 2 finding 2: NOT a body change -> no `revised`).
        # `variant` makes V1/V2 metadata DISTINCT so a refresh is observable. Does NOT touch
        # the title (use set_title), so callers control title and metadata separately.
        if self.name == "greenhouse":
            job["pay_input_ranges"] = [{"min_cents": 100 * variant, "max_cents": 200 * variant}]
        elif self.name == "lever":
            job.setdefault("categories", {})["team"] = f"Platform Engineering {variant}"
        elif self.name == "workable":
            job["department"] = f"Engineering {variant}"
        else:  # ashby — structured comp is metadata (empty components -> salary_* NULL,
            # no body-hash change); a marker field makes the variant observable in raw_json
            job["compensation"] = {"compensationTiers": [{"components": []}], "marker": variant}
        return job

    def metadata_value(self, raw_json: dict[str, Any]) -> Any:
        # the provider-specific metadata field set by set_metadata — for the "refreshed" assertion
        if self.name == "greenhouse":
            return raw_json["pay_input_ranges"]
        if self.name == "lever":
            return raw_json["categories"]["team"]
        if self.name == "workable":
            return raw_json["department"]
        return raw_json["compensation"]["marker"]

    def clone_with_id(self, job: dict[str, Any], new_id: int) -> dict[str, Any]:
        clone = copy.deepcopy(job)
        clone[self.id_key] = new_id
        return clone

    # ---- apply-level snapshot (used by a/b/c/e/f/l) ----
    def snapshot_for(
        self,
        jobs: list[dict[str, Any]],
        status: str = "complete",
        validators: ResponseValidators | None = None,
        error: str | None = None,
    ) -> BoardSnapshot:
        return BoardSnapshot(
            status=status,  # type: ignore[arg-type]
            postings=[self.parse(job) for job in jobs],
            url=self.board_url(),
            observed_validators=validators,
            error=error,
        )

    def failed_snapshot(self, error: str = "HTTP 503 after retries") -> BoardSnapshot:
        return BoardSnapshot(
            status="failed", postings=[], url=self.board_url(),
            observed_validators=None, error=error,
        )

    def unchanged_snapshot(self) -> BoardSnapshot:
        return BoardSnapshot(
            status="unchanged", postings=[], url=self.board_url(),
            observed_validators=None, error=None,
        )


GREENHOUSE_CASE = ProviderCase("greenhouse", GreenhouseProvider(), gh_parse, "jobs", "title")
LEVER_CASE = ProviderCase("lever", LeverProvider(), lever_parse, "array", "text")
ASHBY_CASE = ProviderCase("ashby", AshbyProvider(), ashby_parse, "jobs", "title")
WORKABLE_CASE = ProviderCase(
    "workable", WorkableProvider(), workable_parse, "jobs", "title", id_key="shortcode"
)
ALL_CASES = [GREENHOUSE_CASE, LEVER_CASE, ASHBY_CASE, WORKABLE_CASE]
