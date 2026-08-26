"""`mark_job_applied`: the one writer for "I applied to this", idempotent by design.

Both `track` and the web endpoint call this and nothing else, so what is asserted here is
contract rather than implementation detail:

* a repeat mark appends **no** `application_events` row — counted before and after, because
  "no new event" is the only thing that stops a refresh-happy browser tab from writing a
  history of duplicate transitions;
* `submitted_at` records the FIRST transition into applied and is never re-stamped;
* the unit is the canonical `job_id`, not the posting, so a sibling posting on the same job
  reads as applied the moment either one is marked.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, insert, select, text
from sqlalchemy.exc import IntegrityError

from boardwatch.core.clock import utcnow
from boardwatch.store.applications import (
    APPLIED_STATUSES,
    MarkOutcome,
    MarkResult,
    applied_job_ids,
    create_application,
    get_application,
    get_application_events,
    get_applications,
    mark_job_applied,
    set_application_status,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import (
    application_events,
    applications,
    companies,
    jobs,
    posting_versions,
    postings,
)

# Naive UTC, matching boardwatch.core.clock.utcnow() (A2).
NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _job(conn: Connection) -> int:
    return int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])


def _company(conn: Connection, slug: str = "acme") -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name="Acme", provider="greenhouse", slug=slug, source="user", watched=True,
            )
        ).inserted_primary_key[0]
    )


def _version(conn: Connection, posting_id: int, *, captured_at: Any, tag: str) -> int:
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=tag, body_text=f"body {tag}",
                captured_at=captured_at, capture_reason="new",
            )
        ).inserted_primary_key[0]
    )


def _posting(
    conn: Connection,
    *,
    job_id: int | None,
    key: str = "alpha",
    company_id: int | None = None,
    with_version: bool = True,
) -> tuple[int, int | None]:
    """A posting and its single current version. Returns (posting_id, posting_version_id)."""
    if company_id is None:
        company_id = _company(conn, slug=f"acme-{key}")
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=key,
                title="Software Engineer", normalized_title="software engineer",
                url=f"https://example.test/{key}", locations_json=["Remote"],
                remote_policy="remote", first_seen_at=NOW, last_seen_at=NOW, status="open",
                consecutive_missing=0, content_hash=key, body_text=f"body {key}",
            )
        ).inserted_primary_key[0]
    )
    version_id = _version(conn, posting_id, captured_at=NOW, tag=key) if with_version else None
    return posting_id, version_id


def _row_count(conn: Connection, table: Any) -> int:
    return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def _assert_fks_clean(engine: Engine) -> None:
    """FKs are OFF inside alembic, so a green migration does not prove the rows are sound."""
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []


def test_a_missing_posting_writes_nothing(engine: Engine) -> None:
    with engine.begin() as conn:
        result = mark_job_applied(conn, posting_id=9999, source="web")
    assert result == MarkResult(outcome=MarkOutcome.NO_POSTING)
    with engine.connect() as conn:
        assert _row_count(conn, applications) == 0
        assert _row_count(conn, application_events) == 0


def test_no_posting_and_no_job_are_distinct_outcomes() -> None:
    """The CLI collapses these into one message; the return value must not.

    NO_JOB is defensive rather than dead: `postings.job_id` is nullable in the table
    definition and is held NOT NULL by a trigger, so a legacy or hand-edited store can
    still present the state that the trigger now forbids (see the next test).
    """
    assert MarkOutcome.NO_POSTING != MarkOutcome.NO_JOB


def test_a_null_job_id_is_refused_by_the_trigger(engine: Engine) -> None:
    """Why NO_JOB cannot be reached through a normal write: `postings_job_required_insert`."""
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _posting(conn, job_id=None)


def test_an_untracked_job_gets_an_application_created_in_applied(engine: Engine) -> None:
    with engine.begin() as conn:
        job_id = _job(conn)
        posting_id, version_id = _posting(conn, job_id=job_id)
    with engine.begin() as conn:
        result = mark_job_applied(conn, posting_id=posting_id, source="web")
    assert result.outcome is MarkOutcome.CREATED
    assert result.job_id == job_id
    assert result.application_id is not None
    with engine.connect() as conn:
        app = get_application(conn, result.application_id)
        events = get_application_events(conn, result.application_id)
    assert app is not None
    assert app.status == "applied"                      # not `create_application`'s `interested`
    assert app.attempt_no == 1
    assert app.submitted_at is not None                 # first transition into applied
    assert app.posting_version_id == version_id         # linked, not left NULL
    assert [e.event_type for e in events] == ["created"]
    assert events[0].source == "web"
    _assert_fks_clean(engine)


def test_the_created_application_links_the_current_version_not_the_first(engine: Engine) -> None:
    """`current_posting_versions`, not `min(id)`: a revised posting has two version rows."""
    with engine.begin() as conn:
        job_id = _job(conn)
        posting_id, first_version = _posting(conn, job_id=job_id)
        newest = _version(conn, posting_id, captured_at=NOW + timedelta(days=1), tag="revised")
    with engine.begin() as conn:
        result = mark_job_applied(conn, posting_id=posting_id, source="web")
    assert result.application_id is not None
    with engine.connect() as conn:
        app = get_application(conn, result.application_id)
    assert app is not None
    assert app.posting_version_id == newest
    assert app.posting_version_id != first_version
    _assert_fks_clean(engine)


def test_a_posting_with_no_version_is_still_markable(engine: Engine) -> None:
    """No current version is a NULL link, never a KeyError."""
    with engine.begin() as conn:
        job_id = _job(conn)
        posting_id, _ = _posting(conn, job_id=job_id, with_version=False)
    with engine.begin() as conn:
        result = mark_job_applied(conn, posting_id=posting_id, source="web")
    assert result.outcome is MarkOutcome.CREATED
    assert result.application_id is not None
    with engine.connect() as conn:
        app = get_application(conn, result.application_id)
    assert app is not None
    assert app.posting_version_id is None
    assert app.status == "applied"
    _assert_fks_clean(engine)


def test_an_interested_attempt_is_transitioned_not_duplicated(engine: Engine) -> None:
    with engine.begin() as conn:
        job_id = _job(conn)
        posting_id, _ = _posting(conn, job_id=job_id)
        app_id = create_application(conn, job_id=job_id, status="interested", source="user")
    with engine.begin() as conn:
        result = mark_job_applied(conn, posting_id=posting_id, source="web")
    assert result == MarkResult(
        outcome=MarkOutcome.TRANSITIONED, job_id=job_id, application_id=app_id
    )
    with engine.connect() as conn:
        assert len(get_applications(conn, job_id)) == 1          # transitioned, no new attempt
        app = get_application(conn, app_id)
        events = get_application_events(conn, app_id)
    assert app is not None
    assert app.status == "applied"
    assert app.submitted_at is not None
    assert [e.event_type for e in events] == ["created", "status_change"]
    assert (events[-1].from_status, events[-1].to_status) == ("interested", "applied")
    assert events[-1].source == "web"                            # the caller's source, not "user"
    _assert_fks_clean(engine)


@pytest.mark.parametrize("status", APPLIED_STATUSES)
def test_a_repeat_mark_is_unchanged_and_appends_no_event(engine: Engine, status: str) -> None:
    """The idempotency guarantee the endpoint depends on, counted on both sides."""
    with engine.begin() as conn:
        job_id = _job(conn)
        posting_id, _ = _posting(conn, job_id=job_id)
        app_id = create_application(conn, job_id=job_id, status="interested", source="user")
        set_application_status(
            conn, application_id=app_id, to_status=status, source="user"  # type: ignore[arg-type]
        )
    with engine.connect() as conn:
        events_before = _row_count(conn, application_events)
        before = get_application(conn, app_id)
    with engine.begin() as conn:
        result = mark_job_applied(conn, posting_id=posting_id, source="web")
    with engine.connect() as conn:
        events_after = _row_count(conn, application_events)
        after = get_application(conn, app_id)
        attempts = get_applications(conn, job_id)
    assert result == MarkResult(
        outcome=MarkOutcome.UNCHANGED, job_id=job_id, application_id=app_id
    )
    assert events_before == 2                                    # created + the one transition
    assert events_after == events_before                         # nothing appended
    assert before is not None and after is not None
    assert after.status == status                                # not overwritten with "applied"
    assert after.updated_at == before.updated_at
    assert after.submitted_at == before.submitted_at
    assert len(attempts) == 1
    _assert_fks_clean(engine)


def test_submitted_at_survives_a_repeat_mark(engine: Engine) -> None:
    """Re-stamping submitted_at would move the applied date; three days is not a clock skew."""
    applied_at = NOW - timedelta(days=3)
    with engine.begin() as conn:
        job_id = _job(conn)
        posting_id, _ = _posting(conn, job_id=job_id)
        app_id = create_application(conn, job_id=job_id, status="interested", source="user")
        set_application_status(
            conn, application_id=app_id, to_status="applied", source="user",
            occurred_at=applied_at,
        )
    with engine.begin() as conn:
        mark_job_applied(conn, posting_id=posting_id, source="web")
    with engine.connect() as conn:
        app = get_application(conn, app_id)
    assert app is not None
    assert app.submitted_at == applied_at
    _assert_fks_clean(engine)


def test_marking_one_posting_applies_the_whole_job(engine: Engine) -> None:
    """Two postings, one canonical job: the sibling must read as applied too."""
    with engine.begin() as conn:
        job_id = _job(conn)
        company_id = _company(conn, slug="acme-shared")
        first, _ = _posting(conn, job_id=job_id, key="alpha", company_id=company_id)
        second, _ = _posting(conn, job_id=job_id, key="beta", company_id=company_id)
    with engine.begin() as conn:
        created = mark_job_applied(conn, posting_id=first, source="web")
    with engine.connect() as conn:
        events_before = _row_count(conn, application_events)
    with engine.begin() as conn:
        sibling = mark_job_applied(conn, posting_id=second, source="web")
    with engine.connect() as conn:
        events_after = _row_count(conn, application_events)
        attempts = get_applications(conn, job_id)
        applied = applied_job_ids(conn)
    assert created.outcome is MarkOutcome.CREATED
    assert sibling == MarkResult(
        outcome=MarkOutcome.UNCHANGED, job_id=job_id, application_id=created.application_id
    )
    assert events_after == events_before
    assert len(attempts) == 1
    assert applied == {job_id: "applied"}                        # the read path both postings use
    _assert_fks_clean(engine)
