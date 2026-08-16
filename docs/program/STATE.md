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
**6,411 tests, 70 leaf CLI commands (20 `profile-bundle`)**, 6 ATS providers, an 800 MB / 24,073-posting
store.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily. `resume.yaml` is now an **import source, never hand-fixed**, via
adapter `boardwatch-resume-v1`.

**On 2026-08-15 the bundle → résumé track reached a shippable state.** Gate B moved 7 → 4 → **0**:
the four `employment.organization` facts were resolved by widening that predicate to owner-attestable
(mirroring its siblings) and attesting the employer names (D-201, **promoted as revision 7**) — **Gate B is
MET for the first time.** The first real emission crashed and was fixed (D-199). The emitted résumé's
**formatting was then fixed (D-200):** Experience renders the proper two-line macro (was one crammed bold
line), Projects render `Name | tech | link · dates`, clickable project links shipped as a code feature, and
the company name is now fact-grounded. Task 23 adopted `mean_per_bullet` (D-198). **Still 0 applications
sent** — a polished, fact-grounded, Gate-B-clean one-page résumé now renders; sending is Mit's. `tailor run`
still degrades to the untailored fallback (`bullet_too_long`, open Q5). The owner then re-approved and re-ran
(`approve-projection` + `resume project` + `tailor run`): the polished résumé — GitHub/App Store links +
fact-grounded company — is **now live** (fresh `untailored-349.pdf`, 14:45); the projection stamp matches
the current declaration.

**With the résumé track shippable, the program pivoted to post-Gate-B robustness, and the scoped autonomous
backlog is now shipped in full.** A multi-tenancy sweep found `candidate_promotion.py` is the only
lossy-id-creation site in `src/`; **all four of its slug-collision sites now refuse** rather than silently
merging — skill_id (D-202), entity_id + category_id (D-203), fact_id (D-205). The fourth was missed by the
sweep's own enumeration and found by the pre-push review of D-203, whose "the whole class is now refused"
claim was retracted *before* it was pushed. Alongside it: a missing `pdfinfo` is now a run-level fatal
instead of a laundered `COMPILE_FAILED` (D-204), CSV export to stdout is UTF-8 (D-206), **§5.2 invariant 3 —
the last owed audit invariant — ships**, and two fixture-drift fixes now fail on model/mapping drift.

### The active track — the master reservoir (bundle → résumé)

> **The Stage 1 loop is CLOSED**: `~/dev/portfolio-website/wiki` → an **11-entity master bundle** →
> promoted revision → approved `projection.yaml` → `profile-bundle project` renders a **2-page PDF with
> every bullet showing**. The master is a **RESERVOIR** holding the SUPERSET; per-JD **Stage 2** selects it
> down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the source — the wiki is.

**Live revision: `sha256:23ff1ef9…` (revision 7).** 11 entities — 4 experience (Saayam, NIO co-op,
Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge Forge, StreakSync, Random Forest, FlickSwiper,
BirthdayQuest, Fond). 107 facts (**99 effective** — the 4 `employment.organization` facts resolved to
`owner_confirmed`, D-201), 14 skills, **33 bullets**, **7 evidence records** (two owner-attestation incl. the
new `evidence.mit.employer-names.001` + five `repository_artifact`). Validates **0 error, 0 blocker** (Gate B
MET). The PDF renders **zero overfull** and two underfull hboxes in the Skills block — pre-existing, cosmetic.

**Catalog change (Mit's "Option A"):** `project.contribution` widened to `owner_attested` in **his bundle's**
`policy/predicates.yaml` (the shipped builtin stays strict), so project bullets render on his attestation.
**Facts stay `owner_attested` deliberately** (D-191): `edit-fact` refuses any other basis, so flipping would
forfeit the D-190 edit path for the records iterated most.

**The incremental-edit path SHIPPED (D-190).** A content change rebuilds nothing: `checkout --draft <name>`
→ `edit-fact --fact-id F --value "…"` → `validate` → Mit's TTY `approve` → `promote`. The correction is an
edge (`F.r2` supersedes `F`; the old wording drops out of the render on its own). Batch edits before the
single TTY approve. **Employer headings** are `'{@display_name}'`, so the entity's `display_name` *is* the
rendered line, freely hand-editable (limit ≈ 95 chars; all four fit).

### Stage 2 — unblocked (D-195); the D-200/D-201 formatting changes are approved and live

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

### Gate B — MET (0 blockers) on revision 7

**Measured on promoted revision 7:** **0 error, 0 blocker**, 10 `broken_reference` warnings (permanent
residue of earlier revisions, non-blocking). The path to zero:

- **3 `import_record_undispositioned` — CLEARED** (D-196): the two education rows + the header contact line,
  excluded as `owner_excluded` (no consumer — `LatexRenderer.emit` never reads `Resume.header`/`education`).
- **4 `missing_review_state` — CLEARED** (D-201): the `employment.organization` predicate was the odd sibling
  (`title`/`date_range`/`team_size` already permitted owner attestation; it did not), so it was **widened to
  owner-attestable**; the 4 org facts flipped to `owner_confirmed`/`owner_attested`; and a **new scoped
  attestation** `evidence.mit.employer-names.001` was filed via `add-evidence`. All hand-edits (no CLI sets a
  fact's verification state); owner approved + promoted → revision 7. **This also fact-grounded the résumé
  company name** — the last thing the D-200 formatting needed.

**Owed next.** The bundle → résumé track is complete; its remaining items (1–2) are Mit's. A scoped
**autonomous engineering backlog** (3) needs no owner input. Item 4 is **owner-gated — do not start**.

1. **Résumé emit/format/Gate B — DONE (D-199/D-200/D-201).** The polished one-page résumé is live
   (`untailored-349.pdf`); **sending is Mit's.** `tailor run` degrades to the untailored fallback
   (`bullet_too_long`, open Q5). *Mit's calls:* fact-grounding the dates (needs a canonical-format choice —
   `{employment.date_range}` renders raw ISO) and shortening the 2 over-length bullets to lift the fallback.
2. **Individual bullet refinement** (one `edit-fact` per bullet, real numbers) — Mit's content (D-191); also
   the only lever that widens Stage 2's choice (D-195 caps a page at 16 bullets). Hookrail's CI-chaos suite is
   the strongest unclaimed material, deliberately **not** added (no attestation for wording Mit has not read).
3. **Autonomous engineering backlog — COMPLETE, nothing owed.** All five items the 2026-08-15 4-agent sweep
   scoped shipped on 2026-08-15k; listed only so a fresh session does not re-scope them. Slug-collision class
   **CLOSED, all four sites** (D-202/D-203/D-205); **§5.2 invariant 3 SHIPS** — the last owed audit invariant;
   `pdfinfo` fatal (D-204); CSV stdout UTF-8 (D-206); both fixture-drift fixes derived from live models/config
   and proven red on a mutated source copy. **One residual, low priority, deliberately unfixed:**
   `candidate_promotion.py`'s `_merge_categories` still files a user's slug-colliding label under a
   pre-existing catalog category of a different `display_name` (`if category_id not in known`). Whether the
   catalog or the author owns `display_name` is a genuine design question, so it is not a clear defect.
4. **Owner-gated — do NOT start unilaterally:** **one skill listed in two skill groups silently gets one of
   them as its category** (found by the 2026-08-15k pre-push review). `candidate_promotion.py`'s skill-item
   loop assigns `skill_id_to_label[skill_id]` by bare last-write-wins over an *unsorted* `candidates`, so
   `Python` under both `Languages` and `Backend` yields one `SkillRecord` whose category is whichever
   candidate arrived last. **Reachable with an entirely ordinary résumé, not an adversarial one** — but it is
   *not* the slug-collision class (no id is lost, and `SkillRecord.category` is singular, so some choice is
   forced). Needs a ruling — refuse and make the author pick, or pick deterministically and document the
   rule — and both are defensible, which is why it was not decided unilaterally. Also:
   **`_merge_categories`** (same file), where a user's slug-colliding label is filed under a pre-existing
   catalog category of a different `display_name`; same shape of question (does the catalog or the author own
   `display_name`?). Also: **D-184 finding 2** (partial emission silently drops fields;
   `run_extraction` records a reason only when a record produces *no* candidate — redefines the Gate B
   accounting contract, 4 mutually-exclusive designs, nothing lost today); the provider ATS-fixture +
   eligibility-corpus drift (need live network / a missing generator); **Education Slice C**; promoting
   `header/1`'s `person.professional_name` (`candidate_promotion.py`'s skill-item loop skips `header/*`).

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
| *Gate B / master reservoir* | ***Stage 1 + Stage 2 DONE**; résumé formatting fixed + links shipped (D-200). **Live revision 7, `23ff1ef9`*** | ***MET — 0 blockers** (D-201): the 4 `employment.organization` facts resolved by owner attestation + a predicate widen. First zero-blocker Gate B ever* |

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
   while "Windows" appears zero times in the docs. **The one real bug is now fixed (D-206)**, so what is left
   is purely the support-posture claim — which no code change can settle.
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
| **`boardwatch export --format csv` to stdout — FIXED (D-206)** | The stdout branch now writes through a locally-wrapped UTF-8 `TextIOWrapper`, flushed and detached, matching what `--out` always did. Global stdout is never mutated. **CI still cannot see the original crash** (every per-push runner defaults to UTF-8), so the regression drives an `ascii`-encoded stdout instead | closed |
| **`pdfinfo` soft failure — FIXED (D-204)** | A missing `pdfinfo` is now `BINARY_MISSING` in `_default_runner`, i.e. run-level fatal like `tectonic`, with a poppler install message. It no longer launders into `COMPILE_FAILED`, so it cannot present as a silent empty run. Stage 2's budget loop reads the same fixed path | closed |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | The predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff` (`store/queries.py:183-186`), so ids 1–4 are excluded permanently — the real leak, needing a repair path nothing proposes. `top` is what opens them | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
