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
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from boardwatch.projection.run import ProjectionLeadOutcome
from boardwatch.rank.location_gate import LocationClass, classify_location
from boardwatch.reports.abstain import AbstainReport
from boardwatch.reports.board_coverage import CoverageReport as BoardCoverageReport
from boardwatch.reports.board_coverage import (
    board_coverage_headline,
    board_coverage_table,
    board_coverage_to_dict,
)
from boardwatch.store.run_funnel_queries import (
    CorpusCounts,
    SourceOutcome,
    TailoredArtifactCounts,
)
from boardwatch.tailor.coverage import CoverageReport

# How many distinct missing requirement terms the coverage summary lists, most-frequent first.
_TOP_MISSING = 10

# v4 added the top-level `liveness` block (P6 item 6). It stayed 4 through two keys added inside
# blocks that already existed — D-113's `liveness.gone_after_redirect` and D-146's
# `fabrication.lane_dead`: every bump so far has signalled a new top-level SECTION, and D-113 is
# the precedent for declining one on an additive key. **Not** D-031, which declines a bump for a
# change that does not extend the artifact at all (`boardwatch verify` consumes it). Holding at 4
# was safe because no consumer reads these blocks strictly: `cli/verify_cmd.py` pulls named keys out
# of the frozen JSON and tolerates whatever else is there — no schema, no golden fixture, no
# full-dict equality on `fabrication` anywhere (D-147 R3).
#
# **v5 is the `projection` stage (P5a).** It bumps, and D-113 does not apply to it: this is not an
# additive key inside an existing block. `stages` is the artifact's spine, and a new member of it
# changes the CHAIN a reader walks — but the deciding part is that an existing value changed
# MEANING. On a `--project` run the `tailor` stage's `entered` is no longer the ranker's
# `shortlisted`; it is what projection advanced, and the `withheld_not_live` bucket moves with it.
# A consumer comparing `tailor.entered` against the shortlist across two runs would silently read a
# projection loss as a shortlist that shrank. A changed meaning is exactly what a version signals,
# where an added key is not.
#
# **The bump is GLOBAL — an authored run emits 5 too, and that is deliberate (D-225).** One emitter
# with one schema version; versioning per run type would force every consumer to handle both, for a
# field whose whole job is to say which shape it is reading. So `--project`'s "nothing changes
# without the flag" guarantee covers stages, lineage keys, lead outcomes and dispositions — not
# this field, which moves for every run. An earlier wording claimed byte-identical no-flag output
# alongside the bump; the two cannot both hold and the claim, not the bump, was the error.
#
# **v6 is the `board_coverage` section (D-274).** A new top-level SECTION, so D-113's
# declining-a-bump precedent does not reach it. Unlike v5 it changes no existing value's
# meaning: `scan` still counts what boards LISTED this run, and the new section supplies the
# denominator that section never had. It is named `board_coverage` and not `coverage`
# because this artifact already has a `coverage` key holding resume KEYWORD coverage
# (`tailor/coverage.py`) — two different measurements one word apart would mislead every
# future reader, so the collision is closed in the key name rather than in a comment.
# `null` when the load failed, never a zeroed block: see `board_coverage_to_dict`.
#
# **The `lanes` key does NOT bump it, and the ruling is deliberate.** It is an ADDITIVE key on
# the D-113 → D-147 R3 / D-148 R3 precedent, the same one D-285 applied to `SourceOutcome.stubs`.
# What v5 and v6 each bought was something this does not: v5 changed an EXISTING value's meaning
# (`tailor.entered` stopped being the ranker's `shortlisted`), and v6 supplied a denominator the
# `scan` block had been read without. `lanes` changes no existing value — `scan` still counts
# what the six providers listed, every stage's `entered`/`advanced` is untouched — and no
# consumer reads it: `cli/verify_cmd.py` pulls named keys out of the frozen JSON and tolerates
# whatever else is there, with no schema, no golden fixture and no full-dict equality anywhere.
# A run with no lane enabled emits `"lanes": []`, which is honest and costs a reader nothing.
#
# **v7 is a lead's `locations` and the hard US gate's verdict on them (D-267, shipped D-323).**
# It bumps for the v5 reason and not the v6 one: this does not add a section, it changes what a
# `leads` row IS. Until now the record the location gate produces carried no location, so the one
# gate whose failure mode is a lead the user cannot legally take left no trace in its own
# artifact — every
# "all leads US-located" claim in `METRICS.md` came from a by-hand store read inside a session
# and could not be reproduced from the artifact afterwards. `manifest.location_filter_mode` comes
# with it, because the verdicts are unreadable without it: in the default `soft` mode a `non_us`
# lead is documented behaviour, not a leak, and a reader who cannot see the mode cannot tell a
# passing gate from a disarmed one.
ARTIFACT_VERSION = 7

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
    # B5 — present ONLY on the `shortlist` stage: `{judged, handled, applied, duplicate, dead,
    # unexplained}`, run-scoped. A diagnostic for the zero-output guard, not a drop: it is not
    # summed into `dropped`/`reconciled` above. None on every other stage.
    run_scoped_attribution: dict[str, int] | None = None

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
    """One tailored lead, the board it came from, and where the posting says it is.

    The provenance fields are what make Gate P0's *"which source produced each lead"*
    answerable from the artifact alone. `locations` is the same clause for the hard US
    location gate (D-267, shipped D-323): it is the gate's own input, so a reader holding only
    this file can re-derive the verdict instead of taking `location_class` on trust.

    **`locations` is `None`, never `()`, when the posting names no place.** The column is
    nullable, an empty list and a list of blank strings all mean the same thing — the board
    published no location — and `()` would serialise to `[]`, which asserts the board published
    a list and it was empty. Those are different claims about the same posting, and this
    program keeps them apart everywhere (`delivery_queries._posted_days` returns `None` rather
    than `0` for exactly this reason). The one case `None` does NOT separate is a lead whose
    posting row could not be resolved at all; that lead's `provider`/`board_slug`/
    `company_source` all read `"unknown"`, which is how a reader tells the two apart.
    """

    posting_id: int
    title: str
    company: str
    provider: str
    board_slug: str
    company_source: str
    out_dir: str
    pdf_built: bool
    locations: tuple[str, ...] | None

    @property
    def location_class(self) -> LocationClass:
        """The hard gate's own verdict, from the production classifier — not a second copy.

        DERIVED rather than stored so the pair in the artifact cannot disagree: a stored class
        beside stored locations is two facts that can drift, and a lead labelled `us` over a
        French address is worse than no label at all. A posting naming no place is `unknown`,
        which is what the gate FAIL-OPENS on (never silently delete a real US role, Mit's
        ruling) — and reporting it is the point: `unknown` is not `us`.
        """
        return classify_location(self.locations or ())


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
    # P6 slice 1. Only `exact_quad` reaches this counter, and only when identities are
    # complete — a partial backfill suppresses nothing, so 0 here can mean either "no
    # duplicates" or "not backfilled". `unique` in the per-source table distinguishes them.
    hidden_duplicate: int = 0
    # P6 slice 2: suppressed by a live ledger disposition — already built, already refused, or
    # surfaced recently enough to still be inside its `seen` TTL. Unlike `hidden_duplicate` this
    # is NOT gated on identity completeness, so 0 here means 0: no job the ranker considered
    # carried a live disposition.
    hidden_handled: int = 0
    # P6 item 5: the job already carries a SUBMITTED application, so the operator has acted on
    # this lead outside the program. Not gated on identity completeness either, and unlike
    # `hidden_handled` it is released by nothing the program does on its own — no TTL, no policy
    # stamp — only by `track status <id> withdrawn`.
    hidden_applied: int = 0
    # D-246: the title names a seniority band above the operator's `target_seniority_band`. A
    # genuine DROP and part of the identity above. Drained by `top --include-over-seniority`.
    hidden_over_seniority: int = 0
    # Neither the title nor the body carried any recognised signal: the role gate abstained
    # (`uncertain`) AND there was a body AND its taxonomy extraction ran and recognised exactly
    # zero terms. A genuine DROP and part of the identity above, in the same shape as
    # `hidden_over_seniority`. Drained by `top --include-zero-signal`.
    hidden_zero_signal: int = 0
    # The zero-signal rule's abstain rate: `uncertain`-titled postings whose body signal could
    # not be READ at all — no extraction row at the current taxonomy version, or an empty JD
    # body. REPORTED, NEVER DROPPED, and deliberately NOT part of the identity above — these
    # postings are inside `shortlisted` already, so a `Drop` for them would subtract them twice.
    # Reported the same WAY `uncertain_band` is, and not only for the same reason: it is
    # appended to the shortlist stage's `note`, which is the only place it reaches the durable
    # artifact. Without that, `zero_signal_uncertain: 0` could not be told apart from a gate
    # that never got the input it reads — and that ambiguity is the only reason this counter
    # exists, so a value that never leaves memory would defeat it.
    signal_unmeasured: int = 0
    # D-246, the seniority gate's abstain rate: a level token it could not resolve, because no
    # scheme is bound for the company or the rung falls outside the bound one. REPORTED, NEVER
    # DROPPED, and deliberately NOT part of the identity above — these postings are inside
    # `shortlisted` already, so a `Drop` for them would subtract them twice and the stage would
    # stop reconciling. The keystone invariant wants the abstain rate as a number, not silence.
    uncertain_band: int = 0
    # D-246: titles carrying SOME seniority signal while the gate was inert
    # (`target_seniority_band: any`). The gate short-circuits before parsing there, so the two
    # counters above are structurally 0 and 'inert' is otherwise indistinguishable from
    # 'nothing to gate'. Reported, not dropped, for the same reason as `uncertain_band`.
    band_tokens_seen_while_inert: int = 0
    # B5 — run-scoped twins of four of the buckets above, restricted to postings THIS run
    # judged (`eligible`/`uncertain`, run_id-attributed). Diagnostics for the zero-output guard,
    # surfaced additively in the funnel (no `artifact_version` bump, D-285 precedent) and
    # deliberately NOT part of the `considered == Σ drops` identity above.
    judged_this_run: int = 0
    handled_this_run: int = 0
    applied_this_run: int = 0
    duplicate_this_run: int = 0
    dead_this_run: int = 0


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

    `location_filter_mode` is the one setting reported in PLAIN TEXT as well as inside
    `config_hash` (D-323). It is not a second hash and it is not redundant: it is what makes
    each lead's `location_class` readable. `soft` means the hard US gate never ran, so a
    `non_us` lead is the documented behaviour rather than a leak; `hard` means the run claims
    every lead is `us` or `unknown`. Without it a reader has a column of verdicts and no way to
    know which claim the run was making — and re-deriving the mode from `config_hash` is not
    possible, that being what a hash is for.
    """

    code_fingerprint: str
    config_hash: str
    profile_facts_hash: str | None
    profile_row_hash: str | None
    rules_hash: str | None
    status: str
    location_filter_mode: str


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


@dataclass(frozen=True)
class LivenessCheck:
    """P6 item 6: what the re-fetch found about the shortlist, reported every run.

    `checked is None` means the shortlist was NOT probed — no prober was supplied — and is
    deliberately distinct from `checked=0` (probed an empty shortlist) and from `dead=0` (probed
    and everything was live). Reporting an unprobed run as "0 dead" would assert a measurement
    nobody took, which is the D-022/D-023 rule this artifact applies everywhere else.

    `unknown` is reported next to `dead` rather than folded into `alive`, because it is the
    number that says how much of the check is actually working: a run where every posting came
    back `unknown` has a fail-open probe telling you nothing, and looks identical to a healthy
    run if you only read `dead`.

    `gone_after_redirect` is a **subset of `unknown`**, not a fourth partition member — `alive`
    still subtracts only `dead` and `unknown`. It is emitted because it is the one bucket that
    can disarm the check without any other number moving: if an ATS begins fronting expired
    requisitions with `301 → 404`, every genuine gone posting is forgiven, `dead` sits at 0
    forever, and the run looks exactly like one where every probe timed out.
    """

    checked: int | None
    dead: int | None
    unknown: int | None
    gone_after_redirect: int | None = None

    @property
    def instrumented(self) -> bool:
        return self.checked is not None

    @property
    def alive(self) -> int | None:
        if self.checked is None or self.dead is None or self.unknown is None:
            return None
        return self.checked - self.dead - self.unknown


@dataclass(frozen=True)
class DeathProbeReport:
    """D-325: what the measured-death sweep did to the postings the scanner cannot reach.

    A SEPARATE section from `liveness`, not more keys inside it, because it is a different
    measurement over a different population with a different consequence. `liveness` probes the
    SHORTLIST and writes nothing; this probes open postings under `companies.watched = 0` and
    CLOSES the ones proven gone twice. Sharing a block would invite a reader to add `checked`
    and `attempted` into one probe count, which would be two questions summed.

    Every bucket here exists because its absence would let the sweep fail silently:

    - `due` is the denominator — how many rows the TTL admitted this run. Without it `attempted`
      alone cannot distinguish a healthy sweep from a budget of zero.
    - `budget_refused` is `due - attempted`. A sweep that refuses work must read as refused
      work, never as a clean corpus.
    - `unprobeable` is due rows with no URL. This mechanism can never reach them by any future
      refinement, so they are reported rather than filtered away.
    - `unknown` counts every non-closing outcome, `refetch_gone_after_redirect` included. It is
      the bucket that can disarm the check with no other number moving.
    - `strikes_cleared` is the drain firing. Zero forever alongside a rising `gone` means the
      only path out of the strike counter has stopped working.

    Plain ints, never `None`: the whole object is `None` when the sweep did not run, so an
    unmeasured run is stated once at the section rather than nine times inside it.
    """

    due: int
    unprobeable: int
    attempted: int
    budget_refused: int
    gone: int
    unknown: int
    alive: int
    closed: int
    strikes_cleared: int


def death_probe_to_dict(report: DeathProbeReport | None) -> dict[str, object]:
    """The `death_probe` block. `instrumented: false` and nulls when the sweep did not run —
    never a block of zeros, which would claim a measurement nobody took (D-022/D-023)."""
    if report is None:
        return {
            "instrumented": False,
            "due": None,
            "unprobeable": None,
            "attempted": None,
            "budget_refused": None,
            "gone": None,
            "unknown": None,
            "alive": None,
            "closed": None,
            "strikes_cleared": None,
        }
    return {
        "instrumented": True,
        "due": report.due,
        "unprobeable": report.unprobeable,
        "attempted": report.attempted,
        "budget_refused": report.budget_refused,
        "gone": report.gone,
        "unknown": report.unknown,
        "alive": report.alive,
        "closed": report.closed,
        "strikes_cleared": report.strikes_cleared,
    }


# The closed catalog of Tier-B rewrite outcomes. `drop_reason` is an untyped string at the
# raise site (`tailor/rewrite/lane.py`), so it is mapped here into named buckets; anything the
# catalog does not name lands in `other`, which is a FAILURE signal (CLAUDE.md: out-of-catalog
# is never a new bucket), not silently discarded.
_FILTER_PREFIX = "filter:"

# `passes_overmatch_filter` (tailor/rewrite/filter.py) emits these three STRUCTURAL rejects
# (empty output, multi-line output, output too long against the source) alongside its
# fabrication catches (invented_entity, invented_skill, added_number). A structural reject is
# not a fabrication and must not inflate B4's `rejected` numerator — see
# `filter_structural_rejected` below.
_STRUCTURAL_FILTER_REASONS = frozenset({"empty", "not_single_line", "too_long"})


@dataclass(frozen=True)
class FabricationCounters:
    """P0 item 8 / bar metric B4: the fabrication gate's per-lane tally.

    Tier B is the LLM-assisted lane, the only one that can fabricate — Tier A is structural and
    cannot. `judge_rejected` and `overmatch_filtered` are the two truth gates: the fail-closed
    entailment judge and the deterministic overmatch filter. `budget`/`error`/`no_candidate`/
    `lane_dead` are non-fabrication fallbacks. `other` counts any `drop_reason` the closed
    catalog does not name and is a defect if non-zero.

    `lane_dead` (P3 slice 5, D-146) counts bullets dropped because the LLM credential was
    already dead for the rest of the invocation — no call was made for most of them, so it is
    the one fallback that is not evidence about the bullet at all. Counted apart from `error`
    for exactly that reason: `error` means the provider failed on THIS bullet and the next may
    succeed, `lane_dead` means nothing further was attempted.

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

    `filter_structural_rejected` (P4 checkpoint fix) counts the three STRUCTURAL rejects the
    pre-judge overmatch filter also emits (`filter:empty`, `filter:not_single_line`,
    `filter:too_long`) — an empty/multi-line/too-long candidate is a structural malformation,
    not a fabrication, so unlike its sibling reasons under `_FILTER_PREFIX` it is EXCLUDED
    from `overmatch_filtered` and therefore from `rejected` below.
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
    lane_dead: int
    provenance_rejected: int
    lift_rejected: int
    banned_register_rejected: int
    buzzword_rejected: int
    verb_diversity_rejected: int
    requirement_echo_rejected: int
    filter_structural_rejected: int
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
    filter_structural = lane_dead = 0
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
            if reason[len(_FILTER_PREFIX) :] in _STRUCTURAL_FILTER_REASONS:
                filter_structural += 1
            else:
                overmatch += 1
        elif reason == "budget":
            budget += 1
        elif reason == "error":
            error += 1
        elif reason == "no_candidate":
            no_candidate += 1
        elif reason == "lane_dead":
            lane_dead += 1
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
        lane_dead=lane_dead,
        provenance_rejected=provenance,
        lift_rejected=lift,
        banned_register_rejected=banned_register,
        buzzword_rejected=buzzword,
        verb_diversity_rejected=verb_diversity,
        requirement_echo_rejected=requirement_echo,
        filter_structural_rejected=filter_structural,
        other=other,
    )


@dataclass(frozen=True)
class ProjectionCounters:
    """P5a: the per-lead projection tally, in the shape the `projection` stage needs.

    `drops` names ONLY the outcomes that actually occurred — one `Drop` per non-`PROJECTED`
    member the pipeline counted, and nothing at all for a member nothing reached. That is the
    same absent-versus-zero rule the rest of this module applies (D-023), and it is the reason
    this fold exists instead of the stage reading the counter directly.
    """

    projected: int
    drops: tuple[Drop, ...]


def build_projection_counters(
    outcomes: Mapping[ProjectionLeadOutcome, int],
) -> ProjectionCounters:
    """Fold the per-lead outcome counter into (advanced, drops). Pure.

    **ITERATES the counter; never indexes it.** `summary.projection_outcomes` is a `Counter`, so
    `outcomes[SOME_OUTCOME]` returns 0 for a member nothing reached — walking
    `ProjectionLeadOutcome` and indexing would therefore emit a drop of 0 for every outcome that
    never occurred, and the distinction between "no lead hit this" and "this bucket is empty"
    would be gone with no test failing. `in` and `.items()` only.

    The catalog is closed by the key TYPE, not by an enumeration here, so there is no `other`
    bucket to fall into: `pipeline/runner._projection_scope` routes every projection failure
    through the two classifiers, both of which raise on a cause their catalog does not name, so an
    out-of-catalog outcome cannot reach this fold at all. Contrast `build_fabrication_counters`,
    whose input is an untyped `drop_reason` string and which therefore needs one.

    Drops are sorted by reason so two runs with the same outcomes render the same artifact — a
    `Counter` iterates in first-increment order, which is whichever lead happened to fail first.
    """
    projected = 0
    drops: list[Drop] = []
    for outcome, count in outcomes.items():
        if outcome is ProjectionLeadOutcome.PROJECTED:
            projected = count
        else:
            drops.append(Drop(reason=outcome.value, count=count))
    return ProjectionCounters(
        projected=projected, drops=tuple(sorted(drops, key=lambda drop: drop.reason))
    )


@dataclass(frozen=True)
class CoverageSummary:
    """P4 item 6: this run's keyword-coverage roll-up across leads. A REPORT, never a gate.

    `leads_measured` is how many leads produced a coverage report at all; `leads_with_fraction`
    is the subset whose JD named at least one recognized requirement term (a JD with none has
    `fraction is None`, and averaging that in would be dividing by an undefined denominator).
    `mean`/`median` are `None` — never 0.0 — when no lead has a fraction, for the same reason a
    single lead's fraction is: 0.0 asserts "covers none of many requirements", not "nothing to
    measure". `top_missing` names the requirement terms most leads lacked, most-frequent first.
    """

    leads_measured: int
    leads_with_fraction: int
    mean_fraction: float | None
    median_fraction: float | None
    top_missing: tuple[tuple[str, int], ...]


def build_coverage_summary(
    coverages: Sequence[CoverageReport | None],
) -> CoverageSummary:
    """Fold per-lead coverage reports into a run-level summary. Pure; mirrors
    `build_fabrication_counters`. A 0-lead run (or one where every measurement was unavailable)
    fabricates nothing: zero leads measured, `None` averages, no missing terms."""
    measured = [c for c in coverages if c is not None]
    fractions = [c.fraction for c in measured if c.fraction is not None]
    missing: Counter[str] = Counter()
    for report in measured:
        missing.update(report.missing)
    top_missing = tuple(
        sorted(missing.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_MISSING]
    )
    return CoverageSummary(
        leads_measured=len(measured),
        leads_with_fraction=len(fractions),
        mean_fraction=sum(fractions) / len(fractions) if fractions else None,
        median_fraction=statistics.median(fractions) if fractions else None,
        top_missing=top_missing,
    )


@dataclass(frozen=True)
class LaneReport:
    """What one JD-acquisition lane did this run (spec §4.4, §4.6).

    Deliberately NOT a funnel stage, for the same reason `ScanContext` is not: a lane ADDS to the
    corpus, so its attempts do not enter at any stage's `entered` and cannot be reconciled
    against one. Chaining it into the funnel would be arithmetic that is wrong on every run.

    `counts` carries all ten `AcquisitionOutcome` keys, always, because `AcquisitionTally`
    instruments all ten: a 0 here is a MEASURED zero. Dropping the empty ones would turn it back
    into an absence, which is the confusion that hid the prior art's browser tier for 11 runs.

    `is_silent_outage` is carried rather than left to the reader to derive. It is deliberately
    not `resolved == 0`: a lane with nothing to do is not an outage, and reporting one would
    train the reader to ignore the signal on the day it means something.

    `admitted` and `refused` are the two sides of the per-run company cap, as the
    `(provider, slug)` pairs the store keys a company on. Refusals are IDENTIFIED and not merely
    counted — a company dropped silently is indistinguishable from one the lane never saw, and
    that difference is the whole diagnostic value. `admitted` holds only companies the store did
    NOT already have, so its length is the reach this run ADDED rather than the companies the
    lane touched; a lane that spent its whole cap on companies already stored would otherwise
    report a full admission list and no new reach at all.
    """

    name: str
    counts: Mapping[str, int]
    attempted: int
    resolved: int
    is_silent_outage: bool
    admitted: tuple[tuple[str, str], ...]
    refused: tuple[tuple[str, str], ...]


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
    liveness: LivenessCheck
    fabrication: FabricationCounters
    coverage: CoverageSummary
    abstain: AbstainReport
    unattributed_evaluations: int
    errors: tuple[str, ...] = ()
    fatal: str | None = None
    # D-274. `None` means the coverage load FAILED, not that coverage is zero — a run whose
    # boards were all unreadable still produces a real report (every board `unscanned`,
    # `global_ratio` None), so the two cases stay distinguishable.
    board_coverage: BoardCoverageReport | None = None
    # One entry per lane that RETURNED a result this run. Empty means no lane ran — the default,
    # since `settings.lanes_enabled` ships `()`. A lane that raised is absent from here and
    # present in `errors`, which is the honest pair: it produced no counts to report.
    lanes: tuple[LaneReport, ...] = ()
    # D-325. `None` means the measured-death sweep did NOT run this run — no prober was
    # supplied — which is not the same as a sweep that found nothing. A block of zeros would
    # claim a measurement nobody took, the same rule `LivenessCheck` applies above.
    death_probe: DeathProbeReport | None = None

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
    # Omitted means UNMEASURED, never "0 dead" — a caller that forgets gets the honest report
    # rather than a clean liveness result it never took.
    liveness: LivenessCheck | None = None,
    # P5a. `None` means `--project` was NOT passed, so there is no `projection` stage at all —
    # not a stage of zeros, which would claim projection ran and dropped nothing. The caller
    # decides this from `summary.projection_availability is None`, never from the counter being
    # empty: a projected run legitimately has an empty counter (the preflight refused, or every
    # shortlisted lead was withheld as gone).
    projection: ProjectionCounters | None = None,
    # Read from the store, and only meaningful alongside `projection`. Compared against the LEADS
    # rather than against the projection stage's `advanced` — see the cross-check's note below.
    projected_lineage_rows: int = 0,
    rewrite_rows: Sequence[dict[str, object]],
    unattributed_evaluations: int,
    abstain: AbstainReport,
    coverages: Sequence[CoverageReport | None] = (),
    # D-274, and NOT built here: the caller loads it once and hands the same object to the
    # morning artifact too. `held` is a live count with no run dimension, so two loads
    # seconds apart can disagree, and one run's two artifacts must not.
    board_coverage: BoardCoverageReport | None = None,
    # D7. One entry per lane that returned a result; `()` is the default and means no lane ran,
    # which is what every run emits until `settings.lanes_enabled` names one. Unlike
    # `projection` there is no omission hazard to guard against here: a lane report cannot
    # change what any stage claims, so an omitted list and a genuinely empty one describe the
    # same artifact.
    lanes: Sequence[LaneReport] = (),
    # D-325. Omitted means the sweep did not run and the section reports itself UNMEASURED,
    # never zero — the same omission direction as `liveness` above.
    death_probe: DeathProbeReport | None = None,
    errors: Sequence[str] = (),
    fatal: str | None = None,
) -> RunFunnel:
    """Assemble the funnel from counts. Pure: no engine, no clock, no filesystem."""
    # Normalized once, before the stages: the tailor stage needs `dead` to account for the leads
    # liveness withheld, and an unprobed run must contribute 0 there rather than crash on None.
    liveness = liveness or LivenessCheck(checked=None, dead=None, unknown=None)
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
                        "excluded title; ALSO a non-US location, or a non-US job-ad "
                        "convention on the title, when location_filter_mode is `hard` "
                        "(not the default). Drain with `top --include-hard-filter`, which "
                        "names the clause and the text that vetoed each row"
                    ),
                ),
                Drop(reason="hidden_non_swe", count=shortlist.hidden_non_swe,
                     note="title role gate"),
                Drop(
                    reason="zero_signal_uncertain",
                    count=shortlist.hidden_zero_signal,
                    note=(
                        "role unrecognised and the job description yielded no recognised "
                        "requirement terms, so there is nothing to tailor to; drain with "
                        "`top --include-zero-signal`"
                    ),
                ),
                Drop(
                    reason="hidden_over_seniority",
                    count=shortlist.hidden_over_seniority,
                    note=(
                        "title seniority above target band; "
                        "drain with `top --include-over-seniority`"
                    ),
                ),
                Drop(reason="hidden_ineligible", count=shortlist.hidden_ineligible),
                Drop(
                    reason="hidden_duplicate",
                    count=shortlist.hidden_duplicate,
                    note="provable exact_quad duplicate; drain with `top --include-duplicates`",
                ),
                Drop(
                    reason="hidden_applied",
                    count=shortlist.hidden_applied,
                    note=(
                        "the job already carries a submitted application; drain with "
                        "`top --include-applied`, or release it with "
                        "`track status <id> withdrawn`"
                    ),
                ),
                Drop(
                    reason="hidden_handled",
                    count=shortlist.hidden_handled,
                    note=(
                        "a live ledger disposition: already built, already refused, or surfaced "
                        "inside its seen TTL; drain with `top --include-handled` or "
                        "`ledger reopen`"
                    ),
                ),
                Drop(
                    reason="capped_by_top_n",
                    count=shortlist.hidden_below_cutoff,
                    note="cleared every filter and was beaten only by rank",
                ),
            ),
            # NOT derived. `entered` is the ranker's own row count, measured independently of
            # the drop counters above, so this identity can genuinely fail — it is the stage
            # P0 item 3 turned from bookkeeping into evidence, and it is what catches a new
            # bucket added to the ranker but not mirrored here.
            derived=False,
            # B5 — additive, diagnostic, NOT part of the identity above (see the field's own
            # docstring on `Stage`). `unexplained` can be non-zero on a healthy day: it counts
            # candidates that were DELIVERED, not just ones that were suppressed.
            run_scoped_attribution={
                "judged": shortlist.judged_this_run,
                "handled": shortlist.handled_this_run,
                "applied": shortlist.applied_this_run,
                "duplicate": shortlist.duplicate_this_run,
                "dead": shortlist.dead_this_run,
                "unexplained": (
                    shortlist.judged_this_run
                    - shortlist.handled_this_run
                    - shortlist.applied_this_run
                    - shortlist.duplicate_this_run
                    - shortlist.dead_this_run
                ),
            },
            note=(
                "The ranker's whole considered population. NOT a continuation of `verdict` — "
                "the two count different populations, so the numbers here will not match it. "
                "Every exit is counted where the posting actually leaves. "
                "REPORTED HERE AND NOT AS DROPS, because both count postings that PASSED and "
                "are therefore already inside `advanced` — a `Drop` would subtract them a "
                "second time and this stage would stop reconciling: "
                f"`uncertain_band`: {shortlist.uncertain_band} (the seniority gate met a level "
                "token it could not resolve — no scheme bound for the company, or a rung "
                "outside the bound one — and passed the posting through); "
                f"`band_tokens_seen_while_inert`: "
                f"{shortlist.band_tokens_seen_while_inert} (titles carrying a seniority signal "
                "while the gate was off, i.e. `target_seniority_band: any`); "
                f"`signal_unmeasured`: {shortlist.signal_unmeasured} (titles with no role "
                "signal whose body the zero-signal rule could not read — no extraction row at "
                "the current taxonomy version, or a JD body that was empty — so it declined to "
                "fire and passed the posting through unfiltered). A non-zero value here is the "
                "ONLY thing in this artifact that tells `zero_signal_uncertain: 0` apart from a "
                "gate that never got the input it reads."
            ),
        )

    # The leads liveness withheld. ONE object, used by whichever stage is the ranker's successor:
    # the `tailor` stage on an authored run, the `projection` stage on a projected one. It has to
    # move with the chain — the withheld leads left the funnel between the shortlist and whatever
    # came next, and a bucket that belongs to no stage is a lead counted in none.
    withheld_drop = Drop(
        reason="withheld_not_live",
        count=liveness.dead or 0,
        note=(
            "re-fetched immediately before the render and answered 404/410, so it "
            "never entered the tailor loop (P6 item 6). NOT a render failure — a "
            "third terminal state, which is why it is its own bucket"
        ),
    )
    # P5a — present only on a `--project` run, and NOT INSTRUMENTED when the ranker never ran, for
    # the same reason the shortlist and tailor stages are: the preflight refuses before ranking, so
    # how many leads projection would have attempted is unknown rather than zero.
    projection_stage: Stage | None = None
    if projection is not None:
        projection_stage = Stage(
            name="projection",
            entered=None if shortlist is None else shortlist.shortlisted,
            advanced=None if shortlist is None else projection.projected,
            drops=() if shortlist is None else (withheld_drop, *projection.drops),
            # NOT derived. Every drop is counted where the lead actually leaves — one increment at
            # the raise site inside the loop — so this identity can genuinely fail, and it is what
            # catches a projection exit added without a counter. Do not let arithmetic masquerade
            # as verification: no bucket here is the remainder of the others.
            derived=False,
            note=(
                "NOT INSTRUMENTED. `--project` was passed but the ranker never ran, so how many "
                "leads projection would have attempted is unknown and is reported as unmeasured "
                "rather than as zero. **Why** is whatever the FATAL line above says — this stage "
                "cannot know which cause fired."
                if shortlist is None
                else "Every SHORTLISTED lead, and what the bundle's projection made of it. "
                "Entered at the ranker's shortlist rather than at the leads projection actually "
                "attempted, so the leads liveness withheld keep a named bucket here instead of "
                "vanishing between two stages — nothing projected them, and they are not "
                "projection failures either. Every other drop is named by the "
                "`ProjectionLeadOutcome` the pipeline counted for ONE lead, and an outcome no "
                "lead reached is ABSENT rather than reported as 0. `not_attempted` is the one "
                "bucket that names no cause: a RUN-scoped fault stopped the stage, and those "
                "leads never got a turn — the cause is on the FATAL line, once, for the run. "
                "None of them is a tailor "
                "failure: the tailor stage never ran for these leads, and folding them into "
                "`tailor_failed` would both make that count a lie and hide the loss under a "
                "reason naming the wrong stage."
            ),
        )

    stages = (
        Stage(
            name="dedup",
            entered=None,
            advanced=None,
            note=(
                "NOT INSTRUMENTED. Grouping HAS run — this note asserted the opposite until "
                "2026-08-19, when the store contradicted it (89 grouping events, 70 jobs "
                "carrying more than one posting), so it no longer claims 1:1. What is still "
                "true is that this stage counts nothing: duplicate leakage over a window is "
                "owned by P6 and unmeasured. Reported as unmeasured rather than as zero "
                "duplicates, which is the opposite claim."
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
        *(() if projection_stage is None else (projection_stage,)),
        Stage(
            name="tailor",
            # On a projected run this enters at what PROJECTION advanced, not at the ranker's
            # shortlist: the withheld and projection-dropped leads never reached the tailor loop,
            # and they are accounted for in the stage above. Read off `projection_stage.advanced`
            # rather than recomputed, so the two can never drift apart.
            #
            # None, not 0, for the same reason as the shortlist stage above: if the ranker never
            # ran, how many leads it would have handed over is unknown rather than zero.
            entered=(
                (None if shortlist is None else shortlist.shortlisted)
                if projection_stage is None
                else projection_stage.advanced
            ),
            advanced=tailored,
            drops=(
                Drop(reason="tailor_failed", count=tailor_failed),
                # Only when there is no projection stage to hold it. Keeping it here as well would
                # subtract the withheld leads twice and report a healthy run as unbalanced.
                *(() if projection_stage is not None else (withheld_drop,)),
            ),
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
                "artifacts.uri is the .tex path either way, so a row count would not do"
            ),
        ),
        # P5a. Absent on an authored run — there, 0 lineage-bearing rows is correct and comparing
        # it against the leads would fail every time.
        *(
            ()
            if projection is None
            else (
                CrossCheck(
                    name="projected_leads",
                    in_memory=tailored,
                    from_store=projected_lineage_rows,
                    note=(
                        "pipeline's leads vs resume_tailored rows carrying projection lineage "
                        "(meta_json '$.projection_kind'). Counted against the LEADS, not against "
                        "the projection stage's `advanced`: `advanced` counts leads whose "
                        "projection succeeded, and one of those can still fail the résumé gate "
                        "afterwards — which writes no artifact row at all, so `advanced` is this "
                        "plus `tailor_failed`. A disagreement means a lead on a projected run was "
                        "rendered from something other than the projection, or the lineage stopped "
                        "being recorded — neither of which the `tailored` row count above can see"
                    ),
                ),
            )
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
        liveness=liveness,
        fabrication=build_fabrication_counters(rewrite_rows),
        coverage=build_coverage_summary(coverages),
        abstain=abstain,
        unattributed_evaluations=unattributed_evaluations,
        errors=tuple(errors),
        fatal=fatal,
        board_coverage=board_coverage,
        lanes=tuple(lanes),
        death_probe=death_probe,
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
        "run_scoped_attribution": stage.run_scoped_attribution,
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
            "location_filter_mode": funnel.manifest.location_filter_mode,
        },
        "liveness": {
            # All None when the shortlist was not probed. `instrumented` is emitted so a reader
            # never has to infer "unmeasured" from a null, the same way each stage does.
            "instrumented": funnel.liveness.instrumented,
            "checked": funnel.liveness.checked,
            "dead": funnel.liveness.dead,
            "unknown": funnel.liveness.unknown,
            "alive": funnel.liveness.alive,
            # A subset of `unknown`; do not add it to the others when reconciling.
            "gone_after_redirect": funnel.liveness.gone_after_redirect,
        },
        # D-325. Its own section, NOT more keys under `liveness`: different population, and this
        # one WRITES. Summing the two probe counts would be summing two questions.
        "death_probe": death_probe_to_dict(funnel.death_probe),
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
            "lane_dead": funnel.fabrication.lane_dead,
            "provenance_rejected": funnel.fabrication.provenance_rejected,
            "lift_rejected": funnel.fabrication.lift_rejected,
            "banned_register_rejected": funnel.fabrication.banned_register_rejected,
            "buzzword_rejected": funnel.fabrication.buzzword_rejected,
            "verb_diversity_rejected": funnel.fabrication.verb_diversity_rejected,
            "requirement_echo_rejected": funnel.fabrication.requirement_echo_rejected,
            "filter_structural_rejected": funnel.fabrication.filter_structural_rejected,
            "other": funnel.fabrication.other,
            "rejected": funnel.fabrication.rejected,
        },
        "coverage": {
            "leads_measured": funnel.coverage.leads_measured,
            "leads_with_fraction": funnel.coverage.leads_with_fraction,
            # None, never 0.0, when no lead has a fraction — see CoverageSummary.
            "mean_fraction": funnel.coverage.mean_fraction,
            "median_fraction": funnel.coverage.median_fraction,
            "top_missing": [
                {"term": term, "count": count} for term, count in funnel.coverage.top_missing
            ],
        },
        "scan": {
            "ran": funnel.scan.ran,
            "boards_attempted": funnel.scan.boards_attempted,
            "boards_complete": funnel.scan.boards_complete,
            "boards_failed": funnel.scan.boards_failed,
            "postings_seen": funnel.scan.postings_seen,
        },
        # Board DISCOVERY coverage (D-274), deliberately adjacent to `scan` because it is
        # the denominator `scan` never had. Not to be read as the `coverage` key above,
        # which is resume keyword coverage.
        "board_coverage": board_coverage_to_dict(funnel.board_coverage),
        # D7 — the JD-acquisition lanes (§4). Beside `scan` and `board_coverage` because all
        # three answer "how much did this run reach", and this is the only one of the three
        # that can reach a company no provider can. Always present, `[]` when no lane ran: a
        # missing key would read as an older artifact rather than as a run with lanes off.
        "lanes": [
            {
                "name": lane.name,
                # All ten catalog keys, in catalog order, every time. A zero here is measured.
                "counts": dict(lane.counts),
                "attempted": lane.attempted,
                "resolved": lane.resolved,
                # attempted > 0 and resolved == 0 — a tier that tried and recovered nothing.
                # Not derivable as `resolved == 0`, which is also true of a lane with no work.
                "is_silent_outage": lane.is_silent_outage,
                # The per-run company cap, both sides, as `provider:slug`. `admitted` counts
                # only companies the store did not already hold, so it IS the reach added.
                "admitted": [f"{provider}:{slug}" for provider, slug in lane.admitted],
                "refused": [f"{provider}:{slug}" for provider, slug in lane.refused],
            }
            for lane in funnel.lanes
        ],
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
                # null, never []: a posting that names no place has not named an empty place
                # (D-323). Read `manifest.location_filter_mode` before reading `location_class`
                # — in `soft` mode the hard gate never ran.
                "locations": list(lead.locations) if lead.locations is not None else None,
                "location_class": lead.location_class,
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
                    # Its family is field-tier and does not apply to this profile's
                    # career_field, so zero rows is correct scoping, not a dead rule. Without
                    # this key such a rule reads as never_fired=false / abstain_rate=null and
                    # is indistinguishable from noise.
                    "not_applicable": rule.not_applicable,
                }
                for rule in funnel.abstain.rules
            ],
            "rule_count": len(funnel.abstain.rules),
            "never_fired": len(funnel.abstain.never_fired),
            "not_applicable": len(funnel.abstain.not_applicable),
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


def _lane_section(lanes: Sequence[LaneReport]) -> list[str]:
    """The `## Lanes` section, or nothing at all when no lane ran.

    Every one of the ten outcomes gets a row, including the zeros, because `AcquisitionTally`
    measured all ten — a table that listed only the non-zero rows would make an outcome that
    was measured at 0 indistinguishable from one that is not instrumented. `SILENT OUTAGE` is
    spelled out rather than left as a bool, because it is the line a reader is meant to act on.
    """
    if not lanes:
        return []
    lines = ["", "## Lanes", ""]
    for lane in lanes:
        outage = (
            " — **SILENT OUTAGE: attempted work, recovered no body**"
            if lane.is_silent_outage
            else ""
        )
        lines += [
            f"### {lane.name}",
            "",
            f"{lane.attempted} attempted · {lane.resolved} resolved · "
            f"{len(lane.admitted)} new companies admitted · "
            f"{len(lane.refused)} refused by the cap{outage}",
            "",
            "| outcome | count |",
            "|---|---:|",
        ]
        lines += [f"| {name} | {count} |" for name, count in lane.counts.items()]
        lines += [
            "",
            "*Companies already in the store are admitted free and appear in neither list — "
            "`admitted` is the reach this run ADDED, not the companies the lane touched.*",
            "",
            f"- **admitted:** {_lane_companies(lane.admitted)}",
            f"- **refused:** {_lane_companies(lane.refused)}",
        ]
    return lines


def _lane_companies(keys: Sequence[tuple[str, str]]) -> str:
    """`provider:slug`, in the order the lane presented them, or an explicit `none`."""
    return ", ".join(f"`{provider}:{slug}`" for provider, slug in keys) or "none"


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
        "into the same leads. A hash tied to the profile is `—` on a run with no profile. "
        "`location filter mode` is not a hash — it is already inside `config hash`, and is "
        "repeated in plain text because it is what makes each lead's `US gate` verdict "
        "readable: in `soft` the hard US gate never ran.*",
        "",
        "| field | value |",
        "|---|---|",
        f"| status | {m.status} |",
        f"| code fingerprint | {m.code_fingerprint} |",
        f"| config hash | {m.config_hash} |",
        f"| profile facts hash | {m.profile_facts_hash or '—'} |",
        f"| profile row hash | {m.profile_row_hash or '—'} |",
        f"| rules hash | {m.rules_hash or '—'} |",
        f"| location filter mode | {m.location_filter_mode} |",
        "",
        "*`config hash` covers the decision-relevant `Settings`; `profile row hash` covers the "
        "five profile columns the ranker reads (incl. `exclude_titles`) plus the two "
        "user-overridable catalogs that decide a drop bucket — `leveling.yaml` and "
        "`taxonomy.yaml`. Corpus membership is in neither: watching a board changes which "
        "postings exist without moving any hash here.*",
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

    # The denominator the section above never had: how much of each board we can actually
    # see. Rendered here rather than at the end because a reader who has just been told
    # 14,238 postings were listed needs "out of how many" in the same breath.
    lines += ["", "## Board coverage", ""]
    lines += board_coverage_headline(funnel.board_coverage)
    lines += board_coverage_table(funnel.board_coverage)

    # Rendered only when a lane ran. The JSON half always carries `lanes` (as `[]`), which is
    # what a machine reader needs to tell "lanes off" from "older artifact"; a human reading a
    # run with every lane off is better served by the section being absent than by a heading
    # over a sentence saying nothing happened.
    lines += _lane_section(funnel.lanes)

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
            # D-268's rule, applied where the claim is made: a ratio records its MATCH RULE and
            # its CORPUS SIZE beside it, or only the numerator is quotable later. "no lead is
            # non-US" is worth nothing without both, and the retracted metric this replaces was
            # a grep that returned the same number whether the French city was there or not.
            f"*`location` is what the posting itself named — `—` where it named nothing, which "
            f"is not the same as naming an empty place. `US gate` is "
            f"`rank/location_gate.classify_location` over exactly those strings, evaluated over "
            f"all {len(funnel.leads)} lead(s) in this table. It is a positive US allowlist, so "
            f"it drops only a CONFIRMED `non_us` and keeps `us` and `unknown` — and it only ran "
            f"at all if the manifest's location filter mode above reads `hard`.*",
            "",
            "| posting | title | company | location | US gate | source board | registry/user "
            "| PDF | folder |",
            "|---:|---|---|---|---|---|---|---|---|",
        ]
        for lead in funnel.leads:
            lines.append(
                f"| {lead.posting_id} | {lead.title} | {lead.company} | "
                f"{'; '.join(lead.locations) if lead.locations else '—'} | "
                f"{lead.location_class} | "
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
    not_applicable = funnel.abstain.not_applicable
    lines += [
        "",
        "## Per-rule abstain",
        "",
        # `not applicable` is counted here because it is in NEITHER of the other two buckets:
        # without it the census stops partitioning the catalog and the missing rules read as
        # an arithmetic error.
        f"{len(funnel.abstain.rules)} rules in the catalog · {len(never_fired)} never fired · "
        f"{len(not_applicable)} not applicable to this field · "
        f"{len(fully)} fire but never decide · {funnel.abstain.total_rows} requirement rows",
        "",
        "A rule that has never fired reports `never fired`, **not 0%** — a rate over zero rows "
        "is undefined, and 0% would rank it as the healthiest rule in the catalog.",
        "",
        "| rule | family | observed | met | unmet | abstained | rate |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for rule in funnel.abstain.rules:
        # FIRST, exactly as `eligibility abstain` orders it: a not-applicable rule has zero
        # rows, so every later branch either mislabels it or formats a None rate and raises.
        # Zero rows is not enforced, it is entailed by the report's scope: `evaluate` drops
        # skip families before detection, the counts are scoped to an identity whose hash
        # covers career_field, and LLM-lane rows carry rule_id=None. Widen that scope (a
        # run-scoped or historical abstain report) and a rule could be both not-applicable
        # and non-empty, landing in two census buckets and printing over a real rate.
        if rule.not_applicable:
            rate = "not applicable"
        elif rule.never_fired:
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

    live = funnel.liveness
    probe = funnel.death_probe
    stub = funnel.stub_rate
    stub_rate = "not instrumented (empty corpus)" if stub.rate is None else f"{stub.rate:.2%}"
    fab = funnel.fabrication
    lines += [
        "",
        "## Liveness",
        "",
        (
            "not instrumented — the shortlist was not re-fetched this run, which is NOT the "
            "same as no dead postings"
            if not live.instrumented
            else f"{live.checked} leads re-fetched · {live.dead} withheld as gone · "
            f"{live.unknown} unknown (served), of which "
            f"{live.gone_after_redirect if live.gone_after_redirect is not None else '—'} "
            "were gone-after-redirect"
        ),
        "",
        "*Liveness is never cached and never writes to the store: a `dead` result withholds the "
        "lead from this run only, and `postings.status` stays the scanner's. Only an explicit "
        "404/410 withholds, and only from the URL asked about; every other outcome — timeout, "
        "403, 5xx, no URL, and a 404 reached through a redirect — is served, because missing a "
        "real job costs more than one wasted résumé. A gone-after-redirect count that climbs "
        "while `withheld as gone` stays at 0 means the detector has been disarmed, not that the "
        "corpus is healthy.*",
        "",
        "## Death probe",
        "",
        (
            "not instrumented — the unreachable-by-the-scanner class was not swept this run, "
            "which is NOT the same as nothing having died"
            if probe is None
            else f"{probe.attempted} of {probe.due} due probed "
            f"({probe.budget_refused} refused by the budget, {probe.unprobeable} have no URL) "
            f"· {probe.gone} answered gone · {probe.unknown} unknown · {probe.alive} alive "
            f"· {probe.closed} closed · {probe.strikes_cleared} strike counters cleared"
        ),
        "",
        "*The only mechanism that can close a posting whose company is `watched = 0` — a lane "
        "re-acquires by SEARCH, so absence is never evidence for these rows and the board "
        "scanner never revisits them (D-314). Only a non-redirect 404/410 from the posting's "
        "own URL counts, and only twice in different runs, mirroring `CLOSE_AFTER_MISSES`. "
        "Sensitivity is LOW and measured: 4 of 60 postings the scanner had PROVED closed "
        "(6.7%, Wilson 95% CI 2.6%–15.9%), because a closed Workday requisition still answers "
        "200 (0 of 37). It returned 0 false deaths against 90 live postings. `closed` staying "
        "at 0 is the expected reading, not evidence the class is healthy.*",
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
        f"fallbacks: {fab.budget} budget · {fab.error} error · {fab.no_candidate} no_candidate "
        f"· {fab.lane_dead} lane_dead (the credential was dead; no call was made)",
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
        f"{fab.filter_structural_rejected} rewrites reverted to Tier-A for a structural "
        "malformation (empty, multi-line, or too-long candidate) caught by the pre-judge "
        "overmatch filter (a structural reject, not a caught fabrication — excluded from "
        "`rejected` above)",
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

    cov = funnel.coverage
    mean = "—" if cov.mean_fraction is None else f"{cov.mean_fraction:.0%}"
    median = "—" if cov.median_fraction is None else f"{cov.median_fraction:.0%}"
    lines += [
        "",
        "## Keyword coverage",
        "",
        f"{cov.leads_measured} lead(s) measured · {cov.leads_with_fraction} with a JD naming "
        f"recognized requirement terms · mean coverage {mean} · median {median}",
        "",
        "*Of the requirement terms a JD asks for, how many the MASTER résumé genuinely has — a "
        "REPORT, never a veto: it changes no kept/dropped/degraded decision. The numerator is "
        "the authored résumé's real skills, never the tailored output, so a term a tailored "
        "bullet merely echoes still reads as missing. Mean/median are `—`, not 0%, when no lead "
        "had a JD with recognized requirements.*",
        "",
    ]
    if cov.top_missing:
        lines.append("Most-frequently missing requirement terms:")
        lines.append("")
        lines += [f"- **{term}**: missing from {count} lead(s)" for term, count in cov.top_missing]
    else:
        lines.append("No requirement terms were missing across the measured leads.")

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
    "BoardCoverageReport",
    "CoverageSummary",
    "CrossCheck",
    "DeathProbeReport",
    "Drop",
    "FabricationCounters",
    "Lead",
    "LivenessCheck",
    "ProjectionCounters",
    "RunFunnel",
    "RunManifest",
    "ScanContext",
    "ShortlistCounts",
    "SourceTotal",
    "Stage",
    "StubRate",
    "WrittenArtifact",
    "build_coverage_summary",
    "build_fabrication_counters",
    "build_projection_counters",
    "build_run_funnel",
    "death_probe_to_dict",
    "funnel_to_dict",
    "funnel_to_markdown",
    "write_run_funnel",
]
