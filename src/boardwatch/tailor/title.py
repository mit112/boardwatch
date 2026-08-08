"""Headline-title de-senioritization (P4 item 7, folding in the deferred item 4).

We only STRIP seniority — never down-level to a specific rung, which would require a
seniority profile field that does not exist. A "Senior iOS Engineer" JD yields "iOS
Engineer", never stamping "Senior" onto a new-grad résumé.
"""

from __future__ import annotations

import re

from boardwatch.extract.role_family import classify_role_family
from boardwatch.tailor.persona import Persona
from boardwatch.tailor.tokens import whole_token_sub

# Closed seniority-token set. Ordered most-specific-first so a longer token is removed before a
# shorter one it contains ("sr." before "sr"; roman "iii" before "ii"). The whole-token
# boundaries in `whole_token_sub` ((?<!\w)...(?!\w)) already prevent partial matches — 'sr'
# never fires inside 'SRE', 'lead' never inside 'Leadership' — the ordering is belt-and-braces.
_SENIORITY_TOKENS: tuple[str, ...] = (
    "distinguished",
    "principal",
    "staff",
    "senior",
    "lead",
    "sr.",
    "sr",
    "iii",
    "ii",
    "iv",
    "v",
)

_SEPARATORS = " ,-/|&"


def strip_seniority(title: str) -> str:
    """Remove every seniority token, boundary-safe, then collapse the double spaces and dangling
    separators the removal leaves behind. A title with no seniority token is returned unchanged
    (modulo whitespace normalization)."""
    out = title
    for token in _SENIORITY_TOKENS:
        replaced = whole_token_sub(out, token, "")
        if replaced is not None:
            out = replaced
    out = " ".join(out.split())  # collapse whitespace runs
    out = re.sub(r"\s+([,/|&)])", r"\1", out)  # no space before a closing separator
    out = re.sub(r"([(/|&])\s+", r"\1", out)  # no space after an opening separator
    out = out.strip(_SEPARATORS)  # trim separators the removal left dangling at the edges
    return " ".join(out.split())


def resolve_title(jd_title: str, persona: Persona) -> str:
    """The résumé headline for this JD: the de-senioritized JD title when it is non-empty AND
    still classifies into one of the persona's role families; otherwise the persona's base
    title. Deterministic, never a model call, and never emits a seniority token."""
    stripped = strip_seniority(jd_title)
    if stripped and classify_role_family(stripped) in persona.role_families:
        return stripped
    return persona.title
