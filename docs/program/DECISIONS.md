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
