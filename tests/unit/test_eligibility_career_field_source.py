"""T208 (D-586): the role taxonomy's `field` is the ONE source of the user's career field.

The ranker's field gates already read the taxonomy; the engine's field-tier families read
`Facts.career_field`. These pin that the engine now sees the taxonomy's field at every seam that
builds its facts from the profile row, through the real preflight and a real store, and that the
stored fact is never consulted for it — not as the value, not as a fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from rich.console import Console
from sqlalchemy import select

from boardwatch.core.settings import load_settings
from boardwatch.eligibility.catalog import bundled_rules_text
from boardwatch.eligibility.preflight import current_identity, run_eligibility
from boardwatch.rank.role_taxonomy import write_role_taxonomy
from boardwatch.store.db import get_engine
from boardwatch.store.queries import save_eligibility, save_profile
from boardwatch.store.tables import (
    eligibility_evaluations,
    eligibility_inputs,
    eligibility_requirements,
)
from tests.conftest import write_bundled_role_taxonomy
from tests.pipeline.test_eligibility_flow import DEGREE_BODY, _seed_posting

FIELD_ABSTAIN = "missing_profile_field:career_field"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A config dir whose catalog makes `degree` a field-tier family for `software` only.

    Derived from the SHIPPED rules.yaml, so catalog drift reaches these tests: the bundled
    catalog declares no field-tier family, so without the override nothing here could fire.
    """
    config_dir = tmp_path / "cfg"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    document = yaml.safe_load(bundled_rules_text())
    document["career_fields"] = ["software", "data"]
    for family in document["families"]:
        if family["id"] == "degree":
            family["tier"] = "field"
            family["applies_to"] = ["software"]
    config_dir.mkdir(parents=True)
    (config_dir / "rules.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    return tmp_path / "data"


def _profile(data_dir: Path, stored: dict[str, object]) -> None:
    _seed_posting(data_dir, DEGREE_BODY)
    with get_engine(data_dir).begin() as conn:
        save_profile(
            conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
            locations=["Boston, MA"], remote_only=False, skills=["python"],
            taxonomy_version="v1", resume_max_pages=1,
        )
        save_eligibility(conn, facts_json=stored, policy_json={})


def _evaluate(data_dir: Path, **kwargs: int) -> tuple[object, list[str | None]]:
    """Run the preflight; return the snapshot's `career_field` and the degree rows' rationale."""
    engine = get_engine(data_dir)
    stats = run_eligibility(engine, load_settings(data_dir=data_dir), Console(), **kwargs)
    assert stats.evaluated == 1
    with engine.connect() as conn:
        snapshot = conn.execute(select(eligibility_inputs.c.profile_snapshot_json)).scalar_one()
        rationales = list(
            conn.execute(
                select(eligibility_requirements.c.rationale)
                .join(
                    eligibility_evaluations,
                    eligibility_requirements.c.evaluation_id == eligibility_evaluations.c.id,
                )
                .where(eligibility_requirements.c.rule_id.like("degree:%"))
            ).scalars()
        )
    assert rationales, "premise: the degree family must detect DEGREE_BODY's requirement"
    return snapshot["fields"]["career_field"], rationales


@pytest.mark.parametrize("workers", [1, 2], ids=["serial", "parallel"])
def test_a_null_stored_field_reads_the_taxonomy_and_the_field_family_fires(
    env: Path, tmp_path: Path, workers: int
) -> None:
    """The live shape: `career_field` NULL on the profile, `field: software` in the taxonomy.
    Before T208 the family abstained on the missing fact for the owner. `parallel` also proves the
    child rebuilds the same facts: `_init_worker` refuses an identity the parent did not hash."""
    write_bundled_role_taxonomy(tmp_path / "cfg")
    _profile(env, {"highest_degree": "bachelor"})
    field, rationales = _evaluate(env, workers=workers, parallel_threshold=1)
    assert FIELD_ABSTAIN not in rationales
    assert field == "software"


def test_the_taxonomy_wins_over_a_stored_field(env: Path, tmp_path: Path) -> None:
    """A stored `nursing` (outside the catalog, so read it would abstain) under a `software`
    taxonomy: the engine reads `software`. This is the case a reader of the stored fact fails."""
    write_bundled_role_taxonomy(tmp_path / "cfg")
    _profile(env, {"highest_degree": "bachelor", "career_field": "nursing"})
    field, rationales = _evaluate(env)
    assert FIELD_ABSTAIN not in rationales
    assert field == "software"


@pytest.mark.parametrize("stored", [None, "software"], ids=["null", "stored-software"])
def test_no_taxonomy_abstains_and_never_falls_back_to_the_stored_field(
    env: Path, stored: str | None
) -> None:
    """No taxonomy ⇒ `career_field` is None and the field family ABSTAINS with today's reason —
    even when the stored fact holds a catalog value (the keystone invariant: no fallback, no
    default). `null` is the control, unchanged from before T208."""
    _profile(env, {"highest_degree": "bachelor", "career_field": stored})
    field, rationales = _evaluate(env)
    assert field is None
    assert rationales == [FIELD_ABSTAIN] * len(rationales)


def test_a_taxonomy_field_outside_the_catalog_is_carried_and_abstains(
    env: Path, tmp_path: Path
) -> None:
    """A second tenant's gathered field the catalog does not declare is carried as written (it is
    hashed, so it is visible in the snapshot) and the engine abstains on it — the run is not
    refused, and the family neither fires nor clears."""
    write_role_taxonomy(
        tmp_path / "cfg",
        {"version": 1, "field": "widgetry",
         "role_families": [{"id": "fitter", "title_words": ["widget fitter"]}]},
    )
    _profile(env, {"highest_degree": "bachelor"})
    field, rationales = _evaluate(env)
    assert field == "widgetry"
    assert rationales == [FIELD_ABSTAIN] * len(rationales)


def test_the_read_identity_matches_the_one_the_preflight_wrote(env: Path, tmp_path: Path) -> None:
    """`current_identity` (every read path) and `run_eligibility` (the write) resolve the field at
    the same seam, so a stored `nursing` under a `software` taxonomy still reads its own rows."""
    write_bundled_role_taxonomy(tmp_path / "cfg")
    _profile(env, {"career_field": "nursing"})
    engine = get_engine(env)
    stats = run_eligibility(engine, load_settings(data_dir=env), Console())
    with engine.connect() as conn:
        assert current_identity(conn, load_settings(data_dir=env)) == (
            stats.profile_hash, stats.rules_hash,
        )
