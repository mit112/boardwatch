import io
from datetime import datetime
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import Engine, insert, select

from boardwatch.core.normalize import content_hash
from boardwatch.core.settings import Settings
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    return Settings(data_dir=tmp_path / "data", config_dir=cfg)


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, width=200), buf


def _seed_company(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )


def _seed_posting(engine: Engine, company_id: int, pid: str, body: str, status: str = "open") -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=pid, title=f"SWE {pid}",
                    normalized_title=f"swe {pid}", first_seen_at=datetime(2026, 1, 1),
                    last_seen_at=datetime(2026, 1, 1), status=status,
                    closed_at=datetime(2026, 2, 1) if status == "closed" else None,
                    consecutive_missing=0, content_hash=content_hash(body), body_text=body,
                )
            ).inserted_primary_key[0]
        )


def _seed_profile(engine: Engine, taxonomy_version: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(tables.profile).values(
                id=1, text="Python and Go engineer", skills_json=["Go", "Python"],
                taxonomy_version=taxonomy_version, target_titles_json=[],
                exclude_titles_json=[], locations_json=[], remote_only=False,
                updated_at=datetime(2026, 1, 1),
            )
        )


def _extraction_versions(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(select(tables.extractions.c.engine_version)).scalars())


def test_backfills_open_postings_only_with_progress_line(
    engine: Engine, settings: Settings
) -> None:
    current = load_taxonomy(settings.config_dir).version
    cid = _seed_company(engine)
    _seed_posting(engine, cid, "1", "Python and Kafka systems.")
    _seed_posting(engine, cid, "2", "Go services on Kubernetes.")
    _seed_posting(engine, cid, "3", "Rust tooling.", status="closed")
    _seed_profile(engine, current)
    console, buf = _console()

    stats = run_preflight(engine, settings, console)

    assert stats.profile_refreshed is False
    assert stats.postings_backfilled == 2  # closed posting untouched
    assert "re-extracting 2 postings" in buf.getvalue()
    assert _extraction_versions(engine) == [current, current]


def test_refreshes_stale_profile(engine: Engine, settings: Settings) -> None:
    _seed_profile(engine, "stale-version")
    console, buf = _console()
    stats = run_preflight(engine, settings, console)
    assert stats.profile_refreshed is True
    with engine.connect() as conn:
        row = conn.execute(select(tables.profile)).one()
    assert row.taxonomy_version == load_taxonomy(settings.config_dir).version
    assert "Python" in row.skills_json and "Go" in row.skills_json


def test_silent_and_idempotent_when_current(engine: Engine, settings: Settings) -> None:
    current = load_taxonomy(settings.config_dir).version
    cid = _seed_company(engine)
    _seed_posting(engine, cid, "1", "Python.")
    _seed_profile(engine, current)
    run_preflight(engine, settings, _console()[0])

    console, buf = _console()
    stats = run_preflight(engine, settings, console)
    assert stats.profile_refreshed is False
    assert stats.postings_backfilled == 0  # zero work on the second run
    assert buf.getvalue() == ""  # and silence
    assert len(_extraction_versions(engine)) == 1  # no duplicate rows


def test_superseded_rows_remain_but_are_unreachable(
    engine: Engine, settings: Settings
) -> None:
    cid = _seed_company(engine)
    body = "Python and Terraform."
    posting_id = _seed_posting(engine, cid, "1", body)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.extractions).values(
                posting_id=posting_id, content_hash=content_hash(body), kind="taxonomy",
                engine_version="superseded-version", json={"skills": ["Python"]},
                created_at=datetime(2026, 1, 1),
            )
        )
    _seed_profile(engine, "stale")
    run_preflight(engine, settings, _console()[0])
    current = load_taxonomy(settings.config_dir).version
    with engine.connect() as conn:
        rows = conn.execute(select(tables.extractions)).all()
        current_rows = conn.execute(
            select(tables.extractions).where(tables.extractions.c.engine_version == current)
        ).all()
    assert len(rows) == 2  # superseded row remains in place
    assert len(current_rows) == 1  # but only the current version is reachable by key


def test_crash_between_batches_is_resumable(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = load_taxonomy(settings.config_dir).version
    cid = _seed_company(engine)
    for n in range(3):
        _seed_posting(engine, cid, str(n), f"Python posting {n}.")
    _seed_profile(engine, current)
    monkeypatch.setattr("boardwatch.extract.preflight.BATCH_SIZE", 1)

    from boardwatch.extract.taxonomy import write_extraction as real

    calls = {"n": 0}

    def flaky(*args: object, **kwargs: object) -> bool:
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("injected crash between batches")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("boardwatch.extract.preflight.write_extraction", flaky)
    with pytest.raises(RuntimeError, match="injected crash"):
        run_preflight(engine, settings, _console()[0])
    assert len(_extraction_versions(engine)) == 2  # first two batches committed

    monkeypatch.setattr("boardwatch.extract.preflight.write_extraction", real)
    stats = run_preflight(engine, settings, _console()[0])
    assert stats.postings_backfilled == 1  # resumes exactly the remaining work
    assert len(_extraction_versions(engine)) == 3  # no duplicates (UNIQUE key)
