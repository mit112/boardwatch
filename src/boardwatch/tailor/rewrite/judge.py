from __future__ import annotations

import re
from typing import Literal

Verdict = Literal["ENTAILED", "NOT_ENTAILED", "UNSURE"]

# Only whitespace and the separator characters the judge's own legal spelling variants
# use (the underscore in NOT_ENTAILED, a hyphen, a colon after an optional "Verdict"
# label) are squashed out before the equality check. Anything else — parentheses,
# asterisks, periods, commas, stray prose — is left in place and therefore breaks an
# exact match. That is deliberate: it is what makes an annotated reply like "ENTAILED*"
# or "ENTAILED (low confidence)" fail equality instead of silently squashing away the
# very thing that makes the reply untrustworthy.
_SEPARATOR = re.compile(r"[\s_:-]+")
_NEGATED = frozenset({"NOTENTAILED", "NONENTAILED", "UNENTAILED"})
_VERDICT_PREFIX = "VERDICT"


def parse_verdict(reply: str) -> Verdict:
    """Map a judge reply to a verdict by exact-token allowlist, not by scanning for bad words.

    The judge's own system prompt (``JUDGE_SYSTEM`` in ``prompt.py``) demands "exactly one
    token: ENTAILED, NOT_ENTAILED, or UNSURE. No other text." Acceptance therefore requires
    that exact canonical token: any prose, hedge, annotation, or unrecognized reply is
    off-contract and returns ``UNSURE``, which the lane treats as a drop.

    This replaces an earlier blocklist shape (enumerate bad words, accept anything else that
    merely contains ``ENTAILED``) that regressed three times running — each fix added more
    banned words and the next review found more misses: hedges ("partially entailed",
    "arguably entailed"), annotations ("ENTAILED (low confidence)", "ENTAILED*"), and
    backhanded negatives ("this is unlikely to be entailed"). An open-ended "everything not
    on the deny-list" surface can always be found again; an allowlist of one exact token
    cannot, because there is nothing left to enumerate.

    Only whitespace/underscore/hyphen/colon are squashed out first — just enough to tolerate
    the judge's own legal spelling variants (``NOT_ENTAILED``'s underscore) and a leading
    "Verdict: " label some models add unprompted. Any other leftover character means the
    reply is not a clean token, so the equality check correctly fails.

    This trades false-rejects for the elimination of an open-ended false-accept class: a
    genuinely entailed rewrite phrased as anything other than the exact token now falls back
    to ``UNSURE`` and the bullet is dropped, rather than risking one more hedge word this
    allowlist didn't anticipate slipping through as an accept. That is an acceptable trade
    for this project's bar — a dropped rewrite costs polish; a wrong ``ENTAILED`` puts a
    fabricated claim on a real person's résumé.
    """
    squashed = _SEPARATOR.sub("", reply.upper())
    if squashed.startswith(_VERDICT_PREFIX):
        squashed = squashed[len(_VERDICT_PREFIX):]
    if squashed == "ENTAILED":
        return "ENTAILED"
    if squashed in _NEGATED:
        return "NOT_ENTAILED"
    if squashed == "UNSURE":
        return "UNSURE"
    return "UNSURE"
