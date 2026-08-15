# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and record the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Shipped: `CHANGELOG.md`. **Do not re-derive
> `STANDING-FACTS.md`** (D-139). Both logs carry an index spanning themselves and a closed archive
> (D-108): read the index, then the one range — never the whole file.
>
> **States only what is true now**; no sha or commit count (D-017). **Rewrite it, never prepend.** Keep it
> near 170 lines.

---

## Current standing

**The headline number: 0.** Zero job applications have ever come out of boardwatch (`applications` has 0
rows), zero unattended days, zero acceptance days. Against that: 3 published releases, ~46k lines of source,
**6,387 tests, 70 leaf CLI commands (20 `profile-bundle`)**, 6 ATS providers, an 800 MB / 24,073-posting
store.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily. `resume.yaml` is now an **import source, never hand-fixed**, via
adapter `boardwatch-resume-v1`.

**On 2026-08-14 the bundle→résumé lane came alive and was rebuilt into a MASTER RESERVOIR**; on 08-15 its
bullets were grounded against the real repositories (D-191), `exclude-record` merged, and Task 20's matrix
was recorded unlabeled (D-193). Detail: memories `master-reservoir-built-from-wiki` and
`option-b-repo-grounded-bullets` (read before touching the bundle). **Nothing sendable has been produced
yet.**

### The active track — the master reservoir (bundle → résumé)

> **The Stage 1 loop is CLOSED**: `~/dev/portfolio-website/wiki` → an **11-entity master bundle** →
> promoted revision → **approved `projection.yaml`** → `profile-bundle project` serializes the JD-blind
> pool and renders a **2-page PDF with every bullet showing**. The master is a **RESERVOIR**: it holds the
> SUPERSET, and per-JD **Stage 2** selects it down to one page. `resume.yaml` / `sections.tex` are thin
> per-JD OUTPUTS, **not** the source — the wiki is.

**Live bundle: `sha256:a4bdc0b2…` (revision 5), projection approved, `project` clean.** 11 entities — 4
experience (Saayam, NIO co-op, Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge Forge, StreakSync,
Random Forest, FlickSwiper, BirthdayQuest, Fond). 107 facts (95 effective, 12 superseded), 14 skills,
**33 bullets**, **6 evidence records** (owner attestation + five `repository_artifact`, D-191). Validates
**0 error**. The PDF renders **zero overfull** and **two underfull** hboxes in the Skills block —
pre-existing, cosmetic, from a trailing `\\`. *(An earlier claim of zero underfull was never measured.)*

**Re-promoting always stales the projection approval** (D-167), so `project` refuses with
`stale_approval_stamp` until `approve-projection` runs again on a TTY — budget one extra owner approval per
revision. Previewing a PDF needs no approval: memory `render-preview-without-tty-approve`.

**Catalog change (Mit's "Option A"):** `project.contribution` widened to `owner_attested` in **his bundle's**
`policy/predicates.yaml` (the shipped builtin stays strict), so project bullets render on his attestation.
**Facts stay `owner_attested` deliberately** (D-191): `edit-fact` refuses any other basis, so flipping to
`repository_verified` would forfeit the D-190 edit path for the records iterated most.

**The incremental-edit path SHIPPED (D-190).** A content change rebuilds nothing: `checkout --draft <name>`
→ `edit-fact --fact-id F --value "…"` → `validate` → Mit's TTY `approve` → `promote`. `edit-fact` files a
correction **as an edge** — `F.r2` supersedes `F`, which stays immutable and leaves `EFFECTIVE_STATES`, so
the old wording drops out of the render on its own. Batch many edits before the single TTY approve.

**Employer headings — FIXED.** The heading is never the `employment.organization` fact: every heading is
literally `'{@display_name}'`, so the entity's **`display_name`** *is* the rendered line — entity metadata
with no catalog row, hence freely hand-editable. **Measured limit ≈ 95 characters**; all four fit.

### Stage 2 — blocked by a pinning decision, not only by Task 20 (D-193)

**All 11 entries carry `pinned: true`, so `candidate_entry_ids` is empty.** `select` compiles the
pinned-only set first (`select.py:188`) and raises `PINNED_SET_EXCEEDS_BUDGET` at `:190-197`; scoring does
not start until `:203`. Pinned-only *is* the whole 2-page reservoir against a **1-page** budget. So
`resume project --posting --scorer` **cannot return a résumé for any posting or any scorer today**, whatever
Task 20 decides. Fix is one edit to `projection.yaml`, no rebuild, no promotion — **but which entries stay
pinned is Mit's.** His ground truth constrains it: "work experience is largely fixed", yet "Nakshatra =
drop-if-space" means at least one *experience* entry is a candidate.

**Task 20's matrix exists, unlabeled** — `docs/program/projection-selection-matrix.md`, ten real open
`role=swe` postings spanning backend ×2, distributed systems, infrastructure, platform, iOS ×2, Android,
ML/data, frontend, each with its JD skills recorded verbatim from `posting_context(...).jd_skills` (the
call Stage 2 makes; `show` never enumerates them). **Rankings and cut lines are blank and are Mit's alone**
— labeling after seeing a scorer's output is a test that agrees with itself (D-158). **No scorer has been
run.** Mit's answer key so far: SDE = {Hookrail, Knowledge Forge, StreakSync, Random Forest}; iOS =
{StreakSync, FlickSwiper, BirthdayQuest, Fond}.

### Gate B — 7 blockers, and only 3 of them have a shipped path

Measured 2026-08-15, `validate --completeness`: **7 blockers, 0 errors**, 10 `broken_reference` warnings
(permanent residue of revision 4, superseded not undone).

- **3 `import_record_undispositioned`** — `education/1`, `education/2`, `header/2`. Need **no document**:
  disposition is derived, never authored, so only an owner **exclusion** clears them. `exclude-record` is
  now **merged** (D-192) and pre-flighted against the live bundle: 106 records, exactly 3 `review_required`,
  3 matching report entries, zero drift, so **neither guard will false-refuse**. Running it costs Mit one
  TTY `approve`; honest reason for all three is `owner_excluded`.
- **4 `missing_review_state`** — the `employment.organization` facts. `employment.organization` is
  `minimum_evidence: private_document`, `legal_verification_bases: private_document_verified`,
  `owner_attestation_authority: none`, so Mit **cannot attest them**. The check fires only on
  `verification_state == UNRESOLVED` (`completeness.py:187`), and **no shipped CLI sets a fact's
  verification state at all** — so these need his employment documents *and* a hand-edit, the same path the
  reservoir was originally built with. Closing them also unlocks the last cosmetic gap: the template emits
  everything in argument one, so Experience is a single bold line while Education uses the macro properly.

**Owed next — 1 and 2 are Mit's alone; do not start 3–5 unilaterally:**
1. **The pinned/candidate split** (above) and **Task 20's rankings**. Together these are the whole of
   Stage 2. Nothing else blocks a per-JD résumé.
2. **Individual bullet refinement**, ongoing — one `edit-fact` per bullet, real numbers only. **Offered and
   declined-by-default:** hookrail's CI chaos suite (7 failure scenarios, jobs that kill the Postgres
   primary and Redis master under load asserting RPO=0) is the strongest unclaimed material found and was
   deliberately **not** added — a new claim would be asserted on Mit's behalf against an attestation
   covering only wording he has read (D-191).
3. **§5.2 invariant 3** — the last owed audit invariant; needs a heavy builtin-catalog grounding fixture.
4. **Two D-184 latent findings, both needing a design call** — (a) a partial emission silently drops fields
   (`run_extraction` records a drain reason only when a record produces *no* candidate); all 6 live entries
   parse, so nothing is lost today. (b) A skill-id slug collision silently merges two skills (`C++`/`C#` →
   `skill.c`); Mit's 58 items yield 58 distinct slugs, so it is a multi-tenancy defect. Also unbuilt:
   **Education (Slice C)**, deliberately last, and **promoting `header/1`'s `person.professional_name`**
   (`candidate_promotion.py:180` skips `header/*` unconditionally).

**Carried authoring facts (D-185/186/190/191).** **Three guarantees are each narrower than their name**, and
all three cost a real defect: **`approve` does NOT validate** (only `promote` refuses); **a plain `validate`
cannot see Gate B** (the completeness tier owns it, and every authoring command's closing revalidation runs
the validity tier only); and **`_catalog_admits` is a DIFF** refusing only what a write *introduces*, so a
write that silently *removes* findings passes every layer. Always `validate --draft` before Mit approves,
and `--completeness` too for anything touching `policy/`, the ledger or imports — **diff the blocker COUNT,
not just "0 error"**. `add-evidence` needs `--draft --evidence-file --capture`. No CLI confirms a skill;
`baseline` is spent. **D-181:** the builtin and comprehensive-example catalogs are independent, so the
example bundle is not a valid extraction host for a résumé *with projects*; a fresh `init` is.

### Settled tracks — do not reopen

**Projection** (D-163…D-170): all 22 tasks merged and pushed, CI green. Two facts outlive the detail —
**`LatexRenderer.emit` never reads `Resume.header` or `Resume.education`** (D-156), template-hardcoded, so
the bundle is NOT authoritative for name, contacts or education; and **no scorer is picked or may be picked
by inspection** (D-163), so `--scorer` has no default (D-168) until Task 20. **Do not open a session by
picking a third scorer.**

**Gate A — MET** (D-157): green on all twelve CI jobs at `8475319`, Windows included; cite that run, not
D-145. It moved no program gate. What outlives it: **a closed review loop is evidence about the slices
reviewed, not about the subsystem being defect-free** (D-161/D-162).

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** — all nine items | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** — P1a + P1b | **MET** (D-032, D-033) |
| P2 Profile + keystone | items 1–7 shipped; item 4 inert for bundled `[software]`; **item 8 NOT STARTED** | **MET AS RECONCILED** (D-075) — evidence is fixtures, not a live run |
| P3 Unattended one command | **COMPLETE** except Docker and Mit's input | **NOT MET** — needs 7 consecutive runs; **frozen** (D-155) |
| P4 Craft gate | **COMPLETE** — items 1–7 | **NOT MET** — the blind craft review is the owner's, never run |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** — three slices (D-110, D-111, D-113) | **NOT MET — 2 of 4**, below; **frozen** |
| 14-day acceptance | not started | — frozen; starts after P6 |
| P7 Breadth | not started | — |
| *Gate A (parallel)* | *complete, merged, CI green* | ***MET*** — *has moved no program gate* |
| *Projection* | ***MERGED AND PUSHED**, reviewed clean. Task 20 is Mit's* | *P0–P4 build gates met* |
| *Gate B / master reservoir (active)* | ***Stage 1 DONE**: 11-entity master, promoted, projection approved, clean 2-page render. **Revision 5, `a4bdc0b2`**. Bullets repo-grounded (D-191); `exclude-record` merged (D-192); Task 20 matrix recorded unlabeled (D-193)* | ***7 blockers** (3 have a shipped path, 4 need Mit's documents). **Stage 2 returns nothing for any input** until the pinned/candidate split is decided (D-193)* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days, ≤ 5% | **NOT met.** One-shot baseline **186 surplus of 23,455 = 0.79%**, under the bar but not over 7 days. D-110 changed which callers advance the queue |
| **0** dead postings reaching the lead list | **NOT met.** Needs a real run whose leads are probed. Recall is low **by design** — 7 of 8 known-dead URLs still answer 200 |
| Injected hash-collision test | **MET** (D-100) — a test, so met outright |
| Audit of 20 sampled suppressions | **MET** (D-101) — 20/20 genuine, 13 employers, deterministic sample |

---

## Open questions — Mit's, not to be resolved by fiat

1. **Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
2. **Should any family other than `work_auth` default to `blocker` severity** (e.g. `clearance`)? Owner-gated
   since D-035.
3. **What is boardwatch's Windows story?** Parked 2026-08-13. `pyproject.toml:23` publishes `OS Independent`
   while "Windows" appears zero times in the docs. One real bug is in the gaps table.
4. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.

*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Stage 2 returns nothing for any input** | D-193. All 11 entries pinned ⇒ `candidate_entry_ids` empty ⇒ `PINNED_SET_EXCEEDS_BUDGET` before scoring. One edit to `projection.yaml`; the split is Mit's | Mit |
| **A push run is 9 CI jobs, not 12** | D-151 took Windows off the per-push path (`ci.yml:21-33`): scheduled and `workflow_dispatch` get all three OSes, a push gets ubuntu + macOS, a PR ubuntu only. Any "all twelve green" claim describes a *scheduled* run | standing fact |
| **A contended gate produces FALSE failures** | Running `make check` beside a live subagent turned a green `main` red on three filesystem-timing-sensitive tests. A gate that ran under contention has produced no usable result — re-run alone before diagnosing | standing fact |
| **Two CI-only jobs: `gitleaks` and `perf`** | `generalization` IS inside `make check` — but it **scans git-TRACKED files only**, so `git add` new files before the gate run you intend to trust. Run `gitleaks git --log-opts=origin/main..HEAD` before a push. **`All checks passed!` is `generalization`'s banner, not the gate's** — it prints ~4 min early | mitigated |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle is what renders; wording is `edit-fact`'s job (D-190). Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| **`boardwatch export --format csv` to stdout crashes on Windows** | `cli/export_cmd.py:70` writes to bare `sys.stdout`, whose redirected encoding on Windows is the ANSI codepage, so any non-ASCII company name raises `UnicodeEncodeError`. Reproduced. `--out` at `:73` is already correct. **CI cannot see this** | open Q3 |
| **`pdfinfo` is a hard dependency wearing a soft failure** | `cli/doctor_cmd.py:79-88` says so. Missing tectonic is loud; missing `pdfinfo` returns `None` (`reports/tailor.py:170-171`) laundered into `COMPILE_FAILED`. Hits `boardwatch run` on every OS. **The projection budget loop must not read this as overflow** | open Q3 |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | The predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff` (`store/queries.py:183-186`), so ids 1–4 are excluded permanently — the real leak, needing a repair path nothing proposes. `top` is what opens them | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
