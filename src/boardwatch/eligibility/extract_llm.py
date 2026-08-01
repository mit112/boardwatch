"""The opt-in LLM lane: advisory-only, structurally non-blocking eligibility audit.

This lane never withholds a posting. Everything it writes is ADVISORY (D-P3-13):
`requiredness` is fixed to `"preferred"` regardless of what the job description says,
and the aggregate verdict is capped to `"eligible"` or `"uncertain"` with no code path
to `"ineligible"`. Only `experience_years` is adjudicated at all (a number extracted
from the grounded span against `facts.total_years_experience`); every other family the
model names is recorded as `unknown`, detected but not judged, because there is no
rule catalog entry backing an LLM-sourced disposition for it.

Any failure in the provider call itself (`client.complete`) degrades to a skipped run
(`None`), not an exception, so a flaky or misbehaving adapter never takes down the
deterministic lane it runs alongside. A missing `client` (the tier disabled, or no
credential configured; see `boardwatch.llm.factory.build_client`) does the same.
"""

from __future__ import annotations

import hashlib
import re

from sqlalchemy import Connection

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.ground import GroundedSpan, ground
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import ModelClient
from boardwatch.llm.payload import build_payload
from boardwatch.llm.prompt import PROMPT_VERSION
from boardwatch.store.eligibility import (
    EligibilityVerdict,
    EvidenceDisposition,
    RequirementItem,
    SupportItem,
    record_evaluation,
)

LANE_VERSION = f"llm:{PROMPT_VERSION}"

_EXPERIENCE_YEARS_FAMILY = "experience_years"


def _requirement_for_span(span: GroundedSpan, facts: Facts) -> RequirementItem:
    """One advisory `RequirementItem` for a grounded span (D-P3-13).

    `experience_years` is the sole adjudicated family: a `\\d+ years|yrs` count parsed
    from the span's own quote, compared against `facts.total_years_experience`. Every
    other family is `unknown` with no support, detected but not judged.
    """
    jd_locator = {"field": "body_text", "span": [span.span[0], span.span[1]]}
    if span.family == _EXPERIENCE_YEARS_FAMILY:
        match = re.search(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", span.quote)
        if match is not None and facts.total_years_experience is not None:
            needed = int(match.group(1))
            total = facts.total_years_experience
            disposition: EvidenceDisposition = "met" if total >= needed else "unmet"
            return RequirementItem(
                requiredness="preferred",
                requirement_text=span.quote,
                jd_locator=jd_locator,
                disposition=disposition,
                rule_id=None,
                support=(
                    SupportItem(
                        profile_locator={"field": "total_years_experience"},
                        evidence_quote=str(total),
                        support_kind="fact",
                    ),
                ),
            )
    return RequirementItem(
        requiredness="preferred",
        requirement_text=span.quote,
        jd_locator=jd_locator,
        disposition="unknown",
        rule_id=None,
    )


def extract_and_record(
    conn: Connection,
    *,
    posting_version_id: int,
    jd_text: str,
    facts: Facts,
    policy: Policy,
    catalog: RulesCatalog,
    client: ModelClient | None,
    cache: ResponseCache,
    provider: str | None = None,
    model: str | None = None,
) -> int | None:
    """Run the LLM lane once and record an advisory `engine_kind='llm'` audit row.

    Returns the new evaluation id, or None if the lane was skipped: `client` is None
    (the tier is off or uncredentialed), or the provider call raised. A cache hit
    reuses the prior raw response instead of re-calling the provider; a miss calls
    `client.complete` and populates the cache. The verdict is capped to `"eligible"`
    or `"uncertain"` and can never be `"ineligible"`.

    `provider`/`model` are the caller's OWN record of which adapter it built (e.g. from
    `settings.llm`), recorded verbatim in the audit row. They are not read off `client`:
    the `ModelClient` protocol only guarantees `.complete`, and the real adapters
    (`AnthropicClient`, `OpenAICompatClient`) never carry a `.provider` attribute, so
    duck-typing that off the client silently lost the vendor on every real run.
    """
    if client is None:
        return None

    payload = build_payload(jd_text)
    content_hash = hashlib.sha256(jd_text.encode("utf-8")).hexdigest()
    cache_key = cache.key(content_hash, PROMPT_VERSION, model or "unknown")

    raw = cache.get(cache_key)
    if raw is None:
        try:
            raw = client.complete(payload["user"], system=payload["system"])
        except Exception:
            # Any provider/adapter failure (network, HTTP, malformed body) degrades this
            # opt-in lane to a skipped run. The deterministic lane never sees this.
            return None
        cache.put(cache_key, raw)

    spans = ground(jd_text, raw)
    items = [_requirement_for_span(span, facts) for span in spans]

    verdict: EligibilityVerdict = (
        "eligible"
        if items and all(item.disposition == "met" for item in items)
        else "uncertain"
    )

    identity = build_identity(
        posting_version_id=posting_version_id,
        facts=facts,
        policy=policy,
        catalog=catalog,
        declared_fields=declared_fields(),
    )

    return record_evaluation(
        conn,
        posting_version_id=posting_version_id,
        profile_hash=identity.profile_hash,
        profile_snapshot=identity.profile_snapshot,
        rules_hash=identity.rules_hash,
        rules_snapshot=identity.rules_snapshot,
        input_fingerprint=identity.input_fingerprint,
        engine_kind="llm",
        engine_version=LANE_VERSION,
        verdict=verdict,
        score=None,
        requirements=items,
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        idempotency_key=None,
        raw_output={"raw": raw},
    )
