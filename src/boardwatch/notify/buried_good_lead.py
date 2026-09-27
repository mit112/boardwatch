"""Buried-good-lead detector (unattended observability).

The final gate judges `gate.depth` leads a run and only `--top` are delivered, so a posting the
judge cleared — `eligible`, seniority fit `yes` — can rank below the cut every run until its
requisition comes down. Nothing else sees that: the lead was never delivered, so no delivery or
lane detector counts it, and its closing is an ordinary scan event. Measured 2026-09-26: 6 such
postings closed over runs 43-480 with no signal anywhere.

A SOFT alert when at least one judge-cleared, never-built posting closed since the previous
pipeline run — either closed count grew (the current-key one, or the one cleared only under an
older judge key and never re-judged), i.e. a good job was lost this run. The two are named apart.
Growth is read off `closed_at` rather than off a count stored by the previous run, so a re-judge or
a sibling build that shrinks the population cannot mask a loss in the same run, and no new column
is needed.

**"The previous pipeline run" is the newest earlier run with `corpus_open` set, whatever its
status.** A manual `scan`, `eligibility` or `tailor` mints an `ok` run row too (`ensure_run`), and
anchoring on it would silently skip every closure between the two runs; only the funnel writer
stamps `corpus_open` (`record_corpus_counts`, D-371), in the same read block as the buried
population, so a run carrying it reached this alert. A FAILED pipeline run carries it as well and
also ran this alert (the finalize chain runs on both outcomes), so anchoring on it keeps a closure
it already reported from being reported again. The one gap: a funnel that raised after stamping
the corpus leaves that run's alert abstaining and its closures unreported — a double fault the
funnel's own failure alert already names.

It never sets `fatal`: the run succeeded, and the loss is a ranking outcome to look at, not a
fault that should trip the dead-man's switch.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from boardwatch.store.buried_queries import BuriedLeads
from boardwatch.store.tables import runs


def check_buried_good_lead(
    engine: Engine, buried: BuriedLeads | None, *, run_id: int
) -> str | None:
    """Return a soft-alert string when a posting in `buried` — the population this run's funnel
    read — closed after the previous pipeline run before `run_id` finished, else ``None``.

    `buried` is `None` when the funnel was not collected, and the check abstains: the read is a
    full scan of the gate rows, so it is taken once, by the funnel, and not repeated here. No
    earlier pipeline run abstains too: on a fresh store "since the previous run" is all of
    history, and reporting every past closure as this run's loss would be a false alarm.
    """
    if buried is None:
        return None
    with engine.connect() as conn:
        since = conn.execute(
            select(runs.c.finished_at)
            .where(runs.c.corpus_open.is_not(None), runs.c.id < run_id)
            .order_by(runs.c.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if since is None:
        return None
    lost = sorted(pid for pid, closed_at in buried.closed.items() if closed_at > since)
    stale_lost = sorted(pid for pid, closed_at in buried.stale_closed.items() if closed_at > since)
    if not lost and not stale_lost:
        return None
    parts = []
    if lost:
        parts.append(
            f"{len(lost)} judge-cleared lead(s) closed since the previous pipeline run without "
            f"ever being delivered (posting {_ids(lost)}) — {len(buried.open)} more are eligible, "
            f"seniority-fit and still open below the delivery cut"
        )
    if stale_lost:
        parts.append(
            f"{len(stale_lost)} lead(s) cleared under an older judge key and never re-judged "
            f"closed since the previous pipeline run (posting {_ids(stale_lost)}) — "
            f"{len(buried.stale_open)} more are still open"
        )
    return "buried: " + "; ".join(parts)


def _ids(posting_ids: list[int]) -> str:
    return ", ".join(str(pid) for pid in posting_ids)
