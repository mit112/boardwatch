# Public-readiness plan: onboarding, usability, and release currency

**Date:** 2026-08-24
**Status:** Design approved in shape by the owner (Mit); awaiting spec review before an implementation plan is written.
**Source research:** `docs/superpowers/research/2026-08-24-ai-job-search-comparison.md` (Sol's `ai-job-search` comparison). That file is evidence, not authority; this spec is the owner-approved subset.

## Purpose

Turn the three concerns the owner raised — **user onboarding, ease of use, and getting the published
repo up to date** — into a bounded plan with exact deliverables, verification, and stop boundaries. It
deliberately does **not** re-plan the whole comparison memo.

## Owner decisions locked (do not silently revisit)

1. **Plan scope:** only the three concerns above. No new product features.
2. **Release currency:** cut a fresh release from verified `main`. Version **v0.5.0**.
3. **Initial audience:** **tech-first** — software/technical candidates on the supported ATS boards.
   Matches today's role gate; onboarding can be built now without the unstarted field-taxonomy step.
4. **Onboarding ambition:** **compress and clarify** the existing flow — not a rebuild.
5. **Sequencing:** do the two polish workstreams first, merge to `main`, then cut v0.5.0 so the release
   ships the improved onboarding and README.
6. **`boardwatch guide` command:** yes — add it.

## Explicitly out of scope

Proof gates (blind craft review / 7-day liveness window / 14-day acceptance run), the community
flywheel and GitHub Discussions, the launch story, a demo/proof asset with measured funnel numbers,
the field-taxonomy onboarding rebuild (P2 item 8), and any product-feature expansion (cover letters,
outreach, auto-apply, browser automation all stay out per repo scope). No program gate moves because of
this plan.

---

## Workstream 1 — Clarify the beginner CLI journey

**Problem.** The engine already has every command the beginner path needs, but the path is *half-wired*.
`init` closes with the one real forward hint — "Run `boardwatch scan` next." (`init_cmd.py:139`) — and
then the trail goes cold: `scan` prints only a stats summary and dead-ends (`scan_cmd.py:29-39`), `top`
does not point to `show`/`track`, `show` does not point to `track`, and `run` prints artifact paths with
no next step. Every other `boardwatch <cmd>` string in output today is an *error/empty-state redirect*,
not a forward hint.

**Deliverables.**

1. A small shared helper (working name `_next_step(...)`) that renders a forward "→ do this next" line
   in one consistent style, matching the existing "run `boardwatch init` first" redirects (phrasing is
   inconsistent across `top_cmd.py:820`, `eligibility_cmd.py:90`, `profile_cmd.py:115` today).
2. Forward next-step hints on the success paths that currently dead-end:
   - `scan_cmd.py:39` → point to `boardwatch top`. **Highest value** — `init` promises `scan`, and today
     `scan` is where the journey stalls.
   - `top_cmd.py:908` → point to `boardwatch show <#>` and `boardwatch track add <#>`.
   - `show_cmd.py:215` → point to `boardwatch track add <id>`.
   - `run_cmd.py:203` → point to reviewing the emitted leads and `boardwatch track add <id>`.
3. A net-new `boardwatch guide` leaf command that prints the one canonical journey end-to-end, so a lost
   user has a single "here's the whole path" surface. Registered on the root Typer app
   (`src/boardwatch/cli/app.py:33,48-78`). Read-only; touches no store state.

**Constraints / do-not-touch.**

- **Do not change `init`'s prompt structure.** Its prompt count is pinned by a generalization snapshot
  (`init_cmd.py:78-81,96-100`); reworking prompts would break the R11 snapshot. Compressing the journey
  means wiring the path *between* commands, not rebuilding `init`. `init`'s existing closing hint is the
  pattern the other commands should copy.

**Testing.**

- Add assertions that `scan`/`top`/`show`/`run` print their forward hint on the success path, and that
  `boardwatch guide` renders the canonical path. Prefer tests that fail against the current (hint-less)
  code before the change lands, so they are not vacuous.
- Verify the added output does not disturb any existing CLI snapshot beyond the intended lines.

**Verification.** `make check` green (the only gate). Run it detached, capture the real exit code, never
pipe through `head`/`tail`.

---

## Workstream 2 — Compress and clarify the README

**Problem.** The README is 863 lines. The first content after the `## Quickstart` heading is ~22 lines of
Windows best-effort caveats *plus a postmortem of a fixed bug* (`README.md:80-101`), sitting between the
reader and the first `pipx install`. The golden path (`pipx install → init → scan → top`) is buried at
`README.md:105-110` behind that platform wall, and two competing beginner paths are documented but never
reconciled. Operator/reference depth (scheduling, unattended run, Tier B, provider deep-dives) arrives
before the reader has run a single scan.

**Deliverables.**

1. **Fix the top of the file.** Put the single golden path immediately under Quickstart. Reconcile the two
   documented paths into **one canonical, named lifecycle** for a tech-first user:
   `install → init → scan → top → show → track`, with `run` mentioned once as the "do it all unattended"
   option linked to its own guide. Keep the strong opening pitch and the (clearly labeled) illustrative
   `top` output.
2. **Move operator/reference material into linked `docs/` guides** (the `docs/README.md` index already
   reserves space for provider/privacy/scheduling docs). Candidates, with current line ranges:
   - Windows caveats (`README.md:80-101`) → a platform-support note.
   - Scheduling recipes — cron/launchd/systemd (`README.md:343-438`) → a scheduling guide.
   - Notifications (`README.md:440-467`) → into the scheduling/ops guide.
   - Unattended `run` pipeline (`README.md:471-547`) → an operations guide.
   - Tier B LLM lane + agent lane (`README.md:599-704`) → a résumé-tailoring guide.
   - Workday/SmartRecruiters "honest limits" deep-dives (`README.md:758-778`) → provider notes.
   - Config key table (`README.md:316-339`) → compress to a pointer to the existing
     `docs/configuration.md`.
   - Eligibility leveling-bindings internals (`README.md:236-251`) → compress to a pointer.
3. Link every moved section from both the trimmed README and `docs/README.md`.

**Honesty boundary.** Do **not** fabricate a proof/demo asset. A real demo recording plus measured funnel
numbers is proof-gate work the owner scoped out; keep an honest status/limits note and mark the demo as a
deferred follow-on. The Roadmap's existing "measured acceptance run" item stays as an honest future item.

**Target.** Roughly halve the README; reference depth lives one click away, not inline.

**Verification.** All internal links resolve; the released README describes the package being released
(guaranteed because the release is cut from this same `main`, per sequencing). `make check` green.

---

## Workstream 3 — Cut the catch-up release, v0.5.0

**Why.** The published package and PyPI are still **v0.3.0**; `main` is **608 commits / 428 files /
+122k lines** ahead. A `pipx install boardwatch` today gives a materially older product than the README
describes. Publishing is fully tag-driven: pushing a `v*` tag runs `.github/workflows/release.yml`, which
re-runs `make check`, builds with `uv build`, and publishes to **PyPI (Trusted Publishing via OIDC —
already proven on 0.3.0), GHCR (multi-arch), and GitHub Releases (hand-written notes)**.

**This workstream runs LAST**, after Workstreams 1 and 2 are merged to `main`, so v0.5.0 ships the
improved onboarding and README.

**Steps.**

1. Fast-forward local `main` to `origin/main` (local is 1 commit behind; the remote-only commit is
   program-docs only).
2. **Pre-flight (stop boundary):** confirm `main`'s latest CI is green **and** the nightly Windows run is
   green. The tag-triggered `release.yml` only re-runs `make check` on Ubuntu — it does **not** re-gate
   Windows, perf, or gitleaks (those live in `ci.yml`). Do not tag on a red or unknown Windows/perf state.
3. Bump `pyproject.toml:12` `version` `0.3.0 → 0.5.0` (single source of truth; no `__version__` constant
   exists). Run `uv sync` so installed metadata updates — `tests/unit/test_version.py` binds the CLI's
   reported version to the declared one and will fail otherwise.
4. Retitle `CHANGELOG.md` `## [Unreleased]` (line 7) → `## [0.5.0] - <date>`, open a fresh empty
   `[Unreleased]`. The unreleased delta includes a **schema Migration** subsection — 0.3.0 users get the
   migration on first run via `ensure_schema`. Call that out plainly in the release notes, written in
   user-facing outcomes, not internal decision vocabulary.
5. Run the full `make check` **detached**, gate on the sentinel file, capture the real exit code, confirm
   green. (`export PATH` inside the subshell so tectonic/pdfinfo resolve, or ~68 PDF/tailor tests fail and
   read as a regression.)
6. Open a PR with the version bump + CHANGELOG retitle; merge to `main`.
7. Tag `v0.5.0` on the merged commit and push the tag; watch `release.yml` publish.
8. **Verify from outside the producing path:** PyPI shows 0.5.0, the GHCR image is tagged, and the GitHub
   release exists. A component's self-report is not verification.

**Stop boundaries.**

- Do not tag if the version was not bumped — tagging `v0.5.0` on a `0.3.0` `pyproject` builds a
  `boardwatch-0.3.0` wheel and PyPI rejects the duplicate; the publish job fails.
- Do not tag if `main`'s `make check` (including `generalization` and `index-check`) is not green — the
  release build re-runs it and all publish jobs skip on failure.
- Do not tag on a red/unknown Windows or perf state (see pre-flight).

---

## Sequencing

```
Workstream 1 (CLI hints + guide)  ─┐
                                    ├─ merge to main ─→ Workstream 3 (tag v0.5.0 → publish)
Workstream 2 (README + docs)      ─┘
```

Workstreams 1 and 2 are independent of each other and may proceed in parallel (separate files: CLI command
modules vs. README/`docs/`). Both must be merged and `main` green before Workstream 3 tags.

## Gate

`make check` is the only gate for Workstreams 1 and 2. Workstream 3 additionally depends on green CI on
`main` (multi-OS, gitleaks, perf) and the nightly Windows run, since the tag build does not re-gate those.

## Risks

- **Snapshot coupling:** added CLI output could disturb an existing snapshot test. Mitigation: keep hints
  additive and on success paths; run `make check`, not a narrow subset. Do not touch `init`'s pinned
  prompts.
- **README link rot:** moving sections into `docs/` can break anchors. Mitigation: verify all links resolve
  before merge.
- **Release pre-flight skipped:** the tag build's narrow gate is the main trap. Mitigation: the explicit
  pre-flight stop boundary above.

## Deferred (named, not dismissed)

The demo/proof asset, the community flywheel + Discussions, the launch story, and the field-agnostic
onboarding path all remain worthwhile but are out of this plan's scope by owner decision. They belong to
the larger public-readiness sequence in the research memo, to be planned separately if and when the owner
chooses.
