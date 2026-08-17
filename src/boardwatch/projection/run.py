"""One configuration snapshot per run: every input that decides what a projected résumé says,
resolved once.

A projection is produced one posting at a time today, so each invocation loading its own taxonomy
was harmless. An unattended run produces many, and then it is not: the pool alone is not enough to
pin behaviour. `select` scores through the taxonomy AND the equivalence table, and persona
application reads the persona registry, so a run that freezes only the pool can still build lead 2
under rules lead 1 was not built under — a stale *transformation*, which no digest or hash over the
pool or the résumé bytes can detect.

`load_taxonomy` is imported by name here, exactly as `projection/posting.py` does. A test that
wants to count loads must patch `boardwatch.projection.run.load_taxonomy`; patching
`boardwatch.extract.taxonomy` leaves this already-bound name untouched (the same
resolution-at-call-time subtlety `tailor/plan.py:94` records for `effective_skills`).

Nothing here is caught. See `resolve_projection_run`.

This module also holds the two closed catalogs that classify those failures, and the one table
that maps every `ProjectionIssue` into exactly one of them. There are TWO catalogs because the
units differ: a `ProjectionAvailability` other than `AVAILABLE` is decided once and refuses the
whole run before any lead earns a ledger disposition, while a `ProjectionLeadOutcome` skips one
lead and the run continues. A single catalog cannot reconcile its own counts — "12 leads skipped"
and "the run never started" are not the same number of anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from sqlalchemy import Engine

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import Taxonomy, TaxonomyError, load_taxonomy
from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.projection.errors import ProjectionError, ProjectionIssue, raise_violation
from boardwatch.projection.persona_preflight import reject_entry_declaring_personas
from boardwatch.projection.pool import ProjectionPool, project_pool
from boardwatch.projection.scoring import SCORERS, EntryScorer
from boardwatch.tailor.equivalences import EquivalenceError, EquivalenceTable, load_equivalences
from boardwatch.tailor.persona import PersonaError, load_personas
from boardwatch.tailor.render.latex import TemplateArtifactError


@dataclass(frozen=True)
class ProjectionRunContext:
    """Every input that decides what a projected résumé says, resolved once per run.

    The pool alone is not enough. `select` scores through the taxonomy and equivalence table, and
    `apply_persona` reads the registry, so a run holding one pool and reloading the rest can still
    produce two leads built under different rules.

    `persona_registry_version` is carried instead of the registry itself: nothing downstream of
    this snapshot selects a persona by reading the registry object — the version is what a lineage
    record needs, and holding the object would invite a second, unfrozen read of it.
    """

    pool: ProjectionPool
    scorer: EntryScorer
    scorer_id: str
    taxonomy: Taxonomy
    table: EquivalenceTable
    persona_registry_version: str
    as_of: date


def resolve_projection_run(
    engine: Engine,
    settings: Settings,
    *,
    bundle_root: Path,
    declaration_path: Path,
    scorer_id: str,
    as_of: date,
) -> ProjectionRunContext:
    """Resolve one run's projection configuration, or raise.

    Raises `ProjectionError` / `ProfileBundleError` / `PersonaError` / `TaxonomyError` /
    `EquivalenceError`; a later task maps every one of those to an availability member. Nothing is
    caught here — a preflight that classifies its own failures cannot be reused by a caller that
    wants to classify them differently.

    `scorer_id` is validated first, before anything on disk is read: it is the only input that can
    be judged without touching the bundle, the config dir or the database, and an operator whose
    config names a scorer that does not exist should learn that rather than a bundle diagnosis.

    `engine` is accepted but unused: it is what makes this the run-level twin of
    `posting_context(engine, settings, ...)`, so a caller resolves both halves of a run from one
    `(engine, settings)` pair rather than discovering later that only one of them needed a database.
    """
    scorer = SCORERS.get(scorer_id)
    if scorer is None:
        raise_violation(
            ProjectionIssue.UNKNOWN_SCORER,
            f"no scorer {scorer_id!r}; known: {sorted(SCORERS)}",
            where="run",
        )
    reject_entry_declaring_personas(settings.config_dir)
    taxonomy = load_taxonomy(settings.config_dir)
    table = load_equivalences()
    personas = load_personas(settings.config_dir)
    pool = project_pool(bundle_root, declaration_path, config_dir=settings.config_dir, as_of=as_of)
    return ProjectionRunContext(
        pool=pool,
        scorer=scorer,
        scorer_id=scorer_id,
        taxonomy=taxonomy,
        table=table,
        persona_registry_version=personas.version,
        as_of=as_of,
    )


class ProjectionAvailability(StrEnum):
    """Decided ONCE per run. Anything but `AVAILABLE` refuses the whole run before any lead earns
    a ledger disposition, and sets `summary.fatal`.

    Closed. A cause this does not name is a defect here, never a new bucket.
    """

    AVAILABLE = "available"
    MISSING_APPROVAL = "missing_approval"
    STALE_APPROVAL = "stale_approval"
    DECLARATION_MISSING = "declaration_missing"
    DECLARATION_UNREADABLE = "declaration_unreadable"
    DECLARATION_INVALID = "declaration_invalid"
    #: The file `declaration.shell_source` points at (the résumé shell) is broken. Its own member,
    #: never folded into a DECLARATION_* one: those describe `projection.yaml`, this describes a
    #: DIFFERENT file with a different remedy, and an availability member whose whole job is to
    #: name what the operator can act on must not send them to edit the wrong file.
    #: `INVALID` rather than `UNREADABLE` deliberately: the raise site (`load_shell` in
    #: `projection/shell.py`) catches `OSError`, `UnicodeDecodeError`, `yaml.YAMLError`,
    #: `ValidationError` and `ResumeLoadError` in one arm, so the member spans both "cannot be
    #: read" and "read, but not a valid header/education shell".
    SHELL_SOURCE_INVALID = "shell_source_invalid"
    BUNDLE_UNREADABLE = "bundle_unreadable"
    PERSONA_INVALID = "persona_invalid"
    SCORER_INVALID = "scorer_invalid"
    TAXONOMY_INVALID = "taxonomy_invalid"
    EQUIVALENCES_INVALID = "equivalences_invalid"
    TEMPLATE_INVALID = "template_invalid"
    TOOLCHAIN_UNAVAILABLE = "toolchain_unavailable"
    PINNED_BUDGET_OVERFLOW = "pinned_budget_overflow"


class ProjectionLeadOutcome(StrEnum):
    """Per attempted lead, reachable only once availability is `AVAILABLE`. Skipping one lead
    leaves the run running, so nothing here may name a run-invariant cause: the page budget is one
    global profile column and the pinned set is fixed by the frozen declaration, so a lead can
    never be the unit at which either is decided.

    Closed. A cause this does not name is a defect here, never a new bucket.
    """

    PROJECTED = "projected"
    POSTING_UNAVAILABLE = "posting_unavailable"
    EXTRACTION_UNAVAILABLE = "extraction_unavailable"
    LINEAGE_MISMATCH = "lineage_mismatch"
    OUTPUT_IO_FAILURE = "output_io_failure"


#: One row per `ProjectionIssue` member, in the order `errors.py` declares them. The table is the
#: deliverable: totality asserted without a readable table is unreviewable, and a member's scope
#: is a judgement that has to be written down where the next reader can disagree with it.
ISSUE_SCOPE: Mapping[ProjectionIssue, ProjectionAvailability | ProjectionLeadOutcome] = {
    # -- declaration: read once per run out of `config_dir`, so every arm is run-scoped ---
    ProjectionIssue.DECLARATION_UNREADABLE: ProjectionAvailability.DECLARATION_UNREADABLE,
    ProjectionIssue.DECLARATION_MISSING: ProjectionAvailability.DECLARATION_MISSING,
    ProjectionIssue.MALFORMED_DECLARATION: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.UNKNOWN_ENTRY_KIND: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.DUPLICATE_ENTITY_ID: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.DUPLICATE_BULLET_PREDICATE: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.UNRESOLVED_PLACEHOLDER: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.MALFORMED_PLACEHOLDER: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.MISSING_OPEN_RANGE_LABEL: ProjectionAvailability.DECLARATION_INVALID,
    # -- fallback: `no_match_fallback_ids` is declaration content, validated with it ------
    ProjectionIssue.FALLBACK_ID_NOT_A_CANDIDATE: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.FALLBACK_ID_DUPLICATED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.FALLBACK_OVERLAPS_PINNED: ProjectionAvailability.DECLARATION_INVALID,
    # -- bundle -------------------------------------------------------------------------
    ProjectionIssue.BUNDLE_UNREADABLE: ProjectionAvailability.BUNDLE_UNREADABLE,
    # -- bundle references: the fidelity contract. Every arm is the declaration asking the
    # bundle for something the bundle will not give it, resolved once when the pool is
    # projected — identical for every posting, so DECLARATION_INVALID and not a lead skip.
    ProjectionIssue.UNKNOWN_BUNDLE_ID: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.FACT_NOT_RESUME_SURFACED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.FACT_NOT_EFFECTIVE: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.FACT_EXPIRED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.FACT_VALUE_KIND_NOT_ADMITTED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.CLAIM_NOT_APPROVED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.CLAIM_NOT_RESUME_SURFACED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.CLAIM_SUBJECT_MISMATCH: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.SKILL_NOT_RESUME_SURFACED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.BULLET_TEXT_ALTERED: ProjectionAvailability.DECLARATION_INVALID,
    ProjectionIssue.BULLET_PREDICATE_NO_FACTS: ProjectionAvailability.DECLARATION_INVALID,
    # -- shell: the file `declaration.shell_source` names — a DIFFERENT file from the
    # declaration, with a different remedy, so it gets its own member rather than a
    # DECLARATION_* one. `load_shell` (`shell.py:55-71`) catches OSError, UnicodeDecodeError,
    # yaml.YAMLError, ValidationError and ResumeLoadError in one arm, which is why the member is
    # named INVALID: it spans "cannot be read" and "read, but not a valid shell".
    ProjectionIssue.SHELL_SOURCE_UNREADABLE: ProjectionAvailability.SHELL_SOURCE_INVALID,
    # -- persona: the registry is loaded once per run ------------------------------------
    ProjectionIssue.PERSONA_DECLARES_ENTRIES: ProjectionAvailability.PERSONA_INVALID,
    # -- owner gate: one stamp per (declaration, bundle) pair, not per posting -----------
    ProjectionIssue.MISSING_PROJECTION_APPROVAL: ProjectionAvailability.MISSING_APPROVAL,
    ProjectionIssue.STALE_PROJECTION_APPROVAL: ProjectionAvailability.STALE_APPROVAL,
    # -- selection: raised from `select()` DURING a lead, and still run-scoped -----------
    #: The pinned set comes from the frozen declaration and the budget from one global profile
    #: column, so if the pinned entries alone overflow for one posting they overflow for all.
    #: Per-lead, this would skip every lead in turn and report N content failures for one
    #: setting; run-scoped, it names `resume_max_pages` once.
    ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET: ProjectionAvailability.PINNED_BUDGET_OVERFLOW,
    #: A missing `tectonic`/`pdfinfo` or an unclassified gate reason is a property of the
    #: machine, identical for every posting. Per-lead, it would re-shell out to an absent
    #: binary once per lead and bill each failure to the owner's content.
    ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE: ProjectionAvailability.TOOLCHAIN_UNAVAILABLE,
    #: PER-LEAD, deliberately. `posting_context` raises this when the taxonomy extraction backing
    #: `jd_skills_for` is missing for THIS posting at the run's taxonomy version. One way to
    #: reach it is a mid-run edit to `taxonomy.yaml`: `run_preflight` still loads its own
    #: taxonomy on every `posting_context` call, so a later lead can backfill against a version
    #: the run is not holding. That is acceptable precisely BECAUSE this row is per-lead — the
    #: lead is skipped and counted, and no résumé is ever rendered under two taxonomies. It is
    #: not run-scoped: an extraction row is posting-specific, so refusing the whole run for one
    #: posting's missing row would drop every other lead for an unrelated reason.
    ProjectionIssue.NO_JD_EXTRACTION: ProjectionLeadOutcome.EXTRACTION_UNAVAILABLE,
    # -- posting: per-lead by construction; another posting is unaffected ----------------
    ProjectionIssue.POSTING_NOT_OPEN: ProjectionLeadOutcome.POSTING_UNAVAILABLE,
    ProjectionIssue.POSTING_NO_CURRENT_VERSION: ProjectionLeadOutcome.POSTING_UNAVAILABLE,
    # -- run configuration ---------------------------------------------------------------
    ProjectionIssue.UNKNOWN_SCORER: ProjectionAvailability.SCORER_INVALID,
}

#: The run-scoped causes that arrive as a FOREIGN exception rather than a `ProjectionIssue`,
#: matched by type in order (each entry is checked with `isinstance`, so a subclass of
#: `ProfileBundleError` resolves to the same arm as its base). Ordered most specific first.
FOREIGN_AVAILABILITY: tuple[tuple[type[Exception], ProjectionAvailability], ...] = (
    # Run-invariant: one template per run, resolved from `config_dir` or the bundled default.
    (TemplateArtifactError, ProjectionAvailability.TEMPLATE_INVALID),
    # Run-invariant: `load_taxonomy` / `load_equivalences` are called once by
    # `resolve_projection_run`, and both raise `ValueError` subclasses that are disjoint.
    (TaxonomyError, ProjectionAvailability.TAXONOMY_INVALID),
    (EquivalenceError, ProjectionAvailability.EQUIVALENCES_INVALID),
    (PersonaError, ProjectionAvailability.PERSONA_INVALID),
    # `project_pool` calls `read_stamp`, which raises `ProfileBundleError` (not
    # `ProjectionError`) for a stamp this build cannot parse — so this family really does
    # escape `resolve_projection_run` and must map.
    (ProfileBundleError, ProjectionAvailability.BUNDLE_UNREADABLE),
)


def classify_availability(exc: Exception) -> ProjectionAvailability:
    """The run-scoped catalog member `exc` means, or an `AssertionError`.

    Never returns a default: an unmapped exception at a run gate would otherwise become a silent
    new bucket, and the whole point of a closed catalog is that it cannot grow by accident.
    A `ProjectionError` carrying a PER-LEAD issue is equally a defect here — it means a lead
    failure reached a run gate — so it asserts rather than being promoted to fatal.
    """
    if isinstance(exc, ProjectionError):
        issue = exc.violation.issue
        assert issue in ISSUE_SCOPE, f"unmapped ProjectionIssue {issue!r}"
        scope = ISSUE_SCOPE[issue]
        assert isinstance(scope, ProjectionAvailability), (
            f"{issue!r} is a per-lead outcome ({scope!r}), not a run-scoped availability"
        )
        return scope
    for family, availability in FOREIGN_AVAILABILITY:
        if isinstance(exc, family):
            return availability
    raise AssertionError(f"unclassified projection failure {type(exc).__name__}: {exc}")


def classify_lead_outcome(exc: Exception) -> ProjectionLeadOutcome:
    """The per-lead catalog member `exc` means, or an `AssertionError`.

    Asserts on a run-scoped cause: those surface inside the per-lead loop too (`select()` raises
    `PINNED_SET_EXCEEDS_BUDGET` and `COMPILE_INFRASTRUCTURE_FAILURE` while building one lead), and
    a caller that fed one here would grant the remaining leads a disposition under a run-wide
    fault. The caller reads `ISSUE_SCOPE` / `FOREIGN_AVAILABILITY` to route by scope first.
    """
    assert isinstance(exc, ProjectionError), (
        f"unclassified lead failure {type(exc).__name__}: {exc}"
    )
    issue = exc.violation.issue
    assert issue in ISSUE_SCOPE, f"unmapped ProjectionIssue {issue!r}"
    scope = ISSUE_SCOPE[issue]
    assert isinstance(scope, ProjectionLeadOutcome), (
        f"{issue!r} is a run-scoped availability ({scope!r}), not a per-lead outcome"
    )
    return scope


__all__ = [
    "FOREIGN_AVAILABILITY",
    "ISSUE_SCOPE",
    "ProjectionAvailability",
    "ProjectionLeadOutcome",
    "ProjectionRunContext",
    "classify_availability",
    "classify_lead_outcome",
    "resolve_projection_run",
]
