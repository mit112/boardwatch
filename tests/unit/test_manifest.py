"""P0 item 4: the two new manifest hashes (`config_hash`, `profile_row_hash`).

These pin the two claims the manifest makes and could get wrong: that the config hash tracks
exactly the decision-relevant settings and nothing else, and that it FAILS closed on an
unclassified field rather than silently covering the wrong set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.core.settings import LLMTier, Settings
from boardwatch.reports import manifest
from boardwatch.reports.manifest import (
    UnclassifiedSettingError,
    config_hash,
    profile_row_hash,
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {"data_dir": tmp_path / "data", "config_dir": tmp_path / "cfg"}
    base.update(overrides)
    return Settings(**base)


def test_config_hash_is_stable_for_the_same_settings(tmp_path: Path) -> None:
    assert config_hash(_settings(tmp_path)) == config_hash(_settings(tmp_path))


def test_a_decision_relevant_change_changes_the_hash(tmp_path: Path) -> None:
    base = config_hash(_settings(tmp_path))
    assert config_hash(_settings(tmp_path, location_filter_mode="hard")) != base
    assert config_hash(_settings(tmp_path, recency_half_life_days=30.0)) != base
    assert config_hash(_settings(tmp_path, llm=LLMTier(enabled=True, provider="anthropic"))) != base


def test_a_machine_local_or_throughput_change_does_not_change_the_hash(tmp_path: Path) -> None:
    """scan_workers, notify and max_calls_per_run are OUT — they must not move the hash, or a
    reproducibility check would fire on a change that cannot alter which postings become leads."""
    base = config_hash(_settings(tmp_path))
    assert config_hash(_settings(tmp_path, scan_workers=8)) == base
    assert config_hash(_settings(tmp_path, detail_fetch_budget=999)) == base
    assert config_hash(_settings(tmp_path, reap_stale_after_hours=1)) == base
    assert config_hash(_settings(tmp_path, llm=LLMTier(max_calls_per_run=7))) == base


def test_a_data_dir_change_does_not_change_the_hash(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("elsewhere")
    assert config_hash(_settings(tmp_path)) == config_hash(
        Settings(data_dir=other, config_dir=other)
    )


def test_config_hash_fails_closed_on_an_unclassified_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a newly-added Settings field by dropping one from the classification: the hash
    must refuse rather than quietly cover a different set of fields."""
    monkeypatch.setattr(
        manifest, "_CONFIG_RELEVANT", manifest._CONFIG_RELEVANT - {"location_filter_mode"}
    )
    with pytest.raises(UnclassifiedSettingError):
        config_hash(_settings(tmp_path))


def test_profile_row_hash_distinguishes_missing_from_empty() -> None:
    """A null column and an empty list are different inputs; folding them would let a profile
    that dropped every exclude-title hash the same as one that never had any."""
    missing = profile_row_hash(
        skills=["python"], target_titles=None, exclude_titles=None,
        locations=None, remote_only=False,
    )
    empty = profile_row_hash(
        skills=["python"], target_titles=[], exclude_titles=[],
        locations=[], remote_only=False,
    )
    assert missing != empty


def test_profile_row_hash_tracks_exclude_titles() -> None:
    base = profile_row_hash(
        skills=["python"], target_titles=["swe"], exclude_titles=["manager"],
        locations=["remote"], remote_only=True,
    )
    changed = profile_row_hash(
        skills=["python"], target_titles=["swe"], exclude_titles=["manager", "sales"],
        locations=["remote"], remote_only=True,
    )
    assert base != changed


def test_profile_row_hash_tracks_the_skill_taxonomy() -> None:
    """The taxonomy is user-overridable and, since the zero-signal veto, decides a drop bucket.

    Without it in the identity an operator could edit {config_dir}/taxonomy.yaml, change which
    postings are dropped as having no recognised requirement term, and the manifest would still
    report two runs as identical — the same failure the leveling catalog's digest closes.
    """
    base = dict(
        skills=["python"], target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        target_seniority_band="entry", leveling_digest="lev",
    )
    assert profile_row_hash(**base, taxonomy_version="aaa") != profile_row_hash(
        **base, taxonomy_version="bbb"
    )


_TAXONOMY_ONE = """
patterns:
  - name: Python
    category: language
    pattern: "\\\\bPython\\\\b"
"""
# One pattern MORE, and none of it appears in the profile text below. That is the case the
# manifest docstring names: `skills` is the taxonomy applied to the operator's own text, so it
# sits still here while the set of postings the zero-signal veto drops changes. If the identity
# were covered "indirectly through `skills`", this fixture would not move either hash.
_TAXONOMY_TWO = _TAXONOMY_ONE + """  - name: Kubernetes
    category: platform
    pattern: "\\\\bKubernetes\\\\b"
"""


def test_taxonomy_drift_moves_both_identities(tmp_path: Path) -> None:
    """The manifest hash AND the permanent-disposition stamp, over the two production callers.

    Two identities, both derived from `profile_row_hash`, reached through the two call sites
    that actually build them — `pipeline.funnel_writer.collect_run_funnel` and
    `pipeline.policy.run_policy_version`. Asserting the pure function alone would not catch a
    call site that never passed the argument, which is the failure mode a defaulted parameter
    invites. `run_preflight` is deliberately NOT run, so `profile.skills_json` is identical
    across both halves and the taxonomy version is the only input that moved.
    """
    from boardwatch.pipeline.funnel_writer import collect_run_funnel
    from boardwatch.pipeline.policy import run_policy_version
    from boardwatch.reports.run_funnel import ScanContext
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import insert_run, save_profile

    settings = _settings(tmp_path)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer who writes Python.", target_titles=[],
            exclude_titles=[], locations=[], remote_only=False, skills=["Python"],
            taxonomy_version="pinned", resume_max_pages=1,
        )
    run_id = insert_run(engine)

    def _identities() -> tuple[str | None, str]:
        funnel = collect_run_funnel(
            engine, settings, run_id=run_id, scan=ScanContext(ran=False), shortlist=None,
            tailored=[], tailor_failed=0, projection_ran=False, rewrite_rows=[],
            lanes=[], errors=[], fatal=None,
        )
        with engine.connect() as conn:
            return funnel.manifest.profile_row_hash, run_policy_version(conn, settings)

    (settings.config_dir / "taxonomy.yaml").write_text(_TAXONOMY_ONE, encoding="utf-8")
    first_manifest, first_stamp = _identities()
    (settings.config_dir / "taxonomy.yaml").write_text(_TAXONOMY_TWO, encoding="utf-8")
    second_manifest, second_stamp = _identities()

    assert first_manifest is not None and second_manifest is not None
    assert first_manifest != second_manifest, "the manifest called two runs identical"
    assert first_stamp != second_stamp, "a permanent disposition would carry the wrong policy"
