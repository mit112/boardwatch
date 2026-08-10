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
from urllib.parse import parse_qsl, urlsplit, urlunsplit

_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9 ]")
_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|corp|co|ltd|technologies|technology|labs)\b")
# Title normalization is Unicode-aware (unlike normalize_company's pinned ASCII-only
# caveat): an all-non-ASCII title (e.g. Korean) must keep its letters, otherwise it
# collapses to "" and every such posting collides into one bucket. \W is Unicode-aware
# for str patterns, and _ is excluded so titles fold the same way ASCII ones do.
_NON_ALNUM_TO_SPACE = re.compile(r"[\W_]")
_WS = re.compile(r"\s+")

# Folded to words BEFORE the punctuation strip, which would otherwise erase them and make
# "C++ Developer", "C# Developer" and "C Developer" all normalize to "c developer" — three
# different roles sharing one identity component. `exact_quad` also requires an identical
# content_hash, so the collision only bites when a poster reuses one body across a role
# family, which is exactly what boilerplate reqs do. Precision is the invariant here.
#
# Only these two characters are folded, not punctuation generally: measured on a live
# 23,455-posting corpus, 8 of 147 suppression groups differ in raw title and all 8 differ
# only in punctuation/case noise on the same role (hyphen vs comma, "Store-in-Store" vs
# "Store in Store", "Javascript" vs "JavaScript"). Folding more would leak those 8 real
# duplicates to defend a collision that does not occur. 123 open titles contain "+" and 16
# contain "#", and none of them sits in any suppression group, so this costs no recall.
_LANG_TOKENS = (("+", " plus "), ("#", " sharp "))


def normalize_company(name: str) -> str:
    c = name.lower().strip()
    c = _NON_ALNUM_SPACE.sub("", c)
    c = _COMPANY_SUFFIXES.sub("", c)
    return _WS.sub(" ", c).strip()


def normalize_title(title: str) -> str:
    t = title.lower()
    for char, word in _LANG_TOKENS:
        t = t.replace(char, word)
    t = _NON_ALNUM_TO_SPACE.sub(" ", t)
    return _WS.sub(" ", t).strip()


def normalize_body(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def content_hash(body_text: str) -> str:
    return hashlib.sha256(normalize_body(body_text).encode("utf-8")).hexdigest()


# Allowlist, not denylist (design §4.1). Compared case-insensitively; anything not
# listed is dropped, including every utm_*, gh_src, ref and whatever is invented next.
_URL_PARAM_ALLOWLIST = frozenset(
    {"gh_jid", "jid", "id", "jobid", "req_id", "requisitionid", "posting_id", "lever_id"}
)
_DUP_SLASH = re.compile(r"/{2,}")


def normalize_url(url: str) -> str:
    """Canonical URL for host classification and survivor election.

    Not part of any identity key in P6 slice 1 — identity keys are built from company,
    title, locations and content hash. This exists so two spellings of the same posting
    URL classify and elect identically, and so slice 2's ledger has a stable key.
    """
    raw = url.strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.netloc:
        return raw
    host = parts.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    path = _DUP_SLASH.sub("/", parts.path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    kept = [
        f"{name}={value}"
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name.lower() in _URL_PARAM_ALLOWLIST
    ]
    # sorted() so param order is not identity.
    return urlunsplit(("https", host, path, "&".join(sorted(kept)), ""))
