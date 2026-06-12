"""Naive-UTC time convention at the storage boundary (plan Conventions)."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time as a naive UTC datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Convert any datetime (aware or naive) to naive UTC; naive input is assumed UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)
