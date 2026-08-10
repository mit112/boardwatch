"""P6 slice 2: the decision ledger's pure core (design §2.2, §2.3, §8 claims 1-5)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from boardwatch.core.ledger import (
    DISPOSITIONS,
    PERMANENT_DISPOSITIONS,
    REASON_NAMES,
    LedgerRow,
    MalformedDisposition,
    UnknownDisposition,
    UnknownDispositionReason,
    is_live,
    plan_upsert,
    rank,
    validate,
)

NOW = datetime(2026, 8, 10, 12, 0, 0)
POLICY = "policy-abc"


def _seen(now: datetime = NOW, *, ttl_days: int = 7, reopened: datetime | None = None) -> LedgerRow:
    return LedgerRow(
        disposition="seen",
        reason="surfaced",
        policy_version=None,
        expires_at=now + timedelta(days=ttl_days),
        reopened_at=reopened,
        first_decided_at=now,
        decided_at=now,
    )


def _built(now: datetime = NOW, *, reopened: datetime | None = None) -> LedgerRow:
    return LedgerRow(
        disposition="built",
        reason="lead_built",
        policy_version=POLICY,
        expires_at=None,
        reopened_at=reopened,
        first_decided_at=now,
        decided_at=now,
    )


def test_rank_order_is_seen_then_skipped_then_built() -> None:
    assert rank("seen") < rank("skipped") < rank("built")
    assert DISPOSITIONS == ("seen", "skipped", "built")


def test_unknown_disposition_is_typed_not_a_bare_valueerror() -> None:
    with pytest.raises(UnknownDisposition) as exc:
        rank("dismissed")
    assert exc.value.disposition == "dismissed"


def test_reason_must_be_catalogued_for_its_own_disposition() -> None:
    """`lead_built` is a real reason, but not a reason a `seen` row may carry."""
    validate("built", "lead_built")
    with pytest.raises(UnknownDispositionReason):
        validate("seen", "lead_built")


def test_reason_names_covers_every_disposition_reason() -> None:
    """The store's CHECK is built from REASON_NAMES; a reason missing from it would be rejected
    at INSERT while passing `validate`."""
    assert set(REASON_NAMES) == {"lead_built", "surfaced", "unshippable_artifact"}


# ---------------------------------------------------------------- is_live (claim 4)


def test_a_seen_row_is_live_until_its_expiry_and_not_after() -> None:
    row = _seen()
    assert is_live(expires_at=row.expires_at, reopened_at=None, now=NOW)
    assert is_live(expires_at=row.expires_at, reopened_at=None, now=NOW + timedelta(days=6))
    assert not is_live(expires_at=row.expires_at, reopened_at=None, now=NOW + timedelta(days=8))


def test_a_permanent_row_never_expires() -> None:
    assert is_live(expires_at=None, reopened_at=None, now=NOW + timedelta(days=3650))


def test_a_reopened_row_is_not_live_even_though_it_never_expires() -> None:
    """The drain releases a permanent disposition without a DELETE, so the row survives."""
    assert not is_live(expires_at=None, reopened_at=NOW, now=NOW)


# ------------------------------------------------- monotonicity (claims 1, 2, 3)


def test_built_then_seen_holds_at_built_and_writes_nothing() -> None:
    """The rule that matters: a lead already built is never downgraded to merely surfaced."""
    planned = plan_upsert(
        _built(),
        disposition="seen",
        reason="surfaced",
        policy_version=None,
        expires_at=NOW + timedelta(days=7),
        now=NOW + timedelta(hours=1),
    )
    assert planned is None


def test_seen_then_built_raises_the_rank_and_keeps_first_decided_at() -> None:
    existing = _seen()
    later = NOW + timedelta(days=1)
    planned = plan_upsert(
        existing,
        disposition="built",
        reason="lead_built",
        policy_version=POLICY,
        expires_at=None,
        now=later,
    )
    assert planned is not None
    assert planned.disposition == "built"
    assert planned.expires_at is None
    assert planned.policy_version == POLICY
    assert planned.first_decided_at == existing.first_decided_at
    assert planned.decided_at == later


def test_re_recording_seen_on_a_live_seen_row_pushes_the_ttl_out() -> None:
    """The one case that reads like a monotonicity breach and is not (design §2.3): the rank is
    held, only the expiry moves."""
    existing = _seen()
    later = NOW + timedelta(days=2)
    planned = plan_upsert(
        existing,
        disposition="seen",
        reason="surfaced",
        policy_version=None,
        expires_at=later + timedelta(days=7),
        now=later,
    )
    assert planned is not None
    assert planned.disposition == "seen"
    assert planned.expires_at is not None
    assert existing.expires_at is not None
    assert planned.expires_at > existing.expires_at
    assert planned.first_decided_at == existing.first_decided_at


def test_an_expired_row_is_absent_to_the_writer_so_any_disposition_may_follow() -> None:
    """The writer applies the SAME liveness predicate as the reader. If it did not, an expired
    `built` row would be hidden from the reader and still block the writer — a job that can
    never be surfaced again."""
    after_expiry = NOW + timedelta(days=30)
    planned = plan_upsert(
        _seen(),
        disposition="seen",
        reason="surfaced",
        policy_version=None,
        expires_at=after_expiry + timedelta(days=7),
        now=after_expiry,
    )
    assert planned is not None
    assert planned.first_decided_at == NOW  # the first decision ever, not of this lifetime


def test_a_reopened_built_row_accepts_a_lower_disposition_again() -> None:
    """What the drain buys: after `reopen`, the job re-enters and may be merely surfaced."""
    planned = plan_upsert(
        _built(reopened=NOW),
        disposition="seen",
        reason="surfaced",
        policy_version=None,
        expires_at=NOW + timedelta(days=7),
        now=NOW,
    )
    assert planned is not None
    assert planned.disposition == "seen"
    assert planned.reopened_at is None  # the new decision is live


def test_first_ever_decision_inserts_as_itself() -> None:
    planned = plan_upsert(
        None,
        disposition="built",
        reason="lead_built",
        policy_version=POLICY,
        expires_at=None,
        now=NOW,
    )
    assert planned is not None
    assert planned.first_decided_at == NOW == planned.decided_at


# --------------------------------------------------------- well-formedness (claim 5)


@pytest.mark.parametrize("disposition", sorted(PERMANENT_DISPOSITIONS))
def test_a_permanent_disposition_needs_a_policy_stamp(disposition: str) -> None:
    reason = "lead_built" if disposition == "built" else "unshippable_artifact"
    with pytest.raises(MalformedDisposition):
        plan_upsert(
            None,
            disposition=disposition,
            reason=reason,
            policy_version=None,
            expires_at=None,
            now=NOW,
        )


@pytest.mark.parametrize("disposition", sorted(PERMANENT_DISPOSITIONS))
def test_a_permanent_disposition_may_not_carry_a_ttl(disposition: str) -> None:
    reason = "lead_built" if disposition == "built" else "unshippable_artifact"
    with pytest.raises(MalformedDisposition):
        plan_upsert(
            None,
            disposition=disposition,
            reason=reason,
            policy_version=POLICY,
            expires_at=NOW + timedelta(days=1),
            now=NOW,
        )


def test_seen_needs_a_ttl_and_may_not_carry_a_policy_stamp() -> None:
    with pytest.raises(MalformedDisposition):
        plan_upsert(
            None,
            disposition="seen",
            reason="surfaced",
            policy_version=None,
            expires_at=None,
            now=NOW,
        )
    with pytest.raises(MalformedDisposition):
        plan_upsert(
            None,
            disposition="seen",
            reason="surfaced",
            policy_version=POLICY,
            expires_at=NOW + timedelta(days=1),
            now=NOW,
        )
