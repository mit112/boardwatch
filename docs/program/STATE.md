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

**The headline number: 0.** Zero job applications have ever been sent (`applications` has 0 rows) — the
machine produces leads, it never applies (out of scope). Against that: 3 published releases (none since
**0.3.0**), ~53k lines of source, **~6,900 tests**, 70 leaf CLI commands, 6 ATS providers, a **~1.0 GB**
store.

**P3 MILESTONE — the 08:00 schedule fired for the first time (D-254).** On **2026-08-20 08:00:22 CDT** the
launchd trigger fired unattended: `launchctl` `runs` went 1→2 and **run 63 completed clean** (exit 0, ~50 min,
funnel RECONCILES, 8 leads / 8 one-page PDFs, all US-located). This resolves D-248 — the trigger was never
*broken*, it had simply had no prior opportunity (the Aug-19 plist post-dated that day's window; run 61 was a
kickstart). **Gate P3 is now 1 of 7 UNATTENDED** — it needs 7 consecutive clean scheduled runs. There is still
**no external alarm for a MISSED window**: only a run that happens can notice one that didn't.

**Run 63 funnel:** 135 boards → 26,442 corpus → **13,756 eligible / 11,034 uncertain (D-250) / 1,652
ineligible** → shortlist **8**. **3,453 postings cleared every filter and were cut only by `DEFAULT_TOP_N`** —
the precision tension Mit rules on: fix precision, never tune the cap (ideally show everything eligible).

**Eligibility now decides AND removes.** `work_authorization.needs_sponsorship=true` set (D-249); a
zero-evidence `eligible` abstains to `uncertain` (D-250); two rules that could never resolve MET are fixed —
`degree:any_degree_required` and `work_auth:sponsorship_available` (D-256, #107); and **clearance is armed as
a `blocker`** with `security_clearance={state:none,level:none}` (D-257) so the ~138 clearance-required
postings resolve UNMET → ineligible → dropped.

**Role-gate precision tightened across three passes.** Pre-sales/support/BD consistency denies + "SW Engineer"
signal (D-252/253); non-eng managers/directors + Data Scientist/Analyst out of scope (D-255, #106); and the
run-63 business/ops/admin/pricing leaks — Strategy & Ops, Business Operations/Partner, Stock Plan, Pricing
(D-259, #108). Run 63's ranked top 40 was **~28% non-software** before #108. **Deferred to owner** (borderline):
Team Leader, Data Center Engineer, bare Administrator. **NOT excluding "User Researcher"** — it overlaps real
ML/Research *Engineer* roles, so a broad researcher deny would drop software (Mit's call). Note: for Mit, the
manager/director deny is redundant with his `exclude_titles`, but it is the correct generic (multi-tenant) form.

**Hard location gate is US-only, ARMED and verified firing (D-251).** `config.toml`
`location_filter_mode=hard`; `rank/location_gate.classify_location` is a positive US allowlist (fail-open on
the unclassifiable, Mit's visa ruling). Run 63 confirmed it: all 8 leads carry US `locations_json` (the funnel's
"never measured firing" line is a stale template string). Default stays `soft` for other users.

**Armed pending Mit's ONE TTY act (D-258):** seniority band = `entry` (activates the merged-but-inert gate;
ambiguous level tokens like "Level 3" still ABSTAIN and pass — ladders are not guessed) **and** internships via
`exclude_titles` (`Intern`, `Internship`, `Co-op` — title-based, trap-safe; the engine is body-only so it
cannot do this — see below). `boardwatch profile edit`, answer "no" to eligibility, then `ledger reopen --stale`
after the next run (both fields re-key `policy_version`, ~11 rows).

**The eligibility engine is body-only** — `preflight.py` feeds it `posting_versions.body_text` with no title
column — so title-based filtering (internship, seniority words) lives in the ranker (`exclude_titles`,
`role_gate`, `seniority_gate`), never the engine. job-apps (consulted this session) detects intern/co-op BY
TITLE for exactly this reason; boardwatch's body-only `internship_role_declared` is 100%-precision/~27%-recall
and already suppresses the "internships count" trap.

**CI health — two intermittent flakes.** Tectonic LaTeX-over-network `compile_failed` and
`test_two_writer_concurrency` "database is locked" (under `-n auto`) redden the nightly (#95) and block
auto-merge. Recovery is `gh run rerun <id> --failed` (Mit's ruling: re-run, not admin-bypass or refactor);
local `make check` stays green (a CI-only divergence). Hardening is a deferred reliability win.

**The roadmap is UNFROZEN (D-240); its remaining gates are OPERATIONAL, not build.** P0/P1/P2/P5 gates are
**MET**. P3/P4/P6 builds are essentially done; their gates now close by *running* boardwatch daily. Gate P4
(Mit's blind craft review) is barred until P3's gate is met. Gate P6 needs a real 7-day dedup window plus
liveness-probed leads. The 14-day acceptance clock starts after P6; **P7 breadth stays last.**

**The bundle → résumé + projection + render tracks are COMPLETE and merged; nothing is queued there.** Gate B
is **MET** (0 blockers, D-201); 11 entities refined within the 220-char ceiling; projection reaches the daily
pipeline behind opt-in `run --project` (D-225); the render stack shipped ATS-parsable PDFs (D-233),
`fill_to_page` (D-234), `link_in_first_bullet` + `sort_projects_by_date` (D-235). **What is left on the résumé
is Mit's alone**: whether to send a document, and the two owner-gated prose rewrites of D-220. `resume.yaml` is
an import source, never hand-fixed (D-155).

### Reference facts (do not re-derive)

- **Bundle track:** live revision 22, 11 entities. Do not quote its digest (restamps daily, D-017); re-derive
  with `profile-bundle inventory`. Facts stay `owner_attested` (D-191). Editing is incremental (D-190):
  `checkout --draft` → `edit-fact` → `validate --draft` → Mit's **TTY** `approve` → `promote`. `approve` does
  NOT validate; a plain `validate` cannot see Gate B; `_catalog_admits` is a DIFF — always `validate --draft`
  and diff the blocker COUNT before Mit approves.
- **Stage 2** is live; the one-page budget is a **character** budget ≤ **3,439** (D-219). `mean_per_bullet` is
  the default scorer; `ADMISSION_FLOOR` stays `Decimal(0)` (D-197/8).
- **P5b criteria NAMED (D-229):** 3 clean projected runs, ≥30 postings, 0 preflight fatals, 0 résumé-QA
  failures, 0 fabrications. Four of five evidenced on a store copy.
- **Settled — do not reopen:** Projection (D-156/163); Gate A MET (D-157); autonomous backlog COMPLETE
  (D-202…D-210, D-237); Education Slice C (D-239); D-184 finding 2 (D-238).
- **Fixture + corpus drift (D-228):** R13/R14/R15 in `tools/generalization/fixtures.py`. The corpus content
  pin was re-recorded this session for the m0105 fix (987 rows unchanged). **On 2026-09-11** the greenhouse
  fixture reds `make check` — drain or re-capture. `scratchpad/gen_corpus.py` is uncommitted, so the oracle is
  unregenerable.

### Owner-gated — do NOT start unilaterally

1. **P2 item 8 — the onboarding field-taxonomy gatherer** (needs its own brainstorm). D-054 forbids us
   authoring non-tech field content.
2. **Mit's two résumé content calls** — whether to send; the D-220 prose rewrites.
3. **`add-evidence` takes no bundle lock** (D-143) — raise before two authoring agents run against one bundle.

---

## Phase status

| Phase | Build | Gate |
|---|---|---|
| P0 Instrumentation | **COMPLETE** | **MET** (D-030) |
| P1 Résumé artifact gate | **COMPLETE** | **MET** (D-032/033) |
| P2 Profile + keystone | items 1–7 shipped; item 8 NOT STARTED | **MET AS RECONCILED** (D-075) |
| P3 Unattended one command | **COMPLETE, INSTALLED, FIRING** — run 63 was the first genuine scheduled run (D-254) | **NOT MET — 1 of 7 unattended.** Accrual has begun |
| P4 Craft gate | **COMPLETE** | **NOT MET** — the owner's blind craft review, barred until P3's gate |
| P5 Eligibility decides | **COMPLETE** | **MET** — INELIGIBLE precision 16/16, 0 span violations |
| P6 Liveness + dedup | **BUILD COMPLETE** (D-110/111/113) | **NOT MET — 2 of 4** — needs a real 7-day run |
| 14-day acceptance | not started | starts after P6 |
| P7 Breadth | not started | gated on P0 attribution data |
| *Gate A / Gate B* | *complete, merged* | ***MET*** — *has moved no program gate* |

### Gate P6, clause by clause

| Clause | Standing |
|---|---|
| Duplicate leakage over 7 days ≤ 5% | **NOT met.** One-shot baseline 0.79%, but not over 7 days |
| **0** dead postings reaching leads | **NOT met.** Needs a real probed run; recall low by design |
| Injected hash-collision test | **MET** (D-100) |
| Audit of 20 sampled suppressions | **MET** (D-101) |

---

## Open questions — Mit's, not to be resolved by fiat

1. **Should `pipeline/runner.py` keep swallowing a funnel-write failure into a printed warning?** (D-076.)
2. **The projection spec's six open questions** (§12) — soonest: whether `tailor run` should validate the
   projection manifest, and whether persona's `entries` list survives stage 2.
3. **The Snap `Level 5`/`Level 3` leak stays open by design** — with no bindings file every level token
   abstains, so a level-named title is shortlisted carrying its reason. Closing it takes one deliberate
   binding line; boardwatch ships no verifiable claim about any company's ladder ("Level 3" is entry at some
   shops, senior at others — Mit's point: read the JD's fine print, don't guess).

*(Recently resolved: open Q2 — clearance IS now a blocker (D-257); open Q4 — seniority band = `entry`, arming
pending Mit's TTY (D-258); the launchd trigger — FIRED (D-254).)*

---

## Windows and the lock reclaim window

**Windows is best-effort (D-212)** — in the nightly, out of the pyproject classifiers, caveated in README. A
`nightly-watch` job files a "Nightly CI is failing" issue on a failed scheduled run and closes it on recovery
— **#95 is OPEN now** (the two CI flakes above); it will auto-close on the next green scheduled run.

**The stale-lock race is FIXED at the root; all four `xfail` markers are gone on `main`** (D-224/227).
`core/lock_reclaim.py` owns the constants — **1.0s on `win32`, 0.0 elsewhere, so POSIX is bit-identical**.
Windows evidence comes only from a `workflow_dispatch` of `ci.yml`. **One false-refusal exposure is left
standing DELIBERATELY (D-224):** POSIX `UnixFileLock` unlinks before releasing the flock, so a live-holder
handoff can report `bundle_lock_held` while nobody holds the lock. **Ruled: record, do not widen.**

---

## Live blockers and carried gaps

| Item | Detail | Owner |
|---|---|---|
| **Mit's ONE TTY act (D-258)** | `profile edit` → band `entry` + add Intern/Internship/Co-op to `exclude_titles` + "no" to eligibility; then `ledger reopen --stale` after the next run | **Mit** |
| **#108 final pull owed** | #108 (business/ops role gate) was auto-merging at session close; `git pull` the live checkout once it lands so tomorrow's run has it | next session |
| **CI has two intermittent flakes** | tectonic network + `test_two_writer_concurrency`; re-run failed jobs to recover; local `make check` stays green | tooling |
| **No external missed-window alarm** | nothing outside a run can detect a missed 08:00; the funnel heartbeat is only written from inside `runner.py` | P3 |
| **`resume.yaml` is an IMPORT SOURCE, never hand-fixed** | D-155. Mit pins `resume_max_pages=1`; never advise 2 | Mit |
| **`boardwatch top` advances the queue by default** | records `seen` unless `--no-record`; relevant to Gate P6's clean window | P6 |
| **`add-evidence` takes no bundle lock** | two concurrent captures race on up to 13 files (D-143) | owner-gated |
| **`make check` must be launched DETACHED** | the Bash tool clamps `timeout` to 10 min; a longer gate reads as `Error 143`. Launch double-fork + `setsid` and poll the log | tooling |
