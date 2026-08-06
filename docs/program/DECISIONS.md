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
