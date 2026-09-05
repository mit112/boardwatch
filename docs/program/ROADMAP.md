# Roadmap — what boardwatch is driving toward, in order, and how each step is known to be done

**Written 2026-09-05 (session 2026-09-06b) at the owner's request: "are we making progress, what is
the goal for the time being, and a roadmap so we don't lose focus."** This file is the FOCUS view.
It does not replace `PROGRAM.md` (the bar and the phases), `RETIREMENT-PLAN.md` (the job-apps
switch-off condition) or `STATE.md` (where things stand today); it orders them into milestones
with exit criteria, and says what is deliberately NOT on the path. Rewrite it when a milestone
closes, not every session.

## The goal, in one line

**Every morning, one unattended command hands Mit a queue of live, deduplicated, profile-eligible
new-grad roles, each with a one-page tailored résumé PDF, and job-apps is switched off because
boardwatch finds what it found.** Two bars measure that, and they are different:

| bar | what it measures | where it is written | standing |
|---|---|---|---|
| **B1–B7, 14 frozen days** (`PROGRAM.md` §1) | boardwatch WORKS unattended | provisional pass = 3 frozen clean runs, then a 14-day background confirm | **0 of 3** — the count starts at run 6 (D-483; run 5 failed on a fixed integration defect); every `rules_hash` bump restarts it |
| **Gate 1, per-source recall** (`RETIREMENT-PLAN.md` §1) | boardwatch FINDS what job-apps finds | the owner sets a per-source threshold; job-apps runs until it is met | **28.8%** (5,838 / 20,289, pre-reset). Structure RULED (D-482): employer boards ≥ 85%, LinkedIn no bar; Indeed/hiring.cafe numbers at the first post-reset reading (~09-17) |

Applying is Mit's own work and is deliberately not chased by the program (D-351). The program's
job is to make the queue worth his morning.

## Where we actually are (2026-09-05, rewritten at M1's close — D-482)

- **Everything buildable on the path is built and on `main`.** M1 is DONE: `main` moved, runs 3
  and 4 ran the merged code, `boards_failed` 0. M2's build is DONE: T40 and T41 merged. M3's
  build is DONE: T42–T46 merged, T47 carries the ≤ 1-YoE floor as per-user policy and it is LIVE
  (`rules_hash` `033ea489f254`), the judge is ARMED on haiku, T50 reads its fenced output.
- **What has not happened is a scheduled run on that configuration.** Run 4 (hand-launched)
  showed the floor working — 4,254 hidden as ineligible — and the judge judging NOTHING (fixed,
  T50). No run in the post-reset store has been tick-fired on a valid configuration. **Run 5 at
  06:00 CDT on 2026-09-06 is the first counted run; the provisional pass is 0 of 3** — run 5 then FAILED on a T42 integration defect while the judge worked, fixed as T54/T55 (D-483); runs 6–8 are chained.
- **The product numbers: run 4 delivered 40 leads, all `eligible`**, against 3–5 apply-lane leads
  per run before T43/T45. The apply lane is CUMULATIVE 36; run-scoped apply/review is what run 5
  must report. The 33-of-120 "no requirement rows" class is displaced from the slate by verdict
  tiering and measured at the population (32,602, 33.9%) — T51, not before the third clean run.
- **The owner-gated queue is mostly CLEARED (D-480, D-482).** Left: the Indeed and hiring.cafe
  threshold numbers at the first post-reset reading (~2026-09-17), the reboot that moves the tick
  to 04:00, and the résumé calls.

## The milestones, in order — each has an exit criterion you can read off the store

### M1 — Land what is built, and run it once. **DONE 2026-09-05 (D-482).**
The merge of `close-2026-09-06` and the projection re-approval in one sitting (`STATE.md` §0),
then one `--project` run on the merged code, read against run 4 (the last pre-merge tick).
**Exit:** `main` moved; `boards_failed` 0; the smartrecruiters tail ≤ 3 min; T39's guard readable
in the funnel; the T36 rule applied (`HANDOFF-2026-09-07.md` §5). **Why first:** nothing after
this is measurable on unmerged code, and the tick runs whatever `main` is parked on.

### M2 — Close the store-contention class and freeze. **Build DONE (T40, T41 on `main`); the freeze holds from run 6; provisional pass 0 of 3 (D-483).**
T40 (`apply_board` on the write lock) and, on Mit's word, T41 (one per-host pacing clock per
process). Then **stop changing eligibility, the profile and the résumé gate**, and let the
launchd cadence deliver the **provisional pass: 3 consecutive frozen clean runs**, each meeting
B1–B7 and P5b (≥ 30 considered, 0 preflight fatals, 0 résumé-QA failures). **Exit:** three such
runs in `METRICS.md`; the 14-day confirm starts passively. **Rule during the freeze:** a
`rules_hash` change restarts the count — so every eligibility change waits for M3's window or
is batched.

### M3 — Make the apply lane bigger than five. **Build DONE and LIVE (T42–T47, T50); measured by the same runs as M2 (D-482).**
The 2026-09-08 session landed all five D-477 tickets (D-478). The shape of this milestone has
changed: the build is done and the open items are rulings.

**What landed.** T43 splits the lane BEFORE the tailor loop, so the render is spent on apply-lane
leads only and a review-lane lead is delivered pending-tailor. T45 tiers the shortlist by verdict.
T42 — the judge — is built, gated and **OFF by default**, fail-open at every seam. T46's B8
instrument is the funnel's `pdf` stage `entered`, now apply-lane-only, with its column on the
acceptance table. The judge model is **ruled haiku** (92.6% head-to-head, kappa 0.847, 2.04x
cheaper; METRICS `Session — 2026-09-08`).

**The biggest lever is RULED AND LIVE (T47 merged `2d677aed`, ceiling set, `rules_hash` `033ea489f254` — D-481).** The owner ruled on 2026-09-05 that the
experience bar's **floor must be <= 1 year** — `0`, `1`, `0-1`, `0-2`, `0-3` qualify, `2+` does
not. The engine already reads ranges by floor, so this is a threshold change, not a parser change.
But `near_miss_years_ceiling = 3` makes the engine ABSTAIN on exactly the 2-3 year bars now
rejected: **31-35% of the delivered slate**. The fix is **T47** (D-479): the ceiling becomes
per-user POLICY data beside `Policy.families`, never the bundled catalog and not a whole-file
`rules.yaml` override (which replaces the bundled file outright and has no drift detector). It
re-keys `rules_hash` once when the value is set (83,308 postings re-judged at the next preflight);
the ledger drain is declined (80 `built`, 0 `skipped`); no repo pin and no corpus row moves; the 91
month-stated bars turn over in the live store. **This is the M3 lever, and run 4 read it: 4,254
hidden as ineligible.**

**All three decisions are RULED (D-480, 2026-09-05): D1 = T47, D2 = floor first then arm, D3 = keep hidden. The two below are kept as the record of what was weighed:**
1. **Arm T42, or fix the band deterministically first?** Arming rejects the same 2-3 year bars at
   LLM cost every run; the override does it for free. They are not exclusive, but the order
   changes what run 4 reads.
2. **Should above-band leads be surfaced instead of hidden?** T44 routes `above_band` to review,
   but the ranker drops those leads upstream (`include_over_seniority` is never passed), so the
   rule cannot fire. Surfacing them raises delivered volume with postings currently withheld —
   possibly the wrong direction for an entry-band, <=1-YoE target. A guard test pins the current
   behaviour.

**Still open:** **no requirement rows — MEASURED (D-482):** 33 of 120 delivered, 0 of run 4's 40
(verdict tiering displaces them); 32,602 of 96,266 evaluations (33.9%) at the population, half
with a lexical cue, "N years … experience" phrasings 5.5%. Real detection gaps, ticketed **T51**
for this window. **Role-unconfirmed (6 of 80)** — title taxonomy, small, unchanged.

**Exit:** apply lane >= 10 per run on three consecutive runs, with the review lane's composition in
METRICS. **This restarts the freeze**, which is why it is after M2's provisional pass and before
the 14-day confirm is relied on. All five D-477 tickets restart the provisional-pass count, so the
count begins from run 6 (run 4 disqualified, D-482; run 5 failed, D-483).

### M4 — Find what job-apps finds. **Threshold STRUCTURE ruled and Track 1 CLOSED (D-482); the Indeed/hiring.cafe numbers are owed at the first post-reset reading (~2026-09-17).**
`RETIREMENT-PLAN.md` holds the finished analysis; do not re-derive it. In order: **set the
per-source thresholds** (owner; D-450 on the page); **Track 1** — the 108 already-admissible
LinkedIn boards, 113 postings on the gate-survivor basis, ~5.8 min per run forever (owner's
yes); the **Gate 1 re-measure due ~2026-09-09** (T35); then the remaining LinkedIn tracks per
`LINKEDIN-CLOSURE-PLAN.md`. The unreached 230 are 60.7% aggregator-only, 21.1% unsupported
employer host, 1.8% board-addable — **the gap is lanes, not boards**. **Exit:** every source at
or above its threshold on the re-measure script, two readings a week apart. Then job-apps is
switched off.

### M5 — The 14-day confirm, and calling it done.
The same B1–B7 bar, on true daily cadence, in the background, on a frozen system after M3.
**Exit:** 14 consecutive clean days in METRICS. Nothing new is built in this window.

## What is deliberately NOT on the path

Cover letters, outreach, auto-apply or any browser automation (`CLAUDE.md`); the tier-D lanes
(D-451); the refused-aggregator filter (D-463); the residual-zero chrome class (D-472); the
field-taxonomy gatherer (P2 item 8, deferred by Mit); scan speed beyond T36's rule (the scan is
not the bottleneck to any bar above once M1 lands). Speed work after M1 is a distraction unless a
bar says otherwise.

## How to use this file

At the top of a session: which milestone is open? Work only tickets that move its exit criterion
or the next one's. If a session's whole output is measurement apparatus, say so in the report
and say which exit criterion it protects. When a milestone closes, record it in `DECISIONS.md`
and rewrite this file's "where we are".
