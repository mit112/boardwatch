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

**THE DAILY DRIVER IS FIXED AND THE CADENCE IS RAISED.** Run 70 (2026-08-23 08:00) died on a corpus-sized
`IN` list crossing SQLite's 32,766 bound-parameter cap at 32,771 open postings; six sites were over at
once. Fixed and merged (D-287). The launchd job now fires **eight times a day** — 02, 05, 08, 11, 14, 17,
20, 23 — instead of once (D-288).

**`runs` RESET TO 0 when the job was reloaded.** The pre-reload reading was `runs = 5, last exit code = 1`;
any absolute comparison against that number is void. The gate counts consecutive clean **ticks**, not
launchd invocations.

**GATE P3 IS 0 OF 7 and the next clean tick is 1 of 7 (D-276).** A failed unattended run RESETS the streak
rather than pausing it, and **Gate P4 is barred until P3 is met**. Only a SCHEDULED tick counts — a manual
`run --project` moves nothing. At 8 fires a day this is now roughly a 21-hour gate rather than a 7-day one.

> **A MANUAL RUN RACING A TICK EXITS 2 AND RESETS GATE P3**, and at 8 fires a day that is 8× likelier than
> it was. Check `launchctl print gui/$(id -u)/com.boardwatch.run | grep state` before starting one by hand.
> Two *scheduled* fires cannot collide — launchd never runs two instances of one label.

**The headline number: 0.** Zero job applications have ever been sent (`applications` has 0 rows) — the
machine produces leads, it never applies (out of scope). Against that: 3 published releases (none since
**0.3.0**), ~53k lines of source, **7,386 tests**, 71 leaf CLI commands, 6 ATS providers, a **~1.4 GB**
store holding 37,438 postings / 32,771 open.

**The ASAP execution plan (D-280) governs.** "Done" is a **provisional pass** — 3 clean FROZEN runs meeting
all seven bar metrics (B1–B7) — after which the full 14-day acceptance runs PASSIVELY to confirm. Six
sessionized parts; the plan file at `~/.claude/plans/lets-use-this-session-staged-wren.md` **still names
Part 3 "Indeed" and Part 4 "hiring.cafe + GitHub lists" — that ordering was REVERSED by D-285 and the file
was never rewritten. Trust D-285/D-286, not the plan file.**

**PARTS 1, 2 AND 3 ARE COMPLETE, AND PART 4 IS PROBED BUT NOT BUILT.** Both probes ran 2026-08-23d and
both are ruled, so the next action is the BUILD, in this order: the **GitHub-lists client** (D-291 — company
discovery, no JD body anywhere in 34,984 records, but **887 of 920 boards are new**), then **LinkedIn**
(D-290 — Mit ruled BUILD; the body is free and unauthenticated, and `robots.txt` disallows the route). Then
Part 6, with Part 5 anytime. Plan: `.agent/` scratch notes carry the shape; the rulings are in D-290/D-291.

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

**B1 and B5 caveats, both live (D-281/D-282).** A 14-day B1 pass does NOT evidence discovery health — it is
close to guaranteed for ~92 runs by ledger drain alone; the real threat is a **ledger reopen**, which
re-serves built jobs and scores them 0 net-new. **B5 is UNSCOREABLE** until run-scoped rank attribution
exists — do not score it on exit status alone.

**`DEFAULT_TOP_N` is 40 and LIVE.** `capped_by_top_n` is **3,683** — that many postings clear every filter
and are cut by rank alone. Mit's standing ruling: **fix precision, never tune the cap.**

---

## Next action

**Build Part 4.** Both halves are probed and ruled (D-290, D-291); neither is built. Order is 1→2→3→4→6
with Part 5 anytime; 1–3 are merged. Build the **GitHub-lists client first** — it needs no new provider code
(slugs come out in registry shape) and carries no permission question — then **LinkedIn**, off by default
like hiring.cafe and not armed while Gate P3 accrues.

Two constraints that must survive into the build, both measured: LinkedIn exposes **no external apply URL**
(`externalApply` appears 0 times), so converge on the company **slug**, never the link; and **`f_WT=2`
(remote) is silently ignored**, returning a byte-identical set to unfiltered. Commit **no** captured JD body
from either source — the generalization gate refuses third-party data that would oblige a licence which
does not exist, and 4 of the 6 GitHub repos ship no licence at all.

---

## Owner-gated — do NOT start or decide unilaterally

1. **hiring.cafe's `v5_processed_job_data.workplace_*` fields** — read as provider-asserted location
   metadata, at the level greenhouse's `location.name` is already trusted (D-286 Ruling 4). D-278 called
   that payload untrusted, reasoning from the keystone invariant — which governs eligibility RULES, and the
   engine is body-only so it cannot reach these. The measurement that decided it: `classify_location([])`
   returns `unknown` and the hard US gate PASSES `unknown`, so withholding locations does not filter a
   3.89M-posting board, it admits all of it. On a broader reading the lane needs another location source
   before arming. **One function either way.**
2. **Oracle Cloud HCM / iCIMS as PROVIDERS** — D-278's still-open provider question, explicitly NOT settled
   by D-285 (that ruled on lanes). ~45% of the non-six tail; reaches neither Amazon nor Apple nor TikTok.
3. **Run-scoped rank attribution** — the only honest fix for B5, which is UNSCOREABLE until it exists
   (D-282). Four drop sites plus the funnel reconciliation identity. Matters before Part 6 scores B5.
4. **`locations` on `Lead` + an `artifact_version` bump** — the funnel can evidence no lead's LOCATION, so
   the one gate whose failure is a visa-ineligible lead leaves no trace in its own artifact (D-267). A
   shipped-schema change.
5. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
6. **P2 item 8 — the onboarding field-taxonomy gatherer.** Needs its own brainstorm; D-054 forbids us
   authoring non-tech field content.
7. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.

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
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** — runs 63 and 66 were genuine scheduled ticks (D-254) | **NOT MET — 0 of 7 unattended.** Streak reset by run 68's failed tick (D-276) |
| P4 Craft gate | **COMPLETE** | **NOT MET** — the owner's blind craft review, barred until P3's gate |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **3 of 4** — liveness MET (D-281), leakage measurable and reading **0.00%** but needs a 7-day ledger span (~2026-08-26) |
| 14-day acceptance | not started | starts after P6 |
| P7 Breadth | lane 1 (hiring.cafe) BUILT, **not armed and never run live** (D-286); lanes 2-4 not started | gated on P0 attribution data |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days ≤ 5% | **MEASURABLE AND PASSING, awaiting span (D-283).** `boardwatch identities leakage [--days N] [--json]` ships. **Live: 100 surfaced jobs / 100 distinct `exact_quad` groups / 0 redundant = 0.00%.** Only `exact_quad` counts (Mit's ruling, ratified); counted over jobs that REACHED LEADS, not the corpus; body-less jobs sit in their own `unidentified` bucket, never folded. **Not yet "over 7 days"** — the ledger starts 2026-08-19 so ~3.2 days exist, and the 7-day `seen` TTL cannot be observed faster than itself. First true window **~2026-08-26**, inside Parts 2–4, so off the critical path |
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
| **Five boards report GREEN and return zero, ever** | Snyk, Vercel, HubSpot, Plaid, Qualcomm — clean scans, `last_health='empty'`, 0 postings across 12 scans. 7 of the 12 dead boards are HTTP 422 (malformed request ⇒ probably wrong slugs, recoverable). No backoff, no quarantine, no drain | **Mit** (input-side) |
| **`unchanged` is an unaudited coverage assumption** | 59 of 135 boards listed nothing in run 67 on a payload hash. No test exists for a hash misreporting a changed board. A false `unchanged` is silent, permanent and undetectable by any current instrument | open |
| **`top`'s drain flags break in ~2 DAYS** | with `--include-hard-filter` / `--include-non-swe` / `--include-over-seniority` open — D-277's ONLY drain for a `hidden_hard_filter` that is 59% of the corpus — `eligible_ids` is **30,419** measured against a cap of 32,766: **2,528** postings of headroom at ~**1,264/day** net growth. Runs exit 0 today. The scheduled tick stays safe (~3,683). Chunk `identity_queries.py:45/97`, `regroup.py:52/88`, `ledger_queries.py:48`, and `reopen_jobs:148` which needs a SUMMED rowcount (D-288) | **IMMEDIATE next task** |
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **`add-evidence` takes no bundle lock** | two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **Disk pressure now costs GATE TIME, silently** | The same suite ran **4m51s** at ~7.4 GiB free and **34m40s** at 5.7 GiB / 98% — no error, nothing logged, and a bounded waiter timed out, which reads as a hang. Cause was pytest's own temp trees at **1.1 GB** across 5 runs in `/private/var/folders/*/*/T/pytest-of-mitsheth/`; clearing the stale ones (keep the newest, it is live) plus branch cleanup took the volume to **9.1 GiB / 96%**. The two stale store backups beside the live database are a further **1.67 GB** | **Mit** (the backups) |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to ~10 min; a longer gate reads as `make: *** [test] Error 143` — that is SIGTERM, not a build break. **`setsid` does not exist on macOS**: use `nohup sh -c '<export PATH>; make check > LOG 2>&1; echo $? > DONE' & disown`, set PATH INSIDE the subshell, and gate on the sentinel file, never the launcher's exit code. The clamp is WALL-CLOCK, so CPU contention converts a comfortable run into a kill — a suite that ran 5m17s alone was SIGTERMed at 62% while one subagent ran its own pytest. Never pipe the gate through `head`/`tail` | tooling |
