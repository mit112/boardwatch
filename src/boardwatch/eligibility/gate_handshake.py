"""The `eligibility gate request` / `gate apply` CLI handshake (pure logic, CLI-free).

`build_gate_request` turns the ranked shortlist's visible postings into the same
request-JSON shape `oracle.build_label_request` already produces for the answer-key
labeling handshake — byte-compatible, independence-preserving (no `hint`, no prior
engine verdict), so one skill/judge serves both entry points (design §5.1, §5.6).

`apply_gate_verdicts` is the write side: map each verdict back to its posting via
`label == str(posting_id)`, resolve against the posting's CURRENT OPEN version body
(never a stale one captured at request time — drift can only cost a recall miss, per
the keystone-span downgrade `final_gate.record_gate_verdict` already applies), and
persist through the Task-1 writer under the user's STORED facts+policy (never the
labeling pass's all-blocker reference policy — that is what keeps the ranker's read
on the same identity the write used).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import Connection

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.eligibility.facts import Facts, Policy, facts_payload
from boardwatch.eligibility.final_gate import record_gate_verdict
from boardwatch.eligibility.oracle import (
    OracleVerdict,
    accept_oracle_verdict,
    build_label_request,
)
from boardwatch.store.queries import CurrentVersion


class _HasPostingId(Protocol):
    @property
    def posting_id(self) -> int: ...


def build_gate_request(
    ranked_visible: Sequence[_HasPostingId],
    versions: dict[int, CurrentVersion],
    facts: Facts,
    catalog: RulesCatalog,
    *,
    request_id: str,
) -> dict[str, Any]:
    """One synthetic row per visible posting: `{"label": str(posting_id), "facts":
    facts_payload(facts), "body_text": <current OPEN version body>, "expected_verdict":
    None}`, fed to `build_label_request` (label = posting id, so `apply_gate_verdicts`
    can map a verdict back). `expected_verdict` is always absent/None here — every
    visible posting is unlabeled by construction, independence is `build_label_request`'s
    job (it also drops any `hint`, irrelevant here since these rows never carry one).

    A visible posting with no entry in `versions` is skipped rather than raised: it
    cannot happen when `versions` comes from `current_posting_versions(conn, None)`
    (every open posting), but a caller-supplied narrower map should not crash the
    request build over one stale id.
    """
    payload = facts_payload(facts)
    rows = [
        {
            "label": str(posting.posting_id),
            "facts": payload,
            "body_text": versions[posting.posting_id].body_text,
            "expected_verdict": None,
        }
        for posting in ranked_visible
        if posting.posting_id in versions
    ]
    return build_label_request(rows, catalog, request_id=request_id)


@dataclass(frozen=True)
class ApplyGateResult:
    """Tally from one `apply_gate_verdicts` call.

    `judged` counts verdicts that matched a still-open posting and were persisted
    (a verdict whose label matches no open posting — closed since `gate request`, or
    a malformed label — is skipped, not counted, mirroring `apply_oracle_verdicts`'
    skip-not-crash stance on rows it cannot place). `ineligible` counts what actually
    landed as `ineligible` in the ledger, AFTER both the oracle's four-ANDed
    acceptance gate and `record_gate_verdict`'s keystone-span downgrade — never the
    judge's raw `decision`. `downgraded` counts a verdict the judge decided
    `ineligible` that did not end up persisted as `ineligible` (low confidence,
    out-of-catalog reason, unresolvable provenance, or a provenanced-but-unspannable
    quote) — fail-open by construction. `demoted_labels` lists the labels (posting
    ids, as strings) that were written `ineligible`, for the CLI's warning line.
    """

    judged: int
    ineligible: int
    downgraded: int
    demoted_labels: tuple[str, ...]


def apply_gate_verdicts(
    conn: Connection,
    verdicts: list[OracleVerdict],
    *,
    versions: dict[int, CurrentVersion],
    facts: Facts,
    policy: Policy,
    catalog: RulesCatalog,
    run_id: int | None = None,
) -> ApplyGateResult:
    """Run every verdict through `record_gate_verdict` against the posting's CURRENT
    OPEN version body (`versions`, re-read by the caller at apply time — this is the
    whole of the body-drift safety property: identity hashes the version id, not the
    body, so a rolled version just means provenance is checked against new text).

    Persists under the caller-supplied `facts`/`policy` — the CALLER is responsible
    for passing the user's STORED facts+policy (`parse_facts`/`parse_policy` off the
    profile row), never the labeling pass's all-blocker reference policy; writing
    under the wrong policy computes a different identity and the ranker's read
    silently no-ops.
    """
    judged = 0
    ineligible = 0
    downgraded = 0
    demoted: list[str] = []
    for verdict in verdicts:
        try:
            posting_id = int(verdict.label)
        except ValueError:
            continue
        current = versions.get(posting_id)
        if current is None:
            continue
        # Mirrors record_gate_verdict's own accept+keystone-span logic exactly, so the
        # tally reflects what actually got persisted rather than the judge's raw
        # decision. record_gate_verdict recomputes this itself (pure, cheap, no side
        # effect risk of divergence since both read the same current.body_text).
        accepted = accept_oracle_verdict(verdict, current.body_text, catalog)
        persisted = accepted.expected_verdict
        if persisted == "ineligible" and not accepted.spans:
            persisted = "uncertain"
        record_gate_verdict(
            conn,
            posting_version_id=current.posting_version_id,
            jd_text=current.body_text,
            facts=facts,
            policy=policy,
            catalog=catalog,
            verdict=verdict,
            run_id=run_id,
        )
        judged += 1
        if persisted == "ineligible":
            ineligible += 1
            demoted.append(verdict.label)
        elif verdict.decision.strip().lower() == "ineligible":
            downgraded += 1
    return ApplyGateResult(
        judged=judged,
        ineligible=ineligible,
        downgraded=downgraded,
        demoted_labels=tuple(demoted),
    )
