# boardwatch — Codex instructions

This file is the Codex entry point for the repository. Keep durable history in
`docs/program/DECISIONS.md`, current standing in `docs/program/STATE.md`, and measured gate evidence
in `docs/program/METRICS.md`; do not turn this file into a second changelog.

## Start every session

1. Read `docs/program/STATE.md` first.
2. Verify it against the live tree with `git status --short --branch` and `git log --oneline -5`.
   If the state document and code disagree, the repository wins; correct the state and record the
   correction in `docs/program/DECISIONS.md`.
3. Read the relevant phase in `docs/program/PROGRAM.md` and its gate evidence in `METRICS.md`.
   Do not start a phase whose predecessor gate is unmet.
4. Preserve dirty files and linked worktrees. Do not reset or clean another worker's changes.
5. Before ending, update `STATE.md` and `METRICS.md`; append to `DECISIONS.md` for architectural
   choices or owner rulings.

## Current standing to re-verify

The 2026-08-09 baseline is: before this setup, `main` had no pre-existing modifications; `make check`
passed with generalization OK, Ruff clean, mypy clean, 3,636 tests passed, 1 deselected, and 95.23%
coverage. The only current working-tree addition is this intentional `AGENTS.md`. P0 and P1 are
complete; P2 is met-as-reconciled as a field-tier mechanism, with real per-user field content and the onboarding
gatherer still outstanding; P3 is implemented for the non-owner/non-Docker slices but its operational
gate is unmet; P4's build is complete but its blind craft review is owner work; P5 is met at 16/16
INELIGIBLE precision; P6 and P7 have not started. Re-check `STATE.md` before relying on any of these
numbers.

The two explicit owner questions currently recorded in `STATE.md` are:

- whether `pipeline/runner.py` should swallow funnel-write failures, make them fatal, or surface them
  in run errors;
- whether any eligibility family besides `work_auth` should default to `blocker` severity.

Do not resolve either by assumption or by code fiat.

## Non-negotiable product and safety boundaries

- No cover letters, outreach/referral scaffolding, auto-apply, auto-fill, or browser automation.
- Keep the generalized mechanism in the repository; keep Mit's profile, persona, résumé, targeting
  policy, live store, and credentials local.
- Every declared eligibility profile field must abstain when missing or unresolvable; never turn that
  condition into `ELIGIBLE` or `INELIGIBLE`.
- `ABSTAIN` stays distinct from `ELIGIBLE` and `INELIGIBLE` in every report.
- `INELIGIBLE` requires a quoted span from the frozen JD; otherwise downgrade to `ABSTAIN`.
- An eligible result needs an evidence chain, not merely an absence of flags.
- Every quarantine needs a re-entry/drain path in the same change.
- Prefer existing code, platform features, stdlib, and small dependencies in that order. Keep diffs
  surgical, typed, and free of speculative abstractions.

## Verification and Git

`make check` is the only green gate. It runs generalization, the program-index check, Ruff, strict mypy, and pytest; run it in
plain mode and preserve the real exit code. A failed command is not evidence of a clean negative.

Use descriptive imperative commit messages, one logical change per commit, and never add AI
attribution, `Co-Authored-By`, or generated-by text. Do not commit local `.agent/` or `.superpowers/`
working material, personal data, secrets, or live-store artifacts.
