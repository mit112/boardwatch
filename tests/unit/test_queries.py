from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import finalize_run, get_validators, insert_run


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
