# Public-readiness: onboarding, usability, and release currency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the beginner CLI journey end-to-end, compress the README onto one memorable path with reference depth linked out, then cut a fresh v0.5.0 release so the published package matches `main`.

**Architecture:** Three workstreams. (1) Additive CLI next-step hints + a new read-only `boardwatch guide` command — no engine or `init` changes. (2) README restructure with operator/reference sections moved into linked `docs/` guides. (3) A tag-driven v0.5.0 release cut from the improved `main`. Workstreams 1 and 2 merge to `main` first; the release is last so it ships the improvements.

**Tech Stack:** Python 3.12, Typer CLI, Rich console, SQLAlchemy/SQLite store, pytest, ruff, mypy --strict, hatchling build, GitHub Actions release workflow (PyPI Trusted Publishing + GHCR + GitHub Releases).

**Spec:** `docs/superpowers/specs/2026-08-24-public-readiness-onboarding-usability-release-design.md`

## Global Constraints

- **`make check` is the only gate.** pytest + ruff + mypy passing individually is not green — the generalization and program-index checks run only under `make check`.
- **Run `make check` DETACHED**, never in the foreground and never piped through `head`/`tail` (SIGPIPE → false negative). Use: `nohup sh -c 'export PATH="/opt/homebrew/bin:$PATH"; make check > /tmp/bw-check-<uniq>.log 2>&1; echo $? > /tmp/bw-check-<uniq>.done' & disown`, then gate on the `.done` sentinel, not the launcher exit code. PATH must include `/opt/homebrew/bin` inside the subshell or ~68 PDF/tailor tests fail (`tectonic not found`) and read as a regression.
- **Narrow single-test runs need `--no-cov -n 0`:** `uv run pytest <path>::<name> --no-cov -n 0 -v`.
- **`git add` new/modified tracked files before `make check`** — the generalization checker scans TRACKED files only.
- **Do NOT modify `init`'s prompt structure** (`src/boardwatch/cli/init_cmd.py:78-81,96-100`) — its prompt count is pinned by the R11 generalization snapshot.
- **Version single source of truth:** `pyproject.toml:12`. There is no `__version__` constant. After bumping, run `uv sync` or `tests/unit/test_version.py` fails (it binds the CLI-reported version to the declared one).
- **Release version: `v0.5.0`.** Publishing is fully tag-driven: pushing a `v*` tag runs `.github/workflows/release.yml`.
- **Canonical beginner path:** `install → init → scan → top → show → track`; `run` is the unattended one-shot.
- **No AI attribution** in commits, PRs, branches, tags, or release notes.
- **Surgical diffs:** every changed line traces to this plan; do not reformat adjacent code.

---

## Task 1: Shared next-step hint helper

**Files:**
- Create: `src/boardwatch/cli/_hints.py`
- Test: `tests/unit/test_hints.py`

**Interfaces:**
- Produces: `print_next_step(console: rich.console.Console, *steps: str) -> None` — prints each step on its own line prefixed with `→ `.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_hints.py
from rich.console import Console

from boardwatch.cli._hints import print_next_step


def test_print_next_step_prefixes_each_line_with_an_arrow() -> None:
    console = Console(width=200, force_terminal=False, no_color=True)
    with console.capture() as cap:
        print_next_step(console, "run `boardwatch top`", "then `boardwatch show <#>`")
    out = cap.get()
    assert "→ run `boardwatch top`" in out
    assert "→ then `boardwatch show <#>`" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_hints.py --no-cov -n 0 -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boardwatch.cli._hints'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/boardwatch/cli/_hints.py
"""Consistent forward "do this next" hints printed after a successful command.

The beginner path (init → scan → top → show → track) was half-wired: `init`
pointed to `scan`, then the trail went cold. These hints wire the rest so each
successful command names the next one.
"""

from __future__ import annotations

from rich.console import Console


def print_next_step(console: Console, *steps: str) -> None:
    """Print each forward step on its own line, prefixed with an arrow."""
    for step in steps:
        console.print(f"→ {step}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_hints.py --no-cov -n 0 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/cli/_hints.py tests/unit/test_hints.py
git commit -m "feat(cli): add shared next-step hint helper"
```

---

## Task 2: Wire forward next-step hints into scan, top, show, run

**Files:**
- Modify: `src/boardwatch/cli/scan_cmd.py` (import + after line 39)
- Modify: `src/boardwatch/cli/top_cmd.py` (import + after line 919)
- Modify: `src/boardwatch/cli/show_cmd.py` (import + after line 215)
- Modify: `src/boardwatch/cli/run_cmd.py` (import + after line 203, guarded)
- Test: `tests/pipeline/test_scan.py`, `tests/unit/test_top_new.py`, `tests/pipeline/test_top_show.py`, `tests/pipeline/test_pipeline_run.py`

**Interfaces:**
- Consumes: `print_next_step` from Task 1.

Assertions use short command fragments (e.g. `"boardwatch top"`), not full sentences, so Rich line-wrapping cannot break the match.

### 2a — `scan` → point to `top`

- [ ] **Step 1: Add a failing assertion to the scan CLI smoke test**

In `tests/pipeline/test_scan.py`, locate the CLI smoke test that invokes `runner.invoke(app, [..., "scan"])` on a respx-mocked board and asserts `exit_code == 0`. Add, after its existing assertions:

```python
    assert "boardwatch top" in result.stdout
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_scan.py --no-cov -n 0 -v -k smoke`
Expected: FAIL — the hint is not printed yet. (If the smoke test name differs, run the file and target the failing assertion.)

- [ ] **Step 3: Implement the hint**

In `src/boardwatch/cli/scan_cmd.py`, add the import near the other cli imports:

```python
from boardwatch.cli._hints import print_next_step
```

Then, immediately after `console.print(line)` (currently line 39), add:

```python
    print_next_step(console, "run `boardwatch top` to see your ranked shortlist")
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/pipeline/test_scan.py --no-cov -n 0 -v`
Expected: PASS.

### 2b — `top` → point to `show` and `track`

The `--json` branch already `return`s at `top_cmd.py:858`, so the end of the function (after line 919) is reached only on the human, visible-results path — no `json_output` guard is needed there.

- [ ] **Step 5: Add a failing assertion to a visible-results top test**

In `tests/unit/test_top_new.py`, in `test_new_shows_only_postings_with_a_new_event_past_the_cursor` (which asserts `"alpha" in result.stdout`), add:

```python
    assert "boardwatch show" in result.stdout
    assert "boardwatch track add" in result.stdout
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_top_new.py::test_new_shows_only_postings_with_a_new_event_past_the_cursor --no-cov -n 0 -v`
Expected: FAIL.

- [ ] **Step 7: Implement the hint**

In `src/boardwatch/cli/top_cmd.py`, add the import with the other cli imports:

```python
from boardwatch.cli._hints import print_next_step
```

Then append after the visible-results `_print_hidden_notices(...)` block that ends at line 919 (i.e. as the last statement of the `top` function):

```python
    print_next_step(
        console,
        "`boardwatch show <#>` for the full posting and eligibility evidence",
        "`boardwatch track add <#>` once you apply",
    )
```

- [ ] **Step 8: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_top_new.py --no-cov -n 0 -v`
Expected: PASS. Also confirm the JSON path is unchanged: `uv run pytest tests/unit/test_top_new.py -k json --no-cov -n 0 -v` (if present) stays green.

### 2c — `show` → point to `track`

- [ ] **Step 9: Add a failing assertion to a show success test**

In `tests/pipeline/test_top_show.py`, locate the test that invokes `runner.invoke(app, [..., "show", <id>])` on a seeded posting and asserts on the body. Add:

```python
    assert "boardwatch track add" in result.stdout
```

- [ ] **Step 10: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_top_show.py --no-cov -n 0 -v -k show`
Expected: FAIL.

- [ ] **Step 11: Implement the hint**

In `src/boardwatch/cli/show_cmd.py`, add the import:

```python
from boardwatch.cli._hints import print_next_step
```

Then, immediately after `console.print(row.body_text)` (currently line 215), add:

```python
    print_next_step(console, "`boardwatch track add <#>` to record an application")
```

- [ ] **Step 12: Run it to verify it passes**

Run: `uv run pytest tests/pipeline/test_top_show.py --no-cov -n 0 -v`
Expected: PASS.

### 2d — `run` → point to reviewing leads and `track`

Guarded so the hint prints only for a healthy run that produced leads. The fatal branch (`run_cmd.py:209`) raises before reaching normal completion.

- [ ] **Step 13: Add a failing assertion to a successful-run test**

In `tests/pipeline/test_pipeline_run.py`, locate the test that invokes `runner.invoke(app, [..., "run"])` and reaches at least one tailored lead (`exit_code == 0`, a lead printed). Add:

```python
    assert "boardwatch track add" in result.stdout
```

- [ ] **Step 14: Run it to verify it fails**

Run: `uv run pytest tests/pipeline/test_pipeline_run.py --no-cov -n 0 -v`
Expected: FAIL on that test.

- [ ] **Step 15: Implement the hint**

In `src/boardwatch/cli/run_cmd.py`, add the import:

```python
from boardwatch.cli._hints import print_next_step
```

Then, immediately after the `for err in summary.errors:` loop ends (currently line 203) and BEFORE the `# Only a FATAL condition fails the run.` comment block (line 205), add:

```python
    if summary.fatal is None and summary.tailored:
        print_next_step(
            console,
            "review the leads above, then `boardwatch track add <#>` after you apply",
        )
```

- [ ] **Step 16: Run it to verify it passes**

Run: `uv run pytest tests/pipeline/test_pipeline_run.py --no-cov -n 0 -v`
Expected: PASS.

- [ ] **Step 17: Commit**

```bash
git add src/boardwatch/cli/scan_cmd.py src/boardwatch/cli/top_cmd.py \
        src/boardwatch/cli/show_cmd.py src/boardwatch/cli/run_cmd.py \
        tests/pipeline/test_scan.py tests/unit/test_top_new.py \
        tests/pipeline/test_top_show.py tests/pipeline/test_pipeline_run.py
git commit -m "feat(cli): print forward next-step hints on scan/top/show/run"
```

---

## Task 3: `boardwatch guide` command

**Files:**
- Create: `src/boardwatch/cli/guide_cmd.py`
- Modify: `src/boardwatch/cli/app.py` (import + registration)
- Test: `tests/unit/test_guide_cmd.py`

**Interfaces:**
- Produces: `guide() -> None` registered as `boardwatch guide`. Read-only; opens no store, needs no profile.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_guide_cmd.py
from typer.testing import CliRunner

from boardwatch.cli.app import app

runner = CliRunner()


def test_guide_prints_the_canonical_journey_in_order() -> None:
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    out = result.stdout
    for command in [
        "boardwatch init",
        "boardwatch scan",
        "boardwatch top",
        "boardwatch show",
        "boardwatch track add",
    ]:
        assert command in out
    # the unattended alternative and the differentiator are named
    assert "boardwatch run" in out
    assert "eligibility" in out


def test_guide_needs_no_profile_or_store() -> None:
    # runs from a clean environment with no --data-dir and no init
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    assert "no profile yet" not in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_guide_cmd.py --no-cov -n 0 -v`
Expected: FAIL — no `guide` command registered (Typer exits non-zero / "No such command").

- [ ] **Step 3: Write the command**

```python
# src/boardwatch/cli/guide_cmd.py
"""`boardwatch guide` — the whole beginner journey on one screen.

A user who runs a command and does not know what comes next can run
`boardwatch guide` to see the canonical path from setup to tracking.
"""

from __future__ import annotations

from rich.console import Console

console = Console()

_STEPS: list[tuple[str, str]] = [
    ("boardwatch init", "Pick companies to watch and paste your profile. One-time setup."),
    ("boardwatch scan", "Fetch the watched boards for new and changed postings."),
    ("boardwatch top", "See your ranked shortlist, best matches first."),
    (
        "boardwatch show <#>",
        "Read a posting in full — with eligibility evidence quoted from the listing.",
    ),
    (
        "boardwatch track add <#>",
        "Record an application so it stops re-surfacing and your funnel updates.",
    ),
]


def guide() -> None:
    """Print the canonical boardwatch journey from setup to tracking."""
    console.print("The boardwatch journey — run these in order:\n")
    for command, description in _STEPS:
        console.print(f"  [bold]{command}[/bold]")
        console.print(f"    {description}\n")
    console.print(
        "Prefer one command? `boardwatch run` does scan → rank → tailor in a single "
        "unattended pass — schedule it for a shortlist every morning.\n"
    )
    console.print(
        "Why boardwatch: every eligibility verdict cites the exact span from the "
        "posting, and your data never leaves your machine."
    )
```

- [ ] **Step 4: Register the command**

In `src/boardwatch/cli/app.py`, add the import alongside the others (after the `from boardwatch.cli.export_cmd import ...` group, keeping import order tidy):

```python
from boardwatch.cli.guide_cmd import guide as _guide
```

And register it near the other beginner commands (e.g. right after the `app.command("show")(_show)` line, currently line 61):

```python
app.command("guide")(_guide)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_guide_cmd.py --no-cov -n 0 -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add src/boardwatch/cli/guide_cmd.py src/boardwatch/cli/app.py tests/unit/test_guide_cmd.py
git commit -m "feat(cli): add boardwatch guide command showing the canonical journey"
```

---

## Task 4: Restructure the top of the README onto one path

**Files:**
- Modify: `README.md` (lines 1–171 region; specific moves in Task 5)

No unit test; verification is `make check` (generalization scans the README) plus a manual read. This task only reshapes the first third; Task 5 removes the moved sections.

- [ ] **Step 1: Move the Windows caveats out of Quickstart**

Cut the Windows best-effort caveats block currently at `README.md:80-101` (including the fixed-bug postmortem). It will land in `docs/platform-support.md` in Task 5. In its place under `## Quickstart (≈2 minutes to your first shortlist)`, leave at most one line:

```markdown
> Supported on macOS and Linux. Windows is best-effort — see [platform support](docs/platform-support.md).
```

- [ ] **Step 2: Lead Quickstart with the single golden path**

Immediately under the Quickstart heading and the one-line platform note, put the recommended path first, before the Docker / from-source alternatives:

```markdown
```sh
pipx install boardwatch
boardwatch init      # pick companies, paste your profile
boardwatch scan      # fetch the watched boards
boardwatch top       # your ranked shortlist
```

New here? Run `boardwatch guide` at any time to see the whole journey.
```

Keep the Docker and from-source blocks, but demote them under an `### Other install methods` subheading after the golden path.

- [ ] **Step 3: State the one canonical lifecycle in "How it works"**

In `## How it works` (around `README.md:139-163`), make the diagram and prose show exactly one named path — `init → scan → top → show → track` — and mention `run` once as "the same pipeline, unattended" with a link to the new `docs/unattended-run.md` (created in Task 5). Remove the second, unreconciled path.

- [ ] **Step 4: Verify the reshaped top reads as one path**

Read `README.md` lines 1–171. Confirm: a macOS/Linux beginner reaches `pipx install` with no platform wall in the way; exactly one lifecycle is named; `boardwatch guide` is mentioned. No commit yet — commit with Task 5 so the moved-out sections and their new homes land together.

---

## Task 5: Move operator/reference sections into linked `docs/` guides

**Files:**
- Create: `docs/platform-support.md`, `docs/scheduling.md`, `docs/unattended-run.md`, `docs/tailoring.md`, `docs/providers.md`
- Modify: `README.md` (remove moved sections, leave a one-line link each), `docs/README.md` (index the new guides)

No unit test; verification is a link check + `make check`.

- [ ] **Step 1: Create the guide files from the moved content**

Move each section verbatim (then tighten headings) into its new home, and replace the section in `README.md` with a single sentence linking to it:

| From `README.md` | To | README replacement |
|---|---|---|
| Windows caveats `80-101` (already cut in Task 4) | `docs/platform-support.md` | already a one-line link |
| Scheduling recipes `343-438` (cron/launchd/systemd) + Notifications `440-467` | `docs/scheduling.md` | "Schedule scans and get notified — see [scheduling](docs/scheduling.md)." |
| Unattended `run` pipeline `471-547` | `docs/unattended-run.md` | "Run the whole pipeline unattended — see [the unattended run guide](docs/unattended-run.md)." |
| Tier B LLM lane + agent lane `599-704` | `docs/tailoring.md` | keep the short Tier A résumé section `551-597` in the README; end it with "Opt-in LLM rewriting is covered in [tailoring](docs/tailoring.md)." |
| Workday/SmartRecruiters deep-dives `758-778` | `docs/providers.md` | keep the provider endpoint table in the README; end it with "Per-provider coverage limits: see [provider notes](docs/providers.md)." |

- [ ] **Step 2: Compress the two duplicated blocks to pointers**

- Config key table `316-339` → replace with one line linking to the existing `docs/configuration.md`.
- Eligibility leveling-bindings internals `236-251` → replace with one line: "Level-aware gating is optional and documented in [configuration](docs/configuration.md)."

- [ ] **Step 3: Index the new guides**

In `docs/README.md`, add links to `platform-support.md`, `scheduling.md`, `unattended-run.md`, `tailoring.md`, and `providers.md`, and remove the stale "land in P1–P3" placeholder line.

- [ ] **Step 4: Verify every internal link resolves**

Run this link check (fails loud if any `docs/…md` target referenced from README or docs/README is missing):

```sh
for f in $(grep -rhoE '\]\((docs/[^)]+\.md|[a-zA-Z0-9._-]+\.md)\)' README.md docs/README.md | sed -E 's/^\]\(//; s/\)$//'); do
  case "$f" in
    docs/*) t="$f" ;;
    *) t="docs/$f" ;;
  esac
  [ -f "$t" ] || echo "BROKEN LINK: $f"
done
echo "link check done"
```

Expected: only `link check done`, no `BROKEN LINK` lines. (Adjust the `case` if a link is repo-root-relative rather than docs-relative.)

- [ ] **Step 5: Stage everything and commit**

```bash
git add README.md docs/README.md docs/platform-support.md docs/scheduling.md \
        docs/unattended-run.md docs/tailoring.md docs/providers.md
git commit -m "docs: compress README onto one path, move operator detail into linked guides"
```

---

## Task 6: Full gate for Workstreams 1 and 2, then open the PR

**Files:** none (verification + integration)

- [ ] **Step 1: Confirm the working tree is fully staged/committed**

Run: `git status --porcelain`
Expected: empty. (Generalization scans tracked files only; anything unstaged is invisible to the gate.)

- [ ] **Step 2: Run the full gate DETACHED**

```bash
U=$(date +%s)
nohup sh -c 'export PATH="/opt/homebrew/bin:$PATH"; make check > /tmp/bw-check-'"$U"'.log 2>&1; echo $? > /tmp/bw-check-'"$U"'.done' & disown
echo "log=/tmp/bw-check-$U.log done=/tmp/bw-check-$U.done"
```

Poll for `/tmp/bw-check-$U.done`; when it appears, the file's contents are the real exit code.

- [ ] **Step 3: Confirm green**

Read the `.done` sentinel: it must contain `0`. If non-zero, read the tail of the `.log`, fix, and re-run this task. Do not proceed on a red or timed-out gate. (A contended machine can SIGTERM a comfortable run; re-run alone before treating a kill as a real failure.)

- [ ] **Step 4: Push the branch and open a PR to `main`**

```bash
git push -u origin HEAD
gh pr create --base main --title "Compress onboarding surface and wire the beginner journey" \
  --body "Adds forward next-step hints (scan/top/show/run), a boardwatch guide command, and compresses the README onto one path with reference detail moved into linked docs/ guides. No engine or eligibility changes. Implements docs/superpowers/specs/2026-08-24-public-readiness-onboarding-usability-release-design.md."
```

- [ ] **Step 5: Merge once CI is green**

Wait for CI (multi-OS, gitleaks, perf) to pass on the PR, then merge. Do not admin-bypass the PR.

---

## Task 7: Release pre-flight

**Files:** none (verification only). Begins Workstream 3 — run only AFTER Task 6 is merged to `main`.

- [ ] **Step 1: Fast-forward local `main`**

```bash
git checkout main
git fetch origin
git merge --ff-only origin/main
git log --oneline -3
```

Expected: local `main` equals `origin/main`, including the Task 6 merge.

- [ ] **Step 2: Confirm `main` CI is green**

```bash
gh run list --branch main --limit 5
```

Expected: the latest `ci.yml` run on `main` is success. The tag build re-runs only `make check` on Ubuntu — it does NOT re-gate Windows, perf, or gitleaks, so those must be green here.

- [ ] **Step 3: Confirm the nightly Windows run is green**

```bash
gh run list --workflow ci.yml --limit 15 | grep -i schedule | head
```

Expected: the most recent scheduled (nightly) run is success. **Stop boundary:** if the nightly Windows/perf state is red or unknown, do not tag — trigger and pass a fresh nightly first (`gh workflow run ci.yml`).

---

## Task 8: Bump the version and CHANGELOG, gate locally

**Files:**
- Modify: `pyproject.toml:12`, `CHANGELOG.md`

- [ ] **Step 1: Create a release branch**

```bash
git checkout -b release-v0.5.0
```

- [ ] **Step 2: Bump the version**

Edit `pyproject.toml:12` from `version = "0.3.0"` to `version = "0.5.0"`.

- [ ] **Step 3: Re-sync so installed metadata matches**

```bash
uv sync
uv run pytest tests/unit/test_version.py --no-cov -n 0 -v
```

Expected: PASS — the CLI-reported version now equals `0.5.0`.

- [ ] **Step 4: Retitle the CHANGELOG**

In `CHANGELOG.md`, rename `## [Unreleased]` (line 7) to `## [0.5.0] - 2026-08-24` (use the actual release date), and insert a fresh empty section above it:

```markdown
## [Unreleased]

## [0.5.0] - 2026-08-24
```

Then, at the top of the 0.5.0 section, add a plain-language, user-outcome-first summary line and an explicit upgrade note (the delta already contains a `Migration` subsection):

```markdown
### Notes
- Upgrading from 0.3.0 applies a one-time store migration automatically on the first `scan`/`run`.
```

Keep the existing `Added / Fixed / Changed / Migration` bullets; do not rewrite them beyond the summary/notes additions.

- [ ] **Step 5: Run the full gate DETACHED (as in Task 6 Step 2) and confirm `0`**

The tagged commit must pass `make check` including `generalization` and `index-check`, or the release build's publish jobs skip.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml CHANGELOG.md uv.lock
git commit -m "chore(release): 0.5.0"
```

(Include `uv.lock` only if `uv sync` changed it.)

---

## Task 9: PR and merge the release commit

**Files:** none

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin release-v0.5.0
gh pr create --base main --title "Release 0.5.0" \
  --body "Version bump to 0.5.0 and CHANGELOG cut. Catches the published package up to main (608 commits). Tagging follows after merge."
```

- [ ] **Step 2: Merge once CI is green**

Wait for CI green, merge to `main`, then locally:

```bash
git checkout main && git fetch origin && git merge --ff-only origin/main
```

---

## Task 10: Tag, publish, and verify

**Files:** none (release action + external verification)

- [ ] **Step 1: Tag the merged release commit and push the tag**

```bash
git tag v0.5.0
git push origin v0.5.0
```

This triggers `.github/workflows/release.yml` (build → `make check` → `uv build` → PyPI + GitHub Release + GHCR).

- [ ] **Step 2: Watch the release workflow**

```bash
gh run watch $(gh run list --workflow release.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

Expected: all jobs succeed (`build`, `pypi`, `github-release`, `docker`).

- [ ] **Step 3: Verify from OUTSIDE the producing path**

A component's self-report is not verification. Confirm each artifact independently:

```bash
# PyPI shows 0.5.0
curl -s https://pypi.org/pypi/boardwatch/json | python -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
# GitHub release exists
gh release view v0.5.0 --json tagName,name -q '.tagName'
# GHCR image is tagged (public image; token-free anonymous pull of the manifest)
gh api /users/mit112/packages/container/boardwatch/versions --jq '.[0].metadata.container.tags' 2>/dev/null || echo "check GHCR tags in the GitHub UI"
```

Expected: `0.5.0`, `v0.5.0`, and a `0.5.0`/`latest` container tag.

- [ ] **Step 4: Smoke-test the published package in a clean environment**

```bash
pipx run --spec boardwatch==0.5.0 boardwatch version
```

Expected: prints `boardwatch 0.5.0 · schema <rev>`.

- [ ] **Step 5: Confirm the released README matches the package**

Because the tag was cut from the same `main` that carries Tasks 1–5, the PyPI/GitHub README now describes the shipped behavior. Spot-check the GitHub release page renders the new one-path Quickstart.

---

## Self-Review

**Spec coverage:**
- W1 CLI hints → Tasks 1, 2. `guide` command → Task 3. ✓
- W2 README compression + docs move → Tasks 4, 5. ✓
- W3 v0.5.0 release (pre-flight, bump, changelog, PR, tag, verify) → Tasks 7–10. ✓
- Sequencing (polish merges before the tag) → Task 6 merges W1+W2; Task 7 gates on that merge before W3. ✓
- Honesty boundary (no fabricated proof asset) → Tasks 4/5 add no demo/proof; deferred per spec. ✓
- Do-not-touch `init` prompts → Global Constraints + not touched by any task. ✓

**Placeholder scan:** CHANGELOG date and the specific existing test-function names in Task 2c/2d are the only "find the right spot" steps; each names the exact file and the exact assertion/edit to make, with anchors — no "TBD"/"handle edge cases"/"similar to" placeholders.

**Type consistency:** `print_next_step(console, *steps)` is defined in Task 1 and consumed with that exact signature in Tasks 2 and (implicitly) 3. `guide()` defined in Task 3 matches its registration. Version `0.5.0` is consistent across Tasks 8–10.
