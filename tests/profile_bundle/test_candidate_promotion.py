"""`profile-bundle promote-candidates`: the §6.8 promotion slice (Gate B).

`extract` lands typed candidates and stops; a record reaches `imported` on candidates alone.
Promotion is the only place those candidates become the renderable graph: entities, entity-bound
`FactRecord`s, and `SkillRecord`s whose `skill_id` becomes a real reference (§6.4). It is grounded
and owner-mediated (D-182): every fact is born `unresolved` with no fabricated evidence, and a
skill's entity binding is the one grounded signal a résumé carries — a bullet's authored
`tech_tags`. The owner's confirm/attest/approve step is what promotes and renders.

These tests drive a fresh `init` bundle (NOT the comprehensive example, whose catalog omits
`project.name`, D-179) so a résumé WITH projects extracts, then promote its candidates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle import authoring, drafts
from boardwatch.profile_bundle.models.documents import (
    EmploymentFactsDocument,
    ProjectFactsDocument,
    SkillInventoryDocument,
)
from boardwatch.profile_bundle.models.policy import SkillCategoryCatalog
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME, draft_root
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes

RESUME_SOURCE_ID = "source.synthetic-resume"
AS_OF = date(2026, 8, 14)

#: One employment entry and one project entry, each with a bullet whose `tech_tags` names a skill
#: item exactly. `Rust` is a skill item that no bullet tags — it must NOT become a skill (no entity
#: to ground it).
RESUME_DOCUMENT: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["Python", "Swift", "Rust"]}],
    "entries": [
        {
            "entry_id": "eng-role",
            "heading": "Engineer — Acme — Jan 2020–Feb 2021 — New York, NY",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Jan 2020 -- Feb 2021",
            "location": "New York, NY",
            "bullets": [
                {"bullet_id": "b1", "text": "Built the pipeline.", "tech_tags": ["Python"]}
            ],
        },
        {
            "entry_id": "side-proj",
            "heading": "Widget",
            "kind": "project",
            "title": "Widget",
            "dates": "Mar 2021 -- Present",
            "bullets": [{"bullet_id": "p1", "text": "Shipped the widget.", "tech_tags": ["Swift"]}],
        },
    ],
}

#: D-184 finding 3: two distinct skill items the deliberately-lossy `_derive_skill_id` (D-180) both
#: slug to `skill.c`. A bullet tags both, so `skill.c` is grounded — the exact shape a last-write-wins
#: merge would collapse to one `SkillRecord`, silently dropping the other.
COLLIDING_RESUME: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["C++", "C#"]}],
    "entries": [
        {
            "entry_id": "eng-role",
            "heading": "Engineer — Acme — Jan 2020–Feb 2021 — New York, NY",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Jan 2020 -- Feb 2021",
            "location": "New York, NY",
            "bullets": [{"bullet_id": "b1", "text": "Shipped it.", "tech_tags": ["C++", "C#"]}],
        },
    ],
}

#: The corruption arm of the same finding: only `C++` is tagged, but `C#` shares `skill.c`, so the
#: single grounded skill would silently take whichever colliding item was written last as its
#: `canonical_name` — possibly the untagged sibling's. Still an ambiguous grounded id.
COLLIDING_ONE_GROUNDED: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["C++", "C#"]}],
    "entries": [
        {
            "entry_id": "eng-role",
            "heading": "Engineer — Acme — Jan 2020–Feb 2021 — New York, NY",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Jan 2020 -- Feb 2021",
            "location": "New York, NY",
            "bullets": [{"bullet_id": "b1", "text": "Shipped it.", "tech_tags": ["C++"]}],
        },
    ],
}

#: Two entries whose ids pass the case/punctuation-sensitive dedup (`acme-2021` != `acme_2021`) but whose
#: `_slug` collides (both -> `employment.acme-2021`). Same lossy-slug class as the skill collision, one
#: field over: a bare last-write-wins on the document path would drop a whole entity + its facts.
ENTITY_COLLIDING_RESUME: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["Python"]}],
    "entries": [
        {
            "entry_id": "acme-2021",
            "heading": "Engineer — Acme — Jan 2020–Feb 2021 — New York, NY",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Jan 2020 -- Feb 2021",
            "location": "New York, NY",
            "bullets": [{"bullet_id": "b1", "text": "Did A.", "tech_tags": []}],
        },
        {
            "entry_id": "acme_2021",
            "heading": "Engineer — Beta — Mar 2021–Apr 2022 — San Francisco, CA",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Mar 2021 -- Apr 2022",
            "location": "San Francisco, CA",
            "bullets": [{"bullet_id": "b2", "text": "Did B.", "tech_tags": []}],
        },
    ],
}

#: Two skill-group labels that pass dedup (`Front End` != `Front-End`) but whose `_slug` collides (both ->
#: category `front-end`). Both groups' skills are grounded, so both reach the category builder; a bare
#: last-write-wins would merge the two categories and drop one label.
CATEGORY_COLLIDING_RESUME: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [
        {"label": "Front End", "items": ["React"]},
        {"label": "Front-End", "items": ["Vue"]},
    ],
    "entries": [
        {
            "entry_id": "eng-role",
            "heading": "Engineer — Acme — Jan 2020–Feb 2021 — New York, NY",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Jan 2020 -- Feb 2021",
            "location": "New York, NY",
            "bullets": [{"bullet_id": "b1", "text": "Shipped it.", "tech_tags": ["React", "Vue"]}],
        },
    ],
}


#: The fourth site of the same lossy-slug class — missed by D-203's sweep, found by its pre-push review.
#: Both fact-id builders drop the entity KIND (`_entry_facts` uses `_slug(entity_id.split('.', 1)[1])`,
#: `_tech_fact` uses `_slug(entry_id)`), so two entries of *different* kinds whose ids slug-collide get
#: DISTINCT entity ids (`employment.alpha`, `project.alpha`), pass the D-203 entity guard, and still
#: collide in the global fact-id namespace. The tech fact is the reachable arm: `.tech.` is hardcoded
#: regardless of kind, whereas metadata/bullet facts carry kind-specific predicate locals that differ.
FACT_ID_COLLIDING_RESUME: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.com"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["Python"]}],
    "entries": [
        {
            "entry_id": "alpha",
            "heading": "Engineer — Acme — Jan 2020–Feb 2021 — New York, NY",
            "kind": "experience",
            "title": "Engineer",
            "dates": "Jan 2020 -- Feb 2021",
            "location": "New York, NY",
            "bullets": [{"bullet_id": "b1", "text": "Did A.", "tech_tags": ["Python"]}],
        },
        {
            "entry_id": "Alpha",
            "heading": "Alpha",
            "kind": "project",
            "title": "Alpha",
            "dates": "Mar 2021 -- Present",
            "bullets": [{"bullet_id": "p1", "text": "Did B.", "tech_tags": ["Python"]}],
        },
    ],
}


@dataclass(frozen=True)
class Env:
    bundle_root: Path
    resume_bytes: bytes

    @property
    def draft(self) -> Path:
        return draft_root(self.bundle_root, "baseline")

    def employment(self, entity_id: str) -> EmploymentFactsDocument:
        raw = (self.draft / "facts" / "experience" / f"{entity_id}.yaml").read_bytes()
        return EmploymentFactsDocument.model_validate(
            load_yaml_bytes(raw, logical_path=PurePosixPath("facts/experience/x.yaml"))
        )

    def project(self, entity_id: str) -> ProjectFactsDocument:
        raw = (self.draft / "facts" / "projects" / f"{entity_id}.yaml").read_bytes()
        return ProjectFactsDocument.model_validate(
            load_yaml_bytes(raw, logical_path=PurePosixPath("facts/projects/x.yaml"))
        )

    def skills(self) -> SkillInventoryDocument:
        raw = (self.draft / "skills" / "inventory.yaml").read_bytes()
        return SkillInventoryDocument.model_validate(
            load_yaml_bytes(raw, logical_path=PurePosixPath("skills/inventory.yaml"))
        )

    def categories(self) -> SkillCategoryCatalog:
        raw = (self.draft / "policy" / "skill-categories.yaml").read_bytes()
        return SkillCategoryCatalog.model_validate(
            load_yaml_bytes(raw, logical_path=PurePosixPath("policy/skill-categories.yaml"))
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    """A fresh v2 `init` bundle seeded from the module's default résumé document."""
    return _seed(tmp_path, RESUME_DOCUMENT)


def _seed(tmp_path: Path, document: dict[str, Any]) -> Env:
    """A fresh v2 `init` bundle with a `boardwatch_resume` source declared, imported and extracted.

    The source declaration is the owner-approval step the command does not perform; declaring it in
    the fixture is the same shortcut the extract CLI test takes.
    """
    root = tmp_path / BUNDLE_DIR_NAME
    root.mkdir(parents=True)
    (root / "drafts").mkdir()
    out = drafts.init_draft(root, name="baseline")
    assert out.value is not None, out

    draft = draft_root(root, "baseline")
    sources_path = draft / "policy" / "sources.yaml"
    declared = load_yaml_bytes(
        sources_path.read_bytes(), logical_path=PurePosixPath("policy/sources.yaml")
    )
    assert isinstance(declared, dict)
    declared["sources"].append(
        {
            "source_id": RESUME_SOURCE_ID,
            "source_kind": "boardwatch_resume",
            "portable_locator": "resume.yaml",
        }
    )
    sources_path.write_bytes(
        document_bytes(declared, logical_path=PurePosixPath("policy/sources.yaml"))
    )

    # `init` omits facts/identity.yaml on purpose (the owner's display name + review dates). Author a
    # synthetic one so the draft is otherwise complete and validation isolates promotion's output.
    identity = {
        "person": {
            "entity_id": "person.ada",
            "entity_type": "person",
            "display_name": "Ada Lovelace",
            "created_at": AS_OF.isoformat(),
            "reviewed_at": AS_OF.isoformat(),
        },
        "contacts": [],
        "facts": [],
    }
    (draft / "facts" / "identity.yaml").write_bytes(
        document_bytes(identity, logical_path=PurePosixPath("facts/identity.yaml"))
    )

    resume_bytes = document_bytes(document, logical_path=PurePosixPath("resume.yaml"))
    assert (
        authoring.import_source(
            root, draft_name="baseline", source_id=RESUME_SOURCE_ID, source_bytes=resume_bytes
        ).exit_code
        == 0
    )
    assert (
        authoring.extract_source(
            root, draft_name="baseline", source_id=RESUME_SOURCE_ID, source_bytes=resume_bytes
        ).exit_code
        == 0
    )
    return Env(bundle_root=root, resume_bytes=resume_bytes)


def promote(env: Env):  # type: ignore[no-untyped-def]
    return authoring.promote_candidates(
        env.bundle_root,
        draft_name="baseline",
        source_id=RESUME_SOURCE_ID,
        source_bytes=env.resume_bytes,
        as_of=AS_OF,
    )


def test_promotion_creates_entities_and_only_tech_tag_grounded_skills(env: Env) -> None:
    """The headline: each entry becomes an entity, and only skills a bullet's tech_tags grounds
    become `SkillRecord`s. `Rust` is a skill item no bullet tags, so it never becomes a skill."""
    outcome = promote(env)
    assert outcome.exit_code == 0, outcome

    employment = env.employment("employment.eng-role")
    project = env.project("project.side-proj")
    assert employment.entity.display_name  # created
    assert project.entity.entity_id == "project.side-proj"

    skill_ids = {skill.skill_id for skill in env.skills().skills}
    assert skill_ids == {"skill.python", "skill.swift"}

    python = next(s for s in env.skills().skills if s.skill_id == "skill.python")
    # The skill is grounded by a real technology.used fact on the employment entity.
    (supporting,) = python.supporting_fact_ids
    tech_facts = [f for f in employment.facts if f.predicate == "technology.used"]
    assert [f.fact_id for f in tech_facts] == [supporting]
    assert tech_facts[0].value.skill_id == "skill.python"


def test_the_promoted_draft_validates(env: Env) -> None:
    """The whole point: every entity, fact, and skill the builder writes is a legal member of a
    draft. Run through `validate_bundle` — a different path than the one that produced them — so a
    structural, referential, or semantic defect (a bad subject kind, an unresolvable skill_ref, an
    illegal surface) fails here rather than surfacing only at promotion."""
    from boardwatch.profile_bundle.validation.run import validate_bundle

    assert promote(env).exit_code == 0
    report = validate_bundle(env.draft, bundle_root=env.bundle_root, mode="draft")
    assert report.exit_code == 0, [(d.tier, d.code, d.message) for d in report.diagnostics]
    # And nothing structural/referential/semantic survives even as a warning about our records.
    offending = [d for d in report.diagnostics if d.tier in ("error", "blocker")]
    assert offending == [], [(d.code, d.message) for d in offending]


def test_facts_are_born_unresolved_with_no_fabricated_evidence(env: Env) -> None:
    """D-182: promotion never fabricates an attestation. Every fact is `unresolved`, cites no
    evidence, and a grounded skill's surfaces are empty until the owner confirms its facts."""
    from boardwatch.profile_bundle.models.base import VerificationState

    assert promote(env).exit_code == 0

    all_facts = [
        *env.employment("employment.eng-role").facts,
        *env.project("project.side-proj").facts,
    ]
    assert all_facts  # facts were written
    for fact in all_facts:
        assert fact.verification_state is VerificationState.UNRESOLVED, fact.fact_id
        assert fact.evidence_ids == (), fact.fact_id
        assert fact.import_lineage is not None and fact.import_lineage.source_id == RESUME_SOURCE_ID

    for skill in env.skills().skills:
        assert skill.allowed_surfaces == (), skill.skill_id


def test_entity_status_is_derived_from_dates(env: Env) -> None:
    """A closed employment is `completed`; a project whose dates run to Present is
    `active_development`. Both are owner-editable before promotion, but the default must be honest."""
    from boardwatch.profile_bundle.models.entities import EmploymentStatus, ProjectStatus

    assert promote(env).exit_code == 0
    assert env.employment("employment.eng-role").entity.status is EmploymentStatus.COMPLETED
    assert env.project("project.side-proj").entity.status is ProjectStatus.ACTIVE_DEVELOPMENT


def test_re_promotion_refuses_rather_than_clobbering(env: Env) -> None:
    """Promotion is one-shot (§6.8/D-182): once entities and skills exist, re-running would recreate
    the same IDs over the owner's edits, so it refuses with one code and writes nothing."""
    assert promote(env).exit_code == 0
    again = promote(env)
    assert again.exit_code != 0
    assert [d.code for d in again.diagnostics] == ["duplicate_record_id"]


def test_promotion_refuses_when_two_skills_collide_to_one_id(tmp_path: Path) -> None:
    """D-184 finding 3: `C++` and `C#` both derive `skill.c` (the slug is lossy on purpose, D-180),
    so a bare last-write-wins merge keeps one `SkillRecord` and drops the other with no diagnostic —
    a multi-tenancy data loss. Promotion must refuse the ambiguous grounded id and write nothing,
    exactly as `_entry_subject_kind` refuses an entry that resolves to more than one subject kind.
    The refusal names the id and every colliding item so the owner can rename or merge them."""
    env = _seed(tmp_path, COLLIDING_RESUME)
    outcome = authoring.promote_candidates(
        env.bundle_root,
        draft_name="baseline",
        source_id=RESUME_SOURCE_ID,
        source_bytes=env.resume_bytes,
        as_of=AS_OF,
    )
    assert outcome.exit_code != 0, outcome
    (diag,) = outcome.diagnostics
    assert diag.code == "model_validation_error", diag
    assert "skill.c" in diag.message
    assert "C++" in diag.message and "C#" in diag.message


def test_promotion_refuses_a_grounded_id_with_an_untagged_colliding_sibling(tmp_path: Path) -> None:
    """The corruption arm of D-184 finding 3: only `C++` is tagged, but `C#` shares `skill.c`, so the
    single grounded skill would silently take whichever colliding item was written last as its
    `canonical_name`. Promotion refuses the ambiguous grounded id even when just one collider is
    tagged — the check keys on the grounded id's item set, not on how many of them a bullet grounds."""
    env = _seed(tmp_path, COLLIDING_ONE_GROUNDED)
    outcome = authoring.promote_candidates(
        env.bundle_root,
        draft_name="baseline",
        source_id=RESUME_SOURCE_ID,
        source_bytes=env.resume_bytes,
        as_of=AS_OF,
    )
    assert outcome.exit_code != 0, outcome
    (diag,) = outcome.diagnostics
    assert "skill.c" in diag.message
    assert "C++" in diag.message and "C#" in diag.message


def test_promotion_refuses_when_two_entries_collide_to_one_entity_id(tmp_path: Path) -> None:
    """Same lossy-slug class as the skill collision, one field over (D-184): `acme-2021` and `acme_2021`
    pass the case/punctuation-sensitive entry-id dedup but both `_slug` to `employment.acme-2021`, so a
    bare last-write-wins on the document path would silently drop a whole entity and all its facts —
    while the entity count still reports two. Promotion must refuse rather than merge, naming both
    entries and the shared id."""
    env = _seed(tmp_path, ENTITY_COLLIDING_RESUME)
    outcome = authoring.promote_candidates(
        env.bundle_root,
        draft_name="baseline",
        source_id=RESUME_SOURCE_ID,
        source_bytes=env.resume_bytes,
        as_of=AS_OF,
    )
    assert outcome.exit_code != 0, outcome
    (diag,) = outcome.diagnostics
    assert "employment.acme-2021" in diag.message
    assert "acme-2021" in diag.message and "acme_2021" in diag.message


def test_promotion_refuses_when_two_labels_collide_to_one_category_id(tmp_path: Path) -> None:
    """`Front End` and `Front-End` pass the label dedup but both `_slug` to category `front-end`; both
    groups' skills are grounded, so a bare last-write-wins would merge the two categories and drop one
    label. Promotion must refuse, naming both labels and the shared category id."""
    env = _seed(tmp_path, CATEGORY_COLLIDING_RESUME)
    outcome = authoring.promote_candidates(
        env.bundle_root,
        draft_name="baseline",
        source_id=RESUME_SOURCE_ID,
        source_bytes=env.resume_bytes,
        as_of=AS_OF,
    )
    assert outcome.exit_code != 0, outcome
    (diag,) = outcome.diagnostics
    assert "front-end" in diag.message
    assert "Front End" in diag.message and "Front-End" in diag.message


def test_promotion_refuses_when_two_entries_collide_to_one_fact_id(tmp_path: Path) -> None:
    """The fourth site of the D-184 lossy-slug class, missed by D-203's sweep and caught by its
    pre-push review. Both fact-id builders drop the entity kind, so `alpha`/experience and
    `Alpha`/project get distinct entity ids, clear the D-203 entity guard, and still both emit
    `fact.alpha.tech.python`. Before the guard this escaped as a bare pydantic `ValidationError`
    (the duplicate reaches `UniqueSorted` on `supporting_fact_ids`, and no `PromotionError`
    handler catches it) — never as a refusal naming the cause. It must refuse like its three
    siblings, naming the shared fact id and both colliding subjects."""
    env = _seed(tmp_path, FACT_ID_COLLIDING_RESUME)
    outcome = authoring.promote_candidates(
        env.bundle_root,
        draft_name="baseline",
        source_id=RESUME_SOURCE_ID,
        source_bytes=env.resume_bytes,
        as_of=AS_OF,
    )
    assert outcome.exit_code != 0, outcome
    (diag,) = outcome.diagnostics
    assert diag.code == "model_validation_error", diag
    assert "fact.alpha.tech.python" in diag.message
    assert "employment.alpha" in diag.message and "project.alpha" in diag.message


def test_the_owner_confirmation_step_reaches_a_grounded_resume_skill(env: Env) -> None:
    """§6.8's stop condition: the promoted graph is exactly one honest owner step from a rendering
    skill. Simulate that step — confirm a `technology.used` fact against an owner attestation and
    surface its skill — then run full draft validation, which exercises the grounding
    (`SKILL_UNSUPPORTED`) and surface (`SKILL_SURFACE_UNSUPPORTED`) checks that a born-`unresolved`
    skill never triggers. A clean result with the skill effective and résumé-surfaced is what makes
    it nameable by `projection.yaml` (the LaTeX emission itself is projection-v1's tested domain)."""
    from boardwatch.profile_bundle.validation.run import validate_bundle

    assert promote(env).exit_code == 0

    # The owner confirms the employment's technology.used(python) fact against an attestation.
    employment = env.employment("employment.eng-role").model_dump(mode="json")
    fact = next(f for f in employment["facts"] if f["predicate"] == "technology.used")
    fact["verification_state"] = "owner_confirmed"
    fact["evidence_ids"] = ["evidence.python-attestation"]
    _write(env, "facts/experience/employment.eng-role.yaml", employment)

    evidence = {
        "evidence": [
            {
                "evidence_id": "evidence.python-attestation",
                "evidence_class": "owner_attestation",
                "title": "Owner attests Python use",
                "capture": {
                    "kind": "inline",
                    "text": "I used Python here.",
                    "media_type": "text/plain",
                },
                "captured_at": f"{AS_OF.isoformat()}T00:00:00Z",
                "reviewed_at": AS_OF.isoformat(),
                "sufficiency_review": {"state": "unreviewed"},
                "redactions": [],
                "supports_record_ids": [fact["fact_id"]],
                "contradicts_record_ids": [],
                "contextualizes_record_ids": [],
                "attested_at": AS_OF.isoformat(),
            }
        ]
    }
    _write(env, "evidence/records.yaml", evidence)
    _reseal_evidence_digest(env)

    inventory = env.skills().model_dump(mode="json")
    python = next(s for s in inventory["skills"] if s["skill_id"] == "skill.python")
    python["verification_state"] = "owner_confirmed"
    python["allowed_surfaces"] = ["public", "resume"]
    _write(env, "skills/inventory.yaml", inventory)

    report = validate_bundle(env.draft, bundle_root=env.bundle_root, mode="draft")
    offending = [(d.code, d.message) for d in report.diagnostics if d.tier in ("error", "blocker")]
    assert offending == [], offending

    from boardwatch.profile_bundle.models.base import Surface

    confirmed = next(s for s in env.skills().skills if s.skill_id == "skill.python")
    assert Surface.RESUME in confirmed.allowed_surfaces


def test_the_command_promotes_end_to_end_through_the_cli(env: Env, tmp_path: Path) -> None:
    """The command mirrors `extract`: it runs through `_bundle_root`/`_guarded`/`_with_revalidation`
    and emits a JSON envelope with the promotion counts. Driven via `CliRunner` so the whole CLI
    path — the import wall included — is exercised, not just the library function."""
    resume_file = tmp_path / "resume.yaml"
    resume_file.write_bytes(env.resume_bytes)
    result = CliRunner().invoke(
        app,
        [
            "profile-bundle",
            "promote-candidates",
            "--draft",
            "baseline",
            "--source",
            RESUME_SOURCE_ID,
            "--from",
            str(resume_file),
            "--bundle",
            str(env.bundle_root),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)["result"]
    assert body["changed"] is True
    assert body["entity_count"] == 2
    assert body["skill_count"] == 2


def _write(env: Env, rel: str, payload: object) -> None:
    (env.draft / rel).write_bytes(document_bytes(payload, logical_path=PurePosixPath(rel)))


def _reseal_evidence_digest(env: Env) -> None:
    """Recompute the manifest's `evidence_set_digest` after a hand-edit of `evidence/records.yaml`.

    The real `add_evidence` command maintains this digest; the test edits the file directly, so it
    reseals it here — otherwise the (correct) digest-layer check fires on the test's own bookkeeping
    rather than on anything promotion produced."""
    from boardwatch.profile_bundle.canonical import FilesystemBlobReader, evidence_set_digest
    from boardwatch.profile_bundle.paths import blobs_dir
    from boardwatch.profile_bundle.validation import load_documents

    documents = load_documents(env.draft, mode="draft")
    reader = FilesystemBlobReader(blobs_root=blobs_dir(env.draft))
    digest = evidence_set_digest(documents, reader)
    manifest = load_yaml_bytes(
        (env.draft / "manifest.yaml").read_bytes(), logical_path=PurePosixPath("manifest.yaml")
    )
    assert isinstance(manifest, dict)
    manifest["evidence_set_digest"] = digest
    _write(env, "manifest.yaml", manifest)
