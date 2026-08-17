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
`PAGE_LIMIT_EXCEEDED` ever drops a candidate. `BINARY_MISSING` and `COMPILE_FAILED` are both fatal
and neither may ever read as "every candidate overflowed the budget" — but they are not one fault,
and `_fatal_if_infrastructure` raises a different issue for each of its three arms. A missing
`tectonic` *or* `pdfinfo` is `BINARY_MISSING` (D-204), typed at its source, the machine's problem.
`COMPILE_FAILED` is ambiguous by construction — it folds a non-zero exit, a missing PDF and an
unreadable page count into one value, and `reports/resume_gate.py` reasons that such an exit is
typically environmental — so this module does not classify it by cause at all. It classifies by
whether the failure is ATTRIBUTABLE: mid-growth, the same document minus this candidate compiled
seconds earlier, so the entry is implicated and the scope is one lead; on the pinned-only base,
nothing smaller has compiled and the pinned set is frozen anyway, so it is unattributable and
run-scoped. See `_fatal_if_infrastructure` for how that degrades in both directions.
If the pinned set alone fails to compile for a page-count reason, that
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


def _fatal_if_infrastructure(gate: GateResult, *, where: str, candidate: str | None) -> None:
    """Raise on either non-overflow compile failure — three arms, scoped by ATTRIBUTION rather than
    by cause. Always before any candidate is dropped on its account: neither reason is overflow, so
    neither may ever read as "this candidate did not fit."

    `candidate` is the entry id this compile added, or `None` for the pinned-only base compile. It
    is required, not defaulted, because it is the whole discriminator and a silent default would
    give one of the two call sites the other's scope.

    **This function asserts no cause, deliberately.** `CompileReason.COMPILE_FAILED` folds three
    distinct events into one value — a non-zero `tectonic` exit, a PDF that was never produced, and
    a page count that could not be read (`tailor/render/outcome.py`'s `_default_runner`) — and
    `reports/resume_gate.py:87-90` reasons, in an existing closed catalog, that a non-zero exit is
    typically ENVIRONMENTAL: "cold support-file cache with no network, disk full, OOM, killed
    subprocess", which is why `DETERMINISTIC_GATE_REFUSALS` deliberately excludes it rather than
    burying a lead "on the strength of a bad afternoon". Nothing typed anywhere distinguishes
    content from environment here, so this module does not guess. What IS observable is whether the
    failure can be pinned on one entry:

    - `BINARY_MISSING`, either site — the one arm that IS typed at its source: `evaluate_compile`
      separates it from `COMPILE_FAILED`, so `tectonic`/`pdfinfo` really is absent (D-204). A
      property of the machine, identical for every posting. Run-scoped.
    - `COMPILE_FAILED` with a `candidate` — the same document MINUS this entry compiled `OK`
      moments earlier (`_grow` only reaches here after a strictly smaller prefix passed
      `_reject_unless_ok`), so the failure is attributable to this one entry. Per-lead, so one bad
      `%` in a candidate bullet skips only the leads whose JD admits it.
    - `COMPILE_FAILED` with no `candidate` — the pinned-only base. Nothing has compiled yet, so
      nothing is attributable; the environment and the pinned content are equally implicated. And
      either way the pinned set is fixed by the frozen declaration, so the cause is run-invariant
      by the same argument `PINNED_SET_EXCEEDS_BUDGET` uses. Run-scoped and fatal, which is the
      right direction for both a systemic outage and a pinned-content authoring bug.

    How this degrades, in both directions — no silent empty day either way. If the environment
    really did die mid-run, the per-lead arm misattributes at most ONE lead to a candidate: the
    very next lead begins with its own pinned-only compile, which fails unattributably and takes
    the run-scoped arm, so the run goes fatal. If instead the failure was genuinely that one
    candidate, the next lead's pinned compile succeeds and only the leads admitting that entry are
    skipped. A transient blip costs one lead; a real outage stops the run.
    """
    if gate.reason is GateReason.BINARY_MISSING:
        raise_violation(
            ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE,
            f"a render-toolchain binary is missing ({gate.reason.value}"
            # `GateResult.tool` names WHICH binary, and is None for every other reason. A
            # `RenderTool` is a `Literal[str]`, not an enum — no `.value` to read.
            + (f": {gate.tool}" if gate.tool is not None else "")
            + "); this is an environment fault, never budget overflow, and no candidate is "
            "dropped on its account",
            where=where,
        )
    if gate.reason is GateReason.COMPILE_FAILED and candidate is not None:
        raise_violation(
            ProjectionIssue.CANDIDATE_COMPILE_FAILED,
            f"adding candidate entry {candidate!r} made the compile fail "
            f"({gate.reason.value}) when the same document without it compiled; the failure is "
            "attributable to that entry — check its bullets for an unescaped LaTeX special, and "
            "the compile log for an environment fault that began between the two compiles. Never "
            "budget overflow, and no candidate is dropped on its account",
            where=where,
        )
    if gate.reason is GateReason.COMPILE_FAILED:
        raise_violation(
            ProjectionIssue.PINNED_SET_COMPILE_FAILED,
            f"the pinned entries alone would not compile ({gate.reason.value}); no smaller prefix "
            "has compiled, so this is not attributable to any one entry — read the compile log "
            "first, then the pinned entries' own bullets. Run-scoped because the pinned set comes "
            "from the frozen declaration either way. Never budget overflow, and no candidate is "
            "dropped on its account",
            where=where,
        )


def _reject_unless_ok(gate: GateResult, *, where: str) -> None:
    """Admit by assertion, never by elimination. By the time a caller reaches this check,
    `_fatal_if_infrastructure` has already ruled out `BINARY_MISSING`/`COMPILE_FAILED` and the
    caller's own `PAGE_LIMIT_EXCEEDED` check has run — but `Compiler = Callable[[Resume],
    GateResult]` accepts any `GateResult`, and `GateReason` has ten members, not four:
    `evaluate_compile` produces the four this module names, but the same type is also returned
    by `validate_layout`/`validate_slots` (`BULLET_TOO_LONG`, `TOO_MANY_BULLETS`,
    `ESCAPING_MISMATCH`, `TEMPLATE_ARTIFACT`, `CONTACT_BLOCK_MISSING_NAME`,
    `CONTACT_BLOCK_INVALID_EMAIL`). A compiler wired to one of those would otherwise fall
    through an implicit else and be silently admitted as "it fits." Anything that is not
    exactly `OK` here is unclassified for this module's purposes and must fail named, not pass
    through.

    This catch-all stays with `COMPILE_INFRASTRUCTURE_FAILURE` (run-scoped) rather than moving to
    `CANDIDATE_COMPILE_FAILED` (per-lead) alongside the content arm, and the reason is which
    compiler can produce these reasons at all. The production `compile_prefix`
    (`run.project_for_posting`) returns `evaluate_compile`'s output, whose only reachable reasons
    are the four this module names — so a fifth arriving here means a compiler was wired in that
    `evaluate_compile` is not, which is a run-invariant property of the WIRING, true for every
    posting. Per-lead, it would bill N leads to the owner's content for one miswiring; run-scoped,
    it names the defect once. That is also the fail-safe direction: for a reason nobody classified
    we do not know the document caused it, and stopping is cheaper than N wrong diagnoses."""
    if gate.reason is not GateReason.OK:
        raise_violation(
            ProjectionIssue.COMPILE_INFRASTRUCTURE_FAILURE,
            f"compile gate returned {gate.reason.value!r}, which this module does not "
            "recognise as success or as one of its three handled failure arms "
            "(BINARY_MISSING, COMPILE_FAILED, PAGE_LIMIT_EXCEEDED); an unclassified gate reason "
            "is a property of the compiler wired in, not of the owner's content, so it is "
            "treated as infrastructure failure rather than budget overflow or silent success",
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
        # This candidate is what the prefix gained since the last compile, and that compile was
        # `OK` (the pinned base for the first iteration, `_reject_unless_ok` below for the rest) —
        # which is what makes a failure here attributable to `candidate_id` specifically.
        _fatal_if_infrastructure(gate, where=where, candidate=candidate_id)
        if gate.reason is GateReason.PAGE_LIMIT_EXCEEDED:
            break
        _reject_unless_ok(gate, where=where)
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
    # `candidate=None`: nothing has been added yet and nothing smaller has compiled, so a
    # `COMPILE_FAILED` here is unattributable and run-scoped, not one candidate's fault.
    _fatal_if_infrastructure(pinned_gate, where=where, candidate=None)
    if pinned_gate.reason is GateReason.PAGE_LIMIT_EXCEEDED:
        raise_violation(
            ProjectionIssue.PINNED_SET_EXCEEDS_BUDGET,
            f"the pinned entries alone ({sorted(pinned)}) need {pinned_gate.page_count} "
            f"page(s), over the page budget of {context.page_budget}; raise the profile's "
            "resume_max_pages setting, or unpin an entry",
            where=where,
        )
    _reject_unless_ok(pinned_gate, where=where)

    # `EntryScorer.__call__` is typed to `set[str]` (scoring.py); `frozenset` is not a subtype
    # of `set`, so `PostingContext.jd_skills` is converted once, here (mirrors agreement.py's
    # own note at its one call site).
    jd_skills = set(context.jd_skills)
    ranked = _ranked_candidates(pool, jd_skills, scorer, table, taxonomy)
    # Not simply `not ranked`: that would report `used_fallback=True` even when the declaration's
    # own `no_match_fallback` is empty, growing nothing from it — a run that used no fallback at
    # all. `used_fallback` means the fallback LIST was actually consulted, not merely that ranking
    # came up empty.
    used_fallback = not ranked and bool(pool.no_match_fallback_ids)
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
