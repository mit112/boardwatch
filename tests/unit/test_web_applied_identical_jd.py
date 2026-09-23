"""T125: a lead names every posting at the SAME company, with a byte-identical current body, on a
DIFFERENT job the owner already applied to. Annotation only — nothing is hidden or re-ranked.

The payload functions are called directly rather than over TCP: the envelope is not what this
pins, and `test_web_server.py` already owns it. Seeding is that module's own `_deliver`, so the
leads here are shaped exactly like the ones its queue tests serve.

Each control varies ONE clause of the evidence rule against the positive case, so a query that
dropped that clause alone turns exactly that control red.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, event, select, update

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext, detail_payload, queue_payload
from boardwatch.store.applications import ApplicationStatus, create_application
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import postings
from tests.unit.test_web_server import _deliver

APPLIED_ON = datetime(2026, 9, 14, 15, 30, 0)


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def ctx(tmp_path: Path) -> ApiContext:
    (tmp_path / "out").mkdir()
    (tmp_path / "queue").mkdir()
    return ApiContext(
        settings=load_settings(),
        out_root=(tmp_path / "out").resolve(),
        queue_root=(tmp_path / "queue").resolve(),
        owner_name="Example Owner",
        platform="darwin",
    )


def _twin(conn: Connection, lead: int, other: int, *, company: bool, body: bool) -> None:
    """Point `lead` at `other`'s company and/or current body hash."""
    source = conn.execute(
        select(postings.c.company_id, postings.c.content_hash).where(postings.c.id == other)
    ).one()
    values: dict[str, Any] = {}
    if company:
        values["company_id"] = source.company_id
    if body:
        values["content_hash"] = source.content_hash
    conn.execute(update(postings).where(postings.c.id == lead).values(**values))


def _seed(
    engine: Engine,
    *,
    company: bool = True,
    body: bool = True,
    status: ApplicationStatus = "applied",
    same_job: bool = False,
) -> tuple[int, int]:
    """An applied posting and a delivered lead. Returns `(lead_posting_id, applied_posting_id)`."""
    with engine.begin() as conn:
        applied, applied_job = _deliver(
            conn, "alexandria", title="Software Engineer, Platform",
            locations=["Alexandria, VA"],
        )
        create_application(conn, job_id=applied_job, status=status, occurred_at=APPLIED_ON)
        lead, _ = _deliver(
            conn, "austin", title="Software Engineer, Platform", locations=["Austin, TX"],
            job_id=applied_job if same_job else None,
        )
        _twin(conn, lead, applied, company=company, body=body)
    return lead, applied


def _queue_row(engine: Engine, ctx: ApiContext, posting_id: int) -> dict[str, Any]:
    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)
    served = [row for row in payload["rows"] + payload["review"] if row["posting_id"] == posting_id]
    assert len(served) == 1, "the lead must be served for its annotation to mean anything"
    return served[0]


def test_a_lead_lists_the_applied_posting_with_an_identical_body_at_the_same_company(
    engine: Engine, ctx: ApiContext
) -> None:
    lead, applied = _seed(engine)
    expected = [
        {
            "posting_id": applied,
            "title": "Software Engineer, Platform",
            "location": "Alexandria, VA",
            "applied_at": "2026-09-14T15:30:00+00:00",
        }
    ]
    assert _queue_row(engine, ctx, lead)["applied_identical_jd"] == expected
    # The pane serializes the same row through the same function, so it must say the same thing.
    with engine.connect() as conn:
        detail = detail_payload(conn, ctx, lead)
    assert detail is not None
    assert detail["row"]["applied_identical_jd"] == expected


def test_a_different_body_annotates_nothing(engine: Engine, ctx: ApiContext) -> None:
    lead, _ = _seed(engine, body=False)
    assert _queue_row(engine, ctx, lead)["applied_identical_jd"] == []


def test_the_same_body_at_a_different_company_annotates_nothing(
    engine: Engine, ctx: ApiContext
) -> None:
    lead, _ = _seed(engine, company=False)
    assert _queue_row(engine, ctx, lead)["applied_identical_jd"] == []


@pytest.mark.parametrize("status", ["withdrawn", "interested"])
def test_a_withdrawn_or_interested_application_annotates_nothing(
    engine: Engine, ctx: ApiContext, status: ApplicationStatus
) -> None:
    lead, _ = _seed(engine, status=status)
    assert _queue_row(engine, ctx, lead)["applied_identical_jd"] == []


def test_a_posting_on_the_same_job_annotates_nothing(engine: Engine, ctx: ApiContext) -> None:
    """A sibling on the lead's OWN job is already suppressed as applied, so it is never served;
    the clause is exercised through the pane, which serves any delivered lead."""
    lead, _ = _seed(engine, same_job=True)
    with engine.connect() as conn:
        detail = detail_payload(conn, ctx, lead)
    assert detail is not None
    assert detail["row"]["applied_identical_jd"] == []


@contextmanager
def _counting(engine: Engine) -> Iterator[list[str]]:
    statements: list[str] = []

    def _record(*args: Any) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def _annotation_statements(engine: Engine, ctx: ApiContext) -> int:
    with _counting(engine) as statements, engine.connect() as conn:
        queue_payload(conn, ctx)
    # The reader's own statement is the only one aliasing `postings` as a twin.
    return sum("twin" in statement for statement in statements)


def test_the_annotation_is_one_statement_however_many_rows_are_served(
    engine: Engine, ctx: ApiContext
) -> None:
    _seed(engine)
    few = _annotation_statements(engine, ctx)
    with engine.begin() as conn:
        for index in range(12):
            _deliver(conn, f"more-{index}")
    many = _annotation_statements(engine, ctx)
    assert few == many == 1
