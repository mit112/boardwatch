# Run progress — say how much work a run has, how far along it is, and when it will finish

**Status: T286 built (2026-10-30, D-658); T287–T289 planned.** Written after run 713, the first run on the owner's MacBook Air,
ran 04:00 → ~23:00 and answered "how long, and how many résumés?" only through store queries, source reading and
`top`. A user who is not the maintainer has none of those.

## What a run shows today

`~/Library/Logs/boardwatch-run.log` gets one line per stage name (`scan`, `lanes`, `eligibility`, `gate`, `tailor
(projected)`) plus a few counters. Then nothing, for hours:

| run 713 stage | wall time | what the log said while it ran |
|---|---|---|
| scan | ~2 h | `scan`, `lanes` |
| eligibility (a full re-key after D-651) | ~5.9 h | `evaluating eligibility for 829413 postings…` |
| ranking | ~55 min (12 GB on an 8 GB machine) | nothing |
| gate | ~2 min | one summary line |
| tailor | ~10 h | `tailor (projected)` |

The run already MEASURES most of what a progress view needs, but only reports it when the run ends:
`stage_durations` and `stage_elapsed_seconds` in the funnel (D-343, SP2), `runs.started_at`, the per-lead
`artifacts` rows, and the slate size (`_slate_size` in `pipeline/runner.py`). The slate size is never printed: the
log says "26 beyond the delivered slate" but not how many are inside it.

## What decides the résumé count (the thing a user asks first)

`_slate_size`: the run delivers every decided-good (tier 0–1) post-gate survivor **up to `slate_ceiling`**, and
never fewer than `top_n`. The live config has `top_n` 40 (the daily driver's `--top 40`), `slate_ceiling` 100 and
`gate.depth` 150, so a good day builds 100. Time ≈ scan (fixed, ~2 h at 3,805 boards) + eligibility (scales with new
or changed postings, or with the whole corpus after an `engine_version` change) + ranking + slate × per-résumé time
(~3.4 min on the Mini, ~5 min on the Air).

## The plan, in build order

1. **T286 — announce each stage's size, then count it.** One line when a stage starts, with its unit count
   (`tailor: 100 résumés (100 decided-good, ceiling 100)`; `eligibility: 829,413 postings, full re-check because
   the rules changed`), then a progress line every N units or 60 s (`tailor 63/100 · Stripe · 4m12s · ETA 22:05`).
   The ETA uses this run's own pace for the stage, never a constant. No new measurement: the counters exist.
2. **T287 — a run-status record the web app can read while the run is live.** The runner writes a small status
   row (stage, done, total, started, ETA) at the same points as T286's lines. The single-writer rule holds, since
   the runner is the writer. The web app's `RunsPage` gets a "Tonight's run" panel: stage, progress bar, ETA,
   completed stages with their times. The web app is the only UI (owner, 2026-09-16), so this is the user-facing
   half.
3. **T288 — plain-language outcomes.** `notify/desktop.py` already exists. Send one message when the run ends
   ("100 résumés ready to review"), and one when it will be much longer than usual, with the reason ("the rules
   changed, so every saved posting is being re-checked: about 6 h extra").
4. **T289 — machine checks in `doctor`, in plain words.** Physical RAM against the measured ranking peak, the
   `mit` volume mounted, and background-permission (TCC) readiness for each binary a scheduled job runs through.
   Run 713's day had two silent failures here: Job apps' Stage 1 died on an unanswered Removable Volumes dialog for
   `gtimeout`, and ranking swapped 12 GB. Each finding says what to click or change.

**Not in this plan:** settings copy for non-maintainers ("build up to 100 résumés a night, about 5 min each on this
machine") belongs with v2's multi-user onboarding, which stays parked (D-598 ruling 4). T286–T289 are useful to the
owner today and are the parts any later user would also need.

## Sizing and risk

T286 is small and touches only console output in `pipeline/runner.py` and `eligibility/preflight.py`. T287 adds a
status write on the run path, so it needs its own review: a status write that fails must never fail the run
(fail-open, counted). T288 and T289 are independent of each other. None of them changes eligibility, ranking or
résumé content.
