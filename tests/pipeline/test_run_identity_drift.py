"""T137 — a run reports when its identity DRIFTED mid-run, and records how it was executed.

The manifest is read as the run finishes, while the ranker, the judge and the ledger stamp read the
same inputs earlier. These drive `run_pipeline` on a seeded store and move an input BETWEEN ranking
and finalization, then read the published artifacts back off disk — the only place a reader sees.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from sqlalchemy import func, insert, select

from boardwatch.core.settings import load_settings
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import bundled_rules_text
from boardwatch.extract.taxonomy import bundled_taxonomy_text, load_taxonomy
from boardwatch.pipeline import funnel_writer
from boardwatch.pipeline import runner as runner_mod
from boardwatch.rank.leveling import load_leveling
from boardwatch.reports.manifest import profile_row_hash
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queries import get_profile, save_profile
from tests.pipeline.test_pipeline_run import _pipeline, _ready

_DRIFT_LINE = "run identity drifted mid-run"
_MANIFEST_VALUES = (
    "code_fingerprint",
    "config_hash",
    "profile_facts_hash",
    "profile_row_hash",
    "rules_hash",
    "routing_hash",
)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Defined here rather than imported: importing the fixture would shadow it at every test
    signature, which ruff flags as a redefinition (F811)."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # No test here is about the heartbeat, and none may reach a real monitor.
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)
    return tmp_path / "data"


def _payload(summary: Any) -> dict[str, Any]:
    assert summary.funnel is not None, "guard: the funnel must have been written"
    return json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _markdown(summary: Any) -> str:
    assert summary.funnel is not None, "guard: the funnel must have been written"
    return summary.funnel.markdown_path.read_text(encoding="utf-8")  # type: ignore[no-any-return]


def _manifest_section(markdown: str) -> str:
    return markdown.split("## Manifest", 1)[1].split("\n## ", 1)[0]


def _drift_lines(summary: Any) -> list[str]:
    return [line for line in summary.errors if line.startswith(_DRIFT_LINE)]


def _add_a_target_title(data_dir: Path) -> None:
    """The owner (or a peer session's `boardwatch profile …`) edits the profile, through the
    store's own writer, with every other column written back as it was."""
    with get_engine(data_dir).begin() as conn:
        row = get_profile(conn)
        assert row is not None, "guard: `init` must have written a profile"
        save_profile(
            conn,
            text=row.text,
            target_titles=[*row.target_titles_json, "Platform Engineer"],
            exclude_titles=row.exclude_titles_json,
            locations=row.locations_json,
            remote_only=row.remote_only,
            skills=row.skills_json,
            taxonomy_version=row.taxonomy_version,
            resume_max_pages=row.resume_max_pages,
            target_seniority_band=row.target_seniority_band,
        )


def _edit_mid_run(monkeypatch: pytest.MonkeyPatch, edit: Any) -> list[int]:
    """Run `edit` inside the lane split — after the ranker and the judge, before the tailor loop
    and the funnel — and count how often it fired, so a test cannot pass on an edit that never
    happened."""
    real = runner_mod._lead_lanes
    fired: list[int] = []

    def editing(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        edit()
        fired.append(1)
        return result

    monkeypatch.setattr(runner_mod, "_lead_lanes", editing)
    return fired


# --- 1-3: drift is reported, per field --------------------------------------------------------


def test_a_profile_edit_mid_run_is_reported_as_drift(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The manifest publishes the END reading; the run ranked under the START one. The funnel
    must say the two differ and name the field, and the run raises exactly one alert for it."""
    _ready(env)
    fired = _edit_mid_run(monkeypatch, lambda: _add_a_target_title(env))

    summary = _pipeline(env, tmp_path / "apps")

    assert fired == [1], "guard: the mid-run edit must have happened exactly once"
    payload = _payload(summary)
    assert payload["identity_drift"] == ["profile_row_hash"]
    manifest = _manifest_section(_markdown(summary))
    assert "DRIFTED" in manifest and "`profile_row_hash`" in manifest, manifest
    assert _drift_lines(summary) == [f"{_DRIFT_LINE}: profile_row_hash"], summary.errors


def test_a_run_with_no_edit_reports_a_stable_identity(env: Path, tmp_path: Path) -> None:
    """NULL CONTROL for the test above: the same run with nothing moved. `[]` is a measured
    stable identity — not `null`, which would mean nobody measured — and a stable run adds no
    alert and no sentence to the manifest section."""
    _ready(env)

    summary = _pipeline(env, tmp_path / "apps")

    payload = _payload(summary)
    assert payload["identity_drift"] == []
    assert _drift_lines(summary) == [], summary.errors
    assert "drift" not in _manifest_section(_markdown(summary)).lower()


def test_a_rules_edit_mid_run_names_rules_hash_and_not_the_profile(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `rules.yaml` override written mid-run — the bundled catalog with its version bumped —
    moves `rules_hash` and nothing else. Against the profile edit above, this is what shows the
    comparison is per field rather than one boolean."""
    _ready(env)
    rules = load_settings(data_dir=env).config_dir / "rules.yaml"
    assert not rules.exists(), "guard: the run must start on the bundled catalog"
    edited = re.sub(r"^version: 1$", "version: 2", bundled_rules_text(), count=1, flags=re.M)
    assert edited != bundled_rules_text(), "guard: the version line must have been found"
    fired = _edit_mid_run(monkeypatch, lambda: rules.write_text(edited, encoding="utf-8"))

    summary = _pipeline(env, tmp_path / "apps")

    assert fired == [1], "guard: the mid-run edit must have happened exactly once"
    assert _payload(summary)["identity_drift"] == ["rules_hash"]
    assert _drift_lines(summary) == [f"{_DRIFT_LINE}: rules_hash"], summary.errors


# --- 4: provenance moves where the manifest cannot see ----------------------------------------


def _manifest_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {name: payload["manifest"][name] for name in _MANIFEST_VALUES}


def test_a_gate_prompt_change_moves_provenance_and_no_manifest_value(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`gate_engine_version()` re-keys every gate row, and no manifest value can see it: two runs
    either side of a prompt bump publish byte-identical manifests. The provenance must differ."""
    _ready(env)
    before = _payload(_pipeline(env, tmp_path / "apps"))
    monkeypatch.setattr(final_gate, "PROMPT_VERSION", f"{final_gate.PROMPT_VERSION}-edited")

    after = _payload(_pipeline(env, tmp_path / "apps"))

    assert before["run_id"] != after["run_id"], "guard: two runs, two artifacts"
    assert _manifest_values(after) == _manifest_values(before)
    assert after["provenance"]["gate"]["engine_version"] == final_gate.gate_engine_version()
    assert after["provenance"]["gate"] != before["provenance"]["gate"]


def test_a_larger_fleet_moves_provenance_and_no_manifest_value(
    env: Path, tmp_path: Path
) -> None:
    """Watching one more board changes the corpus a run can see and moves no policy hash — that
    is deliberate (`reports/manifest.py`). So two runs either side of it carry identical manifests,
    and only the provenance can tell them apart. The count is checked against the store through a
    different read than the one that produced it."""
    _ready(env)
    before = _payload(_pipeline(env, tmp_path / "apps"))
    engine = get_engine(env)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.companies).values(
                name="Extra", provider="greenhouse", slug="extra", source="user", watched=True
            )
        )
        watched = int(
            conn.execute(
                select(func.count())
                .select_from(tables.companies)
                .where(tables.companies.c.watched.is_(True))
            ).scalar_one()
        )

    after = _payload(_pipeline(env, tmp_path / "apps"))

    assert _manifest_values(after) == _manifest_values(before)
    assert after["provenance"]["fleet"]["watched_companies"] == watched
    assert before["provenance"]["fleet"]["watched_companies"] == watched - 1


def test_provenance_records_what_the_run_actually_read(env: Path, tmp_path: Path) -> None:
    """Each block against its own source: the flags this call passed, the settings it loaded,
    and the commit of THIS checkout, read through `git log` rather than `rev-parse`."""
    _ready(env)
    settings = load_settings(data_dir=env)

    summary = _pipeline(env, tmp_path / "apps", top_n=7)

    provenance = _payload(summary)["provenance"]
    assert provenance["flags"] == {
        "skip_scan": True, "project": False, "liveness_prober": False, "top_n": 7,
    }
    assert provenance["gate"] == {
        "engine_version": final_gate.gate_engine_version(),
        "model": settings.gate.model,
        "effort": settings.gate.effort,
    }
    assert provenance["lanes"] == list(settings.lanes_enabled)
    assert provenance["fleet"]["boards_attempted"] == 0, "a --no-scan run attempted no board"
    head = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=Path(funnel_writer.__file__).parent,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert provenance["code"]["commit"] == head
    assert isinstance(provenance["code"]["dirty"], bool)
    assert "## Execution provenance" in _markdown(summary)


# --- 5: fail-open --------------------------------------------------------------------------


def test_git_unavailable_leaves_code_none_and_the_run_completes(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `git` on the machine: `code` is `None`, the REST of the provenance is still recorded,
    and nothing about git reaches the run's errors or its fatal."""
    _ready(env)

    def no_git(*_a: Any, **_k: Any) -> Any:
        # What `subprocess.run` raises when `git` is not on PATH. Patched at the ONE git seam
        # rather than on `subprocess.run` itself, which every other subprocess in the run shares.
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(funnel_writer, "_git", no_git)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None
    provenance = _payload(summary)["provenance"]
    assert provenance["code"] is None
    assert provenance["flags"]["skip_scan"] is True, "the other blocks must survive git's absence"
    assert not [e for e in summary.errors if "git" in e.lower()], summary.errors


def test_a_package_root_that_is_not_a_checkout_leaves_code_none(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wheel install: the package directory is in no git work tree at all."""
    _ready(env)
    wheel_root = tmp_path / "site-packages" / "boardwatch"
    wheel_root.mkdir(parents=True)
    monkeypatch.setattr(funnel_writer, "_PACKAGE_ROOT", wheel_root)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None
    assert _payload(summary)["provenance"]["code"] is None


@pytest.mark.parametrize(
    ("raised", "provenance_recorded"),
    [
        (subprocess.TimeoutExpired(cmd=["git"], timeout=5.0), True),
        # Outside the tuple `code_provenance` expects, so it escapes that function and is caught
        # by the runner's own guard instead — which costs the provenance, and still not the run.
        (RuntimeError("git exploded"), False),
    ],
    ids=["timeout", "unexpected"],
)
def test_a_raising_git_subprocess_is_never_a_fatal(
    env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
    provenance_recorded: bool,
) -> None:
    _ready(env)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise raised

    monkeypatch.setattr(funnel_writer, "_git", boom)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None
    assert summary.funnel is not None and summary.morning is not None
    assert not [e for e in summary.errors if "git" in e.lower()], summary.errors
    provenance = _payload(summary)["provenance"]
    if provenance_recorded:
        assert provenance["code"] is None
        assert provenance["flags"]["skip_scan"] is True
    else:
        assert provenance is None


# --- 6: ordering ---------------------------------------------------------------------------


def test_the_drift_line_reaches_the_MORNING_DIGEST(  # noqa: N802
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the alert's position ABOVE `_emit_morning`. Below it the line still reaches
    `summary.errors` and the run row, so only the rendered digest can tell the two apart."""
    _ready(env)
    _edit_mid_run(monkeypatch, lambda: _add_a_target_title(env))

    summary = _pipeline(env, tmp_path / "apps")

    assert _drift_lines(summary), "guard: the drift alert must have fired at all"
    assert summary.morning is not None, "guard: the digest must have been written"
    rendered = summary.morning.markdown_path.read_text(encoding="utf-8")
    assert f"{_DRIFT_LINE}: profile_row_hash" in rendered, (
        "the drift alert is missing from the morning digest — it sits BELOW `_emit_morning`"
    )


# --- 7: T164 — a taxonomy bump must not manufacture drift -----------------------------------

_TAXONOMY_OVERRIDE_EXTRA = (
    "  - {name: 'Zig', category: language, pattern: '\\bzig\\b', case_sensitive: false}\n"
)


def _bump_taxonomy(env: Path) -> str:
    """Write a config-dir taxonomy override whose version differs from the bundled one that
    `_ready` saved the profile at, so the stored `profile.taxonomy_version` reads stale."""
    cfg = load_settings(data_dir=env).config_dir
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "taxonomy.yaml").write_text(
        bundled_taxonomy_text() + _TAXONOMY_OVERRIDE_EXTRA, encoding="utf-8"
    )
    return load_taxonomy(cfg).version


def _make_profile_text_match_the_bump(env: Path) -> None:
    """Add "Zig" to the profile's own text, WITHOUT touching its stored `skills_json` or
    `taxonomy_version` — those still reflect the bundled taxonomy, which has no `Zig` pattern.

    Without this, the bump above changes only the stored `taxonomy_version` column and never the
    derived `skills_json`, so `profile_row_hash` cannot move regardless of when it is read and
    the drift test would pass whether or not T164's ordering bug is present."""
    with get_engine(env).begin() as conn:
        row = get_profile(conn)
        assert row is not None, "guard: `_ready` must have written a profile"
        save_profile(
            conn,
            text=f"{row.text} Zig enthusiast.",
            target_titles=row.target_titles_json,
            exclude_titles=row.exclude_titles_json,
            locations=row.locations_json,
            remote_only=row.remote_only,
            skills=row.skills_json,
            taxonomy_version=row.taxonomy_version,
            resume_max_pages=row.resume_max_pages,
            target_seniority_band=row.target_seniority_band,
        )


def test_a_taxonomy_bump_run_reports_no_drift_and_ranks_the_refreshed_profile(
    env: Path, tmp_path: Path
) -> None:
    """`extract/preflight.py:run_preflight` rewrites `profile.skills_json` +
    `profile.taxonomy_version` mid-ranking when the taxonomy moved. Before T164,
    `_capture_run_start` read the profile BEFORE that refresh while the funnel's end reading
    came AFTER it, so the first run after every taxonomy bump reported a false
    `profile_row_hash` drift though no outside input moved between start and end."""
    _ready(env)
    _make_profile_text_match_the_bump(env)
    bumped_version = _bump_taxonomy(env)
    engine = get_engine(env)
    with engine.connect() as conn:
        before = get_profile(conn)
    assert before is not None and before.taxonomy_version != bumped_version, (
        "guard: the profile must start stale against the bumped taxonomy"
    )
    assert "Zig" not in before.skills_json, "guard: the stale skill set must not have Zig yet"

    summary = _pipeline(env, tmp_path / "apps")

    payload = _payload(summary)
    assert payload["identity_drift"] == []
    assert _drift_lines(summary) == [], summary.errors
    with engine.connect() as conn:
        after = get_profile(conn)
    assert after is not None and after.taxonomy_version == bumped_version, (
        "guard: the run itself must have performed the refresh"
    )
    assert "Zig" in after.skills_json, (
        "guard: the refresh must have actually moved the derived skill set, or this test cannot "
        "tell a fixed ordering from a still-broken one"
    )
    settings = load_settings(data_dir=env)
    expected_hash = profile_row_hash(
        skills=after.skills_json,
        target_titles=after.target_titles_json,
        exclude_titles=after.exclude_titles_json,
        locations=after.locations_json,
        remote_only=after.remote_only,
        target_seniority_band=after.target_seniority_band,
        leveling_digest=load_leveling(settings.config_dir).digest,
        taxonomy_version=bumped_version,
    )
    assert payload["manifest"]["profile_row_hash"] == expected_hash, (
        "the manifest must publish the REFRESHED row's hash, not the stale start reading"
    )


def test_a_taxonomy_bump_run_still_prints_the_taxonomy_changed_line(
    env: Path, tmp_path: Path
) -> None:
    """T164's constraint: splitting the profile refresh out of the ranker's own preflight call
    must not weaken this line to the generic 'extracting N new posting(s)' one — the pending
    postings on this run are unextracted because the taxonomy changed, not because they are new."""
    _ready(env)
    _bump_taxonomy(env)
    settings = load_settings(data_dir=env)
    console = Console(quiet=False, record=True, width=200)

    runner_mod.run_pipeline(
        get_engine(env),
        settings,
        console=console,
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
    )

    assert "taxonomy changed — re-extracting" in console.export_text()
