"""`resume project` reports a malformed CONFIG file as a typed refusal, never as a traceback.

`resolve_projection_run` (Task 3) loads the taxonomy, the equivalence table and the persona
registry, and catches none of them by design — a preflight that classified its own failures could
not be reused by a caller wanting to classify them differently. That puts three foreign exception
families on this command's boundary: `TaxonomyError`, `EquivalenceError` and `PersonaError`. Only
the persona one arrived with the projection-run extraction; the other two were uncaught before it.
All three are closed here, because `exit_code != 0` is what a traceback produces too.

The discriminating assertion in every case is `isinstance(result.exception, SystemExit)`. That is
what a clean `typer.Exit` raises; an uncaught `TaxonomyError` leaves `result.exception` as that
exception instead, and `CliRunner` reports the same non-zero code for both — the same reasoning
`test_projection_cli_resume_project.py` states for its own persona and template cases.

The environment is `test_projection_cli_resume_project.py`'s own `_make_env`/`run`, imported rather
than re-derived: this suite differs from that one only in which config file it corrupts, and that
file must stay byte-identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.tailor import equivalences as equivalences_mod
from tests.projection.test_projection_cli_resume_project import Env, _make_env, run


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return _make_env(tmp_path, monkeypatch)


def _run(env: Env) -> object:
    return run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])


def test_a_malformed_persona_override_is_a_typed_refusal_naming_the_file(env: Env) -> None:
    """A `personas.yaml` override with no `personas` list at all. Distinct from
    `test_refuses_a_persona_declaring_entries_before_selection_runs`: that one is a WELL-FORMED
    registry the projection preflight rejects with its own `ProjectionError`, whereas this never
    parses into a registry, so `load_personas` raises `PersonaError` before the preflight can
    inspect a single persona.

    This is the arm the projection-run extraction introduced — `resolve_projection_run` calls
    `load_personas`, which `resume project` never did — though `reject_entry_declaring_personas`
    reads the same file first, so the refusal surfaces at that earlier boundary.
    """
    (env.config_dir / "personas.yaml").write_text("personas: []\n", encoding="utf-8")

    result = _run(env)

    assert isinstance(result.exception, SystemExit), (
        f"expected a clean refusal, got an uncaught {result.exception!r}"
    )
    assert result.exit_code != 0
    assert "personas.yaml" in result.output, result.output
    # Nothing was written: the refusal precedes `project_pool` and `select` entirely.
    assert not (env.data_dir / "projected" / str(env.posting_id)).exists()


def test_a_malformed_taxonomy_override_is_a_typed_refusal_naming_the_file(env: Env) -> None:
    """`load_taxonomy` prefers `{config_dir}/taxonomy.yaml` over the bundled copy
    (`extract/taxonomy.py:61`), and reports the override's own path in the message. The fixture's
    seeded extraction row was keyed to the BUNDLED version before this file existed, so the
    corruption is what the run trips on, not a version mismatch."""
    (env.config_dir / "taxonomy.yaml").write_text("patterns: [unclosed\n", encoding="utf-8")

    result = _run(env)

    assert isinstance(result.exception, SystemExit), (
        f"expected a clean refusal, got an uncaught {result.exception!r}"
    )
    assert result.exit_code != 0
    assert "taxonomy.yaml" in result.output, result.output
    assert not (env.data_dir / "projected" / str(env.posting_id)).exists()


def test_a_malformed_equivalence_table_is_a_typed_refusal_naming_the_file(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`load_equivalences()` takes no arguments and reads the PACKAGED
    `boardwatch/tailor/equivalences.yaml` through `importlib.resources` — there is no user override
    for it, so this arm means a corrupt installation rather than a mis-edited config, and it cannot
    be reached by writing a file into `config_dir`.

    `equivalences.files` — the name bound inside that module by `from importlib.resources import
    files` — is redirected at a directory this test controls. The exception and its message
    therefore come from the PRODUCTION parser, not from an `EquivalenceError` authored here, which a
    plain `monkeypatch.setattr(run_mod, "load_equivalences", raiser)` could not claim: that would
    make the "names the file" assertion self-fulfilling.

    Patching the source module rather than `run.py`'s bound name is also what makes this exercise
    the real loader: `run.py` does `from ... import load_equivalences`, and that function object
    reads `files` out of its own module globals at call time.
    """
    fake_package = tmp_path / "packaged"
    fake_package.mkdir()
    (fake_package / "equivalences.yaml").write_text("pairs: [unclosed\n", encoding="utf-8")
    monkeypatch.setattr(equivalences_mod, "files", lambda _package: fake_package)

    # Premise: the redirect really does reach the production loader, and it really does refuse.
    with pytest.raises(equivalences_mod.EquivalenceError, match="equivalences.yaml"):
        equivalences_mod.load_equivalences()

    result = _run(env)

    assert isinstance(result.exception, SystemExit), (
        f"expected a clean refusal, got an uncaught {result.exception!r}"
    )
    assert result.exit_code != 0
    assert "equivalences.yaml" in result.output, result.output
    assert not (env.data_dir / "projected" / str(env.posting_id)).exists()
