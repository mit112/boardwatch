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

import re
from dataclasses import dataclass

from boardwatch.eligibility.catalog import RulesCatalog

# Verdict-cache invalidation knobs, ported from job-apps judge.py:14-15. Bump either to
# force a clean re-judge of every JD once later tasks wire the cache key.
POLICY_VERSION = "p5-oracle-1"
PROMPT_VERSION = "p5-oracle-1"

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
