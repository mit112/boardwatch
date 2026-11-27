"""The one writer and the shared readers of `posting_blobs` (T364).

A posting's body and provider payload live in `posting_blobs`, one row per posting, so the
`postings` row the corpus-wide reads walk is a few hundred bytes. Three facts those reads need are
derived from the blobs and kept on `postings`: `body_trimmed_len`, `employment_type` and
`jobapps_employer_url`. They are written HERE, in the statement that writes the blob they come
from, so no caller can move one without the other.

Every write of a posting goes through `insert_posting` or `update_posting`. Both take the old
column names, `body_text` and `raw_json`, so a caller states what it observed and this module
decides where it is stored.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from typing import Any

from sqlalchemy import Connection, ScalarSelect, insert, select, update

from boardwatch.store.tables import posting_blobs, postings

#: The characters `body_trimmed_len` strips: space, tab, LF, CR, FF, VT. The same set as SQLite's
#: `char(32, 9, 10, 13, 12, 11)` that the old empty-body expression named, and NOT `str.strip()`'s
#: default, which also strips Unicode whitespace.
BODY_STRIP_CHARS = " \t\n\r\f\v"

BLOB_COLUMNS = frozenset({"body_text", "raw_json"})


def body_trimmed_len(body: str) -> int:
    """The length of `body` with `BODY_STRIP_CHARS` stripped from both ends."""
    return len(body.strip(BODY_STRIP_CHARS))


def _json_extract(value: Any, *path: str) -> str | None:
    """What SQLite's `json_extract(raw_json, '$.a.b')` stored in a TEXT column returned.

    A string is itself; an object or array is its compact JSON text, escaped as `json.dumps`
    stored it; a number or boolean is its SQLite text form (`true` is 1); an absent key, a
    non-object on the path and a JSON null are NULL. The migration fills the columns with
    `json_extract` itself, and this has to agree with it.
    """
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, float):
        # SQLite's own REAL-to-TEXT rendering (`1.0e+20`, 15 significant digits), not Python's.
        with closing(sqlite3.connect(":memory:")) as con:
            return str(con.execute("SELECT CAST(? AS TEXT)", (value,)).fetchone()[0])
    return str(value)


def _derived_from_raw(raw: Any) -> dict[str, str | None]:
    return {
        "employment_type": _json_extract(raw, "employmentType"),
        "jobapps_employer_url": _json_extract(raw, "jobapps", "employer_url"),
    }


def insert_posting(conn: Connection, **values: Any) -> int:
    """Insert one posting and its blob row; returns the posting id.

    `values` are `postings` columns plus `body_text` (required) and `raw_json` (optional).
    """
    body = values.pop("body_text")
    raw = values.pop("raw_json", None)
    posting_id = int(
        conn.execute(
            insert(postings).values(
                **values, body_trimmed_len=body_trimmed_len(body), **_derived_from_raw(raw)
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )
    conn.execute(insert(posting_blobs).values(posting_id=posting_id, body=body, raw=raw))
    return posting_id


def update_posting(conn: Connection, posting_id: int, values: Mapping[str, Any]) -> None:
    """Update one posting: `postings` columns, and `body_text` / `raw_json` when given.

    An empty `values` writes nothing: SQLAlchemy would emit `UPDATE postings SET WHERE`, which
    SQLite refuses.
    """
    row = {k: v for k, v in values.items() if k not in BLOB_COLUMNS}
    blob: dict[str, Any] = {}
    if "body_text" in values:
        blob["body"] = values["body_text"]
        row["body_trimmed_len"] = body_trimmed_len(values["body_text"])
    if "raw_json" in values:
        blob["raw"] = values["raw_json"]
        row.update(_derived_from_raw(values["raw_json"]))
    if row:
        conn.execute(update(postings).where(postings.c.id == posting_id).values(**row))
    if blob:
        conn.execute(
            update(posting_blobs).where(posting_blobs.c.posting_id == posting_id).values(**blob)
        )


def posting_body() -> ScalarSelect[str]:
    """The current body of the enclosing query's `postings` row, decompressed on read.

    A correlated scalar subquery, so a reader keeps its own FROM and joins: label it
    `body_text` where `postings.c.body_text` stood. It reads `posting_blobs` by primary key, one
    lookup per row the outer query returns.
    """
    return (
        select(posting_blobs.c.body)
        .where(posting_blobs.c.posting_id == postings.c.id)
        .scalar_subquery()
    )


def posting_raw() -> ScalarSelect[Any]:
    """The provider payload of the enclosing query's `postings` row (`posting_body`'s twin)."""
    return (
        select(posting_blobs.c.raw)
        .where(posting_blobs.c.posting_id == postings.c.id)
        .scalar_subquery()
    )
