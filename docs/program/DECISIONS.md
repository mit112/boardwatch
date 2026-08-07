# Decision log

Append-only. One entry per architectural or program decision, so no decision is re-litigated after a
context reset. Newest last. If a decision is reversed, add a new entry that supersedes it — never edit or
delete the original.

Format: **context** (what forced a choice) · **choice** · **alternatives rejected** · **consequence**.

---

## D-001 — Program machinery lives in `docs/program/`, version-controlled
**2026-08-06 · session 1**

**Context.** The program needs to survive context resets. boardwatch's existing planning material lives in
`.agent/plans/`, which is gitignored.

**Choice.** `docs/program/{PROGRAM,STATE,DECISIONS,METRICS}.md`, version-controlled, plus a repo-root
`CLAUDE.md` (which did not previously exist) carrying the session-start ritual.

**Rejected.** `.agent/plans/` — gitignored, so a decision log there has no history and does not survive a
clone. Existing `docs/` root — that is user-facing product documentation; program management is a
different audience.

**Consequence.** Program docs are diffable and reviewable. `CHANGELOG.md` remains authoritative for
shipped behaviour; these files are authoritative for program state.

---

## D-002 — Output-side phases precede input-side phases
**2026-08-06 · session 1**

**Context.** job-apps' roadmap orders instrumentation → profile → eligibility → liveness/dedup → résumé →
unattended → breadth, on the principle that *breadth multiplies whatever is downstream of it*. That puts
PDF emission at position 5 of 7 while `STAGE1_ONLY=1` means nothing generates Mit's résumés today.

**Choice.** Résumé artifact gate at P1, unattended runner at P3. Breadth stays last.

**Rejected.** job-apps' ordering verbatim — ~4 phases of latency on a live, compounding gap. Also rejected:
putting the unattended runner first, which would run 14 days on a work-auth rule that abstains 100%.

**Consequence.** The ordering principle is preserved. It constrains *input*; PDF emission and unattended
running are output-side terminals that multiply nothing. P1 gives Mit compiled PDFs for his existing manual
workflow within days.

---

## D-003 — The 14-day clock is acceptance-only, never a phase gate
**2026-08-06 · session 1**

**Context.** job-apps' Phase 5 gate is "14 consecutive unattended days meeting the bar." But P4, P5 and P6
all mutate eligibility and the résumé gate.

**Choice.** P3's gate is 7 consecutive unattended runs measuring *operational* stability. The 14-day bar
runs once, after P6, on a frozen system. Any change to eligibility, profile, or the résumé gate during the
run resets the clock, and the reset is recorded in `METRICS.md`.

**Rejected.** Using the acceptance run as a mid-program gate — guarantees either a reset or 14 days of
uninterpretable data.

**Consequence.** One clean measurement instead of several dirty ones. Slightly later first reading.

---

## D-004 — Stub defense: take the metric now, defer the machinery
**2026-08-06 · session 1**

**Context.** job-apps' gap audit calls JD acquisition its single largest missed subsystem (~2,200 lines,
7 modules) and inserts a Phase 1.5 before eligibility, because ~64% of its raw discovery folders held stub
JDs and eligibility precision is unmeasurable on stub inputs.

**Choice.** Add stub rate at judge time as a P0 metric — one number, every run. Defer the recovery chain
to P7, to be built with evidence if and when a non-API source appears.

**Rejected.** Building the chain now. All six boardwatch providers are structured ATS APIs; the stub
pathology comes from LinkedIn/Indeed HTML scraping, which boardwatch does not do. job-apps' own gap audit
§1.1 concedes this: *"If boardwatch is judging its postings on ATS-API JSON only, it may be fine today."*

**Consequence.** Largest ordering departure from the handover. Risk is explicitly monitored rather than
assumed away — if the P0 stub number is ever non-trivial, this decision gets superseded.

---

## D-005 — Do not rebuild the tailoring architecture
**2026-08-06 · session 1**

**Context.** job-apps asserts *"If boardwatch hands a model the Typst source and asks for Typst back, that
is almost certainly the root cause of the quality problem Mit saw"* and prescribes a 10-step port whose
steps 2/3/4/6 rebuild the skeleton/contract/reconstruction/judge layers.

**Choice.** Keep the existing architecture. Verified against the code: `tailor/model.py` defines typed
`Resume/Entry/Bullet(bullet_id)/SkillGroup`; `rewrite/prompt.py` sends one bullet's plain text and demands
*"Return ONLY the reworded bullet as a single line"*; `render/typst.py` emits all markup and escapes every
model-authored token; `rewrite/judge.py` is an independent entailment judge; `safety.py::output_is_entailed`
enforces token-for-token identity modulo an approved equivalence table — stricter than job-apps' provenance
check.

**Rejected.** The port. It would rebuild working, better-guarded code.

**Consequence.** The craft complaint is real but differently caused. Attributed to missing page-count
enforcement (P1) and a missing anti-slop/craft rubric (P4). If P1+P4 land and Mit still judges the output
poor, this decision is the first thing to revisit.

---

## D-006 — The PDF cliff is a silent-degrade defect, not a packaging problem
**2026-08-06 · session 1**

**Context.** job-apps' roadmap §7.1 treats "Typst-only, no binary ⇒ source only, no PDF" as blocking and
prescribes vendoring or containerising the binary.

**Choice.** Treat it as a code defect. `typst` is installed at `/opt/homebrew/bin/typst` and
`reports/tailor.py:104` shells out correctly. The defect is `tailor_cmd.py:193,402` printing *"source only
(no PDF; typst not available or compile failed)"* and continuing — a silent degrade that also conflates an
environment fault with a lead fault. P1 makes PDF emission a hard gate and splits the two causes.

**Rejected.** Vendoring the binary now — solves a distribution problem boardwatch does not currently have.
Deferred to P7-era distribution work.

**Consequence.** P1 shrinks from a packaging project to an afternoon.

---

## D-007 — The work-auth fix is one declared field, not a phase
**2026-08-06 · session 1**

**Context.** job-apps calls the profile object *"the real fix for `ead_or_similar`-never-UNMET… The engine
cannot decide because it has nothing to decide against."*

**Choice.** Add `work_authorization.needs_sponsorship` as a field distinct from `status`, and enforce the
abstain-on-missing-field invariant on the resolver `inputs=` declarations that already exist.

**Rejected.** The diagnosis. `resolve.py:167–177` shows the engine abstains **deliberately**, with reasoning
in a comment: it cannot distinguish an F-1 OPT holder who will need sponsorship from an asylee with an EAD
who needs none. It lacks one disambiguating bit, not a profile object. job-apps' own proposed schema
contains exactly that bit.

**Consequence.** B7 ("work authorization resolved decisively") is cheap. The profile object is still built
in P2 for multi-tenancy and cache-keying — it is just not what fixes work auth.

---

## D-008 — Retire the P12 pre-registered parity comparison
**2026-08-06 · session 1**

**Context.** `.agent/plans/p12-parity-report.md` pre-registers a directional boardwatch-vs-job-apps
comparison with a locked ISO week 2026-W33 and N ≥ 14 days. It was never run. Its Gate-1 rationale rests on
"job-apps' only true applied count is 37 — which equals boardwatch's own north-star 37 built." job-apps
verified the real figure is **388** (369 distinct, 380 with PDFs); 37 was one bucket of its current curated
queue.

**Choice.** Retire it. Replace with the absolute bar in `PROGRAM.md` §1. Leave the file in place, unedited,
as a record of what was believed.

**Rejected.** Repairing the parity design with corrected numbers — the comparison was always a proxy, and
job-apps' funnel (942 candidates → 75 built → 0 applied, queue at 465) shows its volume is not the thing to
match.

**Consequence.** The measurement target becomes absolute and self-contained. Also removes boardwatch's
central breadth defense, which rested on the 37/37 pairing and is now known false.

---

## D-009 — Applied-suppression belongs in P6, and is smaller than described
**2026-08-06 · session 1**

**Context.** job-apps' roadmap §0 trap 1 says to build a disposition write-back path in Phase 5, warning
that without it boardwatch re-surfaces applied roles forever and its dedup can never improve.

**Choice.** Keep the requirement, move it to P6 next to dedup, and scope it to the wiring only.
`boardwatch track add|status|list|log` already writes an immutable `application_events` ledger with attempt
numbers. What is missing is that nothing consumes it — no applied-suppression exists in `queries.py` or
`top_cmd.py`, and `applications` has 0 rows.

**Rejected.** Building a tracker. One exists.

**Consequence.** Smaller task, correctly located beside the identity work it depends on. Note the ledger is
unexercised, so the first real use may surface bugs — budget for that rather than assuming it works.

---

## D-010 — Published mechanism vs. personal instance, system wide
**2026-08-06 · session 1**

**Context.** Mit: *"Eventually the system will adapt to anything the end user asks. So we have to publish
the generalized version while we keep the active work on this machine personal. This applies system wide."*
Asked in the narrow context of persona count, stated as a global constraint.

**Choice.** Every subsystem splits into a published *mechanism* and a local *instance*, and the split is
designed in at the same time as the feature — never retrofitted. Published: persona registry format,
profile schema, universal + field-dependent rule catalogs, seed company registry, equivalence-table and
template formats. Local and never published: Mit's two personas and their protected-fact sets, his profile
values, his 135 imported targets, his authored résumé corpus and immutable facts. Full table in
`PROGRAM.md` §3b.

**Rejected.** Building for Mit first and generalizing later. job-apps is the counter-example: hardcoded
paths, user-specific sacred metrics, and a second tenant (`Hetvi/`) that had to live in a parallel
directory with the shared logic switched off, because the eligibility taxonomy was the thing that would
not port.

**Consequence.** A standing test for every catalog added from here: *could a US-citizen senior nurse use
this without editing code?* If it needs a code change, the catalog is in the wrong half of the split.
Precedent already existed — P8 imported 85 boards as user config and declined registry promotion on
purpose; this makes that instinct a rule.

---

## D-011 — Two personas, and `needs_sponsorship` declared per user
**2026-08-06 · session 1**

**Context.** P4 needs to know how many personas to design for; P2 needs to know whether Mit will declare
`needs_sponsorship`, which is what makes work auth resolve decisively and shrinks his funnel.

**Choice.** Two personas for Mit — **SDE and iOS**, with *different* protected-fact sets, matching his
job-apps setup. `work_authorization.needs_sponsorship: true` for Mit, declared knowingly. Both are local
instances expressed through published mechanisms, per D-010; neither value is ever inferred or defaulted.

**Rejected.** One persona initially — Mit already runs two and expects parity. Inferring sponsorship need
from visa status — the ambiguity that inference would paper over (`resolve.py:167–177`: an F-1 OPT holder
versus an asylee with an EAD) is precisely the thing the field exists to resolve.

**Consequence.** Mit's funnel will shrink when P2 lands and some roles will become genuinely INELIGIBLE
for the first time. That is bar metric B7 working, not a regression — record the before/after counts in
`METRICS.md` so the change is visible rather than alarming.

---

## D-012 — Verify rather than assume, as a program rule
**2026-08-06 · session 1**

**Context.** Three verification failures collided in one session. job-apps reported `ALLOWED_REASONS` did
not exist — its grep died on a zsh glob error and it read the failed command as a negative result; the
symbol exists with exactly 16 members. job-apps reported its applied count as 37; the real figure is 388.
boardwatch had repeated that 37 from recollection into its parity doc and built its entire breadth defense
on it. Mit: *"its better to check and verify instead of making assumptions."*

**Choice.** Adopted as a standing program rule. Before asserting a fact about another repo, a figure, or a
subsystem's behaviour: run the check, and confirm the command actually succeeded. Prefer reading code over
reading a summary of code. Where a claim cannot be verified in-session, label it as recollection rather
than stating it flat.

**Rejected.** Treating it as a one-off correction. All three failures share one shape — trusting a
compressed or failed signal — and it recurs by default.

**Consequence.** `METRICS.md` records `—` for "not emitted" and never `0`, because a zero and an absent
check are indistinguishable otherwise. The same distinction applies to any claim in `STATE.md`.

---

## D-013 — Independent review: verdict APPROVE WITH CHANGES, amendments adopted
**2026-08-06 · session 1**

**Context.** Mit required the plan to be reviewed by an agent with no shared context before approving it.
The reviewer was explicitly briefed that the plan's author has a structural incentive to overstate what
already exists, since every such claim shrinks its own workload, and was told to attack the five
load-bearing factual claims independently against the code.

**Verdict returned: APPROVE WITH CHANGES.** Of the five factual claims: D-004, D-007 and D-009
**VERIFIED**; D-005 and D-006 **OVERSTATED** — both in boardwatch's own favour, exactly the failure D-012
was written to catch. D-004 got *stronger* under attack (0.18% short bodies vs job-apps' 64%, no HTML
page-scraping in any provider).

**Choice.** Adopt all twelve required changes. Three were outright false statements and are corrected in
place; the remaining nine are tracked as a worklist in `STATE.md` and folded into their phases.

Corrected in place:
1. **§5.1 / D-005 is now lane-scoped.** `enforce_tier_a` never runs against Tier B and structurally
   cannot — `reports/tailor.py:17-21` documents this and the original review of the code missed it.
   Tier B has **no** token-provenance validator; step 3's pre-accept compile check and step 6's judge
   batching are also absent. Added as P1 items 3b/3c.
2. **P1's "zero overfull/underfull `hbox`/`vbox`" removed.** Those are LaTeX concepts; `typst 0.15.1`
   exits 0 silently on gross overflow, so the clause was vacuously satisfiable and would have been
   recorded as a pass forever. Replaced with a Typst-native page-count + content-bounds check.
3. **`METRICS.md`'s "P0 is substantially rendering what the schema already records" corrected.** Six
   tables lack `run_id`, and `uq_eligibility_deterministic` means a re-run writes no evaluation rows at
   all. P0 now includes the migration and counts cache hits as an asserted stage.

**Rejected.** Contesting any finding. Each was verified against code or the live DB with a citation, and
two were the reviewer catching precisely the self-serving error it was asked to hunt for.

**Consequence.** The plan is stronger and P1/P2 are larger than first scoped. Two structural gaps that the
first pass missed are now owned: the **severity/policy layer** (all six families default to `preference`,
so 1,427 evaluations with unmet *required* dispositions are still `eligible` and no user but Mit can ever
get an `ineligible`) belongs to P2, and the **persona registry** committed to in D-011 had no phase at all.

---

## D-014 — `main` was red; program docs are subject to the generalization checker
**2026-08-06 · session 2**

**Context.** The first `make check` of session 2 exited **2** in the generalization stage, before pytest
ran. Two violations, both rule R1 (home-directory absolute path), both in files committed by session 1's
`84cfab6`: `PROGRAM.md:4` and `STATE.md:27` cited the job-apps handover as `/Users/<name>/dev/Job apps/...`.
Verified pre-existing against `git show main:...`, not caused by session 2's changes.

**Choice.** Fix both to `~/dev/Job apps/...`, the form R1's own message prescribes (`bc0973d`). Record that
**docs are scanned**: `tools/generalization/discovery.py` enumerates via `git ls-files` with no exclusion
filter, so *everything git-tracked is published* and every tracked file is scanned — `docs/` included.

**Rejected.** Allowlisting the paths. R1 exists to keep one user's home directory out of a shipped repo;
the path added nothing that `~` does not convey. Also rejected: treating it as trivial. Session 1 wrote
"`make check` is the only gate" into `CLAUDE.md` and then committed twice without running it, so the gate
was mandated and skipped in the same commit.

**Consequence.** A docs-only commit is not exempt. Run `make check` before any commit, including docs.
Note the asymmetry that made this survivable: `.md` is **not** in the checker's `DATA_SUFFIXES`, so docs
escape the R7 data-admission rule — but they do *not* escape the R1–R6 shape rules.

---

## D-015 — Migration `run_attribution`: nullable, unnamed inline FK, evaluations + artifacts only
**2026-08-06 · session 2**

**Context.** P0 needs `run_id` on the tables behind the funnel's later stages. Four constraints found by
reading the schema rather than the plan: (1) existing `run_id` FKs are *named*
(`fk_posting_versions_run_id_runs`) but SQLite cannot add a named table-level constraint via
`ALTER TABLE ADD COLUMN`; (2) `test_migrations_match_metadata` asserts
`alembic.compare_metadata(...) == []`, so any name mismatch could fail the drift check; (3)
`eligibility_evaluations` is **append-only** (`eligibility_evaluations_no_update` raises on UPDATE);
(4) `PRAGMA foreign_keys=ON` is set on every connection (`store/db.py:30`).

**Choice.** Two additive `ALTER TABLE ADD COLUMN ... INTEGER REFERENCES runs (id)`, nullable, no default,
no index — the `p2_profile_eligibility` path, no table rebuild. FK is inline and therefore unnamed.
Revision id is **`run_attribution`**, deliberately *not* `p0_*`: the existing `p0_`/`p2_` prefixes denote
boardwatch's earlier *product* phases, and reusing `p0_` for this program's P0 would create a permanent
ambiguity in migration history.

**Verified, not assumed.** The unnamed FK satisfies `test_migrations_match_metadata` and still enforces —
the round-trip test asserts a dangling `run_id` raises `IntegrityError` on both tables. `make check` exits
**0** (2633 passed, coverage 94.98%).

**Rejected.** `batch_alter_table` — a table rebuild would have to reconstruct the partial unique index and
both append-only triggers, against this repo's established additive precedent. An index on `run_id` — no
existing `run_id` column has one, and 20,637 rows scan in well under a millisecond; speculative. `run_id`
on `applications`/`application_events` — both hold **0 rows**, so the column would be speculative; it
lands with the work that first writes them.

**Consequence.** Because the table is append-only, `eligibility_evaluations.run_id` can only ever be set
at INSERT and can **never** be backfilled: the 20,637 existing rows are permanently NULL. NULL therefore
means "written before run attribution existed" and the funnel must report it as its own bucket, never fold
it into a real run's counts. The column alone changes nothing until the write paths thread `run_id` —
`write_evaluation` (`eligibility/engine.py:242`) and `record_artifact` (`store/artifacts.py:17`) currently
take no such parameter.

---

## D-016 — `run_id` means a pipeline run, and P0 introduces it
**2026-08-06 · session 2 · ratified by Mit**

**Context.** P0's funnel artifact needs a key, and no existing process spans the seven stages. `runs` rows
are written in exactly one place — `insert_run` at `scan/coordinator.py:104`, inside the scan's file lock.
Eligibility is judged later, as a preflight side-effect of `top`/`stats` (`eligibility/preflight.py:133`),
with no `run_id` in scope. Tailoring is later still and single-posting (`run_tailor` takes one `posting_id`;
**no batch orchestrator exists in `src/`**). The only thing that stitches them into a pipeline is
`.agent/bin/bw-daily` (`bwd`), which is gitignored shell and not part of the product. The argument is
structural — there is no code path in which a `run_id` is in scope when an evaluation or artifact is
written. (`runs` holds 4 rows against 20,637 evaluations. Do **not** cite that ratio as the proof: 4 scan
runs could legitimately produce 20,637 evaluations. It is consistent with the conclusion, not evidence for
it.)

**Choice.** `run_id` denotes a **pipeline run**: one command that runs scan → eligibility → tailor in
sequence and owns the run identity across all of it. P0 introduces the pipeline-run row and the funnel
artifact writer; `scan` populates the stages it owns; stages whose writers do not yet thread `run_id` are
reported as an explicit `unattributed` bucket rather than as 0.

**Rejected.** (a) *`run_id` = the scan run.* An evaluation would be filed under the run that captured its
posting version rather than the run that judged it, so a past run's report keeps changing days later, and
"already judged, cache hit" becomes indistinguishable from "judged during this run" — the exact
indistinguishability D-013 added the migration to prevent. (b) *A time-window report like `stats`.* Bar
metric B6 is "funnel reconciles 100% to a terminal state", and reconciliation needs a unit; a rolling window
has none. `PROGRAM.md` §3.P0.4's run manifest would have no home, and the `run_attribution` migration would
go unused.

**Consequence.** P0 grows: it now builds a slice of what P3 was scheduled to build. This is accepted as
*early* work rather than *extra* work — P3's "one command, unattended" needs exactly this row, so the
alternative was building a throwaway key in P0 and re-keying at P3. It also puts `bwd` on a path to being
replaced by a shipped command instead of gitignored shell. **Sequencing note:** per-rule abstain rate needs
no `run_id` at all (it is a read over `eligibility_requirements` joined against the catalog enumeration), so
it is built first and de-risks the rest of P0 independently of this decision.

---

## D-017 — second independent review; STATE's own header was the defect
**2026-08-06 · session 3**

**Context.** `p0-instrumentation` was five commits ahead of `main` and green under `make check`, but had
been reviewed only by its author. Mit's standing merge permission requires **both** confidence and review,
so a fresh agent with no shared context reviewed `main..p0-instrumentation` adversarially — the same move
that produced D-013, and for the same reason: this program's documented failure mode is asserting things in
its own favour.

**Outcome: APPROVE WITH CHANGES.** The code half survived unchanged. The reviewer independently confirmed,
against the repo and read-only against the live DB, that the migration is genuinely additive (no
`batch_alter_table`, partial unique index and both append-only triggers intact), that its FK actually
enforces (`store/db.py:30` sets `PRAGMA foreign_keys=ON` per connection), that `downgrade()` is a native
DROP COLUMN that leaves `PRAGMA foreign_key_check` clean, that the test exercises the migration rather than
a fresh schema (`upgrade(BASE)` → seed → `upgrade(HEAD)`), and that the revision chain has exactly one head.
It also re-derived the load-bearing numbers: 6 families / 44 patterns, the never-fired set is **exactly** the
7 rule_ids named, `experience_years:scoped_years_minimum` 11,670/11,670 `unknown`, the index is partial, and
every `file:line` citation in the docs resolves to what the docs claim.

**What it caught — all in the documents, none in the code:**

1. **`STATE.md`'s header was false about the branch it described.** It claimed HEAD `c56bc11` and "2 commits
   ahead" at a tip of `bf25023`, 5 ahead, and pinned the gate result to the older sha. The three docs commits
   that added D-015 and D-016 never updated the header above them. A cold session following the
   session-start ritual would find STATE and the repo disagreeing on the very first check.
2. **`STATE.md`'s phase table contradicted four other places in the same file**, saying P0 items were
   "blocked on open question 1" when that question is D-016-resolved and the blocked-items table said none.
3. `METRICS.md` cited `tables.py` line numbers from *before* this branch shifted them by three — written
   after the shift, checked against the file before it.
4. D-016 and STATE both offered "`runs` has 4 rows vs 20,637 evaluations" as *evidence*. It is not: 4 scan
   runs could legitimately produce 20,637 evaluations. The conclusion stands on the structural argument
   (no code path has a `run_id` in scope at the write site); the ratio is a symptom.
5. `PROGRAM.md` still read "awaiting Mit's approval" after approval.

All five corrected before merge. **The lesson, which is the point of recording this:** the branch's *code*
was reviewed by its author to a standard that held up, and its *documents* were not reviewed at all. In a
program where a document is the read-first source of truth, a stale header is a defect of the same kind as
a broken migration — it is the artifact a fresh session acts on. Treat `STATE.md`'s header as code: it is
now self-flagging, and re-checking it against `git log` is part of editing the file.

---

## D-018 — abstain-rate scope, and the `IN`-clause limit is a repo-wide debt, not this metric's
**2026-08-06 · session 3**

**Context.** The second independent review of session 3 (over `540bb34`, the per-rule abstain rate)
returned APPROVE WITH CHANGES with eight findings, all MINOR. It confirmed the central design holds on
every path — enumeration never re-derives from data, never-fired never folds into 0% — and independently
re-derived all four live numbers. Four findings were fixed in `fc6e8a5`. Two are decisions worth pinning.

**Scope, now stated rather than implied.** The report covers the **current deterministic evaluation of
each OPEN posting**, matching `eligibility summary`. So `never fired` means *never fired in that scope*: a
rule that only ever fired on postings that have since closed reports as never-fired. Live impact is ~1%
(186 closed vs 19,262 open). Accepted rather than widened, because the metric's job is to describe the
catalog against the postings a run would actually judge. The footer now prints the evaluation count, so a
scope of zero cannot be misread as a catalog of dead rules — previously, with no profile at all, it printed
"44 never fired" and exited 0.

**Rejected: chunking the `IN` clause here.** Measured: SQLAlchemy renders expanding `IN` as one bind per
element and SQLite's `SQLITE_LIMIT_VARIABLE_NUMBER` is 32,766; 19,262 evaluations are in scope, so there is
59% headroom and it grows with open postings. It is a real ceiling but not this query's: `abstain_cmd`
calls `current_evaluations` first, which passes a same-sized list to `.in_()` at `eligibility/engine.py:301`,
so `abstain`, `summary` and `top` all fail at the identical threshold, in that earlier call. Fixing it here
would leave the actual failure in place while looking solved. It belongs in a repo-wide chunking helper.

**Also accepted:** `RuleAbstain.other` carries rows whose disposition is outside `met|unmet|unknown`.
Impossible while the DB CHECK holds. Carried anyway because the alternative is that widening that CHECK
silently shrinks every abstain-rate denominator in the report — a lost row does not merely vanish, it
inflates the rates, which is the one number this metric exists to state correctly.

**Standing lesson, second occurrence.** As in D-017, the defects were not in the logic. Two of the four
fixed were *a test that did not pin the fix its own docstring cited* (widening the terminal to 160 columns
dodged the 80-column condition the fix addressed; deleting the fix left the suite green) and *a property
documented as load-bearing that nothing asserted*. A test that cannot fail is documentation with a green
tick next to it. Verify a new test fails without its fix before trusting it.

## D-019 — `run_id` is never NULL on a row written after attribution exists
**2026-08-06 · session 4**

**Context.** D-016 settled that `run_id` denotes a *pipeline* run, and P0 item 0 built the row plus
`boardwatch run`. Threading the column then exposed a second question D-016 did not reach: what should a
stage write when it is invoked **standalone**? `run_eligibility` is a preflight side-effect of `top`,
`export`, `stats` and `eligibility run`; `run_tailor` is invoked directly by `boardwatch tailor run`; the
opt-in LLM lane is invoked by `eligibility extract`. None of those has a pipeline above it. Writing NULL
was the obvious default and it is wrong: the ~20,637 pre-existing rows are permanently NULL and can never
be backfilled (`eligibility_evaluations` is append-only), so NULL already means *predates attribution*.
A second meaning makes the funnel's `unattributed` bucket unreadable — it would mix rows nothing can ever
fix with rows a stage simply declined to attribute.

**Choice.** Every write path either receives a `run_id` or mints one, via `ensure_run`
(`store/queries.py`). A stage run standalone records a **degenerate pipeline run** — one whose other
stages did zero work — which is the direct corollary of Mit's 2026-08-06 ruling that a bare `scan` is a
pipeline run with empty stages, and of his rejection of a `kind` column. One row shape everywhere.
`run_id IS NULL` therefore has exactly one meaning, and it is a closed set that can only shrink.

**Where the ratification came from, since D-016 does not contain it.** Mit was asked directly at the start
of session 4, as two batched questions, and chose (a) the command name `boardwatch run` and (b) *"a bare
`scan` writes a pipeline run with empty stages"* over *"keep it a scan-only row, marked as such with a
`kind` column"*. D-016 ratified only what a run **means**; it says nothing about degenerate runs or a
`kind` column, so those answers are logged here rather than being attributed to it.

**The one guard that keeps this affordable.** `run_eligibility` mints **only once `pending` is non-empty**.
Without that, every `top` invocation would log a run and `runs` would become a command log rather than a
ledger of work. Test-locked: `test_eligibility_with_nothing_pending_mints_no_run`.

**Consequences accepted, both recorded because neither is obviously right.**
1. **A cache hit keeps the *first* run's id.** `record_evaluation` returns early on
   `inserted.rowcount == 0`, so no row is rewritten. Correct per D-016: "cache hit" is its own funnel
   stage counted from that rowcount, never inferred from `run_id`. Reattributing would erase the very
   distinction D-013 added the column to preserve.
2. **A reused master résumé artifact keeps the run that first authored it.**
   `get_or_create_master_artifact` is content-addressed, so `run_id` is recorded on CREATE only. The node
   genuinely was not produced by this run. Counting masters per run needs a separate edge, not an
   overwrite.

**Ownership split in `runs`, required by the same change.** `finalize_run` previously wrote the scan
counts *and* stamped `finished_at`. Under a pipeline that would mean the run finished when scan finished,
so it gained `finished: bool = True` and the owner calls the new `finish_run` instead. The bare
`boardwatch scan` contract is untouched: the insert stays **inside** the lock, so a scan rejected for
contention still writes nothing at all (`tests/pipeline/test_scan_lock.py` continues to assert this).

**Rejected.** *Writing NULL from standalone stages and filtering in the funnel.* It cannot be filtered —
nothing distinguishes the two NULL populations. *A `kind` column on `runs`.* Ruled out by Mit on the same
day: it forces every downstream funnel query to carry a qualifier, for a distinction that is already
visible in the stage counts themselves.

---

## D-020 — the scan stage creates the run row; the pipeline finishes it
**2026-08-06 · session 4 · adopted from an independent review**

**Context.** D-019's first implementation had `boardwatch run` mint the `runs` row before calling
`run_scan`. A review with no shared context found that this silently discarded two properties the scan
path had been carefully built to have. `scan_cmd.py` deliberately calls `build_context(..., ensure=False)`
because `run_scan` runs `ensure_schema` **inside** the file lock (`coordinator.py`: *"deferred to inside
the lock: a REJECTED scan writes nothing"*). Minting first meant `boardwatch run` migrated the live
database **outside** that lock — against a possibly-running older binary — and stranded a `runs` row
whenever the lock was held. `tests/pipeline/test_scan_lock.py` asserts the zero-write property for `scan`
only, so nothing caught it.

**Choice.** The scan stage creates the row and exposes it as `ScanSummary.run_id`; the pipeline adopts
that id and stamps `finished_at` at the end. `run_scan`'s `run_id` parameter is gone, replaced by
`finish: bool = True`. With `--no-scan` there is no lock to sit inside, so the pipeline mints its own.

**This is not the option D-016 rejected.** That option was `run_id` **denoting** the scan run, so an
evaluation would be filed under the run that captured its posting version rather than the run that judged
it. Here the id still denotes the pipeline; only the INSERT moves, to the one place already holding a lock
that makes it safe. Who executes the INSERT and what the id means are independent questions, and conflating
them is what made the first implementation look correct.

**Consequence, and it is an improvement.** A contended `boardwatch run` now writes **nothing at all**,
which is strictly stronger than closing an orphan row out. Pinned by a **new** test,
`test_a_contended_pipeline_writes_no_run_row_at_all` in `tests/pipeline/test_pipeline_run.py`.
`tests/pipeline/test_scan_lock.py` was **not** changed — it still covers bare `scan` only, which is why it
never caught this.

**Also adopted from the same review, each a real defect:**

1. **Scan errors were recorded twice.** The scan stage persists its own into `errors_json`; `finish_run`
   *appends*; the pipeline passed the same list again. Any per-run error count was 2× for scan errors and
   1× for tailor errors — uninterpretable. The pipeline now passes only errors raised after scan.
2. **`boardwatch run` would have exited 1 on essentially every real run.** Per-board failures land in
   `summary.errors`, and across 85 watched boards a few dead ones are documented as normal; `boardwatch
   scan` exits 0 for exactly the same condition. `PipelineSummary` now separates `errors` (everything, for
   the ledger) from `fatal` (the one thing that fails the run). An exit status that is 1 every day carries
   no information — the same signal destruction the run ledger exists to prevent.
3. **A dangling run row on any unexpected exception.** Only two abort paths closed the row; a malformed
   taxonomy or a Ctrl-C during the multi-minute tailor loop left `finished_at` NULL, which `doctor`
   reports as in-progress forever, one more row per retry. Now a `try/finally`.
4. **`shortlisted` measured the `--top` flag, not a funnel stage** — `len(ranked.visible)` is capped at
   the limit. The ranker's `hidden_ineligible` and `hidden_non_swe`, the actual denominators, were being
   discarded. All three are now carried.
5. **`doctor` mislabelled every unfinished run as a scan.** Since attribution, an unfinished run is also a
   pipeline still tailoring. Users were sent looking for a held scan lock that was free.
6. **Failed leads left empty folders** in `~/boardwatch-applications/<date>/`. Counting the deliverable by
   listing that directory is the obvious independent check, and a husk inflated it.
7. **`eligibility extract` minted a run unconditionally**, contradicting the lazy-mint rule stated for
   `run_eligibility` in the same change: a provider outage would file a finished run attributing zero
   rows. Now minted on the first posting actually reached.
8. **`date.today()` was the only local-clock read in `src/`.** An evening run wrote leads to one date's
   folder while its run row recorded the next day's UTC timestamp. Now `utcnow().date()`.

**Known gap this does NOT close, stated rather than papered over.** `try/finally` closes the run row on
exceptions and on Ctrl-C. It cannot close it on `SIGKILL`. This was observed live, not theorised: a
verification run against a copy of the real store was killed by a `timeout` after writing 11,200 attributed
evaluations, and left its run row with `finished_at` NULL. **A dangling run row is a quarantine with no
drain**, which `CLAUDE.md` names as a leak, and there is no reaper on either side of the gate. It belongs
with P3's lock work (stale reclaim by atomic rename) and with the run manifest's exit status — filed there,
not bolted on here.

**Two of the review's findings were tests of mine that could not fail** — the third and fourth
consecutive occurrence of this class (D-017, D-018). One asserted `summary.evaluated` against the *same*
query that produced it (`X == X`) while its docstring claimed it counted through a different path. The
other asserted `boards_attempted == 0`, which is the value `insert_run` writes at birth: deleting
`finalize_run` **entirely** left it green. Both were mutation-checked and both passed the mutation I chose,
because I mutated the half the test did pin. **The lesson sharpens: a mutation test proves the mutation is
caught, not that the docstring is true.** Pick the mutation from the claim, not from the code.


---

## D-021 — second review: the exit-code fix had over-corrected into bar metric B5
**2026-08-06 · session 4 · adopted from a second independent review**

**Context.** D-020 fixed "`boardwatch run` exits 1 on essentially every real run" by making only a *fatal*
condition fail the run. A second review, on the fix commit, found the correction had gone too far the other
way: `fatal` was assigned in exactly one place (no profile), so **a total DNS/network outage exited 0** with
a success line, and so did **every lead failing to tailor**. `CLAUDE.md`'s own fail-safe table says
*"systemic outage ⇒ fatal (prevents the silent empty day)"*, and bar metric **B5** is literally *"a run that
succeeds while producing nothing"*. The `CHANGELOG` entry claiming "1 only if the run is fatally broken" was
false for the two most fatal conditions there are.

**Choice.** Two further fatal conditions, both narrow and both read off outcomes rather than a status field:

1. **Systemic scan outage** — boards were attempted and *not one* completed or came back unchanged. A few
   rotten slugs among 85 stay non-fatal; zero successes is the network.
2. **Every shortlisted lead failed to tailor** — zero leads from a *non-empty* shortlist is a broken résumé
   path, not an honest empty day.

**Deliberately still NOT built:** the general zero-output guard, i.e. deciding when producing nothing was
*provably right*. That needs cohort completeness (P3 item 9) and `PROGRAM.md` assigns B5's guard to P3.
The two cases above are the ones where "nothing" is unambiguously a fault, so they do not require that
judgement. **Recorded in `STATE.md`'s known-gaps table so exit 0 is not misread as "produced leads".**

**The other seven findings, all adopted:**

- **D-020's own dangling-row fix had a hole.** The pipeline's `try/finally` begins *after* `run_scan`
  returns, but the row is now created *inside* `run_scan` — so Ctrl-C during the multi-board fetch loop
  stranded exactly the row D-020 claimed to have closed. On an exception the caller cannot learn the id
  (nothing is returned), so the scan now closes the row itself, unconditionally, even when `finish=False`.
- **A crashed run read as a clean empty run.** The `finally` stamped `finished_at` and discarded the
  exception it had in scope. Now recorded into `errors_json`.
- **Three tests were making live HTTP calls to `boards-api.greenhouse.io`** — the seeded company is a real
  watched greenhouse board and the scan stage was not mocked, unlike every other scan test in the repo.
  Offline or sandboxed CI would have burned ~90s per test on retries and gone red for the network.
- **The test named for board failures never failed a board.** It used an unknown *provider*, which takes a
  branch that deliberately never increments `failed` — so `scan_boards_failed` stayed 0 and was pinned by
  nothing. Now a mocked 500 on a real provider.
- **The exit-1 path had no test at all**; deleting it left the suite green. 0 and 2 were pinned, 1 was not.
- **The "lazy" mint in `eligibility extract` could never be lazy** — the list is non-empty and the budget is
  `ge=1`, so it always minted on the first iteration. Rather than fake laziness, the rule is now stated
  honestly: the id must exist *before* a row can carry it, so this lane mints per invocation, and that is
  correct **here** because `extract` is an explicit user action whose failure belongs in the ledger.
  `run_eligibility` fires incidentally on every `top`, which is why its rule differs. The two invocations
  differ, so the two rules differ.
- **`--no-scan` migrates the schema unlocked**, exactly as every other read command does. Not a regression,
  but the `CHANGELOG`'s "no window in which the schema is migrated before the lock is held" was true only
  of the default path. Reworded.

**The meta-point, and the reason this decision exists rather than a quiet fixup.** Two reviews on one
change found nineteen defects between them, and **the second review's most severe finding was a defect in
the first review's fix.** A fix is new code and inherits none of the reviewed status of what it repairs.
Re-review after a substantial fix round; do not treat "adopted all findings" as terminal.

---

## D-022 — the funnel's head is the open-posting corpus, not scan throughput
**2026-08-06 · session 5 · P0 item 1**

**Context.** `PROGRAM.md` §3.P0.1 names the stages `observed → unique → candidates → …`, and the obvious
reading is that `observed` is `ScanSummary.postings_seen` flowing into the next stage. Measured before
building: **`postings_seen` and `open_postings` are different populations.** `postings_seen` accumulates
`result.listed` per board — a board that returns **304 unchanged lists nothing** — while `open_postings` is
a whole-DB `COUNT(*) WHERE status='open'` taken after the fetch loop. On a `--no-scan` run `postings_seen`
is 0 against a corpus of ~19,000.

Chaining them would have produced a funnel edge whose drop bucket was **negative on most real runs**, and
the reconciliation would have been reported as a failure of the pipeline rather than of the arithmetic.

**Choice.** The funnel's head is the **open-posting corpus**, which is the population eligibility actually
judges. Scan counts are emitted as **context**, in their own block, explicitly labelled as throughput and
not as a funnel edge. Rejected: normalising the two into a common population (would need per-board
attribution that does not exist until P0 item 3), and dropping scan from the artifact (the operator needs
to know 5 of 85 boards were dead).

## D-023 — a stage reports `None` when unmeasured, and says when its balance is bookkeeping
**2026-08-06 · session 5 · P0 item 1**

**Context.** Gate P0 wants "the funnel reconciles to 100%". Two ways to pass that gate dishonestly emerged
while building it, and both are the same failure the abstain report already guards against.

1. **A stage nobody instrumented reporting 0.** Dedup has never run — `jobs` and `postings` are 1:1 — so a
   `duplicates_dropped: 0` would assert *boardwatch measured dedup and found none*, the opposite of the
   truth, and would count towards the gate.
2. **A stage that balances by construction**, in either of two ways. `pdf`'s `no_pdf` and `applied`'s
   `not_marked_applied` are remainders of the other buckets; `attribution` and `verdict` are SQL
   *partitions of the very set they are compared against*, and `shortlist`'s `entered` is the sum of the
   ranker's own three outcomes. None of them **can** fail to reconcile. Presenting their green ticks
   beside the ones that can fail inflates the evidence.

**Choice.** `Stage.entered/advanced` are `int | None`; `reconciled` returns **`None`** when unmeasured, not
`True`, so an uninstrumented stage is excluded from the gate rather than silently passing it. Stages whose
balance is arithmetic carry **`derived: true`** and render as `yes (derived)`. The genuinely falsifiable
reconciliations are `corpus`, `attribution` and `verdict`, plus two **cross-checks** that recount `tailored`
and `leads_with_pdf` from the store — `CLAUDE.md`'s "count the deliverable through a different path".

The genuinely falsifiable reconciliations are **`corpus`** — its `no_current_evaluation` is an independent
sweep over a different table expression — and **`tailor`**, plus the two cross-checks. Everything else is
bookkeeping and is labelled as such, and the artifact prints the falsifiable list so a reader never has to
derive it. **One consequence is NOT accounted for anywhere yet:** `shortlist` no longer absorbs postings
ranked below the `--top` cutoff into a remainder, so those postings now sit in no bucket at all. That is an
honest gap rather than a fabricated balance, and P0 item 3 owns it.

This is the same rule as `abstain_rate is None` for a never-fired rule, applied one level up. Consequence
accepted: `reconciles` is False whenever a recount disagrees, even though every stage balances — which is
the point, since a self-report that agrees with itself is not evidence.

**A test-design note worth keeping.** The store module's docstring claims `no_current_evaluation` is an
independent sweep (a `NOT IN` subquery) rather than `open_postings - evaluated`. Every test passed with that claim
mutated to subtraction — the claim was documented and unpinned. Pinning it needed a corpus that genuinely
**cannot** partition (one posting carrying two current-identity evaluations, which slips past the partial
unique index because it keys on `input_id`): the sweep reports `reconciles False`, subtraction reports
`True` by construction. **Derive the mutation from the sentence, not from the code** — again.

## D-024 — the artifact is written from the `finally`, and never fails the run
**2026-08-06 · session 5 · P0 item 1**

**Context.** Where to emit decides what is diagnosable. Writing on the success path only would leave every
crashed run — the ones worth diagnosing — with no artifact. Writing before `finish_run` would stamp every
artifact with `finished_at: null`, reporting each run as still in progress.

**Choice.** The write happens in the **same `finally` that closes the run row, immediately after
`finish_run`**, so a run that raised partway still explains how far it got and still carries a real
finish time. The call is wrapped in `try/except` that prints and swallows: that block can run **while an
exception is propagating**, and raising there would replace the real cause of the failure with a reporting
error, or discard already-produced leads on a healthy run. Reporting is not the deliverable.

Written to `<out_root>/<date>/funnel-<run_id>.{json,md}` — **outside the git tree**, beside the day's
tailored résumés. Generalization rule R7 requires a sha256-pinned `SHIPPED_DATA` entry for any tracked
`.json`, which a per-run artifact can never satisfy. Named by run id, not by date, so two runs in one day
do not overwrite each other.

## D-025 — mutation testing has two failure modes that both report a false PASS
**2026-08-06 · session 5 · process, learned the expensive way**

**Context.** `CLAUDE.md` and D-020 already require confirming a test fails without its fix. This session
showed the *procedure* for doing that is itself capable of lying, twice, in opposite directions.

**1. Restoring with `git checkout -- src/` discards uncommitted fixes.** Mid-review I mutated a source
file, checked the result, then "restored" it with `git checkout`. The fixes from the review round were
still uncommitted, so the restore silently reverted them to the last commit. Two subsequent mutation
results were then read against the **pre-fix** code and recorded as findings that were not real.
**Commit before mutating, or back the file up outside git.**

**2. Rewriting a source file in a loop leaves stale bytecode.** A mutate → test → `cp` back cycle
produced a running module that was a *hybrid* — `inspect.getsource` showed the new source while the
executing code object came from a cached `.pyc`. The tell was a stage whose `entered` matched the old
implementation and whose drop count matched the new one, which no single version of the file could
produce. One test then failed under `make check` having passed in isolation minutes earlier, and one
mutation was recorded as CAUGHT that a clean re-run reports as SURVIVED. **Clear `__pycache__` between
mutations, and re-confirm any surprising result in isolation with a cold cache.**

**Choice.** Mutation runs follow a fixed shape: commit first · back up outside the tree · one mutation
· clear `__pycache__` · run ONE test · restore · clear again. A batched loop over many mutations is
what hid both failures here; when a batch disagrees with an isolated run, **the isolated run wins**.

**Why this is a decision and not a note.** The whole point of mutation-checking is that it is the
evidence a test is real. Evidence gathered by a procedure that can silently report the wrong answer is
worth less than no evidence, because it is trusted. Both failure modes are silent and neither shows up
as an error.

## D-026 — `assisted` is as unmeasurable as `unique`, and both report `None`
**2026-08-06 · session 6 · P0 item 3**

**Context.** `PROGRAM.md` §3.P0.3 specifies the per-source table's columns as
`unique | assisted | eligible | leads | applied`, inherited verbatim from job-apps' roadmap §3.2. D-023
had already established that `unique` reports *not instrumented* because dedup is P6 and has never run.
`assisted` was assumed to be a different kind of quantity and therefore measurable.

**It is not.** job-apps' own text says what it means: *"Assisted-touch accounting matters — a source that
always arrives second gets credited nothing by naive attribution, which is how job-apps nearly cut a
working adapter."* `assisted` credits a source that arrived **second** for a posting some other source
won. It is a dedup-attribution quantity, exactly like `unique`, and it presupposes that one posting can be
seen by more than one source.

boardwatch cannot express that. `jobs` and `postings` are 1:1, and a posting carries a single
`company_id`. There is no second source to credit, so `assisted` has no measurable value until P6 lands
dedup and grouping.

**Choice.** **Both columns report `None` — never 0.** Per D-023's rule, 0 is not a weaker claim than
`None`, it is a *different* claim: `assisted: 0` asserts that no source ever arrived second. That is
precisely the naive attribution job-apps records as having nearly cost it a working adapter, so shipping
it as a number would reproduce the failure the column exists to prevent.

**Alternatives rejected.**
- *Drop both columns.* Silently departs from the spec'd column list, and loses the visible P6 placeholder
  that tells a reader the quantity is owed rather than irrelevant.
- *Interpret `assisted` as "evaluated"* — i.e. postings the engine judged. It is a real number and it is
  already in the funnel's verdict stage, but it is **not what the word means**, and renaming a measurable
  quantity into a slot reserved for an unmeasurable one is how a gate gets passed by a metric that does
  not measure the thing.

**Consequence.** Three of the five spec'd columns carry numbers today. P0 item 3 is complete as specified;
the two `None`s are P6's to fill, and the artifact says so in its own prose rather than in a code comment.

## D-027 — the shortlist stage becomes evidence, by rooting it at what the ranker considered
**2026-08-06 · session 6 · P0 item 3**

**Context.** D-023 marked `shortlist` `derived` because its `entered` was the sum of the ranker's own
outcomes, so its balance held by construction. Worse, the ranker reported only two of its four exits:
`passes_hard_filters` vetoes and everything below the `--top` cutoff each `continue`d with no counter.
On a measured run at `--top 5` that was **15,959 of 19,262 open postings in no bucket at all** — 11,517
hard-filter vetoes and 4,442 below the cutoff — and it is why Gate P0's *"why every non-lead was dropped"*
clause was not met. (An earlier figure of 14,873 circulated in these documents. It was never measured: it
is `18,174 − 3,301`, a derived estimate from a different run at a different `--top`. Cite the measured
numbers.)

**Choice.** `rank_open_postings` now counts **all five exits plus the population it considered**. Five,
not four: the `--new` narrowing was already an uncounted exit before this change, so the ranker had five
ways out and reported two.
`entered` is `len(rows)` — the ranker's own fetch — measured independently of the loop that produces the
drops. So `considered == shortlisted + every drop` is a **genuinely falsifiable identity**: it breaks if a
`continue` is ever added without a counter, which is the only realistic way postings start going missing
again. The stage is therefore **not** `derived`, and it is the first stage besides `corpus` and `tailor`
that the artifact lists as one whose balance could actually have failed.

`skipped_not_new` is its own bucket even though no pipeline caller passes `only_new`. The `continue` it
counts is **pre-existing**, not new here — it was simply never counted. An identity that holds for one
caller and not another is not an identity, and `top --new` is a real caller.

**Alternatives rejected.** *Compute the cutoff bucket as `considered - shortlisted - other drops`.* That
is the remainder pattern D-023 exists to forbid: it makes the stage balance for every possible input, so it
could never catch the very defect it was added to catch.

**Consequence.** Gate P0 clause 2 is closed *mechanically*. The clause is met when a run's artifact shows
it, which is the live-run evidence recorded in `METRICS.md`, not this entry.

## D-028 — only one per-source total was worth reconciling, and the first attempt could not fail
**2026-08-06 · session 6 · P0 item 3 · corrected the same session, after review**

**Context.** Adding a per-board `GROUP BY` invites the obvious check: does the table sum to the funnel's
total? Two `SourceTotal`s shipped — `eligible` and `leads` — and this entry originally argued that both
could genuinely fail because the per-source sweep "travels through the `companies` join, which the funnel's
stages never touch". **That argument was wrong, and an independent review caught it the same session.**

**What was actually true.** `eligible_by_company` groups the *very same* `_current_identity_evaluations`
subquery that the verdict stage counts, by `postings.company_id`, joined to `postings` on its primary key
— a join that can neither lose nor duplicate a row. `companies` is never joined in any counting sweep; it
is read once, at the end, for display labels. And `postings.company_id` is `NOT NULL` behind an enforced
foreign key (`PRAGMA foreign_keys=ON`), so the orphaned-company state this entry named as the failure mode
**cannot occur at all**. Worse, the assembly step keeps a row whose company lookup misses and labels it
`unknown`, so its count is still summed — which would neutralise the check even if the state were
reachable.

So `sum(per_source.eligible) == verdict.eligible` held for every possible database state. It was an
unfailable assertion presented as evidence: precisely the defect **D-023** exists to forbid, reintroduced
one entry after being written down.

**Choice.** **The `eligible` total is deleted, not downgraded.** D-023 deleted two `*_reconciles`
properties rather than keep them as decoration, and the same applies here.

**`leads` survives**, because its two sides genuinely have different shapes: `COUNT(*)` of
`resume_tailored` rows carrying this `run_id`, against `COUNT(DISTINCT postings.id)` resolved through
`posting_versions`. It can disagree in two ways — an artifact whose `posting_version_id` is NULL resolves
to no board, and two artifacts for one posting in one run collapse to a single distinct posting. Neither
is reachable through the current tailor path, so **the artifact describes it as a guard against a future
writer, not as live evidence.** That is a weaker claim than the one first shipped, and it is the true one.

**`applied` is deliberately NOT reconciled.** It counts DISTINCT job ids per board, and summing per-board
distinct counts is not the global distinct count if a job ever spans two boards. `jobs`/`postings` being
1:1 makes that impossible today, but shipping an identity that depends on an accident of current data is
how a check becomes a false green later.

**The retraction took three passes, and that is the more useful lesson.** Correcting this entry and the
`CHANGELOG` left the same false reasoning rendered into every funnel artifact and stated in
`SourceTotal`'s docstring; a re-review then found it still alive in `count_by_source`'s docstring, at the
query site — and a docs-only review then found a **sixth** copy, in a comment at the assembly step 90
lines below the docstring that had just been corrected to say the opposite.

**One claim, six homes:** this entry, the changelog, the prose the program prints, `SourceTotal`'s
docstring, `count_by_source`'s docstring, and a comment beside the assembly loop. It also reached
`PROGRAM.md`, which cites this entry as the authority for a reconciliation this entry deletes. Retracting
a claim means grepping for it, not editing the document you wrote it in — and each pass that "finished"
the retraction was wrong.

**The rest of the lesson.** *"Counts through a different path"* is not
satisfied by grouping the same query differently. A different **path** means a different table expression
that can disagree — the way `no_current_evaluation` is its own `NOT IN` sweep. Grouping by a foreign key
on a table you already joined is the same path with a different `GROUP BY`. The reasoning was written into
a decision entry and a CHANGELOG entry before it was checked, which is D-021's rule ignored: **a fix is
new code and its documentation is new prose; neither inherits the reviewed status of what it repairs.**

---

## D-029 — `runs.status` is a closed catalog whose DEFAULT carries the meaning
**2026-08-06 · session 7 · P0 item 4 (first half)**

**Context.** `PROGRAM.md` §3.P0.4 puts exit status in the run manifest. `runs` recorded only
`started_at`, `finished_at` and `errors_json`, so "finished clean", "finished with errors", "crashed" and
"still running" were not separable in the ledger — `STATE.md`'s gap table names this and parks it here.

**Choice.** A `status` column over the closed catalog `running | ok | failed`, enforced in Python by
`UnknownRunStatusError` at the write site. **Not** a `CHECK` constraint: adding one to an existing SQLite
table costs a full rebuild, and six tables carry an FK to `runs.id`.

**The default is the load-bearing part, not the column.** A SIGKILL never reaches the pipeline's
`finally`, so no code can ever set a terminal status for a killed run — whatever the column defaults to
*is* what a killed run says forever. `running` keeps such a row saying `running` with `finished_at` NULL;
`ok` would launder a killed run into a clean one. This is why the column belongs to the manifest rather
than being bolted onto the row's introduction: the question it answers is "what does an un-updated row
mean", and that has exactly one chance to be decided.

**Status tracks `fatal`, not `errors`.** A run that loses one lead to a tailor failure is a successful run
with an error. Binding status to `summary.fatal` means the ledger's status and the artifact's FATAL line
cannot disagree about the same run — a test asserts that equivalence rather than the two values
separately.

**Alternatives rejected.** Inferring status from `finished_at`/`errors_json` at read time — that is the
"inferrable-but-wrong" shape, and it cannot represent a killed run at all. A `CHECK` constraint — see the
rebuild cost above.

**What review caught, and it is the real lesson.** Two write paths recorded a *failed* run as `ok`, both
by inheriting the new parameter's default:

- the scan's own abort handler (`scan/coordinator.py`) closes the row on Ctrl-C, and under
  `boardwatch run` the scan is called **outside** the pipeline's `try`, so that handler is the only place
  a scan abort is ever recorded and no funnel artifact exists to contradict it;
- a *total* scan outage on the standalone path, which `run_pipeline` already classifies as fatal — so the
  same event recorded `ok` under `boardwatch scan` and `failed` under `boardwatch run`.

**Adding a defaulted parameter to a shared writer silently backfills that default into every existing
caller.** The two callers that needed a non-default were exactly the two failure paths. A new column with
a safe-looking default is not additive at the call sites; each one is a decision.

**Scope, stated honestly.** `running` + `finished_at` NULL means only *nothing closed this row* — a run in
flight, a killed run, and a standalone lane that raised between `ensure_run` and its own `finish_run`
(`reports/tailor.py`, `eligibility/preflight.py`, `cli/eligibility_cmd.py` all call it on the success path
only) share that signature. Separating them needs P3's reaper. **This column does not claim to.**

**Item 4 is HALF done.** The manifest itself — config hash, and emission as an artifact section with
`ARTIFACT_VERSION` 2→3 — is not built. Do not mark item 4 complete.

## D-030 — the run manifest ships two hashes, closing the profile-row gap rather than only noting it

**Context.** P0 item 4's remaining half — the config hash and the artifact section — carried one open
scope call (recorded at session-7 handoff): the manifest's "profile version" is `profile_hash`, an
eligibility-*facts* hash, and the ranker reads five profile columns (`skills`, `target_titles`,
`exclude_titles`, `locations`, `remote_only`) that no existing hash covers. `exclude_titles` alone drives
the single largest drop in the funnel (session 7: 11,517 rejections), so a manifest carrying only
`profile_hash` would report two runs as identical while the setting responsible for that drop changed
underneath it. The fork: ship the config hash and *document* the gap, or add a profile-row hash and *close*
it.

**Choice: close it.** `get_profile(conn)` was already in scope in `funnel_writer`, so `profile_row_hash`
over the five columns is a few lines and needs no new query. Shipping it is strictly more instrumentation
than documenting a gap, and it directly answers the measured problem. The manifest therefore carries BOTH
`profile_facts_hash` (what eligibility scoped by) and `profile_row_hash` (what the ranker read). The one
residual gap that is NOT closed — the **skill-taxonomy version** (`taxonomy.yaml` can change which postings
score as covered without moving either hash) — is stated in the artifact's own manifest note rather than
left implicit.

**The config hash is a closed catalog that fails on drift.** `reports/manifest.py` encodes the METRICS
§"Session 7" classification of all 13 `Settings` + 8 `LLMTier` fields as IN/OUT sets, and `config_hash`
raises `UnclassifiedSettingError` if any field is in neither. A `Settings` field added later cannot be
swept silently into or out of the hash — the build breaks until someone decides whether it changes which
postings become leads. `rules_hash` (covering `{catalog_version, catalog_source, policy}`) is carried in
preference to the bare `RulesCatalog.version`, as the session-7 analysis recommended.

**Stub definition (item 6): an OPEN posting whose `body_text` is empty after trimming.** `body_text` is
NOT NULL, so a stub is a whitespace-only body, never a missing row; the numerator is denominated over
`count_open_postings` so the two share the corpus head. The query uses SQLite's **two-arg** `trim` with an
explicit strip set (` \t\n\r\f\v`) — the one-arg form removes spaces only, so a tab/newline body would
otherwise slip through as non-empty (caught by a test that inserts exactly that). §6 correction 4: this is
insurance, expected near zero for structured ATS JSON.

**Fabrication counters (item 8): the Tier-B `drop_reason` strings are mapped into a closed outcome
catalog** in `build_fabrication_counters`, with `judge_rejected` and `overmatch_filtered` (the two truth
gates B4 measures) counted apart from the `budget`/`error`/`no_candidate` fallbacks. Any `drop_reason` the
catalog does not name lands in `other` and prints a FAILURE line — out-of-catalog is a failure, never a
new bucket (`CLAUDE.md`). Tier A is structural and cannot fabricate, so it is not counted; its own
`TierASafetyError` fail-safe still has no counter, which remains a stated gap.

**Item 5 (the reconciliation sweep) was deliberately NOT folded into artifact v3.** It is a DB-rows-vs-
on-disk-artifacts invariant sweep counting through a different path; the artifact's existing `cross_checks`
are per-run pipeline-memory-vs-store. Keeping them separate means item 5 ships as a standalone verifier and
does not collide with the v3 batch. It is the next P0 item.

---

## D-031 — `boardwatch verify` is a standalone DB↔artifact reconciliation sweep, supplementing Gate P0 rather than re-anchoring it

**Context.** P0 item 5, the last build item, needed a home. D-030 already ruled out folding it into the
funnel artifact: the artifact's `cross_checks` run in-process, at write time, comparing pipeline memory to
the store; item 5 crosses the serialize-then-reload boundary — it reads the **frozen artifact off disk**
and re-derives its run-keyed quantities from the DB **now** — and it touches the filesystem, which no
in-process check does. It needs no `ARTIFACT_VERSION` bump: it consumes the artifact, it does not extend
it.

**Choice: `boardwatch verify`, a standalone command; a supplement to Gate P0, not a re-anchor.** The
in-artifact cross-checks remain the per-run reconciliation and Gate P0 stays met exactly as recorded
(D-030, three consecutive real runs). `verify` adds a DB-vs-disk layer as an additional on-demand guard.
Gate P0's reconciliation clause is not re-expressed as "`verify` exits 0" — that would move the goalposts
onto a check invented after the gate was already met.

**Two invariant classes, deliberately asymmetric in what they check.**

- **Class A — frozen artifact vs. fresh DB re-query, scoped to four `run_id`-filtered fields that cannot
  legitimately change after the run finished:** `cross_checks["tailored"].from_store` against
  `COUNT(*) WHERE run_id=X AND kind='resume_tailored'`; `cross_checks["leads_with_pdf"].from_store` against
  the pdf-built count; `len(leads)` against `COUNT(DISTINCT posting_version_id)`; and `manifest.status`
  against `runs.status`. This is a **serialize-then-reload consistency check, not a "different path"** — for
  immutable run-keyed rows the re-query equals the frozen value unless the write serialized a different
  number than it stamped, or the row was later mutated/deleted. Both are real defects worth catching, but
  the "different path" mandate is satisfied by Class B, not Class A.
- **Class B — DB vs. filesystem, the load-bearing "different path."** For every `artifacts` row with
  `run_id=X AND kind IN ('resume_tailored', 'resume_tailored_llm')` — **both** tailored kinds, since Tier B
  (`resume_tailored_llm`) also writes a run-keyed `.typ` deliverable and a Tier-A-only scan would silently
  miss a missing Tier-B file — assert the `.typ` at `uri` exists, and where `meta_json.typst_pdf_built` is
  truthy, assert the file at **`meta_json.pdf_uri`** exists. The PDF path is read explicitly rather than
  derived by extension-swapping a "sibling" path, because the pipeline is free to write PDFs elsewhere and a
  guessed path would false-positive on every row. `resume_tailored_llm` carries no `pdf_uri`, so its Class-B
  check is `.typ`-only.

**Explicitly excluded, with reasons, so a future reader does not "strengthen" this into a tautology or a
flake:**

- **`judged_this_run` (the eval count) is NOT reconciled.** It comes from `count_corpus`, scoped to open
  postings' current version under the deterministic engine identity
  (`engine_kind`/`profile_hash`/`rules_hash`/version). A naive `COUNT(*) FROM eligibility_evaluations WHERE
  run_id=X` counts a broader population — LLM-lane rows, closed postings, non-current versions — so it would
  false-positive the moment the LLM eligibility lane writes a row. Faithfully re-deriving the identity-scoped
  number would mean replicating the producer's own subquery, i.e. re-treading the same path §9 of the design
  forbids as a tautology. Dropped rather than shipped unsound.
- **`started_at`/`finished_at` are NOT reconciled.** They are scalars copied verbatim from the same
  immutable `runs` row this re-query reads (near-tautological), and comparing an `isoformat()` string
  against SQLite's `YYYY-MM-DD HH:MM:SS.sss` serialization is a false-positive generator for timestamps that
  are actually equal. Dropped rather than papered over with canonicalization for a check that barely earns
  its place.
- **Whole-DB / time-varying fields are NOT reconciled** — `corpus.*`, `marked_applied`,
  `unattributed_evaluations`, `stub_rate.*`, `sources[*]`, the abstain report — comparing them would produce
  spurious failures on any store that kept working after the run.

This is the mirror image of the trap D-023/D-028 killed: there the danger was a check that *cannot* fail;
here it is a check that fails for the *wrong* reason. Both are unsound in the same way and are handled the
same way — deleted, not downgraded.

**Behaviour: two modes, each with its own enumeration source and exit policy.**

- **`verify --run <id>`** locates the artifact by **globbing `<out_root>/*/funnel-<id>.json`** — the exact
  numeric filename, so `funnel-7` never matches `funnel-70` — rather than reconstructing the path from the
  run's start date. The glob still finds an artifact whose `runs` row was later deleted, which is exactly
  the orphaned-artifact case a `STATUS_MISMATCH` (`run_status=""`) exists to surface. If no file is found,
  that is a `NO_ARTIFACT` discrepancy → non-zero exit: a request to verify a specific run that cannot be
  verified is a failure of the request, not a silent skip.
- **`verify` (sweep)** enumerates the `funnel-*.json` files actually present on disk and verifies each. It
  does **not** enumerate the `runs` table and demand an artifact per row — runs 1–4 (pre-item-1) and any
  dangling run legitimately have no artifact and never will, so demanding one would make the sweep
  permanently non-zero for reasons unrelated to any real defect. A run with no on-disk artifact is out of
  the sweep's scope: not a silent PASS, simply never examined, and the summary states how many artifacts
  were found and checked.
- **Exit policy, both modes:** exit 0 iff every *examined* artifact reconciles with zero discrepancies;
  non-zero on any discrepancy, where "discrepancy" includes `NO_ARTIFACT` (`--run` mode) and
  `MALFORMED_FUNNEL` (either mode). `verify` reports, it never "fixes" — a disagreement is made visible, not
  silently resolved.

**Closed `DiscrepancyKind` catalog** (constructed at the raise site, so out-of-catalog is impossible):
`NO_ARTIFACT`, `MALFORMED_FUNNEL` (a parse/field failure maps to a typed kind rather than crashing the
sweep — a truncated write, disk-full, or manual edit becomes visible, not an unhandled exception),
`TAILORED_COUNT_MISMATCH`, `PDF_COUNT_MISMATCH`, `LEAD_COUNT_MISMATCH`, `STATUS_MISMATCH` (skipped, not
failed, for v2 artifacts with no manifest), `MISSING_TYP_FILE`, `MISSING_PDF_FILE`. There is no
`TIMESTAMP_MISMATCH` and no `EVAL_COUNT_MISMATCH` — both were designed, found unsound, and dropped before
shipping (above).

**Shape mirrors item 1's pure/query/glue split** (`reports/reconcile.py` pure; `store/reconcile_queries.py`
the independent `run_id`-scoped re-query reads, deliberately a different query surface from
`run_funnel_queries.py` so Class A does not recount through the same code the artifact used;
`cli/verify_cmd.py` the glue). Read-only throughout — no write path, no mutation of the store or the
artifacts, no re-running of `collect_run_funnel` (that would be the same-path tautology this whole design
avoids).

**Verified on the real store, 2026-08-07:** `verify` (sweep) checked runs 5, 6, 7, 9, 10 — all reconcile,
exit 0 (5–7 are v2, `STATUS_MISMATCH` correctly skipped for lack of a manifest; 9–10 are v3, all four
Class-A checks plus Class-B file existence passed); the dangling run 8 (no artifact) was correctly out of
the sweep's scope. `verify --run 9` → exit 0. `verify --run 8` (the dangling run) → exit 1, a single
`NO_ARTIFACT` discrepancy — confirming unverifiable is never a silent PASS. Read-only: no store changes.

**Consequence.** Gate P0 is unaffected — it was already MET on D-030's three-run evidence. `verify` is
additional, on-demand, unit-tested-under-`make check` coverage of a failure mode (DB row present, file
missing) the gate's own evidence never had to exercise. `docs/program/` carries this decision; the design
lived in gitignored `.superpowers/sdd/p0-item5-reconciliation/design.md` per `CLAUDE.md`.

---

## D-032 — P1a ships a hard PDF gate as impure-runner/pure-policy, splits P1b out, and closes D-006's silent degrade
**2026-08-07 · session 9**

**Context.** P1's five clauses (PROGRAM.md §3.P1, items 1–5) are not homogeneous. Items 1, 2, 3, 3b, 4 and
5 are all artifact-integrity — a lead either has a compliant PDF or it does not, checkable mechanically.
Item 3c (Tier-B token-provenance validator) is a truth gate feeding bar metric B4, is design-heavy on its
own (a fabricated claim like *"single-handedly re-architected … eliminating downtime"* passes today's
overmatch filter because it permits new ordinary lowercase words), and gates nothing in Gate P1 as written.

**Choice — decompose into P1a (this build) and P1b (deferred).** P1a ships items 1/2/3/3b/4/5 and MEETS
Gate P1 on its own. Item 4 (slot-filled) folds in as a trivial build-time assertion rather than its own
slice. P1b (item 3c) is brainstormed separately after P1a ships — see design §9 for its shape (a closed
fabrication-lexicon veto plus verb-swap provenance, slotting into `run_tier_b_core` after
`passes_overmatch_filter`, before the judge).

**Sub-decisions, all recorded together because one design produced them:**

- **Page count is Typst-native, via `typst eval` on an injected `<total-pages>` metadata label**
  (`TypstRenderer.emit` appends the label so every emitted résumé is queryable), spiked live against typst
  0.15.1 before building. **Overflow == `page_count > N`.** NOT PDF byte-parsing (fragile across
  compression/object-streams) and NOT a new Python PDF dependency. LaTeX `hbox`/`vbox` overfull is
  **vacuous in Typst** — 0.15.1 exits 0 with no diagnostic on a deliberately overflowing document — so "0
  overfull boxes" is honestly re-expressed as "rendered page count == N." Horizontal overflow of an
  unbreakable token is out of scope (typst will not flag it; the captured compile log is the diagnostic if
  it ever appears).
- **`resume_max_pages` is a new profile column** (additive Alembic migration, nullable, default 1 for
  new-grad), wired into `save_profile`/`get_profile`/`ProfileInput`/`profile edit`. Kept **OUT of
  `profile_row_hash`** — page count is a tailoring/render knob, not a ranker input, and multi-tenancy
  demands it be per-user (a senior's résumé is legitimately 2 pages), not a global `Settings` constant.
- **Impure runner, pure policy.** `_default_runner` (`reports/tailor.py`) returns a `CompileOutcome` —
  facts only, no `resume_max_pages` in scope, so it can never decide "too long." `evaluate_compile`
  (`reports/resume_gate.py`) is the pure function that turns an outcome + `max_pages` into a `GateResult`.
  Closed catalogs `CompileReason` (`OK` / `BINARY_MISSING` / `COMPILE_FAILED`) and `GateReason` (adds
  `PAGE_LIMIT_EXCEEDED`) — no string-matching to classify a failure. `CompileOutcome.__post_init__`
  enforces its own invariant (`OK` iff `pdf_path`/`page_count` are both set) so a fabricated/buggy runner
  cannot smuggle an inconsistent outcome past the gate.
- **Binary-missing is FATAL; compile-failure/overflow is per-lead.** `BINARY_MISSING` is an environment
  fault — raises `TypstUnavailableError`, the pipeline aborts the whole run (`summary.fatal`), the CLI
  exits non-zero with install guidance. `doctor` catches it proactively; the runtime raise is the backstop,
  not a third mechanism. A `COMPILE_FAILED` or `PAGE_LIMIT_EXCEEDED` on the *tailored* résumé is a lead
  fault: it triggers the untailored-master fallback (below), never a run-level abort. Tier-B is the one
  exception inside the per-lead branch — its own `BINARY_MISSING` still re-raises fatal rather than
  degrading to the Tier-A bullet, because the environment-fault split is absolute and must not be
  swallowed by the Tier-B degrade branch (adopted from the design's unbiased review, Major finding).
- **Untailored-master fallback, and a dropped lead writes NO artifact and leaves NO folder.** Tailored
  not-shippable → render the untailored master and gate it too; shippable → record the artifact with
  `meta.degraded = true` and the tailored `GateReason` as `meta.degrade_reason` (a plain compliant résumé
  beats none); also not shippable → drop the lead via a typed `LeadArtifactError`, writing no
  `resume_tailored` row and leaving no lead folder (the pipeline's existing `_remove_if_empty` cleans the
  husk). This is the fix for **D-006**: the old `tailor_cmd.py` behaviour printed *"source only (no PDF;
  typst not available or compile failed)"* and continued with exit 0. That silent degrade is gone — a
  `resume_tailored` row now always has a compiled, page-compliant PDF, and the run only reports success on
  leads that actually have one. The full compile log (both attempts) is written to a durable
  `<day_dir>/_failed/<slug>.log` before the drop, so "compile log captured per lead" holds even for dropped
  leads.
- **Slot-filled assertion ships as a standalone `validate_slots(resume)` function, NOT a `Resume`
  `model_validator` as design §4.6 specified.** The goal is unchanged from the design — assert a filled
  header, ≥1 entry, ≥1 bullet per entry, non-blank bullet text, fail-closed. The mechanism changed during
  the build: a `model_validator` runs on *every* construction, including legitimately-partial intermediate
  `Resume` models built mid-tailoring, and raises pydantic's own error type, not the repo's. `validate_slots`
  is instead called once, explicitly, at the render gate on the fully-tailored model, and raises the
  repo's typed `ResumeValidationError` there — treated exactly like a compile failure (fallback → possibly
  drop) rather than rejecting a partial construction that was never meant to be shippable.
- **Typst packaging: Dockerfile layer pins the same 0.15.1 binary as local, plus a `doctor` version
  probe.** An older/newer typst may accept `compile` but break the `eval` page-count query syntax, which
  would silently make every lead fall back or drop with no obvious cause — so `doctor` warns loudly on a
  version mismatch, not just on a missing binary, folded into the existing non-zero-exit gate.

**Lesson from Task 5's fix round, generalizable beyond this feature.** Wiring an environment probe
(`shutil.which("typst")` / `typst --version`) into `doctor` coupled **pre-existing, unrelated** tests
(`test_doctor.py`'s board-health/schema/integrity suite) to whatever typst toolchain happens to be on the
machine running `make check` — they invoke `doctor` end-to-end and so silently depended on a real local
binary that has nothing to do with what they claim to test. Fixed by an `autouse` fixture in
`test_doctor.py` that monkeypatches `check_typst()` to a canned healthy result, isolating those tests from
the local toolchain; `test_doctor_typst.py` alone exercises the real probe (including a present-but-broken
binary, which is now a hard failure, not folded into the "unknown version" warning). **The generalizable
rule: any command-level test that transitively calls a newly-added environment probe must isolate that
probe with a fixture, or the suite silently stops being toolchain-independent.**

**Rejected.** Vendoring typst into `pyproject` — it is a system binary; Dockerfile + `doctor` is the
P1-era answer, vendoring stays P7. A third preflight mechanism beyond the `TypstUnavailableError` raise
and `doctor` — redundant with both. Reconciling `PAGE_LIMIT_EXCEEDED` differently for Tier A vs. treating
it as a lead-fault everywhere — Tier B never triggers the untailored-master fallback or a lead drop; it
just omits its overlay PDF and records `degraded`/absence in `llm_meta`, since Tier A is the base and Tier
B is strictly additive.

**Consequence — Gate P1 is MET.** Deterministic tests pin every branch with fabricated `CompileOutcome`s
(`tests/unit/test_resume_gate.py`, `tests/unit/test_run_tailor_gate.py`, `tests/pipeline/test_run_pdf_gate.py`,
`tests/unit/test_typst_runner.py`, `tests/unit/test_doctor_typst.py`) — binary-missing-fatal,
compile-failure→untailored-fallback, page-limit→untailored-fallback, both-unshippable→drop-with-no-artifact,
Tier-B binary-missing re-raising fatal instead of degrading. Real-data dogfood (`METRICS.md` §"Session 9 —
P1a dogfood") confirmed **both** directions on the live store: at the profile's shipped default
(`resume_max_pages=1`), all 3 shortlisted leads correctly triggered the FATAL every-lead-failed path
because Mit's own authored `resume.yaml` compiles to 2 pages — independently confirmed via a direct
`typst compile` + `typst eval` outside the app, and via `boardwatch verify --run 11` reconciling on the
0-tailored, 0-PDF result, with the drop-cleanup leaving no lead folders. On an isolated copy of the same
store (`--data-dir`, live DB never touched) with `resume_max_pages=2`, all 3 leads shipped a PDF, each
independently confirmed at page count 2 by both `typst eval` and a raw PDF byte-scan for `/Type /Page`
markers, each with a `typst-compile.log`, and `boardwatch verify --run 12` reconciled through the
DB-re-query path. **A live, actionable finding, not a code defect:** Mit's real résumé content does not
fit in the new-grad default of 1 page, so `boardwatch run` on his real profile will drop every lead until
either the résumé is shortened or `resume_max_pages` is set to 2 — recorded in `STATE.md`'s next action
rather than silently worked around.

---

## D-033 — Tier-B reword provenance: a deterministic allowlist, fail-closed to Tier-A, counted separately from B4
**2026-08-07 · session 10 · P1b, closes PROGRAM.md §3.P1 item 3c**

**Context.** D-032 split P1 into P1a (shipped) and P1b (item 3c, deferred): the Tier-B LLM-rewording lane
had no token-provenance validator, so a fabricated reword like *"single-handedly re-architected … eliminating
downtime"* passed the existing overmatch filter, which only vetoes ALLCAPS/entity additions and permits new
ordinary lowercase words. Design (`.superpowers/sdd/p1b-tier-b-provenance/design.md`) sketched three
approaches: (A) a fabrication-phrase blocklist, (B) a deterministic provenance allowlist fail-closed to the
structural Tier-A bullet, (C) judge independence (a second, differently-configured judge). An unbiased
review by `deepseek-v4-flash`, run before planning, falsified the draft's own soundness claim.

**Choice — approach B.** Every content token in a reword must be justified as one of exactly three kinds:
a source token, an approved equivalence-table image, or a member of a closed, versioned connective allowlist
of claim-free structural words (articles/prepositions/coordinators only — `the a an of to for and or with in
on at from by as that`). Any other content token vetoes the reword; the bullet keeps its Tier-A text. Chosen
over (A) — a blocklist is exactly the pattern this repo already rejected once, in P7b's Tier-B build (the
allowlist-not-blocklist lesson): a closed permit-list of justification sources is
sound in a way an open-ended list of forbidden phrases can never be, because growing what a blocklist misses
is unbounded while growing what an allowlist permits is a deliberate, auditable edit. Over (C) — judge
independence is a real complement (a second judge configuration catching what the first misses) but is a
separate, later change; it does not remove the need for a deterministic floor Tier B can be shipped with
today.

**No stemmer; no modals or auxiliaries — both were shown, not assumed, to let fabrications through.** An
earlier draft justified a `b`-side token that shared a stem with a source token, and separately allowed
modal/auxiliary verbs into the connective set. The unbiased review broke both with concrete cases:

- **Verb → agent-noun via a stem.** Source *"Architected the service"* → reword *"Architect of the service"*.
  `Architected` and `Architect` share the stem `architect`, so a naive stemmer justifies `Architect` — but a
  verb and an agent noun/title are different claims (did the work vs. holds the role). Same hole for
  `Managed`→`Manager`, `Developed`→`Developer`.
- **Future-commitment fabrication via a modal.** Source *"Implemented the checkout flow"* → reword *"Will
  implement the checkout flow"*. If `will` were in the connective allowlist (it looked structural, like
  `the`/`of`), the check would justify it — but a future commitment is not the same claim as a completed one.

Both fixes make the check strictly *source-token / equivalence-image / claim-free-connective, nothing
derived* — which is what makes the fail-closed soundness claim ("a fabrication cannot pass") actually hold.
A tense variant with no table pair (`optimize`→`optimized`) is therefore also vetoed; there is no morphology
escape hatch, only the equivalence table.

**Where it slots.** In `tailor/rewrite/lane.py::run_tier_b_core`, immediately after `passes_overmatch_filter`
succeeds and **before** the entailment judge call, so a fabricated reword never spends a judge call and the
gate does not depend on the same model that proposed the reword also catching it. Also wired into
`tailor/rewrite/agent_lane.py::screen_candidates` (the agent-lane `screen` step), so the no-API-key lane gets
identical early feedback. Both lanes converge on `run_tier_b_core`, so the veto covers both call paths from
one insertion.

**Closed-catalog bookkeeping.** `drop_reason == "provenance"` joins the existing closed set (`judge`,
`unchanged`, `filter:*`, …) in `reports/tailor.py`'s `op` classifier and `cli/tailor_cmd.py`'s
`fallback:{drop_reason}` tag — no string-matching, a new member is a visible, wired decision. A **separate**
`FabricationCounters.provenance_rejected` counter (P0 item 8's home) records it, reported on its own line in
the funnel Markdown. **It is deliberately NOT folded into `rejected`**, the B4-facing fabrication numerator
(`rejected = judge_rejected + overmatch_filtered`): provenance is intentionally over-broad — `optimize`→
`improve` is a *documented, intended* veto, not a caught fabrication — so summing it in would inflate B4
with conservative false-vetoes and obscure the true fabrication-catch rate. A conservative veto is not a
caught fabrication; they are different signals and are reported as such.

**Versioned data, and cache invalidation.** The connective allowlist ships as a frozenset constant with its
own `PROVENANCE_VERSION` (`"p1b-provenance-1"`), recorded in `llm_meta` alongside the existing
`llm_lane_version` so an artifact proves which version of the gate ran — the published mechanism, tuned by
data Mit (or any user) can edit, per PROGRAM.md §3b. `LLM_LANE_VERSION` bumped `"tier-b-1"` → `"tier-b-2"` so
cached Tier-B outputs from before the gate existed are invalidated rather than silently trusted.

**The honest cost, recorded so it is never later "discovered" as a bug.** The gate is deliberately
aggressive: even a benign synonym or a plain tense change — `optimize`→`improve`, `optimize`→`optimized` — is
vetoed today and reverts to the Tier-A bullet, because neither has an approved equivalence-table pair yet.
Tier-B rewording only grows more useful as the equivalence table is curated with specific, deliberate swaps.
This is accepted, not a defect: Tier B is opt-in, the Tier-A bullet it falls back to is already structurally
sound, and the alternative — permitting synonym drift without an explicit approval — is exactly the
fabrication channel B4 exists to close. Matches `CLAUDE.md`'s fail-safe table verbatim: *"fabrication check ⇒
fail-safe (drop tailoring, emit static)."*

**Rejected.** (A) Blocklist — repo allowlist-not-blocklist lesson. (C) Judge independence — real, deferred,
not a substitute for a deterministic floor. A stemmer/morphology justification — unsound (verb→agent-noun).
Modals/auxiliaries in the connective set — unsound (future-commitment fabrication). Case-sensitive source
matching to close the `US`→`us` case-fold collision — accepted as a low-impact minor instead (the overmatch
filter already gates ALLCAPS/entity *additions*; this is only a fold collision on a token already present),
rather than spuriously vetoing ordinary sentence-initial capitalization changes.

**Consequence.** `make check` exits 0 (2846 passed, 1 deselected, coverage 95.20%, `generalization: OK`) —
see `METRICS.md`. **PROGRAM.md §3.P1 item 3c is DONE; Gate P1 was already MET (D-032) and P1b does not
change that standing — it closes the one item Gate P1's own text did not require. P1 (P1a + P1b) is now
fully complete.** Verified only by deterministic unit and lane-integration tests, mutation-checked per the
task brief (fabrication-hole regressions, judge-not-called-on-veto, counter-not-folded-into-`rejected`); no
live Tier-B LLM run was exercised this session — say so rather than inventing a dogfood, per D-012.

## D-034 — `needs_sponsorship` is an orthogonal bit on the work-auth fact, and it only decides sponsorship rules

**2026-08-07 · session 10 · P2 (item 2, the first P2a slice).**

**Context.** PROGRAM.md §3.P2 item 2 calls for `work_authorization.needs_sponsorship` as a field distinct
from `status`. Today it is entangled: `needs_sponsorship` is one *value* of the `status` enum
(`rules.yaml:77`), so an `ead_or_similar` (EAD / F-1 OPT) holder cannot state a sponsorship need
independently of status, and `_resolve_work_auth` is forced to `UNKNOWN` for them (`resolve.py:174-177`:
"authorization is conditional; a sponsorship need cannot be ruled out"). The keystone abstain is correct but
undecidable-by-construction, not by fact.

**Choice.** Add `needs_sponsorship: bool | None = None` to `WorkAuthFact` (nested — it threads through the
already-declared `work_authorization` input and the identity hash automatically). In `_resolve_work_auth`,
use it **only in the `sponsorship_unavailable` sub-branch**: `True → UNMET`, `False → MET`, `None → the exact
prior status-based inference` (so behaviour is byte-identical when the bit is unset). It disentangles the
OPT-holder case: `ead_or_similar` + `needs_sponsorship=False` now resolves `MET` instead of abstaining.

**Two safety properties, both verified (one by an independent reviewer mutation).** (1) The bit **never**
influences a citizenship/authorization verdict — every path in the sponsorship branch returns before
fall-through, and `needs_sponsorship` is read nowhere else, so `needs_sponsorship=False` cannot satisfy a
"US citizens only" restriction (an EAD holder who needs no sponsorship is still not a citizen — the exact
failure `facts.py:3-6` warns against). (2) With the bit `None`, behaviour is byte-identical to before.

**Deliberately scoped.** The `sponsorship_available` sub-branch is left untouched — the literal
`True→UNMET/False→MET` mapping would invert polarity there (an *offer* + needing sponsorship is MET, not
UNMET). And no cross-field coherence guard for self-contradictory combos (citizen + `needs_sponsorship=True`)
— it only ever yields `UNMET` on that one requirement, never a wrong `ELIGIBLE`, mirroring the absence of a
`status`/`jurisdiction` coherence check today. Both are flagged follow-ups, not this change.

**Alternatives rejected.** A bare `needs_sponsorship` bool used broadly (rejected: `facts.py:3-6` — it would
wrongly satisfy citizenship rules). Fail-safe: the bit can only turn a forced abstain into a user-declared
decision in the sponsorship branch; it never makes eligibility less conservative on citizenship.

This is the first P2a (fail-safe) slice; the rest of P2 (typed keystone-abstain enforcement, facts
`schema_version`, and the fail-dangerous P2b severity-default / taxonomy decisions) is tracked in
`.superpowers/sdd/p2-profile-keystone/design.md` and STATE's next-action.
