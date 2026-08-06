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
