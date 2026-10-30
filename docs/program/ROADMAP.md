# Roadmap — what "complete" means, how it is measured, and what is deliberately off the path

**Finish line retired 2026-10-29 (D-652): there is no freeze and no 14-day count; the bars below are read every day as a
health check.** **Rewritten 2026-09-25b (D-598)** at the owner's request — "get me to a state where you can confidently say, yes this is a
complete product" — after all five milestones of the 2026-09-05 roadmap had closed and its end state ("job-apps is switched
off") had been retired by D-566 §4. The 2026-09-05 version is in `archive/ROADMAP-2026-09-05.md`. This file is the FOCUS
view: `PROGRAM.md` holds the bars, `STATE.md` where things stand today. Rewrite it only when the finish line moves.

## The goal, in one line

**Every morning, one unattended command hands the owner a queue of live, deduplicated, profile-eligible new-grad roles,
each with a one-page tailored résumé PDF, meeting every bar.**
job-apps stays on as an upstream source (D-566 §4); boardwatch is the one queue the owner reads.

## The daily bars (D-598; the finish line retired by D-652)

Each scheduled run is scored against bars **B1–B8** (`PROGRAM.md` §1). A failing bar is a defect to fix; there is no
streak to keep and no count to restart (D-652):

| # | bar | how it is read each day | reading at D-598 (2026-09-26b) |
|---|---|---|---|
| B1 | ≥ 10 net-new eligible, live, deduped leads | funnel `leads` whose job the run decided FIRST (`day_row.py`; D-600 — the bare count includes drain re-deliveries) | **8 (478), 1 (480)** of 40; 40 on 474, before the drain |
| B2 | 100% of apply-lane leads have a PDF | funnel `pdf` advanced / entered | 100% |
| B3 | 100% pass the résumé QA gate | `tailor_failed` 0, one page | 100% |
| B4 | 0 fabrications, independently read, n ≥ 100 | every delivered PDF read back and matched to the approved bundle | **0 on 177**; 0 on all 157 PDFs of 2026-09-26 |
| B5 | 0 silent empty days | status ok, no fatal, leads > 0 | 0 |
| B6 | 100% funnel reconciliation | funnel `reconciles` | met on 476/477 |
| B7 | work authorization decided, never abstained | `us_authorization_required` abstain % | 0% |
| B8 | ≥ 20 apply-lane leads/day **and** ≤ 16% unapplyable | NET-NEW apply-lane placements (D-600); a census of each run's placements judged by **two opus judges**, pooled to n ≥ 100 | 8 (478), 1 (480) net-new; **5.6% on 125 (Wilson 3–11), opus census of runs 476–480 — closed** |

**No freeze (D-652, retiring D-598 ruling 5).** Any change may ship on its own review; a change to eligibility, the
profile or the résumé gate no longer restarts anything. The frozen-day count ran from the **2026-09-27 04:00 run**
(D-600) to 2026-10-29 and never reached 14. Each daily row goes in the maintainer's private `RUNS.md` (D-646);
`METRICS.md` holds the rows through run 680.

## Milestones

- **M1 — land what is built and run it once.** DONE 2026-09-05 (D-482).
- **M2 — close the store-contention class, provisional pass.** DONE, runs 6–8 (D-483).
- **M3 — an apply lane bigger than five.** DONE; 25–36 apply-lane leads per run on the 1,807+ board fleet.
- **M4 — find what job-apps finds.** Gate 1 per-source recall met, 100% for each employer-board source (D-521, re-read
  2026-09-25); the switch-off it was for is retired (D-566 §4, D-598).
- **M5 — the 14-day confirm of B1–B7.** DONE at run 447 (D-521 §5).
- **M6 — B8, and all eight bars together, for 14 frozen days.** RETIRED 2026-10-29 (D-652); the bars are read daily.

## What is deliberately NOT on the path

- **More eligibility-engine batches.** Batches 7–10 changed 880 verdicts and none of those postings was ever delivered;
  the slate cap binds (D-532), and every batch restarted the 14 days. Parked: T239, T240, T241c, T242, T244, T249 (D-598).
- **Discovery / coverage work** (new lanes, boards, LinkedIn tracks): the slate cap binds (D-532); read
  `RETIREMENT-PLAN.md` and `LINKEDIN-CLOSURE-PLAN.md` before proposing any.
- **v2 — parked on purpose (D-598 ruling 4):** multi-user eligibility (field-dependent rules as data, so a non-software user
  needs no code), a real second user, a public release beyond the version cut, community launch, the v2 decision doc's
  product metrics (setup time, review time, retention).
- Cover letters, outreach, auto-apply or any browser automation (`CLAUDE.md`).

## In scope, small, not a bar

- An accurate README and user docs (done 2026-09-28c, D-607; the 25b pass had fixed two lines), the numbers recorded
  (METRICS), the v0.6.0 version cut (T255 — published 2026-09-28c on the owner's confirmation, D-607).
- Keep the run healthy: the seat stays quiet from ~03:00 through a run's gate stage (T247 ruling); Windows is best-effort
  (T251).

## How to use this file

At the top of a session: is M6 still counting? If yes, read the latest run against the table and record the day. Work only
on a defect a delivered lead proved, or on the run's health. If a session's output is anything else, say which bar it
protects — or park it.
