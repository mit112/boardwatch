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
6,308 tests, **63** leaf CLI commands (counted, 17 of them `profile-bundle`), 6 ATS providers, an 800 MB /
24,073-posting store. **New on 2026-08-14:** the
career-profile lane went 0 → **78 of 81 résumé records `imported`** (D-181) → a renderable graph (D-182) →
**two promoted revisions on the real bundle**, whose résumé surface carries 38 facts, 10 skills and 5 contacts
(D-185, D-186). Milestones on the bundle→résumé path; **nothing has rendered a résumé yet**, and no application
has ever been sent.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. Freezing P3, P6 and the 14-day clock costs nothing, because job-apps
produces Mit's résumés daily (measured: 8/28/24/18 PDFs on 08-09…08-12) — a measurement that corrected a
`STANDING-FACTS` claim that nothing did.

### The active track — Gate B, bundle to résumé

> **NEXT SESSION = the render.** `projection.yaml` (at `{config_dir}`, absent today) is the last artifact
> between revision 2 and a PDF. **Answer this first, it is Mit's:** promotion already derived
> `policy/skill-categories.yaml` *inside* the revisioned bundle, but `projection.yaml` sits *outside* it and
> wants skill ids grouped under labels — so the groupings would live in two places with only one versioned.
> Read `projection/declaration.py` to learn whether v1 can reference the bundle's categories before
> hand-authoring a duplicate. Then `approve-projection` (TTY-only, Mit's) and a render. Note `--scorer` has no
> default (D-168) and Task 20 is unbuilt.

**MERGED and at `revision 2`, all on the real bundle (D-184/185/186).** Gate B is on `main`; the merge review's
one blocker — `validate_mapping_against_catalog` had **no production call site**, so a misrouted mapping
extracted clean at exit 0 — is fixed and pinned by two tests confirmed to fail without it.

**`revision 2` is CURRENT** (`sha256:9917b67b…`, stamp `000002`; revision 1 was `sha256:9d8a202d…`). It
validates **0 error, 0 blocker** and its **résumé surface carries 38 facts, 10 skills, 5 contacts**. The whole
lane ran on Mit's live `resume.yaml` against `{config_dir}/career-profile` — every *earlier* Gate B number came
from a scratch tree. `import` exits **0**, `extract` gives **78/81**, `promote-candidates` gives **6 entities /
47 facts / 10 skills**, `review_required` is **0** (3 records excluded: 1 `no_candidate_assertion`, 2
`owner_excluded` for education). Live draft is **`skills-surfaced`**; `baseline` is spent (see (d) below).

**Gate B is NOT mechanically MET: 9 `missing_review_state` blockers, and they are EVIDENCE, not code.** 38 facts
are owner-confirmed against one attestation; the other 9 cannot be — 3 `employment.organization` need
`private_document_verified` (an employer record) and 6 `project.contribution` need `repository_verified`, whose
*only* legal basis is a repository, so the owner's word is inadmissible by construction. **Evidence is
mandatory, proven not assumed**: confirming all 47 while citing nothing yields 47 `evidence_contract_unmet`
errors. Widening those two predicates in the catalog would clear the gate — versioned data, legitimate, and
deliberately not taken.

**`resume.yaml` is an import source, never hand-fixed (D-155)**, via adapter `boardwatch-resume-v1`. The
denominator is **81 records**, measured not derived: header 2 · education 2 · skill-groups 58 · entry metadata
6 · bullets 13. Design doc: `docs/superpowers/specs/2026-08-14-gate-b-candidate-extraction-design.md` (rev 7;
the five-round review loop is closed, do not reopen, D-172…181).

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
-1. **Gate B's last nine are Mit's documents, not code (D-185).** 3 employer records (Nakshatra, NIO, SAKEC) and
   repository evidence for the 6 `project.contribution` facts (StreakSync, crop-rf, gamified-learning). The
   alternative is a catalog edit widening those two predicates to `owner_attested` — legitimate, since the
   catalog is versioned data, but it weakens a claim to pass a gate and was deliberately not taken.
0. **Carried findings (D-185, D-186).** (a) **RESOLVED in revision 2 — and D-185's claim is retracted (D-186).**
   The skills surface. A `SkillRecord` carries its **own** `verification_state`, which confirming the supporting
   facts never touches; `_surface_coverage` needs that **and** the surface. Only two narrow facts survive: **no
   CLI command confirms a skill** (hand edit; `promote-candidates` is one-shot), and skills are absent from the
   `ApprovalAction` catalog so the edit is not owner-gated. (b) **`add-evidence` cannot take an inline
   capture**, so an owner attestation must be hand-authored, which leaves `manifest.yaml`'s
   `evidence_set_digest` stale until repaired. (c) Promoting `header/1`'s `person.professional_name` is a small
   unbuilt slice — identity.yaml does **not** unblock it. (d) **The bootstrap draft is a one-time dead end**:
   a draft with *no* parent that promotes the first revision can afterwards be neither approved
   (`stale_draft_parent`) nor rebased (`draft_rebase_conflict` on every record) — `checkout` a fresh draft.
   `baseline` is spent; the live draft is `skills-surfaced`.
0b. **Two review findings needing Mit's design call (D-184), both latent today, neither with an obvious fix.**
   (a) **A partial emission silently drops fields**: `run_extraction` records a drain reason only when a record
   produces *no* candidate, so an entry with a malformed date emits its other facts, reaches `imported`, and
   loses the date with nothing recording it — so **"78 of 81 imported" does not mean 78 fully extracted**. The
   report attaches reasons only to `review_required` records, so the fix needs a design change, not a patch.
   All six of Mit's live entries parse, so nothing is lost today. (b) **A skill-id collision silently merges two
   skills** — `C++` and `C#` both slug to `skill.c` and the loser leaves the graph with no diagnostic; Mit's 58
   items yield 58 distinct slugs, so this is a multi-tenancy defect, not a Mit defect.
1. **§5.2 invariant 3** (§5.1's behavioural grounding assertion) — the last owed audit invariant; needs a
   builtin-catalog-backed grounding `ValidationContext`, a heavier fixture than D-183 built.
2. **Education (2 lines) is the agent lane, Slice C** (`free_text_deferred`), declared not decomposed. Both
   lines are `owner_excluded` in revision 1, so they are recorded as deferred, not silently dropped.

*(Done 2026-08-14f: `facts/identity.yaml` authored — Mit Sheth, 5 typed contacts — and the promoted revision
cut. Both were the top two owed items.)*

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
| *Gate B (active)* | ***MERGED to `main`, CI green** (D-184). **`revision 1` is cut** (D-185): the real bundle holds 7 entities, 47 facts, 10 skills, 38 effective, `review_required` 0* | ***NOT MET — 9 blockers**, all `missing_review_state`: 3 `employment.organization` need an employer record, 6 `project.contribution` need repository evidence. Evidence, not code* |

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
