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

**The headline number: 0.** Zero job applications have ever been sent from boardwatch (`applications` has 0
rows) — the machine produces leads, it never applies (out of scope). Against that: 3 published releases
(none since **0.3.0**), ~53k lines of source, **6,650 tests collected**, 70 leaf CLI commands, 6 ATS
providers, an ~800 MB store. **The build is complete and the daily driver is now LIVE (D-244):** on
2026-08-19 the first full unattended run (run 61) completed clean end-to-end — 8 leads, 8 one-page PDFs — via
a launchd agent. Working tree clean.

**The roadmap is UNFROZEN (D-240); its remaining gates are OPERATIONAL, not build.** P0/P1/P2/P5 gates are
**MET**. On 2026-08-18 Mit lifted D-155's freeze on P3, P6 and the 14-day clock. The builds for P3/P4/P6 are
essentially done, so their gates now close by *running* boardwatch daily, not by coding. **P3 item 8 — the
last P3 build item (a same-OS two-writer test + a runtime refusal of WAL-unsafe filesystems for the
CI-untestable cross-OS case) — is DONE (D-241);** Gate P3 now needs only its operational half: 7 consecutive
clean unattended runs. Gate P4 is Mit's blind craft review, barred by the ordering rule until P3's gate is
met. Gate P6 needs a real 7-day dedup window plus liveness-probed leads. The 14-day acceptance clock starts
after P6; **P7 breadth stays last.** **The window is now OPEN (D-244):** on 2026-08-19 Mit approved the
projection (TTY), a launchd agent (`com.boardwatch.run`, 8:00 AM daily, `run --project`) was installed with
an explicit homebrew PATH — without which the unattended render silently dies (D-204) — and run 61 completed
clean. **The remaining P3 work is now accrual, not code:** 7 consecutive clean runs. **Mit ruled run 61 is
day 1 (D-245) — 6 to go.** The next arrives with tomorrow's 8:00 AM scheduled fire.

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
  lossy-id site; **all slug-collision sites now refuse** — D-210 closed a fifth and **D-237 closed the last
  (`_merge_categories`, a label colliding with a seeded catalog category: the catalog owns the display_name).**

### Owner-gated — do NOT start unilaterally

1. **P2 item 8 — the onboarding field-taxonomy gatherer** (needs its own brainstorm). D-054 forbids us
   authoring non-tech field content; its open question: a genuinely new field rule is still *code*, not data.
2. **Mit's two résumé content calls** — whether to send; the D-220 prose rewrites (his own writing, D-191).
3. **`add-evidence` takes no bundle lock, and D-143 widened the race** — two concurrent captures race on up
   to 13 files. Raise before anyone runs two authoring agents against one bundle.

*(Closed: **Education Slice C** (D-239) — `header/1`'s name is excluded from promotion like the email, since
onboarding already supplies it; **D-184 finding 2** (D-238) — a partial extraction sets the whole record
aside for review rather than importing a half-record.)*

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
| P3 Unattended one command | **COMPLETE + LIVE** — launchd agent installed, run 61 clean (D-244) | **NOT MET — 1 of 7** — run 61 ruled day 1 (D-245), 6 to go; **unfrozen** (D-240) |
| P4 Craft gate | **COMPLETE** — items 1–7 | **NOT MET** — the blind craft review is the owner's, never run |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** — three slices (D-110, D-111, D-113) | **NOT MET — 2 of 4**, below; **unfrozen** (D-240) — needs real runs |
| 14-day acceptance | not started | **unfrozen** (D-240); starts after P6 |
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
4. **Which seniority band does Mit target?** The gate is built (D-246) but ships **inert** —
   `target_seniority_band` defaults to `any` and short-circuits before any title is read, so ranking is
   unchanged. Setting it (`profile edit` → `entry`) re-keys `policy_version` once: 11 ledger rows stale,
   released with `ledger reopen --stale`.
*(Recently resolved: **D-245's two relevance leaks — CLOSED, D-246**, option (b), the real fix: a guarded
bare-`coordinator` deny in `role_gate` (135 postings flip, 0 `swe` touched) plus a rank-time
`seniority_gate` over a versioned, company-free `leveling.yaml`, with company→scheme binding in user config
(`{config_dir}/leveling-bindings.yaml` — the registry is a 37-entry `extra="forbid"` seed catalog with no
Snap/Twilio/Google). Deferred by design: the role gate's fail-open `uncertain` lane, only 1.2% closed. Also:
projection in the daily pipeline — opt-in, D-225; P5b's criteria — NAMED, D-229; the four backfilled `runs`
rows close `ok` — D-230; a bullet-less entry — declared, D-226; Windows — best-effort, D-212.)*

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
| **D-230 migration — ALREADY APPLIED to live (D-243)** | Verified 2026-08-18 on a byte copy: 0 stuck rows, alembic at `runs_status_backfill_repair` head; `stats` is a no-op. **Do NOT use `doctor`'s exit as the check** — it exits 1 on ~12 dead Workday boards, unrelated. Read-only check: `sqlite3 "file:<db>?immutable=1" "SELECT COUNT(*) FROM runs WHERE status='running' AND finished_at IS NOT NULL"` → 0 | resolved |
| **Daily driver LIVE — Gate P3 now accruing (D-244)** | Projection approved (TTY, 2026-08-19); launchd agent `com.boardwatch.run` runs `run --project` at 8:00 AM daily with an explicit homebrew PATH (the D-204 trap). Run 61 clean: 8 leads, 8 one-page PDFs. **1 of 7** — Mit ruled run 61 = day 1 (D-245), 6 to go | Mit / P3 |
| **`add-evidence` takes no bundle lock** | Only `promote`/`rebase`/`approve` take `bundle_lock`; two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content | owner-gated |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — relevant to Gate P6's clean 7-day window | P6 |
