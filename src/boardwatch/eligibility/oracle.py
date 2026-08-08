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
