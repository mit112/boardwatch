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
**6,451 tests** (6,447 passing + 4 xfailed), **70 leaf CLI commands (20 `profile-bundle`)**, 6 ATS providers,
an 800 MB / 24,073-posting store.

**The program reoriented on 2026-08-13 (D-155):** remaining work runs through the **canonical career-profile
bundle**, not the old `resume.yaml` path. **P3, P6 and the 14-day clock are frozen** — costless, because
job-apps produces Mit's résumés daily. `resume.yaml` is now an **import source, never hand-fixed**, via
adapter `boardwatch-resume-v1`.

**The bundle → résumé track is shippable, and Gate B is MET for the first time.** A polished,
fact-grounded, Gate-B-clean **one-page résumé renders and is live** (`untailored-349.pdf`): Experience in the
two-line macro, Projects as `Name | tech | link · dates`, clickable links, fact-grounded company
(D-199/D-200/D-201) and — since D-208 — **fact-grounded dates**. **`bullet_too_long` can no longer fire:
as of revision 21 every one of the 23 rendering bullets is within the 220-char ceiling** (D-213…D-221),
so the fallback's remaining structural cause is gone — open Q5 needs re-testing against a real
`tailor run`, not re-analysing. **Sending is Mit's, and nothing has been sent.**

**Post-Gate-B robustness is finished: the scoped autonomous backlog is complete and pushed CI-green**
(D-202…D-206, plus **§5.2 invariant 3** — the last owed audit invariant). `candidate_promotion.py` is the
only lossy-id-creation site in `src/`, and **all four of its slug-collision sites now refuse** rather than
silently merging. **D-210 closed the fifth ambiguity in the same loop** — a skill listed under two groups
took its category by arrival order; it now refuses. **"Owed next" item 2 — individual bullet refinement —
is COMPLETE as of 2026-08-17: all eleven entities, revision 21.** Two small residuals are named under it.
**The next task must come from `PROGRAM.md`.**

### The active track — the master reservoir (bundle → résumé)

> **The Stage 1 loop is CLOSED**: `~/dev/portfolio-website/wiki` → an **11-entity master bundle** →
> promoted revision → approved `projection.yaml` → `profile-bundle project` renders a **2-page PDF with
> every bullet showing**. The master is a **RESERVOIR** holding the SUPERSET; per-JD **Stage 2** selects it
> down to one page. `resume.yaml` / `sections.tex` are thin per-JD OUTPUTS, **not** the source — the wiki is.

**Live revision: 21.** *Do not quote its digest here — the refinement sessions promote several times a
day and any stamp written into this file is stale within the hour; re-derive it with `profile-bundle
inventory` (D-017).* 11 entities — 4 experience (Saayam, NIO co-op,
Nakshatra, SAKEC) + 7 projects (Hookrail, Knowledge Forge, StreakSync, Random Forest, FlickSwiper,
BirthdayQuest, Fond). 124 facts (**93 effective** — 29 `superseded` by an active edge, 2 `rejected` by owner ruling),
14 skills, **32 effective bullet-facts of which 25 render** (7 parked by surface per D-213), **7 evidence records** (two
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
declares the range open). **Approved and clean: `profile-bundle project` exits 0 against revision 11.**
Every rendered date is semantically identical to the literal it replaced; only the typography changed, to
one convention (`Oct 2025 – Present`). **Never quote a digest for this pair** — it moved three times in one
session, and older stamps name real digests against superseded bundles; re-derive it with
`profile-bundle project`. Backup: `projection.yaml.bak-preground-20260815`, beside the live config.
**The one-page budget is a CHARACTER budget, not a bullet count (D-219).** Measured by compiling
subsets through the D-195 path: at the old ~250-char-average pool every set ≤ **3,439** chars fit and
every set ≥ **3,528** overflowed, while bullet count did **not** predict fit — two different
18-bullet / 7-entry sets landed on opposite sides. Characters proxy rendered lines, which is the real
mechanism. **D-195's "16 bullets", its "at most two candidates are ever admitted" and its "the
four-project sets do not fit under any split" are RETIRED** — all three were artifacts of the bullet
lengths then in the bundle, not properties of the page. Measured at revision 21 (pinned 1,180 chars):
**both** of Mit's stated per-JD four-project sets fit (SDE 3,131 / iOS 2,968) and **five** projects fit
(3,347); six overflows. Candidate room **2,259**. Previewing
needs no approval; re-promotion and `projection.yaml` edits each stale the stamp independently (D-167).

**Projection reaches the daily pipeline — slice P5a SHIPPED (D-225), and it is OPT-IN.** `boardwatch run
--project` renders each lead from the bundle's projection; **without the flag, `resume.yaml` is still the
unattended default and that is deliberate.** A run-level preflight refuses **before any lead earns a ledger
disposition** — never a per-lead fallback, which would have succeeded and so earned each lead a permanent
`built` the ledger suppresses forever. **The projection spec's P5 is NOT met by this**: its gate includes
"`resume.yaml` stops being the daily default", which is **P5b — owner-gated**, and its criteria (how many
clean projected runs, over how many postings, at what defect budget) are Mit's to name. *Do not confuse this
with the program's `P5 Eligibility decides`, which is a different phase and is MET; the labels `P5a`/`P5b`
were also used in 2026-08 for unrelated eligibility work (D-064/D-065/D-068).* Measured before merge against
a **copy** of the store: projection stage **7.59s / 10 leads**, **max 3 compiles per lead** (structural
ceiling 10), declared ceiling **≤ 6s per lead**.

**Two things about `--project` that are easy to get wrong.** The funnel's `artifact_version` advances to
**5 for every run, authored ones included** — one emitter, one schema version. "Nothing changes without the
flag" is a claim about **behaviour**: no projection stage, no lineage keys, unchanged lead outcomes and
dispositions — **not** about that field, and an earlier wording that also claimed byte-identical no-flag
JSON was an over-claim, corrected in D-225. And **`--project` with an explicit `--resume` REFUSES** (exit 2,
before any `runs` row): the projected path overwrote the résumé path for every lead, so `--resume` had no
effect; what the combination should mean is P5b's to rule.

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
2. **Individual bullet refinement — COMPLETE. All eleven entities refined and promoted** (D-213…D-221),
   one per attended session. **Live revision 21** (`sha256:abed3cab…`), `project` **exit 0**.
   Pool: **11 entries, 23 bullets, 4,608 chars, ZERO over the 220-char ceiling** (was 33 bullets /
   6,492 chars / 10 over). `bullet_too_long` can no longer trip on any render, which retires the
   `tailor run` fallback's only remaining structural cause. Pinned three cost **1,180 chars**
   (`nio-coop` 632, `saayam` 200, `sakec` 348); candidate room **2,259**.
   **The capacity conclusions this file used to carry are retired (D-219)** — see *Stage 2* above.
   **Still owed from this track:**
   - **D-221's "C" — BUILT (D-226) on branch `bulletless-entry-representable`; UNMERGED, unpushed.**
     "Role + org + dates only" is now representable by declaring **`bulletless: true`** on the entry in
     `projection.yaml`. `validate_slots` accepts an entry that declares it and still refuses every other
     empty entry, so Gate P1's direction is unchanged (`PROGRAM.md` item 4 amended). **The fix is the
     opposite of how this bullet used to describe it:** `BULLET_PREDICATE_NO_FACTS` is deliberately
     UNCHANGED — a declared predicate resolving to nothing stays fatal, because dropping the bullet
     instead would trade a loud refusal for a silent omission. No new `ProjectionIssue`; no existing test
     edited. `make check` green, exit 0, 6,443 passed / 4 xfailed. **Mit's `saayam` entry still carries
     its one role-scoped bullet** — the code is his to merge and the `projection.yaml` edit plus its
     re-`approve-projection` are his to make (see *Live blockers*).
   - **The "sole iOS developer" prose is OWNER-GATED, not "one edit", and it lives in TWO files.**
     `wiki/00-profile/application-qa.md` already carries the full D-220 warning block; the prose under it
     is left verbatim **deliberately**, because rewording Mit's own writing is his alone (D-191) — so
     nothing is owed there but a rewrite only he can make. The upstream copy,
     `~/dev/Job apps/Common_App_Questions.md:8`, carried the same two claims with **no** warning and is the
     file a future application would be pasted from — **now flagged** with the same block, committed locally
     as `7dbc4ab` and **not pushed** (Mit's personal repo, his call). Its other answers were checked and
     deliberately left alone: the "gamified learning / 94% / 2,000+ students" claims belong to a *different*
     project, and Mit **retracted** the theory tying them to Knowledge Forge's AWS/GCP contradiction.
     **So all that remains here is Mit's rewrite of his own prose.** Note
     `~/dev/portfolio-website/wiki` is **not a git repo** — edits there have no undo.

   **Method facts this track established, all still binding:**
   **Do the PINNED entries first.** `select.py`: pinned entries are *"emitted in declared order, never
   scored, never dropped"*, and `_grow` adds candidates onto the pinned base one at a time until the page
   overflows. Pinned characters are spent **before any project competes**, so shortening a pinned entry
   does nothing for its own standing — it buys **admission headroom for the next candidate, on every
   posting**.
   **Bullets are the ONLY scored text.** Every scorer routes through `effective_skills(bullet.text, …)`
   (`scoring.py`); a `subtitle` earns **nothing**. The taxonomy does **not** know `Firebase`, `Firestore`
   or `SwiftData` — all extract `[]` — while `Swift` and `iOS` resolve. **Re-measure extraction after any
   length trim** and check the candidate's union is non-empty: a bullet can be entirely score-invisible
   and nothing warns you. This regression fired **twice** (D-213 FlickSwiper, D-215 StreakSync) — treat
   it as a required step, not a note.
   **D-213 fixes the house style** — state what was built with metrics, **never a story**, in Mit's own
   résumé voice; and a bullet is parked by dropping `'resume'` from `allowed_surfaces`, **not** by adding
   a fact (Stage 2 admits *entries*, so an extra fact renders unconditionally). **The rule splits by
   `kind:`** — a `project` entry's subtitle carries its tech stack (and often a `link_url`), so restating
   it wastes characters; a `kind: experience` entry's subtitle is `'{employment.organization}'` with **no
   link**, so its bullets are the **only** place tech keywords can appear.
   **Verification discipline that actually caught defects** (D-215/D-216/D-217/D-220): the résumé's own
   claims are never evidence — they cite themselves via `source.mit-resume`; **the working tree is not
   the repo**, so an absence needs `git log --all -S … -- '*.swift'` plus `git branch -a`, and a control
   test is only evidence about the corpus it ran against; **existence ≠ authorship**, settled by
   `git log --author` across the owner's *whole identity set*; `grep` here is a **ugrep wrapper honouring
   `.gitignore`** (use `command grep`/`rg --no-ignore`); `gh repo list` is mandatory before trusting any
   filesystem negative, because a private repo is invisible to disk **and** makes its org page look empty.
   Wording is Mit's (D-191) — no attestation for text he has not read.
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
   - **Education Slice C**; promoting `header/1`'s `person.professional_name` (the skill-item loop skips
     `header/*`).

**Fixture + corpus drift — the offline half is BUILT and gated (D-228).** R13/R14/R15 in
`tools/generalization/fixtures.py`, inside `make check` and the CI `generalization` job. **The 31 fixture
JSONs were ALREADY pinned by R7 — do not build a second manifest.** **R15 enforces that somebody reviewed
on schedule, NOT that a fixture matches production**; `tools.fixture_refresh --extend` restores green
offline by design. **On 2026-09-11 (greenhouse) the whole `make check` reds**, not one rule — several
real-tree tests assert the gate is clean. Drain it or re-capture. *Owner-gated:* the live-API comparison.
**Unfixed:** the corpus's generator `scratchpad/gen_corpus.py` was **never committed**, so the 987-row
oracle is **unregenerable**; and four fixtures are read by no test (`workable/dead_404.json`, plus
`normal_response_headers.json` under `workable/`, `smartrecruiters/` and `workday/`).

**Carried authoring facts (D-185/186/190/191).** **Three guarantees are each narrower than their name**, and
all three cost a real defect: **`approve` does NOT validate** (only `promote` refuses); **a plain `validate`
cannot see Gate B** (the completeness tier owns it, and every authoring command revalidates at the validity
tier only); and **`_catalog_admits` is a DIFF** refusing only what a write *introduces*, so a write that
silently *removes* findings passes every layer. Always `validate --draft` before Mit approves, and
`--completeness` too for anything touching `policy/`, the ledger or imports — **diff the blocker COUNT, not
just "0 error"**. `add-evidence` needs `--draft --evidence-file --capture`. **No CLI confirms a skill, and
none sets a fact's verification state** — the four `employment.organization` flips were hand-edits.
**Draft names: run `profile-bundle inventory` for the spent list — never a remembered one.** Twenty-two
are spent as of revision 21, and this file no longer enumerates them: the list went stale twice and it
is authoritative nowhere. **The bundle takes no lock** on `checkout`/`edit-fact`/`add-evidence` (only
`promote`/`rebase`/`approve` do), so check `inventory` for a recent write before authoring when more
than one session is live. **D-181:**
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
| *Projection* | ***MERGED AND PUSHED**, reviewed clean; Tasks 20 and 23 closed (D-197, D-198). **Pipeline integration slice P5a SHIPPED** — `run --project`, 11 reviewed tasks (D-225)* | *Projection-spec P0–P4 build gates met; **its P5 NOT met** — P5a only, the default flip is P5b* |
| *Gate B / master reservoir* | ***Stage 1 + Stage 2 DONE**; all 11 entities' bullets refined (D-213…D-221); live revision **21**. Digest deliberately omitted — refinement restamps it several times a day (D-017)* | ***MET — 0 blockers** (D-201), and **0 over-ceiling bullets** since revision 21* |

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
whether the daily pipeline gets projection — **yes, after v1**; the pinned/candidate split (D-195); whether
the 33 bullets get shortened — **DONE, all eleven entities, revision 21** (D-213…D-221); the two contradictory
job-apps dates — **ruled**, item 1; a skill listed under two groups — **refused**, D-210; **boardwatch's
Windows story — RULED best-effort, D-212**.)*

**Windows is best-effort (D-212)** — in the nightly, out of the pyproject classifiers, three caveats in
`README.md` (the fourth was this race and is now recorded there as fixed, with its residual). **A green 9-job push run contains ZERO Windows jobs** (`ci.yml`'s `os` matrix is conditional
on `schedule`/`workflow_dispatch`, D-151; the nightly is 12) — never read it as full-matrix coverage. A
**`nightly-watch`** job files a GitHub issue when a scheduled run fails and closes it on recovery:
**check for an open "Nightly CI is failing" issue at session start.** Both formerly-red Windows tests are
fixed: rich's `legacy_windows` off-by-one, and — as of D-224 — the stale-lock race itself.

**The stale-lock race is FIXED at the root, and all four `xfail` markers are GONE** (D-224, superseding the
D-212/D-222/D-223 suppression track). `locking.py`'s POSIX-only sentence is out; `bundle_lock` re-asks the
OS for `RECLAIM_WINDOW_SECONDS` — **1.0s on `win32`, 0.0 everywhere else, so POSIX is bit-identical** —
rather than believing one refusal. **Zero Windows `xfail` markers remain**; the surviving 4 xfails are
`test_projection_scoring.py:117`'s `strict=True` known-biased scorers, and always were a different four
(the removed markers were conditional on `win32`, hence ordinary passes off Windows).

**Two things about it are departures worth not rediscovering.** It departs from §21's *"no wait or
mutation"* on Windows only: a **genuine** refusal there now costs up to a second, bounded by a deadline.
And **1.0s is a judgement, not a measurement** — too short a window fails the way the module already did, a
false refusal, so it can be widened on evidence. The three deliberately-unmarked contention tests
(`promotion.py:892`, `rebase.py:1389`, `concurrency.py:234`) now read their timing budget as
`RECLAIM_WINDOW_SECONDS + 2.0` from the emitter; left as literals they would have gone flaky on Windows.

**VERIFIED ON WINDOWS as repair, not suppression.** A dispatch of `ci.yml` came back **success on all 12
jobs**, and the pytest summaries were diffed against the pre-fix dispatch rather than trusting the job
conclusions: **pre-fix Python 3.13 reported 5 xfailed / 3 xpassed**, so one of the four marked tests was
*genuinely failing* under its marker; post-fix it is **4 xfailed / 0 xpassed / 0 failed** on all three
versions, the 4 being the unrelated projection scorers. Totals reconcile exactly across two dispatches
(pre-fix `6381 + 4 xpassed = 6385` effectively passing, `+6` new tests = **6391**, `+7` = **6392** on the
final tip, `50 skipped` throughout), so the four tests moved from suppressed to passing rather than being
skipped or weakened. 3.11 and 3.12 xpassed all four *both* times — which is why a green run alone could
never have settled it, and why the **arithmetic** is the evidence. The seventh test also settles that two
handles in one process contend on Windows via `msvcrt.locking` as two file descriptions do via `flock`.

**`make check` can NEVER verify this work** (it passes, and passed before the fix too) — the window is inert
off `win32`. Windows evidence comes only from a **`workflow_dispatch`** of `ci.yml`, which builds the full
12-job matrix and takes **~1 hour** (Windows jobs measured at 40–62 min; 3.13 is usually the long pole).
It **cannot close issue #76** —
`nightly-watch` is gated `if: always() && github.event_name == 'schedule'` (`ci.yml:99`), so only the 07:00
UTC scheduled run files or closes one. Read the dispatch's three `windows-latest` jobs directly; a
still-open #76 is not evidence the fix failed.

**`nightly-watch` issue #76 is OPEN**, filed by scheduled run `32007953224` (a tip that predated even the
markers). Expect it to close on the first nightly that runs with D-224 merged.

**BOTH locks now carry the window, and both are VERIFIED GREEN on Windows.** `core/lock_reclaim.py` owns
`RECLAIM_WINDOW_SECONDS` / `RECLAIM_POLL_SECONDS` and the bundle writer lock and the **scan lock** both
bind it (D-227). The scan lock mattered more despite never having been observed firing: scanning runs
**unattended**, so a killed scan followed by a refused scheduled scan is a **silent empty day**, not a
retryable prompt. Both consumers bind the constants **by name**, so patching `core.lock_reclaim` reaches
neither — patch the consumer, and a test compares both bindings against the source so they cannot drift.

**Three facts from D-227's red first dispatch, kept because they change what a future session does** (the
narration is in D-227): **a timed assertion must enclose only the span it claims** — setup inside the timer
measured a Windows filesystem, not the lock; **forcing a platform's constant does not simulate its
backend**, so a local window-on run proves nothing about `msvcrt` or runner speed; and `gh run view --log`
refuses while *any* job still runs, whereas **`gh api repos/{o}/{r}/actions/jobs/{id}/logs
--allow-escape-sequences`** serves a finished job's log at once.

**One false-refusal exposure is left standing DELIBERATELY (D-224) — do not "fix" it without the owner.**
**POSIX is not exempt.** `UnixFileLock` unlinks the lockfile *before* releasing the `flock` and discards an
already-unlinked inode, so a second writer that opened it first can be reported `bundle_lock_held` while
nobody holds the lock — a **live-holder handoff** race, reproduced on macOS local disk, no network
filesystem needed. **Ruled: record, do not widen the window** — closing it costs a wait where §21 grants
none on the platforms boardwatch actually runs on. `bundle_lock` is the only acquire path *inside*
`profile_bundle`, and `coordinator.run_scan` the only one in `scan`.

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Content comes from the wiki; the bundle is what renders; wording is `edit-fact`'s job (D-190). Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`add-evidence` takes no bundle lock, and D-143 widened the race** | Only `promote`/`rebase`/`approve` take `bundle_lock`. Two concurrent captures race on up to 13 files; a lost update leaves a silent `evidence_link_asymmetry`. Raise it before anyone runs two authoring agents against one bundle | owner-gated |
| **P2 item 8 — the onboarding gatherer** | What would make the field tier fire for anyone. D-054 forbids us authoring non-tech field content. Its open architecture question: a genuinely new field rule is still *code*, not data | owner-gated |
| **Four `runs` rows are `running` WITH `finished_at` set, and no drain can clear them** | **DIAGNOSED 2026-08-17; two prior claims in this row were wrong.** `reap_stale_runs` (`store/queries.py:153-203`, predicate at `183-187`) does exclude ids 1–4 — and `tests/unit/test_queries.py:136-151` **pins that exclusion as intentional**, so it is not an oversight. **The cause is not `top`** — `top_cmd.py` never called `insert_run`/`ensure_run`; only `scan/coordinator.py`'s `insert_run` call could have created them (cited by symbol: D-227 shifted its line). It was migration `p0_run_status.py` (commit `541dfdd`, 2026-08-06) adding `status` with `DEFAULT 'running'`, which backfilled already-closed rows; row 5 onward is a clean `ok`/`failed` split, and **the mechanism cannot recur** through today's write path. **Blast radius: nothing observable** — every other `runs` query is scoped by `run_id` or `finished_at IS NULL`, `doctor`'s in-progress guard reads `finished_at`, and `verify` discovers runs only from `funnel-<run_id>.json` artifacts that postdate all four. So the leak is real but **inert**. Recommended repair: a one-shot predicate-matched (never id-hardcoded) migration for the four, plus a doctor-time invariant so recurrence is loud — a `CHECK` constraint would need a 6-FK table rebuild, disproportionate. **Owner-gated: which terminal status the four rows get** (re-derived `ok`, conservative `failed`-with-breadcrumb, or a new `unknown` catalog value) — a per-gate fail-safe call, since silently rewriting run history differs from leaving an audit trail | P3 |
| **`boardwatch top` advances the queue by default** | Records `seen` unless `--no-record`, so exploratory ranking mutates dedup state — directly relevant to Gate P6's clean 7-day window | P6 |
