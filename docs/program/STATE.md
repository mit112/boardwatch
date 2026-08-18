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
rows), zero unattended days, zero acceptance days. Against that: 3 published releases (none since **0.3.0**),
~53k lines of source, **6,650 tests collected**, 70 leaf CLI commands, 6 ATS providers, an 800 MB /
24,073-posting store. **The build is largely complete; operation is absent.** Working tree clean.

**The buildable roadmap is exhausted pending an owner call.** P0/P1/P2/P5 gates are **MET**. P3, P6 and the
14-day clock are **frozen by D-155** — job-apps delivers Mit's résumés daily, so there is no live gap and the
freeze is costless. P4 is built; its one remaining clause is Mit's blind craft review. P7 is breadth-last and
gated. Because P3's gate is unmet, the ordering rule bars starting P4, and P3/P6 are frozen by owner decision
— so **no linear-roadmap phase is unilaterally startable** (D-236). The next roadmap move is an **owner
decision**: unfreeze P3/P6, run the P4 blind review, or open an owner-gated item (see *Owner-gated* below).
A fresh session should surface this, not manufacture work.

**The bundle → résumé + projection + render tracks are COMPLETE and merged; nothing is queued there.**
Gate B is **MET** (0 blockers, D-201); all 11 entities' bullets are refined and within the 220-char ceiling
(D-213…D-221); projection reaches the daily pipeline behind opt-in `run --project` (D-225); and the render
stack shipped four default-off opt-ins — ATS-parsable PDFs (D-233), `fill_to_page` (D-234), and
`link_in_first_bullet` + `sort_projects_by_date` (D-235), all in Mit's personal template. **What is left on
the résumé is Mit's alone**: whether to send a given document (no gate makes that call), and the two
owner-gated prose rewrites of D-220. **`resume.yaml` is an import source, never hand-fixed** (D-155).

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path; `resume.yaml` is imported via adapter `boardwatch-resume-v1`.

### The bundle track — reference facts (do not re-derive)

**Live revision 22, 11 entities** (4 experience + 7 projects). *Do not quote its digest or counts here —
refinement restamps several times a day (D-017); re-derive with `profile-bundle inventory`.* Validates
**0 error, 0 blocker**, 10 non-blocking `broken_reference` warnings (permanent residue), PDF renders zero
overfull. Facts stay **`owner_attested`** deliberately (D-191); `project.contribution` is widened to
`owner_attested` in Mit's bundle's `policy/predicates.yaml` (the shipped builtin stays strict, "Option A").

**Editing content is incremental (D-190):** `checkout --draft <name>` → `edit-fact --fact-id F --value "…"`
→ `validate --draft` → Mit's **TTY** `approve` → `promote`. Each edit is an edge (`F.r2` supersedes `F`), so
**batch edits before the single TTY approve.** **The approve/promote/approve-projection gates are TTY-only —
no `--yes`, and `!` gives no controlling terminal; hand them to Mit.** Run `profile-bundle inventory` for the
spent draft-name list, never a remembered one. The bundle takes no lock on `checkout`/`edit-fact`/
`add-evidence` — check `inventory` before authoring if more than one session is live.

**Three authoring guarantees are each narrower than their name, and each cost a real defect** (D-185/186):
**`approve` does NOT validate** (only `promote` refuses); a **plain `validate` cannot see Gate B** (the
completeness tier owns it); **`_catalog_admits` is a DIFF** that refuses only what a write *introduces*, so a
write that *removes* findings passes every layer. Always `validate --draft` before Mit approves, and
`--completeness` for anything touching `policy/`, the ledger or imports — **diff the blocker COUNT.**

**Stage 2 (per-JD selection) is live.** The one-page budget is a **character** budget, ≤ **3,439** chars
(D-219), not a bullet count. Projection is fact-grounded throughout (D-208). `mean_per_bullet` is the CLI
`--scorer` default; no clean winner emerged against the labeled matrix, so `ADMISSION_FLOOR` stays
`Decimal(0)` (D-197/D-198). `--project` with an explicit `--resume` REFUSES (exit 2). **Bullet-edit method
facts** (pinned-first buys headroom for the next candidate; bullets are the only scored text; the taxonomy is
blind to `Firebase`/`Firestore`/`SwiftData` so re-measure extraction after any trim; park by dropping
`'resume'` from `allowed_surfaces`, never by adding a fact) are in D-213/D-215/D-217/D-220 — binding on any
future bullet edit.

**P5b's criteria are NAMED (D-229, Mit's):** 3 clean projected runs, ≥ 30 distinct postings, 0 preflight
fatals, 0 résumé-QA failures, 0 fabrications. Four of five are evidenced on a store COPY (35 postings, 35
one-page PDFs, 0 drops, 0 fatals); the fabrication clause once failed (D-232 found StreakSync's *"446 tests
across 36 suites"* against a repo of 396/31) and was repaired in revision 22, character-neutral. Mit attested
the seven unverifiable claims and let Saayam's phrasing stand — **do not reopen either.** Whether runs on a
copy count toward an *unattended* gate, and whether the default flips to `--project`, are Mit's.

### Settled tracks — do not reopen

- **Projection** (D-163…D-170, 22 tasks merged): `LatexRenderer.emit` never reads `Resume.header`/
  `.education` — template-hardcoded (D-156); no scorer may be picked by inspection (D-163).
- **Gate A — MET** (D-157). Internals in `STANDING-FACTS.md` §Gate A internals.
- **Autonomous engineering backlog — COMPLETE** (D-202…D-206). `candidate_promotion.py` is the only
  lossy-id site; all four slug-collision sites refuse, and D-210 closed a fifth. `_merge_categories` remains
  open (owner-gated, below).

### Owner-gated — do NOT start unilaterally

1. **`_merge_categories`** (`candidate_promotion.py`): `if category_id not in known` files a slug-colliding
   label under a pre-existing catalog category of a different `display_name`. Undecided: seeded catalog vs.
   author owns a `display_name`.
2. **D-184 finding 2** — a partial emission silently drops fields (`run_extraction` records a reason only
   when a record produces *no* candidate). Redefines the Gate B accounting contract; four designs.
3. **Education Slice C** — promoting `header/1`'s `person.professional_name` (the skill-item loop skips
   `header/*`).
4. **P2 item 8 — the onboarding field-taxonomy gatherer** (needs its own brainstorm). D-054 forbids us
   authoring non-tech field content; its open question: a genuinely new field rule is still *code*, not data.
5. **Mit's two résumé content calls** — whether to send; the D-220 prose rewrites (his own writing, D-191).
6. **`add-evidence` takes no bundle lock, and D-143 widened the race** — two concurrent captures race on up
   to 13 files. Raise before anyone runs two authoring agents against one bundle.

### Fixture + corpus drift (D-228) — on `main`

R13/R14/R15 in `tools/generalization/fixtures.py`, inside `make check` and the CI `generalization` job. The
31 fixture JSONs were already pinned by R7 — **do not build a second manifest.** R15 enforces that someone
reviewed on schedule, not that a fixture matches production; `tools.fixture_refresh --extend` restores green
offline. **On 2026-09-11 (greenhouse) the whole `make check` reds** — drain or re-capture. *Owner-gated:* the
live-API comparison. **Unfixed:** `scratchpad/gen_corpus.py` was never committed, so the 987-row oracle is
**unregenerable**; four fixtures are read by no test.

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
| P7 Breadth | not started | — gated on P0 attribution data (§P7) |
| *Gate A (parallel)* | *complete, merged, CI green* | ***MET*** — *has moved no program gate* |
| *Gate B / master reservoir* | ***Stage 1 + Stage 2 DONE**; 11 entities refined (D-213…D-221); live revision **22**; digest omitted (D-017)* | ***MET — 0 blockers** (D-201); 0 over-ceiling bullets since rev 21; rev 22 corrects a false number (D-232) — Gate B never tested truth* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days, ≤ 5% | **NOT met.** One-shot baseline 186 surplus of 23,455 = 0.79%, under the bar but not over 7 days |
| **0** dead postings reaching the lead list | **NOT met.** Needs a real run whose leads are probed. Recall is low by design — 7 of 8 known-dead URLs still answer 200 |
| Injected hash-collision test | **MET** (D-100) — a test, so met outright |
| Audit of 20 sampled suppressions | **MET** (D-101) — 20/20 genuine, deterministic sample |

---

## Open questions — Mit's, not to be resolved by fiat

1. **Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
2. **Should any family other than `work_auth` default to `blocker` severity** (e.g. `clearance`)? (D-035.)
3. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
*(Recently resolved: the daily pipeline gets projection — yes, opt-in, D-225; P5b's criteria — NAMED, D-229;
the four backfilled `runs` rows close `ok` — D-230; a bullet-less entry — declared, D-226; Windows —
best-effort, D-212.)*

## Windows and the lock reclaim window

**Windows is best-effort (D-212)** — in the nightly, out of the pyproject classifiers, caveated in
`README.md`. A green 9-job push run contains **zero** Windows jobs (D-151); the nightly is 12. A
**`nightly-watch`** job files a "Nightly CI is failing" issue on a failed scheduled run and closes it on
recovery — **check for an open one at session start** (none open now).

**The stale-lock race is FIXED at the root; all four `xfail` markers are gone on `main`** (D-224, D-227).
`core/lock_reclaim.py` owns `RECLAIM_WINDOW_SECONDS`/`RECLAIM_POLL_SECONDS` — **1.0s on `win32`, 0.0
elsewhere, so POSIX is bit-identical** — and both the bundle-writer lock and the **scan lock** re-ask the OS
until a deadline. Both consumers bind the constants **by name**, so patch the consumer, not
`core.lock_reclaim`. 1.0s is a judgement — widen on evidence. `make check` can never verify this (inert off
`win32`); Windows evidence comes only from a `workflow_dispatch` of `ci.yml` (~1 hour).

**Evidence, bound: run `32065805682`, sha `655c474f`** — 12/12 green including all three Windows jobs, with
the markers already removed. `core/lock_reclaim.py`, `profile_bundle/` and `scan/` are unchanged between that
sha and `main` — re-check with `git log 655c474f..HEAD -- <those paths>` before citing it, as a later commit
to any voids it. **Issue #76's closure is NOT that evidence** — a green scheduled run closed it on a tree that
still carried all four markers; only the dispatch above speaks to the fix.

**One false-refusal exposure is left standing DELIBERATELY (D-224) — do not "fix" it without the owner.**
**POSIX is not exempt:** `UnixFileLock` unlinks the lockfile before releasing the `flock`, so a live-holder
handoff can report `bundle_lock_held` while nobody holds the lock (reproduced on macOS local disk). **Ruled:
record, do not widen the window.**

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle renders; wording is `edit-fact`'s job. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **Apply the D-230 migration to the LIVE store** | `runs_status_backfill_repair` closes the four `status='running' AND finished_at IS NOT NULL` rows as `ok`, matched by predicate not ids. Built and on `main`; **not yet run against Mit's live store.** `doctor` exits 1 on a recurrence | Mit / operational |
| **`add-evidence` takes no bundle lock** | Only `promote`/`rebase`/`approve` take `bundle_lock`; two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content | owner-gated |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — relevant to Gate P6's clean 7-day window | P6 |
