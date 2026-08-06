"""Run bookkeeping and small read queries.

insert_run commits immediately at scan start so the running scan's started_at
is queryable while it runs (§0.3 — the scan lock carries no holder metadata).
Run counts are derived conveniences; posting_events is the source of truth (§4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, Row, func, insert, select, tuple_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import ResponseValidators
from boardwatch.store.tables import (
    board_scans,
    companies,
    http_cache,
    posting_versions,
    postings,
    profile,
    runs,
)

# An alias so the "no newer version exists" correlated EXISTS can compare a row against
# its own table. The pattern mirrors extract/preflight.py:63-81, which finds every
# missing row with ONE set-oriented correlated EXISTS rather than a per-row lookup.
_pv = posting_versions.alias("pv_current")

# The closed catalog of run outcomes (P0 item 4). Out-of-catalog is a failure, never a new
# bucket, so the setter raises rather than writing an unknown string.
RUN_RUNNING = "running"
RUN_OK = "ok"
RUN_FAILED = "failed"
RUN_STATUSES = frozenset({RUN_RUNNING, RUN_OK, RUN_FAILED})


class UnknownRunStatusError(ValueError):
    """A run status outside the closed catalog. Typed at the raise site, never a string match."""


def _checked_status(status: str) -> str:
    if status not in RUN_STATUSES:
        raise UnknownRunStatusError(
            f"{status!r} is not a run status; expected one of {sorted(RUN_STATUSES)}"
        )
    return status


def insert_run(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(insert(runs).values(started_at=utcnow(), boards_attempted=0))
        return int(result.inserted_primary_key[0])  # type: ignore[index]


def finalize_run(
    engine: Engine,
    run_id: int,
    *,
    boards_attempted: int,
    boards_complete: int,
    postings_seen: int,
    new_count: int,
    closed_count: int,
    reopened_count: int,
    errors: list[str],
    finished: bool = True,
    status: str = RUN_OK,
) -> None:
    """Write the scan stage's counts onto a run row.

    `finished=False` when the caller does not own the run — under `boardwatch run` the scan
    is stage one of three, so stamping finished_at here would record the pipeline as complete
    the moment scan returned. The owner calls finish_run instead.
    """
    values: dict[str, object] = {
        "boards_attempted": boards_attempted,
        "boards_complete": boards_complete,
        "postings_seen": postings_seen,
        "new_count": new_count,
        "closed_count": closed_count,
        "reopened_count": reopened_count,
        "errors_json": errors,
    }
    if finished:
        values["finished_at"] = utcnow()
        # Only when this caller owns the run. `errors` is NOT the discriminator: per-board
        # failures are the scan's normal partial outcome (Workday returns `partial`
        # routinely), so the caller decides, and it is the only one that can tell a few dead
        # boards from a systemic outage.
        values["status"] = _checked_status(status)
    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.id == run_id).values(**values))


def finish_run(
    engine: Engine, run_id: int, *, errors: list[str] | None = None, status: str = RUN_OK
) -> None:
    """Stamp finished_at and the terminal status on a run the caller owns.

    `status` is the run's exit status for P0 item 4's manifest. It is a parameter rather than
    something inferred from `errors` because the two are not the same question: a run can
    finish with per-lead tailor errors and still be a successful run, while a run killed
    before this call has no errors recorded at all and is not successful.

    What an un-updated row means is fixed by the column default, and the honest statement is
    narrower than "it was killed": `running` with `finished_at` NULL means only *nothing ever
    closed this row*. Three conditions share that signature — a run still in flight, a run
    killed by SIGKILL, and a standalone lane that raised between `ensure_run` and its own
    `finish_run` (`reports/tailor.py`, `eligibility/preflight.py` and `cli/eligibility_cmd.py`
    each call this on the success path only, with no `try/finally`). Separating those three
    needs the reaper that P3 owns; this column does not claim to do it.

    Errors are appended, not replaced: the scan stage has already written its own into
    errors_json by the time the pipeline finishes, and overwriting would lose them.
    """
    with engine.begin() as conn:
        values: dict[str, object] = {
            "finished_at": utcnow(),
            "status": _checked_status(status),
        }
        if errors:
            existing = conn.execute(
                select(runs.c.errors_json).where(runs.c.id == run_id)
            ).scalar_one_or_none()
            values["errors_json"] = list(existing or []) + errors
        conn.execute(update(runs).where(runs.c.id == run_id).values(**values))


def ensure_run(engine: Engine, run_id: int | None) -> int:
    """Return the caller's run id, minting a fresh run row when there is none.

    This is what keeps `run_id IS NULL` meaning exactly one thing — *the row predates run
    attribution* — instead of also meaning "written outside a pipeline". Every stage that
    writes an attributable row calls this, so a stage invoked standalone is recorded as a
    degenerate pipeline run rather than as an unattributed write.
    """
    return insert_run(engine) if run_id is None else run_id


def get_validators(conn: Connection, url: str) -> ResponseValidators | None:
    row = conn.execute(
        select(http_cache.c.etag, http_cache.c.last_modified).where(http_cache.c.url == url)
    ).one_or_none()
    if row is None:
        return None
    return ResponseValidators(etag=row.etag, last_modified=row.last_modified)


def get_watched_companies(
    conn: Connection, *, slug: str | None = None, provider: str | None = None
) -> list[Row[Any]]:
    stmt = select(companies).where(companies.c.watched.is_(True))
    if slug is not None:
        stmt = stmt.where(companies.c.slug == slug)
    if provider is not None:
        stmt = stmt.where(companies.c.provider == provider)
    return list(conn.execute(stmt).all())


def upsert_watch(conn: Connection, *, provider: str, slug: str, name: str, source: str) -> None:
    stmt = sqlite_insert(companies).values(
        name=name, provider=provider, slug=slug, source=source, watched=True
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[companies.c.provider, companies.c.slug], set_={"watched": True}
        )
    )


# keep the P0 signature working — it is now a thin wrapper (no caller churn)
def upsert_watched_company(conn: Connection, *, provider: str, slug: str, name: str) -> None:
    upsert_watch(conn, provider=provider, slug=slug, name=name, source="user")


def unwatch(conn: Connection, *, provider: str, slug: str) -> int:
    result = conn.execute(
        update(companies)
        .where(companies.c.provider == provider, companies.c.slug == slug)
        .values(watched=False)
    )
    return int(result.rowcount)


def list_watches(conn: Connection) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(
                companies.c.provider, companies.c.slug, companies.c.source,
                companies.c.watched, companies.c.last_health, companies.c.last_ok_at,
            ).where(companies.c.watched.is_(True)).order_by(companies.c.provider, companies.c.slug)
        ).all()
    )


def get_profile(conn: Connection) -> Row[Any] | None:
    return conn.execute(select(profile).where(profile.c.id == 1)).one_or_none()


def save_profile(
    conn: Connection,
    *,
    text: str,
    target_titles: list[str],
    exclude_titles: list[str],
    locations: list[str],
    remote_only: bool,
    skills: list[str],
    taxonomy_version: str,
) -> None:
    stmt = sqlite_insert(profile).values(
        id=1,
        text=text,
        skills_json=skills,
        taxonomy_version=taxonomy_version,
        target_titles_json=target_titles,
        exclude_titles_json=exclude_titles,
        locations_json=locations,
        remote_only=remote_only,
        updated_at=utcnow(),
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[profile.c.id],
            set_={
                "text": stmt.excluded.text,
                "skills_json": stmt.excluded.skills_json,
                "taxonomy_version": stmt.excluded.taxonomy_version,
                "target_titles_json": stmt.excluded.target_titles_json,
                "exclude_titles_json": stmt.excluded.exclude_titles_json,
                "locations_json": stmt.excluded.locations_json,
                "remote_only": stmt.excluded.remote_only,
                "updated_at": stmt.excluded.updated_at,
            },
        )
    )


def save_eligibility(
    conn: Connection, *, facts_json: dict[str, object], policy_json: dict[str, object]
) -> None:
    """Write the eligibility facts and severity policy onto the existing profile row.

    Takes JSON-ready dicts rather than the typed models, so this layer never imports from
    boardwatch.eligibility. The eligibility layer reads and writes the store; the reverse
    dependency would invert the layering.

    A separate UPDATE, never part of save_profile's upsert. Two reasons, both verified:
    profile.text is NOT NULL with no default, so an insert carrying only facts raises
    IntegrityError; and save_profile's set_ map must never list these columns or
    `profile edit` silently wipes declared facts (spec §4.6).
    """
    conn.execute(
        update(profile)
        .where(profile.c.id == 1)
        .values(
            eligibility_facts_json=facts_json,
            eligibility_policy_json=policy_json,
            updated_at=utcnow(),
        )
    )


def last_complete_scan_ages(conn: Connection) -> dict[int, datetime]:
    """company_id → finished_at of its most recent complete-or-unchanged board_scan."""
    stmt = (
        select(board_scans.c.company_id, func.max(board_scans.c.finished_at))
        .where(board_scans.c.status.in_(("complete", "unchanged")))
        .group_by(board_scans.c.company_id)
    )
    return {row[0]: row[1] for row in conn.execute(stmt).all()}


@dataclass(frozen=True)
class CurrentVersion:
    """The newest immutable content version of one posting.

    body_text comes from posting_versions, NEVER from postings.body_text, which
    scan/apply.py:119-120 rewrites in place on every revision. Spans stored against a
    version stay valid forever; spans against the posting garble on the next revision.
    """

    posting_version_id: int
    posting_id: int
    body_text: str
    captured_at: datetime


def current_posting_versions(
    conn: Connection, posting_ids: Sequence[int] | None = None
) -> dict[int, CurrentVersion]:
    """posting_id -> its newest posting_versions row, in ONE statement.

    With posting_ids=None this sweeps every OPEN posting, which is the preflight path.
    With an explicit list it ignores status, which is how `show` renders a closed
    posting's historical verdict (D-P2-9). No per-posting SQL on either path (D-P2-16).

    The tie-break on (captured_at, id) is load-bearing: two versions captured in the same
    transaction share captured_at, and ordering by captured_at alone would make "the
    current version" nondeterministic.
    """
    if posting_ids is not None and not posting_ids:
        return {}
    newer = (
        select(posting_versions.c.id)
        .where(
            posting_versions.c.posting_id == _pv.c.posting_id,
            tuple_(posting_versions.c.captured_at, posting_versions.c.id)
            > tuple_(_pv.c.captured_at, _pv.c.id),
        )
        .exists()
    )
    stmt = (
        select(
            _pv.c.id.label("posting_version_id"),
            _pv.c.posting_id,
            _pv.c.body_text,
            _pv.c.captured_at,
        )
        .join(postings, _pv.c.posting_id == postings.c.id)
        .where(~newer)
    )
    if posting_ids is None:
        stmt = stmt.where(postings.c.status == "open")
    else:
        stmt = stmt.where(postings.c.id.in_(posting_ids))
    return {
        int(row.posting_id): CurrentVersion(
            posting_version_id=int(row.posting_version_id),
            posting_id=int(row.posting_id),
            body_text=str(row.body_text),
            captured_at=row.captured_at,
        )
        for row in conn.execute(stmt).all()
    }
