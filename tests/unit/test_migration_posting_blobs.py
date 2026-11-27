"""T364 step 1: `postings` loses `body_text` and `raw_json` to `posting_blobs`.

Built at the PREVIOUS head, seeded in the old shape with raw SQL, then upgraded, so the migration is
the only thing between the two readings. Every expected value is a literal from this file: the
derived columns are spelled out per row, not recomputed by the rule under test.
"""

import importlib.util
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from boardwatch.store.db import ensure_schema, get_engine

BASE = "p_eligibility_snapshots"
HEAD = "p_posting_blobs"
MIGRATIONS = Path("src/boardwatch/store/migrations")

_OLD_COLUMNS = (
    "id, company_id, provider_posting_id, title, normalized_title, url, locations_json, "
    "remote_policy, department, posted_at, updated_at, first_seen_at, last_seen_at, status, "
    "closed_at, consecutive_missing, content_hash, salary_min, salary_max, salary_currency, "
    "salary_period, job_id, death_strikes, last_death_probe_at"
)

#: (id, body_text, raw_json, salary_min, expected body_trimmed_len, employment_type, employer_url).
#: Ids skip numbers and other tables point at them, so a rebuild that renumbered breaks the keys.
POSTINGS: list[tuple[int, str, str | None, object, int, str | None, str | None]] = [
    (3, " \t Héllo wörld \n", '{"employmentType": "Contract", "x": [1, 2]}', 90000, 11,
     "Contract", None),
    (7, " \t\n\r\f\v", None, None, 0, None, None),
    (12, "", "null", 1.5, 0, None, None),
    # U+00A0 is not in the strip set, so this body is NOT empty (the old expression agreed).
    (13, " ", '{"employmentType": 3}', None, 1, "3", None),
    (20, "x", '{"jobapps": {"employer_url": "https://acme.example/jobs/1"}}', None, 1, None,
     "https://acme.example/jobs/1"),
    # Not valid JSON for SQLite: the derived columns read NULL instead of failing the rebuild.
    (41, "body", '{"employmentType": NaN}', None, 4, None, None),
]


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _migration() -> ModuleType:
    path = MIGRATIONS / "versions" / "p_posting_blobs.py"
    spec = importlib.util.spec_from_file_location("p_posting_blobs_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(engine: Engine, extra_sql: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO companies (name, provider, slug, source, watched) "
                          "VALUES ('Acme','greenhouse','acme','user',1)"))
        for pid, body, raw, salary, *_ in POSTINGS:
            conn.execute(text("INSERT INTO jobs (id, created_at) VALUES (:id, '2026-01-01 00:00:00')"),
                         {"id": pid})
            conn.execute(
                text("INSERT INTO postings (id, company_id, job_id, provider_posting_id, title, "
                     "normalized_title, url, locations_json, remote_policy, first_seen_at, "
                     "last_seen_at, status, consecutive_missing, content_hash, body_text, raw_json, "
                     "salary_min) VALUES (:id, 1, :id, :ppid, 'Engineer', 'engineer', :url, "
                     "'[\"Austin, TX\"]', 'unknown', '2026-01-01 00:00:00.123456', "
                     "'2026-01-02 00:00:00', :status, 0, :hash, :body, :raw, :salary)"),
                {"id": pid, "ppid": f"p-{pid}", "url": None if pid == 7 else f"https://x/{pid}",
                 "status": "closed" if pid == 12 else "open", "hash": f"h{pid}", "body": body,
                 "raw": raw, "salary": salary},
            )
            conn.execute(text(
                "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at, "
                "run_id, capture_reason) VALUES (:id, :hash, :body, '2026-01-01 00:00:00', NULL, 'new')"),
                {"id": pid, "hash": f"h{pid}", "body": body})
        if extra_sql:
            conn.execute(text(extra_sql))


def _store(tmp_path: Path) -> tuple[Config, Engine]:
    url = f"sqlite:///{tmp_path / 'store.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, BASE)
    return cfg, create_engine(url, poolclass=NullPool)


def _old_rows(engine: Engine) -> list[tuple[object, ...]]:
    """Every column as stored, the two blobs as their stored bytes."""
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            f"SELECT {_OLD_COLUMNS}, CAST(body_text AS BLOB), CAST(raw_json AS BLOB), "
            "typeof(salary_min) FROM postings ORDER BY id"))]


def _new_rows(engine: Engine) -> list[tuple[object, ...]]:
    """The same reading through the new shape, decompressing each blob."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT {', '.join('p.' + c.strip() for c in _OLD_COLUMNS.split(','))}, b.body, b.raw, "
            "typeof(p.salary_min) FROM postings p JOIN posting_blobs b ON b.posting_id = p.id "
            "ORDER BY p.id")).all()
    return [
        (*r[:24], zlib.decompress(r[24]), None if r[25] is None else zlib.decompress(r[25]), r[26])
        for r in rows
    ]


def _schema(engine: Engine) -> dict[str, str | None]:
    with engine.connect() as conn:
        return {name: sql for name, sql in conn.execute(text(
            "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))}


def _revision(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def test_every_posting_keeps_its_columns_and_its_stored_bytes(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    before = _old_rows(engine)
    assert [r[24] for r in before] == [p[1].encode() for p in POSTINGS]  # premise: stored bytes

    command.upgrade(cfg, HEAD)

    assert _new_rows(engine) == before
    with engine.connect() as conn:
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(postings)"))]
    assert "body_text" not in columns and "raw_json" not in columns


def test_the_derived_columns_hold_the_old_expressions_values(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        got = [tuple(r) for r in conn.execute(text(
            "SELECT id, body_trimmed_len, employment_type, jobapps_employer_url FROM postings "
            "ORDER BY id"))]
    assert got == [(p[0], p[4], p[5], p[6]) for p in POSTINGS]


def test_the_blobs_are_zlib_and_a_null_payload_stays_null(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        raw = dict(conn.execute(text("SELECT posting_id, raw FROM posting_blobs")).all())
    assert raw[7] is None  # SQL NULL in, SQL NULL out
    assert zlib.decompress(raw[12]) == b"null"  # JSON null text is kept as text


def test_other_tables_still_point_at_the_same_ids_and_the_constraints_hold(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        assert [r[0] for r in conn.execute(text(
            "SELECT posting_id FROM posting_versions ORDER BY id"))] == [p[0] for p in POSTINGS]
        fks = {(r[2], r[3], r[4]) for r in conn.execute(text("PRAGMA foreign_key_list(posting_versions)"))}
        assert ("postings", "posting_id", "id") in fks
        assert {(r[2], r[3]) for r in conn.execute(text("PRAGMA foreign_key_list(posting_blobs)"))} == {
            ("postings", "posting_id")}
        assert [r[2] for r in conn.execute(text("PRAGMA index_info(ix_postings_corpus)"))] == [
            "status", "company_id", "provider_posting_id", "body_trimmed_len", "content_hash"]
        with pytest.raises(IntegrityError, match="postings.job_id is required"):
            conn.execute(text(
                "INSERT INTO postings (company_id, provider_posting_id, title, normalized_title, "
                "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, "
                "content_hash, body_trimmed_len) VALUES (1, 'p-new', 'E', 'e', 'unknown', "
                "'2026-01-01', '2026-01-01', 'open', 0, 'h', 0)"))
        with pytest.raises(IntegrityError, match="postings.job_id is required"):
            conn.execute(text("UPDATE postings SET job_id = NULL WHERE id = 3"))
        with pytest.raises(IntegrityError, match="UNIQUE"):
            conn.execute(text(
                "INSERT INTO postings (company_id, job_id, provider_posting_id, title, "
                "normalized_title, remote_policy, first_seen_at, last_seen_at, status, "
                "consecutive_missing, content_hash, body_trimmed_len) VALUES (1, 3, 'p-3', 'E', "
                "'e', 'unknown', '2026-01-01', '2026-01-01', 'open', 0, 'h', 0)"))


def test_the_rebuild_reads_the_old_table_in_batches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Batches of 2 over 6 rows whose ids skip numbers: every row lands once, none twice."""
    _, engine = _store(tmp_path)
    _seed(engine)
    before = _old_rows(engine)
    migration = _migration()
    monkeypatch.setattr(migration, "_BATCH", 2)
    with engine.connect() as conn, Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()
        conn.commit()
    assert _new_rows(engine) == before


def test_a_body_not_stored_as_text_stops_the_migration(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine, "UPDATE postings SET body_text = CAST(body_text AS BLOB) WHERE id = 20")
    schema_before, rows_before = _schema(engine), _old_rows(engine)

    # Alembic imports its own copy of the migration module, so the class is matched by name.
    with pytest.raises(RuntimeError) as caught:
        command.upgrade(cfg, HEAD)

    assert type(caught.value).__name__ == "PostingBlobUnexpectedValue"
    assert (caught.value.posting_id, caught.value.column) == (20, "body_text")  # type: ignore[attr-defined]
    assert _schema(engine) == schema_before
    assert _old_rows(engine) == rows_before
    assert _revision(engine) == BASE


def test_a_failed_check_rolls_the_whole_rebuild_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, engine = _store(tmp_path)
    _seed(engine)
    schema_before, rows_before = _schema(engine), _old_rows(engine)
    migration = _migration()
    monkeypatch.setattr(migration, "_unresolved_upgrade", lambda: 1)
    with engine.connect() as conn, Operations.context(MigrationContext.configure(conn)):
        with pytest.raises(migration.PostingBlobMismatch):
            migration.upgrade()
    assert _schema(engine) == schema_before
    assert _old_rows(engine) == rows_before


def test_the_check_catches_a_blob_that_does_not_decompress_to_the_old_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check is not vacuous: a compressor that drops one byte of one body fails it."""
    _, engine = _store(tmp_path)
    _seed(engine)
    rows_before = _old_rows(engine)
    migration = _migration()

    def lossy(item: tuple[bytes, bytes | None]) -> tuple[bytes, bytes | None]:
        # `_pack` without its in-memory check, so the SQL check is the one under test.
        body, raw = item
        return zlib.compress(body[:-1] if body == b"body" else body), (
            None if raw is None else zlib.compress(raw))

    monkeypatch.setattr(migration, "_pack", lossy)
    with engine.connect() as conn, Operations.context(MigrationContext.configure(conn)):
        with pytest.raises(migration.PostingBlobMismatch) as caught:
            migration.upgrade()
    assert caught.value.mismatched == 1
    assert _old_rows(engine) == rows_before


def test_downgrade_restores_the_old_shape_and_bytes(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    rows_before, schema_before = _old_rows(engine), _schema(engine)

    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)

    assert _old_rows(engine) == rows_before
    schema_after = _schema(engine)
    assert "posting_blobs" not in schema_after
    assert set(schema_after) == set(schema_before)  # tables, indexes, triggers: the same names
    for name, sql in schema_before.items():
        # The table's own DDL differs in column order and quoting (its `job_id` foreign key was
        # added by ALTER TABLE, unnamed); its indexes and triggers must come back word for word.
        if name != "postings":
            assert schema_after[name] == sql, name
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []


def test_a_second_upgrade_after_a_round_trip_gives_the_same_rows(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    before = _old_rows(engine)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    assert _new_rows(engine) == before


def test_downgrade_refuses_a_posting_whose_blob_row_is_missing(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM posting_blobs WHERE posting_id = 13"))
    with pytest.raises(RuntimeError) as caught:
        command.downgrade(cfg, BASE)
    assert type(caught.value).__name__ == "PostingBlobMismatch"
    assert _revision(engine) == HEAD
    with engine.connect() as conn:  # rolled back: still the new shape
        assert conn.execute(text("SELECT COUNT(*) FROM posting_blobs")).scalar_one() == len(POSTINGS) - 1


class _StampRefused(RuntimeError):
    """Raised in place of alembic's `UPDATE alembic_version`, as a kill at that moment would."""


@contextmanager
def _refusing_the_version_stamp() -> Iterator[list[str]]:
    refused: list[str] = []

    def hook(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("UPDATE ALEMBIC_VERSION"):
            refused.append(statement)
            raise _StampRefused

    event.listen(Engine, "before_cursor_execute", hook)
    try:
        yield refused
    finally:
        event.remove(Engine, "before_cursor_execute", hook)


def test_a_failed_version_stamp_undoes_the_rebuild_and_a_retry_succeeds(tmp_path: Path) -> None:
    """Through `ensure_schema`, the entry point every command uses: a kill at the stamp leaves the
    old schema under the old revision, and the next ordinary start migrates."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    url = f"sqlite:///{data_dir / 'boardwatch.db'}"
    command.upgrade(_cfg(url), BASE)
    engine = create_engine(url, poolclass=NullPool)
    _seed(engine)
    schema_before, rows_before = _schema(engine), _old_rows(engine)

    app_engine = get_engine(data_dir)
    try:
        with _refusing_the_version_stamp() as refused, pytest.raises(_StampRefused):
            ensure_schema(app_engine)
        assert refused
        assert _schema(engine) == schema_before
        assert _old_rows(engine) == rows_before
        assert _revision(engine) == BASE

        ensure_schema(app_engine)
    finally:
        app_engine.dispose()
    assert _revision(engine) == HEAD
    assert _new_rows(engine) == rows_before
