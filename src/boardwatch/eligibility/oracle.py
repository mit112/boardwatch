"""P5b oracle judge foundations: the provenance gate + a best-effort span helper.

Ports job-apps' eligibility judge (`~/dev/Job apps/eligibility/judge.py:24-58`, reading it
is authorized by D-010) with one deliberate calibration change. job-apps tokenizes with
`[a-z0-9]{2,}` and requires >=4 total tokens; that erases "U.S." down to two single-letter
fragments ("u", "s") that the `{2,}` regex then drops entirely, so a real hard-stop
sentence like "U.S. citizenship required." falls short of the floor and never clears
provenance. Here the tokenizer is `[a-z0-9]+` (min 1 char, so "u"/"s" survive) and the
floor is lowered to `_MIN_TOTAL_TOKENS = 3`; the content floor (`_MIN_CONTENT_TOKENS = 2`,
non-stopword tokens) is unchanged, so an all-stopword span like "now or in the" still
fails — the calibration makes terse stops reachable, it does not weaken the content gate
(deepseek M6 / Opus M2, D-067).

`resolve_provenance` stays a boolean on purpose (Opus M2): nothing downstream may treat a
raw offset as ground truth, so the critical path only ever sees pass/fail. `span_of` is a
separate, best-effort helper (reusing ground.py's `str.find` idea) for reporting only —
callers must not gate acceptance on whether it returns a span.

No module-level string collection lives here (R9 scopes eligibility modules against
shipping a preference/title collection as a module default): the stopword set sits inside
`resolve_provenance`, not as a module constant, mirroring ground.py's `coded_families`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boardwatch.eligibility.catalog import RulesCatalog
from boardwatch.lanes.quality import is_employer_body

# Verdict-cache invalidation knobs, ported from job-apps judge.py:14-15. Bump either to
# force a clean re-judge of every JD once later tasks wire the cache key.
POLICY_VERSION = "p5-oracle-1"
PROMPT_VERSION = "p5-oracle-1"

# Multi-tenant rewrite of job-apps' F-1/OPT-hardcoded prompt (`~/dev/Job apps/eligibility/
# judge.py:73-101`, reading authorized by D-010). That original prompt hardcodes one
# person's visa story ("F-1 OPT candidate", "no/again-future sponsorship") directly into
# the instructions; this version judges against whatever `facts` the request supplies, so
# the same prompt serves a citizen, a visa holder in another country, or an OPT candidate
# without a code change (multi-tenancy invariant, CLAUDE.md).
#
# M3: the reference labeling policy treats all six catalog families as blockers, even
# though the engine's own `default_policy` treats several of them (experience_years,
# clearance, degree, contract_not_fte, internship) as soft "preference" signals at
# runtime. That split is deliberate: an answer key that never lets those families produce
# `ineligible` couldn't validate the engine's handling of them at all. The request payload
# carries this as an explicit `policy.families` map (see `build_label_request`), not just
# a version string, so the judge's assumed policy is inspectable and not tacit.
# R9: JUDGING_POLICY stays the single module-level string this file ships (no separate
# string-collection constant). The H2 no-force-fit sentence below is spliced in via
# adjacent string-literal concatenation (no `+`, no embedded newline) purely so it reads
# as one unbroken sentence while still respecting this file's 100-char line limit — the
# assignment below is still exactly one `JUDGING_POLICY = """...""" ` expression.
JUDGING_POLICY = (
    """You are an eligibility judge. Decide whether the job description (JD) below
presents a hard stop against the candidate described by `facts`, using ONLY the JD text and
`facts` supplied in this request. Do not consult, and are not given, any prior guess, engine
verdict, or human label for this posting — judge independently.

`facts` describes ONE real candidate and may include: work-authorization status and whether
they need sponsorship (`ead_or_similar`, `needs_sponsorship`, or equivalent), highest degree
held, employment-type preference (e.g. full-time only), total years of professional
experience, and security-clearance status. Treat every field in `facts` as ground truth about
this candidate; a field that is absent means "unknown," not "no."

For every requirement the JD states, first classify it as REQUIRED or PREFERRED. Only a
REQUIRED hard stop that the candidate's `facts` fail can produce `ineligible` — a PREFERRED /
nice-to-have qualification the candidate lacks is never itself a hard stop.

The reference policy for this labeling pass treats ALL SIX reason_catalog families as
blockers: work_auth, experience_years, clearance, degree, contract_not_fte, internship. A
REQUIRED hard stop in any of these six families, that the supplied `facts` fail, is eligible
to produce `ineligible` — regardless of whether the live engine treats that family as a soft
preference at runtime; this judging pass is calibrating the answer key, not replaying engine
policy.

"""
    "If the JD states a decisive hard stop whose category is NOT one of the "
    "reason_catalog families, output `uncertain` — never force-fit it into a "
    "different family."
    """
(Seniority language, role-family mismatch, location, and similar hard stops are real but
out of scope for this six-family judgment; they belong to `uncertain`, not to the nearest
available reason.)

Return one verdict object per item, using ONLY this schema:
  decision: "eligible" | "ineligible" | "uncertain"
  reason: one of the reason_catalog family ids, or null (null unless decision is "ineligible")
  evidence: the verbatim decisive sentence from the JD (required whenever decision is
    "ineligible"; the exact substring must appear in the JD text, not a paraphrase)
  confidence: "high" | "medium" | "low"
"""
)

_MIN_TOTAL_TOKENS = 3
_MIN_CONTENT_TOKENS = 2


def _norm(s: str) -> str:
    """Normalize for substring comparison. Ported verbatim from job-apps judge.py:37-40:
    fold unicode dashes/quotes to ASCII, strip HTML entities and markdown emphasis chars,
    collapse whitespace, lowercase."""
    s = s.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'")
    s = re.sub(r"&[a-z]+;|[*_`#>]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def resolve_provenance(evidence: str, jd_text: str) -> bool:
    """True iff `evidence` is a normalized substring of the JD AND informative
    (>= _MIN_TOTAL_TOKENS tokens, >= _MIN_CONTENT_TOKENS non-stopword). Boolean
    only — never a raw offset (see span_of). Ported from job-apps judge.py:42-58,
    token floor calibrated so terse clearance/citizenship stops survive."""
    # _STOPWORDS ported verbatim from job-apps judge.py:24-31.
    _STOPWORDS = frozenset({
        "we", "i", "you", "your", "our", "they", "their", "them", "it", "its",
        "a", "an", "the", "this", "that", "these", "those",
        "do", "does", "did", "is", "are", "was", "were", "be", "been", "being", "has",
        "have", "had",
        "will", "would", "shall", "should", "can", "could", "may", "must", "might",
        "no", "not", "or", "and", "but", "if", "so", "as", "of", "to", "in", "on", "at",
        "by", "for",
        "with", "from", "up", "out", "per", "now", "then", "than", "only", "any", "all",
        "we'll",
    })
    ev = evidence.strip()
    if not ev:
        return False
    if _norm(ev) not in _norm(jd_text):
        return False
    toks = re.findall(r"[a-z0-9]+", _norm(ev))
    content = [t for t in toks if t not in _STOPWORDS]
    return len(toks) >= _MIN_TOTAL_TOKENS and len(content) >= _MIN_CONTENT_TOKENS


def span_of(evidence: str, jd_text: str) -> tuple[int, int] | None:
    """Best-effort literal offset into the RAW jd_text (reuse ground.py's idea).
    Returns None when the quote only matches after normalization — tolerated,
    because score() never reads the answer key's spans (design §Note)."""
    ev = evidence.strip()
    idx = jd_text.find(ev)
    if idx < 0:
        return None
    return (idx, idx + len(ev))


class OracleVerdictError(ValueError):
    """Raised when an OracleVerdict.decision is out of the {eligible,ineligible,uncertain}
    vocabulary (e.g. job-apps' legacy "move" decision)."""


@dataclass(frozen=True)
class OracleVerdict:
    """Raw judge output, pre-gate. Mirrors job-apps' judge.py verdict shape."""

    label: str
    decision: str
    reason: str | None
    evidence: str
    confidence: str


@dataclass(frozen=True)
class AcceptedLabel:
    """Answer-key row: the judge's verdict after the ineligible-gate has run."""

    label: str
    expected_verdict: str
    reason: str | None
    spans: tuple[tuple[int, int], ...]
    confidence: str
    evidence: str
    label_provenance: str
    oracle_policy_version: str
    oracle_prompt_version: str
    downgraded: bool


_VERDICTS = frozenset({"eligible", "ineligible", "uncertain"})


def is_allowed_reason(reason: str | None, catalog: RulesCatalog) -> bool:
    return reason is not None and reason in {f.id for f in catalog.families}


def accept_oracle_verdict(v: OracleVerdict, jd_text: str, catalog: RulesCatalog) -> AcceptedLabel:
    """The four-ANDed ineligible-gate, reused as an answer-key-integrity gate. Accept
    `ineligible` ONLY if the reason is in-catalog AND confidence is high AND the evidence
    resolves provenance against the JD — else downgrade to `uncertain` (fail-open: never
    a false INELIGIBLE in ground truth). This is the H2 no-force-fit rule: a hard stop
    whose category isn't one of the 6 families becomes uncertain, never mislabeled — the
    engine is title-blind, so seniority/location/role hard stops legitimately cannot be
    scored here."""
    decision = v.decision.strip().lower()
    if decision not in _VERDICTS:
        raise OracleVerdictError(f"decision {v.decision!r} not in {sorted(_VERDICTS)}")
    confidence = v.confidence.strip().lower()
    accepted: str = decision
    downgraded = False
    spans: tuple[tuple[int, int], ...] = ()
    if decision == "ineligible":
        if (
            is_allowed_reason(v.reason, catalog)
            and confidence == "high"
            and resolve_provenance(v.evidence, jd_text)
        ):
            s = span_of(v.evidence, jd_text)
            spans = (s,) if s is not None else ()  # L3: tolerate normalized-only match
        else:
            accepted, downgraded = "uncertain", True
    return AcceptedLabel(
        label=v.label,
        expected_verdict=accepted,
        reason=v.reason if accepted == "ineligible" else None,
        spans=spans,
        confidence=confidence,
        evidence=v.evidence,
        label_provenance="oracle",
        oracle_policy_version=POLICY_VERSION,
        oracle_prompt_version=PROMPT_VERSION,
        downgraded=downgraded,
    )


def read_worksheet(path: Path) -> list[dict[str, Any]]:
    """Raw jsonl reader: every row as a dict, unlabeled rows INCLUDED. Deliberately not
    `scoring.load_labeled_set`, which discards rows with `expected_verdict is None` — the
    whole point here is to find those rows so they can be sent to the judge (M5)."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _bucket(label: str) -> str:
    """H1: hard-negatives carry the `applied/` prefix (extract_candidates.py:187), NOT
    `_applied/` — that is a job-apps source-folder name, never a worksheet label."""
    return "hard_negative" if label.startswith("applied/") else "hard_stop"


def build_label_request(
    rows: list[dict[str, Any]], catalog: RulesCatalog, *, request_id: str
) -> dict[str, Any]:
    """The request JSON payload sent to the judge. Selects only unlabeled rows
    (`expected_verdict is None`) and drops `hint` from every item (independence: the
    judge must never see a prior guess for the label it is about to produce)."""
    fam = [f.id for f in catalog.families]
    items = [
        {
            "label": r["label"],
            "facts": r.get("facts", {}),
            "jd_text": r.get("body_text", ""),
            "bucket": _bucket(r["label"]),
        }
        for r in rows
        if r.get("expected_verdict") is None
        # The SEND boundary of the lane-body precondition (D-406) at the fourth eligibility seam.
        # A worksheet body that is an aggregator's rendered PAGE — jobright's own `H1B Sponsor
        # Likely` label and CTAs, not the employer's JD — must never reach the judge: reading that
        # label it returns `ineligible(work_auth)` citing a third party's guess, which the CLI then
        # writes to the answer key as ground truth. Mirrors `build_gate_request`'s SEND filter.
        # This function is pure and cannot record the refusal; `apply_oracle_verdicts` enforces the
        # same precondition on the write side, so a hand-authored verdicts file that never came
        # through here is refused there too.
        and is_employer_body(r.get("body_text", ""))
    ]
    return {
        "request_id": request_id,
        "policy_version": POLICY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "reason_catalog": fam,
        "policy": {"families": {f: "blocker" for f in fam}},  # M3
        "judging_policy": JUDGING_POLICY,
        "items": items,
    }


@dataclass(frozen=True)
class ApplyResult:
    """Report from `apply_oracle_verdicts`: what got labeled, and integrity flags worth
    surfacing (H1: hard-negatives the oracle accepted as ineligible)."""

    labeled: int
    downgraded: int
    overwritten: int
    hard_negative_ineligible: tuple[str, ...]
    by_verdict: dict[str, int]


# Every field `apply_oracle_verdicts` writes when it labels a row. `_sanitize_foreign_row`
# clears exactly this set so a foreign body returns to a pristine unlabeled row.
_ORACLE_WRITTEN_FIELDS = (
    "reason",
    "spans",
    "confidence",
    "evidence",
    "label_provenance",
    "oracle_policy_version",
    "oracle_prompt_version",
    "downgraded",
)


def _sanitize_foreign_row(row: dict[str, Any]) -> None:
    """Return an oracle-authored row on a foreign body to unlabeled, clearing every
    oracle-produced field. A current-stamped corrupt row would otherwise satisfy `_skip_row`
    (it looks already-done) and be LEFT in the worksheet as a false `ineligible` answer key;
    a foreign body must leave the worksheet unlabeled regardless of its stamps."""
    row["expected_verdict"] = None
    for field in _ORACLE_WRITTEN_FIELDS:
        row.pop(field, None)


def _skip_row(row: dict[str, Any]) -> bool:
    """M4: version-aware idempotency. Never overwrite a human-audited row; never
    re-label a row already stamped by this exact oracle policy+prompt version
    (idempotent no-op) — a row with a missing or partial stamp is NOT treated as
    current (a malformed/unstamped `oracle` row must be re-judged, not silently
    skipped forever); never overwrite a hand label (a non-null verdict with no
    `label_provenance` at all — i.e. not previously written by this function)."""
    provenance = row.get("label_provenance")
    if provenance == "audited":
        return True
    if (
        provenance == "oracle"
        and row.get("oracle_policy_version") == POLICY_VERSION
        and row.get("oracle_prompt_version") == PROMPT_VERSION
    ):
        return True
    if row.get("expected_verdict") is not None and provenance is None:
        return True
    return False


def apply_oracle_verdicts(
    rows: list[dict[str, Any]], verdicts: list[OracleVerdict], catalog: RulesCatalog
) -> tuple[list[dict[str, Any]], ApplyResult]:
    """Run each verdict through `accept_oracle_verdict` and merge the result back into
    its worksheet row by `label`, in place (M5: preserves every other column — `hint`,
    `company`, `title`, `source`, `facts`, `body_text`, ...). Skips rows the M4 guard
    protects. Flags `applied/`-prefix (hard-negative, H1) rows accepted as `ineligible`
    for review — Mit actually applied to those, so an ineligible verdict is a red flag,
    not necessarily a bug."""
    by_label = {r["label"]: r for r in rows}
    labeled = 0
    downgraded = 0
    overwritten = 0
    hard_negatives: list[str] = []
    by_verdict: dict[str, int] = {}

    for v in verdicts:
        row = by_label.get(v.label)
        if row is None:
            continue
        # The WRITE boundary of the lane-body precondition (D-406), and the one that matters most
        # here: `accept_oracle_verdict` slices an `ineligible` span out of this very body, so a
        # foreign body reaching it writes a FALSE `ineligible(work_auth)` answer-key row — and the
        # answer key is what every precision measurement is scored against. This runs BEFORE
        # `_skip_row`: a row a PRIOR pass already corrupted into `ineligible` and stamped with the
        # current policy+prompt would otherwise be treated as already-done and LEFT intact, so an
        # oracle-authored foreign row is sanitized back to unlabeled here regardless of its stamps.
        # Bodies REJECTED BY THE CURRENT DETECTOR are the ones this refuses — the marker threshold
        # is `is_employer_body`'s, unchanged here. Refused for STALE and HAND-AUTHORED verdicts
        # alike (a verdicts file that names a foreign-body row is stopped even though
        # `build_label_request` never selected it), mirroring the gate APPLY boundary's
        # `withhold_foreign_versions`.
        if not is_employer_body(row.get("body_text", "")):
            if row.get("label_provenance") == "oracle":
                _sanitize_foreign_row(row)
            continue
        if _skip_row(row):
            continue
        was_stale_oracle = row.get("label_provenance") == "oracle"
        accepted = accept_oracle_verdict(v, row.get("body_text", ""), catalog)
        row["expected_verdict"] = accepted.expected_verdict
        row["reason"] = accepted.reason
        row["spans"] = [list(s) for s in accepted.spans]
        row["confidence"] = accepted.confidence
        row["evidence"] = accepted.evidence
        row["label_provenance"] = accepted.label_provenance
        row["oracle_policy_version"] = accepted.oracle_policy_version
        row["oracle_prompt_version"] = accepted.oracle_prompt_version
        row["downgraded"] = accepted.downgraded

        labeled += 1
        if accepted.downgraded:
            downgraded += 1
        if was_stale_oracle:
            overwritten += 1
        by_verdict[accepted.expected_verdict] = by_verdict.get(accepted.expected_verdict, 0) + 1
        if _bucket(v.label) == "hard_negative" and accepted.expected_verdict == "ineligible":
            hard_negatives.append(v.label)

    result = ApplyResult(
        labeled=labeled,
        downgraded=downgraded,
        overwritten=overwritten,
        hard_negative_ineligible=tuple(hard_negatives),
        by_verdict=by_verdict,
    )
    return rows, result
