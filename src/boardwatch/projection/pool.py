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
CURRENT, promoted revision (`effectiveness.py`'s own premise); `stamp_exists` + `read_stamp`
together are the owner gate — the first proves a digest was approved at all, the second proves
that approval still names the bundle revision actually being read, unconditionally (D-167);
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
from boardwatch.profile_bundle.storage import (
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import ValidationContext, context_from_documents
from boardwatch.projection.contract import check_references
from boardwatch.projection.declaration import EntryDeclaration, load_declaration, projection_digest
from boardwatch.projection.effectiveness import resume_facts_for
from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.projection.grammar import render_skill, resolve_template
from boardwatch.projection.shell import load_shell
from boardwatch.projection.stamp import read_stamp, stamp_exists
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


def _entry_id(entity_id: str) -> str:
    """The one derivation rule the brief states once: `entry_id = "entry." + entity_id`.
    Extracted so the four sites that need it cannot drift from one another."""
    return "entry." + entity_id


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

    Every refusal is a `ProjectionError`: most propagate from one of the six modules this
    composes, and the owner-gate check and an unreadable bundle are raised here directly — both
    from the same closed `ProjectionIssue` catalog, so nothing here invents an exception outside
    it.

    **The bundle-digest comparison is unconditional (D-167), not behind an opt-in flag.**
    `stamp_exists` alone proves only that `declaration_path`'s own content was reviewed; it says
    nothing about which bundle revision the owner was looking at when they approved it. Every
    call here — `profile-bundle project` and `resume project` alike — reads the stamp back via
    `read_stamp` and refuses if its `bundle_digest` no longer matches the bundle actually being
    read, so a résumé is never produced from resolved literals the owner never saw. `read_stamp`
    raises `ProfileBundleError`, not `ProjectionError`, for a stamp that fails to parse or
    validate against the current schema — that is deliberately allowed to propagate unwrapped
    here, exactly as `stale_projection_approval`'s propagation already worked before this
    function absorbed it; every caller of `project_pool` must catch both.
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

    try:
        selection = read_current_once(bundle_root)
        documents = selected_documents(selection)
    except SelectionError as exc:
        raise_violation(
            ProjectionIssue.BUNDLE_UNREADABLE,
            f"the bundle at {bundle_root} could not be read to produce a pool: {exc}",
            where=str(bundle_root),
        )

    stamp = read_stamp(config_dir, digest)
    if stamp.bundle_digest != selection.bundle_digest:
        raise_violation(
            ProjectionIssue.STALE_PROJECTION_APPROVAL,
            "the owner's approval was reviewed against a different bundle revision; the "
            "resolved template values may no longer match the bundle's current facts. Run "
            "approve-projection again after reviewing the current text",
            where=digest,
        )

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
        pinned_entry_ids=tuple(_entry_id(entity_id) for entity_id in declaration.pinned_ids),
        candidate_entry_ids=tuple(
            _entry_id(entity_id) for entity_id in declaration.candidate_ids
        ),
        no_match_fallback_ids=tuple(
            _entry_id(entity_id) for entity_id in declaration.no_match_fallback
        ),
        bundle_revision=str(selection.revision),
        bundle_digest=selection.bundle_digest,
        projection_digest=digest,
    )


@dataclass(frozen=True)
class ProjectionCandidate:
    """What the owner is shown before approving: `declaration_path`'s digest, and every declared
    entry with its templates already resolved against the bundle's CURRENT revision.

    Mirrors `profile_bundle.authoring.ApprovalCandidate`'s split from filing — computed here,
    written by `stamp.write_stamp` only after the owner agrees on a controlling terminal.
    **Unlike `project_pool`, `projection_candidate` performs no owner-gate check.** It computes
    the very thing the gate is checked against, so requiring an existing stamp here would make
    the gate permanently unreachable — no command could ever produce the first one.

    `bundle_digest` is the bundle revision these entries were resolved against — carried so
    `approve_projection` can bind the stamp to it (`stamp.ProjectionStamp.bundle_digest`). Reading
    it here rather than deriving it separately at the call site keeps one fact computed once:
    `projection_candidate` already reads `selection` to build `ctx`, so this is a field, not a new
    computation.
    """

    projection_digest: str
    bundle_digest: str
    entries: tuple[Entry, ...]


def projection_candidate(
    bundle_root: Path, declaration_path: Path, *, as_of: date
) -> ProjectionCandidate:
    """Resolve `declaration_path`'s entries against the bundle's CURRENT revision, for the owner
    to review before approving.

    No `config_dir` parameter: unlike `project_pool`, this never resolves `shell_source` (it has
    no template to show) and never checks a stamp (`stamp_exists`/`write_stamp` are the only
    `config_dir`-keyed operations in this package), so there is nothing here that would use it.

    Shares every resolution step with `project_pool` — the same bundle revision, the same
    `check_references`, the same per-entry `resolve_template` call through `_build_entry` — so
    what the owner is shown is the identical rendering `project_pool` would later produce for this
    same digest, not a second, drifting rendering path. Deliberately does not resolve
    `shell_source` or `skill_groups`: neither carries a template placeholder
    (`SkillGroupDeclaration.label` is a plain string), so neither is part of the template hole
    this candidate exists to show.

    Raises the same typed `ProjectionError`s `project_pool` would for a malformed declaration or
    an unresolvable reference. Unlike `project_pool`, this function still lets a bundle-selection
    failure (`profile_bundle.storage.SelectionError`, e.g. no revision ever promoted) propagate
    unwrapped — it adds no new exception boundary of its own. `project_pool` now wraps that same
    failure as `BUNDLE_UNREADABLE`; whether this function should too is a separate decision, not
    made here.
    """
    declaration = load_declaration(declaration_path)
    digest = projection_digest(declaration)

    selection = read_current_once(bundle_root)
    documents = selected_documents(selection)
    ctx = context_from_documents(
        documents, root=selection.root, mode="revision", bundle_root=bundle_root
    )

    check_references(declaration, ctx)

    claims_by_id = {c.claim_id: c for c in ctx.index.claims}
    entries = tuple(
        _build_entry(
            entry_decl,
            ctx=ctx,
            claims_by_id=claims_by_id,
            open_range_label=declaration.open_range_label,
            as_of=as_of,
        )
        for entry_decl in declaration.entries
    )
    return ProjectionCandidate(
        projection_digest=digest, bundle_digest=selection.bundle_digest, entries=entries
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
        entry_id=_entry_id(entry_decl.entity_id),
        heading=render(entry_decl.heading, "heading"),
        bullets=bullets,
        kind=entry_decl.kind.value,
        title=render_optional(entry_decl.title, "title"),
        dates=render_optional(entry_decl.dates, "dates"),
        subtitle=render_optional(entry_decl.subtitle, "subtitle"),
        location=render_optional(entry_decl.location, "location"),
    )
