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
> Mit's ruling, **again on 2026-08-26** (30 settled blocks, 511 → ~260 lines), and **again on
> 2026-09-03d** (95 lines: the whole nine-decision apparatus, run 145's readout, and five closed
> blocks). Nothing was deleted on any of the three passes. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### Session 2026-09-07 (mid; ALL FIVE RULED CALLS EXECUTED — 16,183 postings closed, zero censored boards, four executors merged): **D-494.**

**The PDF drop 21 -> 5 is BENIGN and the question is closed.** The PDF stage converted 100% on both
runs (`21 in, 21 out`; `5 in, 5 out`; `no_pdf: 0`). The whole delta is the apply/review lane split
(`routed_to_review_lane` 19 -> 35): `review_gate.classify` promotes a deterministic `eligible` lead
unconditionally, run 10's slate carried **21** and run 11's carried **zero**. Cause: `new_count` was
779 on run 9, **30,706 on run 10**, 4,852 on run 11, and all 21 of run 10's `eligible` leads were
first seen on 09-07 — run 10 discovered them itself. It was the first-fill of the ~30 boards added
09-06 plus `amazon` and Jane Street. **~5 PDFs a run is the STEADY STATE; the apply lane is bounded
by the arrival rate of new `eligible`+`swe`+in-band postings, not by a backlog.**

**Fleet: 16,183 postings CLOSED and censored boards 10 -> 0.** Workday facet slicing is applied
live to 13 slices across nine boards; open postings ~150,000 -> **137,810**; ~2,650 postings the
blind 2,000-walks had never seen. Per-board closes: Northrop 2,938 · Walmart 2,266 · Target 2,051 ·
T-Mobile 1,988 · PNC 1,897 · Citi 1,529 · Leidos 1,220 · BAH 1,008 · NVIDIA 743. **The ruling's
premise did not survive measurement:** `jobFamilyGroup=Technology` is the right descriptor for only
**3 of the 10** boards — T-Mobile uses a different PARAMETER (`Job_Family_Group`) and Abbott offers
no technology group at all, so Abbott is deliberately not sliced. **Northrop's workday row lost the
comparison** (3,000 of 3,791 on a page cap; its Engineering group is 2,182, above the 2,000 clamp,
so slicing does not fix it) and was DRAINED to 91 then unwatched — 2,938 closed through the absence
rule first, leaving 91 unclosable instead of 3,010. Eightfold keeps 3,424. **Fleet 341 watched.**

**Merged and pushed, six commits, final gate 10,090 passed:** `0e1690ac` **T72** (each judged lead's
shortlist rank recorded with its gate verdict, captured off the ranker's order BEFORE liveness;
`engine_version` unmoved, **no ledger drain owed**) · `aaa4aefc` **T70 `apple`** · `ad215b45` **T73**
(the ranking cap, 2 per company+title+location) · `f3466988` **T74** (the eightfold 405 retry +
employer naming) · `92781ce7` **T75** (`companies facets`) · `60e3efa2` the integration fix.

**T74 proved the planning session's own ticket WRONG, and it changes what item 4 delivers.**
`exact_quad` keys on **`company_id`**, not `normalize_company` — two boards are two `companies` rows,
so **no naming change can ever make it fire across them**. `cross_host` is the one keyed on the name
and it does not suppress, by design (§3.1). **So the cross-board duplicate is now GROUPED, not
SUPPRESSED: the 14-18% queue duplicate rate will NOT fall from this.** Acceptable because the
largest pair (Northrop) was dropped this session and the Qualcomm pair, the one the coverage fix
exposes, does group.

**Two defects found here that four green branch gates did not catch.** (a) T74's backfill selected
`name == slug` case-insensitively, which admits registry rows whose curated name is the slug
re-capitalised; it planned **129 rewrites, downcasing 100 names** (`OpenAI`, `SpaceX`, `AbbVie`) that
reach the résumé filename. Fixed casefolded: **31 rows**. (b) The MERGED-tree gate caught that
`apple` had no declared employer-name shape (T74 predates T70), so it would have named the company
after a COUNTRY. Backfill applied here: 31 rows renamed, `identities backfill` wrote 24,466.

**Next action.** (1) **Read run 12, the 06:00 tick on 09-08** — the first run carrying the shortlist
rank, the ranking cap, the sliced fleet and the eightfold retry. Then the rank-band measurement that
D-493 could not do becomes possible: read conversion by rank band out of
`raw_output_json.$.shortlist_rank` and answer whether `gate.depth = 150` is right. Expect a much
smaller corpus (137,810 open, not 150,000) and watch `hidden_cluster_cap` and the new
`throttle_retries` / `throttle_exhausted` lines. (2) **Thales may never close**: it serves 2-3 rows
with no `externalPath` on every scan, forcing `partial`, so its ~1,800 non-SOFTWARE postings are
stuck open — pre-existing provider behaviour that slicing exposed. (3) **The nightly WINDOWS CI has
failed every day since at least 08-31** on the fake-claude-on-PATH class; `push` CI is green on the
same shas. T61 fixed nine; this class remains and is worth a ticket. (4) Open questions the
executors raised and nobody has ruled on: whether to seed the cluster cap from the standing queue
(D-439's pattern) so a five-member group does not eventually deliver every member; whether 2 is the
right cap once `hidden_cluster_cap` has been observed live; and whether the guide needs a
"network, read-only" effect marker (T75 registered `("network",)` rather than invent one).

**Process note.** Three executors + a full gate + a scan pass at once drove load to 65 and memory
pressure killed six background waiters. Nothing was lost, but a gate under memory pressure can be
OOM-killed into a false red. **Gate BETWEEN executors, not across them.** Also: scans are serialized
by a global `scan.lock`, so a multi-board slicing pass is wall-clock bound and cannot be parallelized.

### Session 2026-09-07 (early; run 10 READ, the depth bet MEASURED, `amazon` and Workday FACET SLICING landed): **D-493.** Run 10 was launched BY HAND at 00:09 CDT on Mit's ruling (the handoff's "read run 10" was not actionable — `runs = 5`, no artifact dir; the tick had not fired). It ran **2h 40m** and came back **`ok`**: the first `gate.depth = 150` run reads `150 checked, 5 gone` → **145 judged (76 eligible, 22 ineligible, 47 uncertain), 0 batches failed open, 83 beyond the delivered slate**, funnel **`reconciles: True`**, `boards_failed` 0, `detail_deferred` 0 everywhere. **T63 has no first-live defect.** A manual run does NOT count toward the confirm streak, so the 06:00 tick still fires as run 11 and is the countable one. **T69 `amazon`** (merged `81fc956a`, CI green) — 22,282 postings over 38 categories, bodies INLINE so a 2,597-posting category costs 26 requests. **T71 Workday facet slicing** (merged `c3a5bc1e`) — `…/site#jobFamilyGroup=Technology`; live, sliced Citi enumerates **1,073 of 1,073 uncensored** against the unsliced board's `total: 2000` censor and 1,988 blind rows of a true 4,411. **Fleet 337** (+`amazon:software-development`, +`greenhouse:janestreet`, +3 lane-discovered). The recurring CI wall-clock flake (4.58 s on 09-06, 4.63 s on 09-07, both vs the same 4.5 s bar) is FIXED by rendezvous, not re-run (`1afd7d0f`).

**The depth bet is measured and it is NOT D-491's number.** Judge rows joined to the deterministic verdict on `input_id`: tier 1 (`uncertain`) **122 judged → 69 eligible = 56.6%**; tier 0 (`eligible`) **23 judged → 7 = 30.4%**. D-491's 85% was measured on the SHALLOW slate. The decision stands (69 judge-eligible leads no shallower run would have seen) but **the right value of `gate.depth` needs conversion BY RANK BAND, which needs each judged lead's rank — **not measured, and NOT computable retroactively: `score` is NULL on all 145 judge rows and no table persists a rank, so this needs a small instrumentation change (persist the shortlist rank with the gate verdict) before it can be answered.**

**Coverage — quote the run's own numbers.** `morning-10.md`: **discovery reach 90.4%** (109,065 of 120,606 stated, across 224 of 335 boards), and **10 censored boards short 35,645 postings** reported SEPARATELY with no ratio. A "67.7%" figure computed mid-session folded censored totals into one ratio and is WITHDRAWN. boardwatch already recovers true totals via facets; T71 extends that from totals to ENUMERATION.

**Run 11 (06:00 tick) READ — `ok`, 43 min, `reconciles`, `boards_failed` 0, `runs = 6`.** Both new boards work live: `amazon:software-development` **complete 2,598 of 2,598** and `greenhouse:janestreet` complete 231 of 231. **The depth cost AMORTIZES: 145 judged on run 10, only 62 on run 11** (a judged-undelivered lead keeps its verdict and is not re-judged) — so `gate.depth = 150` is cheaper after the first run than run 10 implied; read that beside the 56.6% conversion. Discovery reach **91.1%**. The slate is strong (LinkedIn, OpenAI, Apple, TikTok x3, Figma, Ramp, Audible) and run 10's 12-lead Goldman concentration is gone. Unexplained and NOT investigated: pdf 21 -> 5.

**Next action: SUPERSEDED — all five rulings were executed on 2026-09-07 (mid); see D-494 and the block above.** One claim in the removed text was WRONG and is corrected there: `exact_quad` keys on `company_id`, not `normalize_company`, and the hostname-named board count was 35 of 338, not 28 of 337.

### Session 2026-09-06 (late; phenom and eightfold LANDED): **D-492.** T66 `phenom` and T67 `eightfold` resumed ONE AT A TIME on the enterprise seat after Mit's go-ahead ($17.50 together), each reviewed, mutation-checked, live-verified in a scratch store and gated green; merged `0165a43e` / `67989c30`, integration `f17f11bc`, pushed. T67 found and fixed an id-less-row minting bug; its own "largest board is 1,958" correction was WRONG — Northrop Grumman is 3,817 live and the 300-page backstop cut it at 3,000, so the backstop is now 600 (rescan 3,817 = 3,817). **Fleet 332 watched** (+3 phenom: BAE Systems, P&G, Battelle; +4 eightfold: Qualcomm, Northrop, Applied Materials, Boston Scientific). Not started: SuccessFactors (no public JSON found), the bespoke majors (Amazon, Apple, Meta, Google, Jane Street). No `rules_hash`/`engine_version` change. (Run 10 was read in the session above.)

**Next action.** Read run 10 (06:00 CDT 09-07): the first depth run — expect `gate: ~150 judged … ~110 beyond the delivered slate`, gate stage ~15 min, `RECONCILES`; the first scans of 30 new boards (`boards_failed` 0; Oracle/Phenom/Eightfold boards `partial` on the 50-detail budget is by design; Northrop alone is ~10 min of paced requests). If judged ≠ ~150 or the funnel does not reconcile, read `.agent/2026-09-06-exec/RESULT-t63.md` §"reconciliation definition" first. Then the bespoke majors, one ticket each, after asking Mit the seat's usage. Mit ruled 23:53: runs may be as long as full coverage needs — `detail_fetch_budget` ceiling raised to 10,000 (`04e000bb`) and the live value set to 5,000, Northrop kept. Owner calls still pending: whether `config set` should reach gate keys (it does not); the phenom teaser-body rows have no drain.

### Session 2026-09-06 (evening; the Pinloop replacement begun on the enterprise seat): **D-490 + D-491.** Six branches merged and pushed, CI green: **t62** (generated `boardwatch guide` + `skill`, `--json` on eight read commands, 22 wrong claims corrected after a $6 review), **T63 `gate.depth`** (judge deeper than the run delivers; **LIVE at `gate.depth = 150`** in config.toml), **T64 `jibe`** and **T65 `oraclehcm`** providers (live-verified in scratch stores), **T68** (the Indeed control test was hitting the live API). Fleet 325 at that close (+18 Workday tenants, +AMD/JHU APL on jibe, +Oracle/AmEx/Goldman-campus on oraclehcm). Item 3 was REVERSED by measurement: tier-1 leads the judge sees convert 85%, so depth, not a pre-screen. The seat's window died under five parallel executors (~$103); the standing rule is one executor at a time after asking Mit the usage reading.

### Session 2026-09-06c (run 9 READ; B6 found NOT reconciling on runs 7–9 → T60; nightly Windows CI → T61; the B8 lever measured): **run 9 is a clean tick on the restored config** — `runs = 5`, exit 0, every hash identical to runs 6–8, LinkedIn admitted 50, Indeed 57, `jsonld` present (0 attempted is lane ordering, D-422), 37 judged / 31 eligible / 1 ineligible, 36 delivered = **7 apply (all PDF) + 29 review**. **But its funnel reads `DOES NOT RECONCILE`, and so do runs 7 and 8** — the 09-05 (later) session recorded the provisional pass from the run status without reading that line. Cause is REPORTING: `build_run_funnel` never learned T43's review lane or T54's judge rejection; the unnamed remainder is exactly `judge-rejected + review leads` on every run. **T60** (reports only; `rules_hash`/`engine_version` untouched, so the confirm is NOT restarted) adds `gate_rejected` and `routed_to_review_lane` to the projection stage and merges the review leads into the tailor stage's `entered`; `ARTIFACT_VERSION` 8. **T61** fixes the nightly Windows jobs, red every day since ≥ 09-01 on nine tests. Both built by headless Opus executors on the enterprise seat, reviewed and gated here: t60 gate green (9,604 passed); merged tree green (9,604); t61 gate green (9,595 passed); Windows verification run 34061956555: Windows 3.11 and 3.12, macOS and every Linux shard GREEN; 3.13 red on one unrelated wall-clock overlap test (4.58 s vs 4.5 s margin); attempt 2 re-ran that job GREEN, so the whole run is green and the overlap test is a flake. Both merged to `main` (`b240698d`, `67cba250`) and pushed after a green gate on the merged tree. Decision **D-489**; numbers in `METRICS.md`, `Session — 2026-09-06c`.

**The B8 lever, measured read-only:** `delivery/review_gate.classify` never reads the judge. 24 of run 9's 29 review holds carry a judge `eligible`; 46 of the 123 in the lane do. Tier 0 (`eligible`+`swe`) is DRAINED (171, 4 undelivered), so the `--top 40` cap bites on tier 1 only. Promoting on a judge `eligible` is **owner-gated (0-B below)** — it makes the judge an evidence source for `ELIGIBLE` with no span. **Owner ruling owed: whether runs 7 and 8 count toward the pass** (recommendation: they stand — the instrument was wrong, the pipeline was not). The `taxonomy changed — re-extracting N` line on every run is `preflight.py:53`'s wording for new postings, not drift.

### Session 2026-09-06 (planning → the reset's SECOND config loss found and RESTORED; the apply lane blind-audited for B8): **the recovered config had also dropped `jsonld` + `indeed`, the seven LinkedIn hubs (33 combos/run), the caps `linkedin = 50` / `indeed = 50` and `pace_from_request_start`** — D-486 caught only the jobapps half, and runs 6–8 ran LinkedIn at the 10-company default. The last pre-reset `config.toml` was recovered VERBATIM from the transcript archive (2026-09-03T23:55Z) and restored 00:15 CDT on Mit's call ("before it"), read back through the loader; discovery only, the count holds. **Run 9 (06:00 CDT tick) is the first run on the restored five-lane config AND day 1 of the 14-day confirm.** Decision **D-487**; numbers in `METRICS.md`, `Session — 2026-09-06 · the pre-reset config…`.

**B8 measured for the first time (n = 128, the whole apply lane, two blind Sonnet passes, 40/40 inter-rater on the unapplyable axis): 22 of 128 UNAPPLYABLE = 17.2% against the ≤ 16% bar; 14.7% on the 95 gate-judged leads (runs 5–8), 24.2% on the 33 delivered before the judge existed; `jobapps:` targets 2.1% vs board fleet 26.2%.** Causes: six-family `ineligible` 10 (work_auth 4 — PayPal's "Visa Sponsorship … is not available … now or any time in the future" ×3; experience 5 — two U.S. Bank bars in WORDS, "Two to three years"), seniority 6 (Inferact "Member of Technical Staff" ×4), role 5 (Giant Eagle "Front End Lead" ×3), location 1. Report and key: `.agent/2026-09-06-audit/`. **The tier-0 headline is that same board: 46 of the 49 undelivered `eligible`+`swe` are Giant Eagle "Front End Lead Trainee" (`role_verdict` matches "Front End Lead"); tier 0 is drained and the slate already draws from tier 1 (1,644; 1,323 zero-row).** 46 of the 48 `jobapps:` apply leads were already promoted by job-apps itself — parity, not new reach.

### Owed, and specifically NOT done

- **T51 SHIPPED (D-484) before the freeze.** Its residual: a hedged bar carrying a domain noun has no
  `*_preferred` sibling to land in and writes no row; a recall change for M3's window.
- **D-436's per-family topic net is SIZED and NOT BUILT.** Sizing is in D-461: the all-family form
  takes `eligible` to **0**, and the `work_auth` form is worth **245 of 4,617 (5.3%)** — about a
  quarter of the measured defect. **Do not re-derive it, and do not quote the naive 29.9%**, which is
  EEO boilerplate contamination.
- **The hiring.cafe +6.19pp / 1,331-posting ceiling is RETIRED as a fossil (D-463).** Its null
  control rests on an endpoint PR #304 deleted on 2026-09-01, two days before D-451 was written.
  Real value ~**+0.6pp**. **Do not re-size other work off the 1,331.** The lane's dominant problem is
  **availability** — 2 total refusals and 2 near-total in the last 7 armed runs.
- **The refused-aggregator filter is REFUSED (D-463)**, not deferred. Its premise inverts on the
  actual variable. Do not re-raise it from the 24.7%/13.4% figures, which are the wrong comparison.

## Owner-gated — do NOT start or decide unilaterally

**0-B. JUDGE → LANE PROMOTION (D-489).** The review gate routes on the engine verdict alone; 46 of
the 123 review holds carry a judge `eligible` (16 `experience_requirement`, 21 `no_requirements_found`,
9 `role_unconfirmed`). Run 9 would have delivered ~31 apply-lane leads instead of 7. Promoting on a
judge `eligible` makes the judge an evidence source for `ELIGIBLE` with no quoted span (keystone,
D-458). Recommended: promote the two requirement holds only, never the role holds, blind-audit the
promoted cohort first. **Not built. Mit's call.**

**0-A. THE LANE STAGE'S THIRD-PARTY PACING IS WEAKENED ON THREE SCAN HOSTS, AND IT IS LIVE
NOW.** Found by the 09-06 review, re-sized by D-474 choice 1 from run 3's funnel, **not
introduced by anything shipped since SP2** (already on `main`, run in production twice).
`Fetcher._host_locks` and `_last_request_at` are PER INSTANCE and the lane stage's own instance
overlaps the scan, so a host both reach can see 2 in flight and 2 req/s. **The only such
traffic is hiringcafe's one GET per admitted board** — 94 in run 3: 40 to
`boards-api.greenhouse.io` (the scan spends 90.0 s there), 44 to `api.ashbyhq.com` (10.1 s),
10 to `api.lever.co` (12.0 s) — so the exposure is ≤ ~90 s on one host per run, not the lane
stage's 352 s. `grnh_seeds` is a CLI command and `jsonld`'s hosts are not scan hosts. **The
fix is T41** (shared pacing STATE, not a shared client — the client's default UA is what
linkedin and github_lists rely on). **Mit's call, and it is a pacing promise to third parties,
not a performance knob.**

**0. THE ≤ 1-YoE FLOOR — RULED (D-478 §5), PLANNED (D-479), ALL DECISIONS TAKEN (D-480).** D1 = T47
(per-user policy data). D2 = floor first, then arm the judge, both before run 4. D3 = above-band
stays hidden, no ticket. Reach confirmed for 2–3 y total bars, scoped bars > 1 y and 13–36-month
bars; hedged/preferred bars do not move. Nothing here is still owner-gated; it is execution.

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **PER-SOURCE THRESHOLDS — STRUCTURE RULED (D-482):** employer-board sources ≥ 85% independent
   recall; LinkedIn no bar. **Owed: the Indeed and hiring.cafe numbers at the first post-reset
   reading (~2026-09-17)**, with D-450 on the page again. The instrument
   (`.agent/2026-09-02-session/per_source_recall.py`) still points at the OLD account home for
   job-apps' ledger — a one-line fix before it runs.
2. **TRACK 1 — CLOSED (D-482): accept the loss**, per D-453. Do not re-raise it from the 382 or
   the 113.
3. **Mit's résumé calls** — whether to send a document at all; the D-220 prose rewrite of the submitted "sole iOS developer" answer (outside the bundle); the per-lens formatting session.
4. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28.** The last
   multi-tenancy gap of its kind; D-054 forbids us authoring non-tech field content.
5. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
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
5. **ANSWERED 2026-09-05 — T31 (`1fc61596`, on `close-2026-09-05`): `boardwatch init` seeds the
   bundled `resume_template.tex` when absent and never overwrites; the placeholder-phrase catalog
   still refuses the unedited copy, so the fail-closed guarantee is unchanged.**

## Phase status

**P0–P6 are all COMPLETE and their gates all MET, and none has moved in weeks — the full table
moved WHOLE into `STANDING-FACTS.md` on 2026-09-01e.** Read it there. Only these are not settled:

- **P2 item 8** (field-taxonomy gatherer) **NOT STARTED** — the last multi-tenancy gap, owner-gated.
- **P7 Breadth**: LinkedIn, GitHub-lists, jobapps, **`jsonld` and `indeed` are all built and ARMED**
  (D-420). Indeed's cap is **50 again** after one uncapped measurement run (D-459). **hiring.cafe is
  armed and WORKING**, and its 50-board sample is **reverted** (D-456) — watched boards 482 → 432,
  then 490 after run 149's Indeed convergences. Remaining tier-D lanes are **DECIDED AGAINST**, not
  deferred (D-451).
- **Provisional pass: recorded MET on runs 6, 7, 8 (D-483) — but runs 7 and 8's own funnels read `DOES NOT RECONCILE` (B6) through the reporting gap T60 closes (D-489); whether they stand is Mit's ruling.** 14-day confirm: day 1 = run 9 (2026-09-06 06:00 CDT, clean tick, same gap), passive. **B8 first reading (D-487): 17.2% on n = 128, 14.7% gate-judged; bar ≤ 16%.**
  Not chased (D-351 item 2: work comes first), and every `rules_hash` bump restarts the count.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fires **06:00 CDT until a reboot** — launchd keeps its boot zone, and the zone was set five minutes after the 09-03 boot — so a reboot moves it to 04:00. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
