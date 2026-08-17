"""Surgical edits to FIXTURE_PROVENANCE's source.

Pure string-in / string-out, so the rewrite is testable without touching the filesystem and
the caller owns the atomic replace.

Every edit is anchored on a literal this module also OWNS the formatting of, and a missing
anchor raises rather than falling through to a no-op. A rewriter that silently changes nothing
is the failure that matters here: it would report success, leave a stale pin in place, and the
gate would keep passing against a fixture nobody re-reviewed.
"""

from __future__ import annotations

from datetime import date

PROVENANCE_MODULE = "tools/generalization/fixtures.py"

_ENTRY_CLOSE = "\n    ),\n"


class RewriteError(RuntimeError):
    """The source did not have the shape this rewriter requires, so nothing was changed."""


def _entry_span(text: str, provider: str) -> tuple[int, int]:
    key = f'    "{provider}": FixtureProvenance(\n'
    start = text.find(key)
    if start < 0:
        raise RewriteError(f"no FIXTURE_PROVENANCE entry for {provider!r} in {PROVENANCE_MODULE}")
    close = text.find(_ENTRY_CLOSE, start)
    if close < 0:
        raise RewriteError(f"the {provider!r} entry is not closed in the expected layout")
    return start, close + len(_ENTRY_CLOSE)


def _replace_once(block: str, prefix: str, suffix: str, value: str, where: str) -> str:
    """Replace the single `prefix<...>suffix` run inside `block`."""
    start = block.find(prefix)
    if start < 0:
        raise RewriteError(f"no {prefix!r} in {where}")
    if block.find(prefix, start + 1) >= 0:
        raise RewriteError(
            f"{prefix!r} appears more than once in {where}, so the target is ambiguous"
        )
    end = block.find(suffix, start + len(prefix))
    if end < 0:
        raise RewriteError(f"unterminated {prefix!r} in {where}")
    return block[:start] + prefix + value + block[end:]


def record_pins(text: str, *, readmes: dict[str, str], corpus_pin: str, rows: int) -> str:
    """Set every README pin, the corpus pin and the corpus row count to measured values."""
    for provider, digest in sorted(readmes.items()):
        start, end = _entry_span(text, provider)
        block = _replace_once(
            text[start:end],
            'readme_pin="sha256:',
            '"',
            digest,
            f"the {provider!r} entry",
        )
        text = text[:start] + block + text[end:]
    text = _replace_once(
        text, 'CORPUS_PIN = "sha256:', '"', corpus_pin, PROVENANCE_MODULE
    )
    return _replace_once(text, "CORPUS_ROWS = ", "\n", str(rows), PROVENANCE_MODULE)


def extend_deadline(
    text: str, *, provider: str, on: date, reason: str, new_review_by: date
) -> str:
    """Push one review deadline out and append the dated, reasoned rollover that justifies it.

    The extension is appended rather than replacing the previous one on purpose: the count of
    rollovers is the signal. A capture on its fourth extension is a different fact from a
    capture on its first, and overwriting would erase exactly that.
    """
    if not reason.strip():
        raise RewriteError("an extension needs a non-empty reason")
    if '"' in reason or "\\" in reason:
        raise RewriteError('a reason may not contain a quote or a backslash')
    start, end = _entry_span(text, provider)
    block = _replace_once(
        text[start:end],
        "review_by=date(",
        ")",
        f"{new_review_by.year}, {new_review_by.month}, {new_review_by.day}",
        f"the {provider!r} entry",
    )
    entry = f'            Extension(on=date({on.year}, {on.month}, {on.day}), reason="{reason}"),\n'
    if "extensions=(" in block:
        anchor = block.find("extensions=(\n")
        if anchor < 0:
            raise RewriteError(
                f"the {provider!r} entry has a single-line extensions tuple; this rewriter "
                "only appends to the multi-line layout it writes"
            )
        insert = block.find("        ),\n", anchor)
        if insert < 0:
            raise RewriteError(f"the {provider!r} extensions tuple is not closed as expected")
        block = block[:insert] + entry + block[insert:]
    else:
        tail = block.rfind("\n    ),\n")
        block = block[:tail] + "\n        extensions=(\n" + entry + "        ),"  + block[tail:]
    return text[:start] + block + text[end:]
