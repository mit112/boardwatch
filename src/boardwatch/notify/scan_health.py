"""Scan-health detectors (unattended observability).

`is_systemic_scan_outage` only makes a run fatal when EVERY board fails outright
(`complete == 0 and unchanged == 0 and partial == 0`). Two shapes sit below that line and
would otherwise pass for healthy; one soft detector each, neither ever setting `fatal`.

`scan_outage_alert` — most of the fleet failed while a few boards completed. A provider
block (Workday is the bulk of the 379-board fleet) or an IP-reputation problem can dark the
majority, which is not systemic, so the run stays clean and the heartbeat fires green while
intake silently collapses. The intake-death detector (F4) cannot see it either: the
surviving boards still emit some net-new postings, so net-new is not zero. Fires on the
failed FRACTION crossing a threshold. A false page on a transient timeout burst is worse
than a ticket the owner reads on the next review, hence soft.

`degraded_scan_alert` — every board that returned anything returned `partial`. That state
WAS fatal, wrongly: a `partial` board holds real postings, so the run has usable evidence
and is degraded success (owner ruling, 2026-09-20). Narrowing the fatal predicate is what
makes this detector necessary — the run is no longer refused, so something must still say
the listings it acted on were incomplete.
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


def degraded_scan_alert(
    boards_attempted: int,
    boards_complete: int,
    boards_unchanged: int,
    boards_partial: int,
) -> str | None:
    """Return a soft-alert string when a scan produced usable postings but NOT ONE board came
    back clean — `complete == 0 and unchanged == 0 and partial > 0` — else ``None``.

    This is the state the outage predicate used to call fatal. It is degraded success: every
    `partial` board holds real postings, so the run has evidence in hand and the silent empty
    day cannot be what happened. But a run that stops being fatal must not become silent, and
    nothing else observes this shape — the `boards_failed` ratio alert cannot see it (no board
    failed) and intake death cannot (postings arrived). Non-fatal, like every detector here.

    Returns ``None`` when no boards were attempted — a lane-only or `--no-scan` run carries no
    board signal at all, and `--no-scan` must not read as a degraded scan.
    """
    if boards_attempted <= 0:
        return None
    if boards_complete > 0 or boards_unchanged > 0 or boards_partial <= 0:
        return None
    return (
        f"scan degraded: {boards_partial} of {boards_attempted} boards returned PARTIAL "
        f"listings and not one came back complete or unchanged — the postings this run "
        f"holds are incomplete, so treat its closures and net-new as understated"
    )
