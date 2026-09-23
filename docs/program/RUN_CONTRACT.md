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

## The thirteen places `summary.fatal` is set

**Enumerated from the code, not summarised from it.** `runner.py` holds **13** `summary.fatal`
assignments; this table has one row per assignment, in source order. It read *five* until
2026-09-20 and had been wrong for long enough that the count itself is the warning. **The count is
now a gate (T139):** `tests/pipeline/test_run_exit_contract.py` counts the STORES to `summary.fatal`
in `runner.py` through `ast` and fails `make check` when it stops matching this table's rows, and the
same module drives the real `boardwatch run` through each row below. Do not re-derive the count with
a text grep: `summary\.fatal\s*=` also matches a comparison (`summary.fatal == …`).

Two of the thirteen assign `str | None` and may decline — `_zero_output_guard` and `_cohort_guard`
are guards that fire only on a failed check, so reaching them is not the same as failing. The other
eleven set a string unconditionally once reached.

| # | Condition | Where it is set | Why it is fatal, not an error |
|---|---|---|---|
| 1 | **Systemic scan outage** — boards were attempted and not one returned any usable postings: none complete, none unchanged, **none even `partial`** | `src/boardwatch/pipeline/runner.py`, predicate `is_systemic_scan_outage` in `src/boardwatch/scan/coordinator.py` | A DNS/network-wide failure, not a few dead slugs. Reporting success here is exactly the silent empty day CLAUDE.md's fail-safe table exists to prevent. **A `partial`-only scan is NOT this** (owner ruling, 2026-09-20): a `partial` board holds real postings, so the run has usable evidence and is degraded success, reported by `notify/scan_health.degraded_scan_alert` on both callers. Until T130 the predicate ignored `partial`, so a one-board `partial` scan tripped it — five live runs (23/26/31/36/37) were wrongly stamped `failed`, each with an empty error list. |
| 2 | **Projection requested and unavailable — the preflight** — `--project` was passed (`src/boardwatch/cli/run_cmd.py`) and `resolve_projection_run` (`src/boardwatch/projection/run.py`) refused. The typed cause is `summary.projection_availability`, a member of the closed `ProjectionAvailability` catalog assigned by `classify_availability`; the `fatal` string carries the member's `value` and its remedy but nothing classifies by reading it | `src/boardwatch/pipeline/runner.py`, in the `if project:` preflight block, **before** the `rank_open_postings` call | Never a fallback to the authored résumé. A fallback *succeeds*, so every lead enters `summary.tailored`, `built_ids` is derived from exactly that set (`_record_shortlist_dispositions`), and each lead earns a permanent `built` the ledger suppresses on every later run — re-approving projection could not recover them. Refusing before anything is ranked is what keeps the retry a real drain: **no lead disposition is written**, so the next run re-surfaces the same shortlist. Remedy: `boardwatch profile-bundle approve-projection` after fixing what the member names, or drop `--project`. |
| 3 | **No profile configured** (`NoProfileError`, `src/boardwatch/cli/top_cmd.py`; raised inside `rank_open_postings` when `get_profile` returns nothing) | caught in `run_pipeline`'s eligibility stage, `src/boardwatch/pipeline/runner.py` | A fresh install has nothing to rank against; nothing downstream (tailoring) can run. |
| 4 | **Profile row unusable** (`ProfileRowInvalid`) — a stored profile column holds a document nothing can read | caught in `run_pipeline`'s eligibility stage, `src/boardwatch/pipeline/runner.py`, beside #3 and deliberately NOT the same shape | An empty `Policy` materialises the catalog defaults, where only `work_auth` is a `blocker` and the other five families fall back to `preference` — a severity that can never yield `ineligible` (D-P2-1). Continuing would clear postings the user's own policy rejects and report the run successful. Returning here also means no evaluation and no disposition is written under an identity computed from a policy nobody can read. |
| 5 | **Projection unavailable — inside the tailor loop**, where `_projection_scope` classifies the raised error as a run-invariant `ProjectionAvailability` rather than a per-lead fault | `src/boardwatch/pipeline/runner.py`, the tailor loop's projection arm | Run-invariant: every remaining lead would fail identically, so the stage stops exactly as it does for a missing render tool. Recorded as the RUN's verdict and as `fatal`, **never as a lead outcome** — counting it per-lead would grant the leads after it a disposition under a run-wide fault, the one mistake a total table cannot prevent by itself. |
| 6 | **Render tool or template artifact unavailable** — `(RenderToolMissingError, TemplateArtifactError)`, `src/boardwatch/reports/resume_gate.py`. The renderer is `tectonic`, and `pdfinfo` is equally required. **Both** exceptions land here; naming only the first was part of this table's drift | caught around the `run_tailor` call in `src/boardwatch/pipeline/runner.py`'s tailor loop | An environment or authoring fault, not a per-lead one: the binary is either on `PATH` or it isn't and the template is either readable or it isn't, so every remaining lead would fail identically — the stage aborts rather than burning through the whole shortlist re-discovering that. |
| 7 | **Master résumé invalid** (`ResumeLoadError`) — a malformed or genuinely-broken master résumé (P4 item 5b: a bad contact block, a leftover template artifact) | `src/boardwatch/pipeline/runner.py`'s tailor loop | `load_resume()` re-validates on every call, so every remaining lead would fail identically. Abort the stage rather than rediscovering that lead by lead, exactly like #6. |
| 8 | **Persona registry invalid** (`PersonaError`) — a malformed bundled or `{config_dir}` persona registry | `src/boardwatch/pipeline/runner.py`'s tailor loop | A configuration fault, not a per-lead one — `load_personas()` re-validates on every call. Fail the run loudly rather than silently degrading each lead, exactly like #6 and #7. |
| 9 | **Every lead failed to project or tailor** from a non-empty shortlist | `src/boardwatch/pipeline/runner.py`, after the tailor loop | Zero output was not provably right: it was produced from postings the ranker actually shortlisted, which means the résumé path itself is broken (missing `resume.yaml`, `tectonic` or `pdfinfo` gone) — or, under `--project`, that every lead's projection was refused, since `projection_failed_ids` counts into the same numerator — not an honest empty day. |
| 10 | **Zero-output guard** — `_zero_output_guard`, `src/boardwatch/pipeline/runner.py`. Returns `str \| None`: **may decline** | after #9, reachable when `renderable == 0` | 0 leads is provably right IFF every candidate judged THIS run was either delivered or honestly suppressed (already built/skipped/duplicate/dead). Anything left over is a silent empty day wearing an honest one's clothes. Checked BEFORE #11 so the more specific empty-day message wins when both would fire. |
| 11 | **Cohort completeness** — `_cohort_guard`, `src/boardwatch/pipeline/runner.py`. Returns `str \| None`: **may decline** | after #10 | P3 item 9 — every SHORTLISTED candidate must reach a terminal state: a lead or a tailor failure. The unaccounted set is `visible_ids - (lead_ids \| failed_ids)`, with dead, projection-failed, gate-excluded and beyond-slate ids already subtracted from `visible_ids`. |
| 12 | **Filesystem-truth** — the leads the store says this run produced must have a folder on disk (`folders_reconcile`, `src/boardwatch/pipeline/freshness.py`) | `src/boardwatch/pipeline/runner.py`, after #11, guarded by `summary.fatal is None` | P3 item 6. Reuses slice 4's reconciliation rather than a second implementation; only the folder/artifact-row clause, since neither `funnel_present` nor `status` has been written yet at this point in the run. |
| 13 | **Crash path** — any exception during the run, caught by **`except BaseException`** (NOT `except Exception`, which is what this table claimed until 2026-09-20) | `run_pipeline`'s `except BaseException` arm, `src/boardwatch/pipeline/runner.py`; sets `summary.fatal` only `if summary.fatal is None`, then re-raises | Without this, a crashed run and a clean empty run would be indistinguishable in the ledger — the row would read as finished with no errors. **`BaseException` rather than `Exception` is load-bearing**: `KeyboardInterrupt` and `SystemExit` do not derive from `Exception`, so a Ctrl-C or a `sys.exit` mid-run would otherwise skip the recording and leave the run row with no reason. The `finally` block still closes the row (see below), so `status == failed` and this file's FATAL line can never disagree. |

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

If another process holds the scan lease, `ScanLockHeldError` propagates out of `run_pipeline`
before anything is written. **Since T133 the lease covers the WHOLE run**, so the holder may be a
standalone `scan` or another `run` in any stage, including its finalize: `run_pipeline` takes
`scan_lease` (`src/boardwatch/scan/coordinator.py`, the one acquisition site) before the stale-run
reap, the schema step and the run row, with `--no-scan` too. `run_cmd.py` catches it and exits
**2**, printing `SCAN_LOCK_MESSAGE`, with **no run row created and no row reaped**
(`src/boardwatch/cli/run_cmd.py`). This is the one outcome that leaves nothing in `runs` at all —
every other path above produces exactly one row.

## Exit code summary

| Exit code | Meaning | Run row written? |
|---|---|---|
| 0 | Clean run, or a run with only non-fatal errors | yes, `status = ok` |
| 1 | Any of the twelve fatal conditions above, or the crash path on an exception | yes, `status = failed` |
| 2 | Scan lease already held by another process (a scan, or a run in any stage) | no |
| 130 | Ctrl-C (`KeyboardInterrupt`) during the run: the crash path closes the row with its reason and the raise propagates; the CLI framework maps it to 130 | yes, `status = failed` |

Every row of this table is driven through the real CLI by `tests/pipeline/test_run_exit_contract.py`.

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
