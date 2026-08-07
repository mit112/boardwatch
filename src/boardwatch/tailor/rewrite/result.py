"""`RewriteRow`/`TierBResult`, split out of `lane.py` (P4 item 3a) so the résumé-wide
verb-diversity post-pass (`verb_diversity.py`) can consume and produce a `TierBResult`
without a circular import: `lane.py` calls `verb_diversity.enforce_verb_diversity`, so
the result types cannot live in `lane.py` if `verb_diversity.py` also needs them.
`lane.py` re-imports both names so every existing `from
boardwatch.tailor.rewrite.lane import TierBResult` call site keeps working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardwatch.tailor.plan import Rewrite


@dataclass(frozen=True)
class RewriteRow:
    bullet_id: str
    entry_id: str
    a_text: str
    b_text: str
    filter_pass: bool
    judge_verdict: str | None
    kept: bool
    drop_reason: str | None


@dataclass(frozen=True)
class TierBResult:
    accepted: list[Rewrite]
    rows: list[RewriteRow]
    calls_made: int
