from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from boardwatch.reports.manifest import profile_row_hash
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import get_profile, save_profile


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _save(conn, *, pages: int) -> None:
    save_profile(conn, text="t", target_titles=["SWE"], exclude_titles=[], locations=[],
                 remote_only=False, skills=["Python"], taxonomy_version="v1", resume_max_pages=pages)


def test_resume_max_pages_persists(engine: Engine) -> None:
    with engine.begin() as conn:
        _save(conn, pages=2)
    with engine.connect() as conn:
        assert get_profile(conn).resume_max_pages == 2


def test_server_default_is_one_when_column_omitted(engine: Engine) -> None:
    # Genuinely exercises the DDL server_default: INSERT a profile row WITHOUT resume_max_pages
    # (bypassing save_profile) and assert it reads back 1. A migration/column missing
    # `DEFAULT 1` would make this row NULL/error, failing the test — which passing pages=1 to
    # save_profile never would.
    from sqlalchemy import insert

    from boardwatch.core.clock import utcnow
    from boardwatch.store.tables import profile

    with engine.begin() as conn:
        conn.execute(insert(profile).values(
            id=1, text="t", skills_json=["Python"], taxonomy_version="v1",
            target_titles_json=[], exclude_titles_json=[], locations_json=[],
            remote_only=False, updated_at=utcnow(),
        ))
    with engine.connect() as conn:
        assert get_profile(conn).resume_max_pages == 1


def test_resume_max_pages_not_a_profile_row_hash_input() -> None:
    # The ranker's profile_row_hash is a deliberate six-column contract; page count is a render
    # knob and must NOT enter it. The non-vacuous test of "kept out of the hash" is that the
    # function has no such parameter — a buggy impl that threaded it in would add the parameter
    # and fail this. `target_seniority_band` and `leveling_digest` joined the set in D-246
    # because, unlike page count, they drive a funnel drop bucket.
    import inspect

    params = set(inspect.signature(profile_row_hash).parameters)
    assert "resume_max_pages" not in params
    assert params == {
        "skills",
        "target_titles",
        "exclude_titles",
        "locations",
        "remote_only",
        "target_seniority_band",
        "leveling_digest",
    }
