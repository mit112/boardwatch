"""`boardwatch resume project` — Stages 1 and 2 together, posting-aware (Task 19).

Drives the real Typer app through `CliRunner`, mirroring `test_projection_cli_project.py`'s own
`Env`/`run` shape for the bundle half and `tests/unit/test_tailor_cmd.py`'s `_seed_open_posting`
shape for the posting half — this is the first `tests/projection/` suite that needs both a
promoted bundle AND a seeded database in the same environment, because unlike `profile-bundle
project` this command opens the database (JD skills and the page budget are posting-context
facts, not bundle facts).

The packaged example declaration (`projection.example.yaml`) has exactly one pinned entry
(`entry.employment.example-labs`) and one candidate (`entry.project.packet-pantry`), and its
`no_match_fallback` names that same candidate — so with `skills=("Python", "JavaScript")` (which
matches nothing in the candidate's claim text, "Built a retry-safe ingestion path and measured
its sustained local throughput"), the candidate is admitted via the no-match fallback rather than
by ranking. Both entries end up in the résumé either way; the tests below check that directly
rather than asserting which code path inside `select` produced it (that is Task 23's own suite).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.scoring import SCORERS
from boardwatch.projection.stamp import write_stamp
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, extractions, jobs, posting_versions, postings
from boardwatch.tailor.load import load_resume
from tests.profile_bundle.conftest import (
    PromotedRevisionTree,
    promote_example_tree,
    promote_next_revision,
)

NOW = datetime(2026, 8, 2, 12, 0, 0)

_SHELL_BODY = (
    "header:\n"
    "  - Example Candidate\n"
    "  - candidate@example.com\n"
    "education:\n"
    "  - Example University\n"
)


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path
    declaration: Path
    tree: PromotedRevisionTree
    posting_id: int


def _seed_posting(
    data_dir: Path,
    config_dir: Path,
    *,
    status: str = "open",
    skills: tuple[str, ...] = ("Python", "JavaScript"),
    resume_max_pages: int = 1,
) -> int:
    """One posting with a current version, a taxonomy extraction, and a profile row — everything
    `posting_context` (Task 17) needs. Mirrors `tests/projection/test_projection_posting.py`'s own
    `_seed` and `tests/unit/test_tailor_cmd.py`'s `_seed_open_posting`."""
    settings = Settings(data_dir=data_dir, config_dir=config_dir)
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn,
            text="t",
            target_titles=[],
            exclude_titles=[],
            locations=[],
            remote_only=False,
            skills=[],
            taxonomy_version="v1",
            resume_max_pages=resume_max_pages,
        )
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id="pp-acme",
                    title="Backend Engineer",
                    normalized_title="backend engineer",
                    url="https://example.test/acme",
                    locations_json=["Remote"],
                    remote_policy="remote",
                    posted_at=NOW,
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                    status=status,
                    consecutive_missing=0,
                    content_hash="h1",
                    body_text="Python JavaScript backend services",
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash="h1",
                body_text="Python JavaScript backend services",
                captured_at=NOW,
                capture_reason="new",
            )
        )
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id,
                content_hash="h1",
                kind="taxonomy",
                engine_version=load_taxonomy(settings.config_dir).version,
                json={"skills": list(skills)},
                created_at=NOW,
            )
        )
    return posting_id


def _make_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    approve: bool = True,
    posting_status: str = "open",
    declaration_patch: Callable[[str], str] | None = None,
) -> Env:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))

    tree = promote_example_tree(config_dir / BUNDLE_DIR_NAME)
    (config_dir / "master_resume.yaml").write_text(_SHELL_BODY, encoding="utf-8")

    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as packaged:
        declaration_text = packaged.read_text(encoding="utf-8")
    if declaration_patch is not None:
        declaration_text = declaration_patch(declaration_text)
    declaration_path = config_dir / "projection.yaml"
    declaration_path.write_text(declaration_text, encoding="utf-8")

    if approve:
        digest = projection_digest(load_declaration(declaration_path))
        write_stamp(
            config_dir,
            digest=digest,
            bundle_digest=tree.bundle_digest,
            approved_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
        )

    data_dir = tmp_path / "data"
    posting_id = _seed_posting(data_dir, config_dir, status=posting_status)

    return Env(
        data_dir=data_dir,
        config_dir=config_dir,
        declaration=declaration_path,
        tree=tree,
        posting_id=posting_id,
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return _make_env(tmp_path, monkeypatch)


@pytest.fixture
def unapproved_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return _make_env(tmp_path, monkeypatch, approve=False)


@pytest.fixture
def closed_posting_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return _make_env(tmp_path, monkeypatch, posting_status="closed")


def _drop_the_lone_candidate_from_fallback(text: str) -> str:
    """Same packaged declaration, except `packet-pantry` is named in NO fallback either — so
    with this file's default JD skills (which already clear no scorer's `ADMISSION_FLOOR`,
    per `test_pinned_entry_is_always_present...`'s own note), nothing admits the candidate: it
    is dropped from the résumé entirely, unlike every other fixture in this file, where it
    always reaches the résumé one way or another."""
    patched = text.replace(
        "no_match_fallback:\n  - project.packet-pantry\n", "no_match_fallback: []\n"
    )
    assert patched != text  # the substitution actually matched the packaged text
    return patched


@pytest.fixture
def dropped_candidate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return _make_env(
        tmp_path, monkeypatch, declaration_patch=_drop_the_lone_candidate_from_fallback
    )


def _use_bullet_predicates_instead_of_claims(text: str) -> str:
    """The packaged example declares bullets via explicit `claims:`; the LIVE master-reservoir
    declaration declares them via `bullet_predicates:` (D-188) instead, and every other fixture in
    this file uses only the `claims:` form. This rewrites both entries to the predicate form over
    the same synthetic bundle, whose `employment.accomplishment` and `project.contribution` facts
    are both résumé-surfaced."""
    patched = text.replace(
        "    claims:\n      - claim.example-labs.ownership.001\n",
        "    bullet_predicates:\n      - employment.accomplishment\n",
    ).replace(
        "    claims:\n      - claim.packet-pantry.backend.001\n",
        "    bullet_predicates:\n      - project.contribution\n",
    )
    assert patched != text and "claims:" not in patched  # both substitutions matched
    return patched


@pytest.fixture
def predicate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return _make_env(
        tmp_path, monkeypatch, declaration_patch=_use_bullet_predicates_instead_of_claims
    )


def run(env: Env, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(app, ["--data-dir", str(env.data_dir), "resume", "project", *args])


# --------------------------------------------------------------------------------------
# The group exists and is registered on the real app
# --------------------------------------------------------------------------------------


def test_resume_is_a_registered_top_level_group() -> None:
    result = CliRunner().invoke(app, ["resume", "--help"])
    assert result.exit_code == 0, result.output
    assert "project" in result.output


# --------------------------------------------------------------------------------------
# The brief's required steps: writes both files beside each other; loads through load_resume
# --------------------------------------------------------------------------------------


def test_writes_resume_and_manifest_beside_each_other(env: Env) -> None:
    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])
    assert result.exit_code == 0, result.output

    out_dir = env.data_dir / "projected" / str(env.posting_id)
    resume_path = out_dir / "resume.projected.yaml"
    manifest_path = out_dir / "projection-manifest.json"
    assert resume_path.is_file(), result.output
    assert manifest_path.is_file(), result.output
    assert resume_path.parent == manifest_path.parent


def test_an_explicit_out_directory_is_honoured(env: Env, tmp_path: Path) -> None:
    custom = tmp_path / "wherever"
    result = run(
        env,
        ["--posting", str(env.posting_id), "--scorer", "total_distinct", "--out", str(custom)],
    )
    assert result.exit_code == 0, result.output
    assert (custom / "resume.projected.yaml").is_file()
    assert (custom / "projection-manifest.json").is_file()


def test_the_emitted_document_loads_through_load_resume(env: Env) -> None:
    """The brief's own load-bearing claim: the projected document must survive
    `load_resume`'s `validate_master` gate, not merely re-parse as YAML."""
    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])
    assert result.exit_code == 0, result.output
    resume_path = env.data_dir / "projected" / str(env.posting_id) / "resume.projected.yaml"

    resume = load_resume(resume_path)  # raises ResumeLoadError/MasterResumeError if it fails

    entry_ids = {entry.entry_id for entry in resume.entries}
    assert "entry.employment.example-labs" in entry_ids
    assert "entry.project.packet-pantry" in entry_ids
    # The resolved literal, never the raw template — same property `profile-bundle project`
    # already checks for Stage 1 alone.
    raw = resume_path.read_text(encoding="utf-8")
    assert "{@display_name}" not in raw


def test_pinned_entry_is_always_present_and_the_lone_candidate_reaches_it_via_fallback(
    env: Env,
) -> None:
    """`skills=("Python", "JavaScript")` (the env fixture's default) matches nothing in the one
    candidate's claim text, so it scores 0 against every registered scorer and never clears
    `ADMISSION_FLOOR` — the fallback path admits it instead, because the packaged declaration's
    own `no_match_fallback` names the same, only, candidate. Both code paths are already Task
    23's own suite; this only proves the CLI is wired to the fallback outcome faithfully."""
    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])
    assert result.exit_code == 0, result.output
    assert "fallback True" in result.output, result.output

    manifest_path = env.data_dir / "projected" / str(env.posting_id) / "projection-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["selected_entry_ids"]) == {
        "entry.employment.example-labs",
        "entry.project.packet-pantry",
    }
    assert manifest["pinned_entry_ids"] == ["entry.employment.example-labs"]


# --------------------------------------------------------------------------------------
# The manifest sidecar's own contents
# --------------------------------------------------------------------------------------


def test_manifest_carries_the_pool_lineage_and_a_score_for_every_candidate(env: Env) -> None:
    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])
    assert result.exit_code == 0, result.output
    manifest_path = env.data_dir / "projected" / str(env.posting_id) / "projection-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["bundle_digest"] == env.tree.bundle_digest
    assert manifest["posting_id"] == env.posting_id
    assert manifest["jd_skills"] == sorted(["Python", "JavaScript"])
    # Recorded even though it never clears the admission floor — the manifest's own job is
    # "which score each candidate got", not just the admitted ones.
    scores = dict(manifest["scores"])
    assert scores == {"entry.project.packet-pantry": "0"}

    # Independent oracle: every claim id every SELECTED entry declares, read from a fresh parse
    # of the declaration file itself — never from `claim_to_bullet` under test. Before the fix,
    # `claim_to_bullet` was built as `(bullet.bullet_id, bullet.bullet_id)`, so this comparison
    # would have passed by coincidence even if `_build_entry` had stopped setting
    # `bullet_id=claim_id`; comparing against a value this test derives independently would not.
    declaration = load_declaration(env.declaration)
    selected_entity_ids = {"employment.example-labs", "project.packet-pantry"}
    expected_claims = {
        claim_id
        for entry_decl in declaration.entries
        if entry_decl.entity_id in selected_entity_ids
        for claim_id in entry_decl.claims
    }
    claim_pairs = dict(manifest["claim_to_bullet"])
    assert claim_pairs  # non-empty: at least the pinned entry's own claim/bullet
    assert set(claim_pairs) == expected_claims
    for claim_id, bullet_id in claim_pairs.items():
        assert bullet_id == claim_id  # pool._build_entry's identity map, today


# --------------------------------------------------------------------------------------
# `--scorer`: defaults to mean_per_bullet (D-198); unknown name is a typed refusal; choices DERIVED
# --------------------------------------------------------------------------------------


def test_scorer_defaults_to_mean_per_bullet(env: Env) -> None:
    """D-198 adopted `mean_per_bullet` from the owner-labeled selection matrix, so `--scorer` is
    no longer required: omitting it runs, and runs AS `mean_per_bullet`. The command echoes the
    scorer it actually used from the typer-resolved option value, so a different silent default
    would name itself here instead — this reads the default through the real CLI path, not a
    literal typed into the test."""
    result = run(env, ["--posting", str(env.posting_id)])
    assert result.exit_code == 0, result.output
    assert "Missing option" not in result.output
    assert "scorer mean_per_bullet" in result.output, result.output


def test_an_unknown_scorer_name_is_a_typed_refusal_naming_the_real_choices(env: Env) -> None:
    result = run(env, ["--posting", str(env.posting_id), "--scorer", "not-a-real-scorer"])
    assert result.exit_code != 0
    assert "not-a-real-scorer" in result.output
    # Non-vacuity: SCORERS really has members, so a broken derivation returning {} could not
    # coincidentally pass this by asserting nothing.
    assert len(SCORERS) > 0
    for name in SCORERS:
        assert name in result.output, result.output


def test_scorer_choices_are_read_from_scorers_at_runtime_not_a_hardcoded_list(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replaces the real `SCORERS` mapping with a single fake entry and proves the CLI's error
    message reflects THAT mapping, not a copy captured at import time or a list written into the
    command itself — the property R31 requires ("derived... at runtime")."""
    import boardwatch.projection.scoring as scoring_mod

    def _fake_scorer(entry: object, jd_skills: object, table: object, taxonomy: object) -> object:
        raise AssertionError("never actually called by this test")

    monkeypatch.setattr(scoring_mod, "SCORERS", {"only_choice_in_this_test": _fake_scorer})

    result = run(env, ["--posting", str(env.posting_id), "--scorer", "bogus"])
    assert result.exit_code != 0
    assert "only_choice_in_this_test" in result.output
    assert "total_distinct" not in result.output


# --------------------------------------------------------------------------------------
# Typed refusals propagate to a non-zero exit with the underlying issue named
# --------------------------------------------------------------------------------------


def test_refuses_without_bundle_approval(unapproved_env: Env) -> None:
    result = run(unapproved_env, ["--posting", str(unapproved_env.posting_id), "--scorer", "total_distinct"])
    assert result.exit_code != 0
    assert "missing_projection_approval" in result.output


def _add_second_skill(data: Any) -> None:
    """An ADDITION, not an edit — mirrors `test_projection_cli_project.py`'s own
    `_add_second_skill` — so it changes the bundle's content digest without invalidating any
    reference `projection.example.yaml` makes."""
    clone = copy.deepcopy(data["skills"][0])
    clone["skill_id"] = "skill.resume-project-cli-test-added"
    clone["canonical_name"] = "Resume Project CLI Test Skill"
    clone["aliases"] = ["resume-project-cli-test-skill"]
    data["skills"].append(clone)


def test_refuses_when_the_bundle_has_moved_since_approval(env: Env) -> None:
    """D-167/C2: the bundle-digest comparison is unconditional inside `project_pool`, so `resume
    project` — the command that actually writes a résumé — must refuse here too, not only
    `profile-bundle project`. Before the fix, this command never read the stamp back at all, so a
    bundle promoted after approval would silently reach the résumé with template text the owner
    never reviewed."""
    promote_next_revision(env.tree, mutate=_add_second_skill)

    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])

    assert result.exit_code != 0
    assert "stale_projection_approval" in result.output
    out_dir = env.data_dir / "projected" / str(env.posting_id)
    assert not out_dir.exists(), "nothing should be written once the stamp is refused"


def test_refuses_a_closed_posting(closed_posting_env: Env) -> None:
    result = run(
        closed_posting_env,
        ["--posting", str(closed_posting_env.posting_id), "--scorer", "total_distinct"],
    )
    assert result.exit_code != 0
    assert "posting_not_open" in result.output


def test_refuses_an_unknown_posting_id(env: Env) -> None:
    result = run(env, ["--posting", "999999", "--scorer", "total_distinct"])
    assert result.exit_code != 0
    assert "posting_no_current_version" in result.output


# --------------------------------------------------------------------------------------
# Whole-branch review C1: `reject_entry_declaring_personas` (Task 15) was wired to no production
# path — its only callers were its own tests. `resume_project` is the command that actually
# reaches `apply_persona` later (via `tailor run`), so this is the command that must refuse first.
# --------------------------------------------------------------------------------------

_PERSONA_DECLARES_ENTRIES = """
personas:
  - id: general_swe
    title: "Software Engineer"
    default: true
    role_families: [backend]
    skill_group_order: []
    entries: [entry.x, entry.y]
"""


def test_refuses_a_persona_declaring_entries_before_selection_runs(env: Env) -> None:
    """An owner override at `{config_dir}/personas.yaml` that declares `entries` must be refused
    here, cleanly, rather than surviving to crash inside `apply_persona` during a later
    `tailor run` (Task 15's own module docstring)."""
    (env.config_dir / "personas.yaml").write_text(_PERSONA_DECLARES_ENTRIES, encoding="utf-8")

    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])

    # A clean typed refusal, not an uncaught crash: `SystemExit` is what a clean `typer.Exit`
    # raises; an uncaught `ProjectionError` would leave `result.exception` as that exception
    # instead, and `exit_code != 0` alone cannot tell the two apart.
    assert isinstance(result.exception, SystemExit), (
        f"expected a clean refusal, got an uncaught {result.exception!r}"
    )
    assert result.exit_code != 0
    assert "persona_declares_entries" in result.output
    assert "general_swe" in result.output

    # Nothing was written: the refusal happens before `project_pool`/`select` ever run.
    out_dir = env.data_dir / "projected" / str(env.posting_id)
    assert not out_dir.exists()


# --------------------------------------------------------------------------------------
# Fix round 1, Finding 1: `renderer.emit(resume)` (inside `select`'s `compile_prefix`)
# resolves and validates a user-supplied `{config_dir}/resume_template.tex`, and a leftover
# artifact there raises `TemplateArtifactError` — a bare `RuntimeError`, not `ProjectionError`.
# --------------------------------------------------------------------------------------


def test_a_leftover_template_artifact_in_a_custom_template_is_a_typed_refusal_not_a_crash(
    env: Env,
) -> None:
    """A custom template is explicitly supported (`LatexRenderer(config_dir=config_dir)`), and
    `_validate_template` (`tailor/render/latex.py`) raises `TemplateArtifactError` for a leftover
    TODO/FIXME/lorem-ipsum token, a `<placeholder>`, or a stray `%%..%%` marker. Before this fix
    only `except ProjectionError` guarded `select(...)`, so this would have propagated as an
    unhandled traceback. `exit_code != 0` alone cannot tell a typed refusal from an uncaught
    crash — both report the same code through `CliRunner` — so `result.exception` is asserted
    to be the clean `SystemExit` a `typer.Exit` raises, not the real `TemplateArtifactError`."""
    bad_template = "%%SECTIONS_START%%\n%%SECTIONS_END%%\nTODO: finish this template\n"
    (env.config_dir / "resume_template.tex").write_text(bad_template, encoding="utf-8")

    result = run(env, ["--posting", str(env.posting_id), "--scorer", "total_distinct"])

    assert isinstance(result.exception, SystemExit), (
        f"expected a clean refusal, got an uncaught {result.exception!r}"
    )
    assert result.exit_code != 0
    assert "TODO" in result.output


# --------------------------------------------------------------------------------------
# Fix round 1, Finding 2: `claim_to_bullet` is scoped to `selection.resume.entries` (the
# FINAL résumé), not `pool.resume.entries` (every declared entry) — a scoping choice no
# existing fixture could discriminate, because every one of them keeps every entry.
# --------------------------------------------------------------------------------------


def test_a_dropped_candidates_claim_is_absent_while_the_survivors_claim_is_present(
    dropped_candidate_env: Env,
) -> None:
    """`dropped_candidate_env` names the lone candidate in no fallback, and the fixture's own
    default JD skills clear no scorer's floor either — so the candidate is admitted by NEITHER
    path and never reaches the résumé. If `claim_to_bullet` were built from `pool.resume.entries`
    instead, the dropped candidate's claim would still appear (`pool.resume.entries` holds every
    DECLARED entry, selected or not); asserting both directions catches that, since an
    absence-only assertion could pass on an empty map."""
    result = run(
        dropped_candidate_env,
        ["--posting", str(dropped_candidate_env.posting_id), "--scorer", "total_distinct"],
    )
    assert result.exit_code == 0, result.output

    manifest_path = (
        dropped_candidate_env.data_dir
        / "projected"
        / str(dropped_candidate_env.posting_id)
        / "projection-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["selected_entry_ids"] == ["entry.employment.example-labs"]

    claim_pairs = dict(manifest["claim_to_bullet"])
    assert "claim.example-labs.ownership.001" in claim_pairs
    assert "claim.packet-pantry.backend.001" not in claim_pairs


# --------------------------------------------------------------------------------------
# The live declaration renders bullets from `bullet_predicates` (D-188), not `claims` — the
# path the first real emission crashed on and no other fixture in this file exercises.
# --------------------------------------------------------------------------------------


def test_a_predicate_declarations_bullets_map_to_their_source_fact_ids(
    predicate_env: Env,
) -> None:
    """Regression for the first real emission's crash. A `bullet_predicates` entry declares no
    `claims`, so `entry_decl.claims` is empty while the entry still has fact-derived bullets;
    building `claim_to_bullet` by zipping the (empty) claims against those bullets with
    `strict=True` raised `ValueError: zip() argument 2 is longer than argument 1`. The mapping is
    now read from each bullet's own id, which `pool._build_entry` sets to the source fact id for
    the predicate path.

    Independent oracle: the two expected ids are read from the synthetic bundle's own fact files,
    not from the manifest under test — `fact.example-labs.accomplishment.001` and
    `fact.packet-pantry.contribution.001` are its only résumé-surfaced facts for those predicates,
    so a claims-path regression (which would key on `claim.*` ids) fails this outright."""
    result = run(
        predicate_env,
        ["--posting", str(predicate_env.posting_id), "--scorer", "total_distinct"],
    )
    assert result.exit_code == 0, result.output

    manifest_path = (
        predicate_env.data_dir
        / "projected"
        / str(predicate_env.posting_id)
        / "projection-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert dict(manifest["claim_to_bullet"]) == {
        "fact.example-labs.accomplishment.001": "fact.example-labs.accomplishment.001",
        "fact.packet-pantry.contribution.001": "fact.packet-pantry.contribution.001",
    }
