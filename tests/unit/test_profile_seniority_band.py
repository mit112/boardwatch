from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from boardwatch.rank.heuristic import profile_view_from_row
from boardwatch.reports.manifest import profile_row_hash
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import get_profile, save_profile
from boardwatch.store.tables import profile


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _save(conn, **over):
    kwargs = dict(
        text="t", target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        skills=[], taxonomy_version="v1", resume_max_pages=1,
    )
    kwargs.update(over)
    save_profile(conn, **kwargs)


def test_band_defaults_to_any_and_is_never_null(engine) -> None:
    with engine.begin() as conn:
        _save(conn)
        row = conn.execute(select(profile)).one()
    assert row.target_seniority_band == "any"


def test_band_round_trips_through_edit(engine) -> None:
    """The set_ map defect: omitting the column makes `profile edit` silently never update it."""
    with engine.begin() as conn:
        _save(conn, target_seniority_band="entry")
        assert get_profile(conn).target_seniority_band == "entry"
        _save(conn, target_seniority_band="senior")
        assert get_profile(conn).target_seniority_band == "senior"


def test_profile_view_exposes_the_band(engine) -> None:
    with engine.begin() as conn:
        _save(conn, target_seniority_band="entry")
        view = profile_view_from_row(get_profile(conn))
    assert view.target_seniority_band == "entry"


def test_profile_view_falls_back_to_any_for_a_row_without_the_column() -> None:
    class Bare:
        pass
    assert profile_view_from_row(Bare()).target_seniority_band == "any"


def test_profile_row_hash_tracks_the_band() -> None:
    base = dict(skills=[], target_titles=[], exclude_titles=[], locations=[], remote_only=False)
    assert profile_row_hash(**base, target_seniority_band="any") != profile_row_hash(
        **base, target_seniority_band="entry"
    )


def test_profile_row_hash_parameter_set_is_pinned() -> None:
    assert set(inspect.signature(profile_row_hash).parameters) == {
        "skills", "target_titles", "exclude_titles", "locations", "remote_only",
        "target_seniority_band", "leveling_digest",
    }



def test_profile_row_hash_tracks_the_leveling_catalog() -> None:
    """The catalog is user-overridable and decides a drop bucket.

    Without it in the identity, an operator could edit {config_dir}/leveling.yaml, change which
    titles are dropped, and the manifest would still report two runs as identical.
    """
    base = dict(
        skills=[], target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        target_seniority_band="entry",
    )
    assert profile_row_hash(**base, leveling_digest="aaa") != profile_row_hash(
        **base, leveling_digest="bbb"
    )
