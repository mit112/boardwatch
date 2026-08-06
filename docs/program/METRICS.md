# Metrics

One row per run, so gates are checkable over time rather than at a moment. Append; never rewrite history.
A metric that is not yet emitted is recorded as `—` (not emitted) rather than `0` — the distinction matters,
because "no fabrications found" and "fabrication check does not run" look identical in a zero.

---

## Baseline — 2026-08-06, before any program work

Measured directly from the repo and the live SQLite store at
`~/Library/Application Support/boardwatch/boardwatch.db`. These are verified numbers, not recollections.

### Inventory and scale

| Metric | Value | Source |
|---|---|---|
| Companies in store | **135** | `select count(*) from companies` |
| Postings in store | **19,448** | `select count(*) from postings` |
| Jobs in store | **19,448** | `select count(*) from jobs` |
| Shipped seed registry entries | 37 | `registry/companies.yaml` |
| ATS providers | 6 | Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday |
| CLI commands | 17 | `cli/app.py` |
| Source lines (`src/boardwatch`) | 14,431 | `wc -l` |
| Test functions / files | **1,194** / 124 | `grep -c "def test_"` |

**`jobs` = `postings` exactly.** `job_id` is 1:1 with postings; grouping has never run. Duplicate leakage
is structurally unmeasurable until P6 — not merely unmeasured.

### The bar (§1 of PROGRAM.md) — baseline readings

| # | Metric | Bar | Baseline | Note |
|---|---|---|---|---|
| B1 | Net-new eligible/live/deduped leads/day | ≥ 10 | **—** | No funnel artifact exists yet (P0) |
| B2 | Leads with a compiled PDF | 100% | **—** | Not measured; silent source-only degrade exists (D-006) |
| B3 | Leads passing the résumé QA gate | 100% | **—** | Gate does not exist (P1/P4) |
| B4 | Fabrications on n ≥ 100 | 0 | **—** | Tier A is provably entailed; Tier B judge is unaudited at n≥100 |
| B5 | Silent empty days | 0 | **—** | No unattended runner (P3) |
| B6 | Funnel reconciliation | 100% | **—** | No reconciliation check (P0) |
| B7 | Work authorization resolved decisively | required | **FAILING** | 0 postings can ever be `ineligible` for Mit — verified below |

### Verified defects at baseline

| Defect | Evidence | Phase |
|---|---|---|
| Work auth never resolves UNMET | `resolve.py:174,182,188,196` — `ead_or_similar` returns MET or UNKNOWN on all four work_auth paths, never UNMET. Deliberate (comment at 167–177), but it means **0 postings are ever `ineligible` for Mit**. | P2 |
| No page-count enforcement | `grep page_count\|num_pages src/ tests/` → no matches | P1 |
| Silent source-only degrade | `cli/tailor_cmd.py:193,402` | P1 |
| Compile log discarded | `reports/tailor.py:104` captures output, never reads it | P1 |
| No per-rule abstain reporting | Not emitted anywhere | P0 |
| Applied-state never suppresses | No `applied` reference in `store/queries.py` or `cli/top_cmd.py` | P6 |
| Application ledger unexercised | `applications` = 0 rows, `application_events` = 0 rows | P6 |
| No anti-slop guard | No equivalent of `overmatch.py` | P4 |

### Environment

| Fact | Value |
|---|---|
| `typst` binary | **present** — `/opt/homebrew/bin/typst` |
| DB path | `~/Library/Application Support/boardwatch/boardwatch.db` |
| Store tables | 22, incl. `runs`, `posting_events`, `eligibility_evaluations`, `artifacts`, `artifact_derivations`, `job_grouping_events` |

**Note on instrumentation — CORRECTED 2026-08-06 (D-013).** The original claim here was *"P0 is
substantially a matter of rendering what the schema already records, not of adding capture."* **That is
wrong.** Independent review found:

- Only four tables carry `run_id`: `posting_versions`, `posting_version_sources`, `board_scans`,
  `posting_events`. **`eligibility_evaluations`, `eligibility_inputs`, `extractions`, `artifacts`,
  `applications` and `application_events` have none** — so `eligible/ineligible/abstained`,
  `leads_with_pdf` and `marked_applied` (three of the seven funnel stages) cannot be attributed to a run
  without a migration.
- `eligibility_evaluations` carries `uq_eligibility_deterministic ON (input_id, engine_version)`, so a
  re-run over unchanged postings writes **no rows at all**. Runs 2 and 3 of the P0 gate would show ~0
  evaluations against a non-zero candidate count, and a timestamp join cannot fix it — "cache hit" and
  "never judged" are indistinguishable, which is precisely the failure D-012 exists to prevent.

**P0 therefore includes an Alembic migration** adding nullable `run_id` to `eligibility_evaluations` and
`artifacts`, and the reconciliation invariant must count **cache hits as their own asserted stage**.

---

## Run log

One row per run. `—` = not emitted.

**Read the columns, not the row.** `Judged` is *this run's* attribution (`judged_this_run`); the verdict
columns are the **whole current-identity corpus**, not a subset of `Judged`. Runs 7 and 8 judged nothing
new and still report 18,174 eligible, which is correct and is not a funnel edge. Chaining these columns
left-to-right would reproduce exactly the arithmetic D-022 exists to prevent.

`Unique` is **`—` (not emitted)** and will stay so until P6: dedup has never run, and a `0` there would
assert that boardwatch measured duplicates and found none.

| Date | Run id | Corpus | Unique | Judged | Eligible | Ineligible | Abstained | Leads | PDFs | QA pass | Stub rate | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-06 | 6 | 19,262 | — | 8,462 | 18,174 | 0 | 1,088 | 3 | 3 | — | — | 0 |
| 2026-08-06 | 7 | 19,262 | — | 0 | 18,174 | 0 | 1,088 | 3 | 3 | — | — | 0 |
| 2026-08-06 | 8 | 19,262 | — | 0 | 18,174 | 0 | 1,088 | 3 | 3 | — | — | 0 |

**These three rows were read out of the artifacts, not assembled by hand from ad-hoc queries** — which is
the whole requirement, since Gate P0 asks for the funnel to be answerable *from the artifact alone*.

**They are NOT the gate.** All three ran `--no-scan` against a copy of the production store, so the scan
stage was never exercised, and `Observed` is deliberately renamed `Corpus` here: the funnel's head is every
open posting, not the count a scan listed (D-022). The gate needs three consecutive runs of the real
driver, scan included.

---

## Per-rule abstain rate

The metric that makes a rule which cannot fire visible. A rule at 100% abstain is a monitoring failure,
not a conservatism feature.

**This table is superseded and kept only for its baseline column.** P0 item 2 shipped in session 3
(`boardwatch eligibility abstain`) and item 1 now emits all 44 rules inside every run's funnel artifact.
The live figures are in "Session 3" and "Session 5" below; do not maintain this table by hand.

| Rule | Declared fields | Baseline abstain | Latest |
|---|---|---|---|
| `work_auth` | `work_authorization.status` | **~77%** (measured under review 2026-08-06, not 100% as originally inferred) | see sessions 3 and 5 |

**The `—` vs `0` convention worked on its own author.** This row originally read *"100% (inferred from
D-007; not yet emitted)"*. Because it was labelled as inferred rather than stated flat, review caught it
and measured the real figure: **~77%**. Keep labelling inferences.

### The severity layer — the reason `ineligible` is structurally unreachable

Measured 2026-08-06 (D-013). `facts.py:66`: *"Only `blocker` can yield `ineligible`."* All six families
ship `default_policy: preference` (`rules.yaml:72,290,388,606,871,1032`). Live consequence:

| Measure | Value |
|---|---|
| `unmet` REQUIRED dispositions | **1,713** |
| Evaluations carrying ≥1 unmet-required, still verdict `eligible` | **1,427** |
| Verdict `ineligible`, all time | **0** |

Mit is unaffected — he set `work_auth: blocker` by hand. **A fresh user with a perfect profile gets zero
ineligible verdicts by default**, which is the multi-tenancy requirement failing at exactly the point
`CLAUDE.md` says it must not. P2 owns this.

---

## Acceptance run

Starts only after P6, on a frozen system. Any change to eligibility, profile, or the résumé gate resets the
clock; record the reset here with its cause.

| Day | Date | B1 leads | B2 PDF% | B3 QA% | B4 fab | B5 empty | B6 recon% | B7 decisive | Notes |
|---|---|---|---|---|---|---|---|---|---|
| _(not started)_ | | | | | | | | | |

---

## Session 2 — 2026-08-06, P0 measurements

Measured this session against the live store and the catalog loader. Two of session 1's descriptions of
the schema were imprecise in ways that would have mis-shaped the funnel; both are corrected here.

### Corrections to session 1's record

| Session 1 said | Actually | Why it matters |
|---|---|---|
| `uq_eligibility_deterministic ON (input_id, engine_version)` | It is a **partial** unique index: `... WHERE engine_kind = 'deterministic'` (`tables.py:259-260`, `p0_eligibility.py:67`) | LLM-lane evaluations are **not** deduped by it, so the cache-hit stage is lane-specific, not one number |
| The abstain verdict | There is **no** `abstain` value. Stored vocabulary is `eligible \| ineligible \| **uncertain**` (CHECK at `tables.py:262`) | The keystone invariant's ABSTAIN is persisted as `uncertain`; the funnel must state the mapping or look like it is missing a stage |

### Rule catalog — enumerable, and 7 rules have never fired

| Metric | Value | Source |
|---|---|---|
| Families | **6** | `eligibility/rules.yaml`, `families:` |
| Individual rule patterns | **44** | 8 work_auth · 5 experience_years · 13 clearance · 13 degree · 4 contract_not_fte · 1 internship |
| Canonical rule identity | `f"{family}:{pattern.id}"` | `catalog.py:98-105` (`PatternSpec.rule_id`) |
| Pure enumeration (no evaluation) | `load_rules(config_dir)` → `[p.rule_id for f in c.families for p in f.patterns]` | `catalog.py:180` |
| Distinct `rule_id` ever detected | **37** of 44 | `select count(distinct rule_id) from eligibility_requirements` |
| **Rules that have never fired once** | **7** | `clearance:{sap_access,nato_access,active_confidential,doe_q,doe_l,public_trust}_required`, `work_auth:eu_authorization_required` |

**A `GROUP BY rule_id` cannot produce this metric.** Those 7 rules emit no group at all — not 0%, absent.
No table enumerates the catalog, so per-rule abstain *must* enumerate from `load_rules()` in Python and
LEFT JOIN, or a rule that cannot fire stays invisible. That is the failure the metric exists to prevent.

### A 100% abstain rate already exists, live

| Rule | Rows | Abstained (`unknown`) | Rate |
|---|---|---|---|
| `experience_years:scoped_years_minimum` | 11,670 | 11,670 | **100%** |

Its abstains split 10,523 `"requirement is scoped to a skill; no per-skill durations stored"`
(`resolve.py:207-210` — unconditional for this pattern) + 1,147 stage-1 conflict. Separately,
`clearance:clearable_required` returns UNKNOWN unconditionally regardless of facts (`resolve.py:244-245`).
Per `CLAUDE.md`, these are monitoring failures, not conservatism.

### Live ledger totals

| Measure | Value |
|---|---|
| `eligibility_inputs` / `eligibility_evaluations` | 20,637 / 20,637 (1:1; deterministic only, 0 llm rows) |
| Verdicts | eligible **19,527** · uncertain **1,110** · ineligible **0** |
| `eligibility_requirements` rows | 17,753 — met 1,915 · unknown **14,112** · unmet 1,726 |
| Profile policy override | `{"families": {"work_auth": "blocker"}}` — the only non-default |

### Funnel attributability before this session's migration

**1 of 7 stages** was run-attributable (`observed`, via `runs.postings_seen` / `board_scans.postings_listed`).
`unique` is structurally identical to `observed` until P6 ships an identity layer. `candidates`,
`prefilter_stopped`, the verdict split, `leads_with_pdf` and `marked_applied` were all unattributable.
The `run_attribution` migration (`c56bc11`) addresses the schema half for two of them.

### Two things that will not yield to a query

- **`disposition='unknown'` conflates four distinct causes** — catalog `abstain_by` escape, stage-1
  exclusive-group conflict, stage-1b split-threshold conflict, and resolver-missing-fact. They are
  separable only by free-text `rationale`, which carries **no CHECK constraint** (unlike `disposition`), so
  a source edit changes the strings silently. Per-rule abstain *rate* is computable; typed abstain
  *reason* — which the keystone invariant's `ABSTAIN(missing_profile_field:X)` requires — is not.
- **`RewriteRow.drop_reason` is 12 bare untyped strings** (`None`, `budget`, `error`, `no_candidate`,
  `unchanged`, `judge`, and 6 `filter:*` values), contradicting `CLAUDE.md`'s "typed violations at the
  raise site". Aggregates are computed twice for `console.print` (`cli/tailor_cmd.py:196-204`, `:407-414`)
  and discarded. Raw rows do survive into `artifacts.meta_json` on non-dry-run Tier B only. Tier A's
  fail-safe (`TierASafetyError`) is a whole-run raise with **no counter anywhere**.

### One more trap for the artifact writer

`artifacts.uri` stores the **`.typ` source path, not the PDF** (`reports/tailor.py:388-397,421`). Whether a
PDF compiled lives only in `meta_json.typst_pdf_built`. So `leads_with_pdf` is
`json_extract(meta_json,'$.typst_pdf_built') = 1`, not a row count — a `resume_tailored` row can exist with
no PDF, which is exactly D-006's silent degrade. Also: generalization rule **R6 forbids any `.pdf` in the
tracked tree**, and R7 requires a `SHIPPED_DATA` entry with a sha256 pin for tracked `.json`; `.md` is
exempt from R7. The funnel artifact must therefore be written outside the git tree, as tailored résumés
already are.

---

## Session 3 — 2026-08-06 · per-rule abstain rate, measured

First run of `boardwatch eligibility abstain` (commit `540bb34`) against the live database.
Scope is **current evaluations for the current identity** — the same scope `eligibility summary` uses, so
these are smaller than the all-time totals recorded in session 2 and that is expected, not a discrepancy.

**Catalog coverage: 44 rules · 16,674 requirement rows across 19,262 evaluations · 0 unattributed ·
0 out-of-catalog.** (All-time, for comparison: 17,753 rows / 20,637 evaluations. The independent review
re-derived 7 never-fired and 17 fully-abstaining in *both* frames, so neither pathology is an artifact of
scoping.)

| Bucket | Count | Meaning |
|---|---|---|
| Never fired | **7** | No detection has ever matched. Invisible to `GROUP BY`; this is why the metric enumerates the catalog. |
| Fire but never decide | **17** | 100% abstain. The rule matches JD text and then resolves to `unknown` every single time. |
| Working | 20 | Abstain rate strictly between 0% and 100%, or 0%. |

### The 17 that fire and never decide

**The entire `clearance` family.** All 7 clearance rules that have ever fired are at 100%: `polygraph`
(3), `active_ts_sci` (8), `active_top_secret` (7), `active_secret` (16), `generic_clearance` (38),
`clearable` (22), `clearance_preferred` (11) — **105 detections, 0 met, 0 unmet, ever.** The family has
never once decided anything. `clearance:clearable_required` is unconditional by construction
(`resolve.py:244-245` returns UNKNOWN regardless of facts); the other six are not, and their being at 100%
too is the finding.

**`work_auth` — 6 of the 7 rules that fire.** `no_sponsorship_offered` is **1052/1052 abstained**: a
thousand postings stated in their own text that no sponsorship is offered, and the engine declined to
conclude anything on every one. `us_citizen_required` 47/47, `us_citizen_or_lpr_required` 14/14,
`uk_authorization_required` 8/8, `ca_authorization_required` 6/6, `sponsorship_available` 1/1. Only
`us_authorization_required` decides (336 rows, 335 met).

This is **bar metric B7 measured rather than asserted**, and it is the strongest evidence yet for D-007:
the engine is not short a profile object, it is short the one disambiguating bit. `ineligible` is 0 across
the entire database by design, and this is the mechanism by which that happens.

**`experience_years:scoped_years_minimum`** — 10,872/10,872, the single largest abstaining rule and 65% of
all requirement rows.

**Four `degree` rules** at 100%: `bachelor_in_field_required` (79), `any_degree_required` (32),
`master_in_field_required` (17). The `_in_field` variants abstaining while their plain counterparts decide
(`bachelor_required` 17%, `master_required` 32%) points at a missing field-of-study fact, not a broken rule.

### What this does not yet tell us

The rate is computable; the typed **reason** is not. `disposition='unknown'` still conflates four causes
separable only by free-text `rationale` (session 2, above). So "17 rules never decide" is solid, and "why"
is per-rule guesswork until the abstain reason is typed at the raise site. That is the next thing P0 owes
the keystone invariant.

---

## Session 4 — 2026-08-06 · the pipeline-run row (P0 items 0 and 7)

### What changed in what the store can answer

| Question | Before | After |
|---|---|---|
| Which run judged this posting? | unanswerable — `run_id` was NULL on all ~20,637 evaluations | answerable for every evaluation written from now on |
| Which run produced this résumé artifact? | unanswerable — NULL on all artifacts | answerable |
| Does any code path span scan → eligibility → tailor? | **no** — the only one was gitignored shell | `boardwatch run` |
| Does `NULL run_id` have one meaning? | n/a (everything was NULL) | **yes** — "predates attribution", a set that can only shrink (D-019) |

**Not yet answerable when this was written — item 1 has since shipped the per-run artifact, and the
per-source half is item 3:** the funnel counts per run, per source, as an artifact. The run
row is the key; the artifact is the deliverable. **Gate P0 remains not met.**

### Gate

`make check` exit **0** — generalization OK, ruff clean, mypy `--strict` clean on 147 source files,
2679 tests passed, coverage 94.99% (threshold 85%). Measured in plain mode with the real exit code.

### Test-pinning discipline, applied and worth recording

Every new test was mutation-checked: the behaviour it names was removed, the test was watched go red, then
the fix was restored. Eight mutations across the two new files; each produced exactly the failures expected
and no others. The check earned its keep — it surfaced that `finalize_run(finished=False)`, the change that
stops the scan stage from marking a pipeline complete, had **no test at all**. Two were added.

This is the third consecutive session in which the review-worthy defects were in tests and documents rather
than logic (D-017, D-018, and now this). The pattern is stable enough to treat as a rule.

### Independent review — the pattern from sessions 1–3 broke

Three consecutive sessions had reviews that found **only** documents and tests. This one found **eleven
defects, most of them in logic**, all in code written the same session. Recorded because the earlier
pattern was starting to look like a property of the program rather than of the work being reviewed:

**Two** reviews ran, and the second — on the fix commit — found **eight more**, one of which was a defect
in the first review's fix. Nineteen findings total on one change.

| Class | Review 1 | Review 2 | Examples |
|---|---|---|---|
| Logic / correctness | 6 | 3 | run row minted outside the scan lock; scan errors persisted twice; the dangling-row fix left the scan window open; a crash recorded as a clean empty run |
| Signal destruction | 2 | 1 | exit 1 on every real run — then, after the fix, **exit 0 on a total network outage** (bar metric B5) |
| Tests that cannot fail | 2 | 2 | `X == X` cross-check; asserting a value written at row birth; a board-failure test that never failed a board; an untested exit-1 path |
| Test hygiene | 0 | 1 | three tests making live HTTP calls to a real ATS endpoint |
| Wrong message / docs | 1 | 1 | `doctor` calling every unfinished run a scan; a CHANGELOG claim true only of one code path |

**Both untestable tests had been mutation-checked and both survived**, because the mutation was derived
from the code rather than from the claim the test's docstring made. That is the transferable lesson and it
is now in D-020.

### Live verification — D-019's invariant, measured on a copy of the real store

`boardwatch run --no-scan --top 3` against a copy of the production database (580 MB, 19,262 open
postings). Real exit code captured, not piped — an earlier attempt read `tail`'s status through a pipe and
was killed mid-eligibility without my noticing, which is the trap already recorded in memory.

**The copy was deleted and re-made from production before this run**, so the "Before" column below is the
untouched production baseline and not the residue of that aborted attempt (which had left 11,200 attributed
evaluations and one unfinished run). Stated because otherwise the two accounts in these documents cannot
both be readings of one store.

| Quantity | Before | After | Meaning |
|---|---|---|---|
| `runs` rows | 4 | 5 | one pipeline run |
| `runs` with `finished_at IS NULL` | 0 | **0** | the run closed itself |
| evaluations with a `run_id` | 0 | **19,262** | threading works at production scale |
| evaluations with `run_id IS NULL` | 20,637 | **20,637** | **unchanged — not one row moved** |
| artifacts with a `run_id` | 0 | 3 | all three writes attributed |
| output folders / PDFs | — | 3 / 3 | no empty husks |

**The third row is the whole point.** The unbackfillable population is exactly what it was, so `NULL`
still means one thing. Had any standalone write path leaked a NULL, that number would have grown.

Exit 0. Runtime dominated by a taxonomy re-extraction of all 19,262 postings, not by the new code.

---

## Session 5 — 2026-08-06 · the per-run funnel artifact (P0 item 1)

### Three consecutive live runs, `--no-scan`, against a copy of the production store

All three **reconciled**, exit 0. Runs 6, 7 and 8; run 6 resumed 8,462 postings left pending by a
*session-5* verification run that the foreground timeout had SIGKILLed, which is why its attribution
split differs from 7 and 8. (A different kill event from session 4's, which stranded a row after 11,200
evaluations — both are the same known gap: `try/finally` does not cover SIGKILL.)

The table transcribes the buckets that were non-zero or load-bearing; `dedup` (not instrumented) and
`shortlist → hidden_ineligible` (0 in all three) are omitted for width.

| stage | run 6 | run 7 | run 8 | note |
|---|---:|---:|---:|---|
| corpus entered (open postings) | 19,262 | 19,262 | 19,262 | the funnel's head |
| corpus → evaluated | 19,262 | 19,262 | 19,262 | `no_current_evaluation` 0 in all three |
| attribution → judged this run | 8,462 | 0 | 0 | run 6 finished the killed run's backlog |
| attribution → cache hit, prior run | 10,800 | 19,262 | 19,262 | |
| attribution → cache hit, unattributed | 0 | 0 | 0 | no NULL-run row is a CURRENT-identity evaluation |
| verdict → eligible | 18,174 | 18,174 | 18,174 | |
| verdict → ineligible | **0** | **0** | **0** | B7 again: still unreachable, P2 owns it |
| verdict → abstained (`uncertain`) | 1,088 | 1,088 | 1,088 | |
| shortlist → hidden non-SWE | 3,298 | 3,298 | 3,298 | title role gate |
| shortlist → shortlisted | 3 | 3 | 3 | `--top 3` |
| tailor → tailored | 3 | 3 | 3 | 0 failures |
| pdf → with PDF | 3 | 3 | 3 | read from `meta_json.typst_pdf_built` |
| applied → marked applied | 0 | 0 | 0 | `track` has still never been used |

**Unattributed evaluations: 20,637 in all three runs — unchanged.** That is D-019's invariant holding
across three more runs and 8,462 new attributed evaluations: the population can only shrink, so a
constant number means no write path leaked a NULL back in.

**Abstain, emitted every run as the artifact requires:** 44 rules · **7 never fired** · **17 fire and
never decide** · 16,674 requirement rows. Identical to session 3's standalone measurement, which is
the point — the artifact reports it per run without anyone running a CLI command.

### What the three runs do NOT establish

They ran `--no-scan`, so **the scan stage was never exercised**. Gate P0 wants three consecutive runs
of the real driver. These establish that the artifact is correct and that the corpus reconciles at
production scale; they are not the gate.

**Five of the seven instrumented stages are `derived`** and are therefore not evidence, by construction
(D-023): `attribution` and `verdict` are SQL partitions of the set they are compared against, `shortlist`
is rooted at the sum of the ranker's own outcomes, and `pdf` and `applied` carry remainder buckets. Their
balance holds for any input. The falsifiable reconciliations in these runs are **`corpus` and `tailor`**,
plus the two cross-checks.

### Gate

`make check` exit **0** — 2,719 passed (from 2,679), coverage **95.05%** (from 94.99%), plain mode,
real exit code. 40 new tests.

### Review yield

Ten defects across two independent reviews, on code that had already been written carefully:

| Review | Found | Of which logic |
|---|---:|---:|
| Code review (diff vs main) | 4 | 4 |
| Test-quality review (mutation, derived from docstrings) | 6 | 0 (all were unpinnable claims) |

**Every one of the six test findings was a test that PASSED while a mutation falsifying its own
docstring also passed.** Three of them passed only because of substring collisions inside the artifact's
own explanatory prose — the term searched for was in the report's commentary, not its data. The artifact documents itself in English, which makes bare `in body` assertions
almost useless — a term the report explains is a term the report contains.

---

## Session 6 — 2026-08-06 · P0 item 3, the per-source outcome table

### The gap item 3 closed, measured

`boardwatch run --no-scan --top 5` over a copy of the production store — **four consecutive runs, all
reconciled, all exit 0**, the last two on the post-review tree.

**Run-id warning.** This session used a FRESH copy of the store, so its run ids restart and collide with
session 5's: these are ids 5-8 of *this* copy and are **not** session 5's runs 6-8. Where a figure below
says "run 6" it means this session's. Ids are only unique within one store.

The `shortlist` stage before and after, on the same corpus:

Both rows are this session's corpus at `--top 5`; the first applies item 1's formula to it. (Session 5's
own measured `entered` was 3,301, at `--top 3` — a different run, not comparable row-for-row.)

| | entered | advanced | dropped | in no bucket | reconciled |
|---|---:|---:|---:|---:|---|
| item 1's formula, on this corpus | 3,303 | 5 | 3,298 | **15,959** | yes *(derived — could not fail)* |
| item 3 (this session) | **19,262** | 5 | 19,257 | **0** | **yes** *(falsifiable)* |

`entered` was the sum of the ranker's own outcomes, so it silently *excluded* everything the ranker never
reported. It is now the ranker's considered population, measured as its own row count.

**Where the 15,959 actually went** — the two buckets that did not exist before sum to exactly it
(11,517 + 4,442 = **15,959**); the other three were already reported:

| drop reason | count |
|---|---:|
| `hidden_hard_filter` (excluded title, or a rejected location) | **11,517** |
| `hidden_non_swe` (title role gate) | 3,298 |
| `capped_by_top_n` (cleared every filter, beaten only by rank) | **4,442** |
| `hidden_ineligible` | 0 |
| `skipped_not_new` | 0 |
| **total** | **19,257** = 19,262 − 5 |

`hidden_hard_filter` at **11,517 of 19,262 — 60% of the corpus — was entirely invisible before this
session.** It is the single largest drop anywhere in the funnel, larger than every other bucket combined,
and no metric reported it. It is a candidate for real scrutiny in P5, not necessarily a defect.

The artifact now lists **`corpus`, `shortlist`, `tailor`** as the stages whose balance could actually have
failed. It was `corpus`, `tailor` before.

### Full funnel, run 6

| stage | entered | advanced | dropped |
|---|---:|---:|---:|
| dedup | not instrumented | not instrumented | — |
| corpus | 19,262 | 19,262 | 0 |
| attribution | 19,262 | 19,262 | 0 |
| verdict | 19,262 | 18,174 | 1,088 |
| shortlist | 19,262 | 5 | 19,257 |
| tailor | 5 | 5 | 0 |
| pdf | 5 | 5 | 0 |
| applied | 5 | 0 | 5 |

`ineligible` **0**, unchanged — bar metric B7, P2's to fix. Reconciles: **yes**. Exit **0**.

### Per-source, by provider — the first time boardwatch's own funnel can say this

| provider | boards | open postings | eligible | **leads** |
|---|---:|---:|---:|---:|
| greenhouse | 63 | 11,648 | 11,098 | **5** |
| workday | 37 | 5,216 | 4,685 | **0** |
| ashby | 15 | 1,749 | 1,742 | **0** |
| lever | 3 | 649 | 649 | **0** |
| **total** | **118** | **19,262** | **18,174** | **5** |

**Workday: 37 boards, 5,216 open postings, 4,685 of them eligible, and zero leads.** Same for ashby and
lever. All five leads came from greenhouse — four from one board (`affirm`), one from `stripe`.

Two cautions before this is used as an argument. It is **one run at one `--top 5`**: with a cutoff that
tight, `leads` measures the top of the ranking, so a provider contributes nothing unless it holds one of
the five best-scoring postings. And job-apps' own rule is to judge sources by built attribution over **≥3
runs**. The rollup's sums are a **transcription check, not evidence**: boards total 118, `open` 19,262 and
`eligible` 18,174, matching the corpus and verdict stages — but per-board `open` and `eligible` are the
same partitions those stages count, so they agree for every possible database state. This is exactly the
agreement D-028 deleted a reconciliation for treating as proof; it confirms the numbers were transcribed
correctly here and nothing more.

`unique` and `assisted` report **not instrumented** for all 118 boards (D-026), never 0.

### Gate

`make check` exit **0** — **2,749 passed** (from 2,719), coverage **95%**, plain mode, real exit code.
30 new tests. Measured on the final tree, after every review fix.

*This figure was wrong twice before it was right* — 2,745, then 2,748 — each time because a later fix round
added tests after the line was written. It is the `STATE.md`-header failure mode D-017 names, reproduced in
`METRICS.md`: **do not write a test count until the last commit that can change it has landed.**

### Verification yield

| Check | Found | Of which logic |
|---|---:|---:|
| Mutation checks (7, D-025 procedure, cold cache) | 7/7 caught | — |
| Code review (diff vs main) | 3 | 3 |
| Re-review of the fix commit (D-021) | 4 | 2 |
| Docs-only review (docs + shipped prose as the brief) | 22 | 3 blockers, 9 major, 10 minor |

**The docs-only review out-yielded both code reviews combined, for the third session running.** Its three
blockers were all the same falsified claim surviving in places the code reviews had not been pointed at —
including a comment 90 lines below a docstring corrected in the same commit — plus `PROGRAM.md` citing
D-028 as authority for the reconciliation D-028 deletes. It also found that **`14,873`, cited in five
places including two code comments, was never a measured number**: it is `18,174 − 3,301`, a derived
estimate from a different run at a different `--top`. This change measured the real figure (15,959) and
then propagated the estimate anyway.

**The re-review of the fix commit earned its keep, which is D-021's whole point.** It found the falsified
join-path claim surviving in a **third** place — `count_by_source`'s own docstring, at the query site — and
one real defect a layer above the change: an abort reached `stage_errors` and so the `runs` row, but never
the summary the artifact reads, so **a crashed run's funnel reported `RECONCILES` with no FATAL line and an
empty Errors section.** That is D-021's defect, fixed for the ledger in session 4, still live for the
artifact until now.

**All three code-review findings were real, and two were self-inflicted in a specific way worth
recording:**

1. **The `eligible` per-source reconciliation could not fail** — it grouped the same subquery the verdict
   stage counts, by a NOT NULL foreign key, joined on a primary key. It was deleted. This is D-023's exact
   defect, **reintroduced one decision entry after D-023 was cited as the authority against it.** The live
   artifact rendered it as `| eligible | 18174 | 18174 | yes |` — a tick that could never have read
   anything else.
2. **Making `shortlist` non-derived made a second bug worse.** On runs where the ranker never executes (a
   fatal scan outage, a missing profile), the stage reported 0 in / 0 out. As `derived` that was harmless
   bookkeeping; as evidence it became an affirmative claim that the ranker ran and accounted for
   everything, and put `shortlist` in the artifact's list of stages that could have failed. Now `None`.
3. The section headline said *"boards with anything to report this run"* while the table is keyed off open
   postings, which are not run-scoped.

**A fourth defect was found by re-reading rather than by review, and it is the sharpest one:** correcting
D-028 and the CHANGELOG left the *same falsified claim* rendered into every artifact and stated in
`SourceTotal`'s docstring. Gate P0 requires the artifact to be answerable on its own, so a false
explanation inside it is worse than one in a doc. **Correcting a document is not correcting the program:
the prose that ships to the reader is a third place the claim lives.**
