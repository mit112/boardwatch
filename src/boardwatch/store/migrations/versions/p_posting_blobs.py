"""T364 step 1: move each posting's body and provider payload out of `postings`.

`postings` held `body_text` and `raw_json` inline: about 17 KB of a row's 17.4 KB, so every
corpus-wide read walked roughly one 4 KiB page per posting over 25 GB. Now `posting_blobs` holds
both, zlib-compressed, one row per posting, and a `postings` row is a few hundred bytes. Three
facts the corpus reads took from the blobs stay on `postings` as plain columns:

- `body_trimmed_len`: the body's length once `" \\t\\n\\r\\f\\v"` is stripped from both ends;
  `queries.body_is_empty` reads `= 0`, and `ix_postings_corpus` carries it in place of the old
  `trim(body_text, ...) = ''` expression.
- `employment_type` and `jobapps_employer_url`: `json_extract` of `$.employmentType` and
  `$.jobapps.employer_url`, the two paths the queue and the ranker read out of `raw_json`.

A real rebuild, in one transaction. Steps:

1. Create `posting_blobs` and `postings_new` (the new shape).
2. Read `postings` once, in id order, in batches. For each row: compress the stored bytes of
   `body_text` and `raw_json` (threads; `zlib.compress` releases the GIL), check the compressed
   bytes decompress to the input, compute `body_trimmed_len` from the body, and write the
   `posting_blobs` row and the `postings_new` row with every other column copied as stored. A
   value of an unexpected storage class (a BLOB body, say) stops the migration
   (`PostingBlobUnexpectedValue`): the new columns could not give it back as it was.
3. Check, in one more read of the old table, that every old row has its new row with every column
   equal (`IS`, so NULLs compare), that its blob row decompresses to the old bytes, that
   `body_trimmed_len = 0` exactly where the old empty-body expression was true, and that the
   two `json_extract` columns equal the old expressions. A mismatch aborts and rolls back
   (`PostingBlobMismatch`).
4. Drop the old table (its indexes and triggers go with it), rename the new one into place, and
   recreate the indexes and both `postings_job_required_*` triggers.

The ids are unchanged: seven tables reference `postings.id`. Create-new, drop-old, rename-new, as
in `p_eligibility_snapshots`: renaming the OLD table aside would rewrite those foreign keys to
follow it. Alembic's connection does not enable foreign keys, so the drop does not check them.

ONE transaction, never committed here: alembic commits it together with the version stamp (see
`p_eligibility_snapshots` for why a COMMIT in this callback would leave a window with the new
schema under the old revision). The write-ahead log grows by the new tables (about 10 GB on the
maintainer's 52 GB store), and the file does not shrink until a VACUUM: the old table's pages join
the freelist.

Downgrade rebuilds the old shape from the blobs and checks it the same way, byte for byte.
"""

from __future__ import annotations

import os
import zlib
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "p_posting_blobs"
down_revision = "p_eligibility_snapshots"
branch_labels = None
depends_on = None

_BATCH = 5_000
_LEVEL = 6
_STRIP = " \t\n\r\f\v"
_STRIP_SQL = "char(32, 9, 10, 13, 12, 11)"
_EMPLOYMENT = "CASE WHEN json_valid({c}) THEN json_extract({c}, '$.employmentType') END"
_EMPLOYER_URL = "CASE WHEN json_valid({c}) THEN json_extract({c}, '$.jobapps.employer_url') END"

#: Every `postings` column the rebuild copies as stored, in the old table's order.
_KEPT = (
    "id", "company_id", "provider_posting_id", "title", "normalized_title", "url",
    "locations_json", "remote_policy", "department", "posted_at", "updated_at", "first_seen_at",
    "last_seen_at", "status", "closed_at", "consecutive_missing", "content_hash", "salary_min",
    "salary_max", "salary_currency", "salary_period", "job_id", "death_strikes",
    "last_death_probe_at",
)
_DERIVED = ("body_trimmed_len", "employment_type", "jobapps_employer_url")


class PostingBlobUnexpectedValue(RuntimeError):
    """A `body_text` or `raw_json` value whose storage class the new columns cannot give back."""

    def __init__(self, posting_id: int, column: str, storage_class: str) -> None:
        super().__init__(
            f"posting {posting_id}: {column} is stored as {storage_class}, not text"
        )
        self.posting_id = posting_id
        self.column = column
        self.storage_class = storage_class


class PostingBlobMismatch(RuntimeError):
    """The rebuilt tables do not reproduce the rows they replace."""

    def __init__(self, mismatched: int) -> None:
        super().__init__(f"{mismatched} postings do not resolve to their original columns and bytes")
        self.mismatched = mismatched


def _atomically(body: Callable[[], None]) -> None:
    conn = op.get_bind()
    # No COMMIT: alembic commits this transaction together with the version stamp (module docstring).
    conn.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        body()
    except BaseException:
        conn.exec_driver_sql("ROLLBACK")
        raise


def _driver() -> Any:
    """The sqlite3 connection under alembic's, for `executemany` and the check function."""
    return op.get_bind().connection.dbapi_connection


def _unz(value: bytes | None) -> bytes | None:
    return None if value is None else zlib.decompress(value)


def _register_unz() -> None:
    _driver().create_function("t364_unz", 1, _unz, deterministic=True)


def _workers() -> int:
    count: Callable[[], int | None] = getattr(os, "process_cpu_count", os.cpu_count)
    return max(1, count() or 1)


def _pack(item: tuple[bytes, bytes | None]) -> tuple[bytes, bytes | None]:
    body, raw = item
    packed = (zlib.compress(body, _LEVEL), None if raw is None else zlib.compress(raw, _LEVEL))
    # The compressed bytes are what step 3 decompresses, but a bad compression is cheaper to catch
    # here, on bytes already in memory, than in a second read of 23 GB.
    if zlib.decompress(packed[0]) != body or (
        raw is not None and zlib.decompress(packed[1] or b"") != raw
    ):
        raise PostingBlobMismatch(1)
    return packed


def _batches(select_sql: str) -> Iterator[Sequence[tuple[Any, ...]]]:
    """Rows of `select_sql` (which must take `id > ?` and `LIMIT ?` and return id first) in id order."""
    cursor = _driver().cursor()
    last = -1
    while True:
        rows = cursor.execute(select_sql, (last, _BATCH)).fetchall()
        if not rows:
            return
        yield rows
        last = int(rows[-1][0])


def _create_postings_new(*, blobs_inline: bool) -> None:
    """`postings_new` in the shape after (no blobs) or before (`blobs_inline`)."""
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("provider_posting_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("locations_json", sa.JSON(), nullable=True),
        sa.Column("remote_policy", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_missing", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
    ]
    if blobs_inline:
        columns += [
            sa.Column("body_text", sa.Text(), nullable=False),
            sa.Column("raw_json", sa.JSON(), nullable=True),
        ]
    columns += [
        sa.Column("salary_min", sa.Numeric(), nullable=True),
        sa.Column("salary_max", sa.Numeric(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("salary_period", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("death_strikes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_death_probe_at", sa.DateTime(), nullable=True),
    ]
    if not blobs_inline:
        columns += [
            sa.Column("body_trimmed_len", sa.Integer(), nullable=False),
            sa.Column("employment_type", sa.Text(), nullable=True),
            sa.Column("jobapps_employer_url", sa.Text(), nullable=True),
        ]
    op.create_table(
        "postings_new",
        *columns,
        sa.CheckConstraint(
            "remote_policy IN ('remote', 'hybrid', 'onsite', 'unknown')",
            name=op.f("ck_postings_remote_policy_enum"),
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_postings_status_enum")),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_postings_company_id_companies")
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_postings_job_id_jobs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_postings")),
        sa.UniqueConstraint(
            "company_id", "provider_posting_id",
            name=op.f("uq_postings_company_id_provider_posting_id"),
        ),
    )


def _swap_in_postings_new(*, blobs_inline: bool) -> None:
    op.execute("DROP TABLE postings")
    op.execute("ALTER TABLE postings_new RENAME TO postings")
    op.create_index("ix_postings_status_posted_at", "postings", ["status", "posted_at"])
    op.create_index("ix_postings_content_hash", "postings", ["content_hash"])
    op.create_index("ix_postings_job_id", "postings", ["job_id"])
    if blobs_inline:
        op.execute(
            "CREATE INDEX ix_postings_corpus ON postings (status, company_id, provider_posting_id, "
            f"(trim(body_text, {_STRIP_SQL}) = ''), content_hash)"
        )
    else:
        op.create_index(
            "ix_postings_corpus", "postings",
            ["status", "company_id", "provider_posting_id", "body_trimmed_len", "content_hash"],
        )
    op.create_index("ix_postings_id_status", "postings", ["id", "status"])
    for event, when in (("INSERT", "INSERT"), ("UPDATE", "UPDATE OF job_id")):
        op.execute(
            f"CREATE TRIGGER postings_job_required_{event.lower()} BEFORE {when} ON postings "
            "WHEN NEW.job_id IS NULL BEGIN SELECT RAISE(ABORT, 'postings.job_id is required'); END"
        )


def _same_kept_columns(old: str, new: str) -> str:
    return " OR ".join(f"{new}.{c} IS NOT {old}.{c}" for c in _KEPT)


def _unresolved_upgrade() -> int:
    return int(op.get_bind().exec_driver_sql(
        "SELECT COUNT(*) FROM postings o "
        "LEFT JOIN postings_new n ON n.id = o.id "
        "LEFT JOIN posting_blobs b ON b.posting_id = o.id "
        "WHERE n.id IS NULL OR b.posting_id IS NULL OR "
        + _same_kept_columns("o", "n")
        + " OR t364_unz(b.body) IS NOT CAST(o.body_text AS BLOB)"
        " OR t364_unz(b.raw) IS NOT CAST(o.raw_json AS BLOB)"
        f" OR (n.body_trimmed_len = 0) IS NOT (trim(o.body_text, {_STRIP_SQL}) = '')"
        " OR n.employment_type IS NOT " + _EMPLOYMENT.format(c="o.raw_json")
        + " OR n.jobapps_employer_url IS NOT " + _EMPLOYER_URL.format(c="o.raw_json")
    ).scalar_one()) + _count_difference("postings", "postings_new") + _count_difference(
        "postings", "posting_blobs"
    )


def _count_difference(a: str, b: str) -> int:
    counts = [
        int(op.get_bind().exec_driver_sql(f"SELECT COUNT(*) FROM {t}").scalar_one())
        for t in (a, b)
    ]
    return abs(counts[0] - counts[1])


def upgrade() -> None:
    def rebuild() -> None:
        op.create_table(
            "posting_blobs",
            sa.Column("posting_id", sa.Integer(), nullable=False),
            sa.Column("body", sa.LargeBinary(), nullable=False),
            sa.Column("raw", sa.LargeBinary(), nullable=True),
            sa.ForeignKeyConstraint(
                ["posting_id"], ["postings.id"], name=op.f("fk_posting_blobs_posting_id_postings")
            ),
            sa.PrimaryKeyConstraint("posting_id", name=op.f("pk_posting_blobs")),
        )
        _create_postings_new(blobs_inline=False)
        kept = ", ".join(_KEPT)
        select_sql = (
            f"SELECT {kept}, typeof(body_text), CAST(body_text AS BLOB), typeof(raw_json), "
            f"CAST(raw_json AS BLOB), {_EMPLOYMENT.format(c='raw_json')}, "
            f"{_EMPLOYER_URL.format(c='raw_json')} "
            "FROM postings WHERE id > ? ORDER BY id LIMIT ?"
        )
        insert_new = (
            f"INSERT INTO postings_new ({kept}, {', '.join(_DERIVED)}) "
            f"VALUES ({', '.join('?' * (len(_KEPT) + len(_DERIVED)))})"
        )
        width = len(_KEPT)
        driver = _driver()
        with ThreadPoolExecutor(_workers()) as pool:
            for rows in _batches(select_sql):
                for row in rows:
                    body_class, raw_class = row[width], row[width + 2]
                    if body_class != "text":
                        raise PostingBlobUnexpectedValue(int(row[0]), "body_text", body_class)
                    if raw_class not in ("text", "null"):
                        raise PostingBlobUnexpectedValue(int(row[0]), "raw_json", raw_class)
                packed = list(pool.map(
                    _pack, [(row[width + 1], row[width + 3]) for row in rows], chunksize=64
                ))
                driver.executemany(
                    "INSERT INTO posting_blobs (posting_id, body, raw) VALUES (?, ?, ?)",
                    [(row[0], body, raw) for row, (body, raw) in zip(rows, packed, strict=True)],
                )
                driver.executemany(insert_new, [
                    (
                        *row[:width],
                        len(row[width + 1].decode("utf-8", "replace").strip(_STRIP)),
                        row[width + 4],
                        row[width + 5],
                    )
                    for row in rows
                ])
        _register_unz()
        bad = _unresolved_upgrade()
        if bad:
            raise PostingBlobMismatch(bad)
        _swap_in_postings_new(blobs_inline=False)

    _atomically(rebuild)


def downgrade() -> None:
    def rebuild() -> None:
        _register_unz()
        _create_postings_new(blobs_inline=True)
        columns = (*_KEPT[:17], "body_text", "raw_json", *_KEPT[17:])
        values = ", ".join(
            "CAST(t364_unz(b.body) AS TEXT)" if c == "body_text"
            else "CAST(t364_unz(b.raw) AS TEXT)" if c == "raw_json"
            else f"p.{c}"
            for c in columns
        )
        op.execute(
            f"INSERT INTO postings_new ({', '.join(columns)}) SELECT {values} "
            "FROM postings p JOIN posting_blobs b ON b.posting_id = p.id ORDER BY p.id"
        )
        bad = int(op.get_bind().exec_driver_sql(
            "SELECT COUNT(*) FROM postings p "
            "LEFT JOIN postings_new o ON o.id = p.id "
            "LEFT JOIN posting_blobs b ON b.posting_id = p.id "
            "WHERE o.id IS NULL OR b.posting_id IS NULL OR "
            + _same_kept_columns("p", "o")
            + " OR CAST(o.body_text AS BLOB) IS NOT t364_unz(b.body)"
            " OR CAST(o.raw_json AS BLOB) IS NOT t364_unz(b.raw)"
        ).scalar_one()) + _count_difference("postings", "postings_new")
        if bad:
            raise PostingBlobMismatch(bad)
        op.execute("DROP TABLE posting_blobs")
        _swap_in_postings_new(blobs_inline=True)

    _atomically(rebuild)
