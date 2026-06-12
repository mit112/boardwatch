"""Per-component breakdown for `show` and the 'why' summary for `top` (§2.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from boardwatch.rank.heuristic import Score

TITLE_WHY_THRESHOLD = 0.8


@dataclass(frozen=True)
class ExplanationRow:
    component: str
    raw: float | None
    weight: float
    weighted: float | None
    detail: str


def explain(score: Score) -> list[ExplanationRow]:
    return [
        ExplanationRow(
            component=name,
            raw=comp.value,
            weight=comp.weight,
            weighted=None if comp.value is None else comp.value * comp.weight,
            detail=comp.detail,
        )
        for name, comp in score.components.items()
    ]


def why_summary(score: Score, posted_at: datetime | None, now: datetime) -> str:
    parts: list[str] = []
    if score.components["skill_coverage"].value is not None:
        parts.append(f"covers {score.covered}/{score.posting_skill_count} skills")
    title = score.components["title_match"]
    if title.value is not None and title.value >= TITLE_WHY_THRESHOLD:
        parts.append("title")
    if posted_at is not None:
        parts.append(f"{max((now - posted_at).days, 0)}d")
    return " · ".join(parts) if parts else "no ranking signals"
