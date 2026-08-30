"""Partial scan-outage detector (unattended observability).

`is_systemic_scan_outage` only makes a run fatal when EVERY board fails
(`complete == 0 and unchanged == 0`). A provider block — Workday is the bulk of the
379-board fleet — can dark most of the boards while a handful of other providers still
complete. That is not systemic, so the run stays clean and the heartbeat fires green
while intake silently collapses. The intake-death detector (F4) cannot see it either:
the surviving boards still emit some net-new postings, so net-new is not zero.

This raises a SOFT, non-fatal alert when the failed fraction of a run's boards crosses
a threshold, so a majority-provider or IP-reputation outage lands in the run record and
the run line instead of hiding behind a green tick. It never sets `fatal`: a partial
outage is not a systemic one, and a false page on a transient timeout burst is worse
than a ticket the owner reads on the next review.
"""

from __future__ import annotations

# Fraction of a run's attempted boards that must fail before the alert fires. A healthy
# run fails on the order of 0-5% of boards to transient timeouts; half the fleet going
# dark is a provider block or an IP-reputation problem, not bad luck.
SCAN_OUTAGE_FAIL_RATIO = 0.5


def scan_outage_alert(
    boards_attempted: int,
    boards_failed: int,
    *,
    ratio: float = SCAN_OUTAGE_FAIL_RATIO,
) -> str | None:
    """Return a soft-alert string when at least `ratio` of a run's attempted boards
    failed, else ``None``.

    Returns ``None`` when no boards were attempted — a lane-only or `--no-scan` run
    carries no board-outage signal and must not divide by zero.
    """
    if boards_attempted <= 0:
        return None
    if boards_failed < ratio * boards_attempted:
        return None
    pct = round(100 * boards_failed / boards_attempted)
    return (
        f"scan: {boards_failed} of {boards_attempted} boards failed ({pct}%) — "
        f"a provider or this IP may be blocked; intake is collapsing without going systemic"
    )
