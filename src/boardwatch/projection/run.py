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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import Engine

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy
from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.projection.persona_preflight import reject_entry_declaring_personas
from boardwatch.projection.pool import ProjectionPool, project_pool
from boardwatch.projection.scoring import SCORERS, EntryScorer
from boardwatch.tailor.equivalences import EquivalenceTable, load_equivalences
from boardwatch.tailor.persona import load_personas


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


__all__ = ["ProjectionRunContext", "resolve_projection_run"]
