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

| Date | Run id | Observed | Unique | Candidates | Eligible | Ineligible | Abstained | Leads | PDFs | QA pass | Stub rate | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| _(none yet — P0 not started)_ | | | | | | | | | | | | |

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
