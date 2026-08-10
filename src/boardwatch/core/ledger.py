"""The durable decision ledger's pure core (P6 slice 2, design §2).

Pure: no DB, no I/O, no clock — `now` is always passed in. That is the axis on which the
production path (a stored row) and any verification path differ, the same split `core/dedup.py`
draws for the same reason.

Two properties live here rather than at the call sites, because both have a failure mode that is
invisible when duplicated:

- **One liveness predicate, shared by the reader and the writer.** A reader that thinks a row is
  expired while the writer thinks it is live both hides a job and refuses to re-decide it, which
  is a job that can never be surfaced again. `is_live` is the only definition.
- **Monotonicity over the rank, not over the timestamp.** Re-recording `seen` on a live `seen`
  row refreshes its TTL. That is a held rank, not a downgrade — the one case that reads like a
  breach of the rule and is not (design §2.3).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

# Closed and ORDERED: the index is the rank. An upsert may raise the rank or hold it, never
# lower it. Adding a disposition is a catalog edit plus a migration, never a new bucket invented
# at a call site.
DISPOSITIONS: tuple[str, ...] = ("seen", "skipped", "built")

# `built`/`skipped` are permanent and carry a policy stamp; `seen` is TTL'd and carries none.
# The store repeats this as a CHECK constraint (one of three on the table), so a direct INSERT
# cannot violate it either. Note the DB checks the reason catalog FLAT, as a union: pairing a reason
# with the wrong disposition is caught here in Python and not by the constraint.
PERMANENT_DISPOSITIONS = frozenset({"skipped", "built"})

# Closed reason catalog, per disposition. Deliberately three reasons and not one per ranker
# filter: hard-filter, non-swe, ineligible, below-cutoff and duplicate drops are all recomputed
# deterministically every run and already counted in the funnel, so persisting them would be
# ~20,000 writes a run with no reader (design §2.3).
DISPOSITION_REASONS: dict[str, frozenset[str]] = {
    "seen": frozenset({"surfaced"}),
    "skipped": frozenset({"unshippable_artifact"}),
    "built": frozenset({"lead_built"}),
}

REASON_NAMES: tuple[str, ...] = tuple(
    sorted({reason for reasons in DISPOSITION_REASONS.values() for reason in reasons})
)


class UnknownDisposition(ValueError):
    """Typed at the raise site, so a bad disposition is never classified by string-matching."""

    def __init__(self, disposition: str) -> None:
        super().__init__(f"disposition not in catalog: {disposition!r}")
        self.disposition = disposition


class UnknownDispositionReason(ValueError):
    def __init__(self, disposition: str, reason: str) -> None:
        super().__init__(f"reason {reason!r} is not catalogued for disposition {disposition!r}")
        self.disposition = disposition
        self.reason = reason


class MalformedDisposition(ValueError):
    """A permanent disposition with no policy stamp, or a TTL on the wrong tier."""


@dataclass(frozen=True)
class LedgerRow:
    """One job's current decision.

    Not an append-only event: the spec asks for *upserts*, and an append-only log cannot be
    upserted. The append-only trail exists where it is actually needed — `job_grouping_events`,
    the half that mutates a key another table reads (design §2.1).
    """

    disposition: str
    reason: str
    policy_version: str | None
    expires_at: datetime | None
    reopened_at: datetime | None
    first_decided_at: datetime
    decided_at: datetime


def rank(disposition: str) -> int:
    try:
        return DISPOSITIONS.index(disposition)
    except ValueError:
        raise UnknownDisposition(disposition) from None


def is_live(*, expires_at: datetime | None, reopened_at: datetime | None, now: datetime) -> bool:
    """Whether a stored row still governs.

    Lazy read-time expiry: nothing sweeps and nothing deletes, so an expired row stays on disk
    for the drain to report. `reopened_at` is how the drain releases a permanent disposition
    without a DELETE, so history survives being drained.

    Scalars rather than a row object, so the ORM row, `LedgerRow` and a test literal all reach
    the same definition.
    """
    if reopened_at is not None:
        return False
    return expires_at is None or expires_at > now


def validate(disposition: str, reason: str) -> None:
    """Raise unless the (disposition, reason) pair is in the closed catalog."""
    rank(disposition)  # raises UnknownDisposition
    if reason not in DISPOSITION_REASONS[disposition]:
        raise UnknownDispositionReason(disposition, reason)


def _assert_wellformed(
    disposition: str, policy_version: str | None, expires_at: datetime | None
) -> None:
    permanent = disposition in PERMANENT_DISPOSITIONS
    if permanent and (policy_version is None or expires_at is not None):
        raise MalformedDisposition(
            f"{disposition!r} is permanent: it needs a policy_version and no expires_at"
        )
    if not permanent and (expires_at is None or policy_version is not None):
        raise MalformedDisposition(
            f"{disposition!r} is TTL'd: it needs an expires_at and no policy_version"
        )


def plan_upsert(
    existing: LedgerRow | None,
    *,
    disposition: str,
    reason: str,
    policy_version: str | None,
    expires_at: datetime | None,
    now: datetime,
) -> LedgerRow | None:
    """The row to store, or `None` when a live row already outranks the incoming decision.

    `existing` is the raw stored row, live or not — this function applies `is_live` itself, so
    the writer cannot disagree with the reader about which rows still count.

    A non-live existing row is treated as **absent**: any disposition may be recorded over it,
    which is what makes an expiry or a reopen mean anything. `first_decided_at` survives that —
    it is the first decision ever taken for the job, not the first of the current lifetime.
    """
    validate(disposition, reason)
    _assert_wellformed(disposition, policy_version, expires_at)
    incoming = LedgerRow(
        disposition=disposition,
        reason=reason,
        policy_version=policy_version,
        expires_at=expires_at,
        reopened_at=None,
        first_decided_at=now,
        decided_at=now,
    )
    if existing is None:
        return incoming
    if not is_live(
        expires_at=existing.expires_at, reopened_at=existing.reopened_at, now=now
    ):
        return replace(incoming, first_decided_at=existing.first_decided_at)
    if rank(disposition) < rank(existing.disposition):
        return None
    # Equal rank still writes: re-recording `seen` on a live `seen` row pushes its TTL out, and a
    # held rank with a later expiry is not a downgrade (design §2.3).
    return replace(incoming, first_decided_at=existing.first_decided_at)
