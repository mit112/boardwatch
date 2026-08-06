# PROGRAM STATE — read this first

**Last updated:** 2026-08-06 (session 5, P0 in progress)
**Updated by:** boardwatch (Claude)
**Repo state at write time:** every P0 item claimed done below is merged to `main` **except item 1**,
which is on `p0-funnel-artifact` until that branch merges; the tree is clean.
**This header carries no commit count or sha on purpose** — the previous one named both, went stale inside
a single session when three later docs commits did not update it, and a cold session following the
session-start ritual hit the disagreement on its very first check. State what is durably true; verify the
rest against `git log`. (D-017.)
**Gate:** `make check` exits **0** (2719 passed, coverage 95.05%), measured in plain mode with the real exit code.

> This is the single file a fresh session with zero memory reads to know where the program stands.
> If it disagrees with the repo, **the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Full plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`.

---

## Current phase

**P0 — Instrumentation. IN PROGRESS.** Nothing is blocked.

**Numbering note, because session 4 briefly got this wrong:** P0 has **nine** items, numbered **0-8** in
`PROGRAM.md` §3.P0. Item 0 was added later, by D-016. Always cite `PROGRAM.md`'s numbers — an earlier
version of this file invented its own and collided with them on the gate item.

**Four of the nine are done:** item **0** (the pipeline-run row and `boardwatch run`), item **1** (the
per-run funnel artifact), item **2** (per-rule abstain rate), and item **7** (the `run_id` migration *and*
the threading that populates it).

**Five remain:** item **3** the per-source outcome table, item **4** the run manifest, item **5** the
reconciliation sweep, item **6** the stub rate, item **8** the fabrication counters.

**Gate P0 is still NOT met, and item 1 shipping does not by itself meet it.** `PROGRAM.md` §3.P0 gives
the gate three clauses, and **two are outstanding**:

1. *Three consecutive runs reconciling to 100%.* The artifact that makes this checkable now exists and
   reconciled on three consecutive live runs this session (below) — but those ran `--no-scan` against a
   copy of the production store, so **the scan stage has never been exercised under the gate**. This
   needs three consecutive runs of the real daily driver, which is P3's to schedule.
2. *Why every non-lead was dropped, from the artifact alone.* **Not met.** The ranker does not report how
   many postings it considered, so postings ranked below the `--top` cutoff land in no bucket — 14,873 of
   them on run 6. **P0 item 3 is what closes this**, and it is the next task for that reason.

The third clause — per-rule abstain for every rule in the catalog — **is** met: all 44 are emitted every
run, never-fired ones included.

---

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
- **Only `corpus` and `tailor` are falsifiable stages today.** `attribution` and `verdict` are SQL
  partitions of the set they are compared against and are marked `derived` for that reason (D-023).
  Do not "fix" them into looking like evidence — if a per-source table needs a real check, it needs a
  count through a genuinely different path, as the two cross-checks do.
- **`postings_seen` is not the corpus.** D-022. This will bite again on any per-source denominator:
  a board that answered 304 listed nothing this run but still owns open postings.

Then, still open in P0: item **4** the run manifest (config hash, profile version, catalog version,
code fingerprint, **exit status** — a `runs.status` column belongs there), item **5** the
reconciliation sweep, item **6** the stub rate, and item **8** the fabrication counters.

**Fabrication counters need new typed capture, not a query.** Aggregates die at `cli/tailor_cmd.py:196-204`
and `:407-414` after `console.print`; Tier A's fail-safe (`TierASafetyError`) has no counter anywhere; and
`RewriteRow.drop_reason` is **11** bare untyped strings (measured: 5 direct literals plus 6 distinct `filter:*` reasons). Likewise `disposition='unknown'` conflates **four**
causes separable only by free-text `rationale`, which carries no CHECK constraint — so abstain *rate* is
computable but the typed abstain *reason* the keystone invariant wants is not.

---

## Phase status

| Phase | Status | Gate met? |
|---|---|---|
| P0 Instrumentation | **in progress** — items 0, 1, 2, 7 of 0-8 done | **not met** — needs three consecutive runs of the real driver, scan stage included |
| P1 Résumé artifact gate | not started | — |
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
| **A `SIGKILL`ed run leaves a dangling `runs` row.** `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Observed live: a verification run killed by `timeout` left `finished_at` NULL after writing 11,200 attributed evaluations. **A dangling row is a quarantine with no drain**, which `CLAUDE.md` calls a leak. | A reaper belongs with P3's stale-lock reclaim and the run manifest's exit status, not bolted onto the row's introduction | P3 / P0 item 4 |
| **The general zero-output guard is not built** — bar metric **B5**. Two unambiguous cases ARE fatal now (a systemic scan outage, and every shortlisted lead failing to tailor — D-021). What is missing is the judgement call: deciding when producing nothing was *provably right*. **Do not read exit 0 as "the run produced leads".** | That judgement is cohort completeness, P3 item 9; `PROGRAM.md` assigns B5's guard to P3 | P3 item 5 |
| **`runs` has no `status` column**, so "still running", "crashed" and "finished with errors" are only partly separable. | `PROGRAM.md` §3.P0.4 puts exit status in the run manifest; adding it early would mean designing the manifest twice | P0 item 4 |

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
- **`typst` is installed** at `/opt/homebrew/bin/typst`. "No PDF" is a silent-degrade code path, not a
  missing binary.
- **`track` exists but has never been used** — `applications` and `application_events` are both 0 rows.
- **`jobs` and `postings` are both 19,448** — `job_id` is 1:1, grouping has never run, duplicate leakage
  is structurally unmeasurable until P6.
- **`make check` is the only real gate.** pytest + ruff + mypy green is not green; the generalization
  checker only runs under `make check`.
- **`.agent/` and `.superpowers/` are gitignored** working material. `CHANGELOG.md` is authoritative for
  what shipped.
