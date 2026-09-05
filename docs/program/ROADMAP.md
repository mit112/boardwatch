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
| **B1–B7, 14 frozen days** (`PROGRAM.md` §1) | boardwatch WORKS unattended | provisional pass = 3 frozen clean runs, then a 14-day background confirm | **not started** — the freeze needs the merge first, and every `rules_hash` bump restarts it |
| **Gate 1, per-source recall** (`RETIREMENT-PLAN.md` §1) | boardwatch FINDS what job-apps finds | the owner sets a per-source threshold; job-apps runs until it is met | **28.8%** (5,838 / 20,289), thresholds NOT SET |

Applying is Mit's own work and is deliberately not chased by the program (D-351). The program's
job is to make the queue worth his morning.

## Where we actually are (2026-09-05, honest)

- **The machine is more correct than before the 09-03 reset, and faster.** Store, profile and
  fleet rebuilt; a 26-finding architecture review executed (24 tickets merged or gate-green);
  the warm scan 178 → 107 min, modelled 84 after T38; the résumé shell and projection approval
  rebuilt (T30–T32); a lost-board defect diagnosed to its real mechanism and fixed (T37).
- **The product numbers have not moved in that time, and that is the honest read.** Each run
  delivers 40 leads; **3 to 5 are in the apply lane**, the other ~35 need Mit's eyes (of the 80
  delivered so far: 39 experience-unconfirmed, 30 with no requirement rows, 6 role-unconfirmed).
  Gate 1 stands where it stood. Nothing built since the reset is merged, by Mit's ruling, so the
  04:00 tick still runs the pre-review code.
- **What the last four sessions bought is confidence, not yield**: three apparatus zeros caught,
  a 14–18% duplicate headline retired, a scan critical path found and re-ordered. Necessary —
  a queue nobody trusts is not a queue — but it is time not spent on the two bars above.
- **The owner-gated queue is the real backlog.** The merge, the projection re-approval and the
  formatting session, the per-source thresholds, the years-ruling propagation, LinkedIn Track 1,
  the fleet call, T40/T41 — every one is waiting on a sitting with Mit, not on engineering.

## The milestones, in order — each has an exit criterion you can read off the store

### M1 — Land what is built, and run it once. *(one sitting with Mit; days, not weeks)*
The merge of `close-2026-09-06` and the projection re-approval in one sitting (`STATE.md` §0),
then one `--project` run on the merged code, read against run 4 (the last pre-merge tick).
**Exit:** `main` moved; `boards_failed` 0; the smartrecruiters tail ≤ 3 min; T39's guard readable
in the funnel; the T36 rule applied (`HANDOFF-2026-09-07.md` §5). **Why first:** nothing after
this is measurable on unmerged code, and the tick runs whatever `main` is parked on.

### M2 — Close the store-contention class and freeze. *(one execution session)*
T40 (`apply_board` on the write lock) and, on Mit's word, T41 (one per-host pacing clock per
process). Then **stop changing eligibility, the profile and the résumé gate**, and let the
launchd cadence deliver the **provisional pass: 3 consecutive frozen clean runs**, each meeting
B1–B7 and P5b (≥ 30 considered, 0 preflight fatals, 0 résumé-QA failures). **Exit:** three such
runs in `METRICS.md`; the 14-day confirm starts passively. **Rule during the freeze:** a
`rules_hash` change restarts the count — so every eligibility change waits for M3's window or
is batched.

### M3 — Make the apply lane bigger than five. *(the product milestone; owner rulings + one build session)*
The queue is 40 a run and ~35 of those are "look at this yourself". The three buckets and the
lever on each, measured, not guessed:
- **Experience-unconfirmed (39 of 80).** The deterministic `near_miss_years_ceiling` abstains on
  the 2–3-year band across ~78,615 open `uncertain` postings — **the biggest undecided lever in
  the program**, and it is the owner's: he ruled "a stated bar is a bar" on 28 gate verdicts,
  and D-449 says a ruling is only as wide as the question put. **Ask it as its own question,
  with the blast radius on the page.**
- **No requirement rows (30 of 80).** A JD the engine read and found nothing to check. Measure
  first: how many are genuinely requirement-free postings versus extraction misses (chrome,
  page-config JSON, site boilerplate — the four delivery defects the gate judges found are the
  known shapes). The fix is on the extraction side, not the rules.
- **Role-unconfirmed (6 of 80).** Title taxonomy (the `ServiceNow Developer` question); small.
Plus **M1's other output**: T34/M1 says whether the LLM final gate catches anything in the apply
lane the split does not; if it does, it runs per run over the apply lane only (D-474 choice 4).
**Exit:** apply lane ≥ 10 per run on three consecutive runs, with the review lane's composition
in METRICS. **This restarts the freeze**, which is why it is after M2's provisional pass and
before the 14-day confirm is relied on.

### M4 — Find what job-apps finds. *(the retirement milestone; owner thresholds + the LinkedIn tracks)*
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
