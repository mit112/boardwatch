"""Partial scan-outage soft-alert detector. Each firing test names the wrong-version it rejects."""

from boardwatch.notify.scan_health import SCAN_OUTAGE_FAIL_RATIO, scan_outage_alert


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
