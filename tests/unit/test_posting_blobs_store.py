"""T364: `store.posting_blobs` writes a posting's blobs and the three facts derived from them.

The derived columns must hold what the old SQL expressions computed, because the migration fills them
with those expressions and the writer computes them in Python. Each case is checked against SQLite
itself, not against a second Python copy of the rule.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.posting_blobs import (
    _json_extract,
    body_trimmed_len,
    insert_posting,
    posting_body,
    posting_raw,
    update_posting,
)
from boardwatch.store.tables import companies, jobs, posting_blobs, postings

NOW = datetime(2026, 11, 27)


def _sqlite_json_extract(raw: Any, path: str) -> object:
    """`json_extract` stored through a TEXT column, as the migration stores it."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (v TEXT)")
    con.execute(f"INSERT INTO t SELECT json_extract(?, '{path}')", (json.dumps(raw),))
    return con.execute("SELECT v FROM t").fetchone()[0]


@pytest.mark.parametrize("value", [
    "Contract", "", "  FullTime ", "Ünïcode", 3, -2, 1.5, 1e20, True, False, None,
    {"b": 1, "a": [1, "x"]}, [1, "two", None], {"nested": {"deep": "é"}},
])
def test_the_python_reading_agrees_with_json_extract(value: object) -> None:
    raw = {"employmentType": value, "jobapps": {"employer_url": value}}
    assert _json_extract(raw, "employmentType") == _sqlite_json_extract(raw, "$.employmentType")
    assert _json_extract(raw, "jobapps", "employer_url") == _sqlite_json_extract(
        raw, "$.jobapps.employer_url"
    )


@pytest.mark.parametrize("raw", [
    None, {}, [], "text", 7, {"jobapps": "not an object"}, {"jobapps": None}, {"other": 1},
])
def test_an_absent_path_is_null_as_json_extract_has_it(raw: object) -> None:
    assert _json_extract(raw, "jobapps", "employer_url") is None
    assert _sqlite_json_extract(raw, "$.jobapps.employer_url") is None


@pytest.mark.parametrize("body", [
    "", " ", " \t\n\r\f\v", "x", "  a b  ", " ", " word ", "\x0bé\x0c", "line\n\n",
])
def test_the_trimmed_length_agrees_with_sqlites_trim(body: str) -> None:
    con = sqlite3.connect(":memory:")
    want = con.execute("SELECT length(trim(?, char(32, 9, 10, 13, 12, 11)))", (body,)).fetchone()[0]
    assert body_trimmed_len(body) == want


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    return engine


def _insert(engine: Engine, ppid: str, body: str, raw: Any = None) -> int:
    with engine.begin() as conn:
        company = conn.execute(select(companies.c.id)).scalar()
        if company is None:
            company = conn.execute(insert(companies).values(
                name="Acme", provider="jobapps", slug="acme", source="user", watched=True,
            )).inserted_primary_key[0]
        job = conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0]
        return insert_posting(
            conn, company_id=company, job_id=job, provider_posting_id=ppid, title="E",
            normalized_title="e", remote_policy="unknown", first_seen_at=NOW, last_seen_at=NOW,
            status="open", consecutive_missing=0, content_hash=f"h-{ppid}", body_text=body,
            raw_json=raw,
        )


def _read(engine: Engine, posting_id: int) -> tuple[object, ...]:
    with engine.connect() as conn:
        return tuple(conn.execute(select(
            postings.c.body_trimmed_len, postings.c.employment_type,
            postings.c.jobapps_employer_url, posting_body(), posting_raw(),
        ).where(postings.c.id == posting_id)).one())


def test_each_row_reads_its_own_body_and_payload(engine: Engine) -> None:
    """The subquery is correlated: two postings read two different blobs, not the first one twice."""
    a = _insert(engine, "a", " body A ", {"employmentType": "Contract"})
    b = _insert(engine, "b", "body B", {"jobapps": {"employer_url": "https://b.example"}})
    assert _read(engine, a) == (6, "Contract", None, " body A ", {"employmentType": "Contract"})
    assert _read(engine, b) == (
        6, None, "https://b.example", "body B", {"jobapps": {"employer_url": "https://b.example"}}
    )
    with engine.connect() as conn:
        stored = conn.execute(select(posting_blobs.c.posting_id)).scalars().all()
    assert sorted(stored) == sorted([a, b])


def test_an_update_moves_each_blob_with_its_derived_columns(engine: Engine) -> None:
    pid = _insert(engine, "a", "first body", {"employmentType": "Contract"})
    with engine.begin() as conn:
        update_posting(conn, pid, {"title": "New"})  # no blob named: neither blob moves
    assert _read(engine, pid) == (10, "Contract", None, "first body", {"employmentType": "Contract"})
    with engine.begin() as conn:
        update_posting(conn, pid, {"body_text": " \t "})
    assert _read(engine, pid) == (0, "Contract", None, " \t ", {"employmentType": "Contract"})
    with engine.begin() as conn:
        update_posting(conn, pid, {"raw_json": None})
    assert _read(engine, pid) == (0, None, None, " \t ", None)
    with engine.begin() as conn:
        update_posting(conn, pid, {})  # writes nothing, and is not a syntax error
    assert _read(engine, pid) == (0, None, None, " \t ", None)
