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

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from boardwatch.profile_bundle.models.base import Surface
from boardwatch.profile_bundle.models.claims import ClaimRecord
from boardwatch.profile_bundle.models.facts import FactRecord, YearMonthValue
from boardwatch.profile_bundle.models.policy import SkillCategoryCatalog
from boardwatch.profile_bundle.models.skills import SkillRecord
from boardwatch.profile_bundle.storage import (
    SelectionError,
    read_current_once,
    selected_documents,
)
from boardwatch.profile_bundle.validation.context import ValidationContext, context_from_documents
from boardwatch.projection.contract import check_references
from boardwatch.projection.declaration import (
    DateRangeDeclaration,
    EntryDeclaration,
    EntryKind,
    ProjectionDeclaration,
    load_declaration,
    projection_digest,
)
from boardwatch.projection.effectiveness import resume_bullet_facts_for, resume_facts_for
from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.projection.grammar import (
    render_declared_range,
    render_skill,
    render_value,
    resolve_template,
)
from boardwatch.projection.shell import load_shell
from boardwatch.projection.stamp import read_stamp, stamp_exists
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


def _entry_id(entity_id: str) -> str:
    """The one derivation rule the brief states once: `entry_id = "entry." + entity_id`.
    Extracted so the four sites that need it cannot drift from one another."""
    return "entry." + entity_id


def _synthesized_skill_groups(
    skills: tuple[SkillRecord, ...], categories: SkillCategoryCatalog | None
) -> list[SkillGroup]:
    """Derive `skill_groups` from the bundle when the declaration omits them (D-187).

    One group per category that has a résumé-surfaced skill, labelled by the category
    `display_name`, emitted in the catalog's own order; within a group, skills keep inventory
    order. Only résumé-surfaced skills appear (mirroring the explicit path's `check_references`
    contract), and a category with none is omitted so no empty section reaches the page.

    `categories is None` cannot occur for a promoted bundle — `policy/skill-categories.yaml` is a
    required document (`validation/structural.py`) — so the empty return only narrows the optional
    type, exactly as semantic validation's own category check guards `if categories is not None`.
    """
    if categories is None:
        return []
    by_category: dict[str, list[SkillRecord]] = {}
    for skill in skills:
        if Surface.RESUME in skill.allowed_surfaces:
            by_category.setdefault(skill.category, []).append(skill)
    return [
        SkillGroup(label=spec.display_name, items=[render_skill(s) for s in members])
        for spec in categories.categories
        if (members := by_category.get(spec.category_id))
    ]


def _resolved_skill_groups(
    declaration: ProjectionDeclaration, ctx: ValidationContext
) -> list[SkillGroup]:
    """The rendered skills section, from ONE place so the pool and the approval candidate
    cannot resolve it two ways.

    An explicit `skill_groups` block is the owner taking full control of grouping, order and
    inclusion; omitting it defers to the bundle's own category taxonomy so the grouping lives in
    exactly ONE versioned place — `policy/skill-categories.yaml`, bound by the bundle digest —
    rather than being restated, unversioned and drift-prone, in `projection.yaml` (D-187).
    """
    skills_by_id = {s.skill_id: s for s in ctx.index.skills}
    if declaration.skill_groups:
        return [
            SkillGroup(
                label=group.label,
                items=[render_skill(skills_by_id[skill_id]) for skill_id in group.skills],
            )
            for group in declaration.skill_groups
        ]
    return _synthesized_skill_groups(ctx.index.skills, ctx.index.skill_categories)


@dataclass(frozen=True)
class ProjectionPool:
    """The contract between Stage 1 and Stage 2.

    `resume.entries` holds every declared entry; `pinned_entry_ids` / `candidate_entry_ids` /
    `no_match_fallback_ids` locate the declaration's own split within it, by `Entry.entry_id`.
    `fill_to_page` carries the declaration's opt-in "fill the page" flag into Stage 2, exactly as
    `no_match_fallback_ids` carries the declaration's fallback list — both are Stage-2 selection
    inputs the declaration owns, not rendering content.
    """

    resume: Resume
    pinned_entry_ids: tuple[str, ...]
    candidate_entry_ids: tuple[str, ...]
    no_match_fallback_ids: tuple[str, ...]
    bundle_revision: str
    bundle_digest: str
    projection_digest: str
    fill_to_page: bool = False
    #: The declaration's opt-in reverse-chronological PROJECT ordering, carried into Stage 2 like
    #: `fill_to_page` — a selection input the declaration owns, not rendering content. `select`
    #: reorders the final project set by `project_order` when this is set. Default OFF.
    sort_projects_by_date: bool = False
    #: Project entry ids in reverse-chronological order (newest structured start first) — the sort
    #: key `select` applies when `sort_projects_by_date` is on. Computed HERE, where the structured
    #: start FACTS are in scope, so `select` never re-reads the bundle. Empty for a pool with no
    #: project entries.
    project_order: tuple[str, ...] = ()


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

    ctx = context_from_documents(
        documents, root=selection.root, mode="revision", bundle_root=bundle_root
    )

    check_references(declaration, ctx)

    header, education = load_shell(shell_path)

    claims_by_id = {c.claim_id: c for c in ctx.index.claims}
    skill_groups = _resolved_skill_groups(declaration, ctx)

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

    # HERE, not above with `stamp_exists`, because the thing being compared does not exist until
    # the entries are resolved. The gate is on the RESOLVED TEXT the owner reviewed, not on the
    # bundle revision they happened to review it against (D-167's original instrument): a bundle
    # edit the projection does not render must not stale an approval, and any edit that changes
    # one rendered character must. `bundle_digest` is still recorded on the stamp as provenance —
    # which revision the owner was looking at — it just no longer decides.
    #
    # A stamp written before this field existed carries `None` and is treated as stale: fail
    # closed. The owner re-approves once, and every subsequent approval is scoped correctly.
    if stamp.content_digest != projection_content_digest(entries, skill_groups, header, education):
        raise_violation(
            ProjectionIssue.STALE_PROJECTION_APPROVAL,
            "the résumé text this declaration resolves to is not the text the owner approved"
            + (
                " (the approval predates content-scoped stamps)"
                if stamp.content_digest is None
                else ""
            )
            + ". Run approve-projection again after reviewing the current text",
            where=digest,
        )

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
        candidate_entry_ids=tuple(_entry_id(entity_id) for entity_id in declaration.candidate_ids),
        no_match_fallback_ids=tuple(
            _entry_id(entity_id) for entity_id in declaration.no_match_fallback
        ),
        bundle_revision=str(selection.revision),
        bundle_digest=selection.bundle_digest,
        projection_digest=digest,
        fill_to_page=declaration.fill_to_page,
        sort_projects_by_date=declaration.sort_projects_by_date,
        project_order=_project_order(declaration, ctx=ctx, as_of=as_of),
    )


def projection_content_digest(
    entries: Sequence[Entry],
    skill_groups: Sequence[SkillGroup],
    header: Sequence[str],
    education: Sequence[str],
) -> str:
    """`sha256:<hex>` over the RESOLVED entries — the text the approval screen prints.

    This is what the owner actually reviewed, and it is deliberately NOT the bundle's revision
    digest. `bundle_digest` staled an approval whenever ANY document in the bundle moved: adding
    a skill, correcting a date on an entity the projection never cites, promoting a revision for
    an unrelated reason. Every one of those forced a re-approval of text that had not changed by
    one character, and an approval screen that re-appears for no visible reason is how
    rubber-stamping is trained — which then costs the gate the one thing it exists for.

    Digested from `Entry.model_dump(mode="json")`, so it covers every field the screen prints —
    heading, title, subtitle, dates, location, the link pair — AND every bullet's text. The
    resolved SKILLS section is in it too: it is rendered onto the résumé, so leaving it out
    would be a hole exactly where `bundle_digest` used to hold, and the approval screen prints
    it for the same reason. An edit to an entity the projection does not cite, or to a cited
    entity's field the projection does not render, changes nothing here. Any edit that changes
    one rendered character changes it.

    The résumé SHELL (`master_resume.yaml`'s header and education) is in it too, and closing
    that was T32. The shell lives OUTSIDE the bundle, so `bundle_digest` never bound it, and
    `projection_digest` hashes the parsed declaration, which carries `shell_source` as a
    filename rather than as bytes — so the owner's own name, email and university were the one
    part of the projected document that could be rewritten between approval and render with no
    digest moving. They are rendered onto the résumé (`ProjectionPool.resume.header`/
    `.education`, and `resume_document_bytes` serializes them), so they belong here for exactly
    the reason the skills section does, and the approval screen prints them for the same reason.

    `sort_keys` is pydantic's declaration order via `model_dump`, which is stable for a frozen
    model; the list order is the declaration's own entry order, which is itself part of what was
    reviewed, so it is not sorted away.
    """
    payload = {
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "skill_groups": [group.model_dump(mode="json") for group in skill_groups],
        "header": list(header),
        "education": list(education),
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
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
    #: The resolved skills section — rendered onto the résumé, so shown and digested with the
    #: entries rather than left outside the gate.
    skill_groups: tuple[SkillGroup, ...]
    #: The résumé shell read from `{config_dir}/<shell_source>` (T32) — same argument as
    #: `skill_groups`: it is rendered onto the document, so it is shown and digested.
    header: tuple[str, ...]
    education: tuple[str, ...]
    #: The digest of the resolved text above — what `project_pool` compares the stamp against.
    #: Carried on the candidate so the approving command binds the stamp to the very bytes it
    #: printed, rather than recomputing them from a second traversal that could drift.
    content_digest: str


def projection_candidate(
    bundle_root: Path, declaration_path: Path, *, config_dir: Path, as_of: date
) -> ProjectionCandidate:
    """Resolve `declaration_path`'s entries against the bundle's CURRENT revision, for the owner
    to review before approving.

    `config_dir` is here for `shell_source` alone (T32) — it still checks no stamp, so it stays
    reachable before the first approval exists; `stamp_exists`/`write_stamp` remain the only
    other `config_dir`-keyed operations in this package and neither is called here.

    Shares every resolution step with `project_pool` — the same bundle revision, the same
    `check_references`, the same per-entry `resolve_template` call through `_build_entry`, and
    now the same `load_shell` — so what the owner is shown is the identical rendering
    `project_pool` would later produce for this same digest, not a second, drifting rendering
    path. Neither the shell nor `skill_groups` carries a template placeholder
    (`SkillGroupDeclaration.label` is a plain string), so neither is part of the template hole
    this candidate was first written to show; both are resolved anyway because both are RENDERED
    onto the résumé and the content digest has to cover every literal the owner is asked to
    approve.

    Raises the same typed `ProjectionError`s `project_pool` would for a malformed declaration or
    an unresolvable reference. Unlike `project_pool`, this function still lets a bundle-selection
    failure (`profile_bundle.storage.SelectionError`, e.g. no revision ever promoted) propagate
    unwrapped — it adds no new exception boundary of its own. `project_pool` now wraps that same
    failure as `BUNDLE_UNREADABLE`; whether this function should too is a separate decision, not
    made here.
    """
    declaration = load_declaration(declaration_path)
    digest = projection_digest(declaration)
    header, education = load_shell(config_dir / declaration.shell_source)

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
    skill_groups = tuple(_resolved_skill_groups(declaration, ctx))
    return ProjectionCandidate(
        projection_digest=digest,
        bundle_digest=selection.bundle_digest,
        entries=entries,
        skill_groups=skill_groups,
        header=header,
        education=education,
        content_digest=projection_content_digest(entries, skill_groups, header, education),
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

    def render_link_url(template: str | None) -> str | None:
        """The link target, refused HERE when LaTeX cannot carry it.

        Checked on the RESOLVED value rather than the declared template, because `link_url` is
        templated: a bad character can arrive from a bundle fact that no load-time check on the
        template text would ever see.

        The set is exactly the three characters measured to be uncarryable, not the LaTeX-special
        class: `&`, `#` and `%` are ordinary in a real GitHub or portfolio URL and the emitter
        escapes them (`tailor/render/latex._escape_url`), so refusing those would refuse working
        links. `{`, `}` and `\\` break the tectonic compile raw AND escaped — escaping `{`
        renders the backslash into the target rather than failing — so nothing downstream can
        rescue them. Left to the renderer they cost the whole RUN, per lead, with guidance
        pointing at bullets; refused here they cost one entry and name the field.
        """
        rendered = render_optional(template, "link_url")
        if rendered is None:
            return None
        offending = sorted({ch for ch in rendered if ch in "{}\\"})
        if offending:
            raise_violation(
                ProjectionIssue.MALFORMED_DECLARATION,
                f"link_url resolves to {rendered!r}, which carries "
                f"{', '.join(repr(ch) for ch in offending)} — LaTeX cannot carry those in a "
                "link target, escaped or not, so the résumé would fail to compile",
                where=f"entries: {entry_decl.entity_id}.link_url",
            )
        return rendered

    def range_fact(predicate: str) -> FactRecord:
        # Mirrors `resolve_template`'s unresolved-placeholder refusal, and for the same reason: a
        # declared range half that resolves to nothing must not quietly become an open range.
        fact = facts_by_predicate.get(predicate)
        if fact is None:
            raise_violation(
                ProjectionIssue.UNRESOLVED_PLACEHOLDER,
                f"no résumé-surfaced, effective fact with predicate {predicate!r} on this "
                "entity, so the declared date range has no end to render",
                where=f"entries: {entry_decl.entity_id}.dates",
            )
        return fact

    def render_dates(declared: str | DateRangeDeclaration | None) -> str | None:
        if declared is None or isinstance(declared, str):
            return render_optional(declared, "dates")
        return render_declared_range(
            range_fact(declared.start),
            None if declared.end is None else range_fact(declared.end),
            open_range_label=open_range_label,
            where=f"entries: {entry_decl.entity_id}.dates",
        )

    bullets = [
        # `text=` is `claim.text` verbatim — never templated, edited or reflowed. Only
        # `Bullet._single_line`'s own whitespace-run normalisation touches it, identically to
        # every other bullet in the tailoring pipeline.
        Bullet(bullet_id=claim_id, text=claims_by_id[claim_id].text, tech_tags=[])
        for claim_id in entry_decl.claims
    ]

    # Fact-derived bullets (D-188): each declared predicate's résumé-surfaced facts, in predicate-
    # declaration order then index order. `render_value` refuses a non-line kind (a `skill_ref` or
    # list), and a predicate resolving to nothing is a loud refusal rather than a dropped bullet.
    for predicate in entry_decl.bullet_predicates:
        facts = resume_bullet_facts_for(entry_decl.entity_id, predicate, ctx, as_of=as_of)
        if not facts:
            raise_violation(
                ProjectionIssue.BULLET_PREDICATE_NO_FACTS,
                f"no résumé-surfaced {predicate!r} fact on this entity, so the declared bullet "
                "source resolves to nothing",
                where=f"entries: {entry_decl.entity_id}.bullet_predicates: {predicate}",
            )
        bullets.extend(
            Bullet(
                bullet_id=fact.fact_id,
                text=render_value(
                    fact.value,
                    open_range_label=open_range_label,
                    where=f"entries: {entry_decl.entity_id}.{predicate}",
                ),
                tech_tags=[],
            )
            for fact in facts
        )

    return Entry(
        entry_id=_entry_id(entry_decl.entity_id),
        heading=render(entry_decl.heading, "heading"),
        bullets=bullets,
        kind=entry_decl.kind.value,
        title=render_optional(entry_decl.title, "title"),
        dates=render_dates(entry_decl.dates),
        subtitle=render_optional(entry_decl.subtitle, "subtitle"),
        location=render_optional(entry_decl.location, "location"),
        link_url=render_link_url(entry_decl.link_url),
        link_label=render_optional(entry_decl.link_label, "link_label"),
        # `None` rather than `False` when undeclared: the projected document drops None-valued
        # optionals, so this field's existence changes the bytes of no entry that does not use it.
        bulletless=entry_decl.bulletless or None,
        # Same `None`-when-undeclared rule as `bulletless`, for the same serialization reason.
        link_in_first_bullet=entry_decl.link_in_first_bullet or None,
    )


def _project_start_key(
    entry_decl: EntryDeclaration, *, ctx: ValidationContext, as_of: date
) -> str | None:
    """A project entry's STRUCTURED start as a sortable `YYYY-MM` string, or `None` when it has no
    structured start — a literal-string or absent `dates`, or a start fact that is not a
    `year_month`. Reads the same résumé-surfaced facts `_build_entry` renders from (its `range_fact`
    reads this same `resume_facts_for` map), so a project sorts on the very start it prints. `None`
    sorts as most recent (see `_project_order`)."""
    dates = entry_decl.dates
    if not isinstance(dates, DateRangeDeclaration):
        return None
    fact = resume_facts_for(entry_decl.entity_id, ctx, as_of=as_of).get(dates.start)
    if fact is None or not isinstance(fact.value, YearMonthValue):
        return None
    return fact.value.value


def _order_projects_by_start(pairs: list[tuple[str, str | None]]) -> tuple[str, ...]:
    """Given `(entry_id, start_key)` pairs in declaration order, return the entry ids newest-first:
    projects with no structured start (`None`) come first, as most recent; the dated ones then
    follow, DESCENDING by `YYYY-MM` (which sorts chronologically as a plain string). Stable within
    each group, so declaration order breaks ties. Pure — the fact-reading lives in
    `_project_start_key` — so the ordering rule is testable without a bundle."""
    undated = [entry_id for entry_id, key in pairs if key is None]
    dated = [(entry_id, key) for entry_id, key in pairs if key is not None]
    dated.sort(key=lambda row: row[1], reverse=True)
    return tuple(undated) + tuple(entry_id for entry_id, _ in dated)


def _project_order(
    declaration: ProjectionDeclaration, *, ctx: ValidationContext, as_of: date
) -> tuple[str, ...]:
    """Project entry ids newest-start-first — the order `select` applies when the declaration opts
    into `sort_projects_by_date`. Experience entries are excluded — the ordering is projects-only by
    design. Computed unconditionally so the field is a faithful record whether or not the flag is
    on; `select` consults it only when it is."""
    pairs = [
        (_entry_id(entry_decl.entity_id), _project_start_key(entry_decl, ctx=ctx, as_of=as_of))
        for entry_decl in declaration.entries
        if entry_decl.kind is EntryKind.PROJECT
    ]
    return _order_projects_by_start(pairs)
