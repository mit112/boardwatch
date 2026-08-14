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
denominator for that source. The importer (~1,400 lines across `enumerators.py` + `imports.py`) now has a
CLI command: **`profile-bundle import`** (D-170). It writes `imports/source-ledger.yaml` and nothing else.

**The projection design is at revision 3** (`docs/superpowers/specs/…-projection-design.md`), after three
external review rounds, all REWORK. **Do NOT bump it to revision 4** — D-158 closed that loop on purpose,
and **where the spec and the preflight disagree the preflight wins**; the plan carries a correction table.

**No scorer is picked, and none may be picked by inspection** (D-158, D-163). All four candidates are
falsified by one probe or the other, and they are really two families: `coverage_then_density`'s primary
key *is* `total_distinct`, and `mean_top_k` degenerates into `mean_per_bullet` at or below
`MAX_BULLETS_PER_ENTRY` (**6**). **The four cannot break their own tie — Task 20 is the only arbiter that
exists**: ten real postings ranked by Mit, before any scorer is tuned against them. **Do not open a
session by picking a third scorer.** `--scorer` is required with no default until then (D-168).

**The finding that shaped it, and it must not be re-derived: `LatexRenderer.emit` never reads
`Resume.header` or `Resume.education`.** The layout gate says so in its own docstring — *"Increment 1's
template hardcodes them (never model-rendered)"*. Projecting them cannot change the PDF while every
proposed test still passes. **So v1 projects only `skill_groups`, `entries`, `extracurricular`, and the
bundle is NOT authoritative for Mit's name, contacts or education** (D-156).

**The capability the whole track exists for did not exist anywhere.** Verified across every layer: every
`build_plan` op is bullet-scoped, both bundled personas ship `entries: null` so all entries always render,
and nothing manages a page budget. That is why a data-platform JD rendered 13 iOS bullets — not a bad
selection, **no selection**. The design adds pinned-core-plus-scored-candidates with a budget fit.

**The plan is WRITTEN and preflighted (D-160).** `docs/superpowers/plans/2026-08-13-career-profile-projection.md`
— 23 tasks over P0–P4, PM as Mit's one-session task, P5/P6 declared but deliberately not decomposed.
The preflight (`docs/superpowers/research/2026-08-13-projection-plan-preflight.md`) checked ~60 of the
spec's claims: the load-bearing premise held, but **4 are false, 12 citations drifted, and 9 facts the
plan needs are absent**.

**The plan has had its mechanical check and did NOT need a design review** (D-160). A full design
review was considered and declined — the expensive check happened in the right place, the preflight.

### Execution — MERGED AND PUSHED (2026-08-14). Mit approved the merge

`projection-v1` fast-forwarded into `main` and pushed; `origin/main` carries all 46 commits. The
pre-merge gate was green four ways at the merged tree — exit 0, `All checks passed!`, **6,218 passed / 4
xfailed in 275s**, coverage **95.81%**, all five stages present — and `gitleaks` was clean over the range.
**All 22 dispatchable tasks are complete and reviewed clean.** Task 20 is Mit's — ten real postings ranked
by hand — and blocks only Task 22's *selection*, never any code.

The package holds `errors.py`, `declaration.py`, `grammar.py`, `contract.py`, `shell.py`, `stamp.py`,
`serialize.py`, `posting.py`, `scoring.py`, `effectiveness.py`, `pool.py`, `manifest.py`,
`persona_preflight.py`, `agreement.py`, `select.py`, plus `cli/_approval.py` and three commands:
`profile-bundle approve-projection`, `profile-bundle project`, and the new top-level `resume project`.

**Gate green on the final tree: 6,212+ passed, 4 xfailed, coverage ≥95.8%, `make check` exit 0.** The 4
xfailed are Task 21's deliberate scorer-bias probes, `strict=True`, so a scorer that stops being biased
still fails loudly.

**The whole-branch review found two Criticals that all 22 task reviews missed, both in the seams between
tasks** — the case for doing one at all. Task 15 shipped a persona guard **no task ever wired in**, so it
could never fire (D-169); and the approval's bundle binding sat on the *review* command while
`resume project`, which actually writes the résumé, approved by existence-check alone (D-167). Both
fixed; the fix wave was re-reviewed clean and rated **merge-ready**.

**The merge decision is taken and executed**, and CI was green on all nine jobs of the push. Nothing is
blocked on further engineering. The plan workspace `.superpowers/sdd/2026-08-13-career-profile-projection/`
was **deleted** after that green CI, which is the SDD skill's cleanup step; its rulings survive in D-165
through D-170, and the review packages are gone on purpose.

**Carried, and deliberately open:** the shell's *content* is bound by no digest — `shell_source` is
hashed as a filename, and the shell lives outside the bundle, so editing it changes the projected
`header`/`education` with no re-approval. Small blast radius (D-156: the renderer reads neither field);
`shell.py`'s docstring now says so plainly rather than claiming coverage nothing provides (D-167).

Working ledger: `.superpowers/sdd/2026-08-13-career-profile-projection/progress.md` — **gitignored**, so
anything that must survive belongs here or in `DECISIONS.md`. It carries every ruling with what each costs
if wrong.

**CI was RED for four commits, and the cause is fixed (D-171).** Run 31774640890 (`64cf63c`) — the one the
previous session left UNKNOWN — had **failed on all three ubuntu test jobs**, and `2324a49` failed on two of
three. One test: `test_top_help_lists_the_new_flag`, asserting `"--new" in result.stdout` over a `--help`
render.

| Push | Run | Standing |
|---|---|---|
| `ee20abd` (the merge) | 31772590912 | **GREEN, all nine jobs.** Measured |
| `12dda1d` | 31774326397 | **`generalization` FAILED** — the `example.invalid` address |
| `64cf63c` | 31774640890 | **FAILED** — 3 of 3 ubuntu test jobs; macOS, `generalization`, `gitleaks`, `perf` green |
| `2324a49` | 31775389477 | **FAILED** — `3.13`/`3.11` ubuntu; **`3.12` ubuntu PASSED**, over identical tests |
| `1add630` (the fix) | see `git log` | pushed 2026-08-14 |

**That 3.12 row is the whole diagnosis: the failure is a race, not an OS split and not a regression.** typer
imports `rich_utils` *function-locally*, so its `FORCE_TERMINAL` — true whenever `GITHUB_ACTIONS` is set —
bakes at the first help render in an xdist worker. A dozen fixtures `delenv` that var and had been winning
the race by luck; `e3f8fa9`'s 13 new tests changed sharding and it started losing. `tests/conftest.py` now
pops `GITHUB_ACTIONS` and `PY_COLORS` at import alongside rich's two, and a test pins
`FORCE_TERMINAL is not True`. **A green run alone cannot verify this** — it passed by luck before; the
pinning test is what makes a green run mean something.

**Two measurement lessons from it.** A rate-limited `gh` REST quota is not a missing measurement —
**GraphQL was untouched and answered instantly**; the previous session's UNKNOWN was avoidable. And
`All checks passed!` is the **`generalization` stage's** banner, not the gate's: it prints while pytest is
still running, so it reads as a green gate about four minutes early.

**Gate B has STARTED — its first mechanical blocker is cleared, and no data has moved yet.**
`profile-bundle import` exists (D-170), so a real source can now reach a draft's ledger without
transcribing 81 records by hand. **`{config_dir}/career-profile` still does not exist**, nothing has been
imported, and everything remains built against the synthetic example that ships as package data. The next
concrete step is Mit's: `profile-bundle init`, declare `resume.yaml` as a source in `policy/sources.yaml`,
then `import`. **Expect every one of the 81 records to land `review_required` at exit 0** — dispositioning
them is the Gate B work, and `validate --completeness` is what lists them.

**Still missing for a promotable bundle: candidate extraction.** `build_candidate_package` needs
*proposals*, and nothing produces them, so `imports/candidates.yaml` stays owner-authored and no record
can reach `imported` yet. That is the next real design question on this track, not a defect.

**Four import walls exist, in three test files, and no document enumerates them** (D-161, D-162). Each was
found by tripping it. **Before wiring a new module into a package, grep `tests/` for what constrains that
package's imports** — a symbol-existence check cannot find a prohibition, and an `__all__` check cannot
find a reference.

**The plan's production code held up; its sample tests did not.** Seven briefs shipped defective reference
tests — falsified arithmetic, a fixture the prescribed loader rejects, a test asserting only that a file
exists, a bare `pytest.xfail()` call that aborts before its assertion, fixtures silently dropped by
first-wins `setdefault`, and a CLI test where a `KeyError` crash and a clean refusal share an exit code.
**Treat the briefs' tests as untrustworthy; their production code as sound.**

### Gate A — MET (2026-08-12). Detail lives in D-157; do not reopen.

Every clause has a measurement. Merged, pushed, green on **all twelve CI jobs at `8475319`, Windows
included** — cite that run and D-157, **not** D-145, which prohibits the claim and was discharged by it.
Review loop CLOSED at round five (D-137), six reports in `.agent/` — **do not re-run any.** Gate A has
moved no program gate. Three facts outlive the detail: **the manifest is written SECOND, not last**
(D-157 corrects D-143); `add_evidence` takes no bundle lock; start any Gate A session with
`git worktree prune`.

> **A closed review loop is evidence about the slices reviewed, not about the subsystem being
> defect-free.** Two silent-success defects (D-138/D-142, D-141) surfaced *after* it closed, in code six
> reviews and four gates had passed. **D-161 and D-162 are the same lesson twice more** — a
> symbol-existence check cannot find a prohibition, and four import walls sit in three test files that no
> document enumerates.

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
| *Projection (active)* | ***MERGED AND PUSHED** — all 22 dispatchable tasks complete and reviewed; whole-branch review clean, gate exit 0 at the merged tree. Task 20 is Mit's* | *P0–P4 build gates met* |
| *Gate B (active)* | *`profile-bundle import` shipped (D-170) — the importer's missing entry point* | ***NOT MET** — nothing imported, no real bundle exists, and candidate extraction does not exist* |

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
3. **What is boardwatch's Windows story?** Investigated 2026-08-13, **parked**. The core is deliberately
   cross-platform so the gate is not theater, but `pyproject.toml:23` publishes `OS Independent` while
   "Windows" appears **zero times** in the docs. Four caveats would have to be named (`pdfinfo`, desktop
   notifications, Task Scheduler, 48 skipped tests); one real bug is in the gaps table below.
4. **The projection spec's own six open questions** (§12), of which two matter soonest: whether
   `tailor run` should validate the projection manifest (it would close the stale-document path but
   crosses the `profile_bundle`↔`tailor` wall), and whether persona's `entries` list survives stage 2.

*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**, ruled 2026-08-13.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **A push run is 9 CI jobs, not 12** | D-151 took Windows off the per-push path (`ci.yml:21-33`): scheduled and `workflow_dispatch` get all three OSes, a push gets ubuntu + macOS, a PR gets ubuntu only. Any "all twelve green" claim describes a *scheduled* run | standing fact |
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
