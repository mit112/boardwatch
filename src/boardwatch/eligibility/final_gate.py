"""The final eligibility gate lane: an agent-lane judge's verdicts persisted as an
ineligible-capable engine_kind='llm' lane, distinct from the advisory extract_llm lane by an
engine_version 'final_gate:' prefix. Keystone-guarded: an accepted ineligible without a
resolvable raw JD span downgrades to uncertain (fail-open) rather than writing a span-less
INELIGIBLE."""
from __future__ import annotations

from sqlalchemy import Connection

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.facts import Facts, Policy, facts_payload
from boardwatch.eligibility.hashing import build_identity, digest
from boardwatch.eligibility.oracle import (
    POLICY_VERSION,
    PROMPT_VERSION,
    OracleVerdict,
    accept_oracle_verdict,
)
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.eligibility import (
    EligibilityVerdict,
    RequirementItem,
    record_evaluation,
)

GATE_VERSION_PREFIX = "final_gate:"


def gate_engine_version() -> str:
    return f"{GATE_VERSION_PREFIX}{POLICY_VERSION}:{PROMPT_VERSION}"


def gate_facts_key(facts: Facts) -> str:
    """A digest of the EXACT payload the judge is sent — `facts_payload(facts)`, the same
    object `gate_handshake.build_gate_request` puts in every item.

    The freshness test needs this because the ROW IDENTITY cannot see it. `hashing.
    build_identity` folds a family's declared fields into `profile_hash` only when the live
    policy severity is not `"ignore"`, but the judge reads every fact under an all-blocker
    policy (D-461). So under `Policy(families={"work_auth": "ignore"})` a change from
    `citizen` to `needs_sponsorship` leaves the identity byte-identical while the judge's
    request changes, and a cached clear on a no-sponsorship JD stays "fresh" after the fact
    that decides it moved.

    Written into `raw_output` rather than into the identity: eight display readers join gate
    rows on the DETERMINISTIC `(profile_hash, rules_hash)` from `preflight.current_identity`,
    and re-keying the rows under the judge's policy would move every one of them.
    `digest` is `hashing`'s sorted-key compact-JSON sha256 — the canonical form this repo
    already hashes every snapshot with.
    """
    return digest(facts_payload(facts))


def record_gate_verdict(
    conn: Connection, *, posting_version_id: int, jd_text: str, facts: Facts,
    policy: Policy, catalog: RulesCatalog, verdict: OracleVerdict, run_id: int | None = None,
    shortlist_rank: int | None = None,
) -> int:
    """Persist one judge verdict. `shortlist_rank` is the lead's 1-based position in the
    ranker's DEPTH slate, recorded so conversion can be read BY RANK BAND afterwards.

    It goes in `raw_output_json` rather than `score`: `score` means the engine's own
    confidence in its verdict, and a rank is not that — writing a rank there would make
    every future reader of the column wrong. `None` is written as an ABSENT key rather
    than a null, so a row judged through a path that has no ranker (the
    `eligibility gate apply` CLI) is distinguishable from a lead that ranked nowhere.
    """
    accepted = accept_oracle_verdict(verdict, jd_text, catalog)
    persisted: EligibilityVerdict = accepted.expected_verdict  # type: ignore[assignment]
    requirements: list[RequirementItem] = []
    if accepted.expected_verdict == "ineligible":
        # Keystone: an ineligible MUST carry a span. accept_oracle_verdict tolerates a
        # normalized-only provenance match with spans=() (span_of did a raw find and missed);
        # persisting that as ineligible would be a span-less INELIGIBLE. Downgrade, fail-open.
        if accepted.spans:
            start, end = accepted.spans[0]
            requirements = [RequirementItem(
                requiredness="required",
                requirement_text=accepted.evidence,
                jd_locator={"field": "body_text", "span": [start, end]},
                disposition="unmet",
                rule_id=f"final_gate:{accepted.reason}",
            )]
        else:
            persisted = "uncertain"
    identity = build_identity(
        posting_version_id=posting_version_id, facts=facts, policy=policy,
        catalog=catalog, declared_fields=declared_fields(),
    )
    raw_output: dict[str, object] = {
        "gate_verdict": verdict.__dict__, "facts_key": gate_facts_key(facts),
    }
    if shortlist_rank is not None:
        raw_output["shortlist_rank"] = shortlist_rank
    return record_evaluation(
        conn, posting_version_id=posting_version_id,
        profile_hash=identity.profile_hash, profile_snapshot=identity.profile_snapshot,
        rules_hash=identity.rules_hash, rules_snapshot=identity.rules_snapshot,
        input_fingerprint=identity.input_fingerprint,
        engine_kind="llm", engine_version=gate_engine_version(),
        verdict=persisted, score=None, requirements=requirements,
        provider=None, model=None, prompt_version=PROMPT_VERSION,
        idempotency_key=None, run_id=run_id, raw_output=raw_output,
    )
