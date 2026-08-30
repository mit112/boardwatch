"""Cross-run intake-death detector (F4).

The green heartbeat fires whenever a run reaches a clean outcome, so a pipeline that
scans successfully but stops finding ANY new postings — a dead board fleet, a silent
fetch regression, an upstream that has gone quiet — pages nobody: every run looks
identical to a healthy one. This detector reads the per-run net-new count the scan
stage already persists (`runs.new_count`) and raises a SOFT, non-fatal alert when a
window of scanning runs in a row all found zero new postings.

It is deliberately a slow-burn signal, not a page. The alert is appended to
`summary.errors` (reprinted by the CLI, persisted to `runs.errors_json`) and the
detector NEVER sets `summary.fatal`: the run itself succeeded, so the heartbeat must
still fire — an intake stall tickets, it does not trip the dead-man's switch.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from boardwatch.store.tables import runs

# Consecutive SCANNING runs (a recorded `new_count`) that must all read zero net-new
# before the detector fires. Three guards against a single quiet run — new-posting
# rate is a fetch-budget artifact and one empty run is not death — while still
# catching a real stall within a few daily ticks.
INTAKE_DEATH_WINDOW = 3


def check_intake_death(engine: Engine, *, window: int = INTAKE_DEATH_WINDOW) -> str | None:
    """Return a soft-alert string when the last `window` scanning runs all found zero
    net-new postings, else ``None``.

    Only runs whose scan stage recorded a count are considered. ``new_count IS NULL``
    marks a run whose scan never ran — a ``top --no-record`` phantom, or a run that
    aborted before scanning — and such a run carries no intake signal, so it is
    skipped rather than counted as a zero. Fewer than ``window`` qualifying runs means
    there is not yet enough history to judge, so the detector abstains (returns
    ``None``) instead of firing on a fresh store.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(runs.c.id, runs.c.new_count)
            .where(runs.c.new_count.is_not(None))
            .order_by(runs.c.id.desc())
            .limit(window)
        ).all()
    if len(rows) < window:
        return None
    if any(new_count != 0 for _, new_count in rows):
        return None
    run_ids = ", ".join(str(run_id) for run_id, _ in rows)
    return (
        f"intake: 0 net-new postings across the last {window} scanning runs "
        f"(runs {run_ids}) — the board fleet may be dead or a fetch regression is silent"
    )
