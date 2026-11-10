"""The web queue lists its leads as the ranker ordered them: tier first, then score (D-688)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext, queue_payload
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from tests.conftest import write_bundled_role_taxonomy
from tests.unit.test_web_server import _deliver


@pytest.fixture()
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Engine, ApiContext]:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    write_bundled_role_taxonomy(config_dir)
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    (tmp_path / "out").mkdir()
    (tmp_path / "queue").mkdir()
    ctx = ApiContext(
        settings=load_settings(),
        out_root=(tmp_path / "out").resolve(),
        queue_root=(tmp_path / "queue").resolve(),
        owner_name="Example Owner",
        platform="darwin",
    )
    return engine, ctx


def _entry_profile(engine: Engine, band: str) -> None:
    with engine.begin() as conn:
        save_profile(
            conn,
            text="resume",
            target_titles=["software engineer"],
            exclude_titles=[],
            locations=["Boston, MA"],
            remote_only=False,
            skills=["python"],
            taxonomy_version="v1",
            resume_max_pages=1,
            target_seniority_band=band,
            target_countries=["USA"],
        )


def _order(engine: Engine, ctx: ApiContext) -> list[tuple[str, float | None]]:
    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)
    rows = payload["rows"] or payload["review"]
    return [(row["title"], row["score"]) for row in rows]


def test_a_new_grad_title_lists_above_a_higher_scoring_plain_one(
    served: tuple[Engine, ApiContext],
) -> None:
    engine, ctx = served
    with engine.begin() as conn:
        _deliver(conn, "plain", title="Software Engineer")
        _deliver(conn, "grad", title="University Hire, New Grad Platform Developer")
    _entry_profile(engine, "entry")

    order = _order(engine, ctx)

    titles = [title for title, _ in order]
    scores = dict(order)
    # The precondition that makes the order mean something: by score alone the plain title wins.
    assert scores["Software Engineer"] is not None
    assert scores["University Hire, New Grad Platform Developer"] is not None
    assert scores["Software Engineer"] > scores["University Hire, New Grad Platform Developer"]
    assert titles == ["University Hire, New Grad Platform Developer", "Software Engineer"]


def test_a_user_not_targeting_entry_roles_keeps_score_order(
    served: tuple[Engine, ApiContext],
) -> None:
    engine, ctx = served
    with engine.begin() as conn:
        _deliver(conn, "plain", title="Software Engineer")
        _deliver(conn, "grad", title="University Hire, New Grad Platform Developer")
    _entry_profile(engine, "mid")

    assert [title for title, _ in _order(engine, ctx)] == [
        "Software Engineer",
        "University Hire, New Grad Platform Developer",
    ]
