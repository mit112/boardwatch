"""T362: the scan's per-board read of stored postings does not carry the two blobs.

A `postings` row averages 17.4 KB, 17 KB of it `body_text` and `raw_json`. `_apply_listed` used to
`select(postings)` for the whole board, closed history included, on every scan of a board that
listed. It now reads the columns its loop consumes, and fetches a body by id only for a row the
snapshot lists. The stored result must not move.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import Engine, event, insert, select, update

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.identity_queries import load_identities
from boardwatch.store.queries import insert_run

URL = "https://boards.example/acme"


def _company(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]  # type: ignore[index]
        )


def _posting(pid: str, body: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=pid, title=f"Job {pid}", url=f"https://x/{pid}",
        locations=["Austin, TX"], body_text=body, raw_json={"id": pid},
    )


def _snapshot(listed: list[RawPosting]) -> BoardSnapshot:
    return BoardSnapshot(
        status="complete", postings=listed, url=URL, observed_validators=None, error=None,
        listed_ids=frozenset(p.provider_posting_id for p in listed),
    )


def _blob_selects(engine: Engine) -> list[str]:
    """Collected SELECT statements that read a blob column of `postings` (a list that grows)."""
    seen: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        sql = " ".join(statement.split())
        if sql.startswith("SELECT") and re.search(r"postings\.(body_text|raw_json)", sql):
            seen.append(sql)

    return seen


def test_the_board_read_leaves_the_blobs_of_unlisted_rows_unread(tmp_path: Path) -> None:
    """Three stored rows, one listed again. Nothing may read a blob except by id, and only the
    listed row's body is read (its identity needs it): never `raw_json`, never a closed row's."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _company(engine)
    apply_board(
        engine,
        _snapshot([_posting("A", "body a"), _posting("B", "body b"), _posting("C", "body c")]),
        company_id, insert_run(engine),
    )
    with engine.begin() as conn:  # B closed history, C open but unlisted below
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.provider_posting_id == "B")
            .values(status="closed")
        )

    seen = _blob_selects(engine)
    apply_board(
        engine,
        BoardSnapshot(
            status="partial", postings=[_posting("A", "body a")], url=URL,
            observed_validators=None, error=None, listed_ids=frozenset({"A"}),
        ),
        company_id, insert_run(engine),
    )

    assert len(seen) == 1, seen  # A's body, once
    assert "postings.body_text" in seen[0] and "postings.raw_json" not in seen[0]
    assert re.search(r"postings\.id = \?", seen[0]), seen[0]  # by id, not for the whole board


def test_the_result_is_what_it_was(tmp_path: Path) -> None:
    """A re-list with an unchanged body, one with a revised body and one reopening a closed row
    leave the same postings, versions and identities the full-row read did."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _company(engine)
    apply_board(
        engine,
        _snapshot([_posting("A", "body a"), _posting("B", "body b")]),
        company_id, insert_run(engine),
    )
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.provider_posting_id == "B")
            .values(status="closed")
        )
    apply_board(
        engine,
        _snapshot([_posting("A", "body a v2"), _posting("B", "body b")]),
        company_id, insert_run(engine),
    )

    with engine.connect() as conn:
        rows = {
            r.provider_posting_id: r
            for r in conn.execute(select(tables.postings)).all()
        }
        versions = conn.execute(
            select(tables.posting_versions.c.posting_id, tables.posting_versions.c.capture_reason)
            .order_by(tables.posting_versions.c.id)
        ).all()
        identities = load_identities(conn)
    assert rows["B"].status == "open" and rows["B"].closed_at is None  # reopened
    assert rows["A"].body_text == "body a v2"
    assert [(v.posting_id, v.capture_reason) for v in versions] == [
        (rows["A"].id, "new"), (rows["B"].id, "new"), (rows["A"].id, "revised"),
    ]
    # Identities stay in step with the stored rows: an unchanged-body re-list (B) carried the
    # stored body into its identity, a revised one (A) carried the new body.
    for pid, body in (("A", "body a v2"), ("B", "body b")):
        r = rows[pid]
        want = compute_identities(
            IdentityInputs(
                posting_id=int(r.id), company_id=company_id, company_name="Acme",
                provider_posting_id=pid, title=f"Job {pid}", locations=["Austin, TX"],
                content_hash=r.content_hash, body_text=body, url=r.url,
                first_seen_at=r.first_seen_at,
            )
        )
        assert set(identities[int(r.id)]) == set(want)


def test_each_listed_row_gets_the_identity_its_own_body_earns(tmp_path: Path) -> None:
    """A stub (empty body) carries no `exact_quad`; a posting with a body does. Both are listed
    again unchanged, so the stored body is the only source of that fact, and it has to be the
    row's OWN body: a lookup bound to another posting's id gives a stub a quad or takes one away."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    company_id = _company(engine)
    board = [_posting("N1", "body one"), _posting("S", ""), _posting("N2", "body two")]
    apply_board(engine, _snapshot(board), company_id, insert_run(engine))
    apply_board(engine, _snapshot(board), company_id, insert_run(engine))  # unchanged re-list

    with engine.connect() as conn:
        ids = {
            r.provider_posting_id: int(r.id)
            for r in conn.execute(select(tables.postings.c.id, tables.postings.c.provider_posting_id))
        }
        identities = load_identities(conn)
    kinds = {pid: {i.kind for i in identities[row_id]} for pid, row_id in ids.items()}
    assert "exact_quad" in kinds["N1"] and "exact_quad" in kinds["N2"]
    assert "exact_quad" not in kinds["S"]
    assert all("company_title_location" in k for k in kinds.values())
