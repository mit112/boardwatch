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

## D-035 — `work_auth` ships `default_policy: blocker`; the other five families stay `preference`

**2026-08-07 · session 11 · P2 (item 7, the fail-dangerous P2b severity-default slice).**

**Context.** PROGRAM.md §3.P2 item 7 named the actual reason `ineligible` was unreachable: the severity
*mechanism* was already correct and tested (`engine.py:227-238` — `blocker` + `required` + `unmet` →
`ineligible`), but all six families shipped `default_policy: preference` (`rules.yaml`), so a fresh,
policy-less profile got **0 `ineligible` ever**. Mit was unaffected only because he sets `work_auth:
blocker` by hand; a new F-1/OPT or citizen user was not. That is the multi-tenancy requirement failing at
exactly the point `CLAUDE.md` forbids — a monitoring failure dressed as conservatism.

**Choice.** Flip only `work_auth`'s `default_policy` from `preference` to `blocker` (`rules.yaml:72`).
Leave all five other families (`experience_years`, `clearance`, `degree`, `contract_not_fte`,
`internship`) at `preference`. Rationale for singling out `work_auth`: it is the canonical hard stop
(bar metric B7), the most-developed family (suppressors, jurisdiction scoping, negation handling, the
P2a `needs_sponsorship` bit from D-034), and it is keystone-gated — `_resolve_work_auth` (`resolve.py:146`)
returns `UNKNOWN` when `facts.work_authorization` is absent, never `unmet`, so the family can only ever
decide `ineligible` when the user has actually declared a work-auth fact that is genuinely unmet. The other
five are false-skip-risky (a wrong `blocker` default there silently deletes real jobs on a shaky pattern)
and stay opt-in pending Mit's per-family review — this decision does not resolve them, it resolves the one
family the keystone and the corpus both support flipping today.

**Mechanism vs. assignment.** Nothing in `engine.py`, `resolve.py`, or the roll-up changed. `rules.yaml`'s
`default_policy` field already existed and was already read by `catalog.materialised_policy` and honored by
`evaluate`'s roll-up; only the *value* on one family's declaration moved. This is the "sane per-field
defaults ship; the assignment is the user's" split PROGRAM.md §3b already called for — it was simply never
exercised because every family's shipped assignment was the same conservative value.

**Verified.** `evaluate(body, facts, Policy(), catalog)` — the bare, override-free default a fresh profile
actually gets — now returns `ineligible` for a profile declaring `work_authorization.needs_sponsorship`
against a JD containing a genuine no-sponsorship restriction, with the `ineligible` row's `jd_locator`
carrying a real, non-empty span into the frozen JD. The same JD under the same shipped default returns
`eligible` for a US-citizen profile and `ineligible` for an F-1/OPT (`ead_or_similar` +
`needs_sponsorship=True`) profile — two profiles, one posting, two different and individually correct
verdicts (Gate P2's headline, partial: the third roadmap profile, a non-SWE field, needs the still-deferred
`career.field` taxonomy, item 4). The keystone guard was independently re-verified under the new default: a
profile that declares no `work_authorization` fact at all, against the identical JD, still resolves
`uncertain` — never `ineligible` — because the resolver's absent-fact branch returns `UNKNOWN`, and
`UNKNOWN` + `blocker` rolls up to `uncertain`, not `ineligible`, in the roll-up's `blocking()` any() test.

**Fallout, investigated rather than patched over.** One existing test
(`test_a_refusal_to_engage_contractors_is_not_a_contractor_role`, `tests/pipeline/test_eligibility_new_families.py`)
asserted an overall `verdict() == "eligible"` for a corpus sentence about refusing contractors that also,
incidentally, contains a genuine sponsorship-refusal clause ("...not able to sponsor visas, including
CPT/OPT..."). Its facts fixture (`FTE_ONLY`) declares no `work_authorization`, so under the new default the
posting correctly abstains to `uncertain` on that clause — a true finding, not a regression. The test's
actual intent (proving the `contract_not_fte` suppressor does not misfire on this sentence) was already
isolated by its `rows()` helper, which filters to the two P9 families only; `verdict()` had no equivalent
isolation. Fixed by isolating `verdict()`'s policy for this one case (`work_auth: preference` alongside the
existing `contract_not_fte`/`internship` overrides), matching the isolation the file's own comments already
prescribed for `rows()` — not by weakening the assertion.

**Generalization pin.** `rules.yaml` is a sha256-pinned shipped taxonomy (D-P2-7,
`tools/generalization/allowlists.py`); the pin was recomputed and updated to match the new file content.

**Rejected.** Flipping all six families to `blocker` — rejected outright by the brief as the false-skip-risky
direction the other five families exist to avoid; not evaluated further. Flipping none and only improving
reporting — rejected because it leaves Gate P2's headline (a fresh profile returns decisive `INELIGIBLE`)
permanently unmet; reporting a problem is not the same as fixing the one instance that is safe to fix now.

**Consequence.** `make check` exits 0 (2860 passed, 1 deselected, coverage 95.35%, `generalization: OK`).
PROGRAM.md §3.P2 item 7 is DONE for `work_auth`; the other five families' severity decision remains open,
tracked as before. This closes Gate P2's headline metric (B7: work-auth decisive) for the canonical hard
stop; the remaining Gate P2 clauses (items 3, 4, 6, and the three-profile/non-SWE-field leg) are unchanged
by this session and still open.

## D-036 — `eligible` with zero fired requirements renders distinctly from `eligible` with cleared ones

**2026-08-07 · session 12 · P2 (item 6, "no flags" != cleared).**

**Context.** PROGRAM.md §3.P2 item 6 calls for an evidence chain for `ELIGIBLE` too: "which rule cleared
which requirement... 'No flags' != cleared" (CLAUDE.md's own keystone-adjacent invariant). The gap was
narrower than a missing evidence chain — the four-table chain already exists and `AuditView.requirements`
already carries either the cleared rows or an empty tuple. The gap was purely presentational: `engine.py`'s
roll-up (`detect.py:27`: "zero rows stores `eligible`... never 'a clean bill of health'") defaults to
`eligible` whether zero rules fired or N fired and all cleared, and `show`'s render
(`cli/show_cmd.py::_render_audit`) printed the bare `f"Eligibility: {audit.verdict}"` for both, so the two
cases were indistinguishable on screen even though the requirement-row count needed to tell them apart was
already sitting in `AuditView.requirements`.

**Choice (revised after fix round 1 below — see that section for what changed and why).** A derived, typed
classification, `VerdictPresentation` (`StrEnum`, matching this repo's existing convention for small typed
classifications — `GateReason`, `CompileReason`, `DiscrepancyKind`, `BoardHealth`), as a `@property` on
`AuditView` (`eligibility/audit.py`), plus a `met_count` property counting only rows disposed `met`. For an
`eligible` verdict: zero requirement rows → `ELIGIBLE_NO_RULES_APPLIED`; one or more rows and every one
disposed `met` → `ELIGIBLE_CLEARED`; one or more rows but at least one NOT `met` (a non-blocking
`preference`-family `unmet`/`unknown` row, D-035) → `ELIGIBLE_MIXED`. `ineligible`/`uncertain` pass through
unchanged as `INELIGIBLE`/`UNCERTAIN`. It reads only fields `AuditView` already has (`verdict`,
`requirements`) — no new stored column, no migration, no change to `engine.py`'s roll-up or to the stored
`verdict` string. `show`'s `_render_audit` switches on `.presentation` to header "eligible — no eligibility
rule applied (not screened)", "eligible — N requirement(s) cleared" (only when every row is `met`), or
"eligible — N requirement(s) evaluated (M cleared; see details)" for the mixed case, leaving the
ineligible/uncertain and evidence-line rendering below it untouched.

**Scope.** Only the primary deterministic render path (`show <id>`'s `_render_audit`) was changed.
`_render_llm_audit` (the opt-in, advisory LLM lane, D-P3-13) was deliberately left alone: it is a secondary,
dimmed, clearly-labeled-advisory surface next to the authoritative verdict, not the primary "is this
`eligible` a residue or a clearance" question item 6 is about; if Mit wants the same distinction there,
that is a small follow-up, not a blocker.

**Verified.** `AuditView.presentation` is exercised directly (`tests/unit/test_eligibility_audit_presentation.py`,
pure dataclass construction, no DB) for all four outcomes, plus an integration pair in
`tests/pipeline/test_eligibility_flow.py` that runs the real deterministic engine end to end (`eligibility
run` + `show`) against a body with zero catalog matches (`PLAIN_BODY`) and a body with one cleared
`degree` requirement (`DEGREE_BODY`), asserting the CLI's rendered string in each case. The classification
was mutation-tested: inverting the `if self.requirements` branch flips all five of these tests to failing,
confirming they discriminate the two `eligible` cases rather than passing vacuously. `git diff
src/boardwatch/eligibility/engine.py` and every prior test asserting a bare `verdict == "eligible"` are
unchanged by this session — the stored verdict and the engine's roll-up logic were never touched, only a
new read-only presentation layer was added on top.

**Rejected.** A schema change (a stored `cleared_by_rules` column, or a fourth verdict value) — rejected as
unnecessary: the requirement-row count needed to derive the distinction was already persisted and readable
via the existing `AuditView.requirements` tuple, so a schema change would only add migration risk for no
new information. A plain `bool` property (`cleared_by_rules`) instead of the 3-member-relevant enum — also
considered, but the enum reads directly in the render's `match`-like `if/elif` without re-deriving the
ineligible/uncertain cases, and matches the repo's established `StrEnum` idiom for exactly this kind of
small closed classification.

**Consequence.** PROGRAM.md §3.P2 item 6 is DONE. `make check` exit code and counts recorded in the
session report (`.superpowers/sdd/p2-profile-keystone/item6-report.md`); no engine or stored-verdict
behavior changed, so this closes purely a reporting gap.

**Fix round 1 (same session).** Review caught an honesty bug in the first cut: `ELIGIBLE_CLEARED`'s header
counted `len(audit.requirements)` — every fired row, regardless of disposition — as "cleared". Under D-035,
five families (`experience_years`, `clearance`, `degree`, `contract_not_fte`, `internship`) still ship
`preference`, so an `eligible` verdict can legitimately carry a `met` blocker row (e.g. `work_auth`)
alongside a non-blocking `unmet`/`unknown` `preference`-family row that never stopped the verdict. The
original header rendered that as "eligible — 2 requirements cleared" — claiming the unmet row was cleared
when it was not, which is the exact overclaim this item exists to kill, just one level down from the
zero-vs-nonzero distinction the first cut fixed.

Fixed by moving the counting into the property layer rather than the render: a new `AuditView.met_count`
sums only rows disposed `met`, and `VerdictPresentation` gained a third member, `ELIGIBLE_MIXED`, for "one
or more rows fired but not all `met`". `_render_audit` now headers `ELIGIBLE_MIXED` with neutral wording —
"eligible — N requirement(s) evaluated (M cleared; see details)" — that states the honest `met_count`
instead of implying every row cleared; the unmet/unknown row's true disposition still renders on the
per-requirement line below, unchanged. `ELIGIBLE_CLEARED` now only fires when `met_count == len(requirements)`,
so "N requirement(s) cleared" is true whenever it is said.

**Verified (round 1).** Added `met_count` and the `ELIGIBLE_MIXED` branch; extended
`tests/unit/test_eligibility_audit_presentation.py` with cases for one-met-plus-one-unmet, one-met-plus-one-
unknown, and zero-met-of-two, each asserting `presentation is ELIGIBLE_MIXED` and the exact `met_count`; added
`tests/pipeline/test_eligibility_flow.py::test_eligible_with_a_non_met_row_renders_mixed_not_cleared`, which
writes a real evaluation row pair (`met` `work_auth` + `unmet` `degree`) via `record_evaluation`, asserts
`presentation is ELIGIBLE_MIXED` and `met_count == 1`, then asserts on `show`'s actual output: `"2
requirements cleared" not in output` (the overclaim) and `"1 cleared"` and the literal string `"unmet"` both
present (the honest count and the still-visible true disposition). RED confirmed by stashing only the two
source files (`audit.py`, `show_cmd.py`) back to the pre-fix-round-1 commit while keeping the new tests —
6 failures (`AttributeError: no attribute 'met_count'` / `no attribute 'ELIGIBLE_MIXED'`). GREEN restored by
popping the stash — 25/25 pass across both files. Mutation-verified by degrading the `ELIGIBLE_CLEARED`
guard to `if self.met_count >= 0` (always true) — the 4 tests that assert `ELIGIBLE_MIXED` failed as
expected; reverted, 25/25 green again. `git diff` on `engine.py`/`detect.py`/`resolve.py` stayed empty
throughout — still presentation-only. `make check`: `generalization: OK`, ruff clean, mypy clean (159
files), **2872 passed, 1 deselected**, coverage 95.39%, run in the foreground with output redirected
directly to a file (`> log 2>&1`, no pipe) so the captured exit code is `make`'s own, not a downstream
`tee`'s — exit **0**.

---

## D-037 — the fatal-vs-non-fatal contract is written, and the outage predicate is one function

**2026-08-07 · session 13 · P3 slice 1 ("P3-contract").**

**Context.** PROGRAM.md §3.P3 item 3 asks for the fatal-vs-non-fatal policy to be *written* (job-apps
spec-3 §12 as the starting table) before any more P3 code is built on top of it — today the policy exists
only as code comments citing CLAUDE.md's fail-safe table, scattered across `runner.py` and
`cli/run_cmd.py`, with nothing a reader can check the code against. Item 4 asks for the systemic-outage
guard to read the decision field, not a status field — it already did (`runner.py` reads
`scan_summary.complete`/`unchanged`, not any stored `status`), but the exact same predicate,
`attempted > 0 and complete == 0 and unchanged == 0`, was written out twice: once in
`pipeline/runner.py` (deciding `summary.fatal` for the pipeline) and once in `scan/coordinator.py`
(deciding `RUN_FAILED` for a standalone `boardwatch scan`). Two copies of one predicate is exactly the
drift risk PROGRAM.md's own comment at the second site already warned about ("without it here the SAME
event records `ok` under `boardwatch scan` and `failed` under `boardwatch run`") — the warning was
correct, but nothing enforced it.

**Choice.** Two changes, both derived from the code rather than inventing new policy:

1. **`docs/program/RUN_CONTRACT.md`** — a new program doc citing exact `file:line` for each of the four
   existing fatal conditions (systemic scan outage, no profile, typst unavailable, every-lead-failed) plus
   the crash path, the non-fatal norm (per-lead/per-board errors), the lock-held case (exit 2, no run
   row), and the exit-code table (0/1/2). It also states the known gap the design doc already
   flagged — `running` + NULL `finished_at` collapses three situations (in-flight / SIGKILL / a
   standalone lane's unhandled raise, `store/queries.py:111-117`) — and says explicitly that resolving it
   is P3 slice 2's run reaper, not this slice, so the contract does not overclaim completeness it doesn't
   have.
2. **`is_systemic_scan_outage(*, attempted, complete, unchanged) -> bool`**, a pure function added to
   `scan/coordinator.py` (importable from `pipeline/runner.py` without a cycle, since `runner.py` already
   imports from `coordinator.py`). Both call sites now call it instead of repeating the boolean
   expression; the expression itself is byte-for-byte what was already there — `attempted > 0 and
   complete == 0 and unchanged == 0` — so no run's fatal/failed classification changes.

**Rejected.** A module docstring in place of a standalone doc — rejected because PROGRAM.md's own item 3
wants the contract checkable independent of which module happens to house the runner today, and a table
with a `file:line` column reads better as a doc than as a comment block. Placing the helper in a new
`scan/outcomes.py` module — rejected as an unrequested abstraction for one four-line function; putting it
in `coordinator.py` (which both callers can already reach) needed no new module and no import-cycle
workaround.

**Verified.** `tests/unit/test_scan_outage.py` (new) exercises the helper directly: true only when
attempted>0 and complete==0 and unchanged==0, false when attempted==0, false when complete>0, false when
unchanged>0. TDD-style RED confirmed by mutating the helper's `return` to `return True` in place — 4 of
the 5 new tests failed as expected, plus the pre-existing
`tests/pipeline/test_pipeline_run.py::test_a_dead_board_is_reported_but_does_not_fail_the_run` (a healthy
board alongside dead ones must NOT be fatal) also failed under the mutation, confirming the existing
outage-behavior test still discriminates through the new call site. Reverted the mutation; GREEN restored
(48/48 across the three affected test files). `make check`: `generalization: OK`, ruff clean, mypy clean
(159 source files), **2877 passed, 1 deselected**, coverage **95.39%**, run in the foreground with output
redirected directly to a file (no pipe, so the captured exit code is `make`'s own) — exit **0**.

**Consequence.** PROGRAM.md §3.P3 items 3 and 4 are DONE. No behavior change to any run's `fatal`/`status`
outcome — this closes a documentation gap and a duplication risk, nothing else. P3 slice 2
(`P3-lock-liveness`, the run reaper) is unblocked to build against a written contract instead of inferring
one from comments.

---

## D-038 — the run-scoped morning artifact, and freshness from run_id + a terminal row + the funnel's own reconciliation

**2026-08-07 · session 14 · P3 slice 4 ("P3-output").**

**Context.** PROGRAM.md §3.P3 items 2 and 7 were the two remaining fail-safe (read-only, presentation-only)
slices: a morning artifact — ranked leads, apply URL, PDF path, verdict + span, one line of why — and a
freshness check that a `<date>/` folder's artifacts are genuinely from a real, finished run of that
calendar date, not merely present. Both had to be built without sourcing from `digest`/`notify`
(`reports/notify.py`, `reports/digest.py`): those two are cursor-scoped ("new since I last looked"), a
different population from "every lead this run tailored" — the funnel's (P0 item 1) population, which is
the one this artifact had to match. The ranker already computes `verdict`/`why`/`score` per posting
(`cli/top_cmd.py::RankedPosting`), but `run_pipeline`'s tailor loop collapsed that to
`TailoredLead(posting_id, company, title, out_dir, pdf_built)` before the funnel writer ever saw it
(`pipeline/runner.py`), discarding exactly the fields item 7 needed.

**Choice.**

1. **`reports/morning.py`** — a new writer, pure-builder-plus-writer split mirroring `reports/run_funnel.py`:
   `MorningLead` (posting_id, title, company, board, score, why, `verdict_label`, `apply_url`, `pdf_path`,
   `evidence_kind`/`evidence_text`) → `build_morning` (ranks by score, descending, stable) →
   `morning_to_dict`/`morning_to_markdown` → `write_morning`, emitting `morning-<run_id>.{json,md}` beside
   the funnel (reuses `run_funnel.WrittenArtifact` rather than a second near-identical dataclass). It links
   to `funnel-<run_id>.md` by name for the accounting rather than restating any of it — two writers
   repeating one fact is the drift risk `run_funnel.py`'s own docstring already warns against.
2. **`TailoredLead` gained `why: str`, `score: float`, `pdf_path: Path | None`** (defaulted, so the
   funnel's existing 5-field unpacking in `runner.py::_emit_funnel` is untouched) — threaded straight from
   `RankedPosting`/`run_tailor`'s result at the one place they are already computed, in the tailor loop.
   `verdict` was deliberately NOT threaded: item 7 asks for "the honest `AuditView.presentation` label"
   (D-036), not the bare stored `verdict`, so the morning writer calls `eligibility/audit.py::load_audit`
   per lead instead, reusing this run's own `current_identity` (profile_hash, rules_hash) — the same
   identity the funnel writer already resolves — so the label agrees with what `top`/`show` would render
   for that posting right now. A new `_emit_morning` in `pipeline/runner.py` joins `postings.url` for every
   posting_id in one query (mirroring `reports/notify.py`'s existing select) and reuses
   `run_funnel_queries.lead_provenance` for the board string. It runs in the same `finally` block as
   `_emit_funnel`, immediately after it, and swallows-and-reports on failure exactly like the funnel (a
   reporting failure must never mask the run's own outcome). The evidence span is "the strongest cleared
   requirement's quote, or the eligibility rationale" per the design: the longest non-empty quote among
   `met` requirements, falling back to the first requirement's rationale (any disposition) when no `met`
   requirement has a usable quote, and `(None, None)` — never a fabricated string — when nothing is
   available. Every field the design named (apply URL, PDF path, verdict, evidence) renders an honest
   named absence when the underlying fact is missing, never a blank cell.
3. **`pipeline/freshness.py::check_run_freshness(engine, run_id, day_dir) -> Freshness`** — no new schema.
   Three independent clauses, each recorded on the returned dataclass rather than collapsed into one bool
   first: `funnel_present` (does `funnel-<run_id>.md` exist in `day_dir`), `status in {RUN_OK, RUN_FAILED}`
   with `started_at`/`finished_at` both dated to `day_dir.name` (`running` is excluded on purpose —
   `store/queries.py`'s own docstring already names that state as covering an in-flight run, a SIGKILL, and
   an unhandled crash alike, none of which this artifact can vouch for), and `reconciles` — every
   `<slug>/` directory actually on disk under `day_dir` counted and compared against
   `run_funnel_queries.count_tailored_artifacts(conn, run_id).rows`. That last comparison is genuinely new,
   not a re-presentation of the funnel's existing `tailored` cross-check: the funnel compares the
   pipeline's in-memory lead count against the store, while this compares the **filesystem** against the
   store — the first place in the repo that verifies a deliverable against disk rather than against a
   second query, per CLAUDE.md's "count the deliverable through a different path than the one that
   produced it" and §3.P3 item 6 ("filesystem-truth counts"). `Freshness.reasons` names every clause that
   failed, not just the combined verdict, so a caller (a future `doctor` surface, left unwired this slice)
   can say WHICH one broke.

**Rejected.** Sourcing the morning artifact from `digest`/`notify`'s cursor-scoped population — rejected
per the design brief and the funnel's own warning; it would silently drop a re-tailored lead whose posting
was not `new` this run. Threading the ranker's raw `verdict` onto `TailoredLead` for display — rejected as
dead weight: `AuditView.presentation` is the field item 7 actually asks for, and an unused field on a
mutable dataclass is exactly the "speculative" surface CLAUDE.md's engineering defaults forbid. A single
combined `Freshness.fresh` bool with no per-clause detail — rejected because "flagged, but not why" is not
better than "flagged"; a caller diagnosing a stale-day feed needs to know which of the three checks failed.

**Verified.** TDD: `tests/unit/test_morning.py` (7 tests, pure builder — ranking, every promised column
present in both halves, the funnel-link-not-restate assertion, and the missing-url/pdf/evidence honest-
render case) and `tests/unit/test_freshness.py` (8 tests, a real SQLite engine + tmp filesystem — fresh on
a terminal same-day reconciling run, flagged on `running`, flagged on a different-day `started_at`, flagged
on a missing funnel file, flagged on a folder/artifact-row mismatch, flagged on an unknown run_id, flagged
on a missing `day_dir`, and `failed` accepted as terminal too) all pass. `tests/pipeline/test_morning_artifact.py`
(5 tests, e2e, mirrors `test_run_funnel_artifact.py`'s seed/`--no-scan` pattern) proves the artifact is
actually emitted beside the funnel, carries the real `postings.url` and the real compiled PDF path, and —
the load-bearing assertion — that `verdict_label` equals a fresh, independent `load_audit(...).presentation`
call for the same posting, not a value the runner invented on its own path. Mutation-verified three ways,
each reverted after confirming the catch: (1) `Freshness.fresh` hardcoded to `return True` — 6 of 8
freshness tests failed as expected (the two already-fresh-shaped cases passed trivially); (2) the morning
writer's `verdict_label` hardcoded to the literal `"eligible"` — the e2e presentation-equality test failed,
catching the exact overclaim item 7 exists to prevent; (3) `morning.py`'s three `_fmt_*` honest-fallback
helpers stripped to return `""` on a missing fact instead of naming it — the missing-url/pdf/evidence unit
test failed. All reverted; suites confirmed green again after each revert before proceeding.
`tests/pipeline/test_run_funnel_artifact.py` and `tests/pipeline/test_pipeline_run.py` (96 tests, funnel +
PDF-gate) re-run unchanged and stayed green — the `TailoredLead` field additions are additive-only and the
funnel's own tuple-unpacking of `summary.tailored` was not touched. `make check`: `generalization: OK`,
ruff clean, mypy clean (161 source files), **2897 passed, 1 deselected**, coverage **95.31%**
(`morning.py` 97%, `freshness.py` 97%), run in the foreground with output redirected directly to a file
(no pipe, so the captured exit code is `make`'s own) — exit **0**.

**Consequence.** PROGRAM.md §3.P3 items 2 and 7 are DONE. No change to the eligibility engine, the stored
verdict, or the tailor/PDF logic — both additions are read-only reporting layered on facts the pipeline
already computed or already persisted. `doctor` surfacing of `Freshness` is left unwired, as the design
allowed ("optionally"); nothing downstream depends on it existing yet.

---

## D-039 — run-integrity guards: cohort completeness by ID set, zero-output provably-right via run_id attribution, filesystem-truth reusing slice-4

**2026-08-07 · session 15 · P3 slice 3 ("P3-run-integrity").**

**Context.** PROGRAM.md §3.P3 items 5, 9 and 6 are the three fail-safe guards left in the phase: a run
producing 0 leads must exit non-zero unless zero was *provably* right (item 5, bar metric B5); a run that
reached the tailor stage must account for every candidate it shortlisted, not just balance a count (item
9); and the DB's self-report of what it tailored must be checked against the filesystem, independently
(item 6). The design (`.superpowers/sdd/p3-unattended-runner/slice3-design.md`) went through a deepseek-v4
review that reworked the zero-output predicate before any of this was built — the review's Major 3 flagged
that a fuzzy "handled ledger" for excluding prior-run work was ill-defined, and its Blocker flagged that
the cohort formula might omit `skipped_not_new` postings that settle in neither the lead nor the failed
bucket.

**Choice.**

1. **Candidate == shortlisted, not observed.** A candidate is a posting the ranker put in `ranked.visible`
   — verified (not assumed) to already EXCLUDE `skipped_not_new`: `top_cmd.py`'s own accounting identity is
   `considered == len(visible) + skipped_not_new + hidden_hard_filter + hidden_non_swe + hidden_ineligible
   + hidden_below_cutoff` (`top_cmd.py:63`), so the reviewer's Blocker does not arise — `visible` is exactly
   the population the tailor loop iterates, with nothing skipped mixed in.
2. **Terminal == lead | failed.** `PipelineSummary` gained `tailor_failed_ids: list[int]`, appended
   alongside the existing `tailor_failed` counter at both of the tailor loop's `except` sites
   (`LeadArtifactError` and the generic per-lead `except Exception`) — threading the design asked for rather
   than deriving the count from `summary.tailored`, since the counter already existed and only the IDs were
   missing.
3. **`_cohort_guard(visible_ids, lead_ids, failed_ids) -> str | None`**, a pure function in
   `pipeline/runner.py`, reconciles by **set difference** (`visible_ids - (lead_ids | failed_ids)`), not by
   count equality (reviewer Minor, resolved) — a compensating bug (one candidate lost, a different id
   double-counted as a lead) balances `len(visible) == len(lead) + len(failed)` but cannot hide inside a
   set difference. Names every unaccounted posting_id in the fatal message.
4. **`_zero_output_guard(eligible_judged_this_run) -> str | None`**, the reworked predicate: 0 leads is
   provably right IFF this run did no NEW eligible work, measured as the count of open postings whose
   CURRENT evaluation is verdict `eligible` AND was itself judged with **this run's `run_id`** — never a
   cross-run "handled ledger" (the fuzzy mechanism the review's Major 2/3 objected to). A steady-state day
   where every eligible posting is a cache hit from a PRIOR run has this count at 0 and is honest — which
   is what dissolves the false alarm without inventing any new bookkeeping. `scan healthy` is not
   re-checked here because it is structurally guaranteed: `is_systemic_scan_outage` (D-037) already returns
   the run before the tailor stage is ever reached, so the guard is unreachable on an outage. The count
   comes from a new store query, `run_funnel_queries.count_eligible_judged_this_run`, which reuses
   `_current_identity_evaluations` — the same subquery `count_corpus` already partitions — rather than a
   second identity path, filtered to `verdict == 'eligible' AND run_id == this_run`.
5. **Filesystem-truth reuses slice 4, does not reimplement it.** `pipeline/freshness.py` gained
   `folders_reconcile(conn, run_id) -> tuple[int, int]`, factored out of `_existing_lead_folders` +
   `count_tailored_artifacts` — the same pair `Freshness.reconciles` already compares — but callable on its
   own. It has to be separate from `check_run_freshness`/`Freshness.fresh`: the guard runs INSIDE the
   pipeline's `try`, before `finish_run` stamps a terminal status and before the funnel is written, so
   `funnel_present` and `status` would spuriously fail at that point if the guard called the full
   `Freshness` check instead of just this one clause.
6. **Wiring, all in `pipeline/runner.py`, all setting `summary.fatal`** (the slice-1 contract's single
   discriminator, fail-safe direction only — a guard can only turn a run non-zero, never suppress a real
   failure): zero-output checked first, then cohort, then filesystem-truth, matching the design's stated
   order so the more specific empty-day message wins when more than one would fire on the same run. Every
   guard is gated on `summary.fatal is None`, so an already-fatal stage (typst-unavailable, the pre-existing
   every-lead-failed case) is never overwritten and never doubly diagnosed.

**Documented residual.** A scan that "succeeds" but silently returns empty pages — 0 new postings for a
bad reason, not a genuine outage — is not distinguishable from a legitimate all-`unchanged` day by the
zero-output predicate alone. That gap is knowingly left to the systemic-outage guard (D-037) plus the
stub-rate metric (P0 item 6) plus slice-4 freshness (D-038), per the design's own accept-and-note stance —
over-reaching this predicate to cover it would have meant inventing exactly the fuzzy cross-run ledger the
review already rejected.

**Rejected.** A combined count identity (`len(visible) == len(lead) + len(failed)`) instead of an id-set
reconciliation — rejected per the review's Minor, and pinned by
`test_cohort_guard_by_id_set_catches_a_compensating_bug_a_count_check_would_miss`, which constructs exactly
such a compensating bug and shows the count identity balances while the id-set catches it. A cross-run
"handled ledger" tracking which postings a prior run already disposed of — rejected per the review's
Major 3; `judged_this_run` (run_id attribution, D-016/D-019) already answers the same question with no new
state. Calling `check_run_freshness`/`Freshness.fresh` wholesale for the filesystem-truth guard — rejected
because the funnel and the terminal `runs.status` do not exist yet at the point in the run the guard needs
to fire, which would make every healthy run spuriously fatal on `funnel_present`/`status` alone.

**Verified.** TDD throughout: `_cohort_guard` and `_zero_output_guard` are pure functions tested directly
with synthetic id sets/counts in `tests/pipeline/test_pipeline_run.py` (balances not fatal, a vanished
candidate fatal and named, the compensating-bug-vs-count-check case above, both zero-output predicate
sides). `count_eligible_judged_this_run` is tested in `tests/unit/test_run_funnel_queries.py` against a
real SQLite engine (counted when judged this run, NOT counted when the same verdict was judged by a prior
run, NOT counted when the verdict is `ineligible`). `folders_reconcile` is tested in
`tests/unit/test_freshness.py`, including explicitly against a `running`-status row with no funnel file to
pin that it does not depend on either. End-to-end, `tests/pipeline/test_pipeline_run.py` adds: a genuinely
empty corpus (no open postings at all) staying non-fatal; a fresh eligible posting forced to 0 leads
(`--top 0`) going fatal with the exact "empty day not provably right" message; the steady-state case run
TWICE — the first run tailors a real lead, the second (`--top 0`, same profile+rules identity) has the
posting's evaluation attributed to the FIRST run's `run_id` and stays non-fatal, which is the review's
named false-alarm actually exercised rather than only argued about; a lead whose folder is deleted after
`run_tailor` succeeds (monkeypatched to sabotage the real tailor call, not to fake the guard) going fatal
with the `filesystem-truth` message; and an explicit regression pinning that a normal run with real leads
stays `summary.fatal is None`. Every new fatal-path test was confirmed to fail without its guard by
temporarily reverting the corresponding wiring block and re-running the file in isolation; all reverted
before proceeding. Pre-existing `tests/pipeline/test_pipeline_run.py`,
`tests/pipeline/test_run_funnel_artifact.py`, and `tests/pipeline/test_run_pdf_gate.py` (funnel + PDF-gate)
re-run unchanged and stayed green — `tailor_failed_ids` is additive alongside the untouched `tailor_failed`
counter, and no existing call site's argument shape changed. `make check`: `generalization: OK`, ruff
clean, mypy clean, **2913 passed, 1 deselected**, coverage **95.38%**, run in the foreground with output
redirected directly to a file (no pipe, so the captured exit code is `make`'s own) — exit **0**.

**Consequence.** PROGRAM.md §3.P3 items 5, 9 and 6 are DONE. No change to the eligibility engine, the
stored verdict, or the tailor/PDF logic — every guard is read-only over facts the pipeline or the store
already computed, and every guard can only move a run from `ok` to `failed`, never the reverse. P3 slice 5
(LLM economics, item 10) and item 8 (single-writer discipline) are what remains of the phase; slice 2
(lock/reaper) stays flagged unsound (D-036's session, "STATE: P3 slice 2 design found UNSOUND by review").

## D-040 — LLM transient-error retry-with-backoff, ported from politeness into a shared adapter helper

**2026-08-07 · session 16 · P3 slice 5a part 1 ("P3-llm-retry").**

**Context.** `llm/anthropic.py` and `llm/openai_compat.py` both raised a flat `LLMError` for ANY non-2xx
HTTP status — no distinction between a 429/5xx transient that would likely succeed on retry and a genuinely
bad request. Every rewrite in the Tier-B lane that hit a rate limit or a momentary server hiccup lost its
reword and fell back to the Tier-A bullet, for a failure that a retry would usually have recovered. Item 10
of PROGRAM.md §3.P3 names exactly this split: "a quota cap aborts the batch, a transient 429 retries with
backoff." `core/politeness.py` already had the identical pattern for the board fetcher — a distinguishable
retryable-status exception, `tenacity.Retrying` with `wait_exponential_jitter(initial=0.5, max=8.0)`,
`Retry-After` honored over the exponential wait — so this is a port, not a new design.

**Choice.**

1. **`LLMTransientError(LLMError)`** (`llm/client.py`), carrying an optional `retry_after: float | None`.
   `LLMError` stays the flat, non-retryable base — existing callers catching `LLMError` (the rewrite lane's
   containment boundary, `tests/unit/test_llm_adapters.py`'s original 5xx/invalid-body tests) keep working
   unchanged, since `LLMTransientError` IS-A `LLMError`.
2. **One shared helper, `llm/retry.py`**, not duplicated across the two adapters: `request_with_retry(fn,
   *, attempts=DEFAULT_ATTEMPTS)` runs `fn`, retrying ONLY on `LLMTransientError` (`retry_if_exception_type`
   — a plain `LLMError` is not an instance of the subclass and is never retried), honoring the exception's
   `retry_after` over `wait_exponential_jitter` when the provider sent one, capped at `DEFAULT_ATTEMPTS = 4`
   total tries, then re-raising the last error. `parse_retry_after` is a small local copy of
   `politeness.py`'s version (same header, same HTTP-date-ignored fallback) rather than a cross-import — the
   module's own docstring states it must never import `boardwatch.store`, mirroring `politeness.py`'s
   fetch-side boundary (not mechanically enforced by `test_import_hygiene.py`'s `FETCH_ONLY_MODULES` list,
   since neither adapter has ever had a reason to import store).
3. **Both adapters classify status BEFORE the existing body-parsing try/except**: `status_code in
   {429,500,502,503,504}` → `LLMTransientError` with `parse_retry_after(response)`; any other non-2xx →
   the unchanged flat `LLMError`; an invalid JSON body or a missing content path stays `LLMError` too — a
   malformed 200 is not a transient failure, retrying it would just replay the same malformed body.
4. **Placement is BELOW the rewrite lane's budget metering, not beside it.** `tailor/rewrite/lane.py`'s
   `_guarded` wraps `client.complete()` and increments `state["calls"]` exactly once per invocation,
   regardless of what happens inside that call. The retry loop lives entirely inside `complete()` (wrapping
   only the HTTP request + response classification, not the `httpx.Client` construction/teardown around
   it), so N HTTP attempts for one logical rewrite-or-judge call still cost 1 budget unit. Confirmed by
   inspection, not just argued: `_guarded`'s counter is a variable captured by `lane.py`'s own closure, with
   no visibility into the adapter at all — there is no code path by which a retry inside `complete()` could
   touch it.

**Rejected.** Duplicating the tenacity `Retrying` setup separately in `anthropic.py` and `openai_compat.py`
— rejected because the two adapters' retry semantics are identical (same statuses, same backoff, same
`Retry-After` rule), and a single shared helper is the only way a future third adapter doesn't need to
re-derive the pattern a third time. Importing `core/politeness.py`'s `_parse_retry_after` directly instead
of a local copy — rejected: it is private (underscore-prefixed) to that module, and importing across the
fetch/LLM boundary for one four-line pure function creates a coupling the boundary comment exists to avoid,
for no benefit over duplicating four lines. Adding a `Settings` field for the attempt cap, mirroring
`Fetcher`'s `retry_attempts` — rejected as unrequested configurability; item 10 asks for a bounded cap, not
an operator-tunable one, and `DEFAULT_ATTEMPTS` is a plain constant importable by tests without one.

**Verified.** TDD: `tests/unit/test_llm_retry.py` unit-tests the shared helper directly (transient-then-
succeed, `retry_after` honored over the exponential wait, attempts exhausted re-raises `LLMTransientError`,
a non-transient `LLMError` propagates on the first call with no retry) with `time.sleep` monkeypatched to a
no-op or a recorder throughout — no real sleeps, no network. `tests/unit/test_llm_adapters.py` adds the
same coverage at the adapter layer for BOTH `OpenAICompatClient` and `AnthropicClient` (429-then-success,
all four 5xx variants parametrized, `Retry-After` honored, exhausted attempts surface `LLMTransientError`,
a 400 fails on the first call and is confirmed NOT an `LLMTransientError`), plus updates the two pre-existing
5xx tests to assert `route.call_count == DEFAULT_ATTEMPTS` and the pre-existing invalid-JSON-body test to
assert `route.call_count == 1` — the old flat-`LLMError`-on-5xx assertion still holds (subclass), it just
now also retries first. Mutation-verified live in this session, not just narrated: widening
`retry_if_exception_type(LLMTransientError)` to `retry_if_exception_type(Exception)` failed both
`test_non_transient_error_is_not_retried` and `test_openai_compat_non_retryable_400_fails_fast`; raising
`stop_after_attempt(100)` in place of the `attempts` parameter failed
`test_attempts_exhausted_reraises_transient_error`; adding `400` to `openai_compat.py`'s
`_RETRYABLE_STATUSES` failed `test_openai_compat_non_retryable_400_fails_fast` with the exact "got
`LLMTransientError`, expected not" assertion. All three mutations reverted before proceeding. `make check`:
generalization OK, ruff clean, mypy `--strict` clean, **2933 passed, 1 deselected**, coverage **95.36%**,
run in the foreground with output redirected to a file (never piped), exit **0**.

**Consequence.** PROGRAM.md §3.P3 item 10's rate-limit-class clause is PARTIALLY done — "a transient 429
retries with backoff" now holds for both adapters; "a quota cap aborts the batch" and the never-silently-
downgrade requirement are P3 slice 5b, deliberately out of scope here (a Mit fork on the never-downgrade
policy). Idempotence (meta-hash keyed on JD + template + model + prompt version + `profile_version` +
`persona_version`) and batched judging are also still open, unaffected by this change. No change to
`tailor/rewrite/lane.py`'s containment semantics, budget accounting, or `run_tailor` — a retry can only
RECOVER a call that would otherwise have landed on `drop_reason="error"`; on exhaustion, the lane sees the
exact same `Exception` it always caught and takes the exact same Tier-A-keeping path.

## D-041 — the SQLite/WAL concurrency stance is now documented (P3 item 8, doc half)

**2026-08-07 · session 10 · P3 (item 8, the documented-stance half).**

**Context.** PROGRAM.md §3.P3 item 8 asks for a "documented WAL stance + a two-writer test incl. the
cross-OS case." The stance existed only in code + scattered comments; the two-writer test does not exist.

**Choice.** Wrote `docs/program/WAL_DISCIPLINE.md` capturing the already-existing, verified stance:
per-connection `WAL` + `busy_timeout=5000` + `foreign_keys=ON` (`db.py:26-31`); the scan lock serializes
whole SCANS (not the DB), `apply_board` is the serial single writer, and WAL+busy_timeout keep reads + small
writes safe alongside a running scan (D-020). It names the REMAINING hard half explicitly: no two-writer
test exists (only lock-rejection), and critically no CROSS-OS test — the Docker-Linux-container +
macOS-host-mounted-DB config that corrupted job-apps' PK is untested, and a same-OS test proves nothing
about it. That harness is deliberately deferred to a fresh context window (test-infrastructure-hard).

**Fail-safe posture recorded:** the scan lock fails closed (2nd scan rejected, never half-corrupts);
busy_timeout makes contention wait not error; the untested cross-OS path is a verification GAP, not a
known-broken behavior — but running two writers across the container/host boundary is not proven safe until
the harness exists, so avoid it operationally.

**This is the doc half of item 8 only.** The two-writer/cross-OS test remains open (fresh context).

## D-042 — the tailor-level idempotence short-circuit is DECLINED (YAGNI); the response cache already covers it

**2026-08-07 · session 10 · P3 (item 10, idempotence half).**

**Context.** P3 item 10 wants "a re-run is not a full re-tailor." Two design attempts (one at high context,
one by a fresh opus agent) were each deepseek-reviewed and found unsound/incomplete — 2 blockers+4 majors,
then 3 more majors (Typst-binary-version-not-in-key, racy insert-if-absent without a unique index, copied
artifacts not hash-verified). Full findings in `.superpowers/sdd/p3-unattended-runner/slice5a-idempotence-design.md`.

**Choice — DECLINE it.** The material cost item 10 targets — re-paying LLM API calls on a resumable re-run —
is ALREADY avoided by the existing `llm/cache.py` response cache (per-bullet propose/judge keyed on
content-hash+prompt+model). A tailor-level short-circuit only additionally saves a cheap Typst render, and
making that safe demands heavy, correctness-hazardous machinery (typst-version keying, PDF hash-verification,
a partial unique index on `artifacts`, and careful cohort/provenance interactions) — proven by four
unsound/incomplete iterations. Per CLAUDE.md's minimum-code / no-speculative-abstractions / new-code-last
doctrine, that is over-engineering for its payoff. Same disposition as P2 item 1 (schema_version): declined,
revisit only with concrete evidence of a material render cost.

**Recorded gap (not conflated):** LLM response-cache HITS may still increment the `_guarded` budget counter
(a re-run could exhaust budget on cache hits and drop later bullets to Tier-A despite making no API call) —
a small, real, SEPARATE inefficiency worth a future look, not part of this decision.

**Alternatives rejected:** a fifth idempotence redesign (diminishing returns; low value over the cache).

## D-043 — the scan lock now notifies loudly with the blocking pid; the sidecar is message-only, never a lock authority

**2026-08-07 · session 10 · P3 (item 1, notify-loudly clause only).**

**Context.** `.superpowers/sdd/p3-unattended-runner/slice2-design.md`'s full item-1 design (token-authenticated
sidecar, unlock-only-on-token-match, stale reclaim by atomic rename, the run reaper) was deepseek-reviewed and
found UNSOUND: `os.replace` arbitrates a pathname, not the inode `filelock.FileLock` actually locks, so
"reclaim by rename" doesn't compose with a real lock acquirer (2 blockers — a reclaimer can steal a live lock,
two reclaimers can both "win") plus 4 majors (sidecar-removal race, reaper TOCTOU, unsound age-only reap for
the standalone lane, pid-reuse defeating `os.kill(pid,0)` liveness). That review explicitly separated the
unsound reclaim/reaper machinery from the "notify loudly" half, which it called sound on its own.

**Choice — build only the sound half.** `run_scan` (`scan/coordinator.py`) now writes a sidecar
(`scan.lock.meta`, atomically via temp-file + `os.replace`) containing `{pid, hostname, started_at}`
immediately after a successful `lock.acquire()`, and removes it (best-effort, swallowing `OSError`) in the
same `finally` that releases the lock. On contention (`Timeout`), `_lock_held_message` reads the sidecar and,
if present and well-formed, raises `ScanLockHeldError` naming the blocking pid + hostname + started_at and
telling the operator to remove the lock file if that process is gone; a missing, unreadable, or malformed
sidecar falls back to the unchanged generic `SCAN_LOCK_MESSAGE` — never a crash.

**Why this is sound where the fuller design wasn't:** the sidecar is written and read only in the message
path. `filelock.FileLock` remains the sole authority over acquire/release; nothing here ever inspects the
sidecar to decide whether the lock is free, and nothing here removes or renames the lock file itself. A stale
sidecar (process died without reaching the `finally`, or a foreign leftover file) can only make a held-lock
message name a dead pid — cosmetic, already hedged by the message's own "if that process is gone" clause —
never a correctness issue, because no acquire/release/reclaim decision ever reads it.

**A follow-on fix, in scope because "notify loudly" was otherwise dead on arrival:** `run_cmd.py` and
`scan_cmd.py` caught `ScanLockHeldError` but printed the imported `SCAN_LOCK_MESSAGE` constant directly,
never the caught exception's own message — harmless before this change (the exception's message was
always exactly that constant) but it would have silently discarded the new pid-naming message, so a real
`boardwatch scan`/`boardwatch run` user would never see it. Both now `except ScanLockHeldError as exc:
console.print(str(exc))`; the exit-2 path and control flow are otherwise unchanged.

**Deferred, unchanged from the review's verdict:** stale-reclaim by rename, token-gated unlock, and the run
reaper for `running`+NULL-`finished_at` rows remain OUT OF SCOPE, to be redesigned per the review's direction
(reclaim arbitrated by `filelock` itself rather than a side-channel rename; process identity via
pid+start-time, not a bare pid; the reaper gated on "is the lock acquirable now," not an age floor) — this is
the "design fork worth Mit's input" the review flagged, not yet resolved.

**Alternatives rejected:** shipping the full slice2-design.md protocol as reviewed (blocked — unsound, would
let a reclaimer steal a live lock); waiting to build even the message-only half until the reclaim/reaper
redesign lands (rejected — the notify-loudly clause is independently useful and does not need the reclaim
machinery to be safe, per CLAUDE.md's minimum-code default).

## D-044 — P3 slice 5b: KEEP today's Tier-A downgrade on provider/quota error; decline the "never downgrade" inversion

**2026-08-07 · session 10 · P3 (item 10, the never-downgrade half — decided autonomously under Mit's
standing "make the calls" delegation; reversible).**

**Context.** P3 item 10 asks that the pipeline "never silently downgrade to the deterministic engine" and
instead leave leads pending/resumable on a quota cap. Today (`tailor/rewrite/lane.py:96,208`) a Tier-B
provider/quota error is contained → `drop_reason="error"`/`"budget"`, the bullet keeps its deterministic
Tier-A text, and the lead SHIPS. That is a silent downgrade — but a REASONABLE fail-safe: a lead with a
solid, structural, no-fabrication Tier-A bullet is a good, shippable outcome, not a failure.

**Choice — KEEP the current behavior; decline the inversion.** Inverting it (a new non-terminal
pending/resumable lead state + threading a QuotaExceeded past the two containment boundaries + reworking the
slice-3 cohort-completeness invariant, which demands a terminal state per shortlisted posting) is a large,
risky change whose payoff is dubious: for an UNATTENDED daily driver, "ship the Tier-A lead now" beats
"leave it pending and produce no lead today." Per CLAUDE.md's minimum-code / no-speculative-abstractions
doctrine, and the fail-safe table ("fabrication check ⇒ drop tailoring, emit static" — i.e. downgrading to
the deterministic output IS the sanctioned fail-safe), the status quo is the correct default.

**Reversible + the one thing that WOULD change the call:** if Mit wants Tier-B rewording treated as
load-bearing enough that its absence should block a lead (rather than degrade to Tier-A), that is his call
to make — this decision is the conservative default, not a foreclosure. Until then: no pending/resumable
state, no cohort-invariant rework, no batched-judging (defers with it).

**This resolves the 5b fork.** Remaining P3 open items: item 4-adjacent taxonomy is P2 (needs Mit's
domain input on the field→family mapping); the lock reclaim + run reaper stay deferred (reclaim proven
unsound; a sound reaper needs process-liveness identity — fresh context); item 8's cross-OS two-writer test
is environmentally blocked (no Docker here). Idempotence declined (D-042).

## D-045 — P3 slice 2: DECLINE custom stale-reclaim (unsound AND unnecessary); the loud-notify shipped, the reaper stays fresh-context

**2026-08-07 · session 10 · P3 (slice 2, the reclaim half — decided autonomously; reversible).**

**Context.** Slice 2 item 1 wanted stale-lock reclaim (a dead scan's lock reclaimed by a later run). The
designed mechanism (atomic-rename reclaim + token-unlock) was proven UNSOUND (D-noted in slice2-design.md:
`os.replace` arbitrates a pathname, `filelock` locks an inode → a reclaimer can steal a live lock / two
reclaimers both win).

**Choice — DECLINE custom stale-reclaim entirely.** Beyond being unsound as designed, it is UNNECESSARY on
the primary (POSIX) platform: `filelock` uses OS advisory locks (flock/fcntl), which the kernel releases
when the holding process dies — so a crashed scan's lock is already auto-reclaimed by the next bare
`FileLock.acquire()`. No custom rename/token machinery is needed for the common case. The genuinely-hard
cross-platform edge (Windows / network / container-host mounts) is item 8's concern (currently
environmentally unbuildable — no Docker) and must not be papered over with an unsound reclaim.

**What shipped instead (D-043):** the sound, message-only loud-notify (a held lock names the blocking pid).
**What remains (fresh context):** the run REAPER for `running`+NULL rows — deferred because a SOUND reaper
needs process-liveness IDENTITY (pid+start-time / pidfd, not `os.kill(pid,0)` which pid-reuse defeats) to
avoid reaping a live standalone/`--no-scan` run; that is subtle concurrency work for a fresh context, not a
high-context grind (three consecutive high-context P3 designs came back unsound this session).

**This + D-044 resolve the slice-2 and 5b forks to conservative, reversible declines.** The only remaining
items needing input beyond a fresh context window: P2 item 4's taxonomy CONTENT (which rule families are
field-specific for a US-nurse / EU-paralegal persona — Mit's domain call), and item 8's cross-OS test
(needs Docker). Everything else this session was built or reasoned-declined.

## D-046 — P3 slice 2: age-based run REAPER (no schema); this CLOSES the last non-Mit / non-Docker P3 build item

**2026-08-07 · session 10 · P3 (slice 2, the reaper half — built, reviewed, merged).**

**Context.** A crashed/killed run leaves a permanent phantom `runs` row (`status='running'`,
`finished_at IS NULL`) — `finish_run`'s own docstring names "the reaper that P3 owns" as what separates
that signature from a live run and a raised standalone lane. D-045 declined the reclaim; this is the reap.

**Why age-based, not process-liveness (correcting the D-045-era premise).** The `runs` table has no
pid/heartbeat column, so there is nothing to check `os.kill(pid,0)` against, and adding one only works
same-host (a container writer and a host writer have disjoint pid namespaces — item 8's domain). Age is
the sound discriminator instead: a real boardwatch run — even the daily driver over hundreds of leads with
LLM tailoring + retry backoff — is minutes, not hours.

**Mechanism.** `reap_stale_runs(engine, *, older_than)` marks rows matching
`status='running' AND finished_at IS NULL AND started_at < now-older_than` as `failed`, appending a note,
in a SINGLE atomic `UPDATE ... RETURNING id` (`json_insert` for the append — no read-modify-write; the
returned id list is exactly what THIS call mutated, not a pre-UPDATE snapshot that over-reports under a
race). Default threshold `Settings.reap_stale_after_hours=24` (operational; classified CONFIG_IRRELEVANT
so it never enters `config_hash`, and "operational" in the generalization snapshot). Drains in `doctor`
(report+reap, guarded so a lock-contended write can never crash the diagnostic) and at `run_pipeline`
start before the run's own row is minted (swallow-and-logged).

**Why sound / fail-safe.** `finish_run` has no `status='running'` precondition, so a false-reap of a run
that breaches 24h and then finishes self-corrects (`failed`→its real terminal status); the only residual
is an honest `reaped` note on such a >24h run. No guard re-reads `runs.status` — freshness treats `failed`
as terminal (verified) and is run-scoped, so there is no cascade-abort of a later run.

**Reviews.** deepseek (design): found a real `errors_json` read-modify-write race in the first cut → fixed
by the single atomic statement; threshold 6h→24h; its alleged freshness cascade disproven against the
code. diff-reviewer (implementation): found doctor's reap unguarded (fixed), the return list a pre-UPDATE
snapshot (fixed via RETURNING), and a discrimination test gap (added). `make check` green (2948 passed,
95.33% coverage), authoritative gate re-run by the orchestrator.

**The correct-but-deferred alternative:** a `last_heartbeat_at` column bumped every ~60s, reaping on
heartbeat-staleness not start-age, distinguishes a slow-but-live run precisely. It costs a schema
migration + a periodic writer; deferred as a follow-up. **With this merged, the last P3 build item that
needs neither Mit's domain input nor Docker is closed.**
