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
**6,650 tests collected**, **70 leaf CLI commands (20 `profile-bundle`)**, 6 ATS providers, an 800 MB /
24,073-posting store.

**All four 2026-08-17 lanes are MERGED to `main`** (PR #77 then PR #78): **D-224 + D-227** (the Windows
stale-lock race, fixed at the root, all four `xfail` markers gone), **D-225** (projection reaches the daily
pipeline, slice P5a), **D-226** (a bullet-less entry is representable) and **D-228** (fixture + corpus drift
detection). CI green on the full matrix; nothing is released — **no version has been cut since 0.3.0.**
**2026-08-18 added D-229** (P5b's criteria, named by Mit), **D-230** (the backfilled `runs` rows repaired,
plus a `doctor` invariant), **D-231** (D-225's residuals: four closed, one declined, one not found) and
**D-232** (an independent repo audit found a FALSE NUMBER on the rendered résumés; fixed in revision 22).

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily. `resume.yaml` is now an **import source, never hand-fixed**, via
adapter `boardwatch-resume-v1`.

**The bundle → résumé track is shippable, and Gate B is MET.** A fact-grounded, Gate-B-clean **one-page
résumé renders and is live** (`untailored-349.pdf`): Experience in the two-line macro, Projects as
`Name | tech | link · dates`, clickable links, fact-grounded company (D-199/D-200/D-201) and dates (D-208).
**`bullet_too_long` can no longer fire: at revision 22 every rendering bullet is within the 220-char
ceiling** (D-213…D-221), so the fallback's remaining structural cause is gone — open Q5 needs re-testing
against a real `tailor run`, not re-analysing. **Sending is Mit's, and nothing has been sent.**

**Post-Gate-B robustness is finished** (D-202…D-206, plus §5.2 invariant 3). `candidate_promotion.py` is the
only lossy-id-creation site in `src/`, and **all four of its slug-collision sites now refuse** rather than
silently merging; **D-210** closed a fifth ambiguity (a skill listed under two groups). `_merge_categories`
remains open — see item 4. **The next task must come from `PROGRAM.md`.**

### The active track — the master reservoir (bundle → résumé)

> **The Stage 1 loop is CLOSED**: `~/dev/portfolio-website/wiki` → an **11-entity master bundle** →
> promoted revision → approved `projection.yaml` → `profile-bundle project` renders a **2-page PDF with
> every bullet showing**. The master is a **RESERVOIR** holding the SUPERSET; per-JD **Stage 2** selects it
> down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the source — the wiki is.

**Live revision: 22.** *Do not quote its digest or its counts here — refinement promotes several times a day
and any stamp written into this file is stale within the hour; re-derive with `profile-bundle inventory`
(D-017).* 11 entities — 4 experience (Saayam, NIO co-op, Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge
Forge, StreakSync, Random Forest, FlickSwiper, BirthdayQuest, Fond). Validates **0 error, 0 blocker**, with
10 `broken_reference` warnings — permanent residue of earlier revisions, non-blocking. The PDF renders
**zero overfull**.

**Catalog change (Mit's "Option A"):** `project.contribution` is widened to `owner_attested` in **his
bundle's** `policy/predicates.yaml` (the shipped builtin stays strict). **Facts stay `owner_attested`
deliberately** (D-191): `edit-fact` refuses any other basis, so flipping would forfeit the D-190 edit path.

**Editing content is incremental and rebuilds nothing (D-190):** `checkout --draft <name>` → `edit-fact
--fact-id F --value "…"` → `validate` → Mit's TTY `approve` → `promote`. The correction is an edge (`F.r2`
supersedes `F`), so batch edits before the single TTY approve. **Employer headings** are
`'{@display_name}'`, so the entity's `display_name` *is* the rendered line, freely hand-editable (≈ 95
chars).

### Stage 2 — live

`projection.yaml` reads **pinned 3** (`saayam`, `nio-coop`, `sakec`) / **candidates 8** (`nakshatra` + seven
projects); the pinned set alone is 7 bullets → 1 page, so `select` clears its own gate and reaches scoring.
**The declaration is fact-grounded throughout** (D-208) — all eleven `dates` entries reference facts, and an
**omitted `end` declares the range open** while a *named* `end` with no fact stays fatal. **Approved and
clean: `profile-bundle project` exits 0.** **Never quote a digest for this pair** — re-derive it. Backup:
`projection.yaml.bak-preground-20260815`, beside the live config.

**The one-page budget is a CHARACTER budget, not a bullet count (D-219).** Every set ≤ **3,439** chars fit
and every set ≥ **3,528** overflowed; bullet count did **not** predict fit. **D-195's "16 bullets", its "at
most two candidates are ever admitted" and its "the four-project sets do not fit under any split" are
RETIRED.** At revision 21 (pinned 1,180 chars) both of Mit's per-JD four-project sets fit (SDE 3,131 / iOS
2,968) and **five** projects fit (3,347); six overflows. Candidate room **2,259**. Previewing needs no
approval; re-promotion and `projection.yaml` edits each stale the stamp independently (D-167).

**Projection reaches the daily pipeline — slice P5a (D-225), merged here, and it is OPT-IN.** `boardwatch
run --project` renders each lead from the bundle's projection; **without the flag, `resume.yaml` is still
the unattended default and that is deliberate.** A run-level preflight refuses **before any lead earns a
ledger disposition** — never a per-lead fallback, which would have succeeded and so earned each lead a
permanent `built` the ledger suppresses forever. *Do not confuse this with the program's `P5 Eligibility
decides`, which is a different phase and is MET; the labels `P5a`/`P5b` were also used in 2026-08 for
unrelated eligibility work (D-064/D-065/D-068).*

**P5b's criteria are NAMED (D-229, Mit's):** 3 clean projected runs, **≥ 30 distinct postings**, 0
preflight fatals, 0 résumé-QA failures, 0 fabrications. **Four of the five are met with evidence** — three
runs on a store COPY produced **35 distinct postings, 35 PDFs, 0 tailor/pdf drops, 0 fatals**, and
`pdfinfo` independently confirms **1 page for all 35**. Whether runs on a copy count toward a gate about
*unattended* operation is Mit's call; running them live would have earned 35 real postings a permanent
`built`, which is the defect the design exists to prevent.

**The fifth clause FAILED, and that is the important fact (D-232).** An independent session — no access to
boardwatch, the wiki or job-apps, checking **source code and git history only** — audited the 19 claims the
42 PDFs are all subsets of. Ten came back SUPPORTED with **every checkable number exact**; **one was
CONTRADICTED**: StreakSync claimed *"446 XCTest tests across 36 suites"* against a repo holding **396 across
31**. Repaired as `.r4` in **revision 22**, character-neutral so the page budget cannot shift, and verified
rendering. Seven are UNVERIFIABLE by construction (private/absent artifacts) — expected, not a finding.
**Saayam was ruled unchanged by Mit**; its bullet describes the *platform*, not authorship, so the audit's
authorship finding answers a claim the sentence does not make.

**The 42 audited PDFs were rendered from revision 21 and no longer match what the pipeline produces.**
Whether re-rendering and re-auditing is owed before the clause counts as met is **Mit's call**. The default
has NOT flipped. **Gate B's 0 blockers was never a claim about truth** — nothing in the validation layer can
compare a numeral to the world, which is why the outside reader is not optional.

**Two things about `--project` that are easy to get wrong.** The funnel's `artifact_version` advances to
**5 for every run, authored ones included** — one emitter, one schema version. "Nothing changes without the
flag" is a claim about **behaviour**: no projection stage, no lineage keys, unchanged lead outcomes and
dispositions — **not** about that field. And **`--project` with an explicit `--resume` REFUSES** (exit 2,
before any `runs` row); what the combination should mean is P5b's to rule.

**Tasks 20 and 23 are closed** (D-197, D-198). `projection-selection-matrix.md` holds ten real `role=swe`
postings with the owner's rankings over the **eight candidates** — the pinned three are excluded, since
`agreement.score_all` scores only the ids `case.expected` names. Against those labels there is **no clean
winner** (tau-b ≤ 0.16); `mean_per_bullet` is the CLI `--scorer` default, and the cut lines fix no score
threshold, so `ADMISSION_FLOOR` stays `Decimal(0)`.

**Owed next.** Items 1–2 are Mit's content calls. Item 3 is closed. Item 4 is **owner-gated — do not start.**

1. **Résumé emit / format / dates / Gate B — DONE** (D-199/D-200/D-201/D-208/D-209). *Left, and Mit's:*
   whether to send.
2. **Individual bullet refinement — COMPLETE. All eleven entities refined and promoted** (D-213…D-221).
   Pool: **11 entries, 23 bullets, 4,608 chars, ZERO over the 220-char ceiling**; the pinned three cost
   `nio-coop` 632 / `saayam` 200 / `sakec` 348 (page budget under *Stage 2*).
   **Still owed from this track:**
   - **D-221's "C" — BUILT and MERGED to `main` (D-226).** "Role + org + dates only"
     is representable by declaring **`bulletless: true`** on the entry in `projection.yaml`;
     `validate_slots` accepts a declared entry and still refuses every other empty one, so Gate P1's
     direction is unchanged (`PROGRAM.md` item 4 amended). **The fix is the opposite of what STATE and
     D-221 prescribed:** `BULLET_PREDICATE_NO_FACTS` is deliberately UNCHANGED — a declared predicate
     resolving to nothing stays fatal, because dropping the bullet trades a loud refusal for a silent
     omission. **Mit's `saayam` entry still carries its one role-scoped bullet** — the `projection.yaml`
     edit and its re-`approve-projection` are his to make.
   - **The "sole iOS developer" prose is OWNER-GATED, not "one edit", and it lives in TWO files.** Both
     `wiki/00-profile/application-qa.md` and the upstream `~/dev/Job apps/Common_App_Questions.md:8` now
     carry the D-220 warning block; the prose under it is left verbatim **deliberately**, because rewording
     Mit's own writing is his alone (D-191). The upstream flag is committed locally as **`7dbc4ab`** and
     **not pushed** (his personal repo, his call). **All that remains is Mit's rewrite of his own prose.**
     Note `~/dev/portfolio-website/wiki` is **not a git repo** — edits there have no undo.

   **Method facts still binding on any future bullet edit** — the house style, the `kind:`-split, and the
   grounding discipline are in D-213/D-215/D-217/D-220; four are repeated here because forgetting them
   silently corrupts a result:
   **Do the PINNED entries first** — pinned entries are *"emitted in declared order, never scored, never
   dropped"*, so shortening one buys **admission headroom for the next candidate**, never its own standing.
   **Bullets are the ONLY scored text** (`effective_skills(bullet.text, …)`; a `subtitle` earns nothing).
   **The taxonomy does not know `Firebase`, `Firestore` or `SwiftData`** — all extract `[]` while `Swift`
   and `iOS` resolve, so **re-measure extraction after any length trim** and check the union is non-empty:
   a bullet can be score-invisible with nothing warning you. Fired twice.
   **Park a bullet by dropping `'resume'` from `allowed_surfaces`**, never by adding a fact — Stage 2 admits
   *entries*, so an extra fact renders unconditionally. Wording is Mit's (D-191).
3. **Autonomous engineering backlog — COMPLETE, nothing owed** (D-202…D-206). A record, not a queue.
4. **Owner-gated — do NOT start unilaterally.**
   - **`_merge_categories`** (`candidate_promotion.py`): its `if category_id not in known` files a user's
     slug-colliding label under a pre-existing catalog category of a *different* `display_name`. Open:
     whether the seeded catalog or the author owns a `display_name` — both are defensible, which is why it
     was not decided alongside D-210.
   - **D-184 finding 2** — a partial emission silently drops fields (`run_extraction` records a reason only
     when a record produces *no* candidate). Redefines the Gate B accounting contract; four mutually
     exclusive designs; nothing lost today.
   - **Education Slice C**; promoting `header/1`'s `person.professional_name` (the skill-item loop skips
     `header/*`).

**Fixture + corpus drift — the offline half is BUILT and gated (D-228), and this lane IS on `main`.**
R13/R14/R15 in `tools/generalization/fixtures.py`, inside `make check` and the CI `generalization` job.
**The 31 fixture JSONs were ALREADY pinned by R7 — do not build a second manifest.** **R15 enforces that
somebody reviewed on schedule, NOT that a fixture matches production**; `tools.fixture_refresh --extend`
restores green offline by design. **On 2026-09-11 (greenhouse) the whole `make check` reds**, not one rule —
several real-tree tests assert the gate is clean. Drain it or re-capture. *Owner-gated:* the live-API
comparison. **Unfixed:** the corpus's generator `scratchpad/gen_corpus.py` was **never committed**, so the
987-row oracle is **unregenerable**; and four fixtures are read by no test (`workable/dead_404.json`, plus
`normal_response_headers.json` under `workable/`, `smartrecruiters/` and `workday/`).

**Carried authoring facts (D-185/186/190/191).** **Three guarantees are each narrower than their name**, and
all three cost a real defect: **`approve` does NOT validate** (only `promote` refuses); **a plain `validate`
cannot see Gate B** (the completeness tier owns it, and every authoring command revalidates at the validity
tier only); and **`_catalog_admits` is a DIFF** refusing only what a write *introduces*, so a write that
silently *removes* findings passes every layer. Always `validate --draft` before Mit approves, and
`--completeness` too for anything touching `policy/`, the ledger or imports — **diff the blocker COUNT, not
just "0 error"**. `add-evidence` needs `--draft --evidence-file --capture`. **No CLI confirms a skill, and
none sets a fact's verification state** — the four `employment.organization` flips were hand-edits.
**Draft names: run `profile-bundle inventory` for the spent list — never a remembered one.** The bundle
takes no lock on `checkout`/`edit-fact`/`add-evidence` (only `promote`/`rebase`/`approve` do), so check
`inventory` for a recent write before authoring when more than one session is live. **D-181:** the example
bundle is not a valid extraction host for a résumé *with projects*; a fresh `init` is.

### Settled tracks — do not reopen

**Projection** (D-163…D-170): 22 tasks merged to `main`, CI green. Two facts outlive the detail —
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
| *Projection* | *Tasks 1–22 **merged to `main` and pushed**, reviewed clean; Tasks 20 and 23 closed (D-197, D-198). **Pipeline integration slice P5a MERGED to `main`** — `run --project`, 11 reviewed tasks (D-225)* | *Projection-spec P0–P4 build gates met; **its P5 NOT met** — P5a only. **P5b's criteria are now NAMED (D-229) and 4 of 5 clauses are evidenced**; the flip waits on the fabrication audit, which is Mit's* |
| *Gate B / master reservoir* | ***Stage 1 + Stage 2 DONE**; all 11 entities' bullets refined (D-213…D-221); live revision **22**. Digest deliberately omitted — refinement restamps it several times a day (D-017)* | ***MET — 0 blockers** (D-201), and **0 over-ceiling bullets** since revision 21. **Revision 22 corrects a FALSE NUMBER an independent audit found (D-232)** — Gate B never tested truth* |

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
3. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
*(Resolved: docs-only commits and `make check` (D-116); `add-evidence` writing the back-citation (D-143);
whether the daily pipeline gets projection — **yes, opt-in, D-225**; **P5b's criteria — NAMED, D-229**;
**which terminal status the four backfilled `runs` rows get — `ok`, D-230**; the pinned/candidate split (D-195);
whether the 33 bullets get shortened — **DONE, D-213…D-221**; the two contradictory job-apps dates —
**ruled**, D-209; a skill listed under two groups — **refused**, D-210; **boardwatch's Windows story —
RULED best-effort, D-212**; a bullet-less entry — **declared, D-226**.)*

## Windows and the lock reclaim window

**Windows is best-effort (D-212)** — in the nightly, out of the pyproject classifiers, caveats in
`README.md`. **A green 9-job push run contains ZERO Windows jobs** (`ci.yml`'s `os` matrix is conditional on
`schedule`/`workflow_dispatch`, D-151; the nightly is 12) — never read it as full-matrix coverage. A
**`nightly-watch`** job files a GitHub issue when a scheduled run fails and closes it on recovery:
**check for an open "Nightly CI is failing" issue at session start.**

**The stale-lock race is FIXED at the root, all four `xfail` markers are GONE on `main`** (D-224,
superseding the D-212/D-222/D-223 suppression track), **and BOTH locks now carry the window** (D-227), both
verified green on Windows. `core/lock_reclaim.py` owns `RECLAIM_WINDOW_SECONDS` / `RECLAIM_POLL_SECONDS` —
**1.0s on `win32`, 0.0 everywhere else, so POSIX is bit-identical** — and the bundle writer lock and the
**scan lock** both re-ask the OS until a deadline instead of believing one refusal. The scan lock mattered
more despite never having been observed firing: scanning runs **unattended**, so a killed scan followed by a
refused scheduled scan is a **silent empty day**, not a retryable prompt. The surviving 4 xfails are
`test_projection_scoring.py`'s `strict=True` known-biased scorers. This is a departure from §21's *"no wait
or mutation"*, Windows only, and **1.0s is a judgement, not a measurement** — widen it on evidence.

**Two things about it will break if forgotten.** Both consumers bind the constants **by name**, so patching
`core.lock_reclaim` reaches neither — **patch the consumer.** And a test timing a *genuine* contention path
must derive its budget as `RECLAIM_WINDOW_SECONDS + N`, never a literal, or it goes flaky on Windows.

**`make check` can NEVER verify this work** — the window is inert off `win32`. Windows evidence comes only
from a **`workflow_dispatch`** of `ci.yml` (the full 12-job matrix, **~1 hour**; Windows jobs 40–62 min, 3.13
the long pole).

**The evidence exists and is bound: run `32065805682`, on sha `655c474f`** — 12/12 green including all three
Windows jobs, with the four `xfail` markers already removed and D-227's `c916423` in its history.
`core/lock_reclaim.py`, `profile_bundle/` and `scan/` are **unchanged between that sha and `main`**, which is
what carries the evidence forward to HEAD; re-check that with `git log 655c474f..HEAD -- <those paths>` before
citing it again, because a later commit to any of them voids it.

**Issue #76 is CLOSED, and its closure is NOT that evidence** — read it as unrelated. `nightly-watch` closed
it on the 2026-08-18 07:41 scheduled run, whose sha was `834d25a7` (PR #77): **that tree still carried all
four `xfail` markers**, so the nightly it went green on was still suppressing the tests. A green scheduled run
closes #76 regardless of what it ran; only the dispatch above says anything about the fix.

**One false-refusal exposure is left standing DELIBERATELY (D-224) — do not "fix" it without the owner.**
**POSIX is not exempt.** `UnixFileLock` unlinks the lockfile *before* releasing the `flock` and discards an
already-unlinked inode, so a second writer that opened it first can be reported `bundle_lock_held` while
nobody holds the lock — a **live-holder handoff** race, reproduced on macOS local disk, no network
filesystem needed. **Ruled: record, do not widen the window.** `bundle_lock` is the only acquire path
*inside* `profile_bundle`, and `coordinator.run_scan` the only one in `scan`.

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle is what renders; wording is `edit-fact`'s job (D-190). Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| ~~Four `runs` rows are `running` WITH `finished_at` set~~ — **REPAIRED (D-230)** | Migration `runs_status_backfill_repair` closes them as **`ok`** (Mit's ruling), matched on `status='running' AND finished_at IS NOT NULL` — **never on ids**, so it is correct for any operator's store. `doctor` now asserts the same predicate and **exits 1** on a hit, so a recurrence is loud rather than inert. The old premise that these are "indistinguishable from a killed run" is **false**: a killed run keeps `finished_at` NULL, so all four were closed by a writer that ran. **Apply the migration to the live store** — it has not been run there yet | done |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
