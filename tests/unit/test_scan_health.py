"""Scan-health soft-alert detectors. Each firing test names the wrong-version it rejects."""

from boardwatch.notify.scan_health import (
    SCAN_OUTAGE_FAIL_RATIO,
    degraded_scan_alert,
    scan_outage_alert,
)


def test_fires_at_exactly_the_threshold_fraction() -> None:
    # Rejects `<` -> `<=` on the fraction test, which would treat exactly-half as below.
    alert = scan_outage_alert(100, 50)
    assert alert is not None
    assert "50 of 100" in alert
    assert "50%" in alert


def test_fires_when_most_of_the_fleet_is_dark() -> None:
    alert = scan_outage_alert(379, 350)
    assert alert is not None
    assert "350 of 379" in alert


def test_silent_just_below_the_threshold() -> None:
    assert scan_outage_alert(100, 49) is None


def test_silent_on_a_healthy_run() -> None:
    # Rejects a version that fires on the normal 0-5% transient failure rate.
    assert scan_outage_alert(379, 5) is None


def test_silent_when_no_boards_were_attempted() -> None:
    # Rejects dropping the `boards_attempted <= 0` guard: 0 failed of 0 attempted would
    # otherwise satisfy `0 < 0.5*0 == 0` as False and fire on every lane-only run.
    assert scan_outage_alert(0, 0) is None


def test_threshold_default_is_half() -> None:
    assert SCAN_OUTAGE_FAIL_RATIO == 0.5
    # Behavioural pin at the default: 189/379 is below half and silent, 190/379 fires.
    assert scan_outage_alert(379, 189) is None
    assert scan_outage_alert(379, 190) is not None


# --- degraded_scan_alert: every board that returned anything returned `partial` -------------


def test_degraded_fires_on_the_partial_only_shape() -> None:
    # Runs 23/26/31/36/37's shape. Rejects a version wired to `partial >= boards_attempted`,
    # which would go quiet the moment one board failed alongside the partial one.
    alert = degraded_scan_alert(1, 0, 0, 1)
    assert alert is not None
    assert "1 of 1" in alert


def test_degraded_still_fires_when_other_boards_FAILED_outright() -> None:  # noqa: N802
    # The sibling ratio alert covers the failures; this one covers the incompleteness. Both
    # are true at once here, and neither is a reason to silence the other.
    assert degraded_scan_alert(4, 0, 0, 1) is not None


def test_degraded_silent_when_any_board_completed() -> None:
    # Rejects dropping the `boards_complete > 0` clause: a healthy scan with one Workday
    # board back partial is the MODAL live shape (c=123 p=25 u=139) and must never alert.
    assert degraded_scan_alert(2, 1, 0, 1) is None


def test_degraded_silent_when_any_board_was_unchanged() -> None:
    # Rejects dropping the `boards_unchanged > 0` clause. Unchanged is a complete listing
    # the fetch was able to skip, so the run's view of that board is not incomplete.
    assert degraded_scan_alert(2, 0, 1, 1) is None


def test_degraded_silent_on_the_genuine_outage_it_must_not_speak_for() -> None:
    # Zero usable evidence is still FATAL (is_systemic_scan_outage). A soft alert here would
    # read as "degraded" on a run that was refused outright.
    assert degraded_scan_alert(1, 0, 0, 0) is None


def test_degraded_silent_when_no_boards_were_attempted() -> None:
    # Rejects dropping the `boards_attempted <= 0` guard: a `--no-scan` or lane-only run
    # carries no board signal and must not read as a degraded scan.
    assert degraded_scan_alert(0, 0, 0, 0) is None
