# PROGRAM STATE — read this first

**Last updated:** 2026-08-08 (overnight autonomous run — **P4 items 6 AND 7 both SHIPPED to `main`**:
item 6 keyword-coverage `58f032e`/D-061, item 7 persona-registry+de-senioritizer `1988c39`/D-063; both
diff-reviewed + deepseek-reviewed, `make check` green (3148 passed / 95.23%). **P4 BUILD IS COMPLETE**
(items 1–7); only Gate P4's blind-craft review remains, which is Mit's. **P5a SHIPPED** (`faf8aa9`, D-064,
diff- + deepseek-reviewed, `make check` green 3525 passed / 95.17%): three verdict-SAFE eligibility-integrity
slices (INELIGIBLE-span property gate; out-of-catalog family/disposition FAILURE surfacing; LLM cache keyed
on profile+catalog identity). **P5b B0 label-INDEPENDENT scaffolding SHIPPED (D-065):** the Gate-P5
precision scorer + reference all-blocker policy (`eligibility/scoring.py`) + a stratified 173-row local
labeling worksheet — no verdict-changing rule shipped. The verdict-changing rules (B1–B4) stay gated on
Mit's human-verified labeled set; design ready at `.superpowers/sdd/p5-eligibility-decides/design-p5b.md`.
Prior context holds: Increment 1 D-060; Mit's résumé renders 1pp; the 3 over-220-char bullets remain Mit's
deferred content fix.)
**P5b answer-key oracle judge — SHIPPED to `main` (D-068, 2026-08-08; design D-067).** All 7 tasks merged
(`cdaafab..d322e75`), built via subagent-driven development (TDD, a review after each task) + a whole-branch
opus review = **SHIP-AS-IS**; `make check` green (3584 passed). What shipped: `eligibility/oracle.py` (the
oracle judge — `resolve_provenance`/`accept_oracle_verdict` four-ANDed gate with fail-open downgrade,
`JUDGING_POLICY`, `build_label_request`/`apply_oracle_verdicts`), the mechanical audit drain in `scoring.py`
(`audited_coverage`/`meets_ship_gate`/`SHIP_AUDIT_COVERAGE_BAR=0.20`), the `eligibility label request/apply`
+ `score` CLI, the `eligibility-judge` skill, and the `PROGRAM.md` §3.P5 gate line. The two reserved
decisions (both made): **agent lane, no API key** (Claude Code judges via the skill) + **human audit
deferred** with a mechanical drain. **Next action: run the oracle over the 173-row worksheet** (Mit-local:
`boardwatch eligibility label request` → the `eligibility-judge` skill → `label apply`) → first Gate-P5
number via `boardwatch eligibility score`. B1–B4 stay blocked until the deferred human sample-audit lifts
audited coverage ≥ `SHIP_AUDIT_COVERAGE_BAR` (0.20). Non-blocking follow-ups recorded in D-068.
**Updated by:** boardwatch (Claude)
**Repo state at write time:** all nine P0 items (0-8), P1a (the résumé artifact integrity gate —
PROGRAM.md §3.P1 items 1, 2, 3, 3b, 4, 5), and P1b (item 3c, the Tier-B token-provenance validator, D-033)
are merged to `main` and pushed. **P1 is fully complete.** Verify with `git log --oneline -3` and
`git status` — if they disagree, the repo wins.
**This header carries no commit count or sha on purpose** — the previous one named both, went stale inside
a single session when three later docs commits did not update it, and a cold session following the
session-start ritual hit the disagreement on its very first check. State what is durably true; verify the
rest against `git log`. (D-017.)
**Gate:** `make check` exits **0** (2846 passed, 1 deselected, coverage 95.20%, `generalization: OK`),
measured in plain mode with the real exit code on `main` (P1a+P1b merged). Item 5 supplements
Gate P0; per D-031, Gate P0 is not re-anchored to `verify` exiting 0 — it was already MET on D-030's
evidence. Gate P1 was already MET on P1a's evidence (D-032); P1b (D-033) closes the one remaining P1 item
without changing that standing.

> This is the single file a fresh session with zero memory reads to know where the program stands.
> If it disagrees with the repo, **the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Full plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`.

---

## Current phase

**P0 — Instrumentation. COMPLETE (session 9).** All nine build items are shipped and merged to `main`.
**P1 — résumé artifact gate. FULLY COMPLETE + MERGED to `main` (session 10): P1a + P1b both shipped,
Gate P1 MET.** `make check` exits 0 on `main` (2846 passed, 1 deselected, coverage 95.20%,
`generalization: OK`). **Next: P2 — profile object + the keystone invariant** (PROGRAM.md §3.P2).

**P2 has been explored + decomposed (2026-08-07) — see `.superpowers/sdd/p2-profile-keystone/design.md`.**
Much of P2 was already built (INELIGIBLE spans, the 4-table evidence chain, and the severity *mechanism* all
exist). **Shipped this session (all merged, reviewed, `make check` green):**
- **item 2 — `needs_sponsorship` bit** (D-034): orthogonal bit on `WorkAuthFact`, sponsorship-rules only.
- **item 7 — `work_auth: blocker` by default** (D-035): the other five families stay `preference` (opt-in).
  **Gate P2 headline is now 2/3 met** — a fresh F-1/OPT profile → decisive INELIGIBLE-with-span on a
  no-sponsorship JD; a citizen → eligible on the same JD (proven by shipped-default `Policy()` tests). The
  3rd profile (non-SWE) needs item 4.
- **item 3 — keystone invariant machine-enforced**: `tests/unit/test_keystone_invariant.py` iterates the
  resolver registry and asserts every family × every pattern (all 33) abstains on empty `Facts()` — a new
  family/pattern that forgets to abstain now fails the gate. (Typed `AbstainReason` enum deferred — ~15
  call sites, no behaviour change; the property test is the enforcement.)
- **items 5 & 6 DONE**: INELIGIBLE carries a span (pre-existing offset locator); the ELIGIBLE evidence
  chain exists; and item 6's honesty gap is now closed (D-036) — a typed `VerdictPresentation` renders an
  eligible verdict as *cleared* (all rows met), *mixed* (non-met but non-blocking rows — never claims those
  cleared), or *no rule applied* (zero rows / residue). Presentation-only; verdict/engine unchanged.
- **item 4 (taxonomy) is the ONLY remaining P2 item — awaits Mit** (see below).

**P3 (unattended one-command runner) is now DECOMPOSED and building** —
`.superpowers/sdd/p3-unattended-runner/design.md`. Grounded exploration found the foundation exists (single
`fatal` discriminator, WAL already set, `run_id` plumbing, outage guard already reads the decision field);
net-new work clusters into 5 **fail-safe** slices:
- **(1) P3-contract — DONE (D-037, merged):** `docs/program/RUN_CONTRACT.md` writes the fatal-vs-non-fatal
  table (4 fatal conditions + crash path + non-fatal norm + lock-held + the running/NULL gap the reaper
  resolves), each row citing file:line; and the duplicated systemic-outage predicate is consolidated into
  `is_systemic_scan_outage(...)` (`scan/coordinator.py`), used by both call sites.
- **(2) P3-lock-liveness — the notify-loudly clause is DONE (D-043, this session); reclaim/reaper remain
  ⛔ UNSOUND, not built.** `scan/coordinator.py` now writes a message-only `scan.lock.meta` sidecar
  (pid/hostname/started_at) around the existing `FileLock` acquire/release; on contention the raised
  `ScanLockHeldError` names the blocking pid+host+started_at, falling back to the unchanged generic
  message if the sidecar is missing/malformed. The sidecar never governs acquire/release/reclaim —
  `filelock` remains the sole authority — so this is sound on its own even though the fuller design isn't.
  **Still deferred**, per `.superpowers/sdd/p3-unattended-runner/slice2-design.md`'s review: stale-reclaim
  by atomic rename, token-gated unlock, and the run reaper. Core error: `os.replace` arbitrates a
  *pathname* while `filelock` locks an *inode*, so the "atomic-rename reclaim" violates mutual exclusion
  (a reclaimer can steal a live lock; two reclaimers can both win). Also: reaper liveness is TOCTOU,
  standalone-lane age-reap is unsound, and `os.kill(pid,0)` is defeated by pid reuse. **Rethink direction:**
  likely DELETE the custom reclaim — a crashed holder's OS `flock` is already released on process exit, so
  a bare `filelock.acquire()` may reclaim it. Use (pid, start-time)/pidfd for liveness, not the pid alone.
  Make the reaper race-safe by gating on the run's lock being *acquirable now*, not an age floor.
  **DECIDED (D-045): stale-reclaim DECLINED** — unsound AND unnecessary (POSIX releases a dead holder's
  flock, so bare `FileLock.acquire()` already reclaims it; the cross-platform edge is item 8's, no Docker
  here). The loud-notify shipped (D-043). **The run REAPER (`running`+NULL rows) is DONE (D-046).** Age-based (no schema): a single atomic
  `UPDATE ... RETURNING id` marks `running`+NULL rows older than `reap_stale_after_hours` (24) `failed`;
  drains in `doctor` (guarded) and at `run` start (before the run's own row is minted). Sound because
  `finish_run` has no status precondition (false-reap self-corrects) and freshness treats `failed` as
  terminal (VERIFIED). Two reviews (deepseek design → fixed a real errors_json race; diff-reviewer impl →
  fixed unguarded doctor + pre-UPDATE-snapshot return via RETURNING). `make check` green (2948 passed,
  95.33%). Heartbeat-column reaper is the deferred correct alternative. **Slice 2 COMPLETE; with it, the
  last non-Mit / non-Docker P3 build item is closed.**
- **(3) P3-run-integrity — DONE (D-039, merged):** three run-integrity guards in `pipeline/runner.py`, all
  setting `summary.fatal` (fail-safe): cohort completeness (`visible` posting-id set == leads ∪ failed,
  ID-based); zero-output guard (0 leads is provably-right IFF scan healthy AND `eligible-judged-this-run`==0,
  run_id-attributed → no steady-state false alarm); filesystem-truth (run-scoped folder reconciliation,
  reused from slice 4). Read-only; both highest-risk properties mutation-verified by the reviewer.
- **(4) P3-output — DONE (D-038, merged):** `reports/morning.py` writes `morning-<run_id>.md/json` in the
  day folder (sibling of the funnel; apply URL · PDF path · honest verdict label · quoted span · one-line
  why per lead), fed by threading the ranker's verdict/why through the runner + a `postings.url` join +
  per-lead `load_audit`; and `pipeline/freshness.py` asserts a day's artifacts are from a terminal same-day
  run whose own lead folders reconcile (run-scoped). Read-only; verdict/engine unchanged. `doctor` wiring
  for freshness deliberately deferred.
- **(5) P3-llm-economics — REMAINING:** meta-hash idempotence + split LLM rate-limit classes (isolated to
  `llm/*` + `reports/tailor.py` + `tailor/rewrite/*`).
Cross-cutting highest-risk, REMAINING: the two-writer cross-OS WAL test (item 8) — a same-OS test proves
nothing; needs a real cross-process/cross-OS concurrent-writer harness.
**P3 status:** slices 1 (D-037), 3 (D-039), 4 (D-038) DONE + merged. Slice 2 is UNSOUND (rethink + Mit fork
above). **Slice 5 (LLM economics) + item 8 (cross-OS two-writer test) REMAIN** — each substantial and
design-heavy; recommend a fresh context window per slice (session-10's slice-2 unsound-design, slice-4
freshness-scope, and slice-3 predicate reworks were all caught by review — a sign these want sharp context).
All fail-safe, independent of P2 item 4. **Slice 5 (LLM economics) has been grounded + decomposed** —
`.superpowers/sdd/p3-unattended-runner/slice5-design.md`:
- **5a part 1 (retry-backoff) — DONE (D-040, merged):** `llm/retry.py` (`request_with_retry` + `LLMTransientError`)
  retries 429/5xx with exponential-jitter + Retry-After, INSIDE `complete()` (one budget unit per logical
  call), falling through to today's Tier-A containment on exhaustion. Isolated to `llm/*`; non-transient
  errors unchanged.
- **5a part 2 (idempotence short-circuit) — DECLINED (D-042), per YAGNI. NOT a remaining item.**
  Two designs (high-context + a fresh opus agent's) both failed deepseek review (2 blockers+4 majors, then
  3 more: Typst-binary-version not in key, racy insert-if-absent w/o a unique index, copied artifacts not
  hash-verified). Decisive value judgment: the existing `llm/cache.py` response cache ALREADY avoids
  re-paying the expensive LLM API calls on a resumable re-run (item 10's material goal); a tailor-level
  short-circuit only additionally saves a cheap Typst render and needs heavy correctness-hazardous machinery
  to be safe — over-engineering for its payoff (same disposition as P2 item 1). Revisit only with concrete
  evidence of a material render cost. (Separately logged in D-042: response-cache HITS may still consume the
  `_guarded` budget — a small real inefficiency for a future look.)
- **5b — DECIDED (D-044): DECLINE the "never-downgrade" inversion; keep today's Tier-A downgrade.** For an
  unattended driver, a solid deterministic Tier-A bullet on a provider/quota error is a GOOD shippable
  outcome (and the fail-safe table sanctions "drop tailoring, emit static"). No pending/resumable state, no
  cohort rework, no batched judging. Reversible — Mit can request the inversion if he wants Tier-B treated as
  load-bearing. NOT a remaining item.
Item 8: **doc half DONE (D-041, `docs/program/WAL_DISCIPLINE.md`)** — the WAL/busy_timeout/single-writer
stance is now documented. **Test half REMAINS:** a real cross-process/cross-OS concurrent-writer harness
(Docker-Linux-container + macOS-host-mounted-DB — same-OS proves nothing); test-infra-hard, fresh context.

**DECLINED (YAGNI):** item 1's facts `schema_version` — validated + hashed already hold; a schema-version
field is speculative hardening with unclear payoff (schema changes are rare and arrive with value changes
that already re-key `profile_hash`). Build it only if a concrete need appears.

**STILL AWAITS MIT (the one fail-dangerous decision left):** item 4 — the taxonomy shape:
a lightweight `applies_when.career_field` family gate + a `career.field` fact (recommended, minimal
multi-tenancy, unblocks the 3rd Gate-P2 profile) vs the full universal/profile/field 3-way split. Also open
(lower urgency): should any other family (esp. `clearance`) also default to `blocker`? Prior catalog WIP to
review first: `.agent/p2-catalog/` (a reviewed oracle `proto.py` + alternate rules snapshots).
**Remaining P2a (fail-safe, building autonomously):** item 3 keystone enforcement (a cross-resolver property
test "empty facts ⇒ every rule abstains" + a typed in-memory abstain reason — NOT a blanket wrapper, which
would break multi-input alternatives like `degree`; no DB migration), facts `schema_version`, guards.

**P1 was executed in two slices** (decomposed during P1 brainstorming, 2026-08-07):
- **P1a — artifact integrity gate** (items 1, 2, 3, 3b, 4, 5 of PROGRAM.md §3.P1): hard PDF gate,
  binary-missing-vs-compile-failure split, page-count hard fail (Typst-native `typst eval` query, SPIKED),
  degraded untailored-master fallback, per-lead compile-log capture, slot-filled assertion, typst
  Dockerfile+doctor packaging. **DONE — this slice MEETS Gate P1.** Design:
  `.superpowers/sdd/p1a-resume-artifact-gate/design.md`. Decisions: **D-032**.
- **P1b — Tier-B token-provenance validator** (item 3c): the LLM-lane truth gate feeding bar metric B4.
  **DONE (session 10, D-033).** A deterministic provenance allowlist (`reword_is_provenanced`,
  `tailor/rewrite/provenance.py`) — source-token / equivalence-image / claim-free structural connective
  ONLY, no stemmer, no modals/auxiliaries — vetoes any Tier-B reword with an unjustified content token
  before the judge runs, keeping the Tier-A bullet. New closed `drop_reason="provenance"` feeds a
  **separate** `provenance_rejected` counter, never folded into B4's fabrication numerator. Design:
  `.superpowers/sdd/p1b-tier-b-provenance/design.md`. Decisions: **D-033**. It gates nothing in Gate P1's
  own text (already MET on P1a's evidence) but is the item that makes P1 *fully* complete.

**Gate P1 is MET.** Deterministic tests pin every branch (binary-missing-fatal, compile-failure and
page-limit-exceeded → untailored fallback, both-unshippable → drop with no artifact and no folder, Tier-B
binary-missing re-raising fatal rather than degrading) — see D-032 for the full test list. Real-data
dogfood on 2026-08-07 (`METRICS.md` §"Session 9 — P1a dogfood") exercised **both** directions on the live
store: at the shipped default `resume_max_pages=1`, all 3 real shortlisted leads correctly hit the FATAL
every-lead-failed path (Mit's own authored `resume.yaml` compiles to 2 pages, confirmed independently
outside the app with `typst compile`/`typst eval`); on an isolated copy of the same store
(`--data-dir`, live DB never touched) with `resume_max_pages=2`, all 3 leads shipped a PDF at the correct
page count (confirmed two independent ways — `typst eval` and a raw PDF byte-scan), each with a
`typst-compile.log`, and `boardwatch verify` reconciled both runs through the DB-re-query path.
**Live, actionable finding, not a code defect:** Mit's real profile at its default page limit currently
drops every lead — see "Next action" below.

**Numbering note, because session 4 briefly got this wrong:** P0 has **nine** items, numbered **0-8** in
`PROGRAM.md` §3.P0. Item 0 was added later, by D-016. Always cite `PROGRAM.md`'s numbers — an earlier
version of this file invented its own and collided with them on the gate item.

**All nine are done:** item **0** (the pipeline-run row and `boardwatch run`), item **1** (the per-run
funnel artifact), item **2** (per-rule abstain rate), item **3** (the per-source outcome table *and* the
ranker's population accounting), item **4** (the run manifest), item **5** (the reconciliation sweep,
`boardwatch verify` — session 9), item **6** (the stub rate), item **7** (the `run_id` migration *and* the
threading that populates it), and item **8** (the fabrication counters).

**Item 5 does NOT change Gate P0's standing.** D-031: `boardwatch verify` is a **supplement, not a
re-anchor** — Gate P0 was already MET (session 8, D-030) on three consecutive real `boardwatch run --top 5`
runs, and its reconciliation clause is not re-expressed as "`verify` exits 0". `verify` adds an on-demand
DB-vs-disk guard (every run-keyed tailored artifact the DB records actually exists on disk) that the gate's
own evidence never had to exercise. Dogfooded on the real store, 2026-08-07: sweep checked runs 5, 6, 7, 9,
10, all reconcile, exit 0; `verify --run 8` (the one dangling run, no funnel artifact) correctly exits 1
with `NO_ARTIFACT` — unverifiable is never a silent PASS. `METRICS.md` §"Session 9" has the full record.

**Item 4 is now fully DONE (session 8, D-030).** Its exit-status half (`runs.status`) shipped in session
7; this session shipped the manifest itself as a section of the funnel artifact, with `ARTIFACT_VERSION`
bumped 2→3. Everything the spec line asked for was reused, not rebuilt, except the two genuinely-new
hashes:

| Manifest field | Shipped as |
|---|---|
| code fingerprint of decision-relevant modules | `engine_version()`'s AST digest (reused) |
| rule-catalog version | `rules_hash` — `{catalog_version, catalog_source, policy}` (reused, preferred over bare version) |
| profile version | `profile_facts_hash` (the eligibility `profile_hash`, reused) |
| start / end | already read into the funnel (reused) |
| exit status | `runs.status` (session 7) |
| config hash | **NEW** — over a closed classification of all 21 `Settings`+`LLMTier` fields; fails on drift |
| profile-row hash | **NEW** — over the five ranker columns incl. `exclude_titles`, closing the measured gap (D-030) |

**The `exclude_titles` gap is now closed, not merely documented.** `profile_row_hash` covers the five
profile columns the ranker reads. The one residual gap — the **skill-taxonomy version** — is named in the
artifact's own manifest note. Item 6 (stub rate) and item 8 (fabrication counters) shipped in the same
change; see `CHANGELOG.md` and D-030.

**Gate P0 is now MET — all three clauses.** `PROGRAM.md` §3.P0 gives the gate three clauses:

1. *Three consecutive runs reconciling to 100%.* **MET (session 8).** Three consecutive real
   `boardwatch run --top 5` invocations (no `--no-scan`, run_ids **5, 6, 7**) from a worktree pinned to
   `66291bf` — all RECONCILE, all exit 0, the scan stage exercised for the first time under the gate (135
   boards attempted each; the corpus GREW 20,803 → 22,114 → 23,455 as the scan discovered new postings).
   `METRICS.md` §"Session 8" has the full table. Caveat recorded there: these three produced artifact **v2**
   (the pinned worktree predates v3), which is fine — reconciliation is version-independent. No code change
   was needed, as expected.
2. *Why every non-lead was dropped, from the artifact alone.* **NOW MET** (session 6, item 3). The
   `shortlist` stage enters at the ranker's own considered population — **19,262**, against 3,301 measured
   in session 5 — and names all five of its exits. **15,959 postings that previously landed in no bucket
   at all are now attributed**, the largest being `hidden_hard_filter` at 11,517. The stage is also no longer
   `derived`, so its balance can genuinely fail; the artifact lists it beside `corpus` and `tailor` as a
   stage that could have caught a wrong number.
3. *Per-rule abstain for every rule in the catalog.* **MET.** All 44 emitted every run, never-fired ones
   included.

---

## What shipped in session 6 (2026-08-06)

**P0 item 3 — the per-source outcome table, and the ranker accounting that Gate P0 actually needed.**
`PROGRAM.md` §3.P0.3 specifies only the table. The gate clause it was supposed to close needed something
else as well, and shipping only the spec'd half would have left the clause open with no owner.

**Two findings changed what item 3 could honestly deliver, and both were measured before building:**

- **`assisted` is as unmeasurable as `unique`** (D-026). job-apps' own text defines it: a source that
  *"always arrives second gets credited nothing by naive attribution, which is how job-apps nearly cut a
  working adapter."* It is a dedup-attribution quantity. Postings here are 1:1 with jobs and each carries a
  single `company_id`, so there is no second source to credit. **Both columns report `None`** — 0 would
  assert that no source ever arrived second, reproducing the exact failure the column exists to prevent.
  Three of the five spec'd columns carry numbers; the other two are P6's to fill.
- **The spec'd table cannot close the gate clause.** A per-board `GROUP BY` of the verdict stage does not
  say why a non-lead was dropped. The ranker's two uncounted exits do. So item 3 shipped both halves.

### What the ranker was hiding

`rank_open_postings` reported two of its four exits. Hard-filter vetoes and everything below the `--top`
cutoff each `continue`d with no counter, so the `shortlist` stage entered at the *sum of its own outcomes*
— which silently excluded everything the ranker never reported.

> **15,959 of 19,262 open postings were in no bucket at all**, and the largest single drop in the entire
> funnel — `hidden_hard_filter`, **11,517 postings, 60% of the corpus** — had never been reported by any
> metric. Numbers in `METRICS.md`.

`entered` is now the ranker's own row count, measured independently of the drops, so the stage is **not
`derived`**: its balance can genuinely fail. The artifact lists it beside `corpus` and `tailor` as a stage
that could have caught a wrong number — the first addition to that list since it was created.

### The reviews found eight defects, and six were mine in an instructive way

**D-028 was written, cited D-023 as its authority, and then broke D-023's rule in the next file.** The
per-source `eligible` reconciliation grouped the very same subquery the verdict stage counts, by a NOT NULL
foreign key, joined on a primary key — so it agreed for **every possible database state**. The live
artifact rendered it as `| eligible | 18174 | 18174 | yes |`. It is deleted, not downgraded, exactly as
D-023 deleted the two `*_reconciles` properties.

> **"Counts through a different path" is not satisfied by grouping the same query differently.** A
> different path means a different table expression that can disagree, the way `no_current_evaluation` is
> its own `NOT IN` sweep.

**Making `shortlist` non-derived made a second bug worse.** On runs where the ranker never executes — a
fatal scan outage, a missing profile — it reported 0 in / 0 out. While `derived` that was harmless
bookkeeping; as evidence it became an affirmative claim that the ranker ran and accounted for everything.
`PipelineSummary.shortlist` is now `None` until the ranker runs.

**Then the falsified claim was found in a third and a fourth place.** Correcting D-028 and the `CHANGELOG`
left it rendered into **every funnel artifact** and in `SourceTotal`'s docstring — found by re-reading the
artifact, not by review. A re-review of the fix commit then found it *still* alive in the docstring of
`count_by_source` itself, at the query site, where it was most likely to be believed and acted on.

> **Correcting a document is not correcting the program.** This one claim lived in **six** places: D-028,
> the changelog, the prose the program prints, `SourceTotal`'s docstring, `count_by_source`'s docstring, and
> a comment beside the assembly loop. It had also reached `PROGRAM.md`, which cited D-028 as the authority
> for the reconciliation D-028 deletes. **Four separate passes each believed they had finished the
> retraction.** Retracting a claim means grepping for it.

**A re-review of the fix commit found four more, one of them a real defect a layer up from the change.**
The shortlist stage's new "not instrumented" note named *a missing profile or a scan outage* as the cause —
a closed enumeration that fabricates a reason on any run that crashed for a third one. Chasing that
exposed the actual bug: **an abort was recorded in `stage_errors`, which reaches the `runs` row, but not on
the summary, which is what the artifact reads.** A crashed run's funnel therefore said `RECONCILES` with no
FATAL line and an empty Errors section — the same "indistinguishable from a clean empty run" defect D-021
fixed for the ledger, still live one layer up in the artifact. Fixed and pinned by a test that reads the
artifact rather than the ledger. Also: an uninstrumented stage with no note rendered a bare `**` in the
very section Gate P0 requires to be readable.

### Verified on real data

Four consecutive `boardwatch run --no-scan --top 5` against a copy of the production store (runs 5-8),
exit 0, all reconciled — the last two on the post-review tree, confirming the corrected artifact prose
carries no surviving copy of the falsified claim.
Corpus 19,262 · eligible 18,174 · ineligible 0 (B7, P2's) · abstained 1,088 · 5 leads, 5 PDFs. Per
provider: **greenhouse 5 leads; workday 0 from 37 boards and 4,685 eligible postings**; ashby 0; lever 0.
**Four runs reconciled, but they are not four independent days of evidence** — they are repeat runs over
one frozen store copy, so the provider attribution is one measurement observed four times, not the ≥3
independent runs job-apps' rule asks for. See `METRICS.md` for the cautions. The scan stage was exercised
not at all, so this is **not** the gate evidence for clause 1.

## What shipped in session 5 (2026-08-06)

**P0 item 1 — the per-run funnel artifact.** Every `boardwatch run` now writes
`funnel-<run_id>.json` and `funnel-<run_id>.md` into `<out>/<YYYY-MM-DD>/`, beside that day's
tailored résumés and outside the git tree. Named by run, not by date, so two runs in one day do not
overwrite each other.

Three things were measured before building and each changed the design:

- **`postings_seen` and `open_postings` are different populations** (D-022). `postings_seen`
  accumulates what each board LISTED — a board answering 304 lists nothing, `--no-scan` lists nothing
  at all — while `open_postings` is a whole-DB count. Chaining them, which the stage list in
  `PROGRAM.md` reads as implying, would produce a drop bucket that is **negative on most real runs**.
  The funnel's head is the corpus; scan counts are context in their own block.
- **`unique` cannot be measured at all.** `jobs` and `postings` are 1:1, dedup has never run. It
  reports **not instrumented**, never 0 — reporting 0 duplicates asserts the opposite of the truth
  and would count towards the gate (D-023).
- **`leads_with_pdf` is not a row count.** Read from `meta_json.typst_pdf_built`, since
  `artifacts.uri` holds the `.typ` path whether or not a PDF ever compiled.

### The reviews found ten defects, and the most important one was about what counts as evidence

**A code review found four logic defects; a test-quality review found six claims that were
documented but not pinned.** The deepest finding runs through both:

> **Two of the three reconciliations could not fail.** `attribution` and `verdict` are SQL
> *partitions of the very set `entered` counts*, so their sums equal it for every possible database
> state — yet they were labelled as evidence, beside `corpus`, which genuinely can fail. The artifact
> was printing a uniform row of green ticks over one real check and two tautologies.

Both are now `derived`, the two `*_reconciles` properties that could never return `False` are
deleted rather than kept as decoration, and the artifact prints **which stages could actually have
failed**. The honest evidence base is `corpus` (an independent `NOT EXISTS` sweep), `tailor`, and two
cross-checks that recount the deliverable from the store.

Also adopted:

- **The shortlist stage subtracted the ranker's hidden counts from the verdict stage's `eligible`.**
  Different populations, so the remainder could go negative and was clamped at 0 — which breaks the
  stage's identity and drags Gate P0's headline metric to FAILED. **It does not fire today only
  because `ineligible` is 0 store-wide**, so `eligible` dominates. The moment **P2** makes
  `ineligible` reachable it would have fired on every run. Rooted at the ranker's own population now.
- **The applied stage could report `advanced > entered`** — `marked_applied` counts over every
  tailored posting while the stage was rooted at `leads_with_pdf`.
- **`count_applied_for_postings` counted any status**, so a lead merely marked `interested` —
  `create_application`'s default — was reported as a conversion in the one stage that measures
  conversion.
- **Six test claims were green against a mutation that falsified their own docstring.** Three drop
  reasons passed on *substring collisions*: `"ineligible"` inside `"hidden_ineligible"`,
  `"abstained"` in a column header, `"capped_by_top_n"` in a stage note. Deleting those `Drop`s
  outright left the suite green. Every reason is now asserted in its rendered `- **reason**: N` form.
  The derived-label and lead-source assertions matched the table HEADER and the legend prose rather
  than the row.

> **The lesson, sharpened again: a substring assertion over rendered prose is not a test of the
> data.** The artifact explains itself in English, so almost every term it reports also appears in
> its own commentary. Assert the rendered form, scoped to the row.

**Two process errors worth recording, both in the mutation-checking procedure itself — D-025.** I
reverted `src/` with `git checkout --` while the review fixes were still uncommitted, silently
discarding them, so two mutation results were read against the pre-fix code. And a mutate → test →
restore loop left **stale bytecode**: the running module was a hybrid whose `entered` came from the old
implementation and whose drop count came from the new one. A test that passed in isolation then failed
under `make check`, and one mutation recorded as CAUGHT was SURVIVED on a cold cache. **Commit before
mutating, clear `__pycache__` between mutations, and when a batch disagrees with an isolated run the
isolated run wins.**

### Verified on real data

Three consecutive `boardwatch run --no-scan` against a copy of the production store — runs 6, 7 and
8 — **all three reconciled**, exit 0. Numbers in `METRICS.md`. Note this exercised the scan stage not
at all, so it is **not** the gate evidence.

## What shipped in session 4 (2026-08-06)

**P0 items 0 and 7, shipped together deliberately.** Item 0 alone would have changed no observable
behaviour — the same criticism that applied to item 7's migration when it landed inert last session — so
the run row and the threading that populates it landed as one unit.

- **`boardwatch run`** (`src/boardwatch/pipeline/runner.py`, `cli/run_cmd.py`). Owns one run row across
  all three stages and stamps `finished_at` after tailor. `--top N` · `--out` · `--resume` · `--no-scan`.
  **Exit 0 unless the run is fatally broken**, 2 on scan-lock contention — dead boards and leads that fail
  to tailor are counted and printed but do NOT fail the run. This is what `.agent/bin/bw-daily` becomes.
- **`run_id` threaded into both write paths.** `run_eligibility` → `write_evaluation` →
  `record_evaluation`, the opt-in LLM lane (`extract_and_record`, which bypasses `write_evaluation`), and
  `run_tailor` → all three artifact inserts.
- **`runs` ownership split.** The **scan stage creates the row** (inside the lock it already holds) and
  the **pipeline finishes it** — D-020. `finalize_run` gained `finished: bool = True`; new `finish_run`
  stamps `finished_at`. A contended `boardwatch run` therefore writes **nothing at all**, inheriting
  `scan`'s zero-write contract rather than merely closing an orphan row out.

**The invariant this establishes — D-019, and the reason the work is worth this much care:**

> **`run_id` is never NULL on a row written after this change.** A stage invoked standalone mints a
> *degenerate* pipeline run rather than writing NULL. So NULL means exactly one thing — the row predates
> attribution — and that population can only shrink.

`run_eligibility` mints **only once `pending` is non-empty**, or every `top` invocation would log a run
and `runs` would become a command log rather than a ledger of work.

Two consequences accepted on purpose, both in D-019: a **cache hit keeps the first run's id** (no row is
written; "cache hit" is its own funnel stage counted from the insert rowcount, never inferred from
`run_id`), and a **reused master résumé artifact keeps the run that first authored it**.

### The independent review found eleven real defects — the first session where they were in logic

Sessions 1–3 established a pattern: reviews found documents and tests, never logic. **That pattern broke
here, and it broke on new code.** All eleven were adopted; the load-bearing ones are in **D-020**:

- The pipeline minted the run row **before** the scan lock, so `boardwatch run` migrated the live DB
  outside the lock and stranded a row on contention. Fixed by moving the INSERT into the scan stage.
- Scan errors were persisted **twice** (the scan stage writes them; `finish_run` appends; the pipeline
  passed them again), making any per-run error count uninterpretable.
- `boardwatch run` would have exited **1 on essentially every real run** — one dead board out of 85 was
  enough — while `boardwatch scan` exits 0 for the identical condition. `errors` and `fatal` are now
  separate fields.
- No `try/finally`: any unexpected exception left a run row that `doctor` reports as in-progress forever.
- `shortlisted` measured the `--top` flag rather than a funnel stage.

**Two findings were tests of mine that could not fail** — the third and fourth occurrence of this class.
One compared `summary.evaluated` to the *same query that produced it* while its docstring claimed it
counted through a different path. The other asserted a value `insert_run` writes at birth, so deleting
`finalize_run` **entirely** left it green.

> **The sharpened lesson (D-020): a mutation test proves the mutation is caught, not that the docstring is
> true.** Both tests were mutation-checked and both survived, because I picked the mutation from the code I
> had written rather than from the claim the test made. Derive the mutation from the claim.

### A second review, on the fix commit, found eight more — including a defect in the first fix

**D-021.** The most important: my exit-code fix had **over-corrected into bar metric B5**. Going from "any
error ⇒ exit 1" to "only a missing profile ⇒ exit 1" meant a **total network outage exited 0** with a
success line — which `CLAUDE.md`'s own fail-safe table names explicitly (*"systemic outage ⇒ fatal"*). Two
narrow fatal conditions were added: a systemic scan outage, and every shortlisted lead failing to tailor.

Second most important: **D-020's own dangling-row fix had a hole.** The pipeline's `try/finally` starts
after `run_scan` returns, but the row is created *inside* `run_scan` — so Ctrl-C during the multi-board
fetch loop stranded exactly the row D-020 claimed to close. The scan now closes its own row on abort.

Also: a crashed run was recorded as a *clean empty* run (the `finally` discarded the exception it held);
**three tests were making live HTTP calls to `boards-api.greenhouse.io`**; the test named for board
failures never failed a board (it used an unknown *provider*, a branch that deliberately never increments
`failed`); and the exit-1 path had no test at all.

> **The meta-lesson (D-021): a fix is new code and inherits none of the reviewed status of what it
> repairs.** Two reviews on one change found nineteen defects, and the second review's most severe finding
> was a defect in the first review's fix. Re-review after a substantial fix round.

### Verified on real data, not just fixtures

`boardwatch run` against a copy of the production store: **19,262 evaluations attributed** to one finished
run, 3 artifacts, 3 PDFs, exit 0 — and the NULL population stayed at **exactly 20,637, unchanged**. That
last number is the invariant: had any standalone write path leaked a NULL, it would have grown. Numbers in
`METRICS.md`.

---

## What shipped in session 3 (2026-08-06)

Everything below is on `main` and **pushed**. `make check` exited 0 at each commit (2650 passed, 94.91%).

- **Merged `p0-instrumentation` to `main` and pushed** (`88c98d4`), after a second independent review.
  `main` had been red since session 1 and is now green: `make check` exits 0, `generalization: OK`. CI on
  the merge: success.
- **`540bb34` — per-rule abstain rate** (`boardwatch eligibility abstain`), P0 item 2. Enumerates from
  `load_rules()` and LEFT JOINs observed counts, so the 7 rules that have never fired are visible instead of
  absent. Never-fired reports as `never fired`, **never as 0%**.
- **`fc6e8a5`** — closed four nits from a third review (of the abstain feature itself). See D-018.
- **`5f254a3`, `193468e`** — this file, `METRICS.md`, `CHANGELOG.md`, and D-017/D-018.

**Two independent reviews ran this session, and neither found a logic defect.** Both found documents and
tests. D-017: `STATE.md`'s own header named a HEAD and commit count that three later docs commits had
invalidated — the header no longer carries either. D-018: a test whose docstring cited a rendering fix
**did not pin it** (it widened the terminal to 160 columns, dodging the 80-column condition the fix
addressed; deleting the fix left the suite green), and `total_rows` — documented as the property B6
reconciles against — had no caller and no assertion.

> **The standing lesson, now twice-observed: review the documents and the tests, not just the code.**
> A test that cannot fail is documentation with a green tick next to it. Confirm a new test fails without
> its fix before trusting it.

### What the new metric immediately found

**7 of 44 rules have never fired; 17 more fire and never decide.** Full numbers in `METRICS.md`. The two
that matter most:

- **The entire `clearance` family** — 105 detections, **0 met and 0 unmet, ever**. Every clearance rule
  that fires is at 100% abstain.
- **`work_auth:no_sponsorship_offered`: 1052/1052 abstained.** A thousand postings said in their own text
  that they offer no sponsorship, and the engine concluded nothing on every one. This is **bar metric B7
  measured rather than asserted**, and it is why `ineligible` is 0 across the whole database.

---

## What shipped in session 2 (2026-08-06)

Five commits on `p0-instrumentation` — two of substance, three recording them, `make check` green at each:

- **`bc0973d`** — `main` was **red** and had been since session 1. `PROGRAM.md:4` and `STATE.md:27`
  carried an absolute `/Users/<name>` path, violating generalization rule R1, so `make check` exited 2
  before pytest ever ran. Session 1 wrote "`make check` is the only gate" and then committed twice without
  running it. Fixed to `~/...`. See D-014 — **docs are scanned; a docs-only commit is not exempt.**
- **`c56bc11`** — `run_attribution` migration: nullable `run_id` on `eligibility_evaluations` and
  `artifacts`, plus round-trip test and the head-revision pin. See D-015.

Research findings are in `METRICS.md` under "Session 2". The load-bearing ones:

- **6 families, 44 rule patterns. 7 of the 44 have never fired once** in 20,637 evaluations. A
  `GROUP BY rule_id` emits no group for them at all, so per-rule abstain **must** enumerate from
  `load_rules()` and LEFT JOIN, or the rules it exists to expose stay invisible.
- **A 100% abstain rate already exists:** `experience_years:scoped_years_minimum`, 11,670/11,670 `unknown`.
  *(Session-3 correction: it is not one rule. Measuring it properly found **17**, including the whole
  `clearance` family. Session 2 found the one it happened to look at.)*
- Two of session 1's schema claims were imprecise: the dedup index is **partial**
  (`WHERE engine_kind = 'deterministic'`), and there is **no `abstain` verdict** — it is stored as
  `uncertain`.
- `disposition='unknown'` conflates **four** causes, separable only by free-text `rationale` with no CHECK
  constraint. Abstain *rate* is computable; the typed abstain *reason* the keystone invariant wants is not.
- `artifacts.uri` points at the **`.typ`, not the PDF**; PDF-built lives only in
  `meta_json.typst_pdf_built`.
- **Only 1 of 7 funnel stages** was run-attributable before the migration.

---

## What shipped in session 1

Analysis, planning and program machinery — **zero source changes**. Committed as `84cfab6`.

- Read all seven job-apps handover documents (2,609 lines) in `~/dev/Job apps/docs/boardwatch/`.
- Verified job-apps' claims about boardwatch against boardwatch's actual code. job-apps never read this
  repo and said so; four of its factual claims about boardwatch are wrong as a result. See `DECISIONS.md`
  D-002, D-004, D-005, D-006, D-007, D-009 and `PROGRAM.md` §5.
- Wrote `PROGRAM.md`, `STATE.md`, `DECISIONS.md`, `METRICS.md`, and the repo's first `CLAUDE.md`.

**Correction to boardwatch's own record:** the "37 applied folders" figure boardwatch used in
`.agent/plans/p12-parity-report.md` is wrong. job-apps' real figure is **388** `_applied/` folders (369
distinct, 380 with PDFs); 37 was one bucket of its current curated queue. boardwatch's "37 shipped vs 222
targets, and job-apps' applied count is also 37" argument is dead — both halves were coincidence on
job-apps' own numbers. That parity doc is retired by D-008; the file is gitignored working material and
has been left in place, unedited, as a record.

---

## Independent review — 2026-08-06

Reviewed by a fresh agent with no shared context, at Mit's instruction. **Verdict: APPROVE WITH CHANGES.**
Full record in D-013.

Five load-bearing factual claims were attacked: **D-004, D-007, D-009 VERIFIED** · **D-005, D-006
OVERSTATED** (both in boardwatch's own favour — the D-012 failure mode, caught). All twelve required
changes adopted, none contested.

### Worklist from the review

| # | Item | Phase | Status |
|---|---|---|---|
| 1 | Lane-scope D-005; add Tier-B token-provenance validator | P1 (3c) | **corrected in place** |
| 2 | Replace LaTeX `hbox`/`vbox` clause with Typst-native overflow check | P1 (3) | **corrected in place** |
| 3 | `typst` in Dockerfile + loud missing-binary preflight | P1 (3b) | **corrected in place** |
| 4 | `run_id` migration on `eligibility_evaluations` + `artifacts`; cache hit as an asserted stage | P0 | **corrected in place** |
| 5 | B1–B7 → phase → gate traceability table; give B4 an owner; fabrication counters in the funnel (`RewriteRow.drop_reason` already carries the data) | P0 | **closed** |
| 6 | Severity/policy layer into P2 deliverables and §3b's split table; specify which policy P5's labeled set is scored under | P2 / P5 | **closed** |
| 7 | Resolve the P1/P2 ordering inconsistency | P1/P2 | **closed — Mit ratified P1 first 2026-08-06; cost now stated explicitly in §2 rather than denied** |
| 8 | Make P4's blind-craft gate executable — job-apps produces no résumés under `STAGE1_ONLY=1` | P4 | **closed — corpus is job-apps' 392 existing `_applied/` folders** |
| 9 | Restore dropped handover items: sponsorship phrases, cohort completeness, persona registry, fixture-drift discipline, two-OS WAL | P3/P4/P5 | **closed** — persona registry is now P4 item 7; fixture drift is in `CLAUDE.md` |
| 10 | Augment the existing `FileLock` at `scan/coordinator.py:73` rather than replacing it | P3 | **closed** |
| 11 | Tier-B quota + meta-hash idempotence (~300 model calls/day unattended at 2/bullet) | P3 | **closed — P3 item 10** |
| 12 | Commit `docs/program/` and `CLAUDE.md` | — | **closed — committed 2026-08-06; standing permission to commit granted** |

**All twelve closed. The plan is final and approved to execute.**

---

## Next action

**P0, P1, P2-core, and P3-build are all complete (session 10, 2026-08-07).** The run reaper merged
(D-046, `2ce8e2d`+`91e0992`, `make check` green) was the **last P3 build item that needs neither Mit's
domain input nor Docker.** What is left is genuinely gated on things I cannot supply autonomously:

- **P2 item 4 (personas / field-dependent taxonomy) + Gate P2 — RESOLVED by D-054 (Mit, 2026-08-07):**
  non-tech field content is NOT authored by us (we only have tech expertise) — it is **gathered per-user
  at onboarding** (the system gathers each user's field-specific eligibility taxonomy / persona /
  vocabulary as versioned per-user data). So item 4 / P4 item 7 become "ship the field-keyed mechanism +
  tech seed"; a **NEW onboarding-gatherer build item** (needs its own design) produces non-tech content;
  **Gate P2 reframes** to validate the mechanism against ≥3 fields whose non-tech taxonomies are gathered
  (or gathered-output fixtures), not hand-authored. No longer Mit-content-blocked.
- **P3 item 8 + Gate P3** — Gate P3 = 7 consecutive unattended runs **AND** the two-writer test green.
  **The 7-run half can be accumulated by a PARALLEL Claude Code session (or cron) Mit runs on this machine**
  (owns the daily `bwd` + per-run `verify`/funnel Gate-P3 recording), in parallel with dev here — no
  contention (`make check` uses temp DBs; the scan lock serializes live runs). **Prerequisite:** fix the
  live config first (a 1-page résumé) or every run drops all leads.
  The two-writer test half still needs **Docker** (absent; `docker info` fails); documented-stance half
  shipped (D-041). So the parallel session closes the operational half only.
  **ATTEMPTED + BLOCKED 2026-08-07 (parallel Gate-P3 session, read-only, live store untouched):** the
  operational half **never started** — the prerequisite is unmet. Correction to the line above: **Mit
  pins `resume_max_pages=1` for himself** (other users may set 2+), and his authored
  `resume.yaml` renders to **2 pages**, so every `boardwatch run` drops all leads → 0/0 FATAL → the
  7-run counter can never advance. Measured (typst 0.15.1, app renderer): the résumé has **no summary
  field** (schema = header/education/skill_groups/entries only — the overflow is content volume, not a
  summary); page 2 = only the two oldest projects. Capping skills does nothing (they wrap, ~0 vertical
  cost); only fewer entries / shorter bullets help (drop crop-rf **+** gamified-learning → 1pp). **Mit
  paused for major résumé rework in a separate session.** Also: the daily driver is `boardwatch run`,
  **not** `bwd`/`.agent/bin/bw-daily` (that predates `run` and emits no run_id/funnel artifact, so the
  handoff's `verify --run` procedure needs `run`); `profile edit` has no `--resume-max-pages` flag (the
  value is a profile-DB column); CLI is `uv run boardwatch`; `boardwatch doctor` hung >120s.
  See memory `gate-p3-blocked-on-one-page-resume`.

- **P4 IS UNDERWAY (D-047, decided autonomously under Mit's "keep plowing / don't get stuck" mandate).**
  Rationale: P4's craft rubric is functionally independent of the unattended runner and builds on the
  already-met Gate P1; Gate P3 is blocked only by Docker (item 8) + operational runs, neither a P4 build
  dependency; blocking all build on that is exactly "getting stuck." Reversible. **P4 item 1 DONE (D-048,
  `03aefb0`..`15880a6`+`f1cbb3d`):** deterministic overmatch guard (verbatim ≥7-gram lift + unusual-caps
  copy) reverts a Tier-B bullet to Tier-A with `drop_reason="overmatch"`; distinct from the pre-existing
  invention filter; two-gate reviewed (diff-reviewer clean), `make check` green (2967 passed, 95.36%).
  **P4 item 2 DONE (D-049, `f4207f8`+`cf24891`):** consolidated item 1's duplicated `canonical` seed into
  `tailor/canonical.py::build_canonical_vocab` (behavior-preserving; parity-tested); most of item 2 already
  existed (taxonomy + equivalences), and the per-field SELECTOR was DECLINED as YAGNI (one field's vocab
  today; `field="swe"` tag makes future keying trivial). `make check` green (2970 passed, 95.37%).
  **P4 item 3a DONE (D-050, `c0ef15e`..`7c1b8d5`):** banned-register + buzzword-density (per-bullet
  Tier-B gates) + verb-opening diversity (résumé-wide post-pass), reverting to Tier-A with the new
  `drop_reason`s; universal register lists (not per-field), tunable later. One fix round (authoritative
  `make check` caught an R7 SHIPPED_DATA gap the self-report missed; diff-review caught a real
  verb-diversity demote-without-diversifying bug). `make check` green (3003 passed, 95.34%).
  **P4 item 3b DONE (D-051, `b52b858`..`81518ed`) → ITEM 3 COMPLETE.** Requirement-echo AND-gate
  (structural [(a) non-action-verb opener AND (b) qualification-register cue] AND corroboration [4-gram
  with a JD qualifications sentence, ≥1 non-canonical token]); deepseek fixed the design (and/or→AND,
  Jaccard→4-gram); impl review + one fix round closed two real false-positive holes (irregular-verb
  openers; lowercase header span-leak). `make check` green (3037 passed, 95.32%).
  **P4 item 4 DEFERRED into item 7 (D-052):** grounding found it has NO call site today — no forward-looking
  résumé title field exists until item 7 (persona registry) creates one; building the de-senioritizer now
  would be inert dead code. It rides with item 7 (reusing `tokens.py` word-boundary machinery to dodge the
  Sr∈SRE / Lead∈Leader / III-after-II traps); the general down-level rule is additionally Mit-blocked (no
  seniority profile field). **P4 item 5a DONE (D-053, `d738932`..`5295baa`):** per-lead layout gate
  (bullet length/count, escaping round-trip, hyphen-aware template-artifact) on tailored + master +
  Tier-B; degrade-then-drop. Fix round removed a lead-dropping 40-char floor, fixed a "Todo-list"
  false-positive, closed the ungated-Tier-B gap. `make check` green (3067 passed, 95.37%).
  **P4 item 5b DONE (D-056, `d9c7bf1`..`f99600c`):** run-once, fatal `validate_master` at `load_resume`
  (contact-block name + email + template-artifact leak; deliberately NOT length/count — that was the D-055
  regression); a broken master aborts the run loudly (runner `except ResumeLoadError` before the generic
  catch) instead of silent per-lead drops. Reviewed; one fix round removed a false-fatal on single-line
  headers (`len(header)<2`→`not header`). `make check` green (3084 passed, 95.39%). **→ P4 ITEM 5 COMPLETE.**
  **⛔ NEXT ACTION IS NOT P4 item 6 — READ THIS (D-057, Mit 2026-08-07):** Mit determined the résumé
  **TAILORING is fundamentally wrong** (surfaced by the Gate-P3 work seeing real output — NOT just the
  page-count config). A **dedicated résumé-tailoring-fix session** must come FIRST — before Gate 3, and
  (orchestrator rec, pending Mit confirm) before the remaining P4 items 6–7, because P4 gates ON the
  tailored output and polishing a broken foundation is low-value. That session should START by diagnosing
  the actual bad output against Mit's reworked résumé + a real JD (which tailoring stage is wrong:
  Tier-A repositioning / Tier-B rewording / bullet selection / the plan?) BEFORE changing code — the
  specifics are TBD (Mit to provide). The merged P4 guards (items 1/2/3/5) stand; just don't build more on
  top yet. **Only after tailoring is fixed** do the items below resume.

  **UPDATE — résumé-tailoring-fix session (2026-08-07), D-057 no longer "TBD":**
  - **Diagnosis DONE** (`.superpowers/sdd/resume-render-tailoring/diagnosis.md`): the tailored output was a
    "plain-text dump" for two root causes — (1) the renderer preamble was a 5-line Typst stub (no page
    setup, fonts, sections, rules, dates), and (2) the tailoring itself is near-invisible (Tier-A only
    reorders/deletes bullets within an entry, ≤3 bullets each so ~no-op; no keyword bolding; no
    summary/title; Tier-B off by default). Mit's real complaint: it doesn't look like his job-apps
    "Jake's Resume" LaTeX output.
  - **Engine RATIFIED — D-058: tectonic compiling Mit's actual `resume_base.tex` (Typst REVERSED).** Mit
    rejected a Typst spike as "not the same" — his template is a LaTeX file, so Typst can only approximate.
    tectonic = single ~30MB LaTeX binary (the earlier "LaTeX is heavy" rationale was wrong); output is
    identical to job-apps. Page-count moves to `pdfinfo` (installed). Tailoring core (model + Tier-A +
    `output_is_entailed`) is engine-agnostic and stays; only the render layer + the 3 emit-mirror gates +
    page-count change. tectonic NOT yet installed (`brew install tectonic` prereq).
  - **Design APPROVED by Mit** (`.superpowers/sdd/resume-render-tailoring/design.md`): principle
    template≠content (ship the mechanism, user's own template is data); **three increments** — (1) LaTeX
    render substrate, (2) `\textbf{}` keyword bolding from `jd_skills`, (3) per-role authored title/summary
    select. Header+Education stay template-hardcoded in Increment 1 (job-apps-exact); single-source
    (Option i) is a documented fast-follow.
  - **Increment-1 plan WRITTEN + REVIEWED + REVISED** (`plan-increment-1-render-substrate.md`, 7 TDD
    tasks). Fresh-context Opus review returned REWORK; all 3 blockers + 2 majors + 5 minors folded in
    (single-pass LaTeX escape; `title is None` fallback before kind-routing + scaffold; complete
    `.typ`→`.tex` rename; resolved-template artifact scan; `Resume.extracurricular` + honest 3-category
    fidelity check; tectonic bundle-warm; etc.). Reviews at `review-deepseek.md`/`review-opus.md` (of the
    superseded Typst draft) + the plan-review is summarized in the plan's Self-Review.
  - **Increment-1 plan RE-REVIEWED (2nd pass) + CLEARED to execute — D-059.** At resume Mit chose a
    second re-review of the revised plan before execution. tectonic **0.17.0** installed (D-058 prereq);
    pdfinfo present. Two fresh-context Opus reviewers (soundness · tests) BOTH returned REWORK; every
    finding was verified against the live tree and folded into the plan (2 shared blockers — the
    `TypstRunner` import graph, fixed by moving `CompileRunner` to leaf `render/outcome.py` +
    expand-then-contract; and the dash contradiction, fixed by normalizing `–`/`—`→`--` in `escape()` — plus
    `_pdf_page_count` `re.MULTILINE`, expanded Task-6 breaking-test list, full keystone-field entailment
    tests, doctor version regex, and 8 minors). Both reviewers confirmed the entailment tightening, escape,
    firewall, macro arities, and fail-safe posture sound. Verdicts at `review2-soundness.md`/`review2-tests.md`.
  - **Increment-1 EXECUTED + SHIPPED — D-060 (2026-08-08).** Built via subagent-driven development: 7 TDD
    tasks (`1aebe18`..`27e179f`), each gated by `make check` and independently reviewed, plus a final
    whole-branch Opus review — all clean. `make check` on `main`: **3098 passed, 1 deselected, coverage
    95.33%, `generalization: OK`.** The Typst→tectonic swap is complete: `render/typst.py` and its tests are
    DELETED; tectonic compiles Mit's own `resume_base.tex` (installed to `{config_dir}/resume_template.tex`
    + a structured `resume.yaml`); page count reads `pdfinfo`. **Big result 1 — the old Gate-P3 blocker is
    RESOLVED:** Mit's real résumé now renders to **1 page** (verified by a real compile + `pdfinfo`, not
    the app's self-report), so the 2pp-at-limit-1 problem recorded in memory
    `gate-p3-blocked-on-one-page-resume` no longer holds. **Big result 2:** fidelity vs. his job-apps LaTeX
    PDF is a layout match — the required three-category gap check found zero layout/emitter bugs.
    **Big result 3 — a NEW real blocker, content not engine:** three bullets in `resume.yaml` (the National
    Internet Observatory entry's first bullet, and both StreakSync bullets) exceed the per-lead layout
    gate's 220-char ceiling (D-053), so Tier-A degrades to the untailored master on **every** posting until
    Mit shortens them. Also Mit's to fix, not a code gap: `resume.yaml` is missing a 4th project (Knowledge
    Forge), has stale `skill_groups`, and no `extracurricular`; separately, the **job-apps source**
    `~/dev/Job apps/resume_base.tex` has a stale `CGPA: 8.5/10` — the installed copy was corrected to
    `8.81/10` during Task 7, so the two now disagree.
  - **NEXT ACTION is the 220-char bullet fix — Mit's, not a build item.** Once the three bullets are
    shortened, tailoring stops degrading to the master on every run, and **P4 items 6–7 and the Gate-3
    operational runs — both parked behind D-057's "fix tailoring first" ruling — can resume with no further
    build.** After that, Increment 2 (`\textbf{}` keyword bolding from `jd_skills`) and Increment 3
    (per-role title/summary selection) are each their own plan, still not built. Option i (single-sourcing
    Header/Education from `resume.yaml`) remains a documented fast-follow.
    **Session close (2026-08-08):** Mit was shown a live 1-page render of the master résumé and
    **explicitly deferred the bullet trim** — it is not rejected, just not now. So a cold session should
    NOT treat the trim as an urgent block: it gates Increments 2/3 and visible tailoring, but P4 items 6–7
    (persona registry + de-senioritizer) are fully independent of it and are the productive build to start
    when work resumes. Increment 1 is banked, pushed (`76f75f5`), gate-green.
    **Session update (2026-08-08, P4-craft) — item 6 SHIPPED, item 7 READY:** work resumed on P4 items 6–7
    exactly as the line above prescribed (the deferred bullet trim does NOT block them). **P4 item 6
    (keyword-coverage measurement) is DONE** — merged to `main` (`58f032e`, D-061), diff-review clean,
    `make check` green (3112 passed, 95.32%). It is a report, not a veto: coverage counts JD-requirement
    terms (qualifications-span denominator, body fallback) that the **master** résumé genuinely covers, so
    an echoed JD term can't inflate it; surfaced in artifact meta + morning report + a run-level funnel
    summary. **P4 item 7 (persona registry + the now-live title de-senioritizer) is DESIGNED and
    worktree-ready but NOT built** — design at `.superpowers/sdd/p4-item7-persona-registry/design.md`,
    decisions ratified in **D-062** (persona = a résumé-presentation lens, NOT an eligibility variant, so the
    profile DB + eligibility engine are untouched; the de-senioritizer is made live by resolving the résumé
    title from the JD title with seniority stripped).
    **UPDATE — item 7 SHIPPED (D-063, `1988c39`):** built overnight via SDD, diff-reviewed (found + fixed a
    duplicate-`entries`-id gap) and deepseek-reviewed ("OK to ship after nits"; one fatal-abort suggestion
    DECLINED on fail-safe grounds — a degenerate per-lead title falls back to the default persona, never
    aborts the run), `make check` green (3148 passed / 95.23%). **P4 BUILD IS COMPLETE (items 1–7).**
    **Two remaining P4 items are MIT's:** (1) **Gate P4's blind-craft review** (read 10 tailored résumés
    mixed with job-apps output, unlabeled; corpus = job-apps' `_applied/` folders); (2) install the
    `%%TITLE%%` pair into his `{config_dir}/resume_template.tex` so the persona title renders for him (the
    bundled template has it; skill-order + entry emphasis render regardless). The 220-char bullet trim +
    Increments 2/3 remain Mit's deferred content work.
    **P5a SHIPPED (D-064, `faf8aa9`):** the three verdict-SAFE eligibility-integrity slices are on `main`,
    diff- + deepseek-reviewed, `make check` green (3525 passed / 95.17%) — S1 corpus-wide
    "0 INELIGIBLE without a span" property gate, S2 out-of-catalog family/disposition FAILURE surfacing in
    `reports/abstain.py`, S3 LLM cache keyed on profile+catalog identity.
    **NEXT ACTION — P5b, MIT's morning (verdict-changing + data-gated; NOT built overnight on purpose):**
    P5 item 1 new hard-stop families, item 3 named exceptions (`up_to_n`/`range_0_n`/`internships_count` +
    an explicit exception-name field), item 4 REQUIRED/PREFERRED section slicer — all change deterministic
    verdicts, and a false INELIGIBLE silently deletes a real job, so they need the labeled set to measure
    Gate-P5 precision (≥0.95 on INELIGIBLE) before shipping. Data-gated: item 5 the ~200-JD + ~50-hard-
    negative labeled set (curate from `~/dev/Job apps/` skipped folders — reading it is authorized, D-010),
    item 6 the 35+ visa/sponsorship block phrases (from job-apps `batch_tailor_pipeline.py`). The mechanism
    plan is ready at `.superpowers/sdd/p5-eligibility-decides/design-p5b.md` (deepseek-reviewed) — it needs
    Mit to (a) provide/curate the labeled set and (b) greenlight, then it can execute against the precision
    gate. Gate P5 cannot be measured until the labeled set exists.
    **UPDATE — P5b B0 label-independent scaffolding SHIPPED (D-065, 2026-08-08):** at Mit's greenlight the
    parts of B0 that need no labels to BUILD (only to RUN) are on `main`: `eligibility/scoring.py` —
    `reference_all_blocker_policy` (code constant, all families→`blocker`, PROGRAM.md:384, auto-covers B4),
    `score()`→`PrecisionReport` (INELIGIBLE precision/recall, per-rule abstain, false-positive triage, span
    violations, `meets_gate(0.95)`), `carries_valid_span` (extends P5a S1's span property to the labeled
    set, shared not forked), and `load_labeled_set` (a `*.jsonl` worksheet, null-verdict rows skipped as
    unlabeled). 26 tests, module 100% covered, `make check` green (3551 passed, 95.25%). **Local-only
    (gitignored):** `.superpowers/sdd/p5-eligibility-decides/labeled-set/` holds `extract_candidates.py`, a
    stratified **173-row worksheet** (123 hard-stop candidates across families + 50 `_applied/` hard
    negatives from job-apps), and `README.md` labeling instructions — real JD bodies stay local (§3b).
    **Reference `facts` RESOLVED** — = Mit's real profile from job-apps `autoapply/profile.json`
    (`ead_or_similar` + `needs_sponsorship`, `master`, `fte_only`, excl. internships; `total_years=1` fits
    his new-grad targeting of 0/0-1/0-2/1+ roles), baked into the LOCAL worksheet only (§3b). **Answer-key
    location RESOLVED** — user-config location for the published mechanism; Mit's stays in the gitignored
    `labeled-set/`.
    **NEXT ACTION — D-066 (Mit 2026-08-08): the answer key is no longer hand-labeled.** It is
    **AI-oracle-produced + human-audited on a small sample**, via a **PORT of job-apps' LLM judge+gate flow,
    then improved** — and this is **its own dedicated in-depth session** (do not squeeze into a tail).
    Cold-start brief: `.superpowers/sdd/p5-eligibility-decides/design-p5b-answer-key-judge-port.md` (job-apps
    sources to study, boardwatch pieces to reuse incl. the B0 scorer, the integrity guardrail, oracle-model
    TBD). Once the answer key exists, B1–B4 execute one at a time, each gated by `score().meets_gate()`.

  **DEFERRED next action — P4 item 6** — keyword coverage measured against JD *requirement* terms,
  achieved only by re-spelling existing facts (ground it first: reuse the canonical vocab + the
  qualifications-span slicer from item 3b; it's a MEASUREMENT/report, likely not a veto). **Then item 7**
  (persona registry MECHANISM + tech seed + the deferred de-senioritizer [reuse `tokens.py` word-boundary
  to dodge Sr∈SRE/Lead∈Leader/III-after-II] — per D-054 the mechanism is buildable now; non-tech persona
  CONTENT comes from the onboarding-gatherer, NOT Mit-authored). Gate P4's blind-craft-review stays Mit's.
  **NEW build item (D-054): the onboarding-gatherer** — user-facing; DESIGN-FIRST (brainstorm; surface the
  "go out and gather" mechanism choices to Mit); do not build blindly.

**Live findings still owed to Mit (unchanged):** (1) set `resume_max_pages=2` — his `resume.yaml` is 2pp,
so at the shipped default of 1 every lead is correctly dropped (see below); (2) P1b cannot catch a bullet
that recombines real résumé numbers into a false claim (numeric-recombination limitation, D-033).

**A live, actionable finding from the P1a dogfood, not a code defect — surfaced 2026-08-07.** On the real
store, at the profile's shipped default `resume_max_pages=1`, `boardwatch run` drops **every** shortlisted
lead: Mit's own authored `resume.yaml` compiles to **2 pages**, independently confirmed outside the app
(`typst compile` + `typst eval query(<total-pages>).first().value`), so both the tailored and the
untailored-master fallback exceed the 1-page limit and the run ends FATAL with 0 leads, 0 PDFs (real run
11, `~/boardwatch-applications/2026-08-07/funnel-11.md`, `boardwatch verify --run 11` reconciles on the
0/0 result). This is the gate working exactly as designed — it is refusing to ship a résumé that violates
Mit's own configured limit, not malfunctioning. **The gate is correct; the live default is wrong for
Mit's actual résumé content.** Two ways to close it, Mit's call: shorten `resume.yaml` to fit 1 page, or
`boardwatch profile edit --resume-max-pages 2`. Nothing was changed in the live store to work around this
— the dogfood's confirmatory "100% PDF" evidence was gathered on an isolated **copy** of the store instead
(`METRICS.md` §"Session 9 — P1a dogfood").

**Session 9 — P0 item 5, the last P0 build item, SHIPPED.** `boardwatch verify`: a standalone invariant
sweep asserting DB rows and on-disk artifacts agree, counting from a **different path** than the one that
produced them (`CLAUDE.md`: self-report ≠ verification). Per D-030/D-031 it ships as a **standalone
verifier**, NOT as an extension of the funnel artifact's existing `cross_checks` — those are per-run
pipeline-memory-vs-store, while item 5 is a broader DB-vs-disk invariant, and it does **not** change Gate
P0's standing (already MET, session 8). Dogfooded against the real store 2026-08-07: sweep mode checked
runs 5, 6, 7, 9, 10 (v2 and v3 artifacts both), all reconcile, exit 0; `--run 9` exits 0; `--run 8` (the
dangling run with no funnel artifact) correctly exits 1 with a single `NO_ARTIFACT` discrepancy. Read-only
throughout. Full record: `METRICS.md` §"Session 9", D-031.

**Session-8 loose end — RESOLVED.** The confirmatory `--no-scan` run from `main` completed:
`funnel-9.{json,md}` in `~/boardwatch-applications/2026-08-07/` is `artifact_version` 3, reconciles, with
the manifest (all six fields, `status: ok`), stub rate (17 / 23,455 = 0.07%) and fabrication counters (all
zero, Tier B off) all populated correctly on real data. So artifact v3 is now validated end-to-end on the
live store, not just fixtures. See `METRICS.md` §"Session 8". Two `runs` rows are non-clean and belong to
the P3 reaper: one dangling `running` row from a 120s-SIGTERM-killed attempt, and run_id 10 which closed
cleanly as `failed` (a stray run stopped with SIGINT — not dangling, just a recorded interrupt).

**`hidden_hard_filter` has now been looked at (session 7). Still P5's to fix, not a defect to fix now.**
It dropped **11,517 of 19,262 open postings — 60% of the corpus**, the largest single drop anywhere in the
funnel. Full measurement in `METRICS.md` §"Session 7". The headline correction:

**The split is 100% `exclude_titles` / 0% location.** The location clause has *never executed* —
`location_filter_mode` defaults to `"soft"` and the `config.toml` that could override it does not exist.
Any statement that this drop has two active causes is wrong. Three mechanical defects in the 16-entry
list: **`III` is unreachable** (every string containing `iii` contains `ii`), **`Sr` matches inside `SRE`
and `Israel`**, **`Lead` matches inside `Leader`** (127 rejections, incl. Cisco's senior-IC "Technical
Leader" family). But substring collateral is only **1.35%** — the real selection question is the
**`II`/`III` band**, 69 SWE roles vetoed by an entry Mit put there deliberately. `PROGRAM.md` assigns
selection quality to P5.

**A second, for the breadth argument.** Per-provider leads on run 6: greenhouse 5, **workday 0 from 37
boards and 4,685 eligible postings**, ashby 0, lever 0. This is the shape of evidence `PROGRAM.md`'s P7
unlock condition asks for, but it is one run at `--top 5` — where `leads` measures only the top of the
ranking — and job-apps' own rule is ≥3 runs. Do not cite it as settled.

<!-- SUPERSEDED next action, kept for its starting points. WARNING: one of them is now FALSE —
     "Only `corpus` and `tailor` are falsifiable stages" was true before item 3 and is not now; the
     artifact lists `corpus`, `shortlist`, `tailor`. The rest still hold. -->
### Previously: P0 item 3 — the per-source outcome table (DONE, session 6)

**P0 item 3 — the per-source outcome table** (`unique | assisted | eligible | leads | applied`).
`PROGRAM.md` §3.P0.3. It is the natural next item for two reasons: the funnel artifact already
carries per-lead board provenance, so the writer and the renderer both exist, and item 1 left a
**named instrumentation gap that item 3 is what closes** — the ranker does not report how many
postings it considered, so the span between the `verdict` stage and the `shortlist` stage is
uninstrumented and postings ranked below the `--top` cutoff appear in no counter at all.

**Starting points a fresh session should not re-derive.**

- **`reports/run_funnel.py` is pure and `store/run_funnel_queries.py` holds the reads.** Adding a
  per-source table means one more query and one more section; the artifact's shape does not change.
- **`companies` carries `provider`, `slug` and `source`** (`registry` | `user`, a CHECK-constrained
  pair). `lead_provenance` already joins postings → companies for exactly this.
- ~~**Only `corpus` and `tailor` are falsifiable stages today.**~~ **NO LONGER TRUE** — item 3 made
  `shortlist` falsifiable too. The rest of this bullet still holds: `attribution` and `verdict` are SQL
  partitions of the set they are compared against and are marked `derived` for that reason (D-023).
  Do not "fix" them into looking like evidence — if a per-source table needs a real check, it needs a
  count through a genuinely different path, as the two cross-checks do.
- **`postings_seen` is not the corpus.** D-022. This will bite again on any per-source denominator:
  a board that answered 304 listed nothing this run but still owns open postings.

<!-- SUPERSEDED by the "Next action" section above, which is authoritative. Item 4's exit-status half
     SHIPPED in session 7 (D-029): `runs.status` EXISTS — do not rebuild it. Kept only because the
     fabrication-counter note below it is still live. -->
Then, still open in P0: item **4**'s *remaining* half — the config hash and the artifact section (its
exit status shipped) — item **5** the reconciliation sweep, item **6** the stub rate, and item **8** the
fabrication counters.

**Fabrication counters need new typed capture, not a query.** Aggregates die at `cli/tailor_cmd.py:196-204`
and `:407-414` after `console.print`; Tier A's fail-safe (`TierASafetyError`) has no counter anywhere; and
`RewriteRow.drop_reason` is **11** bare untyped strings (measured: 5 direct literals plus 6 distinct `filter:*` reasons). Likewise `disposition='unknown'` conflates **four**
causes separable only by free-text `rationale`, which carries no CHECK constraint — so abstain *rate* is
computable but the typed abstain *reason* the keystone invariant wants is not.

---

## Phase status

| Phase | Status | Gate met? |
|---|---|---|
| P0 Instrumentation | **COMPLETE** (session 9) — all nine items 0-8 done, incl. item 5 (`boardwatch verify`, session 9) | **MET** (session 8, D-030) — three consecutive real-driver runs (5, 6, 7) all reconcile with the scan stage exercised; abstain per rule; why-dropped answerable from the artifact. Item 5 supplements this gate and does not re-anchor it (D-031) |
| P1 Résumé artifact gate | **FULLY COMPLETE** (session 10) — P1a (session 9) + P1b (session 10, D-033), both on `p1b-tier-b-provenance`, not yet merged to `main` | **MET** (session 9, D-032; P1b D-033 closes item 3c without changing the standing) — deterministic fallback/fatal/drop tests + real-store dogfood both directions (default-config FATAL drop, isolated-copy 100% PDF at correct page count); P1b verified by deterministic unit/lane tests only, no live Tier-B LLM run exercised |
| P2 Profile + keystone invariant | not started | — |
| P3 Unattended one command | not started | — |
| P4 Craft gate | not started | — |
| P5 Eligibility decides | not started | — |
| P6 Liveness + dedup | not started | — |
| 14-day acceptance run | not started | — |
| P7 Breadth | not started | — |

---

## Known gaps carried forward, stated rather than papered over

| Gap | Why it is not fixed here | Owner |
|---|---|---|
| **A `SIGKILL`ed run leaves a dangling `runs` row.** `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Observed live: a verification run killed by `timeout` left `finished_at` NULL after writing 11,200 attributed evaluations. **A dangling row is a quarantine with no drain**, which `CLAUDE.md` calls a leak. | A reaper belongs with P3's stale-lock reclaim. The exit-status half it was waiting on shipped in session 7 (D-029), and `runs.status` is where a reaper records what it reclaimed; the reaper itself is P3 | P3 |
| **The general zero-output guard is not built** — bar metric **B5**. Two unambiguous cases ARE fatal now (a systemic scan outage, and every shortlisted lead failing to tailor — D-021). What is missing is the judgement call: deciding when producing nothing was *provably right*. **Do not read exit 0 as "the run produced leads".** | That judgement is cohort completeness, P3 item 9; `PROGRAM.md` assigns B5's guard to P3 | P3 item 5 |
| ~~**`runs` has no `status` column**~~ **CLOSED session 7** (D-029). Closed catalog `running \| ok \| failed`. Note what it does NOT separate: `running` + `finished_at` NULL still means only *nothing closed this row*, covering a run in flight, a killed run, AND a standalone lane that raised between `ensure_run` and its own `finish_run`. | — | done |

## CI on `main` has no signal for item 3 — a GitHub incident, not a repo problem

**2026-08-06.** `make check` was green locally at exit 0 on the merge commit itself, which is this
project's stated gate, and item 3 was merged on that basis. But **GitHub Actions stopped dispatching
workflows partway through the session.** Two `main` pushes (`6a54594`, `4d6209a`) produced **no runs at
all**, and the last run created — for `6a27cf7` — sat queued for 3h50m with the annotation *"The job was
not acquired by Runner of type hosted even after multiple attempts."* The cancel API itself returned
HTTP 502.

**Still unresolved at the end of session 7, and the failure has MOVED — check the right thing.** By
21:41 GitHub had resumed *creating* runs (it backfilled queued runs for the two pushes that previously
produced none), but **not one has been acquired by a runner**: three sat `queued` simultaneously, the
oldest at 4h30m. So dispatch recovered and runner acquisition did not. A fresh session will see runs
listed and must not read their existence as recovery — **check `status`, not presence.**

Two corrections to the advice this section previously gave:
- **`gh workflow run ci --ref main` does not work here** — the workflow has no `workflow_dispatch`
  trigger (HTTP 422). An empty commit, or any real push, is the only re-trigger.
- **An empty commit is usually unnecessary.** `main` already contains every merged item, so the next
  real push gives the un-signalled commits their coverage transitively.

**Do not re-diagnose it as a test or config failure**; nothing in the repo caused it, `make check` has
been green at exit 0 on every commit, and the runs before the incident succeeded.

## Blocked items

| Item | Blocked on | Since |
|---|---|---|
| _(none)_ — the run-key question was ratified as D-016 on 2026-08-06 | | |

---

## Open questions

**None.** The run-key question was **ratified by Mit as option (b), pipeline run, on 2026-08-06** — see
**D-016**. Do not re-litigate it. Its analysis is kept below because the rejected options carry the reasons.

### 1. What is a "run"? — RESOLVED 2026-08-06 (D-016): a pipeline run

> **Everything below this line is a FROZEN SNAPSHOT of the problem as it stood before session 4, kept
> because the rejected options carry their reasons. It is NOT a description of the code today, and several
> of its statements are now false:** `insert_run` is called from two places, not one; `run_eligibility`
> *does* take a `run_id`; a batch orchestrator **does** exist in `src/` (`boardwatch run`); and `runs` no
> longer holds 4 rows. Do not act on this section — see "What shipped in session 4" above.

**The problem, as measured before session 4.** `runs` rows are inserted in exactly one place: `insert_run` at
`scan/coordinator.py:104`, inside the scan's own file lock. `run_id` is then threaded as a plain parameter
(no contextvar, no ambient state) through `apply_board` → `append_event`/`record_version_source`. But:

- **Eligibility runs in a different process.** `run_eligibility` (`eligibility/preflight.py:133`) is called
  from `top`, `stats` and `eligibility` preflight — never from `scan`. No `run_id` is in scope there.
- **Tailoring runs in a third process, one posting at a time.** `run_tailor` takes a single `posting_id`;
  **no batch orchestrator exists in `src/`**. The de facto batch driver is `.agent/bin/bw-daily` (`bwd`),
  which is gitignored shell — it just calls `boardwatch tailor run <id> --out ...` in a loop.

So a seven-stage funnel does not correspond to the boundaries of any process that exists. The evidence is
structural, above — no code path puts a `run_id` in scope where evaluations are written. (`runs` holds 4
rows against 20,637 evaluations, but that ratio proves nothing on its own: 4 scan runs could legitimately
produce 20,637 evaluations. It is a symptom, not the measurement.)

**The fork.** (a) `run_id` = the scan run, with downstream writers recording the scan they are working off —
cheap, but an evaluation's "run" then means *the run that captured the version*, not when it was judged.
(b) Broaden `runs` into a **pipeline run**: a new command wrapping scan → eligibility → tailor that owns the
row and emits the artifact — this is what P3 builds anyway, so P0 would be laying P3's foundation early.
(c) Make the funnel a **window** report like `stats`, not run-keyed at all — but then B6 ("funnel reconciles
to a terminal state") has nothing to reconcile *per run*, and PROGRAM.md §3.P0.4's run manifest has no owner.

**Recommendation: (b)**, scoped so P0 does not wait for P3 — introduce the pipeline-run row and the artifact
writer now, have `scan` populate what it owns, and report downstream stages as an explicit `unattributed`
bucket until their writers thread `run_id`. Do **not** silently pick (a): it makes "cache hit" and
"judged during this run" the same number, which is the exact indistinguishability D-013 added the migration
to prevent.

**Status: RATIFIED — (b), by Mit, 2026-08-06, and BUILT in session 4.** Recorded as **D-016**; the
build and its two follow-on decisions are **D-019**, **D-020** and **D-021**. P0 now includes the pipeline-run row
and the funnel artifact writer; this is accepted as *early* P3 work rather than extra work, since P3's "one
command, unattended" needs the same row and the alternative was re-keying at P3.

### 2. ~~`main` is red until this branch merges~~ — RESOLVED, session 3

`main` has been green since `88c98d4` merged. The cause was D-014: program docs carried an absolute
`/Users/<name>` path violating generalization rule R1, so `make check` exited 2 in the generalization
stage before pytest ran. **The lesson that generalizes and is still live: `docs/` IS scanned** —
`tools/generalization/discovery.py` enumerates via `git ls-files` with no exclusion filter, so a
docs-only commit is not exempt from `make check`. Do not re-diagnose the original failure.

### Previously resolved

All four of session 1's questions were answered by Mit on 2026-08-06 — see `PROGRAM.md` §7 and
`DECISIONS.md` D-010/D-011.

Summary of the answers, because they carry program-wide weight:

1. **Reading the job-apps repo is authorized, standing.** It was revoked only for the self-assessment
   session so the plan would be honest. Accompanying standing instruction: **check and verify rather than
   assume** — a failed command is not a negative result, a recalled number is not a measured one.
2. **Two personas (SDE / iOS)** with different protected-fact sets, matching Mit's job-apps setup.
3. **`needs_sponsorship: true` for Mit**, declared knowingly and declared per user — never inferred.
4. **`~/boardwatch-applications/<date>/`** stays the daily output home.

Answers 2 and 3 both carry the same governing rule, now `PROGRAM.md` §3b and D-010: **publish the
generalized mechanism, keep Mit's instance local. This applies system wide.**

---

## Standing facts a fresh session should not re-derive

- **Live urgency.** `STAGE1_ONLY=1` is active in job-apps' launchd plist. Its 08:30 run stops after
  discovery. **Nothing is generating Mit's résumés daily right now.** P1 and P3 close a live gap.
- **The tailoring architecture is already correct.** Typed skeleton, plain-text-only model contract,
  Python-owns-markup, independent entailment judge — all present. Do not rebuild it. (`PROGRAM.md` §5.1.)
- **`typst` is installed** at `/opt/homebrew/bin/typst`. The old "No PDF" silent-degrade code path
  (D-006) was **ELIMINATED by P1a** (D-032, §3.P1 — Gate P1 MET): a PDF-less lead can no longer ship
  silently — a missing binary now raises/aborts the run fatal, a compile failure or page-limit overflow
  now falls back to the untailored master or drops the lead outright, and a `resume_tailored` row always
  has a compliant PDF.
- **`track` exists but has never been used** — `applications` and `application_events` are both 0 rows.
- **`jobs` and `postings` are both 19,448** — `job_id` is 1:1, grouping has never run, duplicate leakage
  is structurally unmeasurable until P6.
- **`make check` is the only real gate.** pytest + ruff + mypy green is not green; the generalization
  checker only runs under `make check`.
- **`.agent/` and `.superpowers/` are gitignored** working material. `CHANGELOG.md` is authoritative for
  what shipped.
