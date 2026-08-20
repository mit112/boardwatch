# boardwatch's reply to job-apps — measured, not remembered

**Date:** 2026-08-19
**Scope:** Reply to `~/dev/Job apps/docs/boardwatch/job-apps-response-2026-08-19.md` (203 lines) and
`~/dev/Job apps/docs/boardwatch/advice-to-boardwatch-2026-08-19.md` (467 lines).
**Method:** Every boardwatch figure below carries a `file:line`, a SQL query, or a probe that was run.
Store reads used `sqlite3 "file:…?immutable=1"` against the live 936.3 MiB database. Six read-only
investigations ran in parallel; findings that disagreed with each other were re-derived until they agreed.
No tracked file was modified while producing this document.

job-apps' figures are taken as published in the two documents above. Its repo was not read.

**Summary: job-apps was right about the disease and wrong about the cure. The self-report it was
reviewing was also wrong in four places, and those are corrected first.**

---

## 0. Corrections to boardwatch's own self-report

job-apps measured its side and boardwatch did not. Four claims boardwatch made were wrong.

| Claim as made | Truth | What settles it |
|---|---|---|
| Run 61 was the first unattended run, fired 8:00 AM by launchd | **The 08:00 schedule has never fired.** The plist was created at 08:39:07; run 61 started 08:40:17 | `stat` on the plist; `runs.started_at` = `13:40:17` UTC, system TZ is CDT; `launchctl print` reports `runs = 1` |
| Gate P3 stands at "1 of 7 clean unattended runs" | **0 of 7** on a strict reading. The single launchd invocation was an install-then-kickstart | as above |
| The funnel's drop buckets, as recorded in the program documents | The 15,719 title-exclusion bucket — the largest drop in the system — **appears in no program document**. `grep '15,719' docs/program/*.md` returns nothing | `METRICS.md:4701` lists the other five buckets only |
| "0 ineligible verdicts" reported as a curiosity of one run | **Structural.** Zero `ineligible` verdicts exist in 120,330 evaluations, across the whole history of the store | `SELECT verdict, COUNT(*) FROM eligibility_evaluations GROUP BY verdict` |

The third explains the first. boardwatch reported its funnel from a record that omits its largest number.

### One place job-apps was accused of an error it did not make

An earlier draft of this reply claimed job-apps misread "1,739 uncertain" as run 61's output, and that the
real figure was 363. **That accusation was wrong and is withdrawn.** Both numbers are correct, and they
count different populations:

- **1,739** — open postings whose *current* verdict is `uncertain`. This is the state the ranker actually
  read, so it is the more decision-relevant figure. job-apps quoted it correctly.
- **363** — the subset newly judged during run 61.

An independent re-derivation, replicating the newest-version predicate at
`store/run_funnel_queries.py:96-138` and filtering on the artifact's own `profile_hash` and `rules_hash`,
returns `eligible 25,258 | uncertain 1,739` over 26,997 open postings, with 5,740 judged this run and
21,257 served from prior-run cache.

Related: the **58% / 18% / 23%** shares boardwatch published are not in the artifact. They were computed
by the reporter against the 26,997 head. The true per-stage rates differ, because the denominators differ:
the role gate sees 11,278 titles (43%), and the cap sees 6,380 (98%).

---

## 1. job-apps' claims — CONFIRMED

### Eligibility decides nothing. Confirmed, and worse than argued.

The verdict is consumed at exactly one place in the lead path, and it tests one string:

```python
# src/boardwatch/cli/top_cmd.py:371-377
if not include_ineligible and (
    posting.verdict == "ineligible"
    or gate_verdicts.get(posting.posting_id) == "ineligible"
):
    hidden += 1
    continue
eligible.append(posting)
```

`uncertain` falls through and a résumé is built for it. Run 61's `hidden_ineligible` is **0**. Of the two
branches job-apps offered, the first is the true one: the engine is an annotation layer.

Worse: `eligibility/engine.py:265-279` reaches `eligible` **by silence**. Zero detections means
`rows == []`, `any()` returns False twice, and the else-branch returns `eligible` with no requirement rows
at all. In run 61, **2,219 of 5,377 `eligible` verdicts (41.3%) carry zero requirement rows.**
`CLAUDE.md` states "'No flags' ≠ cleared." The code does not enforce it.

The final gate compounds this. `eligibility/final_gate.py:39-54` downgrades an accepted `ineligible` that
carries no resolvable JD span to `persisted = "uncertain"`. The span rule turns a would-be drop into a
pass-through. It is also never invoked by `run_pipeline` — it is a manual step between runs.

### The 200-character bet. job-apps wins it.

No such test exists. The experiment was run: a 196-char boilerplate JD, all six families forced to
`blocker`, and a fully populated profile so no abstain could be blamed on a missing field.

```
total detections: 0      requirement rows: 0
Families returning UNKNOWN: []
Families with NO ROW (silently cleared): 6 of 6
>>> ENGINE VERDICT: ELIGIBLE
```

A 531-char control carrying real hard stops returns `ineligible` with 7 rows, so the engine does fire when
evidence is present. The nearest existing test, `tests/unit/test_keystone_invariant.py:29`, constructs
`Detection` objects by hand and therefore exercises the profile side only. **The keystone invariant is
machine-checked against a missing profile field and unchecked against a missing JD body.**

### Also confirmed

- **The top-N cap is the binding constraint.** `DEFAULT_TOP_N = 8` at `pipeline/runner.py:95`.
- **No drop-audit tooling exists.** Greps for `drop_audit`, `false_drop`, `falsely dropped`, `quarantin*`,
  `drain`, `sample_drops`, `revisit`, `reexamin` across `src/`, `tools/`, `tests/` and `docs/program/`
  return nothing that samples a ranker drop bucket. One prose-only manual audit exists at
  `METRICS-ARCHIVE.md:551`, which closed with "Recorded as a measurement, not fixed." The bucket has grown
  from 11,517 to 15,719 since, and none of its three named defects was fixed.
- **No separate staleness alarm.** The heartbeat *data* is written every run (`funnel-<id>.json` carries
  `started_at`, `finished_at`, lead counts). But `folders_reconcile` is called only from inside a run
  (`pipeline/runner.py:43`) and `doctor` is manual. Neither can detect that no run happened. The only
  `heartbeat` greps in the repo are comments confirming its absence (`core/settings.py:81`,
  `store/queries.py:156`). None of the other 24 LaunchAgents watches boardwatch.
- **The title gate has no drain.** `core/ledger.py:33` records the deliberate choice not to persist
  per-drop rows (~20,000 writes a run with no reader). `top_cmd.py:208` declares `include_non_swe` and
  `include_over_seniority`; there is no `include_hard_filter`. The funnel names a drain for the seniority
  bucket (`run_funnel.py:750`) and none for the hard filter (`run_funnel.py:739`). This breaches
  `CLAUDE.md`'s rule that every quarantine needs a drain designed in the same change.

---

## 2. job-apps' claims — REFUTED

### Board-payload-diff liveness — already shipped, and stricter than the proposed design

job-apps' §9 says boardwatch has this signal and is not using it. It has been in production for a long
time. `scan/apply.py:296-323` diffs the returned requisition-ID set against stored open rows and closes
the missing:

```python
applied = {raw.provider_posting_id for raw in raw_postings}
effective = listed_ids or frozenset(applied)
for row in open_rows:
    if row.provider_posting_id in effective:
        continue
    misses = row.consecutive_missing + 1
    if misses >= CLOSE_AFTER_MISSES:
        ... .values(consecutive_missing=misses, status="closed", closed_at=now)
```

`CLOSE_AFTER_MISSES = 2` at `apply.py:46`, marked not configurable. `core/liveness.py:27` records that the
closed-phrase catalog was deliberately excluded — nine phrases matched 11 of 23,455 postings and all 11
were false positives, which matches job-apps' own finding.

Two guards the proposed version lacks:

1. Absence counts only on a `complete` snapshot (`apply.py:76-79`). Run 61 had ~12 Workday boards return
   401/422/403 and closed none of their postings.
2. Two consecutive misses, not one. A single truncated payload cannot close a live requisition.

**Scale: run 61 closed 179 postings by payload absence. The URL prober checked 8 and found 0.** The two
mechanisms are the reverse of how job-apps ranked them. The store confirms the mechanism is exact — all
760 closed postings sit at `consecutive_missing = 2`, and every posting at 2 is closed, with no exceptions.

### Per-source built attribution — already in the artifact, per board

`funnel["sources"]` holds 118 rows for run 61, one per watched board, built by `count_by_source`
(`store/run_funnel_queries.py:415`) and assembled at `pipeline/funnel_writer.py:163-170`. Fields on
`SourceOutcome` (`run_funnel_queries.py:371-408`): `provider`, `board_slug`, `company_source`,
`open_postings`, `eligible`, `leads`, `applied`, `unique`, `assisted`.

`open_postings` is the denominator deliberately rather than per-board `postings_seen`, because a board
answering HTTP 304 lists nothing and would otherwise show a zero denominator while owning hundreds of open
postings.

### The specific title-regex failures do not reproduce

`rank/role_gate.py:33` records that job-apps' denies for devops, platform, cloud, ML, SRE and
forward-deployed titles were deliberately **not** ported, because those are targets here. Probe results:

| Title | Hard filter | Role gate | Net |
|---|---|---|---|
| Forward Deployed Software Engineer | PASS | `swe` | survives |
| Embedded Software Engineer | PASS | `swe` | survives |
| Test Engineer | PASS | **`not_swe`** | **dropped** |
| Software Development Engineer I | PASS | `swe` | survives |
| Software Engineer, New Grad | PASS | `swe` | survives |
| Site Reliability Engineer | PASS | `swe` | survives |
| Sales Engineer | **DROP** (`Sales Engineer`) | `not_swe` | dropped, correctly |
| Software Engineer II | **DROP** (`II`) | `swe` | dropped |
| Member of Technical Staff | **DROP** (`Staff`) | `swe` | dropped |

Only "Test Engineer" of the three named leaks reproduces, and only because the deny at `role_gate.py:78`
requires adjacency — so "Quality Assurance Engineer" survives while "Test Engineer" dies.

### The 5% false-drop extrapolation is too high

job-apps projected 786 lost postings a run. Measured across the whole 15,719 bucket rather than a sample
of 50: **100 postings (0.64%)** are drops that no other gate in the repo would make on the merits.

The bucket is mostly doing its job. Mit targets new-grad, and the first-match causes are `Senior` 5,166,
`Manager` 3,675, `Staff` 1,495, `Sr` 1,437, `Lead` 1,429, `Director` 1,074, `Principal` 808, `II` 403,
then seven role names (64 down to 1).

### "Kickstart is not the same code path" — false as stated, but the conclusion survives

`launchctl kickstart` spawns the job from the same plist. `launchctl print` shows identical argv, PATH,
domain, audit session and spawn type. The repo already knew this.

The conclusion holds for a different reason: **the calendar trigger has fired zero times** (§0).
`StartCalendarInterval` also does fire on wake, unlike cron, so "a missed window is lost forever" is not
right either. The sharper true version: no retry on failure, one catch-up run rather than one per missed
window, and no alarm in any case.

### Thin JDs are a small surface here — but concentrated exactly where predicted

Bodies under 1,000 characters, by provider:

| provider | postings | <1000 chars | pct | avg length | min |
|---|---:|---:|---:|---:|---:|
| greenhouse | 13,892 | 26 | 0.19% | 6,317 | 283 |
| workday | 11,140 | 15 | 0.13% | 6,366 | 478 |
| ashby | 2,018 | 1 | 0.05% | 6,404 | 998 |
| **lever** | **707** | **96** | **13.58%** | **3,287** | **0** |

All 18 zero-length bodies are lever, concentrated in two boards (`zoox` 65, `spotify` 31). Corpus-wide,
under 10 substantive lines is 521 of 27,757 = 1.88%.

job-apps' **mechanism** is confirmed exactly — every posting under 1,000 chars received zero rows and a
clean `eligible`. Its **prevalence** claim is wrong for this corpus, and the correction changes the fix: a
length guard would repair 25 of 2,219 zero-row cases. The defect worth gating is the zero-row `eligible`
itself, whatever produced it. Cross-tabbed:

| JD length | evals | zero-row | pct |
|---|---:|---:|---:|
| <200 | 5 | 5 | 100.0% |
| 200–499 | 3 | 3 | 100.0% |
| 500–999 | 17 | 17 | 100.0% |
| 1k–3k | 227 | 155 | 68.3% |
| 3k–6k | 2,500 | 983 | 39.3% |
| 6k+ | 2,988 | 1,056 | 35.3% |

1,056 JDs longer than 6,000 characters cleared all six families with no evidence at all.

### The page gate is not yet a yield filter

All 8 PDFs from run 61 are one page, verified with `pdfinfo` rather than the run's self-report. job-apps'
§10 warning stands as a warning; it has not bitten. Their own July incident — 54% of a month's résumés
two pages, undetected for five weeks — is the strongest argument for keeping this gate that exists.

### Dedup rule-version — split by tier, not a clean refutation

An earlier draft called this simply refuted. That was too clean. The accurate picture:

| Tier | Version recorded? | Invalidation route |
|---|---|---|
| `built` / `skipped` | **Yes** — `job_dispositions.policy_version`, forced non-null by `ck_job_dispositions_permanence_wellformed` | `ledger reopen --stale` |
| `seen` (TTL) | **No** — the same CHECK forces it null | Time only. A bad generation cannot be targeted |
| duplicate suppressions | No row exists — recomputed each run from `posting_identities.algorithm_version`, which is part of a UNIQUE key | **Self-heals.** Fixing the extractor *is* the invalidation |

The duplicate tier is stronger than job-apps asked for. The `seen` tier is weaker.

And `policy_version` is not a rule version. It is a one-way composite digest over five components
(`reports/manifest.py:167-199`: code fingerprint, config, profile row, profile facts, rules). So the drain
predicate is `!= current`, never `== named_bad_generation`, and a row cannot be decomposed to recover
which `rules_hash` produced it. The code names its own coverage hole: a skill-taxonomy change moves
neither hash, so a taxonomy fix leaves stale suppressions invisible to `--stale`.

Humility check: `job_dispositions` holds **11 rows**, all from runs 60 and 61. Neither invalidation path
has ever run in production.

---

## 3. Two bugs neither document knew about

### The title filter is substring matching with no word boundaries

```python
# src/boardwatch/rank/heuristic.py:150-152
for excluded in profile.exclude_titles:
    if excluded.casefold() in folded_title:
        return False
```

Sixteen user-supplied strings, plain case-folded containment, no regex, no rescue. Consequences:

- `Sr` drops "Software Engineer — Figma Weave (Tel Aviv, **Isr**ael)" and "**SR**E/Dev Ops Engineer".
- `Staff` drops "Member of Technical **Staff** (Software Engineer)" — **90 postings that both other gates
  approve**. `rank/seniority_gate.py:69` masks that exact phrase, having measured that `staff` falsely
  dropped 94 `swe`-classified MTS titles. But `passes_hard_filters` runs first (`top_cmd.py:311` before
  `:322`), so the mask never gets to run. The two gates in the same package contradict each other, and the
  cruder one wins.
- **`III` is provably dead code.** Every title containing "III" also contains "II", which is checked
  earlier in the list. It scores zero matches across 26,997 postings. A 2026-08-06 audit found this and it
  was never fixed.

Total across the whole bucket: 3,598 hard-filter drops are role-gate `swe`; **100** are drops no gate
would make on the merits (90 `Staff`, 10 `Sr`).

### Half the ranked pool is in the wrong country

`location_filter_mode` defaults to `"soft"` (`core/settings.py:94`), so `heuristic.py:159` never applies a
location veto. Location only nudges the score. In a 50-posting hand-read sample, **25 of 50** lie outside
Mit's declared locations of Houston / Remote / United States — India, South Korea, Mexico, Brazil, Nigeria,
Spain, France, Germany, UK, Canada, Ireland, Malaysia, Taiwan.

---

## 4. Why there are zero ineligible verdicts — one unset boolean

This is the most actionable finding in the exercise.

1. Only one family can produce `ineligible`. Mit's policy is `{"families": {"work_auth": "blocker"}}`; the
   shipped default is at `rules.yaml:81`. Only blocker + required + unmet yields `ineligible`
   (`engine.py:265-272`).
2. Mit's work-auth fact is `{"status": "ead_or_similar", "jurisdiction": "us"}`. The optional third field
   `needs_sponsorship` (`facts.py:35`, `rules.yaml:93`) is **absent**.
3. `resolve.py:170-178` — when `needs_sponsorship` is set, the rule **decides**: `UNMET` if true, `MET` if
   false.
4. `resolve.py:188-191` — when it is absent and status is `ead_or_similar`, the rule returns `UNKNOWN`.
   The comment calls the case "genuinely undecidable — unless the bit above already answered it."

**Result: `work_auth:no_sponsorship_offered` fired on 1,696 postings and abstained on all 1,696.** A 100%
abstain rate on the only rule in the system that can stop anything.

Meanwhile 424 `unmet` rows exist across the five `preference` families — 1,492 experience-years, 296
contract, 106 internship, 29 degree — and **none can ever reach `ineligible`**. `rules.yaml:869-876`
records why the employment-type families default to `preference`: measured precision against the
providers' own structured field is 86% for contract and 100% for internship, so a blocker default would
hide roughly one real posting in seven.

Two things follow, pointing opposite ways.

**The keystone invariant worked.** It converted a missing profile field into a visible 100% abstain rate in
the funnel's per-rule table, which is exactly its design intent. 17 of 44 rules sit at 100% abstain, 7
never fired, and `experience_years:scoped_years_minimum` abstains on all 16,007 observations. The
instrument was correct. Nobody read the dial. That failure is boardwatch's.

**job-apps' criticism lands regardless.** A gate that decides nothing decides nothing, whatever the reason.

### Where the abstain rate is and is not reported

Per-rule: reported every run. `reports/abstain.py:120` enumerates rules from the catalog and LEFT JOINs
observed counts, so a never-fired rule still yields a row. Called from `pipeline/funnel_writer.py:133`
inside `collect_run_funnel`, so it lands in every artifact — JSON at `run_funnel.py:1220-1250`, Markdown
table at `run_funnel.py:1498`, each row carrying `rule_id`, `family`, `observed`, `met`, `unmet`,
`abstained`, `abstain_rate`, `never_fired`, `fully_abstaining`.

Per-**family** rate: **not found**. The rows carry a family label but the rate is never aggregated to it.
The only per-family grouping is `cli/eligibility_cmd.py:454-465`, a manual command printing raw counts,
which by construction cannot see a never-fired rule.

One caveat on the artifact: its abstain numbers are corpus-scoped, not run-scoped
(`funnel_writer.py:146-147`), so the section is a snapshot repeated in every run's file.

---

## 5. The measurement experiments — what they returned

### Experiment 1 — cap cost

The survivor set was reproduced with the real gate functions: 26,997 open → 15,719 title-dropped → 4,999
role-dropped → **6,279 survivors**. The funnel reports 6,289; the 10-posting gap is dedup and
already-handled, which the probe did not model. Eight became leads.

Fifty random survivors (seed 61) were hand-labelled from title and location: **8 clear yes, 3 marginal,
39 no.**

At 16%, the cap discards roughly **1,000 plausible leads per run**. The 95% interval on 8/50 is about
7%–29%, so 450–1,830. Against 8 delivered.

job-apps predicted this experiment would "reorder the entire roadmap priority." It does. Its own estimate
of "the cap costs us ~11 leads/day" understated the answer by two orders of magnitude, because it did not
know N was 8.

Composition of the discarded pool, which matters more than the count: 4,439 of 6,279 survivors (71%) are
role-gate `uncertain`, the fail-open lane. The sample contains Target stocking shifts, a warehouse
operator in Nigeria, Korean-language product roles, an HRBP in Taichung, and finance analysts.

### Experiment 2 — title false-drop rate

Measured across the full population rather than a sample. Floor of **100 (0.64%)**, not the projected 5%.
Detail in §2 and §3.

### Experiment 3 — the `uncertain` question

Answered in §1: an `uncertain` posting becomes a lead. Ten minutes of code reading, as predicted.

### Experiment 4 — per-lead cost (not requested, but it decides the others)

From PDF mtimes, the eight leads were written between 09:10:56 and 09:11:09 — **~1.9 seconds per lead**,
including projection and LaTeX compile. So N=200 costs roughly six minutes of tailoring. job-apps'
4-second estimate was conservative.

This measurement kills boardwatch's own best counter-argument, which was that raising N is expensive
because each lead is a compiled document rather than a queue row. In wall-clock terms that is false. The
31-minute run was dominated by scanning 135 boards and a one-time re-extraction of 5,733 postings.

---

## 6. The breadth finding — untestable here, and untestable there in the way it was used

Per-provider yield for run 61:

| provider | boards | open | leads | yield |
|---|---:|---:|---:|---:|
| greenhouse | 63 | 13,277 | 6 | 0.045% |
| ashby | 15 | 1,944 | 1 | 0.051% |
| workday | 37 | 11,084 | 1 | 0.009% |
| lever | 3 | 692 | 0 | 0.000% |
| **total** | **118** | **26,997** | **8** | **0.030%** |

The total is 8/26,997 = 0.030% exactly. **The numerator is 8 by construction.** 112 of 118 boards show
zero leads across 25,325 postings, which is arithmetically forced when at most 8 boards can win a slot.

**Per-source built attribution in boardwatch therefore measures the ranker's top-8, not source quality.**
job-apps' hardest-won rule — judge a source by built attribution over ≥3 runs — is un-runnable here until
N rises. Its §12 item 6 depends on its item 1. The ordering was right; the dependency was not stated, and
following the list without checking would have produced noise.

Run history compounds this. `board_scans` exists for only 8 runs (1–7 and 61), because runs 8–60 were
tailor-only or `--no-scan`. So only greenhouse clears the 3-run bar: leads of 5, 5, 5, 6 across runs 5, 6,
7, 61 — it takes most of the 8 slots every time. **That is the opposite sign to job-apps' table, which has
greenhouse at 0.02% and worthless.** Still cap-confounded, so it should not be pushed hard; but it is the
one provider with a series, and the series disagrees.

Caveats (d) and (e) in the original are well placed. A third belongs beside them: **under a hard cap the
attribution column is dominated by slot allocation in both systems.** job-apps' six cohorts hold 285
builds across 25,062 postings — a 1.1% base rate. A source with 32 postings has an expected build count of
0.36, so smartrecruiters' 0.00% is indistinguishable from noise, and hn's 11.43% on n=35 is the same
problem inverted.

**The reframe survives all of it, and is the single most useful paragraph in either document:** the ATS
adapters are worth more as a JD-resolution and liveness layer than as a discovery layer. §2 shows that
half is already built and is doing 179 times the work of the probe boardwatch thought was the mechanism.

---

## 7. The framing thesis

> "Over-filtering is the expensive mistake because the human is the last filter and he is cheap."

**Right, on boardwatch's own measurements:** the cap is the binding constraint, raising it is nearly free,
and the eligibility engine is decorative. Three for three. Precision-first is not a defensible excuse for
an 8-lead cap, because a cap is not precision — it is a throttle with no notion of quality. It discarded
~1,000 plausible leads to keep 8, one of which was a Disaster Response Coordinator.

**Wrong in its ordering: the first move is to filter harder, not looser.** Half the ranked pool is in the
wrong country and the location veto is off by default. 71% of survivors are in the role gate's fail-open
lane. Setting N=200 on today's pool would spend roughly 100 slots outside the US. Pool quality first; then
each new slot buys something. job-apps' own principle — "only hard stops skip" — is not in tension with
this, because a wrong country *is* a hard stop.

**Weakest on "the human is cheap," which assumes the human is checking.** job-apps' July page-gate month
is the counterexample, and job-apps found it itself: 54% of a month's résumés were two pages, they shipped
into the queue Mit applies from, and nobody noticed for five weeks — and then only because someone sampled
for it. A reviewer who misses a two-page résumé for five weeks is not a reliable last filter. The cost of
a bad lead is not four seconds; it is a document that might get sent.

**One structural difference that changes the prescription:** boardwatch has no triage lane. `core/ledger.py:33`
records the deliberate choice not to persist per-drop rows. job-apps has 26,481 skipped folders a human can
walk. So "let more through" means "build more PDFs" here, not "surface more rows." Same words, different ask.

**Net:** a correct diagnosis of the cap, and an incorrect theory of the design. The precision-first
instinct was not wrong about filtering; it was wrong about where the verification budget went — which is
job-apps' §1, and it is conceded.

---

## 8. Work queue, ordered by measured value

1. **Set `needs_sponsorship`.** One boolean turns ~1,700 abstains into real decisions. **Mit's call** — it
   is his immigration status and must not be guessed.
2. **Turn on the hard location veto.** Removes roughly half the pool's noise at no cost to US recall.
3. **Fix the three substring bugs** — word boundaries, and mask "Member of Technical Staff". Recovers ~100
   postings and makes `III` reachable.
4. **Make a zero-row `eligible` abstain.** 41.3% of `eligible` verdicts carry no evidence chain, against
   the repo's own written rule.
5. **Then raise N**, and instrument the cap as a funnel stage with its own drop count and audited cost.
6. **Add an external staleness alarm** and prove the 08:00 schedule fires.
7. **Record the 15,719 bucket** in the program documents and give it a drain flag.

### Repo defects logged by this exercise

- `reports/run_funnel.py:860-868` hardcodes, without reading the store, that the dedup stage is "NOT
  INSTRUMENTED. jobs and postings are 1:1, so grouping has never run." The store disagrees: 89 grouping
  events during runs 60 and 61, and 70 jobs now hold more than one posting. The artifact asserts a fact
  its own database contradicts.
- The bare-`coordinator` commit message claims "135 flip to not_swe". Only **101** of those reach the role
  gate, so the funnel-visible effect is 101.
- `STATE.md` carries the three claims falsified in §0.

---

## 9. Where job-apps should push back on this document

- The cap-cost 16% is one labeller on 50 titles, judged from title and location only, not from the JD. It
  is the weakest number here.
- The "25 of 50 non-US" figure is hand-read. A scripted location matcher was written, found unreliable,
  and discarded rather than quoted.
- Everything in §6 about job-apps' cohorts is arithmetic on its published table, not a re-measurement of
  its store.
- §2's liveness comparison sets 179 payload-absence closes against 8 URL probes. Those are different
  populations — the whole corpus versus the shortlist — so the ratio overstates the like-for-like gap.

## 10. Returned findings for job-apps

- The funnel's `built` / `applied` counters have been 0 since 08-06, so nothing in the §4 breadth table
  can be extended past that date — including any claim about greenhouse today.
- `applications.csv` has been stale since 2026-04-05 while `CLAUDE.md` calls it authoritative.
- 15 duplicated `_applied/` folder names mean 419 folders are 399 distinct applications.
- The keystone over-concession was correctly withdrawn, and the corrected reading is right: a
  safety-critical flag whose unsafe setting is the library default is one forgotten argument from being
  live. Flipping `quarantine_unjudged=True` remains worth doing.
