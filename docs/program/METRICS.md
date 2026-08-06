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

One row per run once P0 lands. `—` = not emitted.

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

The metric that makes a rule which cannot fire visible. One column per run, one row per rule. Empty until
P0 lands. A rule at 100% abstain is a monitoring failure, not a conservatism feature.

| Rule | Declared fields | Baseline abstain | Latest |
|---|---|---|---|
| `work_auth` | `work_authorization.status` | **~77%** (measured under review 2026-08-06, not 100% as originally inferred) | — |
| _(remaining rules enumerated when P0 emits the catalog)_ | | | |

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

**Not yet answerable, and P0 item 1 owes it:** the funnel counts per run, per source, as an artifact. The run
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

All three **reconciled**, exit 0. Runs 6, 7 and 8; run 6 resumed 8,462 postings left pending by an
earlier run that `timeout` had SIGKILLed, which is why its attribution split differs from 7 and 8.

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

Two numbers here are also **not evidence**, by construction (D-023): the `attribution` and `verdict`
rows are SQL partitions of the set they are compared against, so their balance holds for any input.
The falsifiable reconciliations in these runs are `corpus` and `tailor`, plus the two cross-checks.

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
docstring also passed.** Three of them failed only on substring collisions inside the artifact's own
explanatory prose. The artifact documents itself in English, which makes bare `in body` assertions
almost useless — a term the report explains is a term the report contains.
