# Projection inside `boardwatch run` — slice P5 design

**Date:** 2026-08-17 · **Status:** awaiting owner review
**Implements:** slice **P5** of `2026-08-13-career-profile-projection-design.md` §10, and that design's
**§12 Q1** (ruled by Mit 2026-08-13: *"what is settled is that it happens; what is open is its form"*).
**Owns:** §4.2's stale-lineage gap and §12 Q2 (manifest validation).

---

## 1. Why this slice, now

The bundle → résumé track is v1-complete: Stage 1 and Stage 2 both work, all eleven entities' bullets are
refined, Gate B is MET, and the pool renders one page with zero overfull. None of it reaches an unattended
run. Measured, not recalled:

- `rg 'projection|profile_bundle|project_pool' src/boardwatch/pipeline/` returns **zero hits**. The whole
  subsystem is reachable only from `cli/projection_cmd.py` and `cli/profile_bundle_cmd.py`.
- `pipeline/runner.py:522` calls `run_tailor(..., resume_path=resume_path)`, and `run_cmd.py:80` sets that
  to `settings.config_dir / "resume.yaml"`. `run_tailor` reaches `load_resume(Path(resume_path))`
  (`reports/tailor.py:410`).

So the résumé an unattended run produces is **not** the résumé eleven sessions of bullet work produced.
That is this slice's entire justification.

## 2. Decisions adopted, and their standing

Mit was away when this was written, so the two shape-determining questions were answered by assumption and
are flagged for review. Both follow the recommendation given at the time.

**A1 — Form: opt-in `boardwatch run --project`.** `resume.yaml` stays the unattended default.
§8's migration order is explicit — *"`resume.yaml` must remain the pipeline default until projection is
proven on real JDs"* — and hand-running one posting at a time is not that proof. The flag makes the
projected path runnable unattended so the evidence can accumulate; flipping the default is a separate,
smaller change gated on that evidence. **Rejected:** projection as the default stage (flips before the
proof condition is met), and an auto-flip on a metric (invents a criterion nobody has argued for).

**A2 — Fail direction: never fatal for the run; always fall back; distinguish the two causes by
severity, not by behaviour.** `CLAUDE.md` fixes the fail-safe direction per gate, and the fabrication-check
direction is *drop tailoring, emit static*. Projection failure therefore never emits a partial projected
document and never aborts the run; the lead renders from the authored `resume.yaml` path instead. What
differs is how loudly it is reported:

| Cause | Behaviour | Severity |
|---|---|---|
| Stamp missing or stale (`bundle_digest` moved) | fall back | **routine** — every promotion causes it |
| `projection.yaml` absent | fall back | **routine** — the user has not opted into a declaration |
| §7 fidelity violation | fall back | **fault** — signals a broken declaration/bundle relation |

**Why §8's "fatal, uniformly" does not transfer unmodified.** §8 rests on *"Refusing costs nothing —
`resume.yaml` still works and job-apps delivers the owner's daily minimum."* Inside `boardwatch run` the
first clause weakens: refusing costs that run's leads. It does not vanish, because the authored path
genuinely does still render — `build_plan` caps at `MAX_BULLETS_PER_ENTRY = 6` (`plan.py:48`) and trims the
master, which is why 46 `resume_tailored` artifacts exist against a 6,134-char master under a live
`resume_max_pages=1`. So fallback is real, and fatality is unnecessary.

## 3. What forces the design

**The approval gate cannot be satisfied unattended, by construction.** `ProjectionStamp.approved_via` is
`Literal["controlling_terminal"]` with no parameter (`stamp.py:62`, `:100-102`), and `project_pool` reads
the stamp back and compares `bundle_digest` **unconditionally** (D-167, `pool.py:131-136`). A 07:00 run
cannot ask Mit anything. Therefore:

> **The projection stage never writes a stamp, and no non-TTY approval path is added — not now, not
> behind a flag.** A stale stamp is a routine fallback, not an obstacle to route around.

This is the load-bearing constraint. It also means a stale stamp is the *expected steady state* after every
promotion, which is why it must be a counted, drained outcome rather than an error.

## 4. Architecture

Three insertion points in `pipeline/runner.py`, and nothing outside it changes shape.

**4.1 One pool per run, resolved once.** Stage 1 is JD-blind, so it is resolved a single time before the
tailor loop, with `as_of` fixed at run start:

```
project_pool(bundle_root, declaration_path, config_dir=settings.config_dir, as_of=run_started_date)
```

Resolving once is a correctness requirement, not an optimisation: a promotion landing mid-run would
otherwise split one day's leads across two bundle revisions, and the manifest lineage would be honest about
each lead while the *day* became unreconcilable. Every refusal from this call is caught here, classified per
§2's table, counted once, and the run continues on the authored path.

**4.2 Per-lead Stage 2 — extracted, not reimplemented.** The sequence the pipeline needs already exists in
full at `cli/projection_cmd.py:443-530`: `project_pool` → `posting_context` → `select` (with a
`compile_prefix` closure that compiles into a scratch dir to gauge page count) → per-candidate scores →
`ProjectionManifest` → write `resume.projected.yaml` and `projection-manifest.json`.

It is not callable from the pipeline as written, because `typer.echo` and `raise typer.Exit(code=1)` are
interleaved through it (`:450`, `:488`, `:532-538`) and it reaches into `reports.tailor._default_runner`, a
private symbol.

**So this slice extracts that body into one reusable function** — `project_for_posting(...)` in a new
`src/boardwatch/projection/run.py` — returning a typed result (the selection, the manifest, and the two
documents' bytes) and **raising** typed `ProjectionError`/`ProfileBundleError` rather than echoing and
exiting. `resume project` becomes a thin caller that formats and sets exit codes; the pipeline becomes the
second caller. This is what makes invariant 5 structural rather than aspirational, and it is the targeted
improvement to code this slice is already working in — not unrelated refactoring.

For each lead the pipeline then calls that function, writes both files into the lead's existing destination
directory, and calls the unchanged `run_tailor(resume_path=<the projected document>)`. `run_tailor` needs no
change — the projected document is *"exactly the shape `tailor/load.py` reads"* (§4.2 of the parent design).

**A named, accepted cost.** `select`'s `_grow` admits candidates one at a time and calls `compile_prefix` on
each attempt, so a lead costs up to one tectonic compile per candidate — with eight candidates and ten
leads, on the order of eighty compiles per run. Unattended runs are not latency-sensitive and this is in
family with the existing gate's own runtime, so it is accepted rather than optimised; what is owed is a
**measurement recorded in `METRICS.md` on the first real projected run**, so the number is known rather than
assumed. If it proves material, the pool is JD-blind and the pinned prefix is identical across leads, which
is where a cache would go — but not before it is measured.

**4.3 Manifest validation and artifact lineage — the slice's owned deliverable.** Today the sidecar makes
staleness *inspectable*, not *detected*: project revision A, promote B, render, and the stale document
renders while the artifact cannot name its revision. Closing it:

- **Before render:** assert the manifest's `bundle_digest` and `projection_digest` equal what §4.1
  resolved. A mismatch is a fault-severity refusal for that lead, not a warning.
- **After render:** copy `bundle_revision`, `bundle_digest`, `projection_digest` and `manifest_schema` into
  the artifact metadata written near `reports/tailor.py:685-708`, so an artifact row names the revision it
  came from.

This is the shape §4.2 predicted — the pipeline already knows the store, the posting and the artifact
ledger, so it crosses no wall that `tailor` would have had to.

**4.4 Counters and the drain.** A closed outcome catalog — `projected`, `skipped_no_declaration`,
`skipped_stale_stamp`, `skipped_fidelity_fault` — counted in the funnel artifact, with an unrecognised
outcome a failure rather than a new bucket. The morning artifact names the outcome **and its remedy**
(`approve-projection` for a stale stamp). That naming is the drain the quarantine rule requires; without it
a projection that silently stops projecting looks identical to one that was never enabled.

## 5. Invariants this slice must not break

1. No non-TTY approval path, ever (§3).
2. One bundle revision per run (§4.1).
3. Never emit a partial projected document; prefer the authored static path (§2, A2).
4. Never abort the run for a projection cause (§2, A2).
5. No second implementation of pool assembly — the pipeline calls the same `project_pool` the CLI calls.

## 6. Testing

Following §9's discipline, with each test confirmed to fail without its fix and naming *which* assertion
trips (D-148), and expectations derived from the bundle at run time rather than hardcoded (D-142/D-149).

- **Each §2 cause:** stale stamp, absent declaration, and a §7 violation each fall back, each increments
  its own counter, and the run's exit status is unaffected.
- **Fault vs routine is visible:** a §7 violation and a stale stamp are distinguishable in the funnel, not
  folded together.
- **Lineage:** a rendered projected lead's artifact row names its bundle revision. This is the gate clause
  "a stale manifest is detected, not merely inspectable", so it gets a mismatch test too — a manifest whose
  digest disagrees refuses that lead.
- **One revision per run:** a promotion simulated between two leads does not change the second lead's pool.
- **No second implementation:** the pipeline's pool and `profile-bundle project`'s pool are identical for
  identical inputs.
- **The extraction is a no-op for the CLI.** `resume project`'s existing tests must pass **unedited** against
  the extracted `project_for_posting`, including its two typed-refusal arms (`:445` stamp/pool refusal,
  `:477` `TemplateArtifactError` from a bad user template) and its stdout contract. An extraction that
  quietly changes an exit code or drops a refusal arm is the defect most likely to hide here, and the
  suite that covers it must not be the suite that is edited to accommodate it.
- **Negative control:** with `--project` absent, behaviour is byte-identical to today. This is the test
  that protects the unattended default, and it must run against the existing suite unedited — a behaviour
  change needs a test it did not edit.

Verification is `make check` in plain mode, exit code captured, never piped.

## 7. Out of scope, deliberately

- **Flipping the unattended default** (A1) — its own change, gated on real-JD evidence.
- **The `shell_source` digest gap.** `projection.yaml` declares `shell_source: resume.yaml`, whose *content*
  no digest covers (`shell.py:18-24`), so editing it changes the projected document with no re-approval.
  Inherited, named here, unfixed — it belongs to §12 Q5's renderer-ownership work.
- **§12 Q3, persona `entries` vs Stage 2.** Guarded by the existing typed preflight, not resolved; §10 puts
  it before P6, not here.
- **P1 item 5's dead safety net.** The untailored last-resort is the full 6,134-char master against
  `resume_max_pages=1`, so it cannot ship for this profile — the degraded path's *last* rung is unreachable
  even though its first rung works. Pre-existing, orthogonal, and a page-budget question rather than a
  projection one.
- The model re-ranker (slice P6), and any LLM lane in `pipeline/runner.py` (§11).

## 8. Gate

§10's P5 row, made measurable:

| Clause | How it is met |
|---|---|
| Projection runs inside `boardwatch run` | `--project` renders projected leads on a real run over live postings |
| A stale manifest is **detected**, not merely inspectable | digest mismatch refuses the lead; artifact rows name their bundle revision |
| `resume.yaml` stops being the daily default | **explicitly NOT met by this slice** — deferred by A1 until §8's proof condition holds |

The third clause is deferred rather than claimed. Recording it as met here would be the failure mode
§8's migration order exists to prevent.
