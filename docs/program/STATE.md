# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and record the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Shipped: `CHANGELOG.md`. Settled
> per-subsystem background: **`STANDING-FACTS.md`** — read the one section for what you are touching,
> never the whole file (D-139). Both logs carry an index spanning themselves and a closed archive
> (D-108): read the index, then the one range.
>
> **States only what is true now**; no sha or commit count (D-017). **Rewrite it, never prepend.**
> **This file holds only what changes between sessions** — current standing, next action, live blockers,
> owner calls. Settled subsystem history was moved WHOLE into `STANDING-FACTS.md` on 2026-08-23d by
> Mit's ruling, and **again on 2026-08-26** (30 settled blocks, this file 511 → ~260 lines, verified
> line-for-line that nothing was lost); nothing was deleted either time. Do not narrate a decision here
> that `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again,
> the fix is to move settled blocks out, not to summarise them away.**

---



## Current standing

### Session 2026-09-03: the queue is audited END TO END, the waste is EXTRACTION — and three items closed by REFUTATION rather than by building

Reasoning: **D-436**, **D-438**, **D-442**, **D-443** (extraction); **D-439**, **D-444** (the slate
cap); **D-445**, **D-446** (the `gh_jid` refutation and the standing duplicates); **D-447** (the
modifier window). Numbers: `METRICS.md`, **both** the `Session — 2026-09-03` and
`Session — 2026-09-03b` blocks. **Run 145** read out below; **run 146** was an eligibility-only
pass (see item 2a). The earlier headline "the catalog is 8% of the problem" is RETIRED — it read a
verdict distribution as a defect attribution, and D-443 names the mechanism it was hiding.

Prior session (2026-09-02d) is settled and NOT restated here: **D-432**, **D-433**, **D-434**,
**D-435**, **D-437**, with its numbers in `METRICS.md` (Session 2026-09-02d).

### The 2026-09-03 queue audit — the waste is catalog COVERAGE, not routing

Blind two-judge audits of what the owner actually opens, reproduced independently by two sessions.
Mechanism: **D-436** (extraction) and **D-442** (the routing read). Full method in METRICS.

**THE HEADLINE THIS SESSION FIRST PUBLISHED — "the catalog is 8% of the problem, routing is the
rest" — WAS WRONG, and it was wrong by reading a verdict DISTRIBUTION as a defect ATTRIBUTION.**
8% of the apply lane carries an `eligible` verdict; that says where verdicts land, not where the
defect lives. Three sessions handed `review_gate.lane()` forward as *the lever* and **none had read
it.**

| | |
|---|---|
| apply lane | **597** — 526 `uncertain`, 49 `eligible`, 22 unevaluated |
| **of the 526, with ZERO requirement rows** | **481-487** (two independent counts) |
| their JD bodies | median **4,636 chars**, only 4 under 200, **~390 over 2,000** |
| `_review` | **1,007** — `experience_requirement` 497, `ineligible_verdict` 288, `role_unconfirmed` 175 |

**The routing is deciding CORRECTLY.** `experience_unconfirmed` fires **497** times, so the flag
works; all 597 apply-lane leads carry both flags False **because nothing was extracted, not because
nothing is wrong**. `_no_evaluable_requirement` makes them `uncertain` and `review_gate` never reads
WHY. **So the ~36% unapplyable rate IS the extraction gap arriving from the other end** — the same
finding as D-436's "every miss was a missing row", and the same reason the abstain report cannot see
it: **a family that extracts nothing is silent, and silence is indistinguishable from "the JD says
nothing".**

**IT SPLITS, AND ONLY A QUARTER IS COVERAGE (D-442).** Probing the zero-row bodies: **128 (26.3%)
carry a years bar in some form** (14 escaped punctuation, 24 spelled-out, 10 parenthesised), 55
citizenship/LPR, 32 sponsorship, 6 clearance, 4 non-English, **0 degree-required**. The other **~74%
trip none of those probes** — for those the JD may genuinely state no catalogued requirement, making
`uncertain` correct and the only question what an apply lane should DO with it. **The negative half
is bounded by those probes and nothing wider**: widening them can only move leads from the second
population into the first, never the reverse.

**THE GATE IS MEASURED, NOT ESTIMATED.** 77 apply-lane leads, two independent judges, real schema,
nothing applied: **15 demoted (19.5%), and 15 of 15 rejections survive `accept_oracle_verdict`'s
keystone span guard — ZERO span failures.** Every rejection quotes the employer's own JD, and two are
cases no amount of pattern work reaches (a French-language JD; markdown-escaped punctuation). Scaled
to 597: ~**116 demoted, each with a checkable quote**. Verdicts at `{config_dir}/verdicts_a.json` /
`verdicts_b.json` — **spot-check, then `gate apply`**. The earlier "~50-100 wrongly removed" treated
inter-rater disagreement as error-against-truth and ignored the guard; **retired**.

**Treatment vs cure.** The `final_gate:` LLM lane is the TREATMENT — it reads the JD directly and
catches what the patterns miss. **Catalog coverage is the CURE**, and the instrument is
**partial-match instrumentation of the patterns themselves** (a family that ALMOST matched), which a
cue vocabulary cannot substitute for: correct silence and a missed extraction look identical to a
cue and different to a near-miss. **D-442 holds the routing question** — ~360 of the 481 have no
detectable requirement at all, so it is "what should an apply lane do with a JD that states
nothing?", a decision about what the lane MEANS rather than a bug fix. Priced: apply **597 → 116**.

**The queue's 219 redundant leads are MOSTLY NOT A DEFECT (D-439).** 127 duplicate
`(company, normalised-title)` groups, but only **45 groups / 76 leads share one `content_hash`**;
the other **82 groups / 143 leads are genuinely distinct requisitions** (Evlo AI ×9 is nine real
reqs). An earlier reading called it identity resolution — **wrong**. The mechanism is D-345's cap
DEFERRING rather than dropping while scoped to one run, so a one-JD group delivers one member per
run forever. CGS Federal ×10 on a single hash is the shape that IS a defect.

**Sized and NOT built:** un-escaping markdown bodies 2.2% (owner-gated, re-versions postings);
`role_gate` missing the inverted `Engineer, Software` form (5 leads — the class D-305 fixed in
`seniority_gate` and never carried across); non-SWE residual in review only (apply-lane NOT_SWE was
0 of 40); `classify_location` fails open on Nottingham.

**`final_gate:` is built, keystone-guarded, identity-keyed, read by the ranker, and 0 rows on the
live store.** Request path VERIFIED live: **521 judgeable items of 537**, independence preserved,
read-only. **Ordering is forced** — `record_gate_verdict` keys on `build_identity(..., catalog, ...)`,
so any catalog change invalidates gate rows written before it. Land catalog PRs first, then arm ONCE.

## Next action

**THE THREE THINGS CARRIED OUT OF 2026-09-03, in the order they pay. Everything else Mit ruled
on is done and recorded — see the ruling table under "Owner-gated".**

1. **RE-PRICE A3 AFTER RUN 147, NOT BEFORE.** D-443's unescape runs at INGEST, so the 478 already-
   escaped bodies keep their escapes until the lane re-ingests them. The 598 → 90 figure is
   computed against a population that has not refreshed yet, so pricing the routing predicate now
   prices the wrong one.
2. **READ A7's YIELD ON THAT SAME RUN.** The 50-board hiring.cafe sample costs ~60 min/run and
   bought 10 delivered leads on run 145. Mit ruled **hold one run**, so run 147 is the read.
3. **A8's SAME-SENTENCE CASE — 581 postings, and it is STILL HIS.** His ruling covered the
   cross-sentence half (7 postings, already the shipped behaviour). The instrument needed is a
   **sentence-scoped `abstain_by`** — `_suppressed` already takes `bounds` and `abstain_by` never
   passes one — which is shared machinery and its own decision. **A document-scoped fix would
   repair the 581 and BREAK the 7 he just ruled on.**

**0. TRACK 2 IS REFUTED AND DISARMED. DO NOT RE-ARM IT, and do not propose per-company cells without naming a mechanism that actually filters by employer** — a quoted company name does not. Code stays merged and inert at `0`. **The 342 already-watched misses are STILL OPEN and the LinkedIn residual has no proposed mechanism again.** Measurement and the closed rescue: **D-437**, and this section verbatim in `STANDING-FACTS.md`.

**1. THE 2-YEAR-BAR QUESTION IS NOW ROW A4 IN "Owner-gated" BELOW — it is a decision, not an
action.** The two things a future session must not re-derive: **lowering
`near_miss_years_ceiling` REJECTS rather than releases** (D-440), and **there is no data fix
hiding behind it** — the résumé parses to 20 months, of which 13 are internships these
postings exclude by name, so the stored `1` and the résumé agree against a 2-year bar. Full
reasoning moved WHOLE into `STANDING-FACTS.md` at this close.

**2a. THE RE-KEY IS RESOLVED — RUN 146 DID IT, AND THE "HOURS" ESTIMATE IN THIS FILE WAS WRONG BY ~10x.** Both hashes moved (`rules_hash` from the catalog change, `profile_hash` because D-438's resolver adds `education_timing` to `declared_fields()`), and this file said a full re-evaluation would write ~138k rows *over hours* so it was deliberately not triggered. **Run 146 wrote them in 10 minutes**, 12:18-12:28 on 2026-09-03: **138,582 of 138,677 open postings now carry a verdict under the live identity — 99.93%.**

**The lane split was RE-READ after the re-key rather than assumed, through `review_gate.lane()` itself and not a proxy: 597 apply / 1,007 review / 107 closed — UNCHANGED. So A3's pricing below is current, not stale.** What still disagrees is the folder tree, and by very little: run 146 ran no reconcile, so disk holds run 145's filing (598 / 732 / 274 `_ineligible` / 107 / 7 `_applied`) while the store now wants 597 / 719 / 288 / 107. **That is ~14 folders out of 1,711 — the re-key barely moved the lanes**, and the next full run closes it.

**Watch out for run 146 in the runs table: `boards_attempted = 0`, every scan column NULL, `status = ok`.** It was **a peer session's `boardwatch eligibility run`**, issued to clear the re-key — not a fleet failure, though it is indistinguishable from one at a glance and it consumed a run id. Do not read it as a lost discovery day and do not compare its minutes against runs 143-145.

**2. THE CATALOG WORK IS MERGED AND THE CHECKOUT IS PULLED — what remains is the DRAIN.** D-436 and
D-438 are on `main`; the checkout is pulled and its catalog loads 7 families / 57 patterns, with 400
live bodies evaluated through the tick's own path and no crash. **The owed ledger drain releases
1,595 of 1,609 decisions — 99.1% — so: precision work FIRST, drain LAST, staged with `--job <id>`.**

**3. THE 50-BOARD SAMPLE IS READ AND THE REMAINING 282 ARE REFUSED (D-441). CLOSED** — do not re-open it from hiring.cafe's in-window counts, which is the number that was wrong. It bought **10 delivered leads** for ~60 min/run. Whether to keep paying is the OWNER's (row **A7**) and is a different question from adding 282 more, which is closed. Full numbers verbatim in `STANDING-FACTS.md`.

**4. RE-MEASURE GATE 1 AROUND 2026-09-09** (D-424) with
`.agent/2026-09-02-session/per_source_recall.py`. **The residual is LinkedIn alone**, and Track 2 is
the only lever that has moved since — which is why arming it (item 0) belongs before this, not after.

**5. SET PER-SOURCE THRESHOLDS** (owner). Framing DECIDED: option D then C — decompose LinkedIn
first (**done**, D-431), then bar on `lane-only` exposure rather than recall. The numeric level is
still the owner's.

**6. TRACK 1 — admit the 92 already-admissible LinkedIn boards** (382 postings, ~4.9 min/run, no new
code) and **ARM the `grnh.se` resolver** (D-429, ~90 boards, ~5 min/run). **Both still HELD until
run 147**: each admits boards, and landing either inside runs 145-147 makes the hiring.cafe sample's
yield unreadable. That is why "both levers" was rejected.

*(Closed since the last close: Track 2 — BUILT and DISARMED, D-433. The buried live requisition —
FIXED, D-432, and its blast radius re-measured as 1 job, not 16. The `_reported` folder drain —
SHIPPED, D-434. The `perf` flaky bound — CHARACTERISED and FIXED, D-435.)*

### Run 145 — read out, and both of the night's queue fixes are CONFIRMED IN PRODUCTION

96.4 min, exit **ok**, 94 tailored leads. Queue **598 apply / 732 review / 274 ineligible /
107 closed / 0 reported**. D-432 and D-434 both confirmed in production. Full readout moved
WHOLE into `STANDING-FACTS.md` at this close; numbers in `METRICS.md` (Run 145).

### Owed, and specifically NOT done

- **`grnh.se` redirect-following is BUILT and SHIPPED (D-429), and deliberately NOT ARMED.**
  `boardwatch companies discover-grnh` emits candidates; `companies import` is the arming act.
  **Arming must wait for run 147** or it contaminates the board sample's reading — the two board
  levers cannot be read apart inside one window. Owner's call.
- **Per-source thresholds are not set** — the owner's.
- **A DEGREE DISJUNCTION DECIDES DIFFERENTLY DEPENDING ON WHICH ARM MATCHES — PINNED, NOT FIXED (A8).** `total_years_minimum` and `range_years_minimum` carry `degree_alternative_to_years`; the six scoped/domain patterns never did. So "a Bachelor's OR N years of X" **abstains** on the total arm and **rejects** on a scoped one — same sentence, opposite outcome, decided by which pattern happens to match. A peer session's control caught it while wiring the recall fix, and the wiring is **reverted**: a test now pins the defect instead. **If that test starts passing, somebody made A8's decision without Mit.**
- **The 2-year-bar question is ROW A4, and is stated there once.** It was written out here, in
  next-action item 1, and in the table — one decision in three places. The numbers that matter
  (**2,809 `unknown` · 258 `unmet` · 43 `met`** across 475 review-lane leads; two blind judges
  swinging ~10 of 40, which is why the wrong-hold rate is a RANGE of **17%-47%**) live in D-440.
- **THE ABSTAIN REPORT CANNOT SEE AN EXTRACTION GAP, BY CONSTRUCTION — D-436, unfixed.** The
  keystone makes a rule that cannot resolve a profile FIELD visible; it says nothing about an
  extractor that cannot find the requirement in the TEXT. Reasoning moved WHOLE into
  `STANDING-FACTS.md` at this close. The honest fix is a THIRD OUTCOME per family, not more
  patterns.
- **THE D-436 PATTERN FIXES CATCH *ZERO* OF THE 13 MEASURED FALSE POSITIVES (D-436).** Moved
  WHOLE into `STANDING-FACTS.md`. The 13 have ~7 distinct root causes, so more patterns is
  whack-a-mole; **D-443 is the first of them fixed at its actual layer.**
- **The job-apps unescape is MERGED (#354, D-443) — the numbers are now history, kept in
  `STANDING-FACTS.md`.** One lane's problem: jobapps **473 of 1,620 bodies (29.2%)**, every other
  provider 0.0%. **132 bodies gained their first requirement row, 83 verdicts moved, 11 leads left
  `eligible`**, each read against the employer's own quoted span.
- **The spelled-out and parenthesised halves are REFUSED on measurement, and that reverses this
  session's own write-up (D-443).** `four (4) years` looked clean at 9 sentences on the 487-lead
  sample; over the whole store the form is **1,006 distinct sentences** dominated by `no convictions
  for DUI … within the last five (5) years`, `Four (4) year undergraduate degree` and `Two (2) year
  Associate degree`. Spelled-out numerals are worse: `every two years thereafter`, `at least every
  five years` (EEO boilerplate), and **`Up to three years of professional software development
  experience` — a CEILING a minimum-bar pattern would invert.** **A class read as safe on a filtered
  sample was not safe on the population.**
- **Unescaping is NECESSARY, NOT SUFFICIENT, and a test pins the residual.** `3+ years of
  non-internship professional software development experience` — the most common escaped form on
  that lane — writes zero rows *even unescaped*, because no catalog arm allows four modifiers
  between `of` and `experience`. That, not more escape handling, is the next coverage increment.
- **THE `gh_jid` CONVERGENCE ITEM IS REFUTED AS AN IDENTITY QUESTION, AND THE REAL MECHANISM IS BIGGER THAN IT WAS (D-445).** It proposed an `IDENTITY_ALGORITHM_VERSION` bump — re-keying **161,085 postings to reach 4 leads**. Measured store-wide first: **all 4 cases are one employer under TWO `companies` rows** (Peloton, Roblox, Stripe, Lyft), so identity is not failing — the employer exists twice. **303 employers have postings under more than one row**, and it costs the shipped slate cap **20 redundant standing leads it cannot see** (89 on the `company_id` key, 109 on a company-NAME key; all 20 read by hand, zero false merges). **Company-row consolidation is the lever, is a DATA change needing no re-key or drain, and is NOT TAKEN** — it re-parents postings on the live store and the merge RULE needs its own measurement. **The first measurement returned a confident, wrong ZERO** because the key included `company_id` and a Greenhouse job id is unique across GREENHOUSE.
- **`classify_location` FAILS OPEN on unrecognised cities**, so Nottingham (UK) postings reached a
  US-only queue in the D-436 audit. Not fixed; the fail-open direction is deliberate (D-294) and
  narrowing it is a precision/recall decision, not a bug fix.
- **THE LIVE STORE HAS 0 REPORTED AND 0 SKIPPED JOBS**, so run 145 cannot exercise the new
  `_reported` drain (D-434) in either direction. **A clean live reconcile is NOT evidence it
  works** — the unit tests are the only thing that can catch it. Measured by a peer session.
- **No alert wiring for the seed leak.** `boardwatch seeds` is a command you must run. The
  finalize-block alert-ordering invariant makes wiring it a separate change with its own review.

## Owner-gated — do NOT start or decide unilaterally

**0-1. RETIRED / ANSWERED — moved WHOLE into `STANDING-FACTS.md` at this close.** Gate 1 is
PER-SOURCE RECALL (D-421) and only the per-source THRESHOLD is still owed; job-apps keeps running
until it is met (`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410). **Do not re-litigate
80%, do not re-derive "most", do not re-probe Indeed.**

**A. THE NINE DECISIONS — FOUR DONE, FOUR RULED, ONE OPEN. 2026-09-03; read the provenance line.**

> **FOUR OF THE NINE ARE DONE AND VERIFIED FROM THE REPO AND THE STORE, not from a merge
> message.** `main` carries **#354 (A1)**, **#357 (A9)** and **#344 (A5)**; the live store holds
> **87 `queue.skipped.*` rows and 0 ledger `skipped` dispositions**, which is **A6** executed
> through the reversible mechanism D-446 recommended. Reversal list:
> `a6-skipped-duplicates-20260903-114210.json` in the config dir.
>
> **The slate cap is confirmed live through the shipped code, not a proxy**: reading
> `standing_slate_keys` against the store gives **1,514 keys held, 3 still carrying more than one
> lead, 3 redundant leads** — down from 53 groups / 89 leads before A6. The 87 skips are correctly
> EXCLUDED from the seed, which is the property that makes every deferral end.
>
> **The RULINGS below (A2, A3, A4, A7, A8) were RELAYED through a peer session**, not read from
> Mit directly by the session that wrote this line. Recorded so the work is not re-litigated, and
> marked so a wrong relay is correctable rather than canon. **Confirm before acting on one that
> deletes or rejects.**

| # | ruling | status |
|---|---|---|
| **A1** | merge | **DONE** — `main` `113b91af` |
| **A2** | **yes — and the SPOT-CHECK IS DONE AND PASSED (15/15 correct against the employer's own words). The APPLY HALF IS IMPOSSIBLE.** | `gate apply` REFUSES `verdicts_a/b.json`: they carry `label`/`reason`/`evidence`, and `OracleVerdict` also requires `decision` and `confidence`. **They are audit notes, not gate verdicts** — nothing can be applied without fabricating a confidence the judges never gave. Applying anything needs a real `gate request` → judge → `gate apply` cycle. VERIFIED by reading both files and the dataclass |
| **A3** | **delegated — re-priced 598 → 90, and NOT YET IMPLEMENTABLE** | the unescape runs in `lanes/jobapps._body` **at INGEST**, while `preflight` reads `posting_versions.body_text` straight from the store — so **all 478 already-escaped bodies stay escaped until the lane re-ingests them**, and `eligibility run` cannot realise D-443. Price the predicate after those bodies refresh, not before. VERIFIED by reading both call sites |
| **A4** | **REFUSED after measurement** | his answer was a FACT, not an instruction — exactly the distinction D-440 exists to record. Measured cost against the CURRENT store is **1,458 postings rejected**, not D-440's 505. `near_miss_years_ceiling` STAYS at 3 |
| **A5** | merge | **DONE** — #344, `main` `6770608c`; gate 0 (9,336 passed), CI 24/24 |
| **A6** | executed | **DONE** — 87 skipped, reversible |
| **A7** | **hold one run** | re-read after the next full run before deciding |
| **A8** | **HALF CLOSED, HALF NEVER ASKED — do not read this row as settled** | **Cross-sentence** ("does a disjunction waive a SEPARATE `8+ years of C++`?") is his ruling, is **7 of 588 postings**, and is **already the shipped behaviour** — nothing to do. **Same-sentence** (`Bachelor's degree or 5+ years of software engineering experience` — does it waive ITSELF on the scoped arm?) is **581 postings and was NEVER PUT TO HIM.** The A8 row conflated the two |
| **A9** | merge | **DONE** — #357, `main` `268f904d` |

**A8's same-sentence half is the live question, and the asymmetry is ONE WORD.**
`…or 5+ years of experience` resolves `uncertain`; `…or 5+ years of **software engineering** experience` resolves `ineligible` — because only the total arm carries
`degree_alternative_to_years`. Mit holds a Master's and clears the degree arm in both. **D-073 already ruled this shape undecidable for the total arm and cites a real job deleted by getting it
wrong.** The D-447-era wiring is the WRONG instrument: being document-scoped it would fix the 581 and break the 7 he just ruled on. The right one is a **sentence-scoped escape** (`_suppressed` already takes `bounds`; `abstain_by` never passes one) — shared machinery, and its own decision.
Written up as **D-449**, on `main`.

**A4's answer is a FACT, not a policy move, and that distinction is the whole of D-440.**
"I don't have 2 years of work ex" answers the profile question; it does NOT by itself say
to lower `near_miss_years_ceiling`, because lowering it makes the engine REJECT those
postings rather than release them. Re-read D-440 before changing the value.

**The priced table below holds only the decisions still OPEN or delegated.** A1, A5, A6 and A9 are done and their pricing is in D-443, D-439/D-444, D-446 and D-447 — repeating it here would be a second copy that can drift.

| # | decision | what it costs / buys | where the numbers are |
|---|---|---|---|
| **A2** | **Spot-check the 15 judged rejections, then decide whether to run a FULL gate cycle** | `verdicts_a.json` (8) + `verdicts_b.json` (7) hold **15 rejections** from the 77-lead measurement, each quoting the employer; **15 of 15 spans survive the keystone guard, 0 failures**. Applying them demotes **15 postings, NOT ~116** — the ~116 is what a full `gate request` → judge → `gate apply` over all 597 would project at the measured 19.5%, and nobody has run that cycle. **MUST run AFTER A1 and D-447 land** (see below) | the two files, in the config dir |
| **A3** | **D-442's routing predicate** — zero requirement rows ⇒ `_review` | apply **597 → 116**, review 1,007 → 1,488. An **81% cut** to the pile you work from. **Not a bug fix** — it is what you want the apply lane to MEAN | D-442 |
| **A4** | **Does a stated 2-YEAR bar rule you out?** | `near_miss_years_ceiling`; **lowering it REJECTS rather than releases** (ceiling 2 rejects 290, 0-1 rejects 505). Recommendation: do NOT lower | D-440 |
| **A7** | **Keep paying for the 50-board hiring.cafe sample, or revert it** | ~**60 min/run forever** for **10 delivered leads** on run 145. Reverting is a `companies` restore from `companies-prehcsample-20260902-183019.csv`. **Adding the other 282 is CLOSED and is not this question** | D-441 |
| **A8** | **Does a degree disjunction reach a SCOPED bar?** — wire `degree_alternative_to_years` to the six scoped/domain minimum patterns | **365 SWE+US postings move `ineligible` → `uncertain`**, out of a reject pile that is never inspected and into review. Cost: `abstain_by` is **DOCUMENT-scoped**, so a JD saying "Bachelor's or 4 years" for its general bar would also waive a separate "8+ years of C++". Today the same sentence **abstains on the total arm and rejects on a scoped one**. **A claim about what a disjunction MEANS, not a consistency repair** | D-447; `test_experience_range_recall.py`, the defect pin |

**A1 and A3 interact and A1 comes first**: the unescape moves 132 leads out of the zero-rows
population A3 prices, so deciding A3 before A1 lands prices a population that is about to shrink.

**A2's ordering note still applies to the FULL cycle, not to the files.** The files cannot be applied at all (see the row); this is about whatever you judge next. **It is ORDER-FORCED and fails SILENTLY if you get it wrong.** `record_gate_verdict` builds its identity from the catalog and stores the `rules_hash`, so **any catalog change invalidates gate rows written before it** — verdicts applied ahead of #354 and D-447 are written under an identity the ranker no longer reads. No error, no warning, just no effect. Land the catalog PRs first, then judge, then apply.

**A8 is independent of A1 and A3** — it moves postings that are already `ineligible`, which neither the unescape nor the routing predicate touches. **A1 and A5 must be read out on ONE run, not two.** **A9 is STACKED on A1**: its base branch is #354's, so #354 merges first or #357 cannot. **A9 also moves the catalog**, so it is one of the two changes A2 must wait behind. #344 shrinks the delivered population and #354 changes the verdicts on it, so whichever lands second is measured against a population the first moved. **A6 is independent of both** — it touches only leads already on disk.

2. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
3. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
4. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
   one bundle.

## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12).
2. **The Snap `Level 3`/`Level 5` leak stays open by design** — with no bindings file every level
   token abstains. boardwatch ships no verifiable claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The class is
   **15 boards and 43,371 postings that can never be listed at all** (run 127) against an ~84,821
   open corpus. **Sized, not solved, and no budget can solve it.** See D-336.
4. **Whether `ServiceNow Developer` should rank at all against a new-grad SWE target.** Role
   TAXONOMY, not dedup. D-345 bounds the delivery damage; it does not answer this.

*(Resolved and no longer open: five items — the delivery slate cap (D-345), the funnel-write
swallow (D-288), clearance as a blocker (D-257), the seniority band (D-258). Moved WHOLE into
`STANDING-FACTS.md` at this close.)*

## Phase status

**P0–P6 are all COMPLETE and their gates all MET, and none has moved in weeks — the full table
moved WHOLE into `STANDING-FACTS.md` on 2026-09-01e when this file passed 250 lines again.** Read it
there. Only these are not settled:

- **P2 item 8** (field-taxonomy gatherer) **NOT STARTED** — the last multi-tenancy gap, owner-gated.
- **P7 Breadth**: LinkedIn, GitHub-lists, jobapps, **`jsonld` and `indeed` are all built and
  ARMED** (D-420; `indeed`'s cap raised to 50 on 2026-09-02). **hiring.cafe is armed and WORKING** —
  runs 143 and 144 both succeeded; its 17% RECALL is a board-fleet gap, not a lane defect (D-425),
  and its one post-fix failure is run 142 alone (blocker table). Remaining tier-D lanes not started
  (D-413 ranks them).
- **14-day acceptance: not started, HELD BY THE OWNER.** The provisional pass is **not being
  chased** (D-351 item 2: work comes first), and every `rules_hash` bump restarts its counter.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
