"""Title-based role-family classifier, ported priority-ordered from the
private pipeline (§3.6, D9/§6.6). First match wins — the order is load-bearing
(e.g. 'Mobile Security Engineer' is mobile, 'ML Infrastructure Engineer' is
devops_sre); reordering is a semantic change requiring an EXTRACTOR_REVISION
bump."""

from __future__ import annotations

import re

ROLE_FAMILIES: list[tuple[str, re.Pattern[str]]] = [
    (
        "mobile",
        re.compile(
            r"\bios\b|\bandroid\b|\bmobile\b|\bflutter\b|react\s?native|\bswift\b",
            re.IGNORECASE,
        ),
    ),
    ("security", re.compile(r"\bsecurity\b|\bappsec\b", re.IGNORECASE)),
    (
        "devops_sre",
        re.compile(
            r"\bdevops\b|site reliab|\bsre\b|cloud engineer|infrastructure engineer"
            r"|platform engineer",
            re.IGNORECASE,
        ),
    ),
    ("data_eng", re.compile(r"\bdata engineer|analytics engineer|\betl\b", re.IGNORECASE)),
    (
        "ml_ai",
        re.compile(
            r"machine learning|\bml\b|\ba\.?i\.?\b|applied scientist|deep learning"
            r"|\bllm\b|gen\s?ai|genai",
            re.IGNORECASE,
        ),
    ),
    ("fullstack", re.compile(r"full[- ]?stack", re.IGNORECASE)),
    ("frontend", re.compile(r"front[- ]?end|frontend|\bui engineer\b|web develop", re.IGNORECASE)),
    ("backend", re.compile(r"back[- ]?end|backend|\bserver\b|\bapi\b|distributed", re.IGNORECASE)),
]


def classify_role_family(title: str) -> str:
    for family, pattern in ROLE_FAMILIES:
        if pattern.search(title):
            return family
    return "general_swe"
