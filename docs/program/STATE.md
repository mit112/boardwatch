# PROGRAM STATE — read this first

> The one file a fresh session with zero memory reads to know where the program stands.
> **If it disagrees with the repo, the repo wins** — fix this file and record the correction in
> `DECISIONS.md`. Plan: `PROGRAM.md`. Numbers: `METRICS.md`. Shipped: `CHANGELOG.md`. **Do not re-derive
> `STANDING-FACTS.md`** (D-139). Both logs carry an index spanning themselves and a closed archive
> (D-108): read the index, then the one range — never the whole file.
>
> **States only what is true now**; no sha or commit count (D-017). **Rewrite it, never prepend.** Keep it
> near 170 lines: how something got here is narration, and narration belongs in `DECISIONS.md` /
> `METRICS.md`. Before cutting a sentence, check it exists somewhere else (D-149).

---

## Current standing

**The headline number: 0.** Zero job applications have ever come out of boardwatch (`applications` has 0
rows), zero unattended days, zero acceptance days. Against that: 3 published releases, ~53k lines of source,
**6,439 tests** (6,435 passing + 4 xfailed), **70 leaf CLI commands (20 `profile-bundle`)**, 6 ATS providers,
an 800 MB / 24,073-posting store.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily. `resume.yaml` is now an **import source, never hand-fixed**, via
adapter `boardwatch-resume-v1`.

**The bundle → résumé track is shippable, and Gate B is MET for the first time.** A polished,
fact-grounded, Gate-B-clean **one-page résumé renders and is live** (`untailored-349.pdf`): Experience in the
two-line macro, Projects as `Name | tech | link · dates`, clickable links, fact-grounded company
(D-199/D-200/D-201) and — since D-208 — **fact-grounded dates**. `tailor run` still degrades to the
untailored fallback (`bullet_too_long`, open Q5). **Sending is Mit's, and nothing has been sent.**

**Post-Gate-B robustness is finished: the scoped autonomous backlog is complete and pushed CI-green**
(D-202…D-206, plus **§5.2 invariant 3** — the last owed audit invariant). `candidate_promotion.py` is the
only lossy-id-creation site in `src/`, and **all four of its slug-collision sites now refuse** rather than
silently merging. **D-210 closed the fifth ambiguity in the same loop** — a skill listed under two groups
took its category by arrival order; it now refuses. **The next task must come from `PROGRAM.md`, or from
"Owed next" item 1–2, which are Mit's.**

### The active track — the master reservoir (bundle → résumé)

> **The Stage 1 loop is CLOSED**: `~/dev/portfolio-website/wiki` → an **11-entity master bundle** →
> promoted revision → approved `projection.yaml` → `profile-bundle project` renders a **2-page PDF with
> every bullet showing**. The master is a **RESERVOIR** holding the SUPERSET; per-JD **Stage 2** selects it
> down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the source — the wiki is.

**Live revision: `sha256:79a9cbf7…` (revision 8).** 11 entities — 4 experience (Saayam, NIO co-op,
Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge Forge, StreakSync, Random Forest, FlickSwiper,
BirthdayQuest, Fond). 107 facts (**94 effective** — 12 `superseded` by an active edge, 1 `rejected` by owner ruling),
14 skills, **33 bullets**, **7 evidence records** (two
owner-attestation, incl. `evidence.mit.employer-names.001`, + five `repository_artifact`). Validates
**0 error, 0 blocker**, with 10 `broken_reference` warnings — permanent residue of earlier revisions,
non-blocking. The PDF renders **zero overfull**.

**Catalog change (Mit's "Option A"):** `project.contribution` widened to `owner_attested` in **his bundle's**
`policy/predicates.yaml` (the shipped builtin stays strict), so project bullets render on his attestation.
**Facts stay `owner_attested` deliberately** (D-191): `edit-fact` refuses any other basis, so flipping would
forfeit the D-190 edit path for the records iterated most.

**Editing content is incremental and rebuilds nothing (D-190):** `checkout --draft <name>` → `edit-fact
--fact-id F --value "…"` → `validate` → Mit's TTY `approve` → `promote`. The correction is an edge (`F.r2`
supersedes `F`; the old wording drops out of the render on its own), so batch edits before the single TTY
approve. **Employer headings** are `'{@display_name}'`, so the entity's `display_name` *is* the rendered
line, freely hand-editable (limit ≈ 95 chars; all four fit).

### Stage 2 — live

`projection.yaml` reads **pinned 3** (`saayam`, `nio-coop`, `sakec`) / **candidates 8** (`nakshatra` + seven
projects); the pinned set alone is 7 bullets → 1 page, so `select` clears its own gate and reaches scoring.
**The declaration is now fact-grounded throughout and its approval has reopened (D-208).** All eleven
`dates` entries reference facts — `'{employment.date_range}'` for the four jobs, a declared
`{start:, end:}` range for the seven projects (Hookrail, StreakSync **and FlickSwiper** omit `end`, which
declares the range open). **Approved and clean: `profile-bundle project` exits 0 against revision 8.**
Every rendered date is semantically identical to the literal it replaced; only the typography changed, to
one convention (`Oct 2025 – Present`). **Never quote a digest for this pair** — it moved three times in one
session, and older stamps name real digests against superseded bundles; re-derive it with
`profile-bundle project`. Backup: `projection.yaml.bak-preground-20260815`, beside the live config. **The one-page ceiling is 16 bullets, not
entries** (D-195): with 3 jobs pinned, **at most two candidates are ever admitted**, and Mit's four-project
per-JD sets cannot fit at one page under any split (most is three, only with two jobs pinned). Previewing
needs no approval; re-promotion and `projection.yaml` edits each stale the stamp independently (D-167).

**Tasks 20 and 23 are closed.** `projection-selection-matrix.md` holds ten real `role=swe` postings with the
owner's rankings and cut lines over the **eight candidates** — the pinned three are excluded, since
`agreement.score_all` scores only the ids `case.expected` names (D-197). Reading `score_all` against those
labels found **no clean winner** (tau-b ≤ 0.16; `mean_per_bullet` adopted as the CLI `--scorer` default), and
the cut lines fix no score threshold, so `ADMISSION_FLOOR` stays `Decimal(0)` (D-198).

**Owed next.** Items 1–2 are Mit's content calls. Item 3 is closed. Item 4 is **owner-gated — do not start.**

1. **Résumé emit / format / dates / Gate B — DONE (D-199/D-200/D-201/D-208).** *Left, and all Mit's:*
   *Left:* whether to send, and the bullets below.
   **RULED 2026-08-15** on the two dates job-apps contradicted itself on: **StreakSync `Jul 2025 –
   Present`** (already what the bundle held) and **FlickSwiper `Jan 2026 – Present`** — Mit: *"im adding
   present because its live on the app store and im maintaining it."* FlickSwiper therefore needed a
   **bundle correction**, not just a declaration edit (D-209): `fact.flickswiper.end-date.001` (`2026-03`)
   is retired to `rejected`, since `EFFECTIVE_STATES` is `{verified, owner_confirmed}` and there is no
   "no end" value for a `year_month`. **DONE — approved, promoted to revision 8, projection re-approved.**
2. **Individual bullet refinement** — **a dedicated attended session**, Mit's ruling: *"a whole different
   attended session where we go through each project/employment to figure out what is the best way to
   showcase it."* Not a trim-to-length task. **10 of the 33 effective bullets exceed the 220-char ceiling**
   (longest 307), not the 2 this file used to claim; only `nio-coop` (241) is in the pinned three, so the
   fallback trips as soon as Stage 2 admits a project. It is also the only lever that widens Stage 2's
   choice (D-195 caps a page at 16 bullets). Wording is Mit's (D-191) — no attestation for text he has not
   read, so Hookrail's CI-chaos suite stays deliberately unclaimed.
3. **Autonomous engineering backlog — COMPLETE, nothing owed.** Listed only so a fresh session does not
   re-scope it; it is a record, not a queue. Recorded in D-202…D-206 and METRICS' 2026-08-15i/j/k sessions.
4. **Owner-gated — do NOT start unilaterally.**
   - **`_merge_categories`** (`candidate_promotion.py`): its `if category_id not in known` files a user's
     slug-colliding label under a pre-existing catalog category of a *different* `display_name`. The open
     question is whether the seeded catalog or the author owns a `display_name`; both answers are
     defensible, which is why it was not decided alongside D-210.
   - **D-184 finding 2** — a partial emission silently drops fields (`run_extraction` records a reason only
     when a record produces *no* candidate). Redefines the Gate B accounting contract; four mutually
     exclusive designs; nothing lost today.
   - Provider ATS-fixture + eligibility-corpus **drift** (need live network / a missing generator);
     **Education Slice C**; promoting `header/1`'s `person.professional_name` (the skill-item loop skips
     `header/*`).

**Carried authoring facts (D-185/186/190/191).** **Three guarantees are each narrower than their name**, and
all three cost a real defect: **`approve` does NOT validate** (only `promote` refuses); **a plain `validate`
cannot see Gate B** (the completeness tier owns it, and every authoring command revalidates at the validity
tier only); and **`_catalog_admits` is a DIFF** refusing only what a write *introduces*, so a write that
silently *removes* findings passes every layer. Always `validate --draft` before Mit approves, and
`--completeness` too for anything touching `policy/`, the ledger or imports — **diff the blocker COUNT, not
just "0 error"**. `add-evidence` needs `--draft --evidence-file --capture`. **No CLI confirms a skill, and
none sets a fact's verification state** — the four `employment.organization` flips were hand-edits. **Spent
draft names — `profile-bundle inventory` is authoritative, not this list:** `baseline`, `fmt-inspect`,
`gate-b-imports`, `headings`, `nio-heading`, `optionb`, `optionb-fix`, `orgfix`, `orgfix-probe`. **D-181:**
the example bundle is not a valid extraction host for a résumé *with projects*; a fresh `init` is.

### Settled tracks — do not reopen

**Projection** (D-163…D-170): 22 tasks merged, CI green. Two facts outlive the detail —
**`LatexRenderer.emit` never reads `Resume.header`/`Resume.education`** (D-156), template-hardcoded (the
bundle is NOT authoritative for name/contacts/education); and **no scorer may be picked by inspection**
(D-163), so `select()`'s parameter stays required with no default — Task 23 adopted `mean_per_bullet` as the
**CLI** `--scorer` default from the labeled matrix (D-198), never a new or third scorer.

**Gate A — MET** (D-157). Its internals, including the caveat that a closed review loop is evidence about
the slices reviewed and not that the subsystem is defect-free, are in `STANDING-FACTS.md` §Gate A internals.

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
| *Projection* | ***MERGED AND PUSHED**, reviewed clean; Tasks 20 and 23 closed (D-197, D-198)* | *P0–P4 build gates met* |
| *Gate B / master reservoir* | ***Stage 1 + Stage 2 DONE**; live revision 8, `79a9cbf7`* | ***MET — 0 blockers** (D-201). First zero-blocker Gate B ever* |

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
3. **What is boardwatch's Windows story?** Parked 2026-08-13. `pyproject.toml` publishes `OS Independent`
   while "Windows" appears zero times in the **user-facing** docs (`docs/*.md`, `docs/registry/`,
   `README.md`) — it appears only in the program logs. **The one real bug is fixed (D-206)**, so what is
   left is purely the support-posture claim, which no code change can settle.
4. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, after v1**; the pinned/candidate split (D-195); whether
the 33 bullets get shortened — **yes, in a dedicated attended session**, item 2; the two contradictory
job-apps dates — **ruled**, item 1; a skill listed under two groups — **refused**, D-210.)*

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle is what renders; wording is `edit-fact`'s job (D-190). Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | `reap_stale_runs`'s predicate is `status='running' AND finished_at IS NULL AND started_at < cutoff`, so ids 1–4 are excluded permanently — the real leak, needing a repair path nothing proposes. `top` is what opens them | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
