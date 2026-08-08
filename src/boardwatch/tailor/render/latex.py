from __future__ import annotations

import re

# A single regex alternation, applied in ONE pass, so a replacement's own characters are
# never re-scanned and rule ORDER does not matter. (Sequential str.replace is broken here.)
_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
    ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
    ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
)
_ESC_MAP = dict(_ESCAPES)
_ESC_RE = re.compile("|".join(re.escape(k) for k, _ in _ESCAPES))


def escape(s: str) -> str:
    """Collapse whitespace to single spaces (matches the frozen single-line invariant), normalize
    en/em dashes to the LaTeX en-dash `--`, then escape every LaTeX special in ONE pass so tectonic
    compiles the payload verbatim as text.

    Dash normalization is the SINGLE site for it (re-review 2 blocker): model dates/headings carry
    `–`/`—` while the emitter asserts `--`; do it here, not a second time in `_subheading`. `-` is
    not a LaTeX special, so `--` passes through untouched. Note the roundtrip `unescape(escape(x))`
    therefore only returns `x` for dash-free `x` (dash normalization is intentionally lossy — the
    no-fabrication belt in `validate_layout` and the model-level `output_is_entailed` both compare
    escaped-vs-escaped or model-vs-model, so this never masks a fabrication)."""
    collapsed = " ".join(s.split()).replace("—", "--").replace("–", "--")
    return _ESC_RE.sub(lambda m: _ESC_MAP[m.group()], collapsed)


def unescape(s: str) -> str:
    """Inverse of `escape` for `parse_bullets`. Longest replacement first so `\textbackslash{}`
    / `\textasciitilde{}` / `\textasciicircum{}` are restored before the 2-char rules can touch
    their inner braces."""
    out = s
    for raw, esc in sorted(_ESCAPES, key=lambda p: -len(p[1])):
        out = out.replace(esc, raw)
    return out
