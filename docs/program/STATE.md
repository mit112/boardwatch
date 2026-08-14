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

**The headline number: 0.** Zero job applications have ever come out of boardwatch (`applications` has 0
rows), zero unattended days, zero acceptance days. Against that: 3 published releases, ~46k lines of source,
6,294 tests at 95.6%, 62 CLI commands, 6 ATS providers, an 800 MB / 24,073-posting store. **New this session
(2026-08-14):** the career-profile candidate lane moved from 0 → **78 of 81 résumé records `imported`** (D-181),
and those candidates were then **promoted into the renderable graph** — 6 entities, 47 facts, 10 grounded skills
on the live résumé (D-182). Milestones on the bundle→résumé path, not an application.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. Freezing P3, P6 and the 14-day clock costs nothing, because job-apps
produces Mit's résumés daily (measured: 8/28/24/18 PDFs on 08-09…08-12) — a measurement that corrected a
`STANDING-FACTS` claim that nothing did.

### The active track — Gate B, bundle to résumé

> **NEXT SESSION = review and merge (Mit's decision, 2026-08-14e).** The branch is gate-green and coherent;
> Mit chose to open the next session with the fresh-context Opus-5 whole-branch review (run manually — external
> reviewers are never driven in-session), then merge `gate-b-extraction-slice-a` → `main` if clean. Do the
> review *before* picking up any owed item below.

**`resume.yaml` is an import source, never hand-fixed (D-155)**, via adapter `boardwatch-resume-v1`.
`profile-bundle import` shipped (D-170); it writes `imports/source-ledger.yaml` and nothing else.

**The denominator is MEASURED, not derived (2026-08-14).** The shipped command ran against the live
`resume.yaml` read-only, with `--bundle` on a scratch tree so `{config_dir}` was untouched: **exactly 81
records, all `review_required`, 0 candidates**, scope `complete_file`, buckets **header 2 · education 2 ·
skill-groups 58 · entry metadata 6 · bullets 13** — counted from the ledger file by a separate parser, not
from the command's self-report.

**Exit was 1, not the documented 0**, with exactly one finding: `error: missing_required_file
(facts/identity.yaml)`. `init` omits that file on purpose and the grammar requires it, so exit 1 on a first
import is expected and is **not** about the records. `docs/profile-bundle-authoring.md` and this file both
said exit 0; both are corrected. **Authoring `facts/identity.yaml` is Mit's next concrete step** — a display
name and review dates only he has, which is why `init` refuses to invent them.

**Candidate extraction SHIPPED end to end (D-181) — the number moved from 0.** On branch
**`gate-b-extraction-slice-a`** (unmerged, local; `make check` EXIT=0, 6301 passed), against the live
`resume.yaml` on a fresh v2 bundle, counted through a separate ledger parse: **78 of 81 records reach
`imported`**, **3 stay `review_required`** with the designed drain (2 education `free_text_deferred`, email
`no_predicate_exists`). The `entry_kind_model` interpreter (O1–O6), two new v2 documents, the schema-v2 bump,
and `profile-bundle extract` — full detail in D-181. Design doc:
`docs/superpowers/specs/2026-08-14-gate-b-candidate-extraction-design.md` (rev 7; the five-round review loop is
closed, do not reopen, D-172…181).

**Deliberate departure (D-181, held D-182): `SUPPORTED_SCHEMA_VERSIONS={2}`, no `1→2` migration.** No v1 bundle
exists, so a v1 tree is refused fail-safe (exit 3) rather than migrated by a transform whose only exerciser
would be a fabricated fixture. Widening to `{1,2}` is the additive change owed when a real v1 bundle first needs
upgrading; the tripwire `test_a_previous_schema_fixture_and_a_forward_migration_are_owed_at_v2` still pins it.

**The promotion slice SHIPPED (D-182) — candidates now become the graph.** `profile-bundle promote-candidates
--draft NAME --source SOURCE_ID` turns one source's imported candidates into entities + `FactRecord`s +
`SkillRecord`s (`candidate_promotion.py`, import-wall pure; `authoring.promote_candidates` + CLI mirror `extract`).
Grounded + owner-mediated (Mit's ruling): facts born `unresolved` with **no fabricated evidence**; a skill exists
only where a bullet's `tech_tags` grounds it to an entity (10 of 58; the other 48 familiarity items stay
candidates); categories derived from skill-group labels; **one-shot** (refuses `duplicate_record_id` if entities
or skills already exist). A test proves the graph is exactly one owner confirm/attest/approve step from a
grounded, résumé-surfaced, validating skill — §6.8's stop condition at the validation layer.

**Shipped this session too (D-183), both gate-hardening, no new surface:** §5.2 audit **invariant 4**
(catalog↔mapping reachability) — the reverse half beside its existing forward half, rostering the 31 catalog
predicates the résumé mapping does not reach; and the **`validate_extraction_report` wiring**, now in the imports
**COMPLETENESS** lane (not `validate_imports` as previously stated — a post-import bundle is valid-but-incomplete,
so wiring it into validity broke `import`; the repo won, D-183). The example bundle's empty report was fixed to
explain its one `review_required` record.

**Owed next, in order:**
1. **Mit's prerequisite** — author `facts/identity.yaml` (a display name + review dates only he has); `init`
   omits it, so `extract`/`promote-candidates` exit 1 with `missing_required_file` while still writing their
   output. With identity present they exit 0. (Unblocks `person.professional_name`, which promotion skips today.)
2. **§5.2 invariant 3** (§5.1's behavioural grounding assertion) — the last owed audit invariant; needs a
   builtin-catalog-backed grounding `ValidationContext`, a heavier fixture than D-183 built.
3. **Education (2 lines) is the agent lane, Slice C** (`free_text_deferred`), declared not decomposed.
4. **Then a promoted revision** — the owner confirms/attests/approves the promoted facts and `promote`s, which is
   what makes Gate B mechanically MET (§7a) and a résumé render.

**Two seams to know (D-181):** the builtin catalog and the comprehensive **example** catalog are independent
(D-179), so the example bundle is **not** a valid extraction host for a résumé *with projects* — its
`predicates.yaml` lacks `project.name`; a fresh `init` seeds the builtin catalog+mapping consistently and is the
correct host. And a **degenerate** all-empty-metadata record of a supported kind drains as
`no_mapping_for_locator` (a real résumé never emits one). Reviewed clean otherwise (no correctness/security
blockers).

### Projection — MERGED, PUSHED, CI green. Rulings in D-165…D-170; do not reopen

`projection-v1` fast-forwarded into `main` (46 commits); all 22 dispatchable tasks complete and reviewed. It
ships `profile-bundle approve-projection`, `profile-bundle project` and top-level `resume project`, now
documented in `CHANGELOG.md`.

Three facts outlive the detail. **`LatexRenderer.emit` never reads `Resume.header` or `Resume.education`**
(D-156) — template-hardcoded, so v1 projects only `skill_groups`, `entries`, `extracurricular`, and the bundle
is NOT authoritative for name, contacts or education. **No scorer is picked and none may be picked by
inspection** (D-163): all four are falsified and collapse into two families, so `--scorer` is required with no
default (D-168) until **Task 20** — ten real postings ranked by Mit, still unbuilt, the only arbiter that
exists. **Do not open a session by picking a third scorer.** And the **whole-branch review found two Criticals
all 22 task reviews missed, both in seams** (D-167, D-169).

Carried: the shell's *content* is bound by no digest, so editing it changes the projected header/education
with no re-approval. Small blast radius, per D-156.

### Gate A — MET (2026-08-12). Detail in D-157; do not reopen

Green on all twelve CI jobs at `8475319`, Windows included — cite that run and D-157, **not** D-145. Review
loop CLOSED at round five (D-137); **do not re-run any of the six reports in `.agent/`.** Gate A has moved no
program gate. Three facts outlive it: the manifest is written **SECOND, not last** (D-157 corrects D-143);
`add_evidence` takes no bundle lock; start any Gate A session with `git worktree prune`.

> **A closed review loop is evidence about the slices reviewed, not about the subsystem being defect-free.**
> Two silent-success defects surfaced *after* it closed (D-138/D-142, D-141). D-161/D-162 are the same lesson
> twice more: **four import walls live in three test files and no document enumerates them** — before wiring a
> module into a package, grep `tests/` for what constrains that package's imports. A symbol check cannot find
> a prohibition.

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** — all nine items | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** — P1a + P1b | **MET** (D-032, D-033) |
| P2 Profile + keystone | items 1–7 shipped; item 4 inert for bundled `[software]`; item 7 `work_auth` only; **item 8 NOT STARTED** | **MET AS RECONCILED** (D-075) — evidence is fixtures, not a live run |
| P3 Unattended one command | **COMPLETE** except Docker and Mit's input | **NOT MET** — needs 7 consecutive runs; **frozen** (D-155) |
| P4 Craft gate | **COMPLETE** — items 1–7 | **NOT MET** — the blind craft review is the owner's, never run |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** — three slices (D-110, D-111, D-113) | **NOT MET — 2 of 4**, below; **frozen** |
| 14-day acceptance | not started | — frozen; starts after P6 |
| P7 Breadth | not started | — |
| *Gate A (parallel)* | *complete, merged, CI green* | ***MET*** — *has moved no program gate* |
| *Projection* | ***MERGED AND PUSHED**, reviewed clean. Task 20 is Mit's* | *P0–P4 build gates met* |
| *Gate B (active)* | ***extraction + promotion SHIPPED (D-181, D-182)** on `gate-b-extraction-slice-a` (unmerged, gate-green): interpreter + schema v2 + `extract` (78/81 `imported`) + `promote-candidates` (6 entities, 47 facts, 10 grounded skills)* | ***progressing** — the graph exists; a promoted revision (owner confirm/attest/approve) is what makes Gate B mechanically MET* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days, ≤ 5% | **NOT met.** One-shot baseline **186 surplus of 23,455 = 0.79%**, under the bar but not over 7 days. D-110 changed which callers advance the queue, so an older window is not comparable |
| **0** dead postings reaching the lead list | **NOT met.** Needs a real run whose leads are probed. Recall is low **by design** — 7 of 8 known-dead URLs still answer 200 |
| Injected hash-collision test | **MET** (D-100) — a test, so met outright |
| Audit of 20 sampled suppressions | **MET** (D-101) — 20/20 genuine, 13 employers, deterministic sample |

---

## Open questions — Mit's, not to be resolved by fiat

1. **Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
   Options: leave it; make it fatal; surface it in the run's `errors`.
2. **Should any family other than `work_auth` default to `blocker` severity** (e.g. `clearance`)? Owner-gated
   since D-035.
3. **What is boardwatch's Windows story?** Parked 2026-08-13. The core is deliberately cross-platform so the
   gate is not theater, but `pyproject.toml:23` publishes `OS Independent` while "Windows" appears **zero**
   times in the docs. One real bug is in the gaps table.
4. **The projection spec's six open questions** (§12), of which two matter soonest: whether `tailor run` should
   validate the projection manifest, and whether persona's `entries` list survives stage 2.

*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **A push run is 9 CI jobs, not 12** | D-151 took Windows off the per-push path (`ci.yml:21-33`): scheduled and `workflow_dispatch` get all three OSes, a push gets ubuntu + macOS, a PR ubuntu only. Any "all twelve green" claim describes a *scheduled* run | standing fact |
| **CI can be red for reasons a local gate cannot see, and one is a RACE** | D-171: typer bakes `FORCE_TERMINAL` from `GITHUB_ACTIONS`/`FORCE_COLOR`/`PY_COLORS` at the **first help render in an xdist worker** (`rich_utils` is imported function-locally), so a substring assert on an option name breaks. It looked OS-determined and was not — the same 3.12-ubuntu job failed at one commit and passed at the next over identical tests. `tests/conftest.py` now pops all four vars at import; a test pins `FORCE_TERMINAL is not True` | fixed |
| **Two CI-only jobs: `gitleaks` and `perf`** | `generalization` IS inside `make check` — but it **scans git-TRACKED files only**, so `git add` new files before the gate run you intend to trust. `gitleaks` is installed (8.30.1); run `gitleaks git --log-opts=origin/main..HEAD` before a push. **`All checks passed!` is `generalization`'s banner, not the gate's** — it prints ~4 min early, so the captured exit code is the only check that cannot be read early | mitigated |
| **`resume.yaml` content is Gate B input, NOT a blocker** | Three bullets over the 220-char gate (245 / 234 / 232, two more at 218 / 215), missing Knowledge Forge and Saayam For All, stale `skill_groups`, empty `extracurricular`. **Do not open a session to shorten bullets** — D-155 makes this bundle content. Mit pins `resume_max_pages=1`; never advise 2 | Mit (via Gate B) |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. **Raise it before anyone runs two authoring agents against one bundle** | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: `catalog._verify_families_are_wired` requires a registered resolver and a `Facts` field per family, so a genuinely new field rule is still *code*, not data | owner-gated |
| **Tier B has never run under `boardwatch run`** | `pipeline/runner.py` never constructs an LLM client, so item 10's per-day call volume is zero today (D-146) | owner-gated |
| **The funnel's drop-reason catalog is enumerated by hand in two places** | The AST test's module list is a hard-coded pair; a third emitter escapes a test whose name promises every drop reason. Complete today. Fix is a shared frozen `DropReason` catalog, ~13 call sites (D-147 R4) | unscheduled |
| **`boardwatch export --format csv` to stdout crashes on Windows** | `cli/export_cmd.py:70` writes to bare `sys.stdout`, whose redirected encoding on Windows is the ANSI codepage, so any non-ASCII company name raises `UnicodeEncodeError`. Reproduced. `--out` at `:73` is already correct. **CI cannot see this** | open Q3 |
| **`pdfinfo` is a hard dependency wearing a soft failure** | `cli/doctor_cmd.py:79-88` says so verbatim. Missing tectonic is loud; missing `pdfinfo` returns `None` (`reports/tailor.py:170-171`) laundered into `COMPILE_FAILED`, surfacing only as "every lead failed to tailor (N/N)". Hits `boardwatch run` on every OS. **The projection budget loop must not read this as overflow** | open Q3 |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can ever clear them** | Measured by running the drain, not reading it: `doctor --offline` reaped **1 of 8**. The predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff` (`store/queries.py:183-186`), so **ids 1–4** (2026-08-04/06) are excluded **permanently** — the real leak, needing a repair path nothing proposes. Ids 15–17 were merely younger than the 24 h cutoff; id 8 was the only qualifier. Three earlier descriptions of this row were wrong. `top` is what opens them | P3 |
| **P3 item 8 — cross-OS two-writer WAL test** | Needs a Docker-Linux + macOS-host harness. The documented-stance half shipped (D-041) | P3 |
| **`boardwatch doctor` takes minutes ONLINE only** | `scan/health.py:41-70` probes all 135 boards serially with 1.0 s pacing, 30 s timeout, 3 retries. **`--offline` skips that and is 17 s** — measured, and it still reaps. `ANALYZE` has now run on the live store (27 `sqlite_stat1` rows, first time ever) | unscheduled |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
