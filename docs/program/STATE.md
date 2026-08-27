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

**THE YEARS-OF-EXPERIENCE GATE HAD NEVER FIRED — FIXED, ARMED AND LIVE (D-319 #175, D-320 #176).** The owner
opened the delivery queue and the first lead demanded 5 years. Measured: **142 of 588 delivered leads (24.1%)
state a minimum of five or more years.** Three stacked causes — (1) `experience_years` sat at the catalog
default `preference` and only `blocker` can yield `ineligible`, so **53 required rows resolved UNMET and not
one changed a verdict**; (2) `scoped_years_minimum` was a **100% abstain, 342 of the family's 441 rows**,
already visible as 10,872/10,872 in `reports/abstain.py`; (3) the pattern missed `5+ years building …` and
`12+ years in …` entirely (37 of the 142 produced no row). Fixed by one sound inference — **a duration scoped
to a single skill cannot exceed the career it sits inside, so `total < need` is UNMET**, while `total >= need`
keeps abstaining because a `met` there would claim a per-skill duration the profile lacks. Owner ruling: keep
`total_years_experience = 1`, literal comparison, **accept 0–1 years and block 2+**. Live: `experience_years:
blocker` written to the profile 21:00 CDT and verified by direct SQL; primary tree at `1dff564`;
**`engine_version` `1+63c6f8fd5a3e` → `1+5bf77461f044`**. Measured effect: delivered **582 → 302**, **101 of
the 142 blocked**, practical false-positive rate ~1–3%. **THE FREEZE IS BROKEN AND D-280's PROVISIONAL-PASS
RUN COUNT RESETS — owner confirmed.** No ledger drain owed, by argument: the change is strictly narrowing (see
D-319). **`eligible` collapses 339 → 24 while delivery only halves** — a scoped requirement within budget
still abstains, so the D-312 end-of-line figure drops hard and that is honest, not a regression.

**~60/day is NOW STALE.** The D-312 rule below still governs HOW to report, but its number predates D-319.
Re-measure before quoting anything; expect roughly half the delivered volume and a far smaller affirmatively
`eligible` count.

**LANE-ACQUIRED POSTINGS CAN NEVER CLOSE — there is no drain, and disarming does not stop delivery (D-314).**
Found by smoke-testing the facet verifier: run 114 ran AFTER the 12:10 lane disarm and still delivered three
lane-sourced non-SWE leads. Chain, each link read in source: the only writer of `status="closed"` is
`_process_missing` (`scan/apply.py`), gated on `CLOSE_AFTER_MISSES = 2`; it runs on **`complete`** snapshots
only; `lanes/base.py::lane_snapshot` returns **always `partial`** by design; `pipeline/liveness.py::check_leads`
*"reads URLs; writes nothing, ever"*; and lane companies are upserted `watched=False` so the scan coordinator
never revisits them. **A lane re-acquires by SEARCH, so absence can never be evidence** — this holds with
lanes armed too. Measured: **282 lane postings, ALL `open`, ZERO ever closed** (197 `not_swe` / 82 `uncertain`
/ 3 `swe`). The facet fixes INFLOW only; these 282 stay in the ranked pool indefinitely. Also: **no downstream
consumer can trust `postings.status` for a lane row** — it reads `open` forever, and "still open" is
indistinguishable from "unverifiable". **NOT FIXED — owner-gated:** an age-based close needs a trigger other
than absence, which is a design question, not a tweak.


**HOW TO REPORT YIELD — the owner's standing rule (D-312).** Every yield, coverage or job-apps comparison
quotes **the end of the line: affirmatively `eligible` jobs** — currently **~60/day** (eligible + software +
in-band + US + non-duplicate + unhandled). **Never** quote a broader upstream population as the headline:
"new postings/day" and "software-titled/day" are different quantities, and doing so overstated yield ~8× in
this session before Mit caught it (the hard US filter alone removes 57% of the corpus). **`uncertain` is
never folded into `eligible`** — the keystone invariant, not a preference; the ~82/day abstains get their own
line. Measure with `stats` / `top --no-record --json` / the run funnel, never ad-hoc SQL over `postings`.

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

**`DEFAULT_TOP_N` is 10 — a HOLDING value until the precision work lands (D-293), and the uncapped set was
MEASURED, not estimated (D-292): 3,771 postings arriving ~220-430/day, of which 67.6% are `role=uncertain`,
so honest confirmed-software arrival is ~70/day. Quote neither figure without naming its population —
they differ by 4x.** Do **not** raise the cap before the precision work is merged, and do **not** set it to
0: that fails B1 (>= 10 net-new leads/day) outright while Gate P3's counter keeps running. The cap sets
**burn rate, not supply** — long-run output equals the arrival rate whatever it is. Lifting it is Mit's
call and is now informed on both sides (D-293, D-294).

---

## Next action

**The provisional pass is NO LONGER met — D-319 reset it deliberately.** Quality still holds (P4 gate MET,
B1–B7 passing, P6 leakage 0.00% over 7d, B4 370/0), but `engine_version` moved, so the frozen-run count starts
again from the first tick on `1+5bf77461f044`. **No build is outstanding for the years gate.** Immediate items:

1. **VERIFY THE FIRST TICK ON THE NEW ENGINE (23:00 CDT / 04:00Z).** Run 117 (01:00Z, `ok`, 234 boards, 59
   min) was the last on the old engine. The next tick is the first with `experience_years: blocker` AND the
   D-319 resolver, and it re-evaluates all 267,434 stale evaluations. Check: delivered volume roughly halves,
   `ineligible` becomes a large bucket, and no posting asking 0–1 years is blocked. A full-corpus
   `top --no-record` was started this session as an independent production-path check.
2. **PR #176 (D-320) may still be in flight** — `make check` green locally (7993 passed), auto-merge armed.
   It adds the activity-gerund pattern (10 newly blocked, 0 spared) and a `we bring` company-side suppressor.
   Confirm it merged and was pulled before reading the next tick's numbers, or the two changes blur together.
3. **Decide the queue's `ineligible` presentation — OWNER-FACING.** `delivered_unapplied` attaches the current
   verdict but never filters on it, and `api._counts` has **no `ineligible` key**, so after D-319 roughly 294
   of 598 queue folders become an unexplained remainder between `in_queue` and `eligible + uncertain`. Needs a
   product call plus a JS bundle rebuild; not taken unilaterally.
4. **Consider raising the LinkedIn body budget (`lane_posting_budget`).** D-311 measured LinkedIn at 49.7%
   of the reachable market and the setting is OUT of `config_hash`, so it is freeze-safe. Measure a run before
   and after rather than assuming.
5. **`internship` and `contract_not_fte` are the SAME defect as D-319 and are NOT armed.** Both sit at
   `preference` while the profile declares `internship_preference: exclude` and `employment_type_preference:
   fte_only`. Measured on 598 delivered leads: arming them blocks **2** (Disney intern reqs) and **1** (a UT
   Austin contract role) respectively; `degree: blocker` would add **1** (Intel, doctorate). All correct, all
   tiny. Owner's call, and each costs another freeze reset.

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

0b. **NO DRAIN EXISTS FOR LANE-ACQUIRED POSTINGS (D-314).** 282 postings, all `open`, none ever closed, and
   the mechanism makes it structural rather than a bug: a lane re-acquires by SEARCH, so absence can never be
   evidence, and `lane_snapshot` is always `partial` so `_process_missing` never runs. An age-based close needs
   a trigger other than absence and a fail-safe direction chosen (closing a live job is the expensive error).
   Also decide whether anything may show an open/closed label for a lane row at all — `postings.status` reads
   `open` forever and cannot distinguish "still open" from "unverifiable".

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
| P4 Craft gate | **COMPLETE** (under-fill fixed D-303; objective anti-slop 0 violations, non-vacuous) | **MET** — objective half certified AND the owner's blind craft review passed cleanly 2026-08-26 (all 5 judged worse were job-apps decoys; all 3 judged better were boardwatch) |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **3 of 4** — liveness MET (D-281), leakage measurable and reading **0.00%** but needs a 7-day ledger span (~2026-08-26) |
| 14-day acceptance | not started | starts after P6 **and after a fresh frozen window** — D-319 reset the clock (`engine_version` `1+5bf77461f044`) |
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
