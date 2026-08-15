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

**On 2026-08-15 Gate B moved for the first time since it was defined (7 → 4, promoted as revision 6), and
Stage 2 stopped refusing.** Both approvals are spent and **`profile-bundle project` is clean** — no approval
is owed. Read memories `master-reservoir-built-from-wiki` and `option-b-repo-grounded-bullets` before
touching the bundle. **Task 23 is resolved (D-198): the owner adopted `mean_per_bullet` (no clean winner,
tau-b ≤ 0.16).** **The first real emission then CRASHED and was fixed (D-199):** `resume project`'s manifest
re-parsed the declaration's `claims`, which the live `bullet_predicates` declaration leaves empty — a
`strict`-zip mismatch no test covered because every fixture used the claims form. **`resume project
--posting 349` now emits a one-page PDF** (pinned 3 + 3 projects: hookrail, knowledge-forge, crop-rf);
`tailor run` degrades to the untailored fallback (`bullet_too_long` — a bullet exceeds the Tier-A rewrite
length filter; the pre-existing content matter of open Q5, not a bug). **Still 0 applications sent.**

### The active track — the master reservoir (bundle → résumé)

> **The Stage 1 loop is CLOSED**: `~/dev/portfolio-website/wiki` → an **11-entity master bundle** →
> promoted revision → approved `projection.yaml` → `profile-bundle project` renders a **2-page PDF with
> every bullet showing**. The master is a **RESERVOIR** holding the SUPERSET; per-JD **Stage 2** selects it
> down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the source — the wiki is.

**Live revision: `sha256:0f794d81…` (revision 6).** 11 entities — 4 experience (Saayam, NIO co-op,
Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge Forge, StreakSync, Random Forest, FlickSwiper,
BirthdayQuest, Fond). 107 facts (95 effective), 14 skills, **33 bullets**, **6 evidence records** (owner
attestation + five `repository_artifact`, D-191). Validates **0 error**. The PDF renders **zero overfull**
and **two underfull** hboxes in the Skills block — pre-existing, cosmetic, from a trailing `\\`.

**Catalog change (Mit's "Option A"):** `project.contribution` widened to `owner_attested` in **his bundle's**
`policy/predicates.yaml` (the shipped builtin stays strict), so project bullets render on his attestation.
**Facts stay `owner_attested` deliberately** (D-191): `edit-fact` refuses any other basis, so flipping would
forfeit the D-190 edit path for the records iterated most.

**The incremental-edit path SHIPPED (D-190).** A content change rebuilds nothing: `checkout --draft <name>`
→ `edit-fact --fact-id F --value "…"` → `validate` → Mit's TTY `approve` → `promote`. The correction is an
edge (`F.r2` supersedes `F`; the old wording drops out of the render on its own). Batch edits before the
single TTY approve. **Employer headings** are `'{@display_name}'`, so the entity's `display_name` *is* the
rendered line, freely hand-editable (limit ≈ 95 chars; all four fit).

### Stage 2 — unblocked and approved (D-195); no approval owed

`projection.yaml` reads **pinned 3** (`saayam`, `nio-coop`, `sakec`) / **candidates 8** (`nakshatra` + seven
projects); the pinned set alone is 7 bullets → 1 page, so `select` clears its own gate and reaches scoring.
`profile-bundle project` is **clean, exit 0** — bundle `0f794d81…`, projection `c5b237d9…`. Backup:
`projection.yaml.bak-allpinned-20260815`. **The one-page ceiling is 16 bullets, not entries** (D-195): with
3 jobs pinned, **at most two candidates are ever admitted**, and Mit's four-project per-JD sets cannot fit at
one page under any split (most is three, only with two jobs pinned). Previewing needs no approval
(`render-preview-without-tty-approve`); re-promotion and `projection.yaml` edits each stale the stamp
independently (D-167).

**Task 20 is LABELED (D-197, 2026-08-15).** `projection-selection-matrix.md` holds ten real, currently-open
`role=swe` postings (backend ×2, distributed systems, infra, platform, iOS ×2, Android, ML/data, frontend),
JD skills from `posting_context(...).jd_skills`, and the owner's rankings + cut lines over the **eight
candidates** (pinned three excluded, since `agreement.score_all` scores only the ids `case.expected` names).
Every row verified to cover exactly the 8 candidates. **No scorer was run before the label landed** (D-158).
**Task 23 read `score_all` against these labels (D-198):** no clean winner (tau-b ≤ 0.16; `mean_per_bullet`
adopted), and the cut lines fix no score threshold, so `ADMISSION_FLOOR` stays `Decimal(0)`.

### Gate B — 4 blockers, down from 7, on the live revision

**Measured on promoted revision 6, not on a draft:** **4 blockers, 0 errors**, 10 `broken_reference`
warnings (permanent residue of revision 4, superseded not undone — the promotion added none).

- **3 `import_record_undispositioned` — CLEARED** (D-196). The two education rows and the header
  contact line, excluded with reason `owner_excluded`, rationale citing D-156: `LatexRenderer.emit` never
  reads `Resume.header` or `Resume.education`, so they have no consumer in the bundle. Ledger moved
  `review_required` 3 → 0, `excluded` 0 → 3, denominator unchanged at 106. Authorised by
  `approval-stamp.000006` (`controlling_terminal`), which binds all three exclusions to their target digests.
- **4 `missing_review_state` — no CLI path at all.** The `employment.organization` facts, whose predicate is
  `minimum_evidence: private_document` / `owner_attestation_authority: none`, so Mit **cannot attest them**.
  The check fires only on `verification_state == UNRESOLVED` (`completeness.py:187`), and **no shipped CLI
  sets a fact's verification state at all** — these need his employment documents *and* a hand-edit. Closing
  them also unlocks the last cosmetic gap: the template emits everything in argument one, so Experience is a
  single bold line while Education uses the macro properly.

**Owed next — 1 is DONE (artifact produced, reviewed); 2 is Mit's content; do not start 3–4
unilaterally:**

1. **Emit a real projected résumé — DONE (D-199).** The command crashed on first run against the live
   `bullet_predicates` declaration and was fixed. `resume project --posting 349` emits `resume.projected.yaml`
   + manifest; `tailor run 349 --resume …` renders a real one-page PDF
   (`{data_dir}/tailored/untailored-349.pdf`, verified 1 page via `pdfinfo`). The artifact is the untailored
   fallback: one bullet trips the Tier-A length filter (`reason=bullet_too_long`), so JD-aware reordering is
   dropped and the Stage-2 selection renders straight. **What's left is Mit's:** whether to send it, and
   whether to shorten bullets (open Q5) so the *tailored* variant survives the filter. Spotify 13160 still
   admits nothing (skill-orthogonal, D-198) — pick a skill-rich posting.
2. **Individual bullet refinement** (one `edit-fact` per bullet, real numbers only) — also the only lever
   that widens Stage 2's choice, since D-195 caps a page at 16 bullets. **Offered and declined-by-default:**
   hookrail's CI chaos suite (7 failure scenarios, jobs that kill the Postgres primary and Redis master under
   load asserting RPO=0) is the strongest unclaimed material found and was deliberately **not** added — a new
   claim would be asserted on Mit's behalf against an attestation covering only wording he has read (D-191).
3. **§5.2 invariant 3** — the last owed audit invariant; needs a heavy builtin-catalog grounding fixture.
4. **Two D-184 latent findings, both needing a design call** — (a) a partial emission silently drops fields
   (`run_extraction` records a drain reason only when a record produces *no* candidate); all 6 live entries
   parse, so nothing is lost today. (b) A skill-id slug collision silently merges two skills (`C++`/`C#` →
   `skill.c`); Mit's 58 items yield 58 distinct slugs, so it is a multi-tenancy defect. Also unbuilt:
   **Education (Slice C)**, and **promoting `header/1`'s `person.professional_name`**
   (`candidate_promotion.py:180` skips `header/*` unconditionally).

**Carried authoring facts (D-185/186/190/191).** **Three guarantees are each narrower than their name**, and
all three cost a real defect: **`approve` does NOT validate** (only `promote` refuses); **a plain `validate`
cannot see Gate B** (the completeness tier owns it, and every authoring command revalidates at the validity
tier only); and **`_catalog_admits` is a DIFF** refusing only what a write *introduces*, so a write that
silently *removes* findings passes every layer. Always `validate --draft` before Mit approves, and
`--completeness` too for anything touching `policy/`, the ledger or imports — **diff the blocker COUNT, not
just "0 error"**. `add-evidence` needs `--draft --evidence-file --capture`. No CLI confirms a skill. Spent
draft names: `baseline`, `headings`, `nio-heading`, `optionb`, `optionb-fix`, `gate-b-imports`. **D-181:**
the example bundle is not a valid extraction host for a résumé *with projects*; a fresh `init` is.

### Settled tracks — do not reopen

**Projection** (D-163…D-170): 22 tasks merged, CI green. Two facts outlive the detail —
**`LatexRenderer.emit` never reads `Resume.header`/`Resume.education`** (D-156), template-hardcoded (bundle
is NOT authoritative for name/contacts/education); and **no scorer may be picked by inspection** (D-163),
so `select()`'s parameter stays required with no default — but Task 23 adopted `mean_per_bullet` as the
**CLI** `--scorer` default from the labeled matrix (D-198), never a new/third scorer. **Gate A — MET** (D-157): green on all twelve CI jobs at `8475319`; a closed review loop
is evidence about the slices reviewed, not that the subsystem is defect-free (D-161/D-162).

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
| *Projection* | ***MERGED AND PUSHED**, reviewed clean. Task 20 LABELED (D-197); Task 23 — `mean_per_bullet` adopted (D-198); first real emission crashed + fixed (D-199)* | *P0–P4 build gates met* |
| *Gate B / master reservoir (active)* | ***Stage 1 DONE**; **Stage 2 unblocked** (D-195) — pinned 3 / candidates 8, pinned set 7 bullets → 1 page. **Live revision 6, `0f794d81`*** | ***4 blockers, down from 7** (D-196), measured on the live revision. The 4 need Mit's employment documents; no CLI reaches them* |

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
5. **Do the 33 bullets get shortened?** D-195 measured the ceiling at 16 bullets, so a one-page résumé shows
   at most 5 entries' worth. Trimming bullet counts is the only lever that widens Stage 2's choice, and it is
   an `edit-fact` job on content that is Mit's.

*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**; the pinned/candidate split (D-195).)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Emit a real projected résumé — DONE (D-199)** | First emission crashed (`resume project`'s manifest re-parsed `claims`; live decl uses `bullet_predicates` → empty, `strict`-zip mismatch, no test covered it). Fixed + regression-tested. `--posting 349` emits a real one-page PDF; `tailor run` degrades to untailored (`bullet_too_long`). **Left: whether to send + bullet-shortening (Q5) — both Mit's** | Mit |
| **A push run is 9 CI jobs, not 12** | D-151 took Windows off the per-push path (`ci.yml:21-33`): scheduled and `workflow_dispatch` get all three OSes, a push gets ubuntu + macOS, a PR ubuntu only. Any "all twelve green" claim describes a *scheduled* run | standing fact |
| **A contended gate produces FALSE failures** | Running `make check` beside a live subagent turned a green `main` red on three filesystem-timing-sensitive tests. A gate that ran under contention has produced no usable result — re-run alone before diagnosing | standing fact |
| **Two CI-only jobs: `gitleaks` and `perf`** | `generalization` IS inside `make check` — but it **scans git-TRACKED files only**, so `git add` new files before the gate run you intend to trust. Run `gitleaks git --log-opts=origin/main..HEAD` before a push. **`All checks passed!` is `generalization`'s banner, not the gate's** — it prints ~4 min early | mitigated |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle is what renders; wording is `edit-fact`'s job (D-190). Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| **`boardwatch export --format csv` to stdout crashes on Windows** | `cli/export_cmd.py:70` writes to bare `sys.stdout`, whose redirected encoding on Windows is the ANSI codepage, so any non-ASCII company name raises `UnicodeEncodeError`. Reproduced. `--out` at `:73` is already correct. **CI cannot see this** | open Q3 |
| **`pdfinfo` is a hard dependency wearing a soft failure** | `cli/doctor_cmd.py:79-88` says so. Missing tectonic is loud; missing `pdfinfo` returns `None` (`reports/tailor.py:170-171`) laundered into `COMPILE_FAILED`. Hits `boardwatch run` on every OS. **Stage 2's budget loop compiles once per candidate, so it reads this too** | open Q3 |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | The predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff` (`store/queries.py:183-186`), so ids 1–4 are excluded permanently — the real leak, needing a repair path nothing proposes. `top` is what opens them | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
