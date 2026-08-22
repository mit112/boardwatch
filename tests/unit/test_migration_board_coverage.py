from pathlib import Path

from sqlalchemy import inspect

from boardwatch.store.db import ensure_schema, get_engine


def test_board_scans_has_nullable_coverage_columns(tmp_path: Path) -> None:
    """Nullable is load-bearing: an existing row has no total and must not read as zero."""
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    cols = {c["name"]: c for c in inspect(engine).get_columns("board_scans")}
    for name in ("board_reported_total", "board_enumerated", "detail_deferred", "board_total_censored"):
        assert name in cols, f"{name} missing from board_scans"
        assert cols[name]["nullable"] is True, f"{name} must be nullable, not 0-defaulted"
