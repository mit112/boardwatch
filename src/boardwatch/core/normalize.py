"""Dedup normalization, ported function-by-function from the private pipeline (D9/§6.6).

content_hash is a pure, documented function of normalized body text:
SHA-256 over normalize_body(text) — lowercase, all whitespace runs collapsed
to single spaces, stripped. Whitespace-only and case-only changes therefore
never change the hash. (Port note: the source pipeline used MD5; the public
port uses SHA-256 — plan deviation 3.)
"""

from __future__ import annotations

import hashlib
import re

_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9 ]")
_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|corp|co|ltd|technologies|technology|labs)\b")
_NON_ALNUM_TO_SPACE = re.compile(r"[^a-z0-9 ]")
_WS = re.compile(r"\s+")


def normalize_company(name: str) -> str:
    c = name.lower().strip()
    c = _NON_ALNUM_SPACE.sub("", c)
    c = _COMPANY_SUFFIXES.sub("", c)
    return _WS.sub(" ", c).strip()


def normalize_title(title: str) -> str:
    t = title.lower()
    t = _NON_ALNUM_TO_SPACE.sub(" ", t)
    return _WS.sub(" ", t).strip()


def normalize_body(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def content_hash(body_text: str) -> str:
    return hashlib.sha256(normalize_body(body_text).encode("utf-8")).hexdigest()
