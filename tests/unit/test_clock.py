from datetime import UTC, datetime, timedelta, timezone

from boardwatch.core.clock import to_naive_utc, utcnow


def test_utcnow_is_naive_utc() -> None:
    now = utcnow()
    assert now.tzinfo is None
    assert abs((datetime.now(UTC).replace(tzinfo=None) - now).total_seconds()) < 5


def test_to_naive_utc_converts_aware_datetimes() -> None:
    aware = datetime(2026, 6, 11, 9, 30, tzinfo=timezone(timedelta(hours=-4)))
    assert to_naive_utc(aware) == datetime(2026, 6, 11, 13, 30)


def test_to_naive_utc_passes_naive_through() -> None:
    naive = datetime(2026, 6, 12, 0, 0)
    assert to_naive_utc(naive) is naive
