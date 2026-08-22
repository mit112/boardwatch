"""Fixtures for cross-module coverage-instrument tests (Task 9).

`store_conn` and `board_factory` are named by task-9-brief.md, but neither existed to be
verified against: the brief predates `board_coverage.py` and `coverage_queries.py`. Built
here against the real schema instead — same `get_engine(dir)` + `ensure_schema` setup as
`tests/cli/test_coverage_cmd.py`, and the same "seed a `jobs` row before every `postings` row"
rule that module documents (`postings.job_id` is NOT NULL, enforced by a trigger).

Everything a test does — inserts via `board_factory`, reads via `load_board_coverage` — runs on
the SAME `Connection`, so a fixture's writes are visible to the test's reads without a commit:
that is what makes `store_conn` a single object both roles share, not a decorative wrapper.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import Connection, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import board_scans, companies, jobs, postings, runs


@pytest.fixture()
def store_conn(tmp_path: Path):
    """A live connection to a freshly migrated, empty store."""
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    with engine.connect() as conn:
        yield conn


@dataclass
class _Board:
    """One watched company, with a `scan()` per run — the shape the brief's test bodies call.

    `_held_so_far` matters: `load_board_coverage` counts `held` straight from
    `postings.status == 'open'` for the company, with NO run_id filter (coverage_queries.py's
    own comment: "counted independently of whatever the scan itself wrote to
    board_scans.postings_listed"). So `held=600` on run 1 and `held=600` again on run 2 must
    NOT insert 1,200 open postings — it must leave exactly 600 in the store. `scan()` therefore
    treats `held` as the total the store should hold after this call, and only inserts the
    delta since the last call.
    """

    conn: Connection
    company_id: int
    _held_so_far: int = field(default=0, init=False)

    def scan(
        self,
        *,
        run_id: int,
        status: str,
        board_reported_total: int | None,
        board_enumerated: int | None,
        detail_deferred: int | None,
        held: int,
    ) -> None:
        now = utcnow()
        run_exists = self.conn.execute(
            select(runs.c.id).where(runs.c.id == run_id)
        ).scalar_one_or_none()
        if run_exists is None:
            self.conn.execute(
                insert(runs).values(id=run_id, started_at=now, boards_attempted=0)
            )
        self.conn.execute(
            insert(board_scans).values(
                run_id=run_id,
                company_id=self.company_id,
                started_at=now,
                finished_at=now,
                status=status,
                postings_listed=0,
                board_reported_total=board_reported_total,
                board_enumerated=board_enumerated,
                detail_deferred=detail_deferred,
            )
        )
        for i in range(held - self._held_so_far):
            seq = self._held_so_far + i
            job_id = int(
                self.conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0]
            )
            self.conn.execute(
                insert(postings).values(
                    company_id=self.company_id,
                    job_id=job_id,
                    provider_posting_id=f"p-{self.company_id}-{seq}",
                    title="Software Engineer",
                    normalized_title="software engineer",
                    remote_policy="unknown",
                    first_seen_at=now,
                    last_seen_at=now,
                    status="open",
                    consecutive_missing=0,
                    content_hash=f"h-{self.company_id}-{seq}",
                    body_text="body",
                )
            )
        self._held_so_far = max(self._held_so_far, held)


@pytest.fixture()
def board_factory(store_conn: Connection) -> Callable[..., _Board]:
    def factory(*, provider: str, name: str) -> _Board:
        slug = f"{provider}-{name}".lower().replace(" ", "-")
        result = store_conn.execute(
            insert(companies).values(
                name=name, provider=provider, slug=slug, source="user", watched=True,
            )
        )
        company_id = int(result.inserted_primary_key[0])
        return _Board(conn=store_conn, company_id=company_id)

    return factory
