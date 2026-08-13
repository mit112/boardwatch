"""Stage 2's selection step (Task 23): given a JD-blind `ProjectionPool` and one posting's
`PostingContext`, decide which candidate entries reach the rendered résumé.

Pinned entries are emitted in declared order, never scored, never dropped. Candidates that
clear `ADMISSION_FLOOR` are ranked by the caller's chosen `scorer` — descending, ties broken by
total distinct matched skills (`scoring.total_distinct`, independent of which scorer is chosen)
then by declared order — and grown into the pinned set one at a time: compile, keep it if the
result still fits the page budget, stop at the first one that doesn't (dropping only that last
one). That is at most `len(candidates) + 1` compiles (the pinned-only base check, plus one per
candidate tried), never `2 * len(candidates)` — there is no separate "try without it" compile,
because the prefix before this candidate was already known to fit.

**This module picks no scorer.** All four registered candidates in `scoring.py` are falsified
by one rank-agreement probe or the other (`test_projection_scoring.py`), and the intersection of
survivors is empty by construction — there is no basis here for preferring one, so `select`
takes `scorer: EntryScorer` as a required parameter with no default.

The compile gate has four arms (`reports.resume_gate.evaluate_compile`) and only
`PAGE_LIMIT_EXCEEDED` ever drops a candidate. `BINARY_MISSING` and `COMPILE_FAILED` are fatal
infrastructure failures — `_pdf_page_count` (`reports/tailor.py`) launders three distinct `None`
causes into `COMPILE_FAILED`, so a missing `pdfinfo` must never read as "every candidate
overflowed the budget." If the pinned set alone fails to compile for a page-count reason, that
is `PINNED_SET_EXCEEDS_BUDGET`, naming the pinned set and the actionable knob
(`resume_max_pages`), not a candidate-selection outcome at all.

If no candidate clears the floor for this JD (`used_fallback=True`), the pinned set is grown
against the declaration's own `no_match_fallback_ids` instead, by the identical one-at-a-time
procedure — so a curated fallback still honours the budget and the same fatal-infrastructure
handling, rather than being trusted verbatim.

**This module never compiles anything itself.** `compile_prefix` is supplied by the caller,
closing over the real `LatexRenderer`, an output directory, and `context.page_budget` — nothing
here shells out to tectonic or pdfinfo, so a test can stub the four-arm gate directly instead of
needing a real toolchain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from boardwatch.extract.taxonomy import Taxonomy
from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.projection.pool import ProjectionPool
from boardwatch.projection.posting import PostingContext
from boardwatch.projection.scoring import EntryScorer, total_distinct
from boardwatch.reports.resume_gate import GateReason, GateResult
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Resume

#: What one compile attempt over a candidate résumé PREFIX produced, gated against the page
#: budget already in scope where the caller builds this closure. The caller's job, not this
#: module's: see the module docstring for why nothing here shells out itself.
Compiler = Callable[[Resume], GateResult]

#: Strict admission floor: a candidate scoring exactly `Decimal(0)` — no JD-skill overlap at
#: all — is never admitted, however roomy the budget. Verified against every registered scorer
#: in `scoring.py` (see the Task 23 report): each one's coverage primitive is
#: `effective_skills(...) & jd_skills`, an intersection that is empty, and therefore contributes
#: nothing to any of `total_distinct`/`mean_per_bullet`/`mean_top_k`/`coverage_then_density`,
#: exactly when an entry shares no skill with the JD. `0` itself does not clear the floor.
ADMISSION_FLOOR: Final = Decimal(0)


@dataclass(frozen=True)
class SelectionResult:
    """What Stage 2 decided for one posting: the résumé to render, and the bookkeeping behind
    it. `selected_candidate_ids` holds only the admitted, non-pinned entries, in the order they
    were admitted (ranked order, or fallback declared order) — not the résumé's own rendering
    order, which `resume.entries` preserves from the declaration instead."""

    resume: Resume
    pinned_entry_ids: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...]
    used_fallback: bool
    page_count: int | None


def _fatal_if_infrastructure(gate: GateResult, *, where: str) -> None:
    """`BINARY_MISSING`/`COMPILE_FAILED` are never overflow: raise before any candidate is
    dropped on their account."""
    if gate.reason in (GateReason.BINARY_MISSING, GateReason.COMPILE_FAILED):
        raise_violation(
            ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE,
            f"compile failed for a reason unrelated to page count ({gate.reason.value}); this "
            "is an infrastructure fault, never budget overflow, and no candidate is dropped "
            "on its account",
            where=where,
        )


def _subset_resume(pool: ProjectionPool, keep: frozenset[str]) -> Resume:
    """`pool.resume` filtered to `keep`, preserving the declaration's own entry order — the
    order `pool.resume.entries` already carries, not insertion order into `keep`."""
    kept = [entry for entry in pool.resume.entries if entry.entry_id in keep]
    return pool.resume.model_copy(update={"entries": kept})


def _ranked_candidates(
    pool: ProjectionPool,
    jd_skills: set[str],
    scorer: EntryScorer,
    table: EquivalenceTable,
    taxonomy: Taxonomy,
) -> list[str]:
    """Candidate entry ids clearing `ADMISSION_FLOOR`, ranked by `scorer` descending; ties
    broken by total distinct matched skills descending, then declared order ascending."""
    entries_by_id = {entry.entry_id: entry for entry in pool.resume.entries}
    ranked: list[tuple[Decimal, Decimal, int, str]] = []
    for position, entry_id in enumerate(pool.candidate_entry_ids):
        entry = entries_by_id[entry_id]
        score = scorer(entry, jd_skills, table, taxonomy)
        if score <= ADMISSION_FLOOR:
            continue
        distinct = total_distinct(entry, jd_skills, table, taxonomy)
        ranked.append((score, distinct, position, entry_id))
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [row[3] for row in ranked]


def _grow(
    pool: ProjectionPool,
    pinned: frozenset[str],
    order: list[str],
    compile_prefix: Compiler,
    *,
    base_gate: GateResult,
    where: str,
) -> tuple[list[str], GateResult]:
    """Add ids from `order` to the pinned set one at a time, compiling after each addition;
    stop and drop the last one at the first `PAGE_LIMIT_EXCEEDED`. At most `len(order)`
    compiles here, on top of the one that produced `base_gate`."""
    admitted: list[str] = []
    last_gate = base_gate
    for candidate_id in order:
        tentative = pinned | frozenset(admitted) | {candidate_id}
        gate = compile_prefix(_subset_resume(pool, tentative))
        _fatal_if_infrastructure(gate, where=where)
        if gate.reason is GateReason.PAGE_LIMIT_EXCEEDED:
            break
        admitted.append(candidate_id)
        last_gate = gate
    return admitted, last_gate


def select(
    pool: ProjectionPool,
    context: PostingContext,
    scorer: EntryScorer,
    *,
    table: EquivalenceTable,
    taxonomy: Taxonomy,
    compile_prefix: Compiler,
) -> SelectionResult:
    """Stage 2: which of `pool`'s candidate entries, beyond the always-kept pinned set, reach
    the résumé projected for `context`'s posting. See the module docstring for the full
    algorithm and its fail-safe direction."""
    where = f"posting:{context.posting_id}"
    pinned = frozenset(pool.pinned_entry_ids)

    pinned_gate = compile_prefix(_subset_resume(pool, pinned))
    _fatal_if_infrastructure(pinned_gate, where=where)
    if pinned_gate.reason is GateReason.PAGE_LIMIT_EXCEEDED:
        raise_violation(
            ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET,
            f"the pinned entries alone ({sorted(pinned)}) need {pinned_gate.page_count} "
            f"page(s), over the page budget of {context.page_budget}; raise the profile's "
            "resume_max_pages setting, or unpin an entry",
            where=where,
        )

    # `EntryScorer.__call__` is typed to `set[str]` (scoring.py); `frozenset` is not a subtype
    # of `set`, so `PostingContext.jd_skills` is converted once, here (mirrors agreement.py's
    # own note at its one call site).
    jd_skills = set(context.jd_skills)
    ranked = _ranked_candidates(pool, jd_skills, scorer, table, taxonomy)
    used_fallback = not ranked
    growth_order = ranked if ranked else list(pool.no_match_fallback_ids)

    admitted, last_gate = _grow(
        pool, pinned, growth_order, compile_prefix, base_gate=pinned_gate, where=where
    )

    return SelectionResult(
        resume=_subset_resume(pool, pinned | frozenset(admitted)),
        pinned_entry_ids=pool.pinned_entry_ids,
        selected_candidate_ids=tuple(admitted),
        used_fallback=used_fallback,
        page_count=last_gate.page_count,
    )
