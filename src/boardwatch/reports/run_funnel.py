"""The per-run funnel artifact — PROGRAM.md §3.P0 **item 1**.

Gate P0 asks for three consecutive runs where the funnel reconciles to 100%, per-rule
abstain for EVERY rule in the catalog, and *which source produced each lead and why every
non-lead was dropped* answerable **from the artifact alone, without reading code**. That
last clause is why this module renders Markdown as well as JSON, and why every stage carries
its drops by name rather than leaving the reader to subtract two numbers.

**P0 item 3 added the two halves item 1 could not carry:** the `shortlist` stage now enters at
the ranker's own considered population, so hard-filter vetoes and everything below the `--top`
cutoff are named buckets instead of vanishing; and the per-source outcome table answers *which
source produced each lead* per board rather than only per lead.

Four properties are load-bearing and each one exists because collapsing it destroys a
signal this program is built to preserve:

  * **A stage that is not instrumented reports `None`, never 0.** Same reasoning as
    `reports/abstain.abstain_rate`: a dedup stage that has never run and a dedup stage that
    dropped nothing are opposite conditions, and 0 reads as the healthy one.
  * **A stage that balances by construction is flagged `derived`.** Either its buckets are a
    SQL partition of what entered, or one bucket is the remainder of the others. Its
    reconciliation cannot fail, so it is bookkeeping and not evidence. Only the non-derived
    stages and the cross-checks can catch a wrong number, and the artifact names which is
    which instead of presenting one uniform row of green ticks.
  * **`cache_hit_unattributed` is never folded into `cache_hit_prior_run`.** Per D-019 a
    NULL run_id means exactly one thing — the row predates attribution — and that population
    can only shrink. Folding it would erase the only evidence that no NULL leaked back in.
  * **`unique` and `assisted` are `None` per source, never 0.** Both are dedup-attribution
    quantities: `assisted` credits a source that arrived second for a posting another source
    won. boardwatch's postings are 1:1 with jobs and each belongs to exactly one company, so
    there is no second source to credit and neither is measurable until P6. Reporting 0 would
    assert "no source ever arrived second" — the naive attribution that, per job-apps'
    handover, nearly cut a working adapter.

The stored verdict vocabulary is `eligible | ineligible | uncertain`; **there is no `abstain`
verdict**. The keystone invariant's ABSTAIN persists as `uncertain`, so this module renames
it on the way out and says so, rather than silently presenting a column the schema lacks.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from boardwatch.reports.abstain import AbstainReport
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    SourceOutcome,
    TailoredArtifactCounts,
)

ARTIFACT_VERSION = 3

# The stored verdict that carries the keystone invariant's ABSTAIN. Named here once so the
# rename is visible rather than scattered through the renderers as a string literal.
STORED_ABSTAIN_VERDICT = "uncertain"


@dataclass(frozen=True)
class Drop:
    """A named reason postings left the funnel at a stage, and how many did."""

    reason: str
    count: int
    note: str = ""


@dataclass(frozen=True)
class Stage:
    """One funnel edge: what entered, what advanced, and every reason for the difference."""

    name: str
    entered: int | None
    advanced: int | None
    drops: tuple[Drop, ...] = ()
    note: str = ""
    # True when one drop bucket is the remainder of the others, so `reconciled` holds by
    # construction. Recorded so a reader never mistakes arithmetic for verification.
    derived: bool = False

    @property
    def instrumented(self) -> bool:
        return self.entered is not None and self.advanced is not None

    @property
    def dropped(self) -> int:
        return sum(drop.count for drop in self.drops)

    @property
    def reconciled(self) -> bool | None:
        """None when the stage is not instrumented — an uncomputable identity is not a pass."""
        if not self.instrumented:
            return None
        assert self.entered is not None and self.advanced is not None  # narrowed by instrumented
        return self.entered == self.advanced + self.dropped


@dataclass(frozen=True)
class CrossCheck:
    """The same quantity counted twice, by paths that share no code.

    `CLAUDE.md`: a component's self-report is not verification. `in_memory` is what the
    pipeline believed it did; `from_store` is what the database says on a read that never
    touched the pipeline's objects. Disagreement is recorded, never resolved by preferring
    one — the artifact's job is to make the disagreement visible.
    """

    name: str
    in_memory: int
    from_store: int
    note: str = ""

    @property
    def agrees(self) -> bool:
        return self.in_memory == self.from_store


@dataclass(frozen=True)
class SourceTotal:
    """A funnel total re-swept per board, and the funnel's own figure for it.

    Distinct from `CrossCheck`, whose two numbers are pipeline-memory vs store. Both numbers
    here come from the store; what has to differ for the comparison to be worth anything is the
    SHAPE of the two counts.

    Only one total qualifies, and a second one was deleted for failing this test (D-028). A
    per-board `eligible` total grouped the very same subquery the verdict stage counts, by a
    NOT NULL foreign key, joined on a primary key — so it agreed for every possible database
    state. Grouping the same query differently is not "counting through a different path".

    `leads` qualifies because its two sides are shaped differently: a row count of artifacts
    against a distinct-posting count resolved through `posting_versions`. Neither way it can
    disagree is reachable through today's tailor path, so it is a guard against a future
    writer, not live evidence — and it says so rather than claiming more.
    """

    name: str
    funnel: int
    per_source: int
    note: str = ""

    @property
    def agrees(self) -> bool:
        return self.funnel == self.per_source


@dataclass(frozen=True)
class Lead:
    """One tailored lead and the board it came from.

    The provenance fields are what make Gate P0's *"which source produced each lead"*
    answerable from the artifact alone.
    """

    posting_id: int
    title: str
    company: str
    provider: str
    board_slug: str
    company_source: str
    out_dir: str
    pdf_built: bool


@dataclass(frozen=True)
class ShortlistCounts:
    """The ranker's population accounting: every exit it has, counted where it happens.

    `considered` is the row count the ranker fetched, measured independently of the loop that
    produces everything else. That is what makes `considered == shortlisted + every drop` a
    falsifiable identity rather than bookkeeping — it breaks if a `continue` is ever added
    without a counter, which is the only realistic way the ranker starts losing postings again.

    This is the stage that closes Gate P0's *"why every non-lead was dropped"* clause. Before
    P0 item 3 the ranker reported only `hidden_ineligible` and `hidden_non_swe`, so hard-filter
    vetoes and everything below the `--top` cutoff landed in no bucket at all — **15,959 of
    19,262 open postings** on this session's run 6, of which 11,517 were hard-filter vetoes and
    4,442 were below the cutoff.
    """

    considered: int
    shortlisted: int
    hidden_hard_filter: int = 0
    hidden_non_swe: int = 0
    hidden_ineligible: int = 0
    hidden_below_cutoff: int = 0
    skipped_not_new: int = 0


@dataclass(frozen=True)
class RunManifest:
    """P0 item 4: the versioned identity a run ran under, so two runs can be compared for
    reproducibility from the artifact alone.

    Five of the six fields are REUSED, not rebuilt (see `reports/manifest.py`): the code
    fingerprint is `engine_version()`, `rules_hash` covers `{catalog_version, source, policy}`,
    `profile_facts_hash` is the eligibility `profile_hash`, and start/end + `status` come off
    the `runs` row. `config_hash` and `profile_row_hash` are the two genuinely-new hashes.

    The hashes that depend on a profile are `None` on a run with no profile — the same run that
    reports the whole corpus as `no_current_evaluation`. `code_fingerprint`, `config_hash` and
    `status` are always present.
    """

    code_fingerprint: str
    config_hash: str
    profile_facts_hash: str | None
    profile_row_hash: str | None
    rules_hash: str | None
    status: str


@dataclass(frozen=True)
class StubRate:
    """P0 item 6: the fraction of the corpus whose JD body is empty, reported every run.

    A stub is a posting the fetcher could not give a body for. §6 correction 4: this is a
    pathology of HTML scraping, and boardwatch reads structured ATS JSON, so the number should
    stay near zero — it is cheap insurance that fires visibly if a non-API source ever makes it
    non-trivial, at which point the recovery chain gets built with evidence rather than on spec.
    """

    open_postings: int
    stubs: int

    @property
    def rate(self) -> float | None:
        """None over an empty corpus — a rate over zero rows is undefined, not 0%."""
        return None if self.open_postings == 0 else self.stubs / self.open_postings


# The closed catalog of Tier-B rewrite outcomes. `drop_reason` is an untyped string at the
# raise site (`tailor/rewrite/lane.py`), so it is mapped here into named buckets; anything the
# catalog does not name lands in `other`, which is a FAILURE signal (CLAUDE.md: out-of-catalog
# is never a new bucket), not silently discarded.
_FILTER_PREFIX = "filter:"


@dataclass(frozen=True)
class FabricationCounters:
    """P0 item 8 / bar metric B4: the fabrication gate's per-lane tally.

    Tier B is the LLM-assisted lane, the only one that can fabricate — Tier A is structural and
    cannot. `judge_rejected` and `overmatch_filtered` are the two truth gates: the fail-closed
    entailment judge and the deterministic overmatch filter. `budget`/`error`/`no_candidate`
    are non-fabrication fallbacks. `other` counts any `drop_reason` the closed catalog does not
    name and is a defect if non-zero.

    Not instrumented for Tier A: its own fail-safe (`TierASafetyError`) has no counter yet, and
    `bullets_seen` counts only bullets that reached the Tier-B lane. Zero here means Tier B did
    not run (LLM tailoring off), which is an honest zero, not a hidden one.

    `provenance_rejected` (P1b) counts rewords vetoed by the token-provenance check — deliberately
    over-broad, so it is reported distinctly and deliberately excluded from `rejected` below: a
    conservative veto is not a caught fabrication.

    `lift_rejected` (P4 item 1, D-048) counts rewords vetoed by the deterministic overmatch
    guard (`drop_reason="overmatch"`) — a verbatim JD-span lift or a copy of the JD's own
    unusual capitalization of a non-canonical term. Same treatment as `provenance_rejected`
    and reported distinctly from `overmatch_filtered` above (an unrelated, older, pre-judge
    invented-entity/skill filter that shares the "overmatch" name by coincidence): a
    style/lift veto is conservative, not a caught fabrication, so it too is excluded from
    `rejected` below.

    `banned_register_rejected` / `buzzword_rejected` / `verb_diversity_rejected` (P4 item
    3a) count the three new craft-register guards — a closed-catalog AI-résumé cliché
    (`drop_reason="banned_register"`), a per-bullet buzzword-density ceiling
    (`"buzzword_density"`), and the résumé-wide verb-opening-diversity post-pass demoting
    an excess-repeat rewrite (`"verb_repeat"`). Same treatment as `provenance_rejected` and
    `lift_rejected`: these are craft/register vetoes, not caught fabrications, so all three
    are excluded from `rejected` below.

    `requirement_echo_rejected` (P4 item 3b) counts rewords vetoed for RESTATING a JD
    qualification instead of describing real work (`drop_reason="requirement_echo"`) — the
    paraphrase case `lift_rejected`'s verbatim-lift check is silent on. Same treatment as
    the other craft/register vetoes: excluded from `rejected` below.
    """

    lane: str
    bullets_seen: int
    kept: int
    unchanged: int
    judge_rejected: int
    overmatch_filtered: int
    budget: int
    error: int
    no_candidate: int
    provenance_rejected: int
    lift_rejected: int
    banned_register_rejected: int
    buzzword_rejected: int
    verb_diversity_rejected: int
    requirement_echo_rejected: int
    other: int

    @property
    def rejected(self) -> int:
        """The two truth-gate rejections — what bar metric B4 is 0-or-not against."""
        return self.judge_rejected + self.overmatch_filtered


def build_fabrication_counters(
    rewrite_rows: Sequence[dict[str, object]], *, lane: str = "tier_b"
) -> FabricationCounters:
    """Fold per-bullet Tier-B rewrite rows into the closed outcome catalog. Pure."""
    kept = unchanged = judge = overmatch = budget = error = no_candidate = provenance = 0
    lift = banned_register = buzzword = verb_diversity = requirement_echo = other = 0
    for row in rewrite_rows:
        if row.get("kept"):
            kept += 1
            continue
        reason = row.get("drop_reason")
        if reason == "unchanged":
            unchanged += 1
        elif reason == "judge":
            judge += 1
        elif isinstance(reason, str) and reason.startswith(_FILTER_PREFIX):
            overmatch += 1
        elif reason == "budget":
            budget += 1
        elif reason == "error":
            error += 1
        elif reason == "no_candidate":
            no_candidate += 1
        elif reason == "provenance":
            provenance += 1
        elif reason == "overmatch":
            lift += 1
        elif reason == "banned_register":
            banned_register += 1
        elif reason == "buzzword_density":
            buzzword += 1
        elif reason == "verb_repeat":
            verb_diversity += 1
        elif reason == "requirement_echo":
            requirement_echo += 1
        else:
            other += 1
    return FabricationCounters(
        lane=lane,
        bullets_seen=len(rewrite_rows),
        kept=kept,
        unchanged=unchanged,
        judge_rejected=judge,
        overmatch_filtered=overmatch,
        budget=budget,
        error=error,
        no_candidate=no_candidate,
        provenance_rejected=provenance,
        lift_rejected=lift,
        banned_register_rejected=banned_register,
        buzzword_rejected=buzzword,
        verb_diversity_rejected=verb_diversity,
        requirement_echo_rejected=requirement_echo,
        other=other,
    )


@dataclass(frozen=True)
class ScanContext:
    """Scan throughput. Deliberately NOT a funnel edge.

    `postings_seen` counts postings a board LISTED this run — an unchanged board returns 304
    and lists none — while the funnel's head is every open posting in the store. Chaining one
    into the other would be arithmetic that is wrong on every run with an unchanged board,
    and on every `--no-scan` run it would be wrong by the entire corpus.
    """

    ran: bool
    boards_attempted: int = 0
    boards_complete: int = 0
    boards_failed: int = 0
    postings_seen: int = 0


@dataclass(frozen=True)
class RunFunnel:
    run_id: int
    started_at: datetime | None
    finished_at: datetime | None
    manifest: RunManifest
    scan: ScanContext
    stages: tuple[Stage, ...]
    leads: tuple[Lead, ...]
    cross_checks: tuple[CrossCheck, ...]
    sources: tuple[SourceOutcome, ...]
    source_totals: tuple[SourceTotal, ...]
    stub_rate: StubRate
    fabrication: FabricationCounters
    abstain: AbstainReport
    unattributed_evaluations: int
    errors: tuple[str, ...] = ()
    fatal: str | None = None

    @property
    def instrumented_stages(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.stages if stage.instrumented)

    @property
    def unreconciled(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.instrumented_stages if stage.reconciled is False)

    @property
    def disagreements(self) -> tuple[CrossCheck, ...]:
        return tuple(check for check in self.cross_checks if not check.agrees)

    @property
    def unattributable(self) -> tuple[SourceTotal, ...]:
        """Totals the per-board sweep could not account for.

        Today that means exactly one thing: a `resume_tailored` ARTIFACT this run counted that
        resolves to no board. Postings are NOT checked — a posting belonging to no board is
        unreachable, and the total that claimed to check it was deleted for being unfailable
        (D-028). Gate P0 asks which source produced each lead, so the artifact side is the part
        that matters.
        """
        return tuple(total for total in self.source_totals if not total.agrees)

    @property
    def reconciles(self) -> bool:
        """Gate P0's "reconciles to 100%": every instrumented stage balances, both independent
        recounts agree with what the pipeline reported, and every `resume_tailored` artifact
        this run counted resolves to a board. Note the last clause covers ARTIFACTS only; no
        posting-level attribution check exists, because one cannot fail (D-028)."""
        return not self.unreconciled and not self.disagreements and not self.unattributable

    @property
    def rules_missing_abstain(self) -> int:
        """Gate P0 requires abstain for EVERY rule; the catalog enumeration guarantees a row
        for each, so this is 0 unless the catalog itself failed to load."""
        return 0 if self.abstain.rules else 1


def build_run_funnel(
    *,
    run_id: int,
    started_at: datetime | None,
    finished_at: datetime | None,
    manifest: RunManifest,
    scan: ScanContext,
    corpus: CorpusCounts,
    shortlist: ShortlistCounts | None,
    sources: Sequence[SourceOutcome],
    leads: Sequence[Lead],
    tailor_failed: int,
    tailored_artifacts: TailoredArtifactCounts,
    marked_applied: int,
    stub_postings: int,
    rewrite_rows: Sequence[dict[str, object]],
    unattributed_evaluations: int,
    abstain: AbstainReport,
    errors: Sequence[str] = (),
    fatal: str | None = None,
) -> RunFunnel:
    """Assemble the funnel from counts. Pure: no engine, no clock, no filesystem."""
    verdicts = dict(corpus.by_verdict)
    eligible = verdicts.pop("eligible", 0)
    ineligible = verdicts.pop("ineligible", 0)
    abstained = verdicts.pop(STORED_ABSTAIN_VERDICT, 0)
    # Anything the CHECK constraint does not currently allow. Carried rather than dropped so
    # that widening the constraint cannot make rows vanish from the verdict stage and quietly
    # shrink its denominator — the same guard `RuleAbstain.other` exists for.
    other_verdicts = sum(verdicts.values())

    tailored = len(leads)
    with_pdf = sum(1 for lead in leads if lead.pdf_built)

    if shortlist is None:
        # The ranker never ran: a fatal scan outage or a missing profile returns before it. Its
        # considered population is therefore UNKNOWN, and per this module's first rule that is
        # reported as None. Reporting 0 in / 0 out with derived=False would assert the opposite
        # — that the ranker ran, considered nothing and accounted for everything — and would put
        # `shortlist` in the artifact's list of stages whose balance could actually have failed.
        shortlist_stage = Stage(
            name="shortlist",
            entered=None,
            advanced=None,
            note=(
                "NOT INSTRUMENTED. No shortlist counts were recorded for this run, so how many "
                "postings the ranker considered is unknown and is reported as unmeasured rather "
                "than as zero. **Why** is not asserted here: it is whatever the FATAL line and "
                "the Errors section below say, and on an aborted run this stage cannot know. An "
                "earlier version named a missing profile or a scan outage, which fabricated a "
                "cause on any run that crashed for some third reason."
            ),
        )
    else:
        shortlist_stage = Stage(
            name="shortlist",
            # The RANKER's own considered population, not the verdict stage's `eligible`. Those
            # are different sets and subtracting one from the other is what an earlier version
            # did: `eligible` spans every open posting's verdict, while the ranker's counters
            # cover only postings that reached it, and it hides on criteria the verdict stage
            # knows nothing about. With `ineligible` currently 0 store-wide `eligible` happens
            # to dominate, but the moment P2 makes `ineligible` reachable the remainder would
            # go negative and Gate P0's headline metric would read FAILED for a benign reason.
            entered=shortlist.considered,
            advanced=shortlist.shortlisted,
            drops=(
                Drop(
                    reason="skipped_not_new",
                    count=shortlist.skipped_not_new,
                    note="narrowed away by --new; a scoping choice, not a rejection",
                ),
                Drop(
                    reason="hidden_hard_filter",
                    count=shortlist.hidden_hard_filter,
                    note=(
                        "excluded title; ALSO a rejected location when "
                        "location_filter_mode is `hard`, which is not the default and has "
                        "never been measured firing"
                    ),
                ),
                Drop(reason="hidden_non_swe", count=shortlist.hidden_non_swe,
                     note="title role gate"),
                Drop(reason="hidden_ineligible", count=shortlist.hidden_ineligible),
                Drop(
                    reason="capped_by_top_n",
                    count=shortlist.hidden_below_cutoff,
                    note="cleared every filter and was beaten only by rank",
                ),
            ),
            # NOT derived. `entered` is the ranker's own row count, measured independently of
            # the five counters below, so this identity can genuinely fail — it is the stage
            # P0 item 3 turned from bookkeeping into evidence.
            derived=False,
            note=(
                "The ranker's whole considered population. NOT a continuation of `verdict` — "
                "the two count different populations, so the numbers here will not match it. "
                "Every exit is counted where the posting actually leaves."
            ),
        )

    stages = (
        Stage(
            name="dedup",
            entered=None,
            advanced=None,
            note=(
                "NOT INSTRUMENTED. jobs and postings are 1:1, so grouping has never run and "
                "duplicate leakage is structurally unmeasurable. Owned by P6 — reported as "
                "unmeasured rather than as zero duplicates, which is the opposite claim."
            ),
        ),
        Stage(
            name="corpus",
            entered=corpus.open_postings,
            advanced=corpus.evaluated,
            drops=(
                Drop(
                    reason="no_current_evaluation",
                    count=corpus.no_current_evaluation,
                    note=(
                        "open posting with no version row, or whose current version has "
                        "never been judged under this profile+rules identity"
                    ),
                ),
            ),
            note="Head of the funnel: every OPEN posting in the store, not just those listed"
            " this run.",
        ),
        Stage(
            name="attribution",
            derived=True,
            entered=corpus.evaluated,
            advanced=corpus.judged_this_run,
            drops=(
                Drop(
                    reason="cache_hit_prior_run",
                    count=corpus.cache_hit_prior_run,
                    note="already judged by an earlier run; no evaluation row written now",
                ),
                Drop(
                    reason="cache_hit_unattributed",
                    count=corpus.cache_hit_unattributed,
                    note=(
                        "judged before run attribution existed (run_id IS NULL). Its own "
                        "bucket by D-019 and never folded into the line above"
                    ),
                ),
            ),
            note=(
                "The stage D-016 exists for: 'judged this run' and 'cache hit' are the same "
                "number without run_id. DERIVED — the three buckets are a SQL partition of "
                "the very set `entered` counts, so this balance holds for every possible "
                "database state. The bucket VALUES are the information here; the tick is not."
            ),
        ),
        Stage(
            name="verdict",
            derived=True,
            entered=corpus.evaluated,
            advanced=eligible,
            drops=(
                Drop(reason="ineligible", count=ineligible),
                Drop(
                    reason="abstained",
                    count=abstained,
                    note=f"stored as verdict {STORED_ABSTAIN_VERDICT!r}; there is no 'abstain'"
                    " verdict in the schema",
                ),
                Drop(
                    reason="verdict_out_of_vocabulary",
                    count=other_verdicts,
                    note="impossible while the CHECK constraint holds; carried so widening it"
                    " cannot shrink this stage silently",
                ),
            ),
            note=(
                "DERIVED for the same reason as attribution: a GROUP BY over the set "
                "`entered` counts. The split is the information; the tick is not."
            ),
        ),
        shortlist_stage,
        Stage(
            name="tailor",
            # None, not 0, for the same reason as the shortlist stage above: if the ranker never
            # ran, how many leads it would have handed over is unknown rather than zero.
            entered=None if shortlist is None else shortlist.shortlisted,
            advanced=tailored,
            drops=(Drop(reason="tailor_failed", count=tailor_failed),),
        ),
        Stage(
            name="pdf",
            entered=tailored,
            advanced=with_pdf,
            drops=(
                Drop(
                    reason="no_pdf",
                    count=tailored - with_pdf,
                    note="résumé source written but no PDF compiled — D-006's silent degrade",
                ),
            ),
            derived=True,
        ),
        Stage(
            name="applied",
            # Rooted at `tailored`, not `with_pdf`. `marked_applied` is counted over every
            # tailored posting, so against `with_pdf` it can legitimately EXCEED what entered
            # — a lead that degraded to no PDF but whose job was already tracked — and the
            # clamped remainder would then report the stage as broken. Bounded by
            # construction here: the count is DISTINCT job ids drawn from these postings.
            entered=tailored,
            advanced=marked_applied,
            drops=(
                Drop(
                    reason="not_marked_applied",
                    count=tailored - marked_applied,
                    note="snapshot at write time; marking applied is a later manual act",
                ),
            ),
            derived=True,
        ),
    )

    cross_checks = (
        CrossCheck(
            name="tailored",
            in_memory=tailored,
            from_store=tailored_artifacts.rows,
            note="pipeline's lead objects vs resume_tailored rows carrying this run_id",
        ),
        CrossCheck(
            name="leads_with_pdf",
            in_memory=with_pdf,
            from_store=tailored_artifacts.with_pdf,
            note=(
                "pipeline's pdf_built flags vs json_extract(meta_json,'$.typst_pdf_built'). "
                "artifacts.uri is the .typ path either way, so a row count would not do"
            ),
        ),
    )

    # ONE total, not two. A per-board `eligible` total was shipped here and deleted after
    # review: it grouped the very same current-identity subquery the verdict stage counts, by a
    # NOT NULL foreign key, joined on a primary key — so its sum equalled the verdict stage's
    # `eligible` for every possible database state. That is the unfailable-assertion defect
    # D-023 exists to forbid, and it was labelled as evidence. Deleted rather than kept as
    # decoration, exactly as D-023 deleted the two `*_reconciles` properties.
    source_totals = (
        SourceTotal(
            name="leads",
            funnel=tailored_artifacts.rows,
            per_source=sum(item.leads for item in sources),
            note=(
                "resume_tailored ROWS for this run vs DISTINCT postings resolved to a board "
                "through posting_versions. Different shapes, so it can disagree: an artifact "
                "whose posting_version_id is NULL resolves to no board, and two artifacts for "
                "one posting in one run collapse to a single distinct posting. Neither is "
                "reachable through the normal tailor path, so treat this as a guard against a "
                "future writer, not as live evidence"
            ),
        ),
    )

    return RunFunnel(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        manifest=manifest,
        scan=scan,
        stages=stages,
        leads=tuple(leads),
        cross_checks=cross_checks,
        sources=tuple(sources),
        source_totals=source_totals,
        stub_rate=StubRate(open_postings=corpus.open_postings, stubs=stub_postings),
        fabrication=build_fabrication_counters(rewrite_rows),
        abstain=abstain,
        unattributed_evaluations=unattributed_evaluations,
        errors=tuple(errors),
        fatal=fatal,
    )


def _stage_json(stage: Stage) -> dict[str, object]:
    return {
        "name": stage.name,
        "entered": stage.entered,
        "advanced": stage.advanced,
        "drops": [
            {"reason": drop.reason, "count": drop.count, "note": drop.note}
            for drop in stage.drops
        ],
        "reconciled": stage.reconciled,
        "instrumented": stage.instrumented,
        "derived": stage.derived,
        "note": stage.note,
    }


def funnel_to_dict(funnel: RunFunnel) -> dict[str, object]:
    """The machine-readable half. Every stage keeps its drops; nothing is pre-summed away."""
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": funnel.run_id,
        "started_at": funnel.started_at.isoformat() if funnel.started_at else None,
        "finished_at": funnel.finished_at.isoformat() if funnel.finished_at else None,
        "reconciles": funnel.reconciles,
        "fatal": funnel.fatal,
        "errors": list(funnel.errors),
        "manifest": {
            "code_fingerprint": funnel.manifest.code_fingerprint,
            "config_hash": funnel.manifest.config_hash,
            "profile_facts_hash": funnel.manifest.profile_facts_hash,
            "profile_row_hash": funnel.manifest.profile_row_hash,
            "rules_hash": funnel.manifest.rules_hash,
            "status": funnel.manifest.status,
        },
        "stub_rate": {
            "open_postings": funnel.stub_rate.open_postings,
            "stubs": funnel.stub_rate.stubs,
            # None, never 0.0, over an empty corpus — see StubRate.rate.
            "rate": funnel.stub_rate.rate,
        },
        "fabrication": {
            "lane": funnel.fabrication.lane,
            "bullets_seen": funnel.fabrication.bullets_seen,
            "kept": funnel.fabrication.kept,
            "unchanged": funnel.fabrication.unchanged,
            "judge_rejected": funnel.fabrication.judge_rejected,
            "overmatch_filtered": funnel.fabrication.overmatch_filtered,
            "budget": funnel.fabrication.budget,
            "error": funnel.fabrication.error,
            "no_candidate": funnel.fabrication.no_candidate,
            "provenance_rejected": funnel.fabrication.provenance_rejected,
            "lift_rejected": funnel.fabrication.lift_rejected,
            "banned_register_rejected": funnel.fabrication.banned_register_rejected,
            "buzzword_rejected": funnel.fabrication.buzzword_rejected,
            "verb_diversity_rejected": funnel.fabrication.verb_diversity_rejected,
            "requirement_echo_rejected": funnel.fabrication.requirement_echo_rejected,
            "other": funnel.fabrication.other,
            "rejected": funnel.fabrication.rejected,
        },
        "scan": {
            "ran": funnel.scan.ran,
            "boards_attempted": funnel.scan.boards_attempted,
            "boards_complete": funnel.scan.boards_complete,
            "boards_failed": funnel.scan.boards_failed,
            "postings_seen": funnel.scan.postings_seen,
        },
        "stages": [_stage_json(stage) for stage in funnel.stages],
        "cross_checks": [
            {
                "name": check.name,
                "in_memory": check.in_memory,
                "from_store": check.from_store,
                "agrees": check.agrees,
                "note": check.note,
            }
            for check in funnel.cross_checks
        ],
        "leads": [
            {
                "posting_id": lead.posting_id,
                "title": lead.title,
                "company": lead.company,
                "provider": lead.provider,
                "board_slug": lead.board_slug,
                "company_source": lead.company_source,
                "out_dir": lead.out_dir,
                "pdf_built": lead.pdf_built,
            }
            for lead in funnel.leads
        ],
        "sources": [
            {
                "provider": item.provider,
                "board_slug": item.board_slug,
                "company_source": item.company_source,
                "open_postings": item.open_postings,
                # null, never 0: both are dedup-attribution quantities and dedup is P6. 0 would
                # assert no source ever arrived second, which is the opposite of unknown.
                "unique": item.unique,
                "assisted": item.assisted,
                "eligible": item.eligible,
                "leads": item.leads,
                "applied": item.applied,
            }
            for item in funnel.sources
        ],
        "source_totals": [
            {
                "name": total.name,
                "funnel": total.funnel,
                "per_source": total.per_source,
                "agrees": total.agrees,
                "note": total.note,
            }
            for total in funnel.source_totals
        ],
        "unattributed_evaluations": funnel.unattributed_evaluations,
        "abstain": {
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "family": rule.family,
                    "observed": rule.observed,
                    "met": rule.met,
                    "unmet": rule.unmet,
                    "abstained": rule.unknown,
                    # None, never 0.0 — a rate over zero rows is undefined, and 0% would
                    # make a rule that has never fired the healthiest in the catalog.
                    "abstain_rate": rule.abstain_rate,
                    "never_fired": rule.never_fired,
                    "fully_abstaining": rule.fully_abstaining,
                }
                for rule in funnel.abstain.rules
            ],
            "rule_count": len(funnel.abstain.rules),
            "never_fired": len(funnel.abstain.never_fired),
            "fully_abstaining": len(funnel.abstain.fully_abstaining),
            "out_of_catalog": list(funnel.abstain.out_of_catalog),
            "out_of_catalog_rows": funnel.abstain.out_of_catalog_rows,
            "unattributed_rows": funnel.abstain.unattributed,
            "total_rows": funnel.abstain.total_rows,
        },
    }


def _fmt(value: int | None) -> str:
    return "not instrumented" if value is None else str(value)


def _provider_rollup(sources: Sequence[SourceOutcome]) -> list[tuple[str, int, int, int, int, int]]:
    """(provider, boards, open, eligible, leads, applied), busiest first.

    Kept beside the per-board table rather than replacing it because the two answer different
    questions. PROGRAM.md's breadth argument — whether direct-ATS-only can carry the volume —
    is a question about PROVIDERS, and 118 board rows do not answer it at a glance.
    """
    totals: dict[str, list[int]] = {}
    for item in sources:
        row = totals.setdefault(item.provider, [0, 0, 0, 0, 0])
        row[0] += 1
        row[1] += item.open_postings
        row[2] += item.eligible
        row[3] += item.leads
        row[4] += item.applied
    return sorted(
        ((provider, *counts) for provider, counts in totals.items()),  # type: ignore[misc]
        key=lambda row: (-row[4], -row[3], -row[2], row[0]),
    )


def funnel_to_markdown(funnel: RunFunnel) -> str:
    """The half a human reads. Gate P0 requires the artifact to answer, on its own, which
    source produced each lead and why every non-lead was dropped — so every drop is named
    and counted here, and the leads table carries its board."""
    verdict = "RECONCILES" if funnel.reconciles else "DOES NOT RECONCILE"
    lines = [
        f"# boardwatch run {funnel.run_id} — funnel",
        "",
        f"- **started:** {funnel.started_at.isoformat() if funnel.started_at else '—'}",
        f"- **finished:** {funnel.finished_at.isoformat() if funnel.finished_at else '—'}",
        f"- **reconciliation:** {verdict}",
    ]
    if funnel.fatal:
        lines.append(f"- **FATAL:** {funnel.fatal}")
    m = funnel.manifest
    lines += [
        "",
        "## Manifest",
        "",
        "*What this run ran AS. Two runs sharing every hash below should turn the same corpus "
        "into the same leads. A hash tied to the profile is `—` on a run with no profile.*",
        "",
        "| field | value |",
        "|---|---|",
        f"| status | {m.status} |",
        f"| code fingerprint | {m.code_fingerprint} |",
        f"| config hash | {m.config_hash} |",
        f"| profile facts hash | {m.profile_facts_hash or '—'} |",
        f"| profile row hash | {m.profile_row_hash or '—'} |",
        f"| rules hash | {m.rules_hash or '—'} |",
        "",
        "*`config hash` covers the decision-relevant `Settings`; `profile row hash` covers the "
        "five profile columns the ranker reads (incl. `exclude_titles`). Neither covers the "
        "skill-taxonomy version — `taxonomy.yaml` can change which postings score as covered "
        "without moving either hash.*",
        "",
        "## Scan",
        "",
    ]
    if funnel.scan.ran:
        lines.append(
            f"{funnel.scan.boards_attempted} boards attempted · "
            f"{funnel.scan.boards_complete} complete · {funnel.scan.boards_failed} failed · "
            f"{funnel.scan.postings_seen} postings listed"
        )
        lines.append("")
        lines.append(
            "*Throughput, not a funnel edge: an unchanged board lists nothing, so this is a "
            "different population from the corpus below.*"
        )
    else:
        lines.append("skipped (`--no-scan`) — the corpus below is whatever was already stored.")

    lines += [
        "",
        "## Funnel",
        "",
        "| stage | entered | advanced | dropped | reconciled |",
        "|---|---:|---:|---:|---|",
    ]
    for stage in funnel.stages:
        if stage.reconciled is None:
            mark = "—"
        elif stage.reconciled:
            mark = "yes (derived)" if stage.derived else "**yes**"
        else:
            mark = "**NO**"
        lines.append(
            f"| {stage.name} | {_fmt(stage.entered)} | {_fmt(stage.advanced)} | "
            f"{stage.dropped if stage.instrumented else '—'} | {mark} |"
        )

    falsifiable = [s.name for s in funnel.instrumented_stages if not s.derived]
    lines += [
        "",
        "`yes (derived)` means the stage balances by construction — its buckets are a "
        "partition of what entered, or one bucket is the remainder of the others — so it "
        "cannot fail. That is bookkeeping, not evidence; the numbers in such a stage are "
        "still the point, but the tick beside them proves nothing.",
        "",
        f"**Stages whose balance could actually have failed: {', '.join(falsifiable) or 'none'}.** "
        "Everything else that can catch a wrong number is in the cross-checks below.",
        "",
        "## Why every non-lead was dropped",
        "",
    ]
    for stage in funnel.stages:
        if not stage.instrumented:
            # Guarded rather than relying on every uninstrumented stage carrying a note: an
            # empty one rendered a bare `**` under "why every non-lead was dropped".
            lines += [f"### {stage.name}", ""]
            lines += [f"*{stage.note}*", ""] if stage.note else ["not measured this run.", ""]
            continue
        lines.append(f"### {stage.name} — {stage.entered} in, {stage.advanced} out")
        lines.append("")
        if stage.note:
            lines += [f"*{stage.note}*", ""]
        if not stage.drops:
            lines += ["nothing dropped here.", ""]
            continue
        for drop in stage.drops:
            suffix = f" — {drop.note}" if drop.note else ""
            lines.append(f"- **{drop.reason}**: {drop.count}{suffix}")
        lines.append("")

    lines += ["## Cross-checks", "", "| quantity | pipeline said | store says | agree |",
              "|---|---:|---:|---|"]
    for check in funnel.cross_checks:
        lines.append(
            f"| {check.name} | {check.in_memory} | {check.from_store} | "
            f"{'yes' if check.agrees else '**NO**'} |"
        )
    lines += [
        "",
        *[f"- *{check.name}*: {check.note}" for check in funnel.cross_checks if check.note],
        "",
        "## Leads",
        "",
    ]
    if funnel.leads:
        lines += [
            "| posting | title | company | source board | registry/user | PDF | folder |",
            "|---:|---|---|---|---|---|---|",
        ]
        for lead in funnel.leads:
            lines.append(
                f"| {lead.posting_id} | {lead.title} | {lead.company} | "
                f"{lead.provider}:{lead.board_slug} | {lead.company_source} | "
                f"{'yes' if lead.pdf_built else '**no**'} | {lead.out_dir} |"
            )
    else:
        lines.append("none.")

    lines += [
        "",
        "## Per-source outcomes",
        "",
        f"{len(funnel.sources)} boards owning an open posting, or a lead from this run.",
        "",
        "`unique` and `assisted` are **not instrumented** — both are dedup-attribution "
        "quantities (`assisted` credits a source that arrived second for a posting another "
        "source won), and dedup is P6. They are not 0: reporting 0 would assert that no source "
        "ever arrived second, which is the naive attribution that nearly cost job-apps a "
        "working adapter.",
        "",
        "`open` is every OPEN posting the board owns, **not** what it listed this run — an "
        "unchanged board lists nothing and would otherwise show a denominator of zero.",
        "",
        "| board | registry/user | open | unique | assisted | eligible | leads | applied |",
        "|---|---|---:|---|---|---:|---:|---:|",
    ]
    for item in funnel.sources:
        lines.append(
            f"| {item.board} | {item.company_source} | {item.open_postings} | "
            f"{_fmt(item.unique)} | {_fmt(item.assisted)} | {item.eligible} | "
            f"{item.leads} | {item.applied} |"
        )
    if not funnel.sources:
        lines.append("| _(none)_ | — | 0 | not instrumented | not instrumented | 0 | 0 | 0 |")

    lines += [
        "",
        "### By provider",
        "",
        "| provider | boards | open | eligible | leads | applied |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for provider, boards, open_postings, eligible_count, leads_count, applied_count in (
        _provider_rollup(funnel.sources)
    ):
        lines.append(
            f"| {provider} | {boards} | {open_postings} | {eligible_count} | "
            f"{leads_count} | {applied_count} |"
        )

    lines += [
        "",
        "### Attributable to a board",
        "",
        "| total | funnel | per-source | agree |",
        "|---|---:|---:|---|",
    ]
    for total in funnel.source_totals:
        lines.append(
            f"| {total.name} | {total.funnel} | {total.per_source} | "
            f"{'yes' if total.agrees else '**NO**'} |"
        )
    lines += [
        "",
        "*Both numbers are read from the store; what differs is the SHAPE of the count — a row "
        "count of this run's artifacts against a distinct-posting count resolved through "
        "`posting_versions`. Neither way it can disagree is reachable through today's tailor "
        "path, so read this as a guard against a future writer rather than as live evidence. "
        "Two quantities are deliberately NOT reconciled here. `eligible` cannot be: the "
        "per-board sweep groups the same subquery the verdict stage counts, by a NOT NULL "
        "foreign key, so it would agree for every possible database state (D-028). `applied` "
        "cannot be either: it counts distinct jobs per board, and summing per-board distinct "
        "counts is not the global distinct count if a job ever spans two boards.*",
        *[f"- *{total.name}*: {total.note}" for total in funnel.source_totals if total.note],
    ]

    never_fired = funnel.abstain.never_fired
    fully = funnel.abstain.fully_abstaining
    lines += [
        "",
        "## Per-rule abstain",
        "",
        f"{len(funnel.abstain.rules)} rules in the catalog · {len(never_fired)} never fired · "
        f"{len(fully)} fire but never decide · {funnel.abstain.total_rows} requirement rows",
        "",
        "A rule that has never fired reports `never fired`, **not 0%** — a rate over zero rows "
        "is undefined, and 0% would rank it as the healthiest rule in the catalog.",
        "",
        "| rule | family | observed | met | unmet | abstained | rate |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for rule in funnel.abstain.rules:
        if rule.never_fired:
            rate = "never fired"
        elif rule.fully_abstaining:
            rate = "**100%**"
        else:
            # 1051/1052 rounds to "100%" and would then read identically to a rule that
            # never decides at all, collapsing the two states this report keeps apart.
            rounded = f"{rule.abstain_rate:.0%}"
            rate = ">99%" if rounded == "100%" else rounded
        lines.append(
            f"| {rule.rule_id} | {rule.family} | {rule.observed} | {rule.met} | "
            f"{rule.unmet} | {rule.unknown} | {rate} |"
        )

    if funnel.abstain.out_of_catalog:
        lines += [
            "",
            f"**FAILURE — closed catalog violated:** {funnel.abstain.out_of_catalog_rows} rows "
            f"carry rule_ids the catalog does not declare: "
            f"{', '.join(funnel.abstain.out_of_catalog)}",
        ]

    stub = funnel.stub_rate
    stub_rate = "not instrumented (empty corpus)" if stub.rate is None else f"{stub.rate:.2%}"
    fab = funnel.fabrication
    lines += [
        "",
        "## Stub rate",
        "",
        f"{stub.stubs} of {stub.open_postings} open postings have an empty JD body · "
        f"rate {stub_rate}",
        "",
        "*A stub is a posting whose body the fetcher could not populate. boardwatch reads "
        "structured ATS JSON, so this should stay near zero; a non-trivial value is the signal "
        "that a scraped source has appeared and the recovery chain is now worth building.*",
        "",
        "## Fabrication gate",
        "",
        f"lane `{fab.lane}` · {fab.bullets_seen} bullets seen · {fab.rejected} rejected by a "
        f"truth gate ({fab.judge_rejected} judge, {fab.overmatch_filtered} overmatch) · "
        f"{fab.kept} kept · {fab.unchanged} unchanged",
        "",
        f"fallbacks: {fab.budget} budget · {fab.error} error · {fab.no_candidate} no_candidate",
        "",
        f"{fab.provenance_rejected} rewrites reverted to Tier-A for lack of provenance "
        "(a conservative veto, not a caught fabrication — excluded from `rejected` above)",
        "",
        f"{fab.lift_rejected} rewrites reverted to Tier-A for a verbatim JD-span lift or "
        "unusual capitalization copied from the JD (a conservative veto, not a caught "
        "fabrication — excluded from `rejected` above)",
        "",
        f"{fab.banned_register_rejected} rewrites reverted to Tier-A for a banned-register "
        f"cliché · {fab.buzzword_rejected} for exceeding the per-bullet buzzword-density "
        f"ceiling · {fab.verb_diversity_rejected} for repeating an opening verb past the "
        "résumé-wide cap (craft/register vetoes, not caught fabrications — excluded from "
        "`rejected` above)",
        "",
        f"{fab.requirement_echo_rejected} rewrites reverted to Tier-A for restating a JD "
        "qualification instead of describing real work (a craft/register veto, not a "
        "caught fabrication — excluded from `rejected` above)",
        "",
        "*Bar metric B4 is 0 fabrications over n≥100. `bullets_seen` is n; the two truth gates "
        "are the fail-closed entailment judge and the deterministic overmatch filter. Tier A is "
        "structural and cannot fabricate, so it is not counted here. 0 bullets means the LLM "
        "lane did not run this run — an honest zero.*",
    ]
    if fab.other:
        lines += [
            "",
            f"**FAILURE — {fab.other} rewrite rows carried a drop_reason the closed catalog does "
            "not name.** A Tier-B outcome reached the funnel unclassified; this is a defect, not "
            "a new bucket.",
        ]

    lines += [
        "",
        "## Unattributed",
        "",
        f"{funnel.unattributed_evaluations} evaluations in the whole store carry no run_id.",
        "",
        "Per D-019 that means exactly one thing — the row predates run attribution — and the "
        "number can only shrink. **If it grew since the last run, a NULL leaked back in.** It "
        "is never folded into this run's counts and never reported as 0.",
    ]

    if funnel.errors:
        lines += ["", "## Errors", ""] + [f"- {err}" for err in funnel.errors]

    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class WrittenArtifact:
    json_path: Path
    markdown_path: Path


def write_run_funnel(funnel: RunFunnel, out_dir: Path) -> WrittenArtifact:
    """Write both halves under `out_dir`, named by run so two runs a day cannot collide.

    Written OUTSIDE the git tree, as tailored résumés already are: generalization rule R7
    requires a sha256-pinned SHIPPED_DATA entry for any tracked `.json`, which a per-run
    artifact can never satisfy.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"funnel-{funnel.run_id}.json"
    markdown_path = out_dir / f"funnel-{funnel.run_id}.md"
    json_path.write_text(json.dumps(funnel_to_dict(funnel), indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(funnel_to_markdown(funnel), encoding="utf-8")
    return WrittenArtifact(json_path=json_path, markdown_path=markdown_path)


# Re-exported so callers assembling a funnel need one import, not four.
__all__ = [
    "ARTIFACT_VERSION",
    "CrossCheck",
    "Drop",
    "FabricationCounters",
    "Lead",
    "RunFunnel",
    "RunManifest",
    "ScanContext",
    "ShortlistCounts",
    "SourceTotal",
    "Stage",
    "StubRate",
    "WrittenArtifact",
    "build_fabrication_counters",
    "build_run_funnel",
    "funnel_to_dict",
    "funnel_to_markdown",
    "write_run_funnel",
]
