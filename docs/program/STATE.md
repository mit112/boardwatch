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
> Mit's ruling; nothing was deleted. Do not narrate a decision here that `DECISIONS.md` already holds —
> cite its number instead.

---

## Current standing

**HOW TO REPORT YIELD — the owner's standing rule (D-312).** Every yield, coverage or job-apps comparison
quotes **the end of the line: affirmatively `eligible` jobs** — currently **~60/day** (eligible + software +
in-band + US + non-duplicate + unhandled). **Never** quote a broader upstream population as the headline:
"new postings/day" and "software-titled/day" are different quantities, and doing so overstated yield ~8× in
this session before Mit caught it (the hard US filter alone removes 57% of the corpus). **`uncertain` is
never folded into `eligible`** — the keystone invariant, not a preference; the ~82/day abstains get their own
line. Measure with `stats` / `top --no-record --json` / the run funnel, never ad-hoc SQL over `postings`.

**GATE P4 IS MET — the owner blind craft review PASSED cleanly (2026-08-26).** Mit reviewed 13 anonymised
résumés (8 boardwatch + 5 job-apps decoys) rendered-page-only. All five he judged WORSE were job-apps decoys;
all three he judged BETTER were boardwatch (Perplexity/Anthropic/Figma); the other 5 boardwatch were on-par.
Both orphan-page-2 defects were decoys — the failure mode D-303's fill fix eliminated. **P4 objective half
(0 anti-slop violations) + subjective half both pass → P4 gate MET.** Assembler/key in
`.agent/2026-08-25-craft-findings/` (build_p4_blind_sample.py, p4_blind_key.md).

**TWO SCAN-ROBUSTNESS FIXES SHIPPED + LIVE (D-306 #167, D-307 #168, 2026-08-26).** (1) `apply.py` now collapses
a duplicate `provider_posting_id` within one board snapshot — a Workable board (`alexander-dennis`) that lists
one shortcode twice was crashing the whole run on `UNIQUE(company_id, provider_posting_id)`. (2) `_scan_body`
now isolates a board's `apply_board` failure per-board (count failed, continue) instead of aborting the run.
Both TDD, both merged and pulled to the primary tree (HEAD `c949e18`). Neither is an eligibility module →
`engine_version` unchanged, no drain, freeze-safe. Found by firing runs, not by review.

**THE LANE ROLE FACET IS BUILT — the lanes now ask for the USER'S target roles (D-309).** Both aggregator
lanes searched FACET-LESS, which returns the general labour market rather than the user's. Measured on the
live store 2026-08-26 over 282 open lane-provider postings: **3 `swe` (1.1%), 82 `uncertain`, 197 `not_swe`**
— and the three real ones (Siemens ×2 semiconductor digital-twin SWE, Zensar data engineering) are
US-eligible but rank BELOW the N=10 cap. **The gates were not rejecting software work; there was almost none
to reject** — lane discovery turned up zaxbys, dominos, twinkletoesnanny, best-choice-roofing. The delivered
non-SWE résumés (Business Unit Leader, Front Office Agent, Instructional Aide — runs 106/112) came through
the `uncertain` role fail-open, not a gate failing to fire. Fixed UPSTREAM: `lanes/facets.py` derives search
facets from `profile.target_titles_json` (never a query written into a lane — that is the multi-tenancy
requirement and why both contracts deferred it), and each lane issues one search per facet, interleaved so
the body budget reaches every facet. hiring.cafe uses the robots-**PERMITTED** path route `/jobs/{role}` —
its own `?searchState=` query search is `Disallow`ed, so the obvious build would have broken a compliant
lane. LinkedIn uses `keywords=` (owner-probed: baseline 0/10 SWE → keyworded **10/10**; `start` pages but
buys nothing against the body budget; `location=` is silently ignored so it is never sent). Live end-to-end
through the real lane on the live profile: **16 `swe` + 2 technical `uncertain`, 0 `not_swe`**, 13 of 14
facets contributing, 0 duplicate `provider_posting_id`. `engine_version` **verified identical**
(`1+63c6f8fd5a3e`) in both trees and no new `Settings` field, so **no ledger drain and no freeze change**.
GitHub-lists arming (+10 boards) and the one-off import of job-apps' targets stand from D-308: coverage of
job-apps' 465-item eligible set is **13.1%** (native ceiling 39.6%, aggregator-only 60.4%).
**D-305 IS SOUND — do not re-investigate the "analyst titles still delivered" report.** Verified against
the live module (`Risk Strategy Execution Analyst` → `not_swe`) and the delivery path (`runner.py:895` passes
no `include_non_swe`). All three offending artifacts are from **run 90, pre-fix**; post-fix runs 92–114 carry
**220 artifacts, 0 `not_swe`**. The remaining delivery-side leak is the 69 `uncertain` (31.4%), about half of
which are REAL engineering titles the taxonomy misses — a taxonomy fix would destroy them. Noise concentrates
in BOARDS: **AlphaHire unwatched** on Mit's ruling (59 open, 0 `swe`), fleet 235 → **234**; Genentech and
Walmart-external measured and ruled KEEP. Delivery-side work is owned by a separate session.

**LANES ARE CURRENTLY DISARMED (`lanes_enabled = []`)** — turned off while the facet was built so the leak
stopped accruing. Re-arm after the facet merges, then confirm on a live faceted run.

**COVERAGE vs job-apps — RE-MEASURED, and the earlier read was WRONG ABOUT WHERE THE GAP IS (D-310/D-311).**
The prior note said native ATS imports "top out at ~40%" and that only the lanes could close the gap. The
39.6% was the CEILING, not the position: boardwatch was watching boards for only **58 of job-apps' 465**
(12.5%). Re-derived by keying each queue posting to the `(provider, slug)` boardwatch would use — for Workday
the FULL composite `host/tenant/site`, which an earlier pass got wrong by comparing bare tenants and so
counted already-watched boards as new. Result: **125 postings across 97 boards were addable with ZERO new
code**. Imported with `--verify`: **95 watched, 2 skipped** (Comcast dead, CMU errored), so the fleet went
**140 → 235** and projected scan time 20 → **33 min** against the 180-min cadence. These are employers
job-apps never TARGETED — it found them through Indeed/JobRight — which is why last session's import of its
222-company target list netted only +7 and this one netted +95.

**NEW ATS PROVIDER ADAPTERS ARE NOT WORTH BUILDING — measured, and it inverts the standing assumption
(D-311).** Owner-gated item 2 recorded Oracle Cloud HCM + iCIMS as "~45% of the non-six tail". That was a
share of a small tail, not of the market. Over job-apps' full **138,788-posting** ledger: LinkedIn **49.7%**,
Indeed **23.4%**, Workday 10.0%, Greenhouse 3.4%, company-custom 3.6%, Ashby 1.1%, **Oracle Cloud 0.84%,
iCIMS 0.44%, Eightfold 0.28%**, and every other platform below 0.2%. So the two "big" candidates are ~1.3%
combined. **~73% of the market is LinkedIn + Indeed**: Indeed is out of scope, and LinkedIn is already a lane
— which is where leverage actually is, now that it has a keyword facet. `lane_posting_budget` is OUT of
`config_hash` (manifest.py), so raising the LinkedIn body budget is freeze-safe and is the cheapest next
experiment. Do NOT build per-ATS adapters at 0.1–0.8% each.

**SYSTEM PROVEN STABLE — 21 clean runs (92, 94–113), 1 failure (run 93, the pre-fix crash).** Corpus grew to
57,175 postings / 48,084 open; watched 140 (CMU's recurring-422 dead board removed as hygiene); 85 lane-
discovered companies recorded unwatched. 4 clean SCHEDULED ticks (92/95/101/108) + many clean manual runs; both
fixes hold every run; lanes healthy (no silent outage). Manual-run cadence was eased to scheduled-ticks-only at
session end to cut lane-leak accrual + conserve the rate-limit window. **The provisional pass (D-280) is
effectively met on quality** — P4 gate met, B1–B7 pass every run, freeze stable — pending only whatever formal
scheduled-tick count Mit wants to require.

**P4 CRAFT UNDER-FILL FIXED — the daily run now fills résumés to the page (D-303, 2026-08-25).** The P4
blind review FAILED on ~3 under-filled résumés: the daily run projected with base `projection.yaml`
(`runner.py:848`), whose `fill_to_page` defaults False; the earlier fill fix went only to the DORMANT
`projection.sde/ios/data.yaml` (persona routing is unwired — D-304). Fix = added `fill_to_page: true` +
`sort_projects_by_date: true` to base `projection.yaml`, owner-reapproved (digest `87513b4d`→`e61a1956`,
stamp on disk). Config-only; **no engine_version change, no ledger drain; freeze-safe.** Verified via a real
render path (thin postings 3→7 entries; compiled PDF 1 page) and the whole delivered set audits clean.
Fill overflow reviewed: it CANNOT ship 2 pages (two independent gates: select `_grow` + `run_tailor`
re-gate). First delivered filled résumés = the first scheduled tick after the 01:25 UTC approval (run 90
finished 01:21, pre-approval; a phantom run 91 took the id — see below), i.e. **run 92 onward**.

**PERSONA ROUTING INTO THE RUN — DEFERRED by owner (D-304).** `select_persona`/`apply_persona` run only in
the `tailor` REPORT path; the daily-run PROJECTION path is persona-blind and nothing maps
role-family→`projection.<persona>.yaml` (those 3 files are dormant). D-303 fixed the under-fill uniformly, so
per-persona projection is emphasis polish, not a fix — deferred; a real-discriminators redesign is future work.

**PRECISION LEAK (10.3% non-SWE leads) FIXED + MERGED + LIVE (D-305, PR #166 = `cbe6df9`, 2026-08-25).**
Two distinct leaks, two gates: (1) non-SWE families (analyst/specialist/administrator/advisor) — `role_verdict`
returned `"uncertain"` for no-signal titles absent from the deny catalog and `top_cmd.py:350` vetoes only
`"not_swe"`; fixed by a `_NOENG`-guarded deny in `rank/role_gate.py`'s `_DENY_FAMILIES_SOFT`. (2) eng-managers
were a SENIORITY-gate bug — the management-word guard was comma-scoped, so the INVERTED form ("Manager, Software
Engineering") shipped `in_band` while "Engineering Manager" was already `above_band`; the comma is the
discriminator, fixed in `rank/seniority_gate.py`. **Ranker-only — engine_version unchanged, NO drain**
(D-294/D-295). Opus-reviewed; verdict-neutral over 37,979 live titles (role `uncertain→not_swe` 2,150; band
`in_band→above_band` 386; **ZERO swe demotions, ZERO backward band moves, ZERO newly-shipped**). Pulled into
the primary tree this session, so the next scheduled tick runs it. **Cert (3 clean B1–B7 runs) counts from the
first post-(fill+role) tick = run 92.** THREE autonomous owner calls flagged for Mit's veto (see
`rolegate-nonswe-and-eng-manager-precision-shipped` memory): option-(b) seniority home for eng-mgrs; broad
families; the bare-`security specialist` carve-out reversal.

**FINISH-LINE INSTRUMENTATION BUILT (`.agent/2026-08-25-craft-findings/`, gitignored).** `finish_line_cert.py`
scores B1–B7 + freeze + P6 per run (validated on run 90: all PASS incl. independent pdfinfo 1-page; only
post_fill fails, correctly). B4 PASS + NON-VACUOUS (350 résumés / 3,426 bullets / 0 fabrications; negative
control catches drift+bogus-id). P4 objective checks (title-seniority / register / buzzword / requirement-echo
/ overmatch) 0 violations over delivered, non-vacuous (33 senior JDs stripped). **P6 leakage 0.00% over a FULL
7-day window** (ledger spans 08-19→08-26). B5 guard reviewed SOUND TO CERTIFY. **Remaining for provisional
pass: role fix live + 3 clean post-(fill+role) scheduled runs + the owner P4 blind review** (assembler ready:
`build_p4_blind_sample.py`, filters delivered by `e61a1956`).

**BOARD FLEET CLEANED + DOCTOR DETECTS MIGRATIONS (2026-08-24, D-300/D-301).** The 135 watched boards were
diagnosed: exactly **17 contributed zero** — not the 59 STATE claimed, which was a `postings_listed`-on-304
measurement artifact (the 118 `ok` boards hold 39,253 open postings). Root cause was ATS migration; **6
boards recovered (~3,522 postings), 11 dead unwatched → 124 watched, 0 dead/error/empty**. `doctor` now
suggests cross-provider board migrations (#161, D-301). Precision was confirmed **already armed** on `main`
(no move owed). PR #160 (community-home prep) merged. Part-4a's capped ramp is already shipped — see below.

**THE DAILY DRIVER IS FIXED AND THE CADENCE IS RAISED.** Run 70 (2026-08-23 08:00) died on a corpus-sized
`IN` list crossing SQLite's 32,766 bound-parameter cap at 32,771 open postings; six sites were over at
once. Fixed and merged (D-287). The launchd job now fires **eight times a day** — 02, 05, 08, 11, 14, 17,
20, 23 — instead of once (D-288).

**`runs` RESET TO 0 when the job was reloaded.** The pre-reload reading was `runs = 5, last exit code = 1`;
any absolute comparison against that number is void. The gate counts consecutive clean **ticks**, not
launchd invocations.

**GATE P3 IS MET — 20 CONSECUTIVE CLEAN SCHEDULED TICKS (runs 71-90), verified 2026-08-26.** All twenty carry
`runs.status='ok'` with `boards_attempted>0` at the scheduled 3h slots; run 70 (13:00 UTC 08-23) was the last
failure. **Verified from the live `runs` table + per-run funnels, not this file's count** — STATE lagged
because the job fires 8×/day and is written once per session. **7 required, 20 clean → MET.** Only a SCHEDULED
tick counts (`boards_attempted>0`) — a manual `run` and the phantom **run 91** (see below) move nothing; a
failed unattended run resets the streak.

> **A MANUAL RUN RACING A TICK EXITS 2 AND RESETS GATE P3**, and at 8 fires a day that is 8× likelier than
> it was. Check `launchctl print gui/$(id -u)/com.boardwatch.run | grep state` before starting one by hand.
> Two *scheduled* fires cannot collide — launchd never runs two instances of one label.

**The headline number: 0.** Zero job applications have ever been sent (`applications` has 0 rows) — the
machine produces leads, it never applies (out of scope). Against that: **4 published releases, latest
`0.5.0`**, ~53k lines of source, **7,584+ tests**, 71 leaf CLI commands, 6 ATS providers, a **~1.4 GB**
store holding **51,004 postings / 43,286 open** (2026-08-26).

> **PHANTOM run 91 (benign, mine).** A `boardwatch tailor run 13549` verification without a scratch
> `BOARDWATCH_DATA_DIR` called `ensure_run` and wrote to the LIVE store: run 91 (empty, `boards_attempted=0`,
> 36ms) + one `artifacts` row (id 498, uri→`/tmp`). NO `job_dispositions`, posting 13549 NOT marked handled,
> dedup/ledger UNAFFECTED, streak intact (the `boards_attempted>0` filter excludes it). Left in place (prod
> store has no rollback snapshot; deleting is riskier than an empty row). Consequence: next scheduled tick is
> **run 92**. Lesson: to verify projection against real postings with the LIVE edited config you must hit the
> live store — use read-only `resume project`, never `tailor run` (it writes a run+artifact).

**A BOUNDED PUBLIC-READINESS EFFORT SHIPPED AND `0.5.0` IS LIVE (D-299).** Scope was exactly three
workstreams — onboarding, README/ease-of-use, release currency — no feature expansion. `boardwatch guide`
and next-step CLI hints ship (PR #156); the README is compressed onto one canonical path with reference
depth moved into five linked guides (PR #156); a Windows-only nightly failure in the coverage-help test
was fixed test-only (PR #157); `0.5.0` is published to PyPI, GHCR, and a GitHub Release, verified with a
clean isolated install (PR #158) — the first release since `0.3.0`.

**PHASE 6 (COMMUNITY-HOME) GROUNDWORK IS OPEN AS DOCS-ONLY PR #160 — gate-neutral, `make check` green,
UNMERGED (Mit's to merge).** A GitHub Discussions launch plan (`docs/community.md`; **prep-and-hold** — Mit
enables Discussions manually at launch), a 6-provider capability matrix (`docs/provider-matrix.md`), and a
"Contributing a board" walkthrough in `CONTRIBUTING.md` (narrow local check = `pytest tests/unit/test_registry.py`).
Moves no program gate (the memo's continuation boundary). Stale nightly issue #142 closed — its commit
predates #157's fix, verified green on the full-matrix `workflow_dispatch` on `794eae2`. **Good-first issues
HELD** (Mit's call). Remaining owner launch decisions from the memo are still unsettled.

**The ASAP execution plan (D-280) governs.** "Done" is a **provisional pass** — 3 clean FROZEN runs meeting
all seven bar metrics (B1–B7) — after which the full 14-day acceptance runs PASSIVELY to confirm. Six
sessionized parts; the plan file at `~/.claude/plans/lets-use-this-session-staged-wren.md` **still names
Part 3 "Indeed" and Part 4 "hiring.cafe + GitHub lists" — that ordering was REVERSED by D-285 and the file
was never rewritten. Trust D-285/D-286, not the plan file.**

**PARTS 1, 2, 3, 4a AND 4b ARE COMPLETE.** Part 4a (GitHub-lists) landed #149/D-296. **PART 4b (LinkedIn) IS
BUILT (D-297)** — a lane sibling of hiring.cafe, OFF by default (`linkedin` not in `lanes_enabled`), **NOT
armed, never run live**. Built from D-290's recorded contract, not a fresh probe (Mit's "build from recorded
contract" ruling), so the card **selectors are RECONSTRUCTED, not freshly pinned** — arm-time live
verification is owed before enabling. Identity keys on the company **slug** (`externalApply`=0, no apply URL);
id from the URN not the URL tail; only `f_TPR=r86400` sent. No capture committed; authored fixtures. Next is
**Part 6** (freeze + 3 frozen B1–B7 runs), with Part 5 anytime.

> **D-291's "920 boards, 887 new" is real but its stated corpus is wrong**, and the difference is 4x. The
> figure is the **two new-grad lists' `active=True` records** (3,778 → 927 boards / 898 new, reproduced), not
> "all 6,088 active records" as the ruling reads. All four lists, unfiltered, give **3,881 / 3,813**. A board
> count needs its list set AND its `active` filter stated beside it. Full table in METRICS 2026-08-24.

**The lane (hiring.cafe) is BUILT but NOT ARMED and has never run against the live service.**
`lanes_enabled` defaults empty. Part 3's exit criterion 2 — a lead at a company none of the six providers
reach, carrying a real JD body — is **unevidenced**; a scratch run is owed before arming, and arming waits
on Gate P3 anyway. Detail: D-286.

**THE STORE IS AT `p_lane_companies`, which is `main`'s head**, so `ensure_schema` on the next tick is a
no-op. **The rule this bought: after any PR that adds a migration, apply it to the live store deliberately
and verify, rather than letting the next unattended tick discover it** (D-279/D-286). **There is no
rollback snapshot** — all three stale backups were verified redundant and deleted (2026-08-23b, ~2.9 GB
reclaimed). Take one before any destructive operation rather than assuming one exists.

**THE LAUNCHD JOB RUNS AN EDITABLE VENV RESOLVING TO `src/` IN THE PRIMARY WORKING TREE**, so a scheduled
tick executes whatever branch is CHECKED OUT there. **Leave that tree on `main`.** Use a worktree for
parallel work, and never `git stash` — it is shared across worktrees.

**Every agent invocation needs BOTH `BOARDWATCH_DATA_DIR` and `BOARDWATCH_CONFIG_DIR` on a scratch dir**
(D-281). `DATA_DIR` alone still READS the live `resume.yaml` / `career-profile/` / template and still
WRITES into the live `~/boardwatch-applications/`. The live store is the DEFAULT, so a forgotten flag
reaches production, and a migration breaks the NEXT scheduled run, not the one that erred. Two
consequences: a scratch run's `funnel-N` collides with the next real run's, and the artifact directory is
**UTC-dated** — match on the run NUMBER, never the date.

**Standing tripwire (D-268):** all six known precision leaks are blocked by the current gates — five
non-SWE `Lead` titles in the role gate, GE HealthCare posting 31365 (`Buc` → `non_us`) in the hard filter.
Any of the six appearing in a funnel's `leads` is a real regression to investigate before anything else.

**B5 IS NOW SCOREABLE — the zero-output guard is ARMED on run-scoped rank attribution (D-302, PR #164 = `0fb50a7`, MERGED 2026-08-25 and armed on the live driver).**
The guard counts the four SUPPRESSION drops restricted to the postings judged this run
(`hidden_handled_this_run`/`hidden_applied_this_run`/`hidden_duplicate_this_run` + `dead_this_run`) and fires
when `J − Σsuppressions_this_run > 0` with 0 leads; a negative raises a typed reconciliation error. Rejections
(hard-filter/non-SWE/over-seniority/below-cutoff) are meant to FIRE the guard (D-246), by owner ruling. No
`artifact_version`/`engine_version` change → no drain; freeze-safe. `make check` green (7584); whole-branch
review APPROVE. The scheduled driver now runs it; B5 can be certified in the frozen runs.

**B1 caveat, still live (D-281).** A 14-day B1 pass does NOT evidence discovery health — it is close to
guaranteed for ~92 runs by ledger drain alone; the real threat is a **ledger reopen**, which re-serves built
jobs and scores them 0 net-new.

**RULINGS 1, 2 AND 4 SHIP; RULING 3 IS DROPPED (D-294/D-295). PR #148 MERGED.** The role gate denies
non-software title families and blocks `Team Leader`; the foreign-location gate gained a CJK-script signal.
**Ranker-only — `engine_version` unchanged (`1+63c6f8fd5a3e`), no ledger drain.** Ruling 3
(`company_title_location` suppression) was implemented, audited over three rounds, and dropped: no
body-similarity floor separates a repost from a second opening (populations overlap).

**Round 3 found a production defect in EACH half — three rounds, three defects, each invisible to the round
before.** The standing lesson is now explicit: **a review round is not finished until a round finds
nothing.**

- **Role gate:** the front-end rescue's head nouns were `(engineer|...|lead)\w*`, so `lead` was
  **`lead\w*` and matched "Leader"**, re-rescuing as `swe` the exact retail rows ruling 2 denies — the same
  failure as the `manager` token D-294 had already rejected. The comment two lines below *and* D-294's own
  record both asserted `\blead\b` does not match "Leader"; the code never had that property. Fixed by an
  inner group, **verdict-neutral over 27,680 unique titles**, 0 live hits today — only breadth would have
  surfaced it.
- **Ruling 3:** its floor was calibrated at min-true-duplicate 0.9421 vs max-non-duplicate 0.8986. Reading
  the body diff of all 40 suppressions below 0.945 found **9 are different openings** — GE HealthCare's
  Lubbock / Salt Lake City / Chattanooga postings (all `locations=["Remote"]`), a Capital One pair whose
  loser's own URL reads `Lead-Software-Engineer--Front-End`, Thomson Reuters Indirect vs Direct Tax. Non-
  duplicates reach **0.9372**: the window is ~0.005 and **the populations overlap, so no floor separates
  them**. The char→word metric change made it *worse*. And no test constrained the constant — any floor in
  (0.1915, 0.9550] left the suite green.

**Dropping ruling 3 dissolved both dedup findings at once**, because each followed from admitting a second
suppressing kind; a forced single-kind control returns byte-identical suppressions (566/566). The cost was
measured before the choice: delivered duplicate leakage is **3 of 146 = 2.05%**, inside Gate P6's 5% bar
**without** ruling 3. A redesign on the real discriminators — requisition slug, the body's own city, salary
band, YOE, all of which lie *outside* the similarity number — is **deferred, not dismissed**.

**The precision work is a PREREQUISITE for raising the cap, not a yield gain.** Measured against delivered
output rather than the corpus: 6 of the 146 résumés ever built were for roles the new gate rejects, and
exactly **1 of run 71's 40 leads** would have been denied. D-292's "51.1% carries no software signal" is a
property of the *uncapped* 3,771 — the ranker already sorts most of it below the cap.

**`DEFAULT_TOP_N` is 10 — a HOLDING value until the precision work lands (D-293), and the uncapped set was
MEASURED, not estimated (D-292): 3,771 postings arriving ~220-430/day, of which 67.6% are `role=uncertain`,
so honest confirmed-software arrival is ~70/day. Quote neither figure without naming its population —
they differ by 4x.** Do **not** raise the cap before the precision work is merged, and do **not** set it to
0: that fails B1 (>= 10 net-new leads/day) outright while Gate P3's counter keeps running. The cap sets
**burn rate, not supply** — long-run output equals the arrival rate whatever it is. Lifting it is Mit's
call and is now informed on both sides (D-293, D-294).

---

## Next action

**The provisional pass (D-280) is effectively met on quality** — P4 gate MET (objective 0-violations + owner
blind review passed), B1–B7 pass on every run (verified via `.agent/2026-08-25-craft-findings/finish_line_cert.py
--runs <N>`), freeze tuple stable across runs 92/94 (`config_hash f56a0166…`, engine_version `1+63c6f8fd5a3e`),
P6 leakage 0.00% over 7d, B4 370/0. 21 clean runs (92, 94–113). **No build left.** Immediate items:

1. **RE-ARM the lanes and confirm the facet on a live run.** The facet is built and merged (D-309); the
   lanes were disarmed during the build. `boardwatch config set lanes_enabled "hiringcafe,linkedin"`, then
   check the next scheduled tick delivers software leads and no ops/retail titles. `lanes_enabled` is out of
   `config_hash`, so arming touches no freeze.
2. **Consider raising the LinkedIn body budget (`lane_posting_budget`).** D-311 measured LinkedIn at 49.7%
   of the reachable market and the setting is OUT of `config_hash`, so it is freeze-safe to change. The facet
   makes those bodies software-relevant for the first time; the budget is now the binding constraint, not the
   search. Measure a run before and after rather than assuming.
3. **Confirm the formal cert bar.** Quality is proven; if a strict "N clean SCHEDULED ticks" count is still
   wanted, scheduled ticks 92/95/101/108 are clean (manual runs 94/96–100/102–107/109–113 don't count as
   scheduled but are all clean). Score any run with `finish_line_cert.py --runs <N>`.

**Arming Part 4a's ~898 boards remains a SEPARATE owner decision, NOT taken.** The capped `discover`→review→
`import` loop is shipped; ramp in batches of ~10 (898 at ~7s each exceeds the 3h cadence). Do **not** add a
defaulted `watched=` to `upsert_watch`. `companies.source` is `CHECK (source IN ('registry','user','lane'))`.

*(The `.agent/2026-08-25-craft-findings/` harnesses — AUTONOMOUS-SESSION-LOG.md, COVERAGE-VS-JOBAPPS.md,
LANE-ARMING.md — and `.agent/2026-08-26-lane-facet/` (NOTES.md with every probe number, DOC-DRAFT.md,
`probe_linkedin_keywords.py`, and the raw `linkedin-probe/` HTML + summary.json) are gitignored working
material; re-derive if pruned. The LinkedIn probe script is the one to re-run before trusting that lane's
request contract again — it drives the production `Fetcher`, so its output IS the contract.)*

---

## Owner-gated — do NOT start or decide unilaterally

0. ~~**THE ARMED LANES LEAK non-SWE noise into delivery — pick one (D-308).**~~ **DECIDED by Mit
   2026-08-26: option (b), build the facet — shipped as D-309.** Recorded because the reasoning bounds the
   next lane: option (c) (extend the role deny-catalog) was measured and REJECTED, not merely passed over —
   the `uncertain` tail is Busser / Water Spider / Dish Steward / Donation Processor / Nannies / Janitorial,
   an unbounded list, and the same bucket holds Linux Engineer, Senior HPC Engineer and Principal Architect
   that a broad deny would lose. **Do not propose a lane-noise fix in the role taxonomy again**; the fix is
   always upstream in what the lane asks for. Item 1 below is also settled by the same probe: hiring.cafe
   showed 100% location fill, so the location fail-open was never the issue — the ROLE fail-open was.

1. **hiring.cafe's `v5_processed_job_data.workplace_*` fields** — read as provider-asserted location
   metadata, at the level greenhouse's `location.name` is already trusted (D-286 Ruling 4). D-278 called
   that payload untrusted, reasoning from the keystone invariant — which governs eligibility RULES, and the
   engine is body-only so it cannot reach these. The measurement that decided it: `classify_location([])`
   returns `unknown` and the hard US gate PASSES `unknown`, so withholding locations does not filter a
   3.89M-posting board, it admits all of it. On a broader reading the lane needs another location source
   before arming. **One function either way.**
2. ~~**Oracle Cloud HCM / iCIMS as PROVIDERS**~~ **CLOSED by measurement (D-311): do NOT build them.** The
   "~45% of the non-six tail" figure was a share of a small tail. Over job-apps' 138,788-posting ledger,
   Oracle Cloud is **0.84%** and iCIMS **0.44%** — ~1.3% combined, and every remaining platform is under
   0.2%. LinkedIn is 49.7% and Indeed 23.4% of that corpus, so ~73% of the market sits on one lane boardwatch
   already has and one source that is out of scope. **The lever is the LinkedIn lane's budget/paging, not new
   adapters.** Reopen only if a measurement on a different corpus contradicts this.
3. ~~**Run-scoped rank attribution** — the only honest fix for B5~~ **DELIVERED + MERGED (D-302, PR #164 =
   `0fb50a7`).** Four run-scoped suppression twins + the reconciliation invariant; B5 is scoreable and armed
   on the live driver. No code left for B5.
4. **`locations` on `Lead` + an `artifact_version` bump** — the funnel can evidence no lead's LOCATION, so
   the one gate whose failure is a visa-ineligible lead leaves no trace in its own artifact (D-267). A
   shipped-schema change.
5. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
6. **P2 item 8 — the onboarding field-taxonomy gatherer.** Needs its own brainstorm; D-054 forbids us
   authoring non-tech field content.
7. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.
8. **Extending the leakage query past `exact_quad`** — the Gate P6 clause **cannot fail** for the
   `company_title_location` class, because `store/identity_queries.py:296` hardcodes `kind == "exact_quad"`.
   Dropping ruling 3 did not close this and made it sharper: those duplicates are now neither suppressed nor
   counted, and the corpus holds **1,597 redundant open postings (4.76%)** on that key. **Never cite a
   passing leakage number as evidence dedup works.** One join condition, but it reverses D-132/D-283's
   ratified "only `exact_quad` counts" **while the gate is being measured** (D-294/D-295).
9. **A redesign of same-role-same-place dedup on real discriminators** — the requisition slug in the
   posting's own URL, the city named in the body, the salary band, the YOE line. Ruling 3 is dropped because
   a fuzzy body score provably cannot do this (D-295), not because the duplicates are acceptable. Its own
   change, its own ruling.

---

## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
2. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level token
   abstains, so a level-named title is shortlisted carrying its reason. boardwatch ships no verifiable
   claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio**, `detail_fetch_budget`, and the 17 silent boards.

*(Resolved and no longer open: whether `runner.py` should keep swallowing a funnel-write failure — D-288
records it and the run still does not fail. Clearance IS a blocker (D-257). Seniority band = `entry`
(D-258). The launchd trigger fires (D-254), and its cadence is now ~3h (D-288).)*

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** at ~3h (D-288) | **MET** — 8 consecutive clean scheduled ticks (runs 71-78), verified from the `runs` table + funnels |
| P4 Craft gate | **COMPLETE** (under-fill fixed D-303; objective anti-slop 0 violations, non-vacuous) | **NEARLY MET** — objective half certified; awaiting the owner's BLIND CRAFT REVIEW on post-fill résumés (run 92+) |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **3 of 4** — liveness MET (D-281), leakage measurable and reading **0.00%** but needs a 7-day ledger span (~2026-08-26) |
| 14-day acceptance | not started | starts after P6 |
| P7 Breadth | lane 1 (hiring.cafe) BUILT not armed (D-286); **Part 4a GitHub-lists discovery BUILT + LANDED (#149/D-296), not armed**; **Part 4b LinkedIn lane BUILT (D-297), off by default, not armed, selectors reconstructed**; remaining lanes not started | unlock MET (D-271/272) |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days ≤ 5% | **STILL CANNOT FAIL FOR ONE CLASS — see D-294 before quoting it.** `identity_queries.py:296` hardcodes `kind == "exact_quad"`, so a job whose only identity is `company_title_location` lands in `unidentified` and can never be counted redundant. Ruling 3 stopped those duplicates reaching leads but did NOT extend this metric, so it reads 0.00% for a structural reason. Measured honestly over the 146 delivered résumés (grouping by company+title+location) the real figure is **3 redundant = 2.05%** — under the bar, not zero. Extending the query reverses D-132/D-283 mid-gate and is the owner's. Original standing: **measurable, awaiting span (D-283).** `boardwatch identities leakage [--days N] [--json]` ships. **Live: 100 surfaced jobs / 100 distinct `exact_quad` groups / 0 redundant = 0.00%.** Only `exact_quad` counts (Mit's ruling, ratified); counted over jobs that REACHED LEADS, not the corpus; body-less jobs sit in their own `unidentified` bucket, never folded. **Not yet "over 7 days"** — the ledger starts 2026-08-19 so ~3.2 days exist, and the 7-day `seen` TTL cannot be observed faster than itself. First true window **~2026-08-26**, inside Parts 2–4, so off the critical path |
| **0** dead postings reaching leads | **MET (D-281).** Two runs on a scratch store copy: `checked 40, dead 0, unknown 2, alive 38, gone_after_redirect 0`, identical in both, agreeing across three read paths (funnel JSON, funnel markdown, stdout). Detector demonstrably ARMED — `checked > 0`, so not the disarmed 0/0 signature. The `runs` table has no liveness columns, so no DB-row path exists; those three are all there are |
| Injected hash-collision test | **MET** (D-100) |
| Audit of 20 sampled suppressions | **MET** (D-101) |

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **A metric that could not fail (D-267)** | `grep -ic buc funnel-N.json` was read as a Buc count; it counts the word "bucket" and is 4 on runs 61/63/65/66 regardless. The funnel enumerates **no ranked pool** and a `leads` row carries **no location** — so the hard location gate, the one gate whose failure is a visa-ineligible lead, leaves no trace in its own artifact. Closing it needs `locations` on `Lead` + an `artifact_version` bump. **Re-raised 2026-08-21c; still Mit's.** D-268 corrects this row's replacement metric too: "0 of 62" had the 0 robust under every bounded rule (27/27/69/70 matched, 0 surviving) but the **62 unreproducible** — match rule and corpus size were never recorded beside it, and a bare substring gives 103 matched / **39 surviving**. A ratio now records its match rule AND corpus size | **Mit** (shipped-schema change) |
| **boardwatch cannot see 92% of job-apps' eligible yield** | 41 of 530 records (7.7%) at a watched company; 352 companies in the set, 24 watched. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| ~~Five boards GREEN-and-zero + 12 dead~~ **RESOLVED (D-300)** | Diagnosed 2026-08-24: root cause is ATS migration, not typos. The 5 empty — HubSpot→`greenhouse:hubspotjobs`, Plaid→`ashby:plaid`, Vercel→`greenhouse:vercel` recovered; Qualcomm/Snyk unwatched. The 12 error/dead were all Workday: **5 GATED (401/403, unrecoverable)**, 7 wrong-site (422, recovered walmart wd504 + veeva→lever + purestorage→greenhouse, rest unwatched). Watched 135→124, **0 dead/error/empty**. `doctor` now suggests migrations (D-301, #161). Backoff/quarantine still absent but the fleet is clean | done |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| ~~`top`'s drain flags break in ~2 days~~ | **CLOSED by #145** (D-289): all six corpus-sized `IN` lists chunk through `store/param_chunks.id_chunks`, three merge shapes each mutation-tested, including `reopen_jobs`' summed rowcount | done |
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **`add-evidence` takes no bundle lock** | two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **Disk pressure now costs GATE TIME, silently** | The same suite ran **4m51s** at ~7.4 GiB free and **34m40s** at 5.7 GiB / 98% — no error, nothing logged, and a bounded waiter timed out, which reads as a hang. Cause was pytest's own temp trees at **1.1 GB** across 5 runs in `/private/var/folders/*/*/T/pytest-of-mitsheth/`; clearing the stale ones (keep the newest, it is live) plus branch cleanup took the volume to **9.1 GiB / 96%**. The two stale store backups beside the live database are a further **1.67 GB** | **Mit** (the backups) |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to ~10 min; a longer gate reads as `make: *** [test] Error 143` — that is SIGTERM, not a build break. **`setsid` does not exist on macOS**: use `nohup sh -c '<export PATH>; make check > LOG 2>&1; echo $? > DONE' & disown`, set PATH INSIDE the subshell, and gate on the sentinel file, never the launcher's exit code. The clamp is WALL-CLOCK, so CPU contention converts a comfortable run into a kill — a suite that ran 5m17s alone was SIGTERMed at 62% while one subagent ran its own pytest. Never pipe the gate through `head`/`tail` | tooling |
