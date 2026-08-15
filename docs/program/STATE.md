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
6,308 tests, 63 leaf CLI commands (17 `profile-bundle`), 6 ATS providers, an 800 MB / 24,073-posting store.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily (8/28/24/18 PDFs on 08-09…08-12). `resume.yaml` is now an **import
source, never hand-fixed**, via adapter `boardwatch-resume-v1`.

**On 2026-08-14 the bundle→résumé lane came alive, then was rebuilt into a MASTER RESERVOIR.** Full detail
and the rebuild recipe: **memory `master-reservoir-built-from-wiki`** (read it before touching the bundle).
Nothing sendable has been produced yet — **no application sent** — and Mit has not deemed the résumé
application-worthy; individual bullets still get refined.

### The active track — the master reservoir (bundle → résumé)

> **The full loop is CLOSED**: `~/dev/portfolio-website/wiki` (the canonical knowledge base) → an **11-entity
> master bundle** → promoted revision → **approved `projection.yaml`** → `profile-bundle project` serializes
> the JD-blind pool and renders a **2-page PDF with every bullet showing**. The master is a **RESERVOIR**, not
> a résumé: it holds the SUPERSET, and per-JD **Stage 2** (`resume project --posting --scorer`, gated on
> Task 20) selects it down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the
> source — the wiki is.

**Live bundle: `sha256:206786a3…` (revision 3, 2026-08-15).** Revision 2 re-authored the four employer
headings and organization values; revision 3 shortened the NIO heading to fit. **The projection approval is
now STALE** — `projection/pool.py` re-checks the stamp's bundle digest unconditionally (D-167), so
`profile-bundle project` refuses with `stale_approval_stamp` until Mit runs `approve-projection` again on a
TTY. A preview render needs no approval: see memory `render-preview-without-tty-approve`. **11 entities** — 4
experience (Saayam, NIO co-op, Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge Forge, StreakSync, Random
Forest, FlickSwiper, BirthdayQuest, Fond). ~95 facts, **91 owner-confirmed**, 14 skills, **33 résumé bullets**
(9 experience + 24 project), all wiki-grounded with real metrics. Validates **0 error**.

**Mit's Stage-2 selection ground truth (the Task-20 answer key):** SDE = {Hookrail, Knowledge Forge,
StreakSync, Random Forest}; iOS = {StreakSync, FlickSwiper, BirthdayQuest, Fond}; Nakshatra = drop-if-space.

**Catalog change (Mit's "Option A"):** `project.contribution` was widened to `owner_attested` in **his bundle's**
`policy/predicates.yaml` (the shipped builtin stays strict), so project bullets render on his attestation. This
dropped Gate B to **7 blockers** — 4 `employment.organization` (`private_document`) + 3 `review_required`
import items; the 11 project contributions are now resolved. "Option B" (LATER, new session): supply repo
evidence per project AND use the repos to sharpen the bullets. Still true from before: **D-187** (`skill_groups`
optional → synthesized) and **D-188** (`bullet_predicates` render bullets from facts); Path 1 (ClaimRecord)
deferred.

**The incremental-edit path SHIPPED (2026-08-14, D-190)** — the top workflow debt is cleared. A content
change no longer rebuilds anything: `checkout --draft <name>` → `profile-bundle edit-fact --fact-id F
--value "…"` → `validate` → Mit's TTY `approve` → `promote`. `promote-candidates` is out of the loop, so its
one-shot guard never fires. `edit-fact` files a correction **as an edge** — a successor `F.r2` supersedes `F`,
which stays immutable and leaves `EFFECTIVE_STATES`, so the old wording drops out of the render on its own.
`add-fact` writes a new fact. Both keep the three documents an edit touches in agreement (the fact document,
`evidence/records.yaml`'s back-citation, and the manifest's `evidence_set_digest`). Verified on Mit's real
bundle: editing one BirthdayQuest bullet validates **0 error** and the entry still renders 3 bullets, not 4.
The TTY `approve` is unchanged and stays — its frequency drops from per-rebuild to per-batch.

**Owed next (mostly owner-gated; the reservoir loop itself is DONE):**
1. **Individual bullet refinement** — Mit's, ongoing, before the résumé is application-worthy. **Adding
   metrics is now cheap** — one `edit-fact` per bullet. Source real numbers from the wiki/repos, never
   fabricate.
2. **Option B** — ground project bullets against the real repos (new session).
3. **Employer headings — FIXED 2026-08-15 (revisions 2 and 3).** The heading was never the
   `employment.organization` fact: every `projection.yaml` heading is literally `'{@display_name}'`, so the
   entity's **`display_name`** *is* the whole rendered line, and it held "Title — Org — Dates — Location"
   at up to 143 characters. `display_name` is entity metadata with no catalog row, so it is freely
   hand-editable. **Measured limit: ~95 characters** (116 → 95.1pt overfull, 99 → 13.8pt, 91 → fits;
   measured through tectonic, not estimated). All four now fit — 82 / 77 / 77 / 91 — and the render has
   **zero overfull and zero underfull hboxes**. The 4 `employment.organization` fact values were also
   re-authored to just the employer name; they are `unresolved`, so this changes nothing visible today but
   is correct data for when the documents land.
   **Two things that stay true:** `edit-fact` can never touch those org facts — the catalog row is
   `legal_verification_bases: [private_document_verified]` with `owner_attestation_authority: none`, so the
   owner may never attest the predicate and `edit-fact` corrects only `owner_attested` facts. And the
   remaining cosmetic gap is structural: the template emits `\resumeSubheading{...}{}{}{}` with all four
   arguments crammed into the first, so Experience is one bold line while **Education uses the macro
   properly** (title left, dates right). The real fix is teaching the projection to emit the four parts
   separately — the heading grammar already admits `{predicate}` placeholders, so
   `'{employment.title} — {employment.organization} — {employment.date_range} — {entity.location}'` is
   expressible today and blocked only by `employment.organization` being `unresolved`.
4. **Stage 2 / Task 20** — the scorer that turns the reservoir into per-JD résumés; needs Mit's posting
   rankings (his SDE/iOS sets above are the start).

**Owed next (all owner-gated or frozen — do not start unilaterally):**
1. **Gate B's 9** — Mit's documents (above). Highest-leverage step to a sendable résumé.
2. **§5.2 invariant 3** — the last owed audit invariant; needs a heavy builtin-catalog grounding fixture.
   Get Mit's effort/value call.
3. **Two D-184 latent findings, both needing a design call** — (a) a partial emission silently drops fields
   (`run_extraction` records a drain reason only when a record produces *no* candidate, so a malformed date
   emits its other facts and reaches `imported` losing the date; "78 of 81 imported" ≠ 78 fully extracted).
   All 6 live entries parse, so nothing is lost today. (b) A skill-id slug collision silently merges two
   skills (`C++`/`C#` → `skill.c`); Mit's 58 items yield 58 distinct slugs, so it is a multi-tenancy defect.
4. **Education (Slice C)** — the agent lane, `owner_excluded`, declared not decomposed, deliberately last.
5. **Promote `header/1`'s `person.professional_name`** — small unbuilt slice; `candidate_promotion.py:180`
   skips `header/*` unconditionally, and `identity.yaml` does not unblock it.

**Carried authoring facts (D-185/186):** `add-evidence` needs `--draft --evidence-file --capture`; hand-authoring
evidence leaves `manifest.yaml`'s `evidence_set_digest` stale (get the computed digest from `validate --json`).
No CLI command confirms a skill (hand edit; `promote-candidates` is one-shot); skills are absent from the
`ApprovalAction` catalog. The bootstrap draft is a one-time dead end — `checkout` a fresh draft; `baseline` is
spent. **Two seams (D-181):** the builtin and comprehensive-example catalogs are independent (D-179), so the
example bundle is not a valid extraction host for a résumé *with projects* — a fresh `init` seeds the builtin
catalog+mapping consistently and is the correct host.

### Projection — MERGED, PUSHED, CI green. Rulings in D-163…D-170; do not reopen

`projection-v1` fast-forwarded into `main`; all 22 tasks complete and reviewed. Ships `profile-bundle
approve-projection`, `profile-bundle project`, top-level `resume project`. Three facts outlive the detail:
**`LatexRenderer.emit` never reads `Resume.header` or `Resume.education`** (D-156) — template-hardcoded, so v1
projects only `skill_groups`, `entries`, `extracurricular`; the bundle is NOT authoritative for name, contacts
or education, and a faithful preview needs a template carrying real header/education. **No scorer is picked
and none may be picked by inspection** (D-163): all four are falsified and collapse into two families, so
`--scorer` is required with no default (D-168) until **Task 20** — ten real postings ranked by Mit, still
unbuilt, the only arbiter. **Do not open a session by picking a third scorer.** The shell's *content* is bound
by no digest, so editing it changes the projected header/education with no re-approval (small blast radius).

### Gate A — MET (2026-08-12). Detail in D-157; do not reopen

Green on all twelve CI jobs at `8475319`, Windows included — cite that run and D-157, **not** D-145. Gate A
has moved no program gate. `add_evidence` takes no bundle lock; start any Gate A session with `git worktree
prune`. **A closed review loop is evidence about the slices reviewed, not about the subsystem being
defect-free** — before wiring a module into a package, grep `tests/` for what constrains its imports; a symbol
check cannot find a prohibition (D-161/D-162).

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
| *Gate B / master reservoir (active)* | ***DONE loop** (2026-08-14): 11-entity master built from `~/dev/portfolio-website/wiki` (4 exp + 7 projects, 33 bullets), promoted, **projection approved**, 2-page render with every bullet. Bundle `268b7c78`, projection `5642175e`. See memory `master-reservoir-built-from-wiki`* | ***7 blockers left** (4 `employment.organization` + 3 import items); project contributions resolved via the `owner_attested` widening. Résumé not yet application-worthy — bullets still refined; Stage 2 (per-JD) needs Task 20* |

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
| **A push run is 9 CI jobs, not 12** | D-151 took Windows off the per-push path (`ci.yml:21-33`): scheduled and `workflow_dispatch` get all three OSes, a push gets ubuntu + macOS, a PR ubuntu only. Any "all twelve green" claim describes a *scheduled* run | standing fact |
| **CI can be red for a reason a local gate cannot see, and one is a RACE** | D-171: typer bakes `FORCE_TERMINAL` from `GITHUB_ACTIONS`/`FORCE_COLOR`/`PY_COLORS` at the first help render in an xdist worker, so a substring assert on an option name breaks. It looked OS-determined and was not. `tests/conftest.py` now pops all four vars at import; a test pins `FORCE_TERMINAL is not True` | fixed |
| **Two CI-only jobs: `gitleaks` and `perf`** | `generalization` IS inside `make check` — but it **scans git-TRACKED files only**, so `git add` new files before the gate run you intend to trust. Run `gitleaks git --log-opts=origin/main..HEAD` before a push. **`All checks passed!` is `generalization`'s banner, not the gate's** — it prints ~4 min early, so the captured exit code is the only check that cannot be read early | mitigated |
| **`resume.yaml` content is Gate B input, NOT a blocker** | Three bullets over the 220-char gate, missing Knowledge Forge and Saayam For All, stale `skill_groups`, empty `extracurricular`. **Do not open a session to shorten bullets** — D-155 makes this bundle content. Mit pins `resume_max_pages=1`; never advise 2 | Mit (via Gate B) |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| **`boardwatch export --format csv` to stdout crashes on Windows** | `cli/export_cmd.py:70` writes to bare `sys.stdout`, whose redirected encoding on Windows is the ANSI codepage, so any non-ASCII company name raises `UnicodeEncodeError`. Reproduced. `--out` at `:73` is already correct. **CI cannot see this** | open Q3 |
| **`pdfinfo` is a hard dependency wearing a soft failure** | `cli/doctor_cmd.py:79-88` says so. Missing tectonic is loud; missing `pdfinfo` returns `None` (`reports/tailor.py:170-171`) laundered into `COMPILE_FAILED`, surfacing only as "every lead failed to tailor (N/N)". Hits `boardwatch run` on every OS. **The projection budget loop must not read this as overflow** | open Q3 |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | The predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff` (`store/queries.py:183-186`), so ids 1–4 (2026-08-04/06) are excluded permanently — the real leak, needing a repair path nothing proposes. `top` is what opens them | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
