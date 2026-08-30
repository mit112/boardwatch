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

**RUN 133 READ OUT: THE DIGEST HALF OF THE ALERT CHANNEL IS ACCEPTED, AND hiring.cafe FAILED AGAIN.**
`morning-133.md` opens with `## Alerts`, above `## Discovery reach`, rendering the run's one alert — the
acceptance criterion for the ten 2026-08-29f PRs, met. The baseline is proven on the artifact:
`morning-131.md` is 489 lines with **zero** `## Alerts` sections, while that run's identical lane failure
sat at **line 1390 of a 1,390-line, 116 KB funnel**. Run 133 was clean — `status=ok`, launchd exit 0,
**1h52m52s** (inside the ~1h45m estimate), 379 boards / 271 complete / 21 partial / **0 failed**, 23,166
seen, 4,300 net-new, 1,053 closed, 40 leads with 40 PDFs, reach 88.1%. The heartbeat fired (`errors_json`
holds the lane failure and no `heartbeat:` entry, which a refused ping would have left, D-375).

**THE ALERT CHANNEL TO AN ABSENT OWNER WAS *NOT* CLOSED ON 2026-08-29f. IT IS CLOSED NOW, AND IT SHIPS
DISARMED (D-376, #258).** What 2026-08-29f closed was the channel to someone *sitting at the machine*.
Verified this session, every link: the digest is a file under `~/boardwatch-applications/<date>/` and
neither it nor `~/boardwatch-queue` is inside iCloud Drive, Dropbox or Google Drive; the heartbeat gate is
`fatal is None and funnel is not None and morning is not None` — **`errors` is not in it**, so a run raising
every soft alert still pings **green**; `runner.py` never imports `WebhookChannel`; and the plist declares
exactly two environment variables with no `com.boardwatch.notify` job. **Runs 130 and 131 are the proof it
already bit** — both `status='ok'` with a dead hiring.cafe lane, both pinged green.
**Scope the claim precisely: the uncovered class is NON-FATAL DEGRADATION.** The dead-man's switch does
work; a crash or a sleeping machine leaves no ping and healthchecks.io alerts inside 1 day + 2 h grace.

**ARMING IS ONE PLIST LINE AND IT IS MIT'S CALL — IT IS THE ONLY ACTION THAT MAKES #258 DO ANYTHING.**
`BOARDWATCH_ALERT_URL` is unset, so the code is a strict no-op today (verified through the editable venv).
The exact edit, the reload commands and the two questions to settle first — do you want daily paging while
away, and does your healthchecks target reach you — are in `.agent/2026-08-30-session/ARMING-alert-
escalation.md`. **Deliberately not armed: it pages a real person.**

**WHAT ESCALATES IS THE FINALIZE-BLOCK SLICE, NOT `summary.errors`, AND THAT WAS MEASURED.**
`summary.errors` accumulates every stage error — one dead board slug, a lane that could not collect, a
per-lead tailor degradation. Over the last 25 runs **nine carried a non-empty `summary.errors` and not one
of the nine was a finalize-block alert**; runs 124-128 each carried `plaid: HTTP 404`. Escalating that list
would have driven the monitor DOWN on five ordinary `status=ok` runs. **Consequence to know: a dead LANE no
longer reaches the remote channel**, only the digest — closing that means a lane-health *detector*, not a
wider payload. On run 133 itself the channel would have posted **nothing**, which is correct.

**RUN 134 IS THE FIRST PRODUCTION EXECUTION OF #258 AND #260 — RUN 133 IS NOT EVIDENCE FOR THEM.**
Run 133 finished 10:52:56 UTC; #258 merged 11:03:05 UTC and #260 11:44:15 UTC, so both landed AFTER
it. Run 133 IS the acceptance evidence for the ten 2026-08-29f PRs (#247-#256), which is what its
`## Alerts` section proves — do not stretch it further. The escalation chain was instead proven
end-to-end **in a real pipeline run** on an isolated store: a real detector result reached
`summary.errors`, the digest rendered `## Alerts` above `## Discovery reach`, and the real
`escalate_alerts` POSTed the body over a real socket, with the run surviving. That is a test
environment, not production. **Expect run 134 to be the first time this code runs for real, and
expect it to POST nothing** — the channel is unarmed, and even armed, run 133's only alert was a
LANE error, which the finalize-block slice deliberately excludes.

**A STEP DETECTOR CANNOT HELP DURING A CODE FREEZE — do not count corpus-regression as coverage
for these two weeks.** Firing on a >50% step between runs is the documented design
(`corpus_regression.py`, "this is a STEP detector ... fires roughly three times, then ... goes
quiet" — that is a stated limitation, NOT a defect, and a sweep has now mistaken it for one once).
But a freeze removes every mechanism that produces a step: a rules edit, a profile fact that stops
resolving, a taxonomy change are all changes the freeze forbids. What a freeze permits is gradual
composition drift, which a step detector is blind to by construction. Combined with its cold start
(dark until ~run 138), treat it as unavailable for most of the absence.

**THE 2026-08-27 CADENCE CHANGE SILENTLY RESCALED EVERY WINDOW, because they count RUNS not TIME.**
At 8 runs/day `INTAKE_DEATH_WINDOW = 3` and `DELIVERY_DROUGHT_WINDOW = 3` meant ~9 h; at 1 run/day
they mean **3 days**. `CORPUS_REGRESSION_WINDOW = 5` (needing 6 runs) went ~18 h -> **6 days**. And
`death_probe_budget = 50` went 400/day -> **50/day** against 75-384 new unwatched-company postings a
day, so `due` grows monotonically (run 133: `due=1139, attempted=50, refused=1089`). The probe drift
is bounded in importance by its own 6.7% detection rate. **Detection latency during the absence is
3 days, not hours** — worth knowing before reading a quiet morning as healthy.

**`check_intake_death` HAS NO RUN-STATUS FILTER, and both its siblings do — owner's call.**
`intake_death.py:42-47` selects on `new_count IS NOT NULL` only, while `delivery_drought.py:50` and
`corpus_regression.py:89` both filter `status == RUN_OK`; no test covers the status dimension. Two
wrong directions, the second worse: a failed run with `new_count = 0` can contribute to a FALSE
alert, and a failed run with `new_count > 0` **RESETS the window and MASKS** a real intake death —
run 132 is exactly that shape (`status='failed'`, `new_count=400`, one board). **Not fixed here**:
it cannot bite while nobody is running ad-hoc scans, it is not a one-line change (a seeded run
defaults to `status='running'`, so adding the filter silences all six existing tests), and whether a
FAILED run should count toward "intake died" is a judgement, not a typo.

**THE ORDERING INVARIANT IS LOAD-BEARING AND A MECHANICAL REBASE BREAKS IT SILENTLY (D-374).**
`_emit_funnel -> _sync_queue -> [ALL soft alerts] -> _emit_morning -> heartbeat gate`. An alert appended
BELOW `_emit_morning` still fires, is still recorded, and is **invisible to the owner** — which is exactly
how the queue-sync note and #249's intake-death alert shipped. Three separate branches tried to union into
that region this session and two would have landed below the digest. **Verify the order in source after any
rebase touching the finalize block; do not assume a clean rebase preserved it.**

**SAY WHICH ELIGIBILITY POLICY YOU MEAN, EVERY TIME (D-350)** — catalog and live profile diverge on **five
of six** families (`rules.yaml`: only `work_auth` is a `blocker` default; live store: all six). Full rule in
`STANDING-FACTS.md`.

**The lane question is CLOSED (D-346/D-347) — do not re-propose lane parallelism.** In `STANDING-FACTS.md`.

**Everything below this line is carried and remains true.** Gate P6 is 4 of 4; **the delivery cap is 40, set
in the plist (D-366)** and the code default `DEFAULT_TOP_N` stays 10; breadth is argued on precision and
capacity, never an application count (D-312). Board cost is provider-weighted and **s/board is a lying
unit**. **Raising `scan_workers` above `le=8` stays RETIRED** (D-344). Numbers: `METRICS.md`.

---

## Next action

> **THE ONE ACTION THAT MATTERS BEFORE THE ABSENCE: decide whether to ARM `BOARDWATCH_ALERT_URL`.** #258 is
> merged and verified on `main` and through the editable venv, but it is a **strict no-op until armed**, so
> without this the fortnight has no remote signal for a degraded-but-successful run. One line in the plist;
> exact edit in `.agent/2026-08-30-session/ARMING-alert-escalation.md`. Deliberately left to Mit: it pages a
> real person, and it depends on the healthchecks target actually reaching him.
>
> **Run 133 already migrated the store** (`p_runs_board_split` -> `p_runs_corpus_counts`, `alembic_version`
> confirmed) and populated the corpus columns for the first time. **`boardwatch web` was NOT restarted this
> session and still need not be** — verified that PID 22459 holds no descriptor on `boardwatch.db`, so it
> cannot block a WAL checkpoint; the viewer never migrates (D-279), so restarting it against a checkout
> ahead of the store 500s it. It is now safe to restart *if wanted*, since the store has migrated.
>
> **corpus-regression CANNOT FIRE until ~run 138 (~2026-09-04).** All 133 pre-existing runs have
> `corpus_open/evaluated/candidates` NULL; run 133 is qualifying baseline point **1 of 6**. Bounded, and
> **not worth patching** — the obvious zero-floor fix contradicts `test_abstains_below_the_window`, a
> tested and documented decision. The one run the detector could not judge was run 133 itself, and that was
> checked by hand: no collapse.

> **THE HEARTBEAT IS NOW SELF-REPORTING, BUT RECEIPT IS STILL MIT'S TO CONFIRM (D-375).**
> `send_heartbeat()` used to return a `bool` whose value was discarded, with `False` meaning BOTH "refused"
> and "no URL configured" — so the obvious "alert on falsy" fix would have fired on every unconfigured
> install. It now returns `str | None` and a refused ping is recorded durably. **What it still cannot do is
> prove the ping ARRIVED.** Open the healthchecks.io dashboard and confirm the 04:00 pings landed, and that
> the notification target is one Mit reads while away. **Do NOT GET the ping URL to check — that
> manufactures a green.** Note the heartbeat's own alert reaches NO artifact: the gate is last, after
> `_emit_morning`, and no report reads a prior run's `errors_json` (verified, not assumed).

1. **hiring.cafe: THE READOUT IS IN AND IT IS NEGATIVE — HEADERS ARE ELIMINATED (D-369, #245).** Run 133
   failed exactly as run 131 did, byte for byte: `SearchPageError("every role facet yielded nothing (14
   searched, 14 request failures)")`. It started 04:00 on 08-30, well after the fix committed 13:23 on
   08-29, so it **is** the readout. The header hypothesis is dead. **Do not re-run this experiment.**
   **What remains is the ENDPOINT, and it is the OWNER'S call, not an agent's.** Path-scoped protection on
   `/jobs/*` is the strongest surviving hypothesis (volume is the weaker one): job-apps succeeds on `/`,
   our `/api/` calls succeeded every run through 128, our `/jobs/` calls have now failed **14 of 14 on two
   separate runs**. Moving off `/jobs/` is a **compliance decision, not a repair** — robots.txt ALLOWS
   `/jobs/` and DISALLOWS job-apps' `?searchState=` form, so the compliant route is the blocked one. The
   drafted, unsent access request is at `.agent/2026-08-28g-session/hiringcafe-access-request.md`.
   **Still do NOT probe the site, even once.** Until it lifts, lane coverage is **HALVED**.
   **A second, smaller decision now sits beside it:** left enabled, the lane will issue ~14 refused facet
   requests per run — roughly **196 over an unattended fortnight** — to a host that refuses us. Disabling
   it is one line in the LOCAL `config.toml` (`lanes_enabled`). Genuinely balanced and NOT actioned:
   against disabling, those requests are within hiring.cafe's own published robots policy and 14/day is
   trivial load; for disabling, it stops futile traffic and *may* help if the "more requests keep it
   closed" premise holds — which is a hypothesis, not a measurement. Leaving it enabled preserves the only
   signal that would show a recovery.


2. **THE PACING TRIAL IS HELD, NOT CANCELLED (D-355).** #222 **is merged now** — the previous
   STATE claimed that while the PR was still OPEN and RED, and the repo won (D-358). The lever ships
   **disarmed**; arming is one config line plus a read-back check, and the whole procedure is in
   `.agent/2026-08-28f-degree-audit/RUN131-CHECKLIST.md`. Mit held it on 2026-08-28 because
   hiring.cafe began refusing us on a day that ran FOUR runs against a cadence of one, and
   **raising the per-host rate 0.6 -> 1.0 req/s on that day is the wrong direction**. Revisit once
   hiring.cafe is healthy and the run cadence is back to normal. **`Settings` does NOT forbid extra
   keys, so a typo'd config key arms NOTHING silently — always read the value back through
   `load_settings()`.**

   **2026-08-29d — there is now a MECHANICAL reason too, not just a judgement call.** `_lane_fetcher`
   builds its `Fetcher` from the **same `Settings`**, so `pace_from_request_start` applies to the
   **LANE** as well as the scan. Arming it cuts the hiring.cafe facet interval from "1.0 s + response
   time" to a flat 1.0 s — **2-4x faster against the host that is currently refusing us**, and a
   **second variable in the D-369 readout**. Keep it disarmed at least until that run reads out. Live
   config confirmed at this close: `per_host_delay_seconds=1.0`, `pace_from_request_start=False`,
   `scan_workers=8`, `detail_fetch_budget=400`.

   **The revert trigger is the PARTIAL RATE AMONG FETCHED BOARDS, and the two earlier versions were
   both wrong (D-353).** Revert on **+5 pts or worse**; run 130 read 9.7%. Do NOT use a raw
   `complete -> partial` count (background rate 3-6 EVERY run) and do NOT use the net of the two
   (it read **-10 on run 130, which had no pacing change**, because `unchanged` collapsed 153 -> 36
   when the validator TTL expired). Any `board_scans` query MUST filter `scan_kind='board'`.

   **Run safety, worktrees and the shared scratchpad have moved to `STANDING-FACTS.md`** ("Moved out
   of STATE on 2026-08-28g") — process-liveness guarding, the EDITABLE venv, PID-scoped kills, and
   per-launch log/sentinel naming. Read that section before touching a live run or launching a gate.

3. **THE PROVISIONAL PASS IS ALLOWED TO SLIP — "work comes first" (D-351).** #218 reset the
   3-clean-run counter and it is **not being chased**. **Read it as UNBLOCKING: eligibility is NOT
   frozen**, so rules work may land freely and a `rules_hash` bump is not costly on this basis until
   the owner reopens the pass. The P4 blind review remains passed and does not repeat.

4. **Phase 1b and its follow-up are COMPLETE — item RETIRED.** Detail moved verbatim to
   `STANDING-FACTS.md` 2026-08-28h, including why #230 is keyed on the `role_vetoed` MEMBER and
   must not be re-broadened to the review lane (D-354, D-359).

5. **`main` IS GREEN** and stayed green across #240-#243. The three deflakes behind that, and the
   standing rule they produced — **when a timing test flakes, ask what it MEASURED versus what it
   CLAIMS**, and **mutate every new assertion** — are in `STANDING-FACTS.md`.

6. **Re-read the queue after the next run.** The D-333 band moved 6,123 evaluations into `uncertain`
   and D-332 routes them; `.agent/2026-08-27-queue-split/` holds the read-only harness.
   `phase2_measure.py` correctly reports 0 movers — that is "already moved", not a broken query.

7. **Deferred with numbers, do not re-derive:** job-apps' preferred-vs-required HEADING state
   machine is **2 of 286** and architectural (D-320). The years-detection gap that sat here was
   addressed by #218 — read that PR, not the old 24-leads/1.3% figure.

## Owner-gated — do NOT start or decide unilaterally

8. **Mit's two résumé content calls** — whether to send a document at all; the D-220 prose rewrites.
9. **P2 item 8 — the onboarding field-taxonomy gatherer. DEFERRED by Mit 2026-08-28**: no time before
   he steps back from active work (~2026-08-31, unattended after). **Not dropped — an accepted known
   gap**, and the last multi-tenancy gap of its kind. Still owner-gated and still needs its own
   brainstorm; D-054 forbids us authoring non-tech field content.
10. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against
   one bundle.
## Open questions — Mit's, not to be resolved by fiat

1. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate
   the projection manifest, and whether persona's `entries` list survives stage 2.
2. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level
   token abstains, so a level-named title is shortlisted carrying its reason. boardwatch ships no
   verifiable claim about any company's ladder.
3. **Whether `censored` boards publish a coverage ratio, and the 17 silent boards.** The
   `detail_fetch_budget` half moved 2026-08-28: raised **50 → 400 in Mit's local config only** (never
   the code default — a multi-tenancy call). **The "four censored boards are short 18,927" figure is
   STALE against the current fleet**: the class is **15 boards and 43,371 postings that can never be
   listed at all** (run 127), against an ~84,821-posting open corpus. **Sized, not solved, and no
   budget can solve it** — those postings are never enumerated. See D-336.
4. **Whether `ServiceNow Developer` should rank at all against a new-grad SWE target.** Surfaced by
   run 129's location-split failure and **left unexamined** — it is role TAXONOMY, not dedup, and
   possibly upstream of the whole slate-cap question. D-345 bounds the delivery damage; it does not
   answer this.

*(Resolved and no longer open: **how to cap the delivery slate when one requisition is split across
cities — RULED by Mit and shipped as D-345**, `(company_id, normalized_title, content_hash)` at N=1;
do not reopen it as identity suppression, which is D-295 and is refused. Whether `runner.py` should
keep swallowing a funnel-write failure — D-288. Clearance IS a blocker (D-257). Seniority band =
`entry` (D-258). The launchd trigger fires (D-254), once daily at 04:00, a fallback rather than the
thing to plan around.)*

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** once daily at 04:00 local (owner's call 2026-08-27; was ~3h under D-288). The agent is now a FALLBACK HEARTBEAT — Mit's ruling is to invoke a run manually as and when needed, so do not wait for the schedule | **MET** — 8 consecutive clean scheduled ticks (runs 71-78), verified from the `runs` table + funnels |
| P4 Craft gate | **COMPLETE** (under-fill fixed D-303; objective anti-slop 0 violations, non-vacuous) | **MET** — objective half certified AND the owner's blind craft review passed cleanly 2026-08-26 (all 5 judged worse were job-apps decoys; all 3 judged better were boardwatch) |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113); leakage report shipped (D-283) | **MET — 4 of 4** (2026-08-27): liveness MET (D-281), leakage measurable over a true 7-day span and reading **0.00%**; see the clause table for the `exact_quad` caveat |
| 14-day acceptance | not started | **HELD BY THE OWNER (2026-08-27)** — the provisional pass was MET by runs 119-123, and Mit ruled to keep fixing precision first rather than start the clock. Starting it freezes eligibility, profile and the résumé gate for 14 days. **2026-08-28e: the provisional pass's remaining item — 3 clean post-fix runs — RESTARTED FROM ZERO**, because #218 bumps `rules_hash` and those runs are therefore pre-fix again. The P4 owner blind review is still PASSED (2026-08-26) and does not repeat. With runs on demand and Mit stepping back ~2026-08-31, that is 3 runs in ~3 days; **the trade (stricter eligibility now vs the pass possibly not closing before unattended operation) was raised to Mit and is his**. **2026-08-28f: #221 bumps `rules_hash` again, so the counter restarts again — and this is NOT being chased (D-351 item 2 stands: work comes first)** |
| P7 Breadth | **lane 1 (hiring.cafe) and Part 4b (LinkedIn) are BUILT AND ARMED and ran in run 122** (hiringcafe 70 attempted/56 resolved; linkedin 71/51) — the previous "not armed" text was stale. **Part 4a GitHub-lists discovery BUILT + LANDED (#149/D-296) and NOW PARTLY ARMED**: 97 boards imported 2026-08-27, ~765 candidates still capped. Remaining lanes not started | unlock MET (D-271/272) |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6 — MET, 4 of 4

The clause-by-clause table moved to `STANDING-FACTS.md` on 2026-08-28f: every clause is MET and
none has moved since 2026-08-27. Read it there before quoting the leakage figure — the `exact_quad`
caveat (D-294) is what makes 0.00% a structural reading rather than a clean one.

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **boardwatch sees 16.4% of job-apps' eligible yield — RE-DERIVED 2026-08-30, and the METHOD was wrong before** | **45 of 275 (16.4%)**, cohorts 08-23..08-29, on the **379-board fleet**. This replaces "10.1%, owed a check". It decomposes: fleet growth 344->379 gave 10.1 -> **13.8%**; adding an **exact ATS-slug key** alongside name matching gave 13.8 -> **16.4%**. **Name-only matching undercounts, so 7.7% and 10.1% are FLOORS** — boardwatch stores Micron as `Micron TDIT`, so the old method scored a watched company as unwatched; same for HPE/`Hewlett Packard Enterprise`, Cox/`Cox Automotive`, Disney/`Walt Disney Company`, Toyota, VIAVI. **The unreached 230 split: aggregator-only 60.7%, unsupported employer host 21.1%, board-addable just 1.8%** (5 postings in 7 days, 4 of them SmartRecruiters — the class D-370 declined on measured cost), so the cheap remainder is ONE Workday board (Motorola Solutions). **The gap is lanes, not boards.** Script: `.agent/2026-08-30-session/reach_v2.py`. Amazon/TikTok/Apple/ByteDance use none of the 6 ATS, so a slug cannot reach them. Closing it means a new discovery lane — GitHub new-grad lists are 19.1% of yield for ~5 public-repo GETs and are NOT the ToS trap the v2 decision was written about. **Reopens D-008** | **Mit** (reverses a shipped decision) |
| **Delivery-drought cannot see APPLY-LANE starvation** | `delivery_drought.py` counts `artifacts.kind == TAILORED_KIND`, which is written **regardless of which lane `review_gate.lane()` routes to**. If location classification broke globally every lead would go to `_review`, artifacts would keep appearing, drought would abstain, and the owner would get **zero apply-ready leads for a fortnight with nothing firing**. Verified open. Current split is healthy (run 133: 40 new to apply; 420 apply / 189 `_review` = 31%). NOT built: the lane decision lives in `_sync_queue`'s copy step (`delivery/queue.py:385`) and its result type is shared with the web server, so a guard is a materially bigger change than it looks — wrong thing to ship days before an absence | **Mit** (on return) |
| ~~Four detector fallbacks are print-only, not durable~~ **CLOSED by #260** | The `intake-death` / `delivery-drought` / `liveness-blindness` / `corpus-regression` "check not run" handlers now call `append_run_error` like the three artifact-write handlers beside them, so a DETECTOR that crashes leaves a row in `runs.errors_json` and not only a digest line. Four one-line additions, inert on the normal path; each pinned by its OWN parametrised test, because a single test crashing all four passes while three of the four calls are missing. **Known shared property:** `append_run_error` is not internally defensive and these sit inside `except` handlers — matched to the three existing handlers deliberately rather than diverging; it needs two simultaneous failures and fails loudly via the withheld heartbeat | **CLOSED** |
| **`companies.last_health` / `last_ok_at` are a LYING instrument** | 178 of 379 watched boards read NULL, which looks like "never succeeded" — **all 178 were scanned by run 133** (128 complete, 7 partial, 43 unchanged). The scan path does not maintain these columns. **Judge fleet health from `board_scans` per run instead**: run 133 was 379 attempted / 271 complete / 87 unchanged / 21 partial / **0 failed** | tooling gotcha |
| **Citi sits at 13.1% coverage, permanently** | Workday's `total` censors at 2,000; the facet sum (uncapped, control-verified) says 4,589. Our pager wraps at ~2,000 too, so post-drain Citi holds ~2,214 of 4,589 and nothing reports it | **Mit** (input-side) |
| **`unchanged` staleness is now BOUNDED (D-298, #153)** | The `unchanged` verdict comes from the upstream HTTP validator (ETag/Last-Modified → 304), not a boardwatch payload hash. `validator_max_age_hours` (default 24) drops a validator older than the TTL, forcing an unconditional refetch, so a permanently-stale upstream can no longer freeze a board forever — the silent-staleness window is capped at the TTL, and a regression test now exercises the aged-validator refetch. Still open: within the TTL an `unchanged` is trusted with no independent check. The separate "59 of 135 boards listed nothing" figure was a **`postings_listed`-on-304 artifact — CORRECTED to 17 real dead-weight (D-300)**, now cleaned; the 118 `ok` boards hold 39,253 open postings | open (mitigated) |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **A live store is readable ONLY via Python `sqlite3` `?mode=ro`** | the `sqlite3` CLI with `?mode=ro` fails `CANTOPEN(14)` on a cleanly-checkpointed store (no `-shm`; not the sandbox), and `?immutable=1` skips the WAL so it is STALE against a live writer. Mid-run progress: `SELECT COUNT(*) FROM eligibility_evaluations WHERE run_id=N` (D-268) | tooling |
| **`boardwatch web` IS RUNNING — started 2026-08-29d** | Started from the primary checkout on `main` with `--port 0 --no-open` and **verified through a second path**: `GET /` returns 200 and `GET /api/runs` returns **401 without a token and 200 with the bearer**. The session URL is `http://127.0.0.1:<port>/#<token>` — the token rides in the **fragment** so it never reaches a server log or a `Referer`, it is stable, and it lives at `~/Library/Application Support/boardwatch/web-token` (mode 0600). **The port is whatever `--port 0` picked**, so read it from the process rather than assuming: `lsof -nP -iTCP -sTCP:LISTEN -a -p $(pgrep -f 'boardwatch web')`. It was stopped and restarted once during this session to take the store lock for the D-370 cold scan — **never write to the store with the viewer up**, a WAL two-writer deadlock against a running pipeline is on record. The underlying skew is still structural (D-360): the bundle is served from **disk** and the API from the Python imported **at startup**, so any merge or branch switch under a running viewer separates the two — **DO NOT RESTART IT AS OF 2026-08-29f.** `main` now carries the `p_runs_corpus_counts` migration while the store is still at `p_runs_board_split` until the 04:00 run migrates it, and the viewer NEVER migrates (D-279) — restarting against a checkout AHEAD of the store 500s it. The running process holds the pre-merge code in memory and is correct either side of an additive migration, so leaving it alone is the safe action. Restart only AFTER a run has migrated the store; the bundle it serves is built on disk (`web/dist` is untracked) and only `make web` changes it. #232 makes a missing field degrade to the pre-#224 view instead of blanking the page | **Mit** (restart after merges) |
| **The unattended 04:00 tick runs the PRIMARY checkout's branch — and it is now PROVEN to fire** | Run 131 (2026-08-29, `runs = 1`, exit 0) was the first real unattended tick. The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Verified at the 2026-08-29f close: the tree is on `main` at `10baad5`, clean, and all six alert modules import through the editable venv.** A stale 8-hour-old `.git/index.lock` had silently blocked every `git pull` that session — check the lock's MTIME and `pgrep -x git` before blaming contention. **Park it on `main` before ending every session** — from ~2026-08-31 a stray branch changes EVERY subsequent run, not one. Closing it mechanically means pointing the plist at a worktree pinned to `main`, which moves a scheduled job and a venv | **Mit** (mechanism); every session (discipline) |
| **hiring.cafe lane is DOWN; the HEADER LEVER FAILED and the remaining call is the OWNER'S** | **D-369/#245 shipped the search route's browser-navigation header set and run 133 is its readout: NEGATIVE.** Run 133 reproduced run 131's `SearchPageError` byte for byte (14 facets, 14 refusals), so **headers are ELIMINATED and that experiment must not be repeated.** D-368's other premises were already dead: the UA premise is FALSE (we have sent a Chrome UA since the lane shipped) and the volume premise did not survive the run log (run 128 spent ~28 requests; run 131 was refused on its FIRST request 14 h later). **What remains is the ENDPOINT — path-scoped protection on `/jobs/*`**: job-apps succeeds on `/`, our `/api/` calls succeeded every run through 128, our `/jobs/` calls have failed **14 of 14 on two separate runs**. That is a **compliance decision, not a repair** — robots.txt ALLOWS `/jobs/` and DISALLOWS job-apps' `?searchState=` form. **Still do NOT probe.** Half the lane coverage job-apps' edge comes from. **Second, smaller call:** ~196 refused requests over an unattended fortnight if the lane stays enabled (balanced; see Next action item 1) | **Mit** (the endpoint call, or send the drafted access request; and whether to leave the lane enabled) |
