"""Budgeted D-659 recovery. HTTP is strictly between short store transactions."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from sqlalchemy import Engine, select

from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardRequest, RawPosting, ResponseValidators
from boardwatch.core.normalize import content_hash
from boardwatch.core.politeness import Fetcher, FetchFailure, FetchResult
from boardwatch.core.posting_identity import compute_identities
from boardwatch.core.settings import Settings
from boardwatch.lanes.dereference import PostingTarget, parse_posting_target
from boardwatch.lanes.quality import is_employer_body
from boardwatch.providers.base import (
    PostingRefetcher,
    Provider,
    RefetchUnsupported,
    posting_refetcher,
    supports_employer_body_recovery,
)
from boardwatch.providers.registry import build_providers
from boardwatch.store.body_revision import record_body_revision
from boardwatch.store.db import write_connection
from boardwatch.store.employer_body_queries import EMPLOYER_BODY_PENDING, pending_employer_bodies
from boardwatch.store.identity_queries import load_identity_inputs, write_identities
from boardwatch.store.quarantine_queries import drain_quarantine, record_quarantine, sweep_bodies
from boardwatch.store.sources import record_version_source
from boardwatch.store.tables import quarantined_bodies


class RecoveryOutcome(StrEnum):
    RECOVERED = "recovered"
    UNAVAILABLE = "unavailable"
    REFUSED = "refused"
    UNSUPPORTED = "unsupported"
    WRONG_IDENTITY = "wrong_identity"
    EMPTY_OR_FOREIGN = "empty_or_foreign"
    BUDGET = "budget_exhausted"
    SUPERSEDED = "superseded"
    UNRECOVERABLE_STUB = "unrecoverable_stub"


class RecoveryCounts(Counter[RecoveryOutcome]):
    """Typed outcomes plus the provider breakdown of stubs deliberately left unheld."""

    def __init__(self) -> None:
        super().__init__()
        self.unrecoverable_stubs: Counter[str] = Counter()


class EmployerIdentityMismatch(ValueError):
    """The provider answered for a different posting or employer."""


class RecoveryBudgetExhausted(FetchFailure):
    """An employer refetch requested another read after spending its originating lane's cap."""


class _RecoveryFetcher(Fetcher):
    # Reserve one slot per candidate, including unsupported/failed candidates. The first
    # request spends that reservation; additional provider bootstrap/detail reads spend more.
    remaining: int = 0
    reserved: bool = False

    def _dispatch(
        self, method: str, url: str, validators: ResponseValidators | None,
        json_body: dict[str, Any] | None, headers: Mapping[str, str] | None,
        min_host_delay: float | None = None,
    ) -> FetchResult:
        if self.reserved:
            self.reserved = False
        elif self.remaining > 0:
            self.remaining -= 1
        else:
            raise RecoveryBudgetExhausted("employer read budget exhausted")
        return super()._dispatch(method, url, validators, json_body, headers, min_host_delay)


def _read(fetcher: Fetcher, provider: Provider, target: PostingTarget) -> RawPosting | None:
    if not supports_employer_body_recovery(provider):
        raise RefetchUnsupported(f"no employer body recovery for {provider.name}")
    if isinstance(provider, PostingRefetcher):
        return posting_refetcher(provider).fetch_posting(fetcher, target.slug, target.posting_ref)
    # The shared support predicate admits only the implemented one-board fallbacks here.
    snapshot = provider.fetch_board(fetcher, BoardRequest(
        provider=target.provider, slug=target.slug, url=provider.board_url(target.slug),
    ))
    if snapshot.status not in {"complete", "partial"}:
        raise FetchFailure("employer board could not be read") from None
    return next((raw for raw in snapshot.postings
                 if raw.provider_posting_id == target.posting_ref), None)


def recover_employer_bodies(
    engine: Engine, settings: Settings, run_id: int, *, spent: Mapping[str, int],
) -> RecoveryCounts:
    """Retry oldest pending first on EVERY run, including when discovery lanes are disabled.

    Budget is per originating lane, using lane_posting_budget. `spent` is a conservative
    upper bound on its discovery reads (a board can account for multiple hits). Failed and
    unsupported attempts consume a slot too. Retried rows rotate to the back of the queue;
    budget-deferred rows retain their age. No verdict is an input to recovery.
    """
    counts = RecoveryCounts()
    with write_connection(engine) as conn, conn.begin():
        sweep_bodies(conn, now=utcnow(), run_id=run_id)
        pending = list(pending_employer_bodies(
            conn, unrecoverable=counts.unrecoverable_stubs,
        ).values())
        if counts.unrecoverable_stubs:
            counts[RecoveryOutcome.UNRECOVERABLE_STUB] = sum(counts.unrecoverable_stubs.values())
        # Support can disappear without a body revision; release those holds even with no work.
        drain_quarantine(conn, now=utcnow())
        age = {int(row.posting_version_id): row.quarantined_at for row in conn.execute(
            select(quarantined_bodies).where(quarantined_bodies.c.reopened_at.is_(None))
        )}
    if not pending:
        return counts
    pending.sort(key=lambda item: (
        age.get(item.posting_version_id, item.captured_at), item.posting_version_id,
    ))
    remaining = {
        item.lane: max(0, settings.lane_posting_budget - spent.get(item.lane, 0))
        for item in pending
    }
    providers = build_providers()
    fetcher = _RecoveryFetcher(settings)  # identifying UA and the existing shared host pacing
    for item in pending:
        if remaining[item.lane] <= 0:
            counts[RecoveryOutcome.BUDGET] += 1
            continue
        remaining[item.lane] -= 1
        fetcher.remaining = remaining[item.lane]
        fetcher.reserved = True
        with write_connection(engine) as conn, conn.begin():
            record_quarantine(conn, posting_version_id=item.posting_version_id,
                              posting_id=item.posting_id,
                              markers=[EMPLOYER_BODY_PENDING, item.employer_url, item.lane],
                              now=utcnow(), run_id=run_id)
        try:
            target = item.target()
        except ValueError:
            counts[RecoveryOutcome.UNSUPPORTED] += 1
            continue
        try:
            provider = providers.get(target.provider)
            if provider is None:
                raise RefetchUnsupported(f"no provider for {target.provider}")
            raw = _read(fetcher, provider, target)
            if raw is None or not raw.body_text.strip() or not is_employer_body(raw.body_text):
                counts[RecoveryOutcome.EMPTY_OR_FOREIGN] += 1
                continue
            try:
                returned = parse_posting_target(raw.url or "")
            except ValueError as exc:
                raise EmployerIdentityMismatch("returned URL has no posting identity") from exc
            if raw.provider_posting_id != target.posting_ref or returned != target:
                raise EmployerIdentityMismatch("returned posting differs from the evidenced URL")
        except RecoveryBudgetExhausted:
            counts[RecoveryOutcome.BUDGET] += 1
            continue
        except RefetchUnsupported:
            counts[RecoveryOutcome.UNSUPPORTED] += 1
            continue
        except EmployerIdentityMismatch:
            counts[RecoveryOutcome.WRONG_IDENTITY] += 1
            continue
        except FetchFailure as exc:
            counts[RecoveryOutcome.REFUSED if exc.status_code in {401, 403}
                   else RecoveryOutcome.UNAVAILABLE] += 1
            continue
        except Exception:  # noqa: BLE001 - per-copy isolation; no fallback to the old verdict
            counts[RecoveryOutcome.UNAVAILABLE] += 1
            continue
        finally:
            remaining[item.lane] = fetcher.remaining
        with write_connection(engine) as conn, conn.begin():
            # Recheck after HTTP: a board scan or evidence update may have superseded the copy.
            current = pending_employer_bodies(conn, posting_id=item.posting_id)
            if current.get(item.posting_version_id) != item:
                counts[RecoveryOutcome.SUPERSEDED] += 1
                continue
            now = utcnow()
            digest = content_hash(raw.body_text)
            vid = record_body_revision(conn, posting_id=item.posting_id, body_text=raw.body_text,
                                       content_hash=digest, captured_at=now)
            record_version_source(conn, posting_version_id=vid, run_id=run_id,
                                  source_url=item.employer_url, source_record_id=target.posting_ref,
                                  observed_at=now, payload_hash=digest)
            for inputs in load_identity_inputs(conn, [item.posting_id]):
                write_identities(conn, item.posting_id, compute_identities(inputs), now=now)
        counts[RecoveryOutcome.RECOVERED] += 1
    with write_connection(engine) as conn, conn.begin():
        drain_quarantine(conn, now=utcnow())
    return counts


def recovery_errors(counts: RecoveryCounts) -> list[str]:
    """One counted run diagnostic; the successful revisions have immutable source rows."""
    failures = [
        f"{key.value}={value}" for key, value in counts.items()
        if key not in {RecoveryOutcome.RECOVERED, RecoveryOutcome.UNRECOVERABLE_STUB} and value
    ]
    failures.extend(f"unrecoverable_stub[{provider}]={value}"
                    for provider, value in sorted(counts.unrecoverable_stubs.items()) if value)
    if not failures:
        return []
    return ["employer body recovery: " + ", ".join(failures)]
