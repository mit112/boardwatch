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


#: What a gate row records for `gate.effort = None` — the calibrated argv, no `--effort` flag.
#: A string outside the setting's closed five-level vocabulary, NOT a JSON null: `json_extract`
#: reads a null and an absent key alike, and an absent key has to keep meaning "never recorded".
CLI_DEFAULT_EFFORT = "cli-default"


def gate_effort_key(effort: str | None) -> str:
    """The `$.effort` value a gate row judged at `settings.gate.effort` records, and the value the
    freshness read (`read.fresh_gate_verdicts`) matches on (T155)."""
    return CLI_DEFAULT_EFFORT if effort is None else effort


def record_gate_verdict(
    conn: Connection, *, posting_version_id: int, jd_text: str, facts: Facts,
    policy: Policy, catalog: RulesCatalog, verdict: OracleVerdict, run_id: int | None = None,
    shortlist_rank: int | None = None, provider: str | None = None, model: str | None = None,
    effort: str | None = None,
) -> int:
    """Persist one judge verdict. `shortlist_rank` is the lead's 1-based position in the
    ranker's DEPTH slate, recorded so conversion can be read BY RANK BAND afterwards.

    It goes in `raw_output_json` rather than `score`: `score` means the engine's own
    confidence in its verdict, and a rank is not that — writing a rank there would make
    every future reader of the column wrong. `None` is written as an ABSENT key rather
    than a null, so a row judged through a path that has no ranker (the
    `eligibility gate apply` CLI) is distinguishable from a lead that ranked nowhere.

    `provider`/`model` name the judge that reached this verdict, and go into the COLUMNS of
    those names rather than into `raw_output_json` — unlike `facts_key`, which is in
    `raw_output` only because re-keying the deterministic identity would have moved eight
    display readers. `model` is what the freshness read (`read.fresh_gate_verdicts`) and, since
    T161, every value read (`read.current_gate_verdicts`) match on, so a configured-model change
    is a MISS and the lead is re-judged under the new judge rather than coasting on the old one's
    verdict forever (T108).

    Both default to `None`, which is the legacy shape and the honest one for a caller that
    cannot name its judge: the `eligibility gate apply` CLI applies a verdicts file produced
    by whatever agent session the operator ran, not by `settings.gate.model`, and writing the
    configured model there would put a judge's name on a verdict it never reached. A row with
    `model IS NULL` never matches a given model, so the daily stage re-judges it ONCE (bounded
    by `--top`, D-477 pt 1) and it comes back keyed; the ledger is append-only, so there is no
    backfill and this is the only way those rows become attributable. No value read finds such
    a row either (T161), so a verdict applied through that CLI holds and releases nothing until
    the lead is re-judged by a named judge.

    `effort` is `gate_effort_key(settings.gate.effort)` from the daily stage and the T113
    refresh, and `None` — written as an ABSENT key — from a caller that cannot name the level,
    for the same reason as `model`. Unlike the judge's name it has no column, so it goes into
    `raw_output`; the eligibility tables are append-only, so this is forward-only (T155).

    `years` is the candidate's `total_years_experience` — the one fact the seniority question is
    asked relative to — and is what `read.current_gate_seniority` keys a reading on in place of
    the row identity (T152). Always written, as a JSON null when the profile has none.
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
        "years": facts.total_years_experience,
    }
    if shortlist_rank is not None:
        raw_output["shortlist_rank"] = shortlist_rank
    if effort is not None:
        raw_output["effort"] = effort
    return record_evaluation(
        conn, posting_version_id=posting_version_id,
        profile_hash=identity.profile_hash, profile_snapshot=identity.profile_snapshot,
        rules_hash=identity.rules_hash, rules_snapshot=identity.rules_snapshot,
        input_fingerprint=identity.input_fingerprint,
        engine_kind="llm", engine_version=gate_engine_version(),
        verdict=persisted, score=None, requirements=requirements,
        provider=provider, model=model, prompt_version=PROMPT_VERSION,
        idempotency_key=None, run_id=run_id, raw_output=raw_output,
    )
