# Tickets from astra review 04 (the runner, the store, concurrency) — verified, measured, ranked

Source: `.agent/astra/findings/04-runner-store-concurrency.md` (gitignored; written at checkout
`5040bc4a`, 2026-09-20). Consumed per D-526 against `main` `663dd3cf`.

**How this was verified.** The falsifier (`.agent/astra/scratch/test_04_runner_contract.py`) was
re-run by the orchestrating session at `663dd3cf` — **7 passed, every printed line byte for byte**.
Every `file:symbol` was opened by a read-only Opus verifier on the enterprise seat
(`.agent/astra/verify/04-report.md`, 120 turns, $10.75). **All ten findings CONFIRMED; F9 PARTIAL;
nothing refuted.** The verifier read `main`, not astra's checkout: `runner.py` had moved ~37 lines,
but `run_pipeline`'s guards and `_sync_queue` are byte-identical.

One PR per ticket, one worktree per PR, `make check` per PR. **Every ticket's acceptance test must
FAIL against the current code before the fix is counted.**

**Re-key rule.** NOTHING in review 04 touches the four digested engine modules or `rules.yaml`.
**No ticket here moves `engine_version`, `rules_hash` or `profile_hash`, none owes a ledger drain,
and none restarts a confirm clock.** What moves is run bookkeeping, scan classification, one
notification gate and one error-classification predicate.

## The measurement that reorders this list

Read-only against the live store (`sqlite3 ?mode=ro`), each probe with a control. **The severity
ranking inverts, for the second review running (cf. D-525).**

| finding | astra | live instances | the control that makes it a result |
|---|---|---|---|
| F1 pipelines not serialized | wrong-now | **0** of 468 runs | +1 h on each end ⇒ 37,238 pairs, so the probe can see an overlap |
| F2 deferred RMW snapshot | wrong-now | **0** BUSY_SNAPSHOT in run errors; 1 `database is locked` cost a board (run 3); 19 pipeline×CLI windows | full error taxonomy over 468 runs |
| F3 queue sync reverses an action | wrong-now | **0** — `app_state` holds 0 rows | independently matches D-525's F4 |
| F4 all-judge-rejection false fatal | wrong-now | **0** runs carry the string | reproduced in test with an `eligible` control arm |
| F5 heartbeat without durable finish | wrong-now | **2** (runs 310/312, `running` for 35.2 h) | 468 rows did finish |
| F6 manifest a late observation | design-limit | **0** mid-run drift over 27 corpus runs | `rules_hash` has 4 distinct values historically |
| F7 folder reconcile predicate | design-limit | **0** — 1,396/1,396 `.tex` present, 0 intra-run shared parents | the 494 PDF-less folders are all `pending_tailor` stubs, which need none |
| F8 reaper vs a live run | design-limit | **2** correct reaps; D-046's "minutes, not hours" is **false** (14 runs > 60 min, max 35 h) | default 24 h ⇒ no exposure; the `ge=1` floor is |
| F9 editable checkout | design-limit | n/a | **lowered** — `_init_worker` already raises on identity mismatch |
| **F10 partial-only scan is fatal** | **improvement** | **5** (runs 23/26/31/36/37) | **0 of 70 scanning runs ever had zero usable evidence — the predicate has NEVER fired on a real outage** |

**Two apparatus corrections, both caught before the number was used.** The overlap probe first read
**259**; p50 run duration is 0.0 min because **396 of 468 run rows are CLI invocations, not
pipelines**, and restricted to pipeline-shaped rows it is **0**. A delivered-unapplied query
returned a clean 0 because **`artifacts.job_id` is NULL on all 1,396 `resume_tailored` rows** —
artifacts are attributed by `posting_version_id`/`run_id`.

## What the verifier found that astra did not

1. **A wrong-now bug filed under "Checked and sound."** Astra wrote that `server._write` "retries
   the complete transaction and returns an explicit 503." True for codes 5/6 — **false for
   `SQLITE_BUSY_SNAPSHOT` (517)**, which carries the same `database is locked` message. Shipped as
   **T132**.
2. **F4's fix must intersect, or it raises.** `gate_excluded_ids` is run-scoped but is *not* a
   subset of `judged_this_run_ids` (a posting can be gate-judged this run off a deterministic
   evaluation written in an earlier one). Subtracting the raw count underflows and raises
   `ZeroOutputReconciliationError` instead of clearing. Load-bearing for **T131**.
3. **F5's blast radius is wider than stated:** 13 unguarded `append_run_error` calls in the
   `finally`, **four in blocks with no `try` at all** (2924, 3024, 3048, 3076).
4. **The repo already documented F4 and worked around it** — `tests/pipeline/test_gate_stage.py:251-257`
   gave the test a second lead to dodge the path.
5. **F2's mechanism is already pinned** by `tests/pipeline/test_two_writer_concurrency.py:90` and
   `:153`. The review prompt's claim that no such test exists was stale.
6. **F1: `WAL_DISCIPLINE.md` contradicts itself** — item 1 (17-20) is right, line 30 is wrong.
7. **F8: no test pins D-020's "writes nothing at all"** — the existing one asserts only row COUNT.
8. **F10: 13 `summary.fatal` assignments** against RUN_CONTRACT's five-row table.

## Shipped — one gated wave, `make check` exit 0, 10,498 passed (baseline 10,470), 9m51s, 95.23%

| # | ticket | finding | size | moves |
|---|---|---|---|---|
| **T129 SHIPPED** | durable terminal status gates the heartbeat; the failure note escalates; four untried alert blocks guarded | F5 | M | run bookkeeping + one notification gate |
| **T130 SHIPPED** | a partial-only scan is degraded, not a systemic outage | F10 / ruling 1 | S-M | scan classification + one soft alert |
| **T132 SHIPPED** | the web write path's retry recognises `SQLITE_BUSY_SNAPSHOT` | F2 (web half) | S | one error-classification predicate |

**T130 shipped incomplete and only the live measurement showed it.** Its degraded alert lived in
`run_pipeline`; **all five live instances were standalone `boardwatch scan` calls**
(`corpus_evaluated IS NULL`, two ingesting 879 and 344 postings), so as shipped it converted the
measured population from `failed`-with-a-reason into **`ok`-with-nothing**. No test could catch it:
both callers agree on *status*, which is what D-037 demands and what the parity test pins, and
alert parity is not something this repo has for any soft detector. Fixed in `_scan_body`, gated on
`finish`. **Nothing pinned the non-duplication invariant** — with the gate relaxed to `else:`, 136
tests passed and none saw the duplicate, because the assertion was `any(...)`.

## Ticketed, not built

| # | ticket | finding | size | why not now |
|---|---|---|---|---|
| **T131** | the zero-output guard gains a judge-rejection explainer, **intersected with `judged_this_run_ids`** | F4 | S-M | correctness fix on a guard with **0** live instances in 468 runs; the seat was low. Ready to dispatch — `.agent/executor/T131.md` is written |
| **T133** | a whole-run lease covering `--no-scan`, rejecting a contender before any write; fix `WAL_DISCIPLINE.md:30` | F1 | L | **0** live instances, but the store cannot see PEER SESSIONS, which is the real exposure — needs an argument the store cannot supply |
| **T134** | ~18 DEFERRED read-modify-writes with no retry; make `finish_run`'s append atomic (`json_insert`, as `append_run_error` already is); end the form sweep's read txn BEFORE HTTP | F2 | L | broad; the verifier's census names five writers astra omitted: `extract/preflight.py:40`, `death_probe.py:481`, `identities_cmd.py:45/76/122`, `postings_cmd.py:77`, `track_cmd.py:67/103` |
| **T135** | take the queue lock before establishing the read snapshot; one snapshot per filesystem plan | F3 | M | **0** live instances (`app_state` empty). Note T116 **lengthened** this window |
| **T136** | `reap_stale_after_hours` permits `ge=1` while 12 of 14 real pipeline runs exceed 60 min; add the test D-020's stronger claim never got | F8 | S-M | no exposure at the 24 h default; revisit D-046's premise on the measured durations |
| **T137** | a frozen `RunContext` + separate execution provenance (release SHA, gate prompt fingerprint, armed lanes, fleet count) | F6 | L | **0** live drift; keep D-524's T111 lane fingerprint separate |
| **T138** | reuse `reports/reconcile.py`'s per-file checks in the run guard; check required files by artifact kind | F7 | M | **0** live instances; review stubs legitimately need no PDF |
| **T139** | the stage extraction — **and FIRST correct `RUN_CONTRACT.md` to the 13 real fatal causes and `except BaseException`** | F10 | XL | refactoring against the stale five-row table would change semantics silently |

**F9 is not a ticket.** It is a deployment question (a non-editable wheel in a versioned release
venv), lowered in severity by `_init_worker`'s identity refusal, and it is the owner's call.

## Known unpinned assumption

`_finish_run_with_one_retry`'s docstring asserts "the attempt that raised committed nothing", but
the test's fake raises *before* calling through, so the commit-then-raise path is untested. If the
assumption were wrong, `errors_json` would gain a duplicated append. Low likelihood under SQLite's
transaction semantics; recorded rather than left silent.

## Corrected here

`RUN_CONTRACT.md`'s fatal row 1 — T130 made it wrong in both clauses (the condition, and a
parenthetical claiming Workday's `partial` does not trip it, which was backwards: a partial-only
scan was the only thing that ever did). The table's wider drift — **five** documented conditions
against **13** in code, and `except Exception` against `BaseException` — is **T139's**.

## Owner rulings (Mit, 2026-09-20), both priced before asking

1. **A partial-only scan is degraded, not fatal.** Fatal is reserved for zero usable evidence.
   Priced first: 5 live instances, and **0 of 70 scanning runs were ever a true outage**.
2. **Delivery-queue publication is NOT a run-success condition.** Queue failure stays non-fatal and
   does not withhold the heartbeat. Priced first: **0 queue/delivery failures across 468 runs**.
   This bounds T129.
