# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and note the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Rationale: `DECISIONS.md`. What shipped:
> `CHANGELOG.md`. **Facts you should not re-derive: `STANDING-FACTS.md`** (D-139) — read it by section,
> when you are about to touch the thing it describes.
>
> `DECISIONS.md` and `METRICS.md` each carry an **index spanning themselves and a closed archive**
> (`*-ARCHIVE.md`, D-108). Read the index, then the one range you need — never the whole file.

**This file states only what is true now**, and carries no commit sha or commit count on purpose — both go
stale inside a single session (D-017). `git log --oneline -1` and `git status --short --branch` are the
authority. **Rewrite it, never prepend to it.** Keep it near 170 lines.

---

## Current standing

**The program reoriented on 2026-08-13 (D-155).** A broad roadmap review found the system close to fully
built and almost never run, and Mit ruled that the remaining work runs through the **canonical
career-profile bundle**, not through the old `resume.yaml` path.

**The headline number: 0.** Zero job applications have ever come out of boardwatch (`applications` has 0
rows), zero unattended days accumulated, zero acceptance days. Against that: 3 published releases, ~46k
lines of source, 5,979 tests at 95.71%, 61 CLI commands, 6 ATS providers, a 24,073-posting store.

**There is no live gap, and that is a correction.** `STANDING-FACTS.md` claimed nothing generates Mit's
résumés daily. Measured: job-apps produced résumés on 08-09 (8 PDFs), 08-10 (28), 08-11 (24), 08-12 (18).
`PROGRAM.md` §2's output-side-first ordering argument rested on the false premise. **Freezing P3, P6 and
the 14-day clock therefore costs nothing**, which is what makes the reorientation affordable.

### The active track — bundle to résumé

**`resume.yaml` is an import source, never hand-fixed (D-155).** The bundle design already names it:
`source_kind: boardwatch_resume`, adapter `boardwatch-resume-v1`. Run against the live file it enumerates
**81 source records** (header 2 · education 2 · skill-groups 58 · entry metadata 6 · bullets 13) — Gate B's
denominator for that source. The importer exists (~1,400 lines) but **has no CLI command**.

**The projection design is at revision 2**, spec at
`docs/superpowers/specs/2026-08-13-career-profile-projection-design.md`. Two external reviewers ran
in-repo with executable probes; **both returned REWORK**; all eighteen findings are dispositioned in the
spec's §13. Reviews kept at `.agent/REVIEW-R1-{GPT,DEEPSEEK}.md`.

**The finding that shaped it, and it must not be re-derived: `LatexRenderer.emit` never reads
`Resume.header` or `Resume.education`.** The layout gate says so in its own docstring — *"Increment 1's
template hardcodes them (never model-rendered)"*. Projecting them cannot change the PDF while every
proposed test still passes. **So v1 projects only `skill_groups`, `entries`, `extracurricular`, and the
bundle is NOT authoritative for Mit's name, contacts or education** (D-156).

**The capability the whole track exists for did not exist anywhere.** Verified across every layer: every
`build_plan` op is bullet-scoped, both bundled personas ship `entries: null` so all entries always render,
and nothing manages a page budget. That is why a data-platform JD rendered 13 iOS bullets — not a bad
selection, **no selection**. The design adds pinned-core-plus-scored-candidates with a budget fit.

**Next action: `writing-plans`, in a FRESH session.** Agreed deliberately — the plan must not be written by
the context that wrote and twice-fixed the spec, and a spec-reviewed plan still needs its own preflight
against the code. **Gate B (populating the real bundle) has NOT started**; `{config_dir}/career-profile`
does not exist. Everything is designed against the synthetic example bundle that ships as package data.

### Gate A — MET (2026-08-12)

Met because every clause has a measurement saying so. The code is complete, merged, pushed, and **green on
all twelve CI jobs at `8475319`, Windows included** — cite the CI run and D-157, **not** D-145, which
prohibits the claim and was discharged by that run. Numbers in `METRICS.md`; four gates re-run on the
result (`make check` exit 0 · 5,930 passed · 95.65%; `gitleaks` exit 0; `perf` exit 0; acceptance 8 PASS /
0 FAIL). Windows runs 5,883 passed / 48 skipped in 1:18:03 — slow, not hanging.

The review loop is CLOSED at round five (D-137), five rounds each finding a defect in the one before it;
six reports in `.agent/`. **Do not re-run any of them.** The last open question is answered (D-143).

> **Treat the closed review loop as evidence about the slices reviewed, not about the subsystem being
> defect-free.** Two silent-success defects (D-138/D-142, D-141) were found *after* it closed, in code six
> reviews and four gates had passed.

Also load-bearing and easy to lose: **the manifest is written SECOND, not last** — D-143's stated order is
wrong and D-157 is the correction of record. Gate A has moved no program gate. Start any Gate A session
with `git worktree prune`.

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** — all nine items | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** — P1a + P1b | **MET** (D-032, D-033) |
| P2 Profile + keystone | items 1–7 shipped; item 4 is a *mechanism*, inert for bundled `[software]`; item 7 done for `work_auth` only; **item 8 NOT STARTED** | **MET AS RECONCILED** (D-075) — evidence is test fixtures, not a live run |
| P3 Unattended one command | **COMPLETE** except Docker and Mit's input | **NOT MET** — needs 7 consecutive runs; **frozen deliberately** (D-155) |
| P4 Craft gate | **COMPLETE** — items 1–7 | **NOT MET** — the blind craft review is the owner's, never run |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** — all six items, three slices merged (D-110, D-111, D-113) | **NOT MET — 2 of 4**, below; **frozen deliberately** |
| 14-day acceptance | not started | — frozen; the clock measures a frozen system and starts after P6 |
| P7 Breadth | not started | — |
| *Gate A (parallel)* | *complete, merged, pushed, CI green* | ***MET*** — *has moved no program gate* |
| *Projection (active)* | *design revision 2, two REWORKs dispositioned* | *plan not yet written* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days, ≤ 5% | **NOT met.** One-shot baseline says **186 surplus of 23,455 = 0.79%**, well under the bar — but not measured over 7 days. D-110 changed which callers advance the queue, so a window started before it is not comparable |
| **0** dead postings reaching the lead list | **NOT met.** The check runs on every `boardwatch run`; needs a real run whose leads are probed. Recall is low **by design** — 7 of 8 known-dead URLs still answer 200 |
| Injected hash-collision test | **MET** (D-100) — a test, not a measurement, so met outright |
| Audit of 20 sampled suppressions | **MET** (D-101) — 20/20 genuine, 0 false positives, 13 employers, deterministic sample |

---

## Open questions — Mit's, not to be resolved by fiat

1. **Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
   Also defensible as a fail-open. Options: leave it; make it fatal; surface it in the run's `errors`.
2. **Should any family other than `work_auth` default to `blocker` severity** (e.g. `clearance`)?
   Owner-gated since D-035.
3. **What is boardwatch's Windows story?** Investigated 2026-08-13, **parked**. The core *is* deliberately
   cross-platform, so the gate is not theater — but `pyproject.toml:23` publishes `OS Independent` while
   "Windows" appears **zero times** in README, CHANGELOG, SECURITY or `docs/configuration.md`. Four caveats
   would have to be named: `pdfinfo` has no package-manager route there *and fails silently everywhere*;
   no desktop notifications (webhook instead); no Task Scheduler recipe; 48 tests skipped, leaving
   crash-atomicity and the permission-error taxonomy unverified. One real bug in the gaps table.
4. **The projection spec's own six open questions** (§12), of which two matter soonest: whether
   `tailor run` should validate the projection manifest (it would close the stale-document path but
   crosses the `profile_bundle`↔`tailor` wall), and whether persona's `entries` list survives stage 2.

*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**, ruled 2026-08-13.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **The ubuntu/3.12 CI failure — ROOT CAUSE FOUND and FIXED (D-159)** | rich 15's `Console.__init__` bakes width from `COLUMNS` **eagerly**, and `cli/eligibility_cmd.py:66` builds its console at import — so `monkeypatch.setenv("COLUMNS", …)` was a **no-op** and three width-controlling tests had never controlled anything. Fixed by popping `COLUMNS`/`LINES` at conftest import, plus a premise test. Reproduces in 1.5 s: `COLUMNS=80 uv run pytest tests/unit/test_eligibility_cmd.py -k abstain --no-cov -n 0`. **D-153 is partial, not wrong** — it closed the `is_terminal` arm, not this one. **Residual: what supplies `COLUMNS≈80` to that one job is still unknown**; the fix does not depend on it | merged, awaiting CI |
| **`resume.yaml` content is Gate B input, NOT a blocker** | Three bullets over the 220-char gate (245 / 234 / 232, two more at 218 / 215), missing Knowledge Forge and Saayam For All, stale `skill_groups`, empty `extracurricular`. **Do not open a session to shorten bullets** — D-155 makes this bundle content. Mit pins `resume_max_pages=1`; never advise 2 | Mit (via Gate B) |
| **No local pre-push check for the TWO CI-only jobs** | **`gitleaks` and `perf` — two, not three.** `generalization` IS inside `make check`. `gitleaks` is installed (8.30.1) but not wired into project tooling | mitigated |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures now race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. **Raise it before anyone runs two authoring agents against one bundle** | owner-gated |
| **P2 item 8 — the onboarding gatherer** | The thing that would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Needs its own brainstorm. Its open architecture question: `catalog._verify_families_are_wired` requires a registered resolver and a `Facts` field per family, so a genuinely new field rule is still *code*, not data | owner-gated |
| **Tier B has never run under `boardwatch run`** | `pipeline/runner.py` never constructs an LLM client, so item 10's per-day call volume is zero today (D-146) | owner-gated |
| **The funnel's drop-reason catalog is enumerated by hand in two places** | The AST test's module list is a hard-coded pair; a third emitter escapes a test whose name promises every drop reason. Complete today. Fix is a shared frozen `DropReason` catalog, ~13 call sites (D-147 R4) | unscheduled |
| **`boardwatch export --format csv` to stdout crashes on Windows** | `cli/export_cmd.py:70` writes to bare `sys.stdout`, whose redirected encoding on Windows is the ANSI codepage, so any non-ASCII company name raises `UnicodeEncodeError`. Reproduced. `--out` at `:73` is already correct. **CI cannot see this** | open Q3 |
| **`pdfinfo` is a hard dependency wearing a soft failure** | `cli/doctor_cmd.py:79-88` says so verbatim. Missing tectonic is loud; missing `pdfinfo` returns `None` (`reports/tailor.py:170-171`) laundered into `COMPILE_FAILED`, surfacing only as "every lead failed to tailor (N/N)". Hits `boardwatch run` on every OS. **The projection design's budget loop must not read this as overflow** | open Q3 |
| **P3 item 8 — cross-OS two-writer WAL test** | Needs a Docker-Linux + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **A `SIGKILL`ed run leaves a dangling `runs` row** | `try/finally` covers exceptions and Ctrl-C, not SIGKILL. Largely drained by the age-based reaper (D-046). **Observed live 2026-08-13**: three rows in `status='running'` (ids 15–17). `top` is what opens them | P3 |
| **`boardwatch doctor` takes minutes** | `scan/health.py:41-70` probes all 135 boards serially with 1.0 s pacing, 30 s timeout, 3 retries; plus `PRAGMA integrity_check` on an 803 MB database and an untimed `tectonic --version`. **Which stage consumes the time is unmeasured** — `doctor --offline` discriminates | unscheduled |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window. Also `ANALYZE` has never run on the live store (`sqlite_stat1` absent) | P6 |
