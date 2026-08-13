"""Stage 1: bundle + declaration → `ProjectionPool`. JD-blind, and total — it either emits a
faithful pool of every declared entry, or refuses outright.

**The pool, not a plain `Resume`, is the contract with Stage 2.** `tailor.model.Entry` has no
`pinned` field, so a bare `Resume` would leave Stage 2 unable to tell the fixed core from the
swappable candidates without rereading `projection.yaml` or guessing. `pool.resume.entries` holds
EVERY declared entry, pinned and candidate alike, because which candidates survive is a JD-scored
decision (a later task) that Stage 1 — reading no posting — cannot make. `pinned_entry_ids` /
`candidate_entry_ids` / `no_match_fallback_ids` name the split over those same `Entry.entry_id`
values.

**`shell_source` resolution happens HERE, and nowhere else.** `load_declaration` deliberately
performs no filesystem resolution on it (`declaration.py:67-68`, R3): this is the first place a
`config_dir` is in scope. `load_shell` likewise takes an already-resolved, absolute path and
resolves nothing itself. A relative `declaration.shell_source` resolves against `config_dir`; an
absolute one passes through unchanged — `Path.__truediv__`'s own rule for an absolute right
operand — matching every other `config_dir / <declared path>` site in this codebase
(`tailor/persona.py`, `extract/taxonomy.py`, `eligibility/catalog.py`).

Every other step calls straight into the six modules this task integrates, never restating their
checks: `read_current_once` / `selected_documents` / `context_from_documents` read the bundle's
CURRENT, promoted revision (`effectiveness.py`'s own premise); `stamp_exists` is the owner gate;
`check_references` is §7's fidelity contract; `resume_facts_for` + `resolve_template` render each
entry's templates; `render_skill` maps a skill id to display text; `load_shell` supplies the inert
header/education. `Bullet.text` is copied from `ClaimRecord.text` byte for byte — never templated —
and `tech_tags` is emitted empty on purpose: `reports/tailor.py:433` hashes the model, and an empty
list (rather than an absent field) is what keeps that hash stable until tailoring itself assigns
tags. `Resume.title` stays `None`: persona shaping is the tailor's job, not Stage 1's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from boardwatch.profile_bundle.models.claims import ClaimRecord
from boardwatch.profile_bundle.storage import read_current_once, selected_documents
from boardwatch.profile_bundle.validation.context import ValidationContext, context_from_documents
from boardwatch.projection.contract import check_references
from boardwatch.projection.declaration import EntryDeclaration, load_declaration, projection_digest
from boardwatch.projection.effectiveness import resume_facts_for
from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.projection.grammar import render_skill, resolve_template
from boardwatch.projection.shell import load_shell
from boardwatch.projection.stamp import stamp_exists
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


@dataclass(frozen=True)
class ProjectionPool:
    """The contract between Stage 1 and Stage 2.

    `resume.entries` holds every declared entry; `pinned_entry_ids` / `candidate_entry_ids` /
    `no_match_fallback_ids` locate the declaration's own split within it, by `Entry.entry_id`.
    """

    resume: Resume
    pinned_entry_ids: tuple[str, ...]
    candidate_entry_ids: tuple[str, ...]
    no_match_fallback_ids: tuple[str, ...]
    bundle_revision: str
    bundle_digest: str
    projection_digest: str


def project_pool(
    bundle_root: Path, declaration_path: Path, *, config_dir: Path, as_of: date
) -> ProjectionPool:
    """Assemble the JD-blind pool from the bundle's current revision and `declaration_path`.

    Every refusal is a `ProjectionError` from one of the six modules this composes; nothing here
    invents a new one.
    """
    declaration = load_declaration(declaration_path)
    digest = projection_digest(declaration)

    if not stamp_exists(config_dir, digest):
        raise_violation(
            ProjectionIssue.MISSING_PROJECTION_APPROVAL,
            f"projection digest {digest} has not been approved; no template literal reaches a "
            "résumé unapproved",
            where=digest,
        )

    shell_path = config_dir / declaration.shell_source

    selection = read_current_once(bundle_root)
    documents = selected_documents(selection)
    ctx = context_from_documents(
        documents, root=selection.root, mode="revision", bundle_root=bundle_root
    )

    check_references(declaration, ctx)

    header, education = load_shell(shell_path)

    claims_by_id = {c.claim_id: c for c in ctx.index.claims}
    skills_by_id = {s.skill_id: s for s in ctx.index.skills}

    skill_groups = [
        SkillGroup(
            label=group.label,
            items=[render_skill(skills_by_id[skill_id]) for skill_id in group.skills],
        )
        for group in declaration.skill_groups
    ]

    entries = [
        _build_entry(
            entry_decl,
            ctx=ctx,
            claims_by_id=claims_by_id,
            open_range_label=declaration.open_range_label,
            as_of=as_of,
        )
        for entry_decl in declaration.entries
    ]

    resume = Resume(
        header=list(header),
        education=list(education),
        skill_groups=skill_groups,
        entries=entries,
        extracurricular=list(declaration.extracurricular),
        title=None,
    )

    return ProjectionPool(
        resume=resume,
        pinned_entry_ids=tuple("entry." + entity_id for entity_id in declaration.pinned_ids),
        candidate_entry_ids=tuple(
            "entry." + entity_id for entity_id in declaration.candidate_ids
        ),
        no_match_fallback_ids=tuple(
            "entry." + entity_id for entity_id in declaration.no_match_fallback
        ),
        bundle_revision=str(selection.revision),
        bundle_digest=selection.bundle_digest,
        projection_digest=digest,
    )


def _build_entry(
    entry_decl: EntryDeclaration,
    *,
    ctx: ValidationContext,
    claims_by_id: Mapping[str, ClaimRecord],
    open_range_label: str,
    as_of: date,
) -> Entry:
    """One declared entry, fully resolved. `check_references` has already run, so every id this
    reads — the entity, each claim — is known to exist and (for claims) to be approved,
    résumé-surfaced and about this same entity.
    """
    entity = ctx.index.entities[entry_decl.entity_id]
    facts_by_predicate = resume_facts_for(entry_decl.entity_id, ctx, as_of=as_of)

    def render(template: str, field_name: str) -> str:
        return resolve_template(
            template,
            entity=entity,
            facts_by_predicate=facts_by_predicate,
            open_range_label=open_range_label,
            where=f"entries: {entry_decl.entity_id}.{field_name}",
        )

    def render_optional(template: str | None, field_name: str) -> str | None:
        return None if template is None else render(template, field_name)

    bullets = [
        # `text=` is `claim.text` verbatim — never templated, edited or reflowed. Only
        # `Bullet._single_line`'s own whitespace-run normalisation touches it, identically to
        # every other bullet in the tailoring pipeline.
        Bullet(bullet_id=claim_id, text=claims_by_id[claim_id].text, tech_tags=[])
        for claim_id in entry_decl.claims
    ]

    return Entry(
        entry_id="entry." + entry_decl.entity_id,
        heading=render(entry_decl.heading, "heading"),
        bullets=bullets,
        kind=entry_decl.kind.value,
        title=render_optional(entry_decl.title, "title"),
        dates=render_optional(entry_decl.dates, "dates"),
        subtitle=render_optional(entry_decl.subtitle, "subtitle"),
        location=render_optional(entry_decl.location, "location"),
    )
