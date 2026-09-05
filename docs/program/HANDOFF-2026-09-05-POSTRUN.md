# Handoff 2026-09-05 (post-run) — execution session → planning session (Fable) → next execution

Written by the execution session at ~00:10 CDT on 2026-09-05, **while run 3 is still in flight**.
Read `REPORT-2026-09-05.md` first — it is what this list is the remainder of. Reasoning for the
work already done: **D-471**. Reasoning for the original list: **D-470**.

## 0. The state of the tree, exactly

- **`main` is UNTOUCHED at `84671523`.** Nothing was merged, because the primary checkout runs the
  editable venv and run 3 must not have its code swapped underneath it.
- Branch **`close-2026-09-05`** carries three commits on top of `main`, in order:
  `1fc61596` (T31) → `d406a9f6` (T32) → the close commit (STATE / METRICS / D-471 / report / this
  file). **One `--ff-only` merge lands all three.** The full gate was run on the T31+T32 state
  (**exit 0, 9,462 passed**) and again on the close commit.
- Worktrees left in place: `../bw-t31`, `../bw-t32`, `../bw-close`. Delete after merging.
- Run 3 was launched manually at 22:39 CDT 2026-09-04 as
  `run --project --top 40` with `BOARDWATCH_HEARTBEAT_URL` and `BOARDWATCH_ALERT_URL` **unset**,
  so **the 04:00 tick still owns the heartbeat signal**. Log:
  `.agent/2026-09-05-session/run-manual.log`; exit sentinel `run-manual.exit`.

## 1. THE FIRST THREE THINGS, IN THIS ORDER — do not reorder them

1. **Wait for run 3.** `pgrep -fl "boardwatch run"` must find nothing. Do not merge, do not switch
   `main`'s branch, do not touch `{config_dir}` until it does.
2. **R1 — read run 3** (the readout the original handoff §1.1 specified, against run 3 rather than
   the tick). `.venv/bin/python .agent/2026-09-05-session/r1_readout.py 3` prints all of it: the
   run row, all eight `stage_durations` against run 2's pinned baseline, each lane's own scalars
   (SP2's `stage_elapsed_seconds` vs the residual `lanes` join wait), the verdict distribution at
   BOTH engine keys with the per-posting move count (T4 predicted 29), artifacts and dispositions.
   **The script carries its own null control: run against run 2 it reproduces the pinned baseline
   exactly** (scan 10,716.2 / lanes 363.8 / eligibility 665.5; 61,927 evaluations at
   ineligible 30,817 / uncertain 29,385 / eligible 1,725). Still owed by hand from the run log:
   renderer refusals (T10 `\href`, T2 template), T15 empty-complete guards, T13 `Retry-After`
   refusals, and the apply/review split.
3. **Merge, then Mit re-approves.**
   `git -C ~/dev/projectY/boardwatch merge --ff-only close-2026-09-05`. **T32 stales the
   projection approval** — Mit chose this explicitly at 23:26 on 09-04, on the condition that he
   re-approves before the next `--project` run:
   `boardwatch profile-bundle approve-projection` on a controlling TTY, review the screen (it now
   prints the header and education for the first time), type `approve`. **Until he does, any
   `--project` run scans in full and then refuses at the P5a preflight.**

## 2. What run 3 already tells you, so it is not re-derived

| | run 2 (cold) | run 3 (warm) |
|---|---|---|
| board scan | 10,716.2 s = 178.6 min | **283 of 288 boards in 79.3 min** |
| new posting_versions | 61,297 | ~20,024 at the 79-min mark |
| open postings after | 61,927 | 81,777 and still climbing |

The corpus GREW by ~20k, which is `detail_fetch_budget = 400` absorbing the backlog run 2 left
(run 2 finished with `boards_partial = 70`). Expect the eligibility stage to be larger than run
2's 665.5 s, not smaller, because the corpus it re-keys is bigger.

## 3. The carried tickets

### T28 — duplicate decomposition (read-only, S)
`.agent/2026-09-04e-session/t28_quad_decomposition.py`, unchanged, over run 3's delivered set.
**Null control: the probe must find the delivered count the funnel reports before grouping.** If
it is 0 groups again, record that as the reading — the 14-18% headline was a `--top 100`
measurement on a 95-lead shortlist. No identity change without a class table.

### T34 — M1: one gate pass, then the lane × verdict table (the judging is the cost)
`eligibility gate request` → the `eligibility-judge` skill, **two judges blind** → `gate apply` →
`.agent/2026-09-04e-session/m1_probe.py` unchanged. **Null control: the join must reproduce the
gate pass's own verdict totals before the lane column is added.** Output
`.agent/2026-09-05-session/m1.md` and the table into METRICS. **The planning session rules on the
cadence, not the execution session.** Note `eligibility gate request` is a default-context CLI
command and therefore a write path.

### T36 — `scan_workers`, and it now looks WEAKER than it did
Re-decide on run 3's own `stage_durations`, not run 2's. The warm scan is **2.25× faster at
`scan_workers` unchanged**, so the lever the original handoff called "the real one" may already
have been paid by the corpus warming up. Three facts the original spec did not have:
- `board_scans` cannot model this at all (report §2); only `funnel.scan.fetch_cost` can;
- `fetch_cost.seconds` double-counts same-host blocking, so **every projection from it is an
  upper bound on the saving**, not an estimate;
- **smartrecruiters is 24.0% of run 2's summed fetch cost on ONE host over 10 boards**, which no
  worker count can split.
If it still goes ahead: Mit's explicit OK in the transcript, never while a run is in flight, the
`config.toml.bak-*` convention the comment describes — **and correct the comment, which still
claims "8 is the schema's ceiling (`scan_workers` is `le=8`)" against `le=32` since SP1.**

### T35 — Gate 1 re-measure (D-424, due ~2026-09-09)
`.agent/2026-09-02-session/per_source_recall.py`. Standing 28.8% (5,838/20,289). Still gated on
the date.

## 4. The one open question this session produced

**T33's `residual_chars == 0` class — ship it or drop it?** The class the original spec authorised
is dead on inspection and that is settled. The residual-zero predicate is the survivor: **118
bodies / 0.193%**, 96 of them net new, 10 of 10 sampled are chrome, stable across a 24% corpus
change. It is **M, not S**, and the decision that governs everything else is: **may it be a
SWEEP-ONLY class?** It cannot run at the `extract_llm` ingest site — one body, no board — so
`require_employer_body`'s contract would stop being a complete statement of what holds a body. It
also needs the board grouping built into `drain_quarantine` as well as `sweep_bodies`, and an
ABSTAIN for the 695 bodies on boards with < 10 open postings (the keystone invariant: a rule that
cannot fire must be visible, not silently clearing). Full sizing and the ruled-out repairs:
`.agent/2026-09-05-session/t33.md`.

## 5. Still Mit's, untouched

`git push origin main` once the merge lands (`main` has not moved yet, so there is nothing to push
before it); `discover-candidates.yaml` (80 GitHub-list boards, D-291); the formatting session —
per-lens skills, the SAKEC/Nakshatra order, the `projection.{sde,ios}.yaml` drafts, **which should
be done in the same sitting as T32's re-approval, since both re-stale the stamp**; and the
owner-gated items unchanged in STATE (years-ruling propagation, the tier-aware Indeed cap,
per-source thresholds, Track 1 LinkedIn).
