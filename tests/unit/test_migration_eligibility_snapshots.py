"""T363: `eligibility_inputs` keeps each snapshot once, in `eligibility_snapshots`.

Proven the way a backfill has to be: the store is built at the PREVIOUS head, seeded with rows in the
old shape, then upgraded, so the migration is the only thing between the two snapshots.

The seeded snapshots are NOT canonical JSON (key order and spacing differ from `json.dumps` with
sorted keys), and every expected value below is a literal from this file. A migration that
re-serialised, or that compared hashes instead of stored bytes, would not return them.
"""

import importlib.util
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

BASE = "p_listing_runs"
HEAD = "p_eligibility_snapshots"
MIGRATIONS = Path("src/boardwatch/store/migrations")

#: Stored bytes, deliberately not canonical: spaces after the separators and unsorted keys.
PROFILE_A = '{"fields": {"z": 1, "a": [2, 1]}, "v": 1}'
PROFILE_B = '{"v": 2, "fields": {}}'
RULES_X = '{"catalog_version": "x",  "rules": ["b", "a"]}'
RULES_Y = '{"rules": [], "catalog_version": "y"}'

#: (input id, profile hash, profile bytes, rules hash, rules bytes). Ids skip numbers and the
#: evaluations point at them, so a rebuild that renumbered would break the foreign key.
INPUTS = [
    (3, "pa", PROFILE_A, "rx", RULES_X),
    (7, "pa", PROFILE_A, "ry", RULES_Y),
    (12, "pb", PROFILE_B, "rx", RULES_X),
    (40, "pa", PROFILE_A, "rx", RULES_X),
]


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _migration() -> ModuleType:
    path = MIGRATIONS / "versions" / "p_eligibility_snapshots.py"
    spec = importlib.util.spec_from_file_location("p_eligibility_snapshots_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(engine: Engine, inputs: list[tuple[int, str, str, str, str]] = INPUTS) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO companies (name, provider, slug, source, watched) "
                          "VALUES ('Acme','greenhouse','acme','user',1)"))
        conn.execute(text("INSERT INTO jobs (created_at) VALUES ('2026-01-01 00:00:00')"))
        conn.execute(text(
            "INSERT INTO postings (company_id, job_id, provider_posting_id, title, normalized_title, "
            "remote_policy, first_seen_at, last_seen_at, status, consecutive_missing, content_hash, "
            "body_text) VALUES (1,1,'p-1','E','e','unknown','2026-01-01 00:00:00',"
            "'2026-01-01 00:00:00','open',0,'h1','b1')"))
        conn.execute(text(
            "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at, run_id, "
            "capture_reason) VALUES (1,'h1','b1','2026-01-01 00:00:00',NULL,'new')"))
        for input_id, p_hash, p_json, r_hash, r_json in inputs:
            conn.execute(
                text("INSERT INTO eligibility_inputs (id, posting_version_id, profile_hash, "
                     "profile_snapshot_json, rules_hash, rules_snapshot_json, input_fingerprint, "
                     "created_at) VALUES (:id, 1, :ph, :pj, :rh, :rj, :fp, '2026-01-02 03:04:05')"),
                {"id": input_id, "ph": p_hash, "pj": p_json, "rh": r_hash, "rj": r_json,
                 "fp": f"fp{input_id}"},
            )
            conn.execute(
                text("INSERT INTO eligibility_evaluations (input_id, engine_kind, engine_version, "
                     "verdict, score, created_at) VALUES (:id,'deterministic','1','eligible',1.0,"
                     "'2026-01-02 00:00:00')"),
                {"id": input_id},
            )


def _store(tmp_path: Path) -> tuple[Config, Engine]:
    url = f"sqlite:///{tmp_path / 'store.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, BASE)
    return cfg, create_engine(url, poolclass=NullPool)


def _old_rows(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            "SELECT id, posting_version_id, profile_hash, profile_snapshot_json, rules_hash, "
            "rules_snapshot_json, input_fingerprint, created_at FROM eligibility_inputs ORDER BY id"))]


def _resolved_rows(engine: Engine) -> list[tuple[object, ...]]:
    """The same rows, taking each snapshot through the hash."""
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            "SELECT i.id, i.posting_version_id, i.profile_hash, p.snapshot_json, i.rules_hash, "
            "r.snapshot_json, i.input_fingerprint, i.created_at FROM eligibility_inputs i "
            "JOIN eligibility_snapshots p ON p.kind = 'profile' AND p.hash = i.profile_hash "
            "JOIN eligibility_snapshots r ON r.kind = 'rules' AND r.hash = i.rules_hash "
            "ORDER BY i.id"))]


def _schema(engine: Engine) -> dict[str, str | None]:
    with engine.connect() as conn:
        return {name: sql for name, sql in conn.execute(text(
            "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))}


def test_every_input_resolves_to_its_original_stored_bytes(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    before = _old_rows(engine)
    assert [row[3] for row in before] == [PROFILE_A, PROFILE_A, PROFILE_B, PROFILE_A]  # premise

    command.upgrade(cfg, HEAD)

    # Each snapshot once: one profile row per hash and one rules row per hash, with the seeded bytes.
    with engine.connect() as conn:
        snapshots = sorted(tuple(r) for r in conn.execute(
            text("SELECT kind, hash, snapshot_json FROM eligibility_snapshots")))
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(eligibility_inputs)"))]
    assert snapshots == [
        ("profile", "pa", PROFILE_A), ("profile", "pb", PROFILE_B),
        ("rules", "rx", RULES_X), ("rules", "ry", RULES_Y),
    ]
    assert "profile_snapshot_json" not in columns and "rules_snapshot_json" not in columns
    # Every id, with every other column and both snapshots' bytes, as before.
    assert _resolved_rows(engine) == before


def test_evaluations_still_point_at_the_same_input_ids(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert [r[0] for r in conn.execute(text(
            "SELECT input_id FROM eligibility_evaluations ORDER BY id"))] == [3, 7, 12, 40]
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        fks = [(r[2], r[3], r[4]) for r in conn.execute(
            text("PRAGMA foreign_key_list(eligibility_evaluations)"))]
        assert ("eligibility_inputs", "input_id", "id") in fks
        # The rebuilt table's own foreign key and unique fingerprint survived.
        assert [(r[2], r[3]) for r in conn.execute(
            text("PRAGMA foreign_key_list(eligibility_inputs)"))] == [("posting_versions", "posting_version_id")]
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO eligibility_inputs (posting_version_id, profile_hash, "
                              "rules_hash, input_fingerprint, created_at) "
                              "VALUES (1,'pa','rx','fp3','2026-01-02 00:00:00')"))


@pytest.mark.parametrize("table", ["eligibility_inputs", "eligibility_snapshots"])
def test_the_recreated_triggers_still_refuse_update_and_delete(tmp_path: Path, table: str) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    column = "profile_hash" if table == "eligibility_inputs" else "snapshot_json"
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match=f"{table} is append-only"):
            conn.execute(text(f"UPDATE {table} SET {column} = 'x'"))
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match=f"{table} is append-only"):
            conn.execute(text(f"DELETE FROM {table}"))
    with engine.connect() as conn:
        assert conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() > 0


def test_the_upgrade_keeps_the_identity_index(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    command.upgrade(cfg, HEAD)
    with engine.connect() as conn:
        cols = [r[2] for r in conn.execute(
            text("PRAGMA index_info(ix_eligibility_inputs_version_identity)"))]
    assert cols == ["posting_version_id", "profile_hash", "rules_hash"]


@pytest.mark.parametrize(
    ("conflict", "kind"),
    [
        # Same hash, different bytes: only the key order differs, which is exactly what a hash of
        # canonical JSON cannot see.
        ((41, "pa", '{"v": 1, "fields": {"z": 1, "a": [2, 1]}}', "rx", RULES_X), "profile"),
        ((41, "pa", PROFILE_A, "rx", '{"rules": ["b", "a"], "catalog_version": "x"}'), "rules"),
    ],
)
def test_two_rows_with_one_hash_and_different_bytes_stop_the_migration(
    tmp_path: Path, conflict: tuple[int, str, str, str, str], kind: str
) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine, [*INPUTS, conflict])
    schema_before = _schema(engine)
    rows_before = _old_rows(engine)

    # Alembic imports its own copy of the migration module, so the class is matched by name.
    with pytest.raises(RuntimeError) as caught:
        command.upgrade(cfg, HEAD)

    assert type(caught.value).__name__ == "EligibilitySnapshotConflict"
    assert caught.value.kind == kind  # type: ignore[attr-defined]
    # Nothing moved: same schema text, same rows, same revision.
    assert _schema(engine) == schema_before
    assert _old_rows(engine) == rows_before
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == BASE


def test_a_failed_check_rolls_the_whole_rebuild_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Alembic's SQLite impl has no transactional DDL: without the migration's own BEGIN, the
    snapshot table and `eligibility_inputs_new` would already be committed when the check fails."""
    cfg, engine = _store(tmp_path)
    _seed(engine)
    schema_before = _schema(engine)
    rows_before = _old_rows(engine)

    migration = _migration()
    monkeypatch.setattr(migration, "_unresolved", lambda **_: 2)
    with engine.connect() as conn, Operations.context(MigrationContext.configure(conn)):
        with pytest.raises(migration.EligibilitySnapshotMismatch):
            migration.upgrade()

    assert _schema(engine) == schema_before
    assert _old_rows(engine) == rows_before


def test_downgrade_restores_the_old_shape_and_bytes(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    rows_before = _old_rows(engine)
    schema_before = _schema(engine)

    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)

    assert _old_rows(engine) == rows_before  # every id, every column, the seeded bytes
    schema_after = _schema(engine)
    assert "eligibility_snapshots" not in schema_after
    assert set(schema_after) == set(schema_before)  # tables, indexes, triggers: the same names
    for name, sql in schema_before.items():
        if name != "eligibility_inputs":  # SQLite quotes a renamed table's name in its DDL
            assert schema_after[name] == sql, name
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match="eligibility_inputs is append-only"):
            conn.execute(text("DELETE FROM eligibility_inputs"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []


def test_a_second_upgrade_after_a_round_trip_gives_the_same_snapshots(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    before = _old_rows(engine)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    assert _resolved_rows(engine) == before


def test_downgrade_refuses_an_input_whose_snapshot_is_missing(tmp_path: Path) -> None:
    cfg, engine = _store(tmp_path)
    _seed(engine)
    command.upgrade(cfg, HEAD)
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER eligibility_snapshots_no_delete"))
        conn.execute(text("DELETE FROM eligibility_snapshots WHERE kind = 'rules' AND hash = 'ry'"))
    with pytest.raises(IntegrityError):
        command.downgrade(cfg, BASE)
    with engine.connect() as conn:  # rolled back: still the new shape
        assert conn.execute(text("SELECT COUNT(*) FROM eligibility_snapshots")).scalar_one() == 3
        assert "profile_snapshot_json" not in [
            r[1] for r in conn.execute(text("PRAGMA table_info(eligibility_inputs)"))]


class _StampRefused(RuntimeError):
    """Raised in place of alembic's `UPDATE alembic_version`, as a kill at that moment would."""


@contextmanager
def _refusing_the_version_stamp() -> Iterator[list[str]]:
    """Fail the statement that stamps the revision, on every engine, alembic's own included."""
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


def _revision(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def test_a_failed_version_stamp_undoes_the_rebuild_and_a_retry_succeeds(tmp_path: Path) -> None:
    """The window a COMMIT inside the migration would open: schema rebuilt, revision not yet stamped.

    Driven through `ensure_schema`, the entry point every command uses, with the stamp forced to
    fail. The store must be exactly as it was (schema text, rows, revision), and the next ordinary
    start must then succeed; with the old code it failed on the missing JSON columns."""
    data_dir = tmp_path / "data"
    url = f"sqlite:///{data_dir / 'boardwatch.db'}"
    data_dir.mkdir()
    command.upgrade(_cfg(url), BASE)
    engine = create_engine(url, poolclass=NullPool)
    _seed(engine)
    schema_before, rows_before = _schema(engine), _old_rows(engine)

    app_engine = get_engine(data_dir)
    try:
        with _refusing_the_version_stamp() as refused, pytest.raises(_StampRefused):
            ensure_schema(app_engine)
        assert refused  # premise: the migration ran and reached the stamp
        assert _schema(engine) == schema_before
        assert _old_rows(engine) == rows_before
        assert _revision(engine) == BASE

        ensure_schema(app_engine)  # the retry
    finally:
        app_engine.dispose()
    assert _revision(engine) == HEAD
    assert _resolved_rows(engine) == rows_before


def test_a_failed_version_stamp_undoes_the_downgrade_and_a_retry_succeeds(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'store.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, BASE)
    engine = create_engine(url, poolclass=NullPool)
    _seed(engine)
    rows_before = _old_rows(engine)
    command.upgrade(cfg, HEAD)
    schema_new = _schema(engine)

    with _refusing_the_version_stamp() as refused, pytest.raises(_StampRefused):
        command.downgrade(cfg, BASE)
    assert refused
    assert _schema(engine) == schema_new
    assert _resolved_rows(engine) == rows_before
    assert _revision(engine) == HEAD

    command.downgrade(cfg, BASE)  # the retry
    assert _revision(engine) == BASE
    assert _old_rows(engine) == rows_before
