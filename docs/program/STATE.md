# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and record the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Rationale: `DECISIONS.md`. Numbers: `METRICS.md`. Shipped:
> `CHANGELOG.md`. **Do not re-derive `STANDING-FACTS.md`** (D-139) — read the section for what you are
> about to touch. Both logs carry an index spanning themselves and a closed archive (D-108): read the
> index, then the one range — never the whole file.
>
> **States only what is true now**; no sha or commit count, both go stale inside one session (D-017).
> **Rewrite it, never prepend.** Keep it near 170 lines.

---

## Current standing

**The headline number: 0.** Zero job applications have ever come out of boardwatch (`applications` has 0
rows), zero unattended days, zero acceptance days. Against that: 3 published releases, ~46k lines of source,
**6,353 tests, 69 leaf CLI commands (19 `profile-bundle`)** — both measured 2026-08-15 — 6 ATS providers, an
800 MB / 24,073-posting store.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily (8/28/24/18 PDFs on 08-09…08-12). `resume.yaml` is now an **import
source, never hand-fixed**, via adapter `boardwatch-resume-v1`.

**On 2026-08-14 the bundle→résumé lane came alive, then was rebuilt into a MASTER RESERVOIR**; on 08-15 its
bullets were grounded against the real repositories. Detail: memories `master-reservoir-built-from-wiki`
and `option-b-repo-grounded-bullets` (read before touching the bundle). Nothing sendable has been produced
yet — **no application sent** — and the résumé is not yet deemed application-worthy.

### The active track — the master reservoir (bundle → résumé)

> **The full loop is CLOSED**: `~/dev/portfolio-website/wiki` (the canonical knowledge base) → an **11-entity
> master bundle** → promoted revision → **approved `projection.yaml`** → `profile-bundle project` serializes
> the JD-blind pool and renders a **2-page PDF with every bullet showing**. The master is a **RESERVOIR**, not
> a résumé: it holds the SUPERSET, and per-JD **Stage 2** (`resume project --posting --scorer`, gated on
> Task 20) selects it down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the
> source — the wiki is.

**Live bundle: `sha256:a4bdc0b2…` (revision 5, 2026-08-15), projection re-approved and `project` clean.**
**11 entities** — 4 experience (Saayam, NIO co-op, Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge
Forge, StreakSync, Random Forest, FlickSwiper, BirthdayQuest, Fond). 107 facts (95 effective, 12
superseded), 14 skills, **33 résumé bullets** (9 experience + 24 project), and **6 evidence records** — the
owner attestation plus five `repository_artifact` captures pinned to full commits (D-191). Validates
**0 error**, and the 2-page PDF renders with **zero overfull** hboxes and **two underfull** ones in the
Skills block — pre-existing, cosmetic, caused by a trailing `\\`. *(This file previously claimed zero
underfull. It was never measured; re-rendering revision 3 through the same path emits the same two.)*

**Re-promoting always stales the projection approval** (D-167 — `pool.py` re-checks the stamp's bundle
digest unconditionally), so `project` refuses with `stale_approval_stamp` until `approve-projection` runs
again on a TTY. Budget one extra owner approval per bundle revision. Previewing a PDF needs no approval at
all: memory `render-preview-without-tty-approve`.

**Mit's Stage-2 selection ground truth (the Task-20 answer key):** SDE = {Hookrail, Knowledge Forge,
StreakSync, Random Forest}; iOS = {StreakSync, FlickSwiper, BirthdayQuest, Fond}; Nakshatra = drop-if-space.

**Catalog change (Mit's "Option A"):** `project.contribution` was widened to `owner_attested` in **his bundle's**
`policy/predicates.yaml` (the shipped builtin stays strict), so project bullets render on his attestation.
Gate B sits at **7 blockers** — 4 `employment.organization` (`private_document`) + 3 `review_required`
import items. Still true: **D-187** (`skill_groups` optional → synthesized) and **D-188**
(`bullet_predicates` render bullets from facts); Path 1 (ClaimRecord) deferred.

**"Option B" is DONE (2026-08-15, D-191).** All five project repositories were measured against the live
bullets and **every one carried a false claim** — 12 bullets corrected (hookrail 219→218 Go files;
StreakSync 335→**446** tests, its "27 warnings" unverifiable and CloudKit removed not shipped; FlickSwiper
128→127 and a "no third-party libraries" overclaim; BirthdayQuest 15/5→**13/4**; Fond's widgets are
iPhone/iPad only, the macOS and visionOS targets having been deleted). Five `repository_artifact` records
now ground them. **Facts stay `owner_attested` deliberately**: `edit-fact` refuses any other basis, so
flipping to `repository_verified` would forfeit the D-190 edit path for the records iterated most.
Knowledge Forge has no repo and Crop-RF is a paper, so both stay attestation-backed.

**The incremental-edit path SHIPPED (2026-08-14, D-190).** A content change rebuilds nothing:
`checkout --draft <name>` → `edit-fact --fact-id F --value "…"` → `validate` → Mit's TTY `approve` →
`promote`, with `promote-candidates` out of the loop. `edit-fact` files a correction **as an edge** — `F.r2`
supersedes `F`, which stays immutable and leaves `EFFECTIVE_STATES`, so the old wording drops out of the
render on its own — and keeps the fact document, the evidence back-citation and `evidence_set_digest` in
agreement. Batch many edits before the single TTY approve.

**Employer headings — FIXED (revisions 2 and 3).** The heading was never the `employment.organization`
fact: every `projection.yaml` heading is literally `'{@display_name}'`, so the entity's **`display_name`**
*is* the whole rendered line. It is entity metadata with no catalog row, hence freely hand-editable —
unlike the org fact, which `edit-fact` can **never** touch (`owner_attestation_authority: none`).
**Measured limit ≈ 95 characters** through tectonic (116 → 95.1pt overfull, 91 → fits); all four now fit.

**Owed next — 1 and 2 are Mit's alone; do not start 3–5 unilaterally:**
1. **Gate B's 7 blockers.** The 4 `missing_review_state` need **Mit's employment documents** (each
   `employment.organization` fact needs `private_document` evidence; `edit-fact` can never touch them). The
   3 `import_record_undispositioned` are `education/1`, `education/2`, `header/2` and need **no document at
   all** — disposition is derived, so only an owner **exclusion** clears them, which is what
   `exclude-record` was built for (D-192, unmerged). Closing the 4 also unlocks the last cosmetic gap: the
   template emits `\resumeSubheading{...}{}{}{}` with everything in argument one, so Experience is a single
   bold line while **Education uses the macro properly**. The heading grammar admits `{predicate}`
   placeholders, so `'{employment.title} — {employment.organization} — {employment.date_range} —
   {entity.location}'` is expressible the day `employment.organization` resolves.
2. **Individual bullet refinement**, ongoing, before the résumé is application-worthy — one `edit-fact` per
   bullet, real numbers only. **Offered and declined-by-default:** hookrail's CI chaos suite (7 failure
   scenarios, jobs that kill the Postgres primary and Redis master under load asserting RPO=0) is the
   strongest unclaimed material found and was deliberately **not** added — a new claim would be asserted on
   Mit's behalf against an attestation covering only wording he has read (D-191).
3. **Stage 2 / Task 20** — the scorer that turns the reservoir into per-JD résumés; needs Mit's posting
   rankings (his SDE/iOS sets above are the start). **This is now the binding constraint on a sendable
   per-JD résumé.**
4. **§5.2 invariant 3** — the last owed audit invariant; needs a heavy builtin-catalog grounding fixture.
   Get Mit's effort/value call.
5. **Two D-184 latent findings, both needing a design call** — (a) a partial emission silently drops fields
   (`run_extraction` records a drain reason only when a record produces *no* candidate, so a malformed date
   emits its other facts and reaches `imported` losing the date). All 6 live entries parse, so nothing is
   lost today. (b) A skill-id slug collision silently merges two skills (`C++`/`C#` → `skill.c`); Mit's 58
   items yield 58 distinct slugs, so it is a multi-tenancy defect. Also unbuilt: **Education (Slice C)**,
   deliberately last, and **promoting `header/1`'s `person.professional_name`** (`candidate_promotion.py:180`
   skips `header/*` unconditionally).

**Carried authoring facts (D-185/186/190/191).** **Three guarantees are each narrower than their name**, and
all three cost a real defect to learn: **`approve` does NOT validate** (it checks manifest type, parent
digest, quarantined captures — nothing else, so a draft with four errors stamps cleanly and only `promote`
refuses); **a plain `validate` cannot see Gate B** (the completeness tier owns it, and every authoring
command's closing revalidation runs the validity tier only — so `clean` from `edit-fact` says nothing about
whether Gate B moved); and **`_catalog_admits` is a DIFF** that refuses only what a write *introduces*, so a
write that silently *removes* findings passes every layer. Always `validate --draft` before Mit approves,
and `--completeness` too for anything touching `policy/`, the ledger or imports. `add-evidence` needs
`--draft --evidence-file --capture`; a hand edit leaves `evidence_set_digest` stale (take the computed one
from `validate --json`). No CLI confirms a skill; each bundle gets one `init` draft and `baseline` is spent.
**Two seams (D-181):** the builtin and comprehensive-example catalogs are independent (D-179), so the
example bundle is not a valid extraction host for a résumé *with projects*; a fresh `init` is.

### Projection — MERGED, PUSHED, CI green. Rulings in D-163…D-170; do not reopen

All 22 tasks complete. Ships `approve-projection`, `project`, top-level `resume project`. Two facts outlive
the detail: **`LatexRenderer.emit` never reads `Resume.header` or `Resume.education`** (D-156) —
template-hardcoded, so the bundle is NOT authoritative for name, contacts or education and a faithful
preview needs a template carrying them. **No scorer is picked and none may be picked by inspection**
(D-163): all four are falsified, so `--scorer` has no default (D-168) until **Task 20**, ten real postings
ranked by Mit, the only arbiter. **Do not open a session by picking a third scorer.**

### Gate A — MET (2026-08-12). Detail in D-157; do not reopen

Green on all twelve CI jobs at `8475319`, Windows included — cite that run and D-157, **not** D-145. It has
moved no program gate. What outlives it: **a closed review loop is evidence about the slices reviewed, not
about the subsystem being defect-free** (D-161/D-162).

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
| *Gate B / master reservoir (active)* | ***DONE loop**: 11-entity master from `~/dev/portfolio-website/wiki` (4 exp + 7 projects, 33 bullets), promoted, projection approved, clean 2-page render. **Revision 5, bundle `a4bdc0b2`** (2026-08-15). Incremental edits ship (D-190); bullets are repo-grounded (D-191). See memory `option-b-repo-grounded-bullets`* | ***7 blockers left**, measured 2026-08-15 (4 `missing_review_state` + 3 `import_record_undispositioned`, 0 errors). Résumé not yet application-worthy — bullets still refined; Stage 2 (per-JD) needs Task 20* |

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
   gate is not theater, but `pyproject.toml:23` publishes `OS Independent` while "Windows" appears zero times
   in the docs. One real bug is in the gaps table.
4. **The projection spec's six open questions** (§12), of which two matter soonest: whether `tailor run` should
   validate the projection manifest, and whether persona's `entries` list survives stage 2.

*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **`exclude-record` is BUILT but PARKED, unmerged** | D-192. Three commits on `worktree-agent-af5fde0288e79b376`, `make check` green at exit 0 (6381 passed), re-run rather than taken from the builder. Clears Gate B's 3 `import_record_undispositioned` blockers. Held back because the last commit — the drain guard — is the one change no fresh reviewer has seen, and each of three rounds found a real defect. **Merge owes one review.** Same class, still open elsewhere: `source_scope_target_digest` has the identical dict/list divergence, zero callers, no pinning test | Mit |
| **A push run is 9 CI jobs, not 12** | D-151 took Windows off the per-push path (`ci.yml:21-33`): scheduled and `workflow_dispatch` get all three OSes, a push gets ubuntu + macOS, a PR ubuntu only. Any "all twelve green" claim describes a *scheduled* run | standing fact |
| **CI can be red for a reason a local gate cannot see, and one is a RACE** | D-171: typer bakes `FORCE_TERMINAL` from `GITHUB_ACTIONS`/`FORCE_COLOR`/`PY_COLORS` at the first help render in an xdist worker, so a substring assert on an option name breaks. It looked OS-determined and was not. `tests/conftest.py` now pops all four vars at import; a test pins `FORCE_TERMINAL is not True` | fixed |
| **Two CI-only jobs: `gitleaks` and `perf`** | `generalization` IS inside `make check` — but it **scans git-TRACKED files only**, so `git add` new files before the gate run you intend to trust. Run `gitleaks git --log-opts=origin/main..HEAD` before a push. **`All checks passed!` is `generalization`'s banner, not the gate's** — it prints ~4 min early, so the captured exit code is the only check that cannot be read early | mitigated |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle is what renders; wording is `edit-fact`'s job (D-190). Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| **`boardwatch export --format csv` to stdout crashes on Windows** | `cli/export_cmd.py:70` writes to bare `sys.stdout`, whose redirected encoding on Windows is the ANSI codepage, so any non-ASCII company name raises `UnicodeEncodeError`. Reproduced. `--out` at `:73` is already correct. **CI cannot see this** | open Q3 |
| **`pdfinfo` is a hard dependency wearing a soft failure** | `cli/doctor_cmd.py:79-88` says so. Missing tectonic is loud; missing `pdfinfo` returns `None` (`reports/tailor.py:170-171`) laundered into `COMPILE_FAILED`, surfacing only as "every lead failed to tailor (N/N)". Hits `boardwatch run` on every OS. **The projection budget loop must not read this as overflow** | open Q3 |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | The predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff` (`store/queries.py:183-186`), so ids 1–4 (2026-08-04/06) are excluded permanently — the real leak, needing a repair path nothing proposes. `top` is what opens them | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
