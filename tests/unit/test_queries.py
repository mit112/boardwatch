from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import (
    RUN_FAILED,
    RUN_OK,
    RUN_RUNNING,
    append_run_error,
    finalize_run,
    finish_run,
    get_validators,
    insert_run,
    reap_stale_runs,
)


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def test_insert_run_is_visible_immediately(engine: Engine) -> None:
    run_id = insert_run(engine)
    # A separate connection sees the row while the scan is still running —
    # this is what doctor surfaces instead of lock-holder metadata (§0.3).
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    assert row.started_at is not None
    assert row.finished_at is None


def test_finalize_run_records_derived_counts(engine: Engine) -> None:
    run_id = insert_run(engine)
    finalize_run(
        engine, run_id,
        boards_attempted=3, boards_complete=2, postings_seen=40,
        new_count=5, closed_count=1, reopened_count=0, errors=["acme: HTTP 503"],
    )
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    assert row.finished_at is not None
    assert row.boards_attempted == 3
    assert row.boards_complete == 2
    assert row.postings_seen == 40
    assert row.new_count == 5
    assert row.closed_count == 1
    assert row.errors_json == ["acme: HTTP 503"]


def _insert_run_row(
    engine: Engine,
    *,
    started_at: datetime,
    status: str = RUN_RUNNING,
    finished_at: datetime | None = None,
    errors_json: list[str] | None = None,
) -> int:
    values: dict[str, object] = {
        "started_at": started_at, "boards_attempted": 0, "status": status,
        "finished_at": finished_at,
    }
    if errors_json is not None:
        values["errors_json"] = errors_json
    with engine.begin() as conn:
        result = conn.execute(insert(tables.runs).values(**values))
        return int(result.inserted_primary_key[0])


def _run_row(engine: Engine, run_id: int):
    with engine.connect() as conn:
        return conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()


# --- reap_stale_runs (P3 slice 2, D-046) --------------------------------------------


def test_reap_stale_runs_reaps_an_old_running_row_and_preserves_prior_errors(
    engine: Engine,
) -> None:
    run_id = _insert_run_row(
        engine,
        started_at=utcnow() - timedelta(hours=25),
        errors_json=["scan: board x failed"],
    )

    reaped = reap_stale_runs(engine, older_than=timedelta(hours=24))

    assert reaped == [run_id]
    row = _run_row(engine, run_id)
    assert row.status == RUN_FAILED
    assert row.finished_at is not None
    assert row.errors_json[0] == "scan: board x failed"
    assert row.errors_json[-1].startswith("reaped")


def test_reap_stale_runs_leaves_recent_running_and_old_ok_rows_untouched(engine: Engine) -> None:
    recent_running = _insert_run_row(engine, started_at=utcnow() - timedelta(hours=1))
    old_ok = _insert_run_row(
        engine,
        started_at=utcnow() - timedelta(hours=25),
        status=RUN_OK,
        finished_at=utcnow(),
    )

    reaped = reap_stale_runs(engine, older_than=timedelta(hours=24))

    assert reaped == []
    assert _run_row(engine, recent_running).status == RUN_RUNNING
    assert _run_row(engine, old_ok).status == RUN_OK


def test_reap_stale_runs_discriminates_a_stale_row_from_a_fresh_one_in_the_same_call(
    engine: Engine,
) -> None:
    """One call, two `running` rows: only the row past the cutoff is reaped. The other tests
    here either have no matching row (an early no-op) or a single row (no sibling to prove
    the UPDATE's WHERE discriminates row-by-row rather than something equivalent to
    updating-by-a-captured-id-list)."""
    stale_id = _insert_run_row(engine, started_at=utcnow() - timedelta(hours=25))
    fresh_id = _insert_run_row(engine, started_at=utcnow() - timedelta(hours=1))

    reaped = reap_stale_runs(engine, older_than=timedelta(hours=24))

    assert reaped == [stale_id]
    assert _run_row(engine, stale_id).status == RUN_FAILED
    assert _run_row(engine, fresh_id).status == RUN_RUNNING


def test_reap_stale_runs_leaves_a_running_row_with_finished_at_already_set_untouched(
    engine: Engine,
) -> None:
    """A `running` row that somehow already carries a `finished_at` is not this reaper's
    business — `finished_at IS NULL` is checked explicitly, not inferred from `status` alone."""
    run_id = _insert_run_row(
        engine,
        started_at=utcnow() - timedelta(hours=25),
        status=RUN_RUNNING,
        finished_at=utcnow(),
    )

    reaped = reap_stale_runs(engine, older_than=timedelta(hours=24))

    assert reaped == []
    assert _run_row(engine, run_id).status == RUN_RUNNING


def test_reap_stale_runs_leaves_a_non_running_status_row_untouched_regardless_of_finished_at(
    engine: Engine,
) -> None:
    """`status='running'` is checked explicitly, not inferred from `finished_at` alone — a
    row that already reads a terminal status is never this reaper's business."""
    run_id = _insert_run_row(
        engine, started_at=utcnow() - timedelta(hours=25), status=RUN_OK, finished_at=None
    )

    reaped = reap_stale_runs(engine, older_than=timedelta(hours=24))

    assert reaped == []
    assert _run_row(engine, run_id).status == RUN_OK


def test_reap_stale_runs_is_idempotent_on_a_second_call(engine: Engine) -> None:
    run_id = _insert_run_row(engine, started_at=utcnow() - timedelta(hours=25))
    first = reap_stale_runs(engine, older_than=timedelta(hours=24))
    assert first == [run_id]

    second = reap_stale_runs(engine, older_than=timedelta(hours=24))

    assert second == []
    row = _run_row(engine, run_id)
    assert row.errors_json is not None and len(row.errors_json) == 1, (
        "a second reap appended a duplicate note"
    )


def test_a_false_reap_self_corrects_when_finish_run_completes_it(engine: Engine) -> None:
    """`finish_run` has no `status='running'` precondition, so a reaped-then-completed run
    ends up `ok` — proving a false reap is benign (the soundness claim, as a test).

    That self-correction is `status`-only, not `errors_json`: `finish_run(errors=None)` never
    touches `errors_json`, so the `reaped: ...` note this reaper appended persists on an
    otherwise-successful row. This is intentional (the note is a truthful breadcrumb that the
    run breached the 24h threshold before completing) rather than an oversight — pinned here so
    a future change that starts clearing the note on completion is a deliberate decision, not a
    silent behavior change."""
    run_id = _insert_run_row(engine, started_at=utcnow() - timedelta(hours=25))
    reaped = reap_stale_runs(engine, older_than=timedelta(hours=24))
    assert reaped == [run_id]
    reaped_note = _run_row(engine, run_id).errors_json[-1]
    assert reaped_note.startswith("reaped")

    finish_run(engine, run_id, status=RUN_OK)

    row = _run_row(engine, run_id)
    assert row.status == RUN_OK
    assert row.finished_at is not None
    assert row.errors_json[-1] == reaped_note, (
        "the reaped note should persist through a clean finish_run — it is a truthful "
        "breadcrumb of the >24h threshold breach, not a stale artifact to strip"
    )


def test_get_validators_round_trip(engine: Engine) -> None:
    from datetime import datetime

    with engine.begin() as conn:
        conn.execute(
            insert(tables.http_cache).values(
                url="https://x.example/board", etag='W/"v1"', last_modified=None,
                fetched_at=datetime(2026, 1, 1), status=200,
            )
        )
    with engine.connect() as conn:
        validators = get_validators(conn, "https://x.example/board")
        assert validators is not None and validators.etag == 'W/"v1"'
        assert get_validators(conn, "https://other.example/") is None


def test_current_posting_versions_returns_the_newest_version_per_posting(tmp_path) -> None:
    """The first production read of posting_versions. Set-oriented by construction: one
    statement for the whole corpus, never a per-posting lookup (D-P2-16)."""
    from datetime import timedelta

    from sqlalchemy import insert

    from boardwatch.core.clock import utcnow
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import current_posting_versions
    from boardwatch.store.tables import companies, jobs, posting_versions, postings

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        ids = []
        for n, status in ((1, "open"), (2, "open"), (3, "closed")):
            jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
            pid = int(conn.execute(insert(postings).values(
                company_id=cid, job_id=jid, provider_posting_id=f"p-{n}", title="Eng",
                normalized_title="eng", first_seen_at=now, last_seen_at=now, status=status,
                consecutive_missing=0, content_hash=f"h{n}", body_text="current body",
            )).inserted_primary_key[0])
            ids.append(pid)
            conn.execute(insert(posting_versions).values(
                posting_id=pid, content_hash=f"h{n}a", body_text=f"first body {n}",
                captured_at=now - timedelta(days=2), run_id=None, capture_reason="new",
            ))
            conn.execute(insert(posting_versions).values(
                posting_id=pid, content_hash=f"h{n}b", body_text=f"latest body {n}",
                captured_at=now - timedelta(days=1), run_id=None, capture_reason="revised",
            ))

    with engine.connect() as conn:
        everything = current_posting_versions(conn)
        scoped = current_posting_versions(conn, [ids[0]])

    # closed postings are excluded from the default sweep (D-P2-9)
    assert set(everything) == {ids[0], ids[1]}
    assert everything[ids[0]].body_text == "latest body 1"
    assert everything[ids[1]].body_text == "latest body 2"
    assert set(scoped) == {ids[0]}
    # an explicit id list reaches a closed posting, which is how `show` renders history
    with engine.connect() as conn:
        assert set(current_posting_versions(conn, [ids[2]])) == {ids[2]}


def test_current_posting_versions_handles_an_empty_id_list(tmp_path) -> None:
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import current_posting_versions

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.connect() as conn:
        assert current_posting_versions(conn, []) == {}


def test_current_posting_versions_tie_breaks_on_id_when_captured_at_is_equal(tmp_path) -> None:
    """Two versions captured in the SAME transaction share captured_at. Ordering on
    captured_at alone would make "the current version" nondeterministic, so the query
    tie-breaks on (captured_at, id) and must return the HIGHER id."""
    from sqlalchemy import insert

    from boardwatch.core.clock import utcnow
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import current_posting_versions
    from boardwatch.store.tables import companies, jobs, posting_versions, postings

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        pid = int(conn.execute(insert(postings).values(
            company_id=cid, job_id=jid, provider_posting_id="p-tie", title="Eng",
            normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
            consecutive_missing=0, content_hash="ht", body_text="current body",
        )).inserted_primary_key[0])
        first = int(conn.execute(insert(posting_versions).values(
            posting_id=pid, content_hash="hta", body_text="same instant, earlier row",
            captured_at=now, run_id=None, capture_reason="new",
        )).inserted_primary_key[0])
        second = int(conn.execute(insert(posting_versions).values(
            posting_id=pid, content_hash="htb", body_text="same instant, later row",
            captured_at=now, run_id=None, capture_reason="revised",
        )).inserted_primary_key[0])
    assert second > first

    with engine.connect() as conn:
        got = current_posting_versions(conn, [pid])
    assert got[pid].posting_version_id == second
    assert got[pid].body_text == "same instant, later row"


def test_current_posting_versions_ignores_postings_body_text(tmp_path) -> None:
    """body_text MUST come from posting_versions, never from postings.body_text, which
    scan/apply.py rewrites in place on every revision. A span stored against a version
    stays valid forever; a span against the posting garbles on the next revision."""
    from sqlalchemy import insert

    from boardwatch.core.clock import utcnow
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import current_posting_versions
    from boardwatch.store.tables import companies, jobs, posting_versions, postings

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        pid = int(conn.execute(insert(postings).values(
            company_id=cid, job_id=jid, provider_posting_id="p-src", title="Eng",
            normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
            consecutive_missing=0, content_hash="hs",
            body_text="MUTABLE posting body, must not be read",
        )).inserted_primary_key[0])
        conn.execute(insert(posting_versions).values(
            posting_id=pid, content_hash="hsa", body_text="IMMUTABLE version body",
            captured_at=now, run_id=None, capture_reason="new",
        ))

    with engine.connect() as conn:
        got = current_posting_versions(conn, [pid])
    assert got[pid].body_text == "IMMUTABLE version body"


def test_current_posting_versions_skips_a_posting_with_no_versions(tmp_path) -> None:
    """A posting that has never been captured has no current version, so it must be
    ABSENT from the mapping rather than present with an empty body."""
    from sqlalchemy import insert

    from boardwatch.core.clock import utcnow
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import current_posting_versions
    from boardwatch.store.tables import companies, jobs, postings

    engine = get_engine(tmp_path)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        pid = int(conn.execute(insert(postings).values(
            company_id=cid, job_id=jid, provider_posting_id="p-bare", title="Eng",
            normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
            consecutive_missing=0, content_hash="hb", body_text="body",
        )).inserted_primary_key[0])

    with engine.connect() as conn:
        assert current_posting_versions(conn) == {}
        assert current_posting_versions(conn, [pid]) == {}


# --- append_run_error (D-287, open question 1) ---------------------------------------


def test_append_run_error_appends_without_clobbering_prior_errors(engine: Engine) -> None:
    """Appending an error AFTER `finish_run` must not lose what the run already recorded.

    The funnel/morning emits run after `finish_run` in `runner.py`'s finally block, so the
    only way a reporting failure reaches the run row is a second, additive write. Atomic
    `json_insert` rather than a read-modify-write, matching `reap_stale_runs`.
    """
    run_id = insert_run(engine)
    finish_run(engine, run_id, errors=["scan: board x failed"])
    append_run_error(engine, run_id, "funnel artifact not written: boom")
    with engine.connect() as conn:
        row = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    assert list(row.errors_json) == [
        "scan: board x failed",
        "funnel artifact not written: boom",
    ]


def test_append_run_error_leaves_the_runs_terminal_status_and_finished_at_alone(
    engine: Engine,
) -> None:
    """A reporting failure is not a run outcome, so this must not re-stamp either field.

    Re-running `finish_run` would have been the cheap way to append and would have moved
    `finished_at`, making the artifact's own timestamp disagree with the run's.
    """
    run_id = insert_run(engine)
    finish_run(engine, run_id, status=RUN_OK)
    with engine.connect() as conn:
        before = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    append_run_error(engine, run_id, "funnel artifact not written: boom")
    with engine.connect() as conn:
        after = conn.execute(select(tables.runs).where(tables.runs.c.id == run_id)).one()
    assert after.status == before.status == RUN_OK
    assert after.finished_at == before.finished_at
    assert list(after.errors_json) == ["funnel artifact not written: boom"]
