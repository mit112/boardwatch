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
──  14-day acceptance run  → the bar, measured on a frozen system
P7  Breadth                → only now is more input worth having
```

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
   written to `<out_root>/<date>/funnel-<run_id>.{json,md}`, outside the git tree (D-024). Two departures
   from the stage list above, both measured rather than assumed: the head is the **open-posting corpus**,
   not `observed`, because `postings_seen` and `open_postings` are different populations (D-022); and
   `unique` reports **not instrumented** rather than 0, because dedup is P6 and has never run (D-023).
   Carries the abstain report for every catalog rule, per-lead board provenance, and two cross-checks that
   recount the deliverable from the store.
2. **Per-rule abstain rate**, every run. This is the metric that makes a rule that cannot fire *visible*.
3. **Per-source outcome table**: `unique | assisted | eligible | leads | applied`.
4. **Run manifest**: config hash, profile version, rule-catalog version, code fingerprint of
   decision-relevant modules, start/end, exit status.
5. **Reconciliation check** — an invariant sweep asserting DB rows and on-disk artifacts agree. Counts
   from a different path than the one that produced them (job-apps spec-3 §6: self-report ≠ verification).
6. **Stub-rate metric** at judge time — one number, reported every run. Cheap insurance; see §6 correction 4.
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

### Bar → phase → gate traceability

Every bar metric in §1 has exactly one owning phase. Added after review found B1–B7 appeared only in the
§1 table and nowhere else — B4 in particular had no owner and no mechanism anywhere in P0–P6.

| Bar | Owned by | Emitted by |
|---|---|---|
| B1 leads/day | P5 (selection) + P6 (dedup/liveness) | P0 funnel artifact |
| B2 PDF 100% | **P1** | P1 hard gate |
| B3 QA gate 100% | **P1** (mechanical) + **P4** (craft) | per-lead pass/fail |
| B4 0 fabrications, n≥100 | **P1** (Tier-B provenance validator) + **P4** (audit) | P0 fabrication counters |
| B5 0 silent empty days | **P3** | zero-output guard + exit status |
| B6 funnel reconciles 100% | **P0** | reconciliation invariant |
| B7 work auth decisive | **P2** | per-rule abstain + `ineligible` count |

**Gate P0:** three consecutive runs where the funnel reconciles to **100%**, per-rule abstain is emitted
for **every** rule in the catalog, and *which source produced each lead, and why every non-lead was
dropped* is answerable **from the artifact alone, without reading code**.

### P1 — Résumé artifact integrity (live gap, cheapest first)

The render path exists and is architecturally sound (§6, correction 1). What is missing is enforcement.

1. **Kill the silent source-only degrade.** `tailor_cmd.py:193,402` currently prints
   `"source only (no PDF; typst not available or compile failed)"` and continues. Split the two causes —
   binary-missing is an environment fault, compile-failure is a lead fault — and make each a hard,
   distinguishable failure. A lead without a PDF is not a lead.
2. **Page count = hard fail.** N from profile (1 for new-grad). Absent today; verified nowhere in `src/`.
3. **Overflow detection — Typst-native.** *(Corrected: the original clause said "zero overfull/underfull
   `hbox`/`vbox`", copied from job-apps. Those are **LaTeX** concepts. Verified: `typst 0.15.1` exits 0
   with no diagnostic output on a deliberately overflowing document, so that clause was vacuously
   satisfiable and would have been recorded as a pass forever.)* Use a Typst-native check — assert
   rendered page count against the profile's N, and assert content fits via `measure`/`layout` bounds.
   The compile log is currently captured at `reports/tailor.py:104` and discarded; capture it per lead
   for diagnosis regardless.
3b. **Packaging, because P1 turns a degrade into a hard failure.** `typst` is on Mit's laptop but is
   **not** in the `Dockerfile` and **not** in `pyproject.toml`. A hard PDF gate therefore breaks every
   Docker and PyPI user — violating §3b/D-010. Add a `typst` layer to the Dockerfile and a loud
   `doctor`/startup preflight that names the missing binary and how to install it. Hours, not a vendoring
   project; vendoring still waits.
3c. **Tier-B token-provenance validator** (see §5.1) — the lane in daily use currently has none.
   Placed here rather than P4 because it is a truth gate, not a craft gate.
4. **Slot-filled assertion** (job-apps resume-transfer §13.1): if a slot was expected to be filled, assert
   it was, and fail the lead if not.
5. **Degraded path** (job-apps §13.3): on compile failure, retry with the untailored résumé before giving
   up. A plain résumé beats none. Only then fail that lead — non-fatal for the run.

**Gate P1:** on a real run, **100%** of leads emit a PDF; **0** page-count violations; **0** overfull
boxes; compile log captured per lead; and an injected compile failure demonstrably falls back to
untailored rather than losing the lead.

### P2 — Profile object and the keystone invariant

The declaration mechanism already exists — resolvers are declared `@resolver("experience_years",
inputs=("total_years_experience",))`. What is missing is *enforcement* and *reporting*.

1. **Versioned, validated, hashed profile**, part of every verdict cache key.
2. **`work_authorization.needs_sponsorship` as a field distinct from `status`.** This is the whole
   work-auth fix (§6, correction 6) — one disambiguating bit, not a rebuild.
3. **Enforce the invariant:** a rule whose declared field is missing or unresolvable returns
   `ABSTAIN(missing_profile_field:X)` — never ELIGIBLE, never INELIGIBLE.
4. **Three-tier rule taxonomy** — universal / profile-dependent / field-dependent — as versioned *data*,
   keyed by `career.field`.
5. **INELIGIBLE must carry a quoted span** from the frozen JD. No span ⇒ downgrade to ABSTAIN.
6. **Evidence chain for ELIGIBLE too** (job-apps spec-1 §6, where it says boardwatch should beat it):
   which rule cleared which requirement, against which profile field, citing which span, and which rules
   abstained. "No flags" ≠ cleared.
7. **The severity/policy layer — the actual reason `ineligible` is unreachable.** `facts.py:66`: *"Only
   `blocker` can yield `ineligible`."* All six families ship `default_policy: preference`
   (`rules.yaml:72,290,388,606,871,1032`). Live consequence: **1,713** unmet *required* dispositions,
   **1,427** evaluations carrying one and still verdict `eligible`, **0** `ineligible` ever. Mit is
   unaffected only because he set `work_auth: blocker` by hand — **a fresh user with a perfect profile
   gets zero ineligible verdicts by default.** That is the multi-tenancy requirement failing at exactly
   the point `CLAUDE.md` forbids. Severity belongs in the published/personal split (§3b): the *mechanism*
   and sane per-field defaults ship; the *assignment* is the user's.

**Gate P2:** the same JD evaluated against **three** profiles (F-1 OPT new-grad SWE / US-citizen senior
SWE / non-SWE field) yields three different and individually correct verdicts; Mit's profile returns a
decisive **INELIGIBLE with a quoted span** on a JD containing "we are unable to sponsor work visas"
(today: returns nothing); **0** rules in the catalog lack a declared-field list; **0** INELIGIBLE verdicts
lack a span; per-rule abstain rate reported for all rules.

### P3 — One command, unattended (live gap closed)

Port job-apps' orchestration contract (spec-3) — it is the most scar-tissue-dense document in the handover
and nearly every line is an incident.

1. **Lock — augment, do not replace.** `scan/coordinator.py:73` already uses `FileLock` (a declared
   dependency) and already provides the atomicity. Add only what is missing: pid/started/**token**
   metadata, stale reclaim by atomic **rename** (never `rm -rf` — two racers that both see a dead pid
   would otherwise delete each other's lock), unlock only on token match, and a held lock that
   **notifies loudly with the blocking pid** rather than silently no-opping. Porting job-apps' `mkdir`
   primitive wholesale would contradict this repo's own reuse-first default.
2. **Freshness, not existence** — is this artifact from *this* run?
3. **Written fatal-vs-non-fatal contract** before coding it (job-apps spec-3 §12 is the starting table).
4. **Systemic-outage guard** reading the **decision** field, not the status field. Status is a policy
   output and is blind to a total outage by construction.
5. **Zero-output guard** — a run producing nothing exits non-zero unless zero was provably right.
6. **Filesystem-truth counts** as independent verification of the DB's self-report.
7. **Morning artifact** — ranked leads, apply URL, PDF path, verdict + span, one line of why.
8. **Single-writer discipline** on the SQLite file, a documented WAL stance, and a test that opens two
   writers concurrently (job-apps spec-2 §10.1). **The test must cover the cross-OS case**, not just
   same-OS: boardwatch ships a Docker image over a host-mounted DB, which *is* the Linux-container-plus-
   macOS-host configuration that corrupted job-apps' primary key. A same-OS test will pass and prove
   nothing about the failure actually at risk.
9. **Cohort completeness as a mechanism, not a phrase.** Item 5's "unless zero was provably right" *is*
   cohort completeness. A day is `complete` only when every posting that materialised into a **candidate**
   reached a terminal state — not every posting observed. That distinction cost job-apps several days of
   an evidence window to scaffold-only orphans that never settled.
10. **Tier-B quota and idempotence.** At 2 model calls per bullet, B1's ≥10 leads/day is ~300 calls/day
   unattended. Needs: meta-hash idempotence keyed on JD + template + model + prompt version +
   `profile_version` + `persona_version` so a re-run is not a full re-tailor; batched judging in the API
   lane (the agent lane already batches); and **split rate-limit classes** — a quota cap aborts the batch,
   a transient 429 retries with backoff. Untailored leads stay pending for a resumable re-run, and the
   run **never silently downgrades** to the deterministic engine to finish.

**Gate P3:** **7** consecutive unattended runs with **0** silent empty days, **0** runs reporting success
while producing nothing, **0** stale-day feeds, and the two-writer test green. (Seven, not fourteen — the
14-day clock is acceptance and runs after P6.)

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

### Acceptance — the 14-day run

System frozen. All seven bar metrics (§1) measured daily into `docs/program/METRICS.md`. Any code change
to eligibility, profile, or the résumé gate resets the clock and that reset is recorded.

### P7 — Breadth, and only now

**Unlock condition:** P0's attribution data shows, *in boardwatch's own funnel*, that direct-ATS-only is
starving it. job-apps' data suggests this strongly (greenhouse_api 701 unique → 0 built on 2026-08-05) but
that is job-apps' filter stack, not boardwatch's. **Measure it here before spending a week on adapters.**

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
| The ~2,200-line JD acquisition + stub recovery chain | boardwatch reads structured ATS APIs, not scraped HTML. Deferred to P7 where a non-API source might first appear. Replaced now by a one-number stub-rate metric in P0. §6 correction 4. |
| Matching job-apps' ~35 leads/day | The bar is ≥10. 942 candidates → 75 built → **0 applied** with a 465-item queue is the evidence that the marginal lead is worth ~nothing. |
| A 216-bucket reason taxonomy | Closed versioned catalog; matched pattern is event metadata, never bucket identity. |
| Transitive dedup clustering | Chains unrelated postings at a 0.85 threshold. Pairwise only, deliberately. |
| Multi-pass Typst compile | No cross-references in the template. Revisit if that changes. |
| Statistical parity testing vs job-apps | Superseded. The bar is absolute (§1), not comparative. The old P12 pre-registered parity design is retired — see DECISIONS D-008. |

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
job-apps prescribes vendoring the Typst binary. `typst` is installed at `/opt/homebrew/bin/typst` and
`reports/tailor.py:104` shells out to it correctly. The actual defect is `tailor_cmd.py:193` printing
*"source only (no PDF; typst not available or compile failed)"* and continuing — a silent degrade that
also conflates an environment fault with a lead fault. Fix is a hard gate plus disambiguation. Vendoring
is a P7-era distribution concern.

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
| `docs/program/DECISIONS.md` | One entry per architectural decision: context, choice, alternatives rejected | Append-only |
| `docs/program/METRICS.md` | Per-run numbers so gates are checkable over time | Every run |
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
