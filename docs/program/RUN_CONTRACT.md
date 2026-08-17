# Run contract — fatal vs. non-fatal

**Read this to know whether an exit code or a `runs.status` value means the day actually failed.**
Origin: job-apps spec-3 §12, the "most scar-tissue-dense document in the handover" (PROGRAM.md §3.P3,
preamble). This is boardwatch's own version of that table, derived from the code below rather than
copied from job-apps — verify every row against the cited file and symbol before trusting it; a
stale contract is worse than none (CLAUDE.md). **No line numbers**: they drift on any edit above
them, and a citation that still resolves — to the wrong line — is worse than one that names only
the file and the symbol (this repo's own convention for prose, CLAUDE.md).

## The single discriminator

Every pipeline run (`boardwatch run`) produces one `PipelineSummary` with exactly one field that
decides success or failure: `fatal: str | None`
(`PipelineSummary`, `src/boardwatch/pipeline/runner.py`). Everything else — per-lead tailor
failures, per-board scan errors — lands in `summary.errors` and does not affect the verdict.

That one field drives both the persisted status and the process exit code:

- `finish_run(..., status=RUN_FAILED if summary.fatal is not None else RUN_OK)`
  (`run_pipeline`'s `finally`, `src/boardwatch/pipeline/runner.py`).
- `run_cmd.py` maps `summary.fatal is not None` to `typer.Exit(code=1)`
  (`src/boardwatch/cli/run_cmd.py`); a clean run falls through to exit 0.

## The five fatal conditions, plus the crash path

| # | Condition | Where it is set | Why it is fatal, not an error |
|---|---|---|---|
| 1 | **Systemic scan outage** — boards were attempted and not one completed or was left unchanged | `src/boardwatch/pipeline/runner.py`, predicate `is_systemic_scan_outage` in `src/boardwatch/scan/coordinator.py` | A DNS/network-wide failure, not a few dead slugs (Workday's normal `partial` outcome does not trip this). Reporting success here is exactly the silent empty day CLAUDE.md's fail-safe table exists to prevent. |
| 2 | **No profile configured** (`NoProfileError`, `src/boardwatch/cli/top_cmd.py`; raised inside `rank_open_postings` when `get_profile` returns nothing) | caught in `run_pipeline`'s eligibility stage, `src/boardwatch/pipeline/runner.py` | A fresh install has nothing to rank against; nothing downstream (tailoring) can run. |
| 3 | **Render tool unavailable** (`RenderToolMissingError`, `src/boardwatch/reports/resume_gate.py`) — the renderer is `tectonic`, and `pdfinfo` is equally required | caught around the `run_tailor` call in `src/boardwatch/pipeline/runner.py`'s tailor loop | An environment fault, not a per-lead one: the binary is either on `PATH` or it isn't, so every remaining lead in the shortlist would fail identically — the stage aborts rather than burning through the whole shortlist re-discovering that. |
| 4 | **Every lead failed to project or tailor** from a non-empty shortlist | `src/boardwatch/pipeline/runner.py`, after the tailor loop | Zero output was not provably right: it was produced from postings the ranker actually shortlisted, which means the résumé path itself is broken (missing `resume.yaml`, `tectonic` or `pdfinfo` gone) — or, under `--project`, that every lead's projection was refused, since `projection_failed_ids` counts into the same numerator — not an honest empty day. |
| 5 | **Projection requested and unavailable** — `--project` was passed (`src/boardwatch/cli/run_cmd.py`) and `resolve_projection_run` (`src/boardwatch/projection/run.py`) refused. The typed cause is `summary.projection_availability`, a member of the closed `ProjectionAvailability` catalog (`src/boardwatch/projection/run.py`) assigned by `classify_availability`; the `fatal` string carries the member's `value` and its remedy but nothing classifies by reading it | `src/boardwatch/pipeline/runner.py`, in the `if project:` preflight block, **before** the `rank_open_postings` call | Never a fallback to the authored résumé. A fallback *succeeds*, so every lead enters `summary.tailored`, `built_ids` is derived from exactly that set (`_record_shortlist_dispositions`), and each lead earns a permanent `built` the ledger suppresses on every later run — re-approving projection could not recover them. Refusing before anything is ranked is what keeps the retry a real drain: **no lead disposition is written**, so the next run re-surfaces the same shortlist. Remedy: `boardwatch profile-bundle approve-projection` after fixing what the member names, or drop `--project`. |
| — | **Crash path** — any other exception during the run | `run_pipeline`'s `except Exception` arm, `src/boardwatch/pipeline/runner.py`; sets `summary.fatal` before re-raising | Without this, a crashed run and a clean empty run would be indistinguishable in the ledger — the row would read as finished with no errors. The `finally` block still closes the row (see below), so `status == failed` and this file's FATAL line can never disagree. |

Terminal status is always written in a `finally`, whether the run returned normally or raised
(`run_pipeline`, `src/boardwatch/pipeline/runner.py`), so a run row is never left with a stale
status for a run that actually finished.

## The non-fatal norm

Per-lead tailor failures (`LeadArtifactError` and any other exception raised by `run_tailor`, caught
per lead in `src/boardwatch/pipeline/runner.py`'s tailor loop) and per-board scan errors (recorded
into `scan_summary.errors`, folded into `summary.errors` by the same module's scan stage) are
both **non-fatal**: recorded in `summary.errors`, the run still finishes `ok`, and the process still
exits 0. With 85 watched boards, a few dead ones are the documented norm — `boardwatch scan` already
treats them as success (`PipelineSummary`'s docstring, `src/boardwatch/pipeline/runner.py`), and
making the daily driver exit 1 every day for them would destroy the exit code as a signal
(`src/boardwatch/cli/run_cmd.py`).

## The lock-held case

If another scan already holds the file lock, `ScanLockHeldError` propagates out of `run_pipeline`
before any row is written — the INSERT lives inside the lock it failed to acquire (`run_scan`'s
`lock.acquire` precedes `_run_scan_locked`, `src/boardwatch/scan/coordinator.py`). `run_cmd.py`
catches it and exits **2**, printing `SCAN_LOCK_MESSAGE`, with **no run row created**
(`src/boardwatch/cli/run_cmd.py`). This is the one outcome that leaves nothing in `runs` at all —
every other path above produces exactly one row.

## Exit code summary

| Exit code | Meaning | Run row written? |
|---|---|---|
| 0 | Clean run, or a run with only non-fatal errors | yes, `status = ok` |
| 1 | One of the five fatal conditions, or a crash | yes, `status = failed` |
| 2 | Scan lock already held by another process | no |

## Known gap: `running` + NULL `finished_at` is ambiguous

`finish_run`'s docstring (`src/boardwatch/store/queries.py`) is explicit that a row left in
`running` with `finished_at` still `NULL` collapses three distinct situations into one signature:

1. a run genuinely still in flight,
2. a run killed by `SIGKILL` (no Python exception ever ran, so no `finally` fired),
3. a standalone lane (`reports/tailor.py`, `eligibility/preflight.py`, `cli/eligibility_cmd.py`) that
   raised between `ensure_run` and its own `finish_run` call — each calls `finish_run` on the success
   path only, with no `try/finally`.

This contract does not resolve that ambiguity; the column does not claim to. **Resolving it is P3
slice 2's run reaper** (PROGRAM.md §3.P3, decomposition slice "P3-lock-liveness" in
`.superpowers/sdd/p3-unattended-runner/design.md`), not this slice.
