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
> blocks), **on 2026-09-12** (the four settled 2026-09-06 session blocks), **on 2026-09-12b** (the 2026-09-07 early and mid blocks) and **on 2026-09-13c** (the 2026-09-07 review block and the whole 2026-09-12 session). Nothing was deleted on any of the six passes. Do not narrate a decision here that
> `DECISIONS.md` already holds — cite its number instead. **If this file passes ~250 lines again, the
> fix is to move settled blocks out, not to summarise them away.**

---

## Current standing

### 2026-09-13 close (c) — THE SENIORITY LEVER, RULE (b), THE 243 RENDERS, AND THE THRESHOLDS RULED: **D-504, D-505.** PR #375.

**Mit gave full authority for everything on the previous close's list, and all of it is done.**

**The apply lane's bottleneck MOVED, and that is the session's real finding (D-504).** After 0-B,
the dominant residual defect is not eligibility at all — **`seniority_fit` is 60% of the audit's
unapplyable calls and 13 of the 14 in the promoted cohort** — and the title ladder cannot see it,
because **every audited item read `in_band`**. So the judge that already reads the whole JD is asked
`seniority_fit` beside its verdict (never inside it: no verdict, no `rules_hash`, **the confirm is
not restarted**), and a `no` holds under its own reason `seniority_judged_above_band`.
**SHIPPED DISARMED** — validated against sonnet and opus on 149 items, haiku catches **14 of 15**
senior bodies and invents **18 of 134**, so arming projects **457 @ 16.3% → 364 @ 9.0%, volume
−20%**. That trade is Mit's; `gate.seniority_hold = true` is one line, needs no re-judge, and the
reading accumulates either way so it can be re-measured live first. **This is the open
recommendation: ARM IT** — 9.0% clears B8's ≤ 16% bar with room, and a held lead is still delivered.

**The 243 promoted leads all have résumés now, and the drain was recorded WRONG.**
`boardwatch tailor run <id>` alone returns `page_limit_exceeded` on every lead — it renders the
authored résumé, which does not fit the page budget. The real drain is **two** commands
(`resume project` then `tailor run --resume`), ~5.1 s. Ran over all 243: **243 ok, 0 failed**;
verified through `delivered_unapplied` at **244 with a PDF, 0 missing**. The `runner.py` comment is
corrected.

**0-D's repair half needs NO CODE.** Re-measured, the population GREW through run 57 (112 → 123
overwrites, 301 → 302 `raw_json`) — but **118 of the 123 are on WATCHED boards**, where the scan
already revises them every run and the lane simply overwrote it again afterwards. With the
declaration shipped the board body wins, so it drains itself. **Prediction for run 64: both counts
fall toward 0.** Residual: 5 postings on unwatched boards, measured and accepted.

**D-498 rule (b) shipped** (highest-ranked lane copy survives a lanes-only group).

**Next action.** (1) Merge PR #375 when CI is green. (2) Read the 04:00 tick — **run 64**, confirm
day 9 — and read it against four changed behaviours: a bigger apply lane and smaller review lane
(0-B), `hidden_lane_copy` non-zero (0-C + rule (b)), 484 boards, and the 0-D drain prediction above.
`seniority_judged_above_band` should be an EMPTY bucket until Mit arms it. (3) **Arm
`gate.seniority_hold`?** — Mit's, recommended yes, numbers above. (4) **The second Gate 1 reading is
owed ~09-19** and it is the LAST condition on M4: with D-505 ruling no bar for Indeed and
hiring.cafe, the employer-board half alone decides, and all four boards already clear 85%. If the
second reading holds, **job-apps switches off**. (5) Still open from D-494: seed the cluster cap
from the standing queue; ratify `apple`'s `board_reported_total = None`.

### 2026-09-13 close (b) — MIT'S FOUR OWNER CALLS TAKEN AT SESSION START AND ALL FOUR EXECUTED: **D-502, D-503.** PR #374.

**The batch, and the answers.** 0-B promote the two requirement holds, blind-audit first. 0-C rule (a)
only. 0-D declare on the converging lanes. Retail: drain and drop. Every one is now shipped, gated
(`make check` exit 0, zero failures) and on PR #374. **Nothing moved `engine_version` or `rules_hash`,
so the 14-day confirm is NOT restarted.**

**0-D shipped NARROWER than the ruling, because D-500's premise was wrong for two of the three lanes
(D-502).** hiring.cafe appends the PROVIDER's own `RawPosting` verbatim — only its recorded
`source_url` is the aggregator's, because the lane owns the GET — and `jsonld` has never converged
onto a board posting at all; declaring either would freeze firsthand data. **job-apps IS the defect**:
612 `revised` versions onto board postings, ALL tier 1, and the board's very next reading reverted
**87 of 436 (20.0%)** by more than half the body. Tier 1 declares `CONVERGED_SECONDHAND`; tiers 2 and
3 declare nothing. The REPAIR half (117 overwritten bodies, 301 lane-payload `raw_json` rows) is NOT
done — Mit chose the declaration, not the repair, and it stays available.

**0-B shipped BEHIND the audit Mit required, and the audit is the reason it is safe (D-503).** Three
arms of 56 shuffled into one pool, judges **sonnet and opus** (never haiku, the production judge under
test), 96.4% inter-rater agreement: **the apply lane as it stands 21.4% unapplyable, `experience_requirement` + judge 1.8%, `no_requirements_found` + judge 16.1%** — so promoting 248
leads into 209 gives **457 at 16.3%**, moving B8 toward its ≤ 16% bar instead of away from it. D-458's
**32%** for the same silent-clear class collapses to **16.1%** once the judge filters it, which is the
claim that was under test. It releases those two holds ONLY; `eligibility_unconfirmed` stands because
an abstain is not evidence. **No seniority refinement exists** — 13 of the 14 `nrf` failures are
`seniority_fit` and every item in all three arms reads `in_band`, so the title ladder cannot see them.
Report: `.agent/2026-09-13-session/promotion-audit/REPORT.md`.

**0-C shipped as rule (a):** 17 of the 34 multi-member `cross_host` groups on the 589-lead standing
queue, own bucket `shortlist.hidden_lane_copy`, `top --include-lane-copy` drain, keyed on
`PROVIDER_NAMES` and not `classify_host`.

**The three retail boards are GONE. Fleet 487 → 484, 6,884 postings closed, 3 residual open.** Measured
first against a control: 0 leads ever delivered from any of the three. Abbott stays (7 delivered).

**PR #374 is MERGED and main's CI is green.** `main` is `78068ef9`; the editable venv the tick runs
carries all three changes.

**Next action.** (1) Read the 04:00 tick on 09-14. **It is run 64, NOT run 58** — this session's
retail drain wrote runs 58–63 (six `boardwatch scan` invocations, 18:39–18:40 UTC), exactly as the
09-12 session's drain wrote 49–56. It is **confirm day 9** whichever number it carries; only the tick
counts toward the confirm, a hand scan never does. Read it knowing THREE delivery behaviours changed:
expect a bigger apply lane and a smaller review lane (0-B — **244 standing folders move `_review` →
apply on the first reconcile, all with `pdf_missing`**, see the résumé item below), `hidden_lane_copy`
non-zero in the funnel (0-C), and 484 watched boards. Also on the list: the reach line's `stale` (139
on run 57, 26–42 before) and the T78 nightly count (2 of 10 if green). (2) **The Indeed and hiring.cafe per-source THRESHOLD is the only
M4 item left and is still Mit's** — the numbers are in hand (24.9% / 22.1%, D-499) and the
recommendation put to him is NO BAR on either, same as LinkedIn, on the ground that they are reach
lanes into employers no board covers. (3) **The 244 promoted folders carry no résumé and were deliberately NOT rendered.** They were
delivered `pending_tailor`, and the tailor loop only renders the current run's shortlist, so no run
will pick them up. The drain is `boardwatch tailor run <posting_id>`, ~4.35 s each (~18 min for 244).
Held because **Mit's per-lens formatting session is still owed** (open questions item 3) — rendering
244 documents in a format he has not signed off is the wrong order. His call. (4) Still open from
D-494: seed the cluster cap from the standing queue; ratify `apple`'s `board_reported_total = None`.
(5) D-498's rule (b) (+18) and 0-D's REPAIR half (117 bodies, 301 `raw_json` rows) are sized and
unbuilt — neither was ruled on.

### 2026-09-13 close (run 57 READ — the first tick on everything the 09-12 session shipped; the first GREEN NIGHTLY since 08-31)

**Run 57, the 04:00 tick, `ok` in 58 min: 480 boards, 0 failed, 5,098 new, 4,108 closed, 177,958 open,
funnel reconciles — confirm day 8 of 14.** Gate 58 judged (30 / 6 / 22), **0 batches failed open**, and the
new partial path worked live: batch 3/5 answered 12 of 13 and the run reads `partly failed open: 1 of 13
verdicts missing` with the 12 kept. 9 PDFs + 31 review, 10 withheld as gone, 6 gate-rejected; queue 40 new,
12 moved. No watched unsliced copy of a sliced board (the D-496 query is empty). The lanes admitted 32 more
boards → **watched 487**; censored 4 (short 15,242). One number to read again on run 58: the reach line's
`stale` jumped to 139 (26–42 on runs 44–48) — likely a quiet Sunday of 304s, unverified. **Nightly CI
2026-09-13 (34757609598): GREEN — the first scheduled green since 08-31; T78 clean-nightly count 1 of 10.**

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

**0-B, 0-C and 0-D are ALL SHIPPED (2026-09-13, D-502/D-503) and are no longer owner-gated.** 0-D
shipped narrower than the ruling and the correction is in D-502; 0-D's REPAIR half (117 overwritten
bodies, 301 lane-payload `raw_json` rows) was not part of the ruling and remains available if Mit
wants it. D-498's rule (b) — collapsing a lanes-only group to one member, +18 on today's queue — was
not ruled on and is not built; rule (c) stays refused.

**0. THE ≤ 1-YoE FLOOR — RULED (D-478 §5), PLANNED (D-479), ALL DECISIONS TAKEN (D-480).** D1 = T47
(per-user policy data). D2 = floor first, then arm the judge, both before run 4. D3 = above-band
stays hidden, no ticket. Reach confirmed for 2–3 y total bars, scoped bars > 1 y and 13–36-month
bars; hedged/preferred bars do not move. Nothing here is still owner-gated; it is execution.

**0-1. RETIRED / ANSWERED — held WHOLE in `STANDING-FACTS.md`.** Gate 1 is PER-SOURCE RECALL (D-421)
and only the per-source THRESHOLD is still owed; job-apps keeps running until it is met
(`RETIREMENT-PLAN.md`); Indeed's posture is decided (D-410, re-scoped by D-450). **Do not
re-litigate 80%, do not re-derive "most", do not re-probe Indeed.**

1. **PER-SOURCE THRESHOLDS — FULLY RULED (D-482 structure, D-505 the last two).** Employer-board
   sources ≥ 85%; **LinkedIn, Indeed and hiring.cafe: NO BAR** — a reach lane's recall against
   job-apps' ledger measures its OVERLAP with the system it exists to go beyond, so a bar there
   would mean job-apps runs forever. **Nothing is owed here any more.** M4's exit is the
   employer-board half alone and all four already clear it (greenhouse 97.2 / ashby 100 /
   workday 96.6 / lever 100, D-499); the only condition left is D-482's SECOND reading a week
   after D-499, owed **~2026-09-19**.
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
| **Run 9 (2026-09-06) tick-fired CLEAN on the restored five-lane config (D-487, read D-489); run 10 is the first whose funnel can reconcile a split slate (T60)** | The launchd job invokes the **editable** venv at `boardwatch/.venv/bin/boardwatch`, so whatever branch that tree is parked on IS the unattended run's code and `rules.yaml`. **Park the primary checkout on `main` before ending every session**; a stray branch changes EVERY subsequent run. The tick fired 06:00 CDT until the 09-09 reboot and **04:00 CDT since** — launchd keeps its boot zone, and the plist's hour is 4. Verify a tick by `runs = N` in `launchctl print` and the log mtime, never by the run row alone: a hand run proves the code, only a tick proves the plist | **Mit** (reboot); every session (discipline) |
