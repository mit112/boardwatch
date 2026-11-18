"""T317: the funnel records the store file's size. Every expected number is a byte count written
by the test itself, never read back from the code under test."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from boardwatch.pipeline import funnel_writer
from boardwatch.pipeline.funnel_writer import read_store_size
from boardwatch.reports.run_funnel import (
    ARTIFACT_VERSION,
    StoreSize,
    funnel_to_dict,
    funnel_to_markdown,
)
from tests.unit.test_run_funnel import funnel


def _engine(db: Path):  # type: ignore[no-untyped-def]
    return create_engine(f"sqlite:///{db}")


def test_the_db_and_its_wal_are_measured_by_stat(tmp_path: Path) -> None:
    db = tmp_path / "boardwatch.db"
    db.write_bytes(b"x" * 1234)
    (tmp_path / "boardwatch.db-wal").write_bytes(b"y" * 56)

    assert read_store_size(_engine(db)) == StoreSize(db_bytes=1234, wal_bytes=56)


def test_an_absent_wal_is_zero_but_an_absent_db_is_null(tmp_path: Path) -> None:
    db = tmp_path / "boardwatch.db"
    db.write_bytes(b"x" * 10)
    assert read_store_size(_engine(db)) == StoreSize(db_bytes=10, wal_bytes=0)

    assert read_store_size(_engine(tmp_path / "gone.db")) == StoreSize(db_bytes=None, wal_bytes=0)


def test_a_failing_stat_records_null_and_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "boardwatch.db"
    db.write_bytes(b"x" * 10)
    (tmp_path / "boardwatch.db-wal").write_bytes(b"y" * 7)
    real = os.stat

    def stat(path: str | os.PathLike[str], *a: object, **k: object) -> os.stat_result:
        if str(path).endswith(".db"):
            raise PermissionError("denied")
        return real(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(funnel_writer.os, "stat", stat)

    assert read_store_size(_engine(db)) == StoreSize(db_bytes=None, wal_bytes=7)


def test_a_store_with_no_file_behind_it_is_not_recorded() -> None:
    assert read_store_size(create_engine("sqlite://")) is None


def test_the_section_is_published_and_a_funnel_without_one_says_null() -> None:
    recorded = replace(funnel(), store_size=StoreSize(db_bytes=1234, wal_bytes=0))

    assert funnel_to_dict(recorded)["store_size"] == {"db_bytes": 1234, "wal_bytes": 0}
    assert "db 1,234 bytes · wal 0 bytes" in funnel_to_markdown(recorded)

    assert funnel_to_dict(funnel())["store_size"] is None
    assert "NOT RECORDED" in funnel_to_markdown(funnel()).split("## Store size", 1)[1]
    unreadable = replace(funnel(), store_size=StoreSize(db_bytes=None, wal_bytes=0))
    assert funnel_to_dict(unreadable)["store_size"] == {"db_bytes": None, "wal_bytes": 0}
    assert "db unreadable" in funnel_to_markdown(unreadable)


def test_a_new_top_level_key_does_not_bump_the_artifact_version() -> None:
    """Held at 9 on the `buried` / `direct_share` precedent (see the comment above the constant)."""
    assert ARTIFACT_VERSION == 9
    assert funnel_to_dict(funnel())["artifact_version"] == 9


def test_a_symlinked_store_reads_the_wal_beside_its_target(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "boardwatch.db").write_bytes(b"x" * 10)
    (real / "boardwatch.db-wal").write_bytes(b"y" * 7)
    link = tmp_path / "boardwatch.db"
    link.symlink_to(real / "boardwatch.db")

    got = read_store_size(create_engine(f"sqlite:///{link}"))
    assert got is not None and (got.db_bytes, got.wal_bytes) == (10, 7)
