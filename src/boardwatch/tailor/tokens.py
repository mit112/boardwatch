from __future__ import annotations

import re

_TOKEN = re.compile(r"\w+|\S")


def toks(s: str) -> list[str]:
    return _TOKEN.findall(s)


def _pat(frm: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(frm)}(?!\w)", re.IGNORECASE)


def has_whole_token(text: str, frm: str) -> bool:
    return _pat(frm).search(text) is not None


def whole_token_sub(text: str, frm: str, to: str) -> str | None:
    p = _pat(frm)
    return p.sub(to, text) if p.search(text) else None
