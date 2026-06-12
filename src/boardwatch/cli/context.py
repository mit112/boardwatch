"""Per-invocation app context: settings + engine, built lazily by DB-touching commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from boardwatch.core.settings import Settings, load_settings
from boardwatch.store.db import ensure_schema, get_engine


@dataclass
class AppContext:
    settings: Settings
    engine: Engine


def build_context(data_dir: Path | None, *, ensure: bool = True) -> AppContext:
    settings = load_settings(data_dir=data_dir)
    engine = get_engine(settings.data_dir, busy_timeout_ms=settings.busy_timeout_ms)
    if ensure:
        ensure_schema(engine)
    return AppContext(settings=settings, engine=engine)
