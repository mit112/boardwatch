# boardwatch replacement program — plan of record

**Owner:** boardwatch (Claude) · **Established:** 2026-08-06 · **Status:** approved, executing (P0)
**Derived from** `~/dev/Job apps/docs/boardwatch/roadmap.md`, with documented departures (§6).
**Current standing:** `docs/program/STATE.md` — read that first, every session.

---

## 1. The bar (Mit's, unmodified)

boardwatch replaces job-apps when, for **14 consecutive unattended days**, one command produces:

| # | Metric | Bar |
|---|---|---|
| B1 | Net-new profile-eligible, live, deduped leads/day | **≥ 10** |
| B2 | Leads with a compiled résumé PDF | **100%** |
| B3 | Leads passing the deterministic résumé QA gate (page count = hard fail) | **100%** |
| B4 | Fabrications, independently audited | **0** on n ≥ 100 |
| B5 | Silent empty days (run "succeeds", produces nothing) | **0** |
| B6 | Funnel reconciliation | **100%** to a terminal state or explicit `pending` |
| B7 | Work authorization resolved **decisively** for a declared profile | required |

**Scheduling consequence, stated up front:** the 14-day clock measures a *frozen* system. Any change to
eligibility, profile, or the résumé gate resets it. So the clock starts **after** P6, not during. Starting
it early and mutating underneath it produces 14 days of uninterpretable data. This is the single most
important program-level scheduling fact and it is why no phase gate below is "run for 14 days".

### The provisional pass — how "done" is called (D-280)

**"Done" is called on a provisional pass; the 14-day clock confirms it afterwards instead of gating it.**
A provisional pass is **3 consecutive clean frozen daily runs**, each meeting every B1–B7 threshold above
and each also clearing P5b's criteria (**≥ 30** postings considered, **0** preflight fatals, **0**
résumé-QA failures). On the third, the replacement is declared provisional and the full 14-day acceptance
starts **passively, in the background**, on daily cadence.

"Frozen" carries the same meaning it does above — no change to eligibility, profile, or the résumé gate —
and it binds the 3 provisional runs as well as the confirm. **All build work therefore merges before the
freeze.**

**The 3 runs ARE compressible, and Mit ruled to compress them (D-281).** The belief that they were bound
to real days rested on net-new drying up intraday; that is measured false. `built` is a permanent
disposition, so each run retires its whole shortlist for good, and run 69 produced **40 of 40 net-new
three hours after run 68 took its own 40** — the two lead sets are 100% disjoint. With **3,683** postings
cut only by rank, a compressed cadence is supplied for ~92 more runs.

**The mechanism:** the launchd cadence is raised to roughly every 3 hours, the first **7 consecutive clean
unattended ticks** close Gate P3, and **3 of those same ticks** — frozen, each meeting every B1–B7
threshold — constitute the provisional pass. Both gates close together in ~1–2 days. Daily cadence is
restored afterwards for the 14-day confirm.

**State the cost plainly, so this is never misread later.** B1 ("≥10 net-new leads/**day**") and B5
("silent empty **days**") are written per day. Read off three ticks inside one afternoon, B1 becomes ~120
net-new in a single day rather than ≥10 on each of three, and B5 is evidenced over hours rather than days.
**The provisional pass therefore certifies per-run behaviour, not per-day behaviour** — which is precisely
what the 14-day background confirm, on true daily cadence, exists to establish. Mit accepted that trade
knowingly; the confirm is the control.

---

## 2. Ordering principle

job-apps' principle — *breadth multiplies whatever is downstream of it* — is correct and I adopt it.
**But it constrains input, not output.** PDF emission and unattended running are output-side: shipping them
early multiplies nothing. They make the current small, precise funnel actionable. So the live gap can be
closed early without violating the principle, and breadth still goes last.

```
P0  Instrumentation        → anything below is measurable at all
P1  Résumé artifact gate   → a lead is actionable (LIVE GAP, partial relief in days)
P2  Profile + keystone     → eligibility has a declared thing to resolve against
P3  Unattended one command → it happens without Mit (LIVE GAP closed)
P4  Craft gate             → the output reads human
P5  Eligibility decides    → "eligible" is a claim, not a residue
P6  Liveness + dedup       → "eligible" means TODAY, once
P7  Breadth                → the three discovery lanes (PULLED FORWARD, D-280)
──  Provisional pass       → 3 frozen B1–B7 runs; "done" is called here
──  14-day acceptance run  → the same bar, confirming in the background
```

**Breadth now precedes acceptance (D-280), and that is a departure from the principle above, taken
knowingly.** Breadth still multiplies whatever is downstream of it — the reason it went last — but the
downstream is now measured rather than assumed: dedup leakage and liveness are instrumented, and boardwatch
reaches only 7.7% of job-apps' eligible yield (D-271) because of *company reach*, not fetch depth.

**Breadth is NOT required to hold B1, and the reason it was thought to be is measured false (D-281).**
`built` is a permanent disposition, so every run retires its shortlist for good and the next 40 by rank
become leads whether or not anything new arrived. Run 69 demonstrated this directly: 40 of 40 leads
net-new, three hours after run 68 took its own 40. **3,683** postings currently clear every gate and are
cut only by rank — ~92 more runs, ~368 days at ≥10/day — and that reservoir is *growing*, not draining
(+126 then +55 net across runs 67→68→69, after 40 consumed each time). So the lanes are justified by
**parity and company reach**, which is what D-272 ruled them in for, and not by B1 survival.

**The corollary is a caveat on the bar itself:** a 14-day B1 pass does **not** evidence discovery health.
It is close to guaranteed for the next ~92 runs by ledger drain alone. The real threat to a B1 day is the
opposite of an empty reservoir — a **ledger reopen**, which re-serves already-built jobs as repeats and
scores them 0 net-new. Run 66 produced 8 leads and **0** net-new for exactly that reason, and any change to
`engine_version` owes a drain (D-266). During a frozen window that drain is the one thing that can fail B1.

**Why P1 before P2/P3 — and what it costs.** *(Ratified by Mit 2026-08-06 after review flagged the
original wording as overclaiming.)* P1 runs against a render path that already exists and gives Mit
compiled PDFs for his existing manual workflow immediately. Nothing generates his résumés right now, so
P1 is the shortest path to changing that.

**The honest cost:** "output-side work multiplies nothing" is not unconditional. Between P1 and P5,
boardwatch compiles PDFs for leads chosen by a selector that currently returns `eligible` on **1,427**
evaluations carrying unmet *required* dispositions. That is wasted compile time and wasted review time —
the same argument §4 makes against volume. It is accepted deliberately: a compiled PDF is useful for any
lead Mit picks by hand, and zero résumés a day is the worse failure. P2 follows immediately and closes it.

**Why P2 before P3:** running unattended while the work-auth rule abstains on 100% of postings produces
14 days of leads Mit may not be eligible for. P2 is cheap (§6, correction 5) and is Mit's stated keystone.

---

## 3. Phases, with measurable gates

Every gate below is expressed in numbers boardwatch can emit from its own SQLite store (`runs`,
`posting_events`, `eligibility_evaluations`, `artifacts`, `artifact_derivations`, `applications`) or from
the per-run funnel artifact P0 introduces. No gate depends on a metric that does not yet exist.

### P0 — Instrumentation and the run ledger

Nothing below P0 is checkable without it, and it is the cheapest phase.

**Item 0 was added to this list by D-016**, after the original eight were written. The list is therefore
nine items numbered 0-8, and **item numbers are stable** — later documents cite them, so renumber nothing.

0. **The pipeline-run row.** One command running scan -> eligibility -> tailor that owns run identity
   across all three, because no existing process spans the seven funnel stages and nothing else here has a
   key without it. Accepted as *early P3 work* rather than extra work (D-016). **DONE** — `boardwatch run`,
   plus D-019's invariant that `run_id` is never NULL on a new row, and D-020's split of who creates the
   row from who finishes it.
1. **Per-run funnel artifact** (`json` + `md`), one per run: `observed → unique → candidates →
   prefilter_stopped → eligible / ineligible / abstained → leads_with_pdf → marked_applied`. **DONE** —
   written to `<out_root>/<date>/funnel-<run_id>.{json,md}`, outside the git tree (D-024). Carries the
   abstain report for every catalog rule, per-lead board provenance, and two cross-checks that recount
   the deliverable from the store.

   **The stages shipped are `dedup · corpus · attribution · verdict · shortlist · tailor · pdf · applied`,
   which is not the list written above.** Every departure was measured, not assumed:
   - the head is the **open-posting corpus**, not `observed` — `postings_seen` and `open_postings` are
     different populations (D-022);
   - `unique` reports **not instrumented** rather than 0, because dedup is P6 and has never run (D-023);
   - `candidates` and `prefilter_stopped` had **no counterpart at all** when item 1 shipped: the ranker
     did not report how many postings it considered, so the population entering the prefilter was
     unmeasured and postings leaving the ranker uncounted landed in no bucket — **15,959 of 19,262
     open postings** on a measured run at `--top 5` (11,517 hard-filter vetoes, 4,442 below the cutoff).
     **Item 3 closed this** (D-027). The `shortlist` stage now enters at the ranker's own considered
     population and names all five of its exits, and because `entered` is measured independently of the
     drops it is a stage whose balance can genuinely fail;
   - `attribution` and `tailor` are additions the run key made possible.
2. **Per-rule abstain rate**, every run. This is the metric that makes a rule that cannot fire *visible*.
   **DONE** — `boardwatch eligibility abstain`, and emitted for all 44 rules inside the item-1 artifact.
3. **Per-source outcome table**: `unique | assisted | eligible | leads | applied`. **DONE** — per
   watched board, plus a provider rollup, in the item-1 artifact. Two departures, both measured:
   **`unique` AND `assisted` both report `not instrumented`** — `assisted` credits a source that arrived
   second for a posting another source won, so it is as dedup-dependent as `unique` and equally blocked on
   P6 (D-026); and the denominator is **open postings per board, not `postings_seen`** (D-022). Shipped
   with it, because the same gate clause needed both: the ranker's full population accounting, which is
   what actually closes *"why every non-lead was dropped"* (D-027), and a per-board check on LEADS that
   fails when a tailored artifact resolves to no board. A companion check on verdicts was written and
   **deleted before merge because it could not fail** — D-028 is the entry that deletes it, and the
   surviving leads check is a guard against a future writer rather than live evidence.
4. **Run manifest**: config hash, profile version, rule-catalog version, code fingerprint of
   decision-relevant modules, start/end, exit status. **DONE** (D-029 exit status; D-030 the manifest
   section, `ARTIFACT_VERSION` 2→3). The code fingerprint is `engine_version()`'s AST digest, the
   rule-catalog version is `rules_hash`, the profile version is `profile_facts_hash`, start/end and
   `runs.status` come off the `runs` row — all reused. Two hashes were new: `config_hash` over a **closed
   classification of all 13 `Settings` + 8 `LLMTier` fields** (fails on drift), and `profile_row_hash` over
   the five ranker columns incl. `exclude_titles`, closing the gap `profile_hash` left. Residual gap named
   in the artifact: the skill-taxonomy version.
5. **Reconciliation check** — an invariant sweep asserting DB rows and on-disk artifacts agree. Counts
   from a different path than the one that produced them (job-apps spec-3 §6: self-report ≠ verification).
6. **Stub-rate metric** at judge time — one number, reported every run. Cheap insurance; see §6 correction 4.
   **DONE** (D-030) — open postings with an empty `body_text` over the corpus head, in the artifact; `None`
   over an empty corpus, never 0%.
7. **`run_id` migration** (Alembic, nullable) on `eligibility_evaluations` and `artifacts`, **and the
   threading that populates it** — the column alone changes no behaviour, so the migration is not this
   item, only half of it. **DONE.** Without it,
   three of the seven funnel stages cannot be attributed to a run at all. **Count cache hits as their own
   asserted stage** — `uq_eligibility_deterministic ON (input_id, engine_version)` means a re-run over
   unchanged postings writes no evaluation rows, and "cache hit" vs "never judged" must not be
   indistinguishable.
8. **Fabrication-gate counters** in the funnel artifact: rejections and fail-safe fallbacks per lane.
   `rewrite/lane.py:29-37`'s `RewriteRow.drop_reason` already carries the data. job-apps §12 lists this as
   a day-one metric that cannot be retrofitted, and it is the only mechanism that ever feeds bar metric B4.
   **DONE** (D-030) — Tier-B `drop_reason`s folded into a closed catalog with the two truth-gate rejections
   (judge, overmatch filter) counted apart from fallbacks; an unrecognised reason is a FAILURE, not a new
   bucket. Tier A's `TierASafetyError` fail-safe still has no counter (stated gap).

### Bar → phase → gate traceability

Every bar metric in §1 has exactly one owning phase. Added after review found B1–B7 appeared only in the
§1 table and nowhere else — B4 in particular had no owner and no mechanism anywhere in P0–P6.

| Bar | Owned by | Emitted by |
|---|---|---|
| B1 leads/day | P5 (selection) + P6 (dedup/liveness) | P0 funnel artifact |
| B2 PDF 100% | **P1** | P1 hard gate |
| B3 QA gate 100% | **P1** (mechanical) + **P4** (craft) | per-lead pass/fail |
| B4 0 fabrications, n≥100 | **P1** (Tier-B provenance validator) + **P4** (audit) | P0 fabrication counters |
| B5 0 silent empty days | **P3** | zero-output guard + exit status — **the instrument is DORMANT, see D-282** |
| B6 funnel reconciles 100% | **P0** | reconciliation invariant |
| B7 work auth decisive | **P2** | per-rule abstain + `ineligible` count |

**Gate P0:** three consecutive runs where the funnel reconciles to **100%**, per-rule abstain is emitted
for **every** rule in the catalog, and *which source produced each lead, and why every non-lead was
dropped* is answerable **from the artifact alone, without reading code**.

**B5's instrument does not currently work, and this is the one bar metric with no honest reading
(D-282).** The zero-output guard is the named instrument. Firing requires `hidden_handled == 0` (measured 8 /
48 / 128 on runs 68 / 69 / 71) and an empty shortlist (`capped_by_top_n` is 3,603–3,683, so `visible` is 40
every run), so it is dormant. It cannot simply be widened either: the ranker's `hidden_*` buckets are an
**exhaustive partition** of the corpus, so "can this run explain the empty day?" is always yes by
construction, and a complete partition cannot evidence a silent failure. Making B5 real needs **run-scoped**
rank attribution, which is not built and is an owner call. **Scoring B5 as passing on exit status alone
would be scoring the absence of an alarm that cannot sound.**

### P1 — Résumé artifact integrity (live gap, cheapest first)

The render path exists and is architecturally sound (§6, correction 1). What is missing is enforcement.

**P1a (items 1, 2, 3, 3b, 4, 5) is DONE — shipped on `p1a-resume-artifact-gate`, Gate P1 MET (D-032).**
**P1b (item 3c) is DONE (D-033).** P1 (P1a + P1b) is now fully complete.

1. **DONE.** Kill the silent source-only degrade. ~~`tailor_cmd.py:193,402` currently prints
   `"source only (no PDF; typst not available or compile failed)"` and continues.~~ Split into
   `TypstUnavailableError` (binary-missing, environment fault, run-fatal) vs. `COMPILE_FAILED`/
   `PAGE_LIMIT_EXCEEDED` (lead fault, routes to the fallback in item 5) — closed `CompileReason`/
   `GateReason` catalogs, never string-matched. A lead without a compliant PDF is never recorded.
2. **DONE.** Page count = hard fail. `resume_max_pages` is a new profile column, N from profile (default
   1 for new-grad), enforced in `evaluate_compile`.
3. **DONE.** Overflow detection — Typst-native. *(Corrected: the original clause said "zero
   overfull/underfull `hbox`/`vbox`", copied from job-apps. Those are **LaTeX** concepts. Verified: `typst
   0.15.1` exits 0 with no diagnostic output on a deliberately overflowing document, so that clause was
   vacuously satisfiable and would have been recorded as a pass forever.)* Shipped as `page_count > N` via
   a `typst eval` query against a `<total-pages>` metadata label the renderer injects (spiked against
   0.15.1 before building). The compile log, previously captured and discarded, is now written per lead
   to `typst-compile.log` (and to `_failed/<slug>.log` for a dropped lead).
3b. **DONE.** Packaging, because P1 turns a degrade into a hard failure. `typst` is now installed by a
   Dockerfile layer (pinned to the local 0.15.1 version) and `doctor` probes both presence and version,
   warning loudly on a mismatch (an unpinned typst can silently break the `eval` page-count syntax).
   **Superseded by D-058/D-060:** the render engine is now tectonic + the user's own LaTeX template, and
   `render/typst.py` was deleted. The packaging *requirement* stands; the binary it names does not.
   Vendoring still waits for P7.
3c. **DONE (P1b, D-033).** Tier-B token-provenance validator (see §5.1) — a deterministic allowlist
   (`reword_is_provenanced`, `tailor/rewrite/provenance.py`) vetoes any reword whose content tokens are not
   a source token, an approved equivalence-table image, or a claim-free structural connective — no stemmer,
   no modals/auxiliaries. Slots into `run_tier_b_core` (and `screen_candidates`) after
   `passes_overmatch_filter`, before the judge. Vetoed rewords get `drop_reason="provenance"` and keep the
   Tier-A bullet; counted by a separate `provenance_rejected` counter, never folded into B4's fabrication
   numerator. Placed here rather than P4 because it is a truth gate, not a craft gate.
4. **DONE.** Slot-filled assertion (job-apps resume-transfer §13.1) — shipped as a standalone
   `validate_slots(resume)` function (a build-time refinement from a `Resume` `model_validator`, which
   would run on every construction including legitimately-partial intermediate models), raising
   `ResumeValidationError`, called once on the tailored model right before render. Its
   bullets-per-entry clause was narrowed by D-226: an entry that **declares** `bulletless` may render
   with none. Every other route to an empty entry — including one whose declared bullet source resolved
   to nothing — is still refused, so the assertion's fail-closed direction is unchanged.
5. **DONE.** Degraded path (job-apps §13.3): on compile failure or page-limit overflow, retry with the
   untailored résumé before giving up. A plain résumé beats none. Only if the untailored master is also
   unshippable is that lead dropped — non-fatal for the run unless every shortlisted lead fails (D-021).

**Gate P1: MET.** On a real run, **100%** of leads emit a PDF; **0** page-count violations; **0** overfull
boxes (Typst-native: page count honestly stands in for the vacuous LaTeX concept); compile log captured
per lead; and an injected compile failure demonstrably falls back to untailored rather than losing the
lead. Evidence: deterministic tests pinning every catalog branch, plus a real-store dogfood 2026-08-07
exercising both the FATAL/drop path (live default `resume_max_pages=1` against Mit's real 2-page résumé)
and the 100%-PDF path (isolated store copy at `resume_max_pages=2`) — full record in `METRICS-ARCHIVE.md`
§"Session 9 — P1a dogfood" and `DECISIONS-ARCHIVE.md` D-032.

### P2 — Profile object and the keystone invariant

The declaration mechanism already exists — resolvers are declared `@resolver("experience_years",
inputs=("total_years_experience",))`. What is missing is *enforcement* and *reporting*.

1. **Versioned, validated, hashed profile**, part of every verdict cache key.
2. **`work_authorization.needs_sponsorship` as a field distinct from `status`.** This is the whole
   work-auth fix (§6, correction 6) — one disambiguating bit, not a rebuild. **DONE (session 10, D-034):**
   orthogonal bit on `WorkAuthFact`, influences sponsorship rules only (never citizenship), `None` = prior
   behaviour.
3. **Enforce the invariant:** a rule whose declared field is missing or unresolvable returns
   `ABSTAIN(missing_profile_field:X)` — never ELIGIBLE, never INELIGIBLE.
4. **Three-tier rule taxonomy** — universal / profile-dependent / field-dependent — as versioned *data*,
   keyed by `career_field`. **DONE (D-075) — as a MECHANISM, not a populated taxonomy.** `rules.yaml`
   gained a required per-family `tier` (`universal|profile|field`), a flat `applies_to`, and a closed
   top-level `career_fields` list (`CATALOG_REVISION` 1→2, so every cached verdict re-keys once);
   `Facts.career_field` is validated against that list and hashed unconditionally into `profile_hash`;
   `engine.field_applicability` routes a field-tier family to **active** (in scope, or not field-tier),
   **skip** (the profile's career field is a valid *other* field), or **abstain** (career field missing
   or out-of-catalog ⇒ `missing_profile_field:career_field`, the keystone), with the field-abstain branch
   taking precedence over the posting-waive branch. `not_applicable` is report-only and never persisted
   as a disposition. All six bundled families are `tier: profile` and the bundled `career_fields` is
   `[software]`, so bundled behaviour is unchanged and the routing is exercised by test fixtures only.
   Non-tech field **content** is deliberately out of scope here — D-054 gathers it per user at
   onboarding, never authored by us; see item 8.
5. **INELIGIBLE must carry a quoted span** from the frozen JD. No span ⇒ downgrade to ABSTAIN.
6. **Evidence chain for ELIGIBLE too** (job-apps spec-1 §6, where it says boardwatch should beat it):
   which rule cleared which requirement, against which profile field, citing which span, and which rules
   abstained. "No flags" ≠ cleared. **DONE (session 12, D-036, fix round 1 same session):** the four-table
   evidence chain already stored the requirement rows (or zero); `AuditView.presentation` (a typed
   `VerdictPresentation`) derives `eligible_no_rules_applied` / `eligible_cleared` / `eligible_mixed` from
   the existing rows' dispositions (`met_count` vs. total), and `show` renders all three distinctly — never
   claiming a non-`met` row (e.g. a D-035 `preference`-family unmet row) is "cleared" — no schema change,
   stored `verdict` unchanged.
7. **The severity/policy layer — the actual reason `ineligible` is unreachable.** `facts.py`: *"Only
   `blocker` can yield `ineligible`."* All six families shipped `default_policy: preference` in
   `rules.yaml` (line numbers deliberately omitted — they drift). Live consequence: **1,713** unmet *required* dispositions,
   **1,427** evaluations carrying one and still verdict `eligible`, **0** `ineligible` ever. Mit was
   unaffected only because he set `work_auth: blocker` by hand — **a fresh user with a perfect profile
   got zero ineligible verdicts by default.** That is the multi-tenancy requirement failing at exactly
   the point `CLAUDE.md` forbids. Severity belongs in the published/personal split (§3b): the *mechanism*
   and sane per-field defaults ship; the *assignment* is the user's. **DONE for `work_auth` (session 11,
   D-035):** the `work_auth` family now ships `default_policy: blocker` — the canonical hard stop, most-developed
   family, keystone-gated (abstains to `uncertain`, never `ineligible`, when the fact is absent). A fresh
   profile now gets a decisive `ineligible` on a genuine work-auth stop. The other five families
   (`experience_years`, `clearance`, `degree`, `contract_not_fte`, `internship`) remain `preference` —
   they are false-skip-risky and stay opt-in pending Mit's decision.
8. **The onboarding field-taxonomy gatherer — NOT STARTED, owner-gated, needs its own brainstorm.**
   D-054 settled that non-tech field content (eligibility taxonomy, vocabulary, persona) is **gathered
   per user at onboarding as versioned data**, never authored by us. Item 4 shipped the mechanism that
   consumes such content; nothing yet produces it, so the field tier is inert for every real profile.
   This item exists so that deferral stays addressable rather than becoming a silent drop. Scope,
   schedule and design are deliberately **not** specified here — they are the brainstorm's output.
   **The open architecture question it must answer:** `catalog._verify_families_are_wired` requires
   every declared family to have both a registered resolver and a matching `Facts` field, so a
   genuinely new field-specific rule is still *code*, not data — which contradicts "ship the taxonomy
   as versioned data" from `CLAUDE.md`. Until that is resolved, a gathered taxonomy can only re-tier
   and re-scope families that already exist. **It also owns the Gate-P2 clause D-075 deferred:** the
   "same JD × three profiles → three *different* verdicts" test, which becomes satisfiable once
   gathered field content can carry `blocker` severity.

**Gate P2: MET AS RECONCILED (D-075).** Evidence is TEST FIXTURES representing gathered career-field
output, not a live run. Clause by clause: the same JD evaluated against **three** profiles (F-1 OPT new-grad SWE /
US-citizen senior SWE / non-SWE field) yields three **individually correct** verdicts, which **may coincide**
on a generic JD — only `work_auth` ships `default_policy: blocker` (D-035), so divergence beyond that one
family depends on content the field mechanism cannot manufacture by itself; the field-tier mechanism is
demonstrated across **≥3** `career_fields` via test fixtures representing gathered career-field output, not
a live run (D-054 forbids authoring field content ourselves) — covering active routing, skip-for-a-valid-
other-field, and keystone abstain; Mit's profile returns a decisive **INELIGIBLE with a quoted span** on a
JD containing "we are unable to sponsor work visas" (already met, D-035); **0** rules in the catalog lack a
declared-field list; **0** INELIGIBLE verdicts lack a span; per-rule abstain rate reported for all rules,
with `not_applicable` distinguished from `never_fired`. The dropped "three **different** verdicts" clause
is **deferred, not retired** — it is a gate clause of item 8, the onboarding gatherer. Numbers in
`METRICS-ARCHIVE.md` §"Gate P2".

### P3 — One command, unattended (live gap closed)

Port job-apps' orchestration contract (spec-3) — it is the most scar-tissue-dense document in the handover
and nearly every line is an incident.

1. **Lock — augment, do not replace.** `scan/coordinator.py:73` already uses `FileLock` (a declared
   dependency) and already provides the atomicity. Add only what is missing: pid/started/**token**
   metadata, stale reclaim by atomic **rename** (never `rm -rf` — two racers that both see a dead pid
   would otherwise delete each other's lock), unlock only on token match, and a held lock that
   **notifies loudly with the blocking pid** rather than silently no-opping. Porting job-apps' `mkdir`
   primitive wholesale would contradict this repo's own reuse-first default. **PARTIAL** (D-043) — the
   notify-loudly clause is **DONE**: a message-only `scan.lock.meta` sidecar (pid/hostname/started_at,
   written/removed around the existing `FileLock` acquire/release, never a lock authority) names the
   blocking process on contention, falling back to the generic message if the sidecar is missing or
   malformed. Still open: the review (`slice2-design.md`) found the token/stale-reclaim/reaper design
   UNSOUND as written (rename doesn't arbitrate the same primitive `FileLock` locks) — that redesign,
   and the run reaper, remain deferred to a future P3 slice.
2. **Freshness, not existence** — is this artifact from *this* run? **DONE** (D-038) —
   `pipeline/freshness.py::check_run_freshness`: a `<date>/` folder's `funnel-<run_id>` must map
   to a `runs` row with a terminal status, `started_at`/`finished_at` dated to that folder, and
   its lead folders on disk must reconcile with the store's tailored-artifact row count for that
   run_id. No new schema; every clause named independently so a caller can say WHICH one failed.
3. **Written fatal-vs-non-fatal contract** before coding it (job-apps spec-3 §12 is the starting table).
   **DONE** (D-037) — `docs/program/RUN_CONTRACT.md`, derived from and cited against the four existing
   fatal conditions; the `running`+NULL-`finished_at` gap is named there but left to slice 2's run reaper.
4. **Systemic-outage guard** reading the **decision** field, not the status field. Status is a policy
   output and is blind to a total outage by construction. **DONE** (D-037) — the predicate was already
   correct but duplicated; consolidated into `is_systemic_scan_outage` (`scan/coordinator.py`), used by
   both `run_pipeline` and standalone `run_scan`, no behavior change.
5. **Zero-output guard** — a run producing nothing exits non-zero unless zero was provably right.
   **DONE** (D-039) — `pipeline/runner.py::_zero_output_guard`: provably right IFF the count of open
   postings verdict `eligible` AND judged with THIS run's `run_id`
   (`run_funnel_queries.count_eligible_judged_this_run`) is 0. Run_id-attributed, not a cross-run
   "handled ledger" — a steady-state day where every eligible posting is a prior-run cache hit reads as
   honest with no new bookkeeping.
6. **Filesystem-truth counts** as independent verification of the DB's self-report. **DONE** (D-039) —
   `pipeline/freshness.py::folders_reconcile`, factored out of slice 4's own reconciliation so the
   pipeline can call just this clause mid-run, before the funnel or a terminal `runs.status` exist.
7. **Morning artifact** — ranked leads, apply URL, PDF path, verdict + span, one line of why.
   **DONE** (D-038) — `reports/morning.py`, `morning-<run_id>.{json,md}` beside the funnel,
   sourced from the same run-scoped tailored-leads population as the funnel, never from
   cursor-scoped `digest`/`notify`.
8. **Single-writer discipline** on the SQLite file, a documented WAL stance, and a test that opens two
   writers concurrently (job-apps spec-2 §10.1). **The test must cover the cross-OS case**, not just
   same-OS: boardwatch ships a Docker image over a host-mounted DB, which *is* the Linux-container-plus-
   macOS-host configuration that corrupted job-apps' primary key. A same-OS test will pass and prove
   nothing about the failure actually at risk.
   **DONE** (D-241). Documented stance: `WAL_DISCIPLINE.md`. Single-writer discipline: the scan lock +
   unique indexes (D-020, D-041). Same-OS two-writer test: `tests/pipeline/test_two_writer_concurrency.py`
   (two subprocesses append concurrently; `PRAGMA integrity_check == ok`; no lost write). The cross-OS case
   **cannot run in GitHub CI** — macOS runners have no Docker — so it is handled by prevention, not a test:
   `store/fs_safety.py::unsafe_wal_filesystem` + `get_engine` **refuse** a WAL-unsafe filesystem (a host
   bind-mount reads as `virtiofs`/`fuse.grpcfuse` inside the container; a named Docker volume reads as
   `ext4`/`overlay` and is cleared; non-Linux hosts have no `/proc/self/mountinfo`, so local runs are never
   refused).
9. **Cohort completeness as a mechanism, not a phrase.** Item 5's "unless zero was provably right" *is*
   cohort completeness. A day is `complete` only when every posting that materialised into a **candidate**
   reached a terminal state — not every posting observed. That distinction cost job-apps several days of
   an evidence window to scaffold-only orphans that never settled. **DONE** (D-039) —
   `pipeline/runner.py::_cohort_guard`: the candidate set is `ranked.visible` (verified to already exclude
   `skipped_not_new`), reconciled against `summary.tailored` ∪ `summary.tailor_failed_ids` by **posting_id
   SET**, not by count — a compensating bug (one candidate lost, another double-counted) can balance a
   count identity but cannot hide inside a set difference.
10. **Tier-B quota and idempotence.** At 2 model calls per bullet, B1's ≥10 leads/day is ~300 calls/day
   unattended. Needs: meta-hash idempotence keyed on JD + template + model + prompt version +
   `profile_version` + `persona_version` so a re-run is not a full re-tailor; batched judging in the API
   lane (the agent lane already batches); and **split rate-limit classes** — a quota cap aborts the batch,
   a transient 429 retries with backoff. Untailored leads stay pending for a resumable re-run, and the
   run **never silently downgrades** to the deterministic engine to finish.
   **PARTIAL** (D-040, D-146). The transient-429/5xx retry half is DONE (D-040). Lane-death
   classification, latching, and honest reporting are DONE for the two lanes that actually call
   out (D-146). **The premise of this item is retracted:** `boardwatch run` makes ZERO LLM calls
   in the tailor lane — `pipeline/runner.py` never constructs a client and passes none to
   `run_tailor`, so `reports/tailor.py:459` skips Tier B on every unattended run. There is no
   ~300-calls/day workload to bound until the pipeline is wired, which is an open owner decision,
   not part of this item. Resumable idempotence is **declined**, not open (D-042). Batched judging
   remains deferred.

**Gate P3:** **7** consecutive unattended runs with **0** silent empty days, **0** runs reporting success
while producing nothing, **0** stale-day feeds, and the two-writer discipline enforced (D-241): the same-OS
two-writer test green, and the cross-OS bind-mount config refused at runtime, since it is not CI-runnable.
(Seven, not fourteen — the 14-day clock is acceptance and runs after P6.) **The item-8 test/guard half is
DONE**; the 7-run half is operational and begins when Mit stands up the daily unattended run.

### P4 — Craft

The deterministic craft rubric is the thing job-apps explicitly does not have and says boardwatch should
beat it on. It is a perfect fit: quality as deterministic, evidence-linked assertions on a compiled artifact.

1. **Port `overmatch.py`** near-verbatim — verbatim-span lift (n-gram overlap with the JD) and
   unusual-capitalization copying. Fully deterministic, no model.
2. **Canonical technology vocabulary + aliases**, per field, so "re-spell to the JD's wording" is safe.
3. **Extend the guard:** banned register · buzzword-density ceiling · verb-opening diversity ·
   **requirement-echo detection** (a bullet restating a JD requirement instead of describing work done —
   the most damaging AI-résumé tell).
4. **Deterministic title** with seniority stripping. A senior-titled JD must not stamp "Senior" on a
   new-grad résumé.
5. **Section order, bullet length distribution, bullet count per role, contact-block integrity,
   escaping, no template artifacts** — asserted, not hoped for.
6. **Keyword coverage measured properly** against JD requirement terms, achieved only by re-spelling
   existing facts.
7. **Persona registry** — D-011 commits to two personas (SDE / iOS) with *different* protected-fact sets,
   and no phase built the mechanism. It lands here: a registry format, **deterministic** JD→persona
   selection (role family + primary stack, never a model free-choice), per-persona project emphasis,
   skill ordering, title, and immutable-fact subset. Published mechanism, personal instance (§3b) — the
   protected-fact set is a property of the persona, never a global constant.

**Gate P4:** **0** anti-slop violations in shipped output over a run; every §3.P4 check emitting a
pass/fail per lead; and the one subjective gate in this program — **blind craft review**: Mit reads 10
tailored résumés with no indication of origin, mixed with job-apps output, and cannot pick boardwatch's
out as worse.

**Making that gate executable.** `STAGE1_ONLY=1` means job-apps produces **no new résumés**, so "mixed
with job-apps output" has no live comparison set — the gate as first written was unexecutable, which is
job-apps' own anti-pattern §11.6 (*a procedure that cannot produce the evidence it requires*). The corpus
is job-apps' **392 existing `_applied/` folders**, which do exist on disk. Note the tension with D-008,
which retired boardwatch-vs-job-apps comparison: this is not a parity metric, it is a blind quality
control for a subjective judgement, and it does not feed any bar metric.

### P5 — Eligibility that decides

1. **Expand rule families** toward the hard-stop space that matters (sponsorship · clearance/citizenship ·
   years floor · seniority language · internship/co-op · employment type · location · credentials ·
   role-family · stub · closed · graduation window).
2. **Closed catalog, out-of-catalog ⇒ unjudged** — the mechanism that prevents 216-bucket sprawl.
3. **Named exceptions carried forward** (job-apps spec-1 §3, its highest-value single transfer):
   `up_to_n`, `range_0_n`, `internships_count`, degree-or-experience alternatives — passed to the decider
   *with the exception name*, not silently filtered.
4. **REQUIRED vs PREFERRED section context** decides whether a year count is a floor.
5. **Labeled evaluation set** — ~200 JDs stratified across families with human-verified verdicts and
   quoted spans, plus ~50 **hard negatives** (JDs that look like hard stops and are not). Curated from
   job-apps' 17,942 skipped folders; permission granted and standing (§7).
6. **Port job-apps' 35+ visa/sponsorship block phrases** (`batch_tailor_pipeline.py`, roadmap §10 —
   *"months of false-negative tuning"*). boardwatch's own `no_sponsorship_offered` already fires on 5.5%
   of postings; this is a near-free recall win on the exact rule that carries bar metric **B7**. Take the
   calibration with it: a bare aggregator "No H1B" tag alone is **REVIEW, not a hard stop**, because it is
   frequently aggregator metadata rather than JD prose.
6. **Every quarantine gets a drain, designed in the same change as the quarantine**, running on both
   sides of the gate.
7. **Deterministic default stays the default.** Any model lane is opt-in, cached on a key including
   `profile_version` and `catalog_version`, with an invalidation path shipped from day one.

**Gate P5:** on the held-out labeled set, **precision ≥ 0.95 on INELIGIBLE** (false-skips silently delete
real jobs and are the expensive error), abstain rate reported per rule, **0** INELIGIBLE without a quoted
span. Recall is explicitly secondary.

**Scored under which policy — this must be stated or the gate is undefined.** Precision on `INELIGIBLE`
is meaningless until severity assignment is fixed, because under the shipped all-`preference` default the
count of `INELIGIBLE` is structurally **0** (P2 item 7). The labeled set is scored under a **declared
reference policy** shipped alongside it — every family at `blocker` — so the gate measures the *rules*,
not a user's tolerance. Mit's personal policy is then a separate, unscored instance.

**Gate P5 measures INELIGIBLE precision on modeled-family hard stops only.** The deterministic engine is
title-blind and fires only on the six catalog families (`work_auth`, `experience_years`, `clearance`,
`degree`, `contract_not_fte`, `internship`); hard stops in unmodeled families — seniority language,
location, role-family mismatch — are out of the engine's scope by construction, and the oracle labels
them `uncertain` rather than force-fitting them into the nearest family.

**The P5b oracle-judge labeling build slices B1–B4 are blocked until the answer key's audited coverage ≥
`SHIP_AUDIT_COVERAGE_BAR` (default 20%)** — enforced mechanically by `boardwatch eligibility score`'s
non-zero exit when an ineligible label exists and `meets_ship_gate()` is `False`; the oracle-only
measurement is provisional until audited.

### P6 — Liveness and dedup

1. **Posting-identity table** separate from URLs, multiple ranked identity kinds per posting; only exact
   identities may suppress.
2. **Allowlist URL normalization** (not a denylist) + `sorted(kept)` + **string-verify on hash hit**.
3. **Cross-host identity** — `company + normalized_title (+ location)` as a second key; on collision keep
   the direct-ATS URL, drop the aggregator.
4. **Durable ledger over decisions, not artifacts**, with `built`/`skipped` permanent and `seen` TTL'd,
   monotonic upserts, lazy read-time expiry, and a **policy-version stamp** on permanent dispositions.
5. **Applied-state suppression** — wire the existing `track` ledger into surfacing (§6, correction 3).
6. **Liveness never cached; verdicts always cached.** Two signals with documented precedence: a saved body
   containing a closed phrase is authoritative; a live re-fetch 404 is suggestive. Fail-open on unknown.

**Gate P6:** duplicate leakage **measured** over 7 days and **≤ 5%**; **0** dead postings reaching the
lead list; a deliberately-injected hash-collision test proving the wrong job cannot be deduped; and a
suppression audit of 20 sampled suppressions confirming each was a genuine duplicate or policy skip.

**What counts as a duplicate, for the leakage clause: only an `exact_quad` identity** — company + title +
location + body (D-283). A shared body hash alone is not a duplicate, and neither is company + title +
location alone; 727 body-hash groups span genuinely different titles and locations, so either broader rule
merges distinct jobs. This matches `SUPPRESSING_KINDS` in `core/identity_kinds.py`, so the gate measures
the rule the code already enforces. **Leakage is counted over JOBS that reached leads, not over the
corpus** — a corpus-wide suppression rate answers a different question, and the unit is the job because
`job_dispositions` is keyed on `job_id`, so counting postings would read a correct `regroup` merge as a leak.
A body-less posting is withheld an `exact_quad` identity by design, is therefore unjudgeable here, and is
reported in its own bucket that is never folded into either neighbour.

### Acceptance — the 14-day run

System frozen. All seven bar metrics (§1) measured daily into `docs/program/METRICS.md`. Any code change
to eligibility, profile, or the résumé gate resets the clock and that reset is recorded.

**It runs as a background confirm, after the provisional pass (§1, D-280)** — it no longer gates the
"done" call. It is still the only measurement of the bar over a full 14 days, and a reset still costs the
whole window, so the freeze is real for its whole duration.

### P7 — Breadth

**The unlock condition is MET and breadth is in scope now (D-271, D-272, D-280).** It required attribution
data from boardwatch's own funnel showing that direct-ATS-only is starving it, rather than inferring it
from job-apps' filter stack. Measured: of job-apps' 530 eligible records over 2026-08-12…08-21, **41
(7.7%)** are at a company boardwatch watches; the set spans **352** companies against boardwatch's **24**,
and the largest misses (Amazon, TikTok, AWS, Apple, ByteDance, SpaceX) use **none** of the six supported
ATS providers — so no slug can reach them. Three lanes are approved, bespoke first-party adapters are not
(D-272).

Then: company list as a user asset, not a repo constant · a growth mechanism *and* a slug-rot repair
mechanism (inventory decays on its own) · any aggregator lane behind all the same gates plus a
dereferencing step, with a hard assertion that no aggregator URL survives into the final apply surface ·
judge every new source by **leads produced over ≥3 runs**, never by discovered count.

---

## 3b. Published mechanism vs. personal instance — a system-wide split

**Mit, 2026-08-06:** *"Eventually the system will adapt to anything the end user asks. So we have to
publish the generalized version while we keep the active work on this machine personal. This applies
system wide."*

This is a governing constraint on every phase, not a packaging step at the end. boardwatch is a shipped
product; job-apps failed exactly here, with hardcoded paths, user-specific "sacred metrics", and a second
tenant (`Hetvi/`) that had to live in a parallel directory with the shared logic switched off.

Every subsystem therefore splits in two, and **the split is designed in at the same time as the feature**:

| Subsystem | Published mechanism | Personal instance (local, never published) |
|---|---|---|
| Personas | Registry format; deterministic JD→persona selection | Mit's two: SDE / iOS, with **different** protected-fact sets |
| Profile | Versioned schema, validation, hashing, cache-keying | Mit's values, incl. `work_authorization.needs_sponsorship: true` |
| Eligibility rules | Universal + field-dependent catalogs, as versioned data | Profile-dependent resolution against Mit's declared fields |
| Companies | Seed registry + import mechanism | Mit's 135 imported targets |
| Résumé | Template format, equivalence-table format, QA rubric | The authored corpus and immutable facts |

**Precedent already set:** P8 imported 85 boards as *user config* and registry promotion was declined on
purpose. That instinct was right; this makes it a rule.

**Test for every catalog added from here:** could a US-citizen senior nurse use this without editing code?
If the answer needs a code change, the catalog is in the wrong half of the split.

---

## 4. Deliberately NOT doing

| Not doing | Why |
|---|---|
| Cover letters · outreach/referrals · auto-apply, auto-fill, browser automation | Mit's explicit deferral. Not scope creep candidates. |
| Rebuilding the tailoring architecture | Already built and correct — see §6 correction 1. job-apps' §14 steps 2/3/4/6 are done. |
| ~~The ~2,200-line JD acquisition + stub recovery chain~~ | **THE DEFERRAL CONDITION HAS BEEN MET (D-272).** This was deferred "to P7 where a non-API source might first appear"; three now have. A body-less posting is a stub, and the engine is body-only (`preflight.py` reads `posting_versions.body_text` alone), so under D-250 every aggregator posting would abstain to `uncertain` and never surface — the lane would add corpus and **zero leads**. boardwatch does NOT need job-apps' 2,200 lines: P7's own required dereferencing step is also the fix, because an aggregator link mostly resolves to an ATS board whose parser already exists. |
| ~~Matching job-apps' ~35 leads/day~~ | **SUPERSEDED 2026-08-22 (D-272).** `DEFAULT_TOP_N` goes 8 → 40 at the owner's ruling. The ≥10 bar was set when the cap hid nothing worth seeing; run 67 discarded **3,502 postings that cleared every gate**, and the cap also makes P7's own gate un-runnable (per-source yield is `8/26,997` with the numerator fixed by construction). |
| A 216-bucket reason taxonomy | Closed versioned catalog; matched pattern is event metadata, never bucket identity. |
| Transitive dedup clustering | Chains unrelated postings at a 0.85 threshold. Pairwise only, deliberately. |
| Multi-pass Typst compile | No cross-references in the template. Revisit if that changes. |
| ~~Statistical parity testing vs job-apps~~ | **REOPENED 2026-08-22 (D-271/D-272).** D-008 retired it and the bar stayed absolute for a year of program time; the owner then asked for a comparative guarantee and it was measured. boardwatch sees 7.7% of job-apps' eligible yield. The absolute bar in §1 still stands — parity is now an *additional* bar, not a replacement. |

---

## 5. Where I disagree with job-apps

Seven documented departures. Corrections 1–4 are factual (job-apps never read boardwatch's code and said
so); 5–7 are judgment.

**1. The architecture is already built — but the claim is LANE-SCOPED.**
*(Corrected 2026-08-06 after independent review — see D-013. The original wording overstated this in
boardwatch's own favour, which is the exact failure D-012 exists to catch.)*

job-apps: *"If boardwatch hands a model the Typst source and asks for Typst back, that is the root cause of
the quality problem Mit saw."* That specific claim is false for both lanes: `tailor/model.py` defines a
typed `Resume/Entry/Bullet(bullet_id)/SkillGroup` skeleton, `rewrite/prompt.py` sends **one bullet's plain
text** and demands *"Return ONLY the reworded bullet as a single line"*, and `render/typst.py` emits 100%
of the markup and escapes every model-authored token. Per-bullet independent keep/revert is present.

**But the safety story splits by lane, and only Tier A is strong:**

| Port step | Tier A (deterministic) | Tier B (LLM/agent — the lane in daily use) |
|---|---|---|
| 2 — typed skeleton, plain-text contract | done | done |
| 3 — Python owns markup + escaping | done | done |
| 3 — **pre-accept `compiles()` check** | **absent** — compile happens *after* acceptance, failure is silent | **absent** |
| 4 — per-bullet keep/revert | done | done |
| 4 — **token-provenance validator** | `safety.py::output_is_entailed` (token-for-token identity modulo an approved equivalence table — genuinely stricter than job-apps) | **NONE.** `enforce_tier_a` never runs here and structurally cannot: any reword fails token-identity. Documented in `reports/tailor.py:17-21`. Only guard is `rewrite/filter.py`'s heuristic + a judge on the **same client and model as the proposer**. |
| 6 — batched entailment judge | n/a | present but **not batched** in the API lane: 2 calls *per bullet* vs job-apps' ~2 per folder |

`rewrite/filter.py:45-65` blocks new digits, ALLCAPS, taxonomy skills and mid-sentence Title-case nouns.
It does **not** block new ordinary words: *"Optimized the ingestion service"* → *"Single-handedly
re-architected the ingestion service, eliminating downtime"* adds no digit, no entity, no taxonomy skill,
stays under 1.5× length, and passes.

**Consequence:** steps 2 and 4-keep/revert are done. Step 3's pre-accept compile check, step 6's batching,
and a **Tier-B token-provenance validator** are NOT — they are P1/P4 work items, not things to skip. The
craft problem's cause is still no page-count gate, no anti-slop guard, no craft rubric. It is not an
architecture rebuild.

**2. The PDF cliff is a silent-degrade defect, not a packaging problem.**
job-apps prescribes vendoring the Typst binary. (**Superseded by D-058/D-060** — the engine is now
tectonic + LaTeX; the vendoring argument below still applies, with `tectonic` as its subject.)
`typst` is installed at `/opt/homebrew/bin/typst` and
`reports/tailor.py:104` shells out to it correctly. The actual defect is `tailor_cmd.py:193` printing
*"source only (no PDF; typst not available or compile failed)"* and continuing — a silent degrade that
also conflates an environment fault with a lead fault. Fix is a hard gate plus disambiguation. **Shipped —
P1a (D-032, §3.P1) closed this exact defect: Gate P1 is MET.** Vendoring is a P7-era distribution
concern.

**3. The applied write-back path already exists; the gap is the suppression loop.**
job-apps: *"Build the marking path in Phase 5."* `boardwatch track add|status|list|log` already writes an
immutable `application_events` ledger with attempt numbers. What is missing is that **nothing consumes
it** — `grep` finds no applied-suppression in `queries.py` or `top_cmd.py`, and `applications` has **0
rows** (the path exists and has never been exercised). That is a much smaller, differently-shaped task,
and it belongs in P6 next to dedup, not P3.

**4. Stub defense is near-zero priority today, and job-apps' own text concedes it.**
gap-audit §1.1: *"If boardwatch is judging its postings on ATS-API JSON only, it may be fine today."* All
six providers are structured ATS APIs. The ~64% stub rate is a pathology of LinkedIn/Indeed HTML scraping,
which boardwatch does not do. Building a 2,200-line recovery chain now is building for a source type that
does not exist yet. **I take the metric and defer the machinery:** stub rate becomes a P0 number, and if
it is ever non-trivial the chain gets built then, with evidence. This is my largest ordering disagreement.

**5. The work-auth diagnosis is wrong even though the fix is right.**
job-apps: *"The engine cannot decide because it has nothing to decide against."* Reading `resolve.py:167–
177`, the engine has plenty to decide against and abstains **deliberately**, with the reasoning in a
comment: it cannot distinguish an F-1 OPT holder who will need sponsorship from an asylee with an EAD who
needs none. It lacks **one disambiguating bit**, not a profile object. job-apps' own proposed schema
contains exactly that bit (`needs_sponsorship: true`). So the fix is one declared field plus enforcement —
cheap — not a phase-sized rebuild. Worth stating precisely, because "the engine is non-functional" and
"the engine is missing one input" imply very different amounts of work.

**6. Output-side work can precede input-side work without violating job-apps' own ordering principle.**
*Breadth multiplies whatever is downstream of it* constrains **input**. PDF emission and unattended
running are downstream terminals — they multiply nothing. job-apps' roadmap puts them at positions 5 and 6
of 7, which means ~4 phases of latency while Mit gets zero résumés a day. I move the résumé artifact gate
to P1 and the unattended runner to P3, and keep breadth last. This is consistent with job-apps' principle,
not a departure from it.

**7. No phase gate is "run for 14 days."**
job-apps' Phase 5 gate is *"14 consecutive unattended days meeting §1's bar."* Using the acceptance run as
a mid-program gate is a scheduling error: the clock measures a frozen system, and P4/P5/P6 all mutate
eligibility and the résumé gate. Running it at P5 guarantees either a reset or 14 days of uninterpretable
data. P3's gate is 7 days of *operational* stability; the bar is measured once, after P6.

**Not disputed, and adopted wholesale:** the keystone abstain invariant · the three-tier rule taxonomy ·
breadth-last · closed reason catalogs · certainty-determines-consequence in dedup · the fail-safe direction
table · the lock discipline · the systemic-outage guard reading the decision field · never caching
non-terminal verdicts · policy/prompt version split as the cache-invalidation knob · every quarantine
needs a drain.

---

## 6. Program machinery

| File | Purpose | Rewritten |
|---|---|---|
| `docs/program/PROGRAM.md` | This file — phases, gates, scope, disagreements | On phase change or gate revision |
| `docs/program/STATE.md` | **Read first.** Current phase, shipped, next, blocked, open questions | **Every session, without exception** |
| `docs/program/DECISIONS.md` | One entry per architectural decision: context, choice, alternatives rejected. D-077 onward, plus the index spanning both decision files | Append-only |
| `docs/program/DECISIONS-ARCHIVE.md` | D-001 … D-076, verbatim (D-108) | Closed |
| `docs/program/METRICS.md` | Per-run numbers so gates are checkable over time. Live tables, P6-era records, plus the index spanning both metrics files | Every run |
| `docs/program/METRICS-ARCHIVE.md` | The closed P0–P5 session records (D-108) | Closed |
| `CLAUDE.md` | Session-start ritual + repo conventions | Rarely |

---

## 7. Resolved — Mit, 2026-08-06

All four answered. No open questions block the program.

1. **Labeled set sourcing — permission granted, standing.** Reading the job-apps repo is authorized from
   now on; it was revoked only for the preceding self-assessment session so the plan would be honest.
   P5 curates its ~200 labeled JDs + ~50 hard negatives from job-apps' 17,942 skipped folders.
   Accompanying instruction, adopted program-wide: **check and verify rather than assume.** A failed
   command is not a negative result; a recalled number is not a measured one.
2. **Two personas — SDE and iOS**, matching Mit's job-apps setup, with different protected-fact sets.
   Built through the published persona-registry mechanism; Mit's two are local instances (§3b).
3. **`needs_sponsorship: true` for Mit** — declared knowingly, and declared *per user*. Never inferred,
   never defaulted (§3b).
4. **Daily output stays `~/boardwatch-applications/<date>/`** — what `bwd` already builds becomes P3's
   morning-artifact home.
