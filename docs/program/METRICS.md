# Metrics

One row per run, so gates are checkable over time rather than at a moment. Append; never rewrite history.
A metric that is not yet emitted is recorded as `—` (not emitted) rather than `0` — the distinction matters,
because "no fabrications found" and "fabrication check does not run" look identical in a zero.

---

## Index — spans both files

**Do not read either file end to end.** `STATE.md` carries the current standing; these are the underlying
numbers. Find the section you want, then read just its range:

```
sed -n '<start>,<end>p' docs/program/<file>
```

This file holds the **live** tables — the run log and the acceptance-run table, both still appended to —
and the P6-era session records. Everything closed (the baseline, the superseded abstain table, and every
session record from P0 through Gate P2) is in `METRICS-ARCHIVE.md`.

Line numbers drift as sections are appended. Confirm one before trusting it:

```
grep -n '^## ' docs/program/METRICS.md docs/program/METRICS-ARCHIVE.md
```

**After appending a section, add its index row and then run `make reindex`**, which rewrites both files'
line numbers from the headings themselves and is a no-op when they are already right. `make index-check`
reports drift without writing, and `make check` depends on it (D-109).

| File | Line | Section |
|---|---|---|
| METRICS-ARCHIVE.md | 14 | Baseline — 2026-08-06, before any program work |
| METRICS-ARCHIVE.md | 87 | Per-rule abstain rate |
| METRICS-ARCHIVE.md | 121 | Session 2 — 2026-08-06, P0 measurements |
| METRICS-ARCHIVE.md | 200 | Session 3 — 2026-08-06 · per-rule abstain rate, measured |
| METRICS-ARCHIVE.md | 252 | Session 4 — 2026-08-06 · the pipeline-run row (P0 items 0 and 7) |
| METRICS-ARCHIVE.md | 330 | Session 5 — 2026-08-06 · the per-run funnel artifact (P0 item 1) |
| METRICS-ARCHIVE.md | 399 | Session 6 — 2026-08-06 · P0 item 3, the per-source outcome table |
| METRICS-ARCHIVE.md | 551 | Session 7 (2026-08-06) — what `hidden_hard_filter` is actually dropping |
| METRICS-ARCHIVE.md | 601 | Session 7 — what a config hash can honestly cover (input to P0 item 4) |
| METRICS-ARCHIVE.md | 633 | Session 8 — 2026-08-06 · P0 items 4, 6, 8 (artifact v3) + the scan-run gate |
| METRICS-ARCHIVE.md | 683 | Session 9 — 2026-08-07 · P0 item 5, the reconciliation sweep (`boardwatch verify`) |
| METRICS-ARCHIVE.md | 709 | Session 9 — 2026-08-07 · P1a build, gate, and dogfood (résumé artifact integrity) |
| METRICS-ARCHIVE.md | 797 | Session 10 — 2026-08-07 · P1b gate, decisions (Tier-B token-provenance validator, D-033) |
| METRICS-ARCHIVE.md | 826 | Gate P3 window — 2026-08-07 (parallel session): NOT STARTED, blocked |
| METRICS-ARCHIVE.md | 845 | Résumé-render session (resumed) — 2026-08-07 · Increment-1 plan re-review (D-059) |
| METRICS-ARCHIVE.md | 863 | Résumé-render session (execution) — 2026-08-08 · Increment-1 build, D-060 |
| METRICS-ARCHIVE.md | 910 | Session 2026-08-08 — P4-craft + P5a (overnight autonomous run) |
| METRICS-ARCHIVE.md | 932 | Session 2026-08-08 — P5b B0 scaffolding (scorer + reference policy) + D-066 pivot |
| METRICS-ARCHIVE.md | 975 | Session — 2026-08-08 (P5b oracle judge shipped, D-068) |
| METRICS-ARCHIVE.md | 994 | Session — 2026-08-08 (P5 oracle run #1 — first Gate-P5 precision number) |
| METRICS-ARCHIVE.md | 1047 | Session — 2026-08-08 (P5 run #2 — disjunctive fix, Gate P5 MET at 100%; D-073) |
| METRICS-ARCHIVE.md | 1084 | Session — 2026-08-08 (D-071b final eligibility gate build — no answer-key number changes) |
| METRICS-ARCHIVE.md | 1120 | Gate P2 — 2026-08-08 · field-tier mechanism (P2 item 4, D-075). **MET AS RECONCILED** |
| METRICS.md | 67 | Run log |
| METRICS.md | 95 | Acceptance run |
| METRICS.md | 106 | Session — 2026-08-09/10 · P6 Slice 1 design + plan. **No build, no gate movement.** |
| METRICS.md | 132 | Session — 2026-08-10 · P6 Slice 1 BUILT (unattended run). Branch `p6-slice1`, not merged. |
| METRICS.md | 342 | 2026-08-10 — P6 Slice 1 on the LIVE store (first real backfill) + Gate P6 clause 4 |
| METRICS.md | 381 | Session 2026-08-10 (later) — P6 Slice 2: the durable decision ledger, its drain, and job regrouping |
| METRICS.md | 474 | Session — 2026-08-10 (later) · D-109, the program-index gate. No phase gate moved. |

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

## Acceptance run

Starts only after P6, on a frozen system. Any change to eligibility, profile, or the résumé gate resets the
clock; record the reset here with its cause.

| Day | Date | B1 leads | B2 PDF% | B3 QA% | B4 fab | B5 empty | B6 recon% | B7 decisive | Notes |
|---|---|---|---|---|---|---|---|---|---|
| _(not started)_ | | | | | | | | | |

---

## Session — 2026-08-09/10 · P6 Slice 1 design + plan. **No build, no gate movement.**

Nothing shipped. These are the live-corpus measurements taken while designing P6, recorded here
because they are the **pre-registered baseline** Gate P6's "duplicate leakage ≤ 5%" clause will be
judged against, and because two of them are the evidence for decisions in D-077.

Corpus: the live store, **23,455 open postings**.

| Measurement | Value | What it decided |
|---|---|---|
| Groups `content_hash` alone would collapse | **727** | Why `content_hash` may never suppress on its own (D-077) |
| Groups `exact_quad` collapses | **131** | The sole suppressing kind |
| Surplus rows `exact_quad` removes | **168** (0.72% of open postings) | The honest size of Slice 1's dedup effect |
| Open postings with **no** location evidence | **7** of 23,455 | Cost of emitting no location-bearing identity rather than a `"[]"` sentinel |

**Gate P6: not met, and not approached.** Slice 1 makes exactly one of its four clauses measurable
(duplicate leakage, via the funnel's `unique` counter). The other three — 0 dead postings reaching the
lead list, the injected hash-collision test, and the 20-suppression audit — belong to Slice 1's own
test set and Slices 2–3. Gate P6 is checked here when there is a 7-day window to check.

**Sampling note, so the 131 is not read as stronger than it is.** The sampled `exact_quad` groups are
same-role-different-requisition pairs with byte-identical descriptions — *not* verified re-postings of
one requisition. The defended claim is "one application decision", not "the same job".

---

## Session — 2026-08-10 · P6 Slice 1 BUILT (unattended run). Branch `p6-slice1`, not merged.

All nine plan tasks executed. `make check` result and the branch's standing are in `STATE.md`;
these are the measured numbers.

### `make check`

| Run | Covers | Result |
|---|---|---|
| after Task 4 (`bca78bd`) | Tasks 1-4 | **exit 0** — 3703 passed, coverage 95.19%, `generalization: OK`, 18m47s |
| first full-branch (`b1d2364`) | Tasks 5-8 | **exit 2 — RED.** `test_migrations_match_metadata` failed: the migration's UNIQUE-constraint name disagreed with the one `tables.py`'s naming convention renders. Real defect, fixed in `3646c27`. |
| re-run (`3646c27`) | whole branch | **exit 0** — 3733 passed, 1 deselected, coverage 95.20%, `generalization: OK`, 16m07s |

Both were run in a detached worktree pinned to the commit, capturing the real exit code, never
piped through `head`/`tail`. **The red run is recorded rather than overwritten**: it is the
session's best evidence that the gate catches what TDD did not — the migration applied cleanly, all
five schema tests passed, a 23,455-posting backfill ran and `identities verify` exited 0, and only
`make check` saw the drift.

### Live-corpus dedup, measured on an isolated COPY of the store

The live store was never written to. `boardwatch.db` was copied to `/tmp/bw-smoke-copy` and every
command below ran with `--data-dir` pointed at the copy (P1a's dogfood pattern).

| Measurement | Value |
|---|---|
| Open postings | **23,455** |
| Identity rows written by `identities backfill` | **117,254** |
| `identities verify` | **exit 0** — 23,455 postings verified |
| `identities_complete` | **True** |
| Groups `exact_quad` collapses | **147** |
| Surplus rows `exact_quad` removes | **186** (**0.79%** of open postings) |
| Kinds appearing in any suppression | `exact_quad` only |
| ~~Suppressions failing an INDEPENDENT four-field recheck~~ | ~~**0 of 186**~~ — **RETRACTED, see below** |
| A survivor that was itself suppressed | **none** |

### The figure moved from the pre-registered baseline, and why

The 2026-08-09 baseline (previous session, above) pre-registered **131 groups / 168 surplus /
0.72%**. The shipped implementation measures **147 / 186 / 0.79%** — *more* suppression. This was
investigated before the code was committed, because a dedup number moving the wrong way is exactly
what the smoke step exists to catch.

**Cause: the baseline grouped locations RAW; the shipped code normalizes them.** Re-running the
grouping over the same corpus with raw `locations_json` reproduces **136 groups / 174 surplus /
0.74%** — matching the design's own *unguarded* baseline of 135/173/0.74% to within one group.
Normalizing locations (sort + case-fold + whitespace-collapse, per design §2.1) merges a further
**11 groups / 12 rows**: pairs whose location lists differ only in order or spelling case. Measured
directly: **12 of the 186** suppressions have raw location lists that are not equal.

Not a cause: title normalization. **0 of 186** suppressions have a stored `normalized_title` that
disagrees with `normalize_title(title)`.

**What that check actually measures — corrected 2026-08-10.** `scan/apply.py:157` writes
`normalized_title` as `normalize_title(raw.title)`, i.e. the *same function* the comparison calls. So
this is a **staleness detector, not a normalization check**: it can only disagree when a row was
written by an older `normalize_title` than the one running now. Read as "no row here predates the
current normalizer", it is a real result; read as "normalization is correct", it is `X == X`.

An earlier version of this correction claimed the column is "a plain `casefold()`" and therefore
disagrees for every `+`/`#` title. That was wrong — `casefold()` appears in a *test helper*
(`tests/unit/test_identity_queries.py`), not in production. D-096's normalizer change does make
pre-change rows with `+`/`#` disagree until the next scan upsert rewrites them, which is exactly the
staleness this check is good for; it is not a permanent schema-level divergence.

**RETRACTED 2026-08-10 — this was not a second path.** The original claim read, in full:
*"**Precision is intact and was checked through a second path.** Every one of the 186 suppressions was
re-verified outside `_verify_quad`, comparing company_id, normalized title, normalized locations and
normalized body independently — **0 failures**. Sampled groups are same-role-different-requisition
pairs: identical titles, identical locations, distinct `provider_posting_id`."*

But `_verify_quad` **is** those four comparisons using those normalizers, so re-running them outside
the function agrees for every possible input. The "0 failures" was determined before the check ran.
Same defect D-028 deleted a per-board `eligible` total for, and the same class D-020 already recorded:
a check whose docstring claims a different path while computing `X == X`.

**"Precision is intact" is withdrawn as well, explicitly** — not merely narrowed to the arithmetic. It
was the broadest assertion in the original and it rested entirely on the empty check. Precision is
*separately* supported by the raw-field audit below, which can disagree and does (8 groups) — but
nothing supported it at the time it was written.

The paragraph is retracted, not deleted, because a read-first document must not quietly lose a claim
someone may have already acted on. Sampled groups genuinely are same-role-different-requisition
pairs — that observation stands on its own.

See "Precision re-derived independently (2026-08-10)" below for a check that can actually disagree.

### Count and precision re-derived independently (2026-08-10, post-review-fixes, `p6.2`)

*The count is re-derived first; the precision audit is the second table below. The heading originally
said only "Precision", over a table that re-derives a count — corrected, since STATE.md points readers
here for the precision audit specifically.*

Run on a copy of the copy (`scratchpad/auditdir`), so neither the live store nor the smoke copy was
touched. This replaces the retracted check above.

**What makes it a different path:** the grouping is done in **SQL** over the stored `identity_key`s
and never calls `resolve_duplicates`, `_verify_quad`, or any Python normalizer. It can therefore
disagree with the Python path — and the interesting result is where it does and does not.

| Measurement | Value |
|---|---|
| SQL-only grouping of open `exact_quad` rows at `p6.2` | **147 groups / 186 surplus rows** |
| Python `resolve_duplicates` on the same store | **186 surplus, 147 distinct survivors** |
| Kinds appearing in any suppression | `exact_quad` only |
| A survivor that was itself suppressed | **none** |
| `identities verify` | **exit 0** — 23,455 verified |
| `p6.1` rows still present beside `p6.2` | **117,254 each** |

The equal `p6.1`/`p6.2` row counts carry a second fact worth stating, since this is the only place it
is measured: the `[null]`-locations loader fix drops the three location-bearing kinds for an affected
posting, so a single `locations_json = [null]` row would cost 3 identities at `p6.2` and the totals
could not stay equal — no `p6.2` change adds rows to compensate. So identical totals also mean **zero**
open postings have `locations_json = [null]` in this corpus, on the premise (true here) that the `p6.1`
rows were written by the pre-fix loader. The fix guards a shape the corpus does not currently contain;
it is not a correction to these numbers.

### `make check` — fix session

| Run | Result |
|---|---|
| `f2f2430`, detached worktree | **exit 0** — `generalization: OK`, ruff clean, `mypy --strict` clean, 3749 passed / 1 deselected, 95.22%, **4m17s** |
| first post-fix run (`ae83743`) | **exit 2 — RED**, 2 failed: the pinned C++/C caveat (D-096) and the version-bump test's hard-coded `"p6.2"` |

The 4m17s is not a smaller gate than the overnight 16m07s — it ran *more* tests (3749 vs 3733). Warm
venv and filesystem cache is the likely cause; that is inferred, not measured.

**The two paths agree at 186 — and that agreement is itself the finding.** SQL surplus equals the
resolver's surplus, which means `_verify_quad` rejected **zero** members across the entire corpus.
The string-verify did not fire once on this corpus (it does reject in
`tests/unit/test_dedup_resolver.py`, where a divergent body is forged, so this is a property of the
data, not of the function). It is not broken; it is redundant with the key on this data,
because it re-runs the same normalizers the key was built from. So it defends against a SHA-256
collision and against staleness, but **not** against the normalizers being lossy — which is exactly
how the C++/C# title collision got in. Recorded so nobody cites "string-verified" as evidence of
precision it cannot supply.

**Precision checked where the key cannot help — raw-field disagreement inside a group.** Exactly two
comparisons qualify, because the `exact_quad` key hashes *normalized* title and *normalized* locations
but takes `company_id` and `content_hash` **raw**:

| | |
|---|---|
| Groups whose members differ in RAW `title` | **8 of 147** |
| Groups whose members differ in RAW `locations_json` | **11 of 147** |

A first draft of this table also reported "groups differing in `content_hash`: 0" and "in `company_id`:
0". **Both were deleted, not downgraded** (D-028's precedent), because sharing one `identity_key`
*entails* sharing both — they hold for every possible database state, modulo a SHA-256 collision. Two
tautologies in the paragraph written to replace a retracted tautology, under a heading that says
"where the key cannot help". Caught by the docs review, and recorded because the near-miss is the
point: the reflex to pad a verification table with rows that cannot fail survived the retraction that
was supposed to cure it.

All 8 raw-title disagreements were read by eye and every one is punctuation, spacing or case noise on
the same role. The five distinct shapes, all five of which are pinned by
`test_punctuation_noise_still_collapses`: `Mobile Expert - Bilingual…` vs `Mobile Expert, Bilingual…`;
`Store-in-Store, Retail Sales` vs `Store in Store - Retail Sales`; `Javascript` vs `JavaScript`;
`IC design Engineer` vs `IC Design Engineer`; `Manager, Clinical Study Lead` vs `Manager Clinical Study
Lead`. **Zero are semantic collisions.** That measurement is what killed the first proposed fix for the C++/C# hole (adding a raw
case-folded title comparison to `_verify_quad`): it would have broken 6 of those 8 real suppressions
to defend a collision this corpus does not contain. The shipped fix folds `+` and `#` to words in
`normalize_title` instead — 123 open titles contain `+`, 16 contain `#`, **none of them is in any
suppression group**, so the figure is unchanged at 147/186 and no recall was traded away.

### Cost the fifth sweep adds to every run — measured, and worth a reviewer's eye

`count_by_source`'s new survivor sweep loads **every open posting's `body_text`** (it must: the
`unique` denominator is corpus-wide, so unlike the ranker it cannot bound the load to a shortlist).
Measured on the copy:

| | |
|---|---|
| `count_by_source` over 23,455 open postings | **9.4 s**, peak RSS **471 MB** |
| `identities backfill` (117,254 rows, cold) | **41 s** |

9 s on a run that already takes minutes is not a concern; the **471 MB peak** is the number to
watch, and it scales with corpus size.

Flagged rather than tuned, and the distinction matters — **corrected 2026-08-10**, because the
sentence that stood here contradicted the section above. SQL grouping over stored `identity_key`s is
legitimate **as an out-of-band re-derivation of the count** (that is exactly the independent path used
above, and it is independent precisely because it shares no code with the resolver). What it may not
do is **replace the resolver in the production read path**: it would drop the guard against a stale
stored identity, which is a live condition (D-098). The earlier text conflated the two and called the
first one a D-028 tautology — it is not; D-028 was about grouping *the same already-counted set* a
second way and calling it verification.

The earlier text also said the verify is what "makes suppression safe". Deleted: `_verify_quad`
rejected zero members corpus-wide (D-097), and it re-runs the key's own normalizers, so it cannot be
cited as the thing that makes suppression safe.

### `assisted`

**Not instrumented — reports `None`, not 0.** `exact_quad` is keyed on `company_id` and sources *are*
`company_id`, so no suppression this slice can produce crosses a source boundary; there is no
mechanism that could count one. Reporting `0` would assert a measurement that was never taken
(D-088, and the D-022/D-023 rule). It becomes measurable when an aggregator posting can be
dereferenced to exact requisition evidence.

### NOT measured — so Gate P6 cannot be read as met

**Gate P6 is NOT met.** Slice 1 makes exactly one of its four clauses measurable. Still unmeasured:

- **7-day duplicate leakage** — needs a 7-day window of real runs. Operational, Mit-side.
- **Dead postings reaching the lead list** — liveness is Slice 3; nothing here measures it.
- **The 20-sample suppression audit** — needs a human to re-derive 20 suppressions from the data.

The build made these measurable; it did not meet them.

## 2026-08-10 — P6 Slice 1 on the LIVE store (first real backfill) + Gate P6 clause 4

Merged Slice 1, then migrated and backfilled the **live** store (`~/Library/Application
Support/boardwatch`). Backed up to `boardwatch.db.pre-p6-backup-20260810` first; the WAL was 0 bytes,
so the copy is complete. `cli/context.py` calls `ensure_schema` on every command, so the migration
applied as part of the backfill — one pending revision, an additive `CREATE TABLE`.

| Measurement | Value |
|---|---|
| Schema head after | `p6_posting_identities` |
| Algorithm versions present | `p6.2` only (the live store never held `p6.1`) |
| Open postings | **23,455** |
| Identity rows written | **117,254** |
| `identities backfill` wall time | **12.4 s** |
| `identities verify` | **exit 0** — 23,455 verified |
| Groups `exact_quad` collapses (SQL, independent of the resolver) | **147** |
| Surplus rows removed | **186** (**0.79%**) |

**The live figures reproduce the copy's exactly** (147/186/0.79%), which is the outcome the isolated-copy
methodology was for: the copy was a faithful stand-in, and the numbers were not an artifact of it.

### Gate P6 clause 4 — 20-sample suppression audit: **MET, 20/20 genuine**

Sampled deterministically (every 7th group ordered by `identity_key`, first 20 — reproducible, not
random) and read by eye. **All 20 groups are same-company, same-title, same-location, distinct
`provider_posting_id`** — same-role-different-requisition, which is precisely what `exact_quad` targets.
**Zero false positives.** Spread across 13 employers and both software and non-software roles (Cisco,
Broadcom ×3, Capital One ×4, Verizon ×2, T-Mobile, Twilio, Duolingo, Target, Workday, Citi, Chewy, GE
HealthCare, UT Austin), so the result is not an artifact of one board's ID scheme.

**One group is worth recording on its own.** Duolingo `6469`/`6470`, "Software Engineer II, Android",
differ **only** in location list order — `["Pittsburgh, PA", "New York, NY"]` against
`["New York, NY", "Pittsburgh, PA"]`. Nothing but the sort in `normalized_locations` catches that pair;
under raw grouping they are two distinct postings. This is the empirical justification for design §2.1's
sort + case-fold, and it is the mechanism behind the shipped 186 exceeding the raw-grouped 174 — the
delta is real duplicates, not over-suppression.

---

## Session 2026-08-10 (later) — P6 Slice 2: the durable decision ledger, its drain, and job regrouping

### The gate

| Measurement | Value |
|---|---|
| `make check` | **exit 0** |
| Tests | **3822 passed**, 1 deselected |
| `generalization` | OK · ruff clean · `mypy --strict` clean (190 files) |
| Wall time | **4m42s**, detached worktree pinned to `8a70f36` |
| Schema head after | `p6_job_dispositions` |

A first gate run at `6086e07` came back **exit 2 — 4 failed, 3811 passed**, and was right. All four were one
class: a caller that ranks twice against the same corpus, now getting a second answer that hides what the
first surfaced, because the ranker records `seen`. See D-103 for the ruling and the fix.

### The premise, measured on the live store BEFORE the slice

The ledger exists because nothing suppressed an already-built lead, so the top-N never advanced.

| Measurement | Value |
|---|---|
| Postings ever tailored | 18 |
| Tailored in **more than one** run | **6** |
| Postings tailored in **four** runs each | **5** — 2011, 2012, 10947, 15498, 15499 (runs 5, 6, 7, 9) |

**Caveat, stated so the figure is not oversold:** runs 5–7 and 9 were the Gate-P0 repeat-run evidence over
one frozen store on one day, not four steady-state days. The *mechanism* is measured; the daily frequency is
inferred.

### The decision unit, measured

| Measurement | Value |
|---|---|
| `postings` | 24,073 |
| `jobs` | 24,073 |
| `count(distinct postings.job_id)` | 24,073 |
| `postings.job_id IS NULL` | **0** |
| `applications` | **0 rows** |
| `job_grouping_events` before | **0** |
| `artifacts` with a non-NULL `job_id` | **0** of 44 |

So `job_id` was exactly an alias for `posting_id`, and no tracking key could be stranded by regrouping today
— which is what makes the refusal guard latent rather than unreachable (D-104).

### Host classes over the live corpus — why `cross_host` dereference has no population

| Class | Open postings |
|---|---|
| `ats` | **15,217** |
| `unknown` | **8,238** |
| `aggregator` | **0** |

There is no aggregator posting to dereference. D-082's re-entry path is unchanged; its trigger is P7.

### Regrouping verified on an isolated COPY of the live store — the live store was never written to

| Measurement | Value |
|---|---|
| `identities regroup --dry-run` | **186** merges over **147** groups, **0** refused |
| `identities regroup` (apply) | **186** moved, 0 refused, 0.9 s |
| Second pass (idempotence) | **0** moved |
| Jobs anchoring 2+ open postings, by SQL | **147** |
| Surplus open postings, by SQL | **186** |
| `job_grouping_events` rows | **186** |
| Distinct postings moved | **186** |
| Events where `from_job_id == to_job_id` | **0** |
| `count(distinct postings.job_id)` | 24,073 → **23,887** (−186 exactly) |

The 147/186 matches D-081/D-101's independently measured groups and surplus rows. The SQL path groups the
**projection** (`postings.job_id`) while the planner worked from `posting_identities` + `resolve_duplicates`,
so they are different paths.

**What this agreement does and does not show.** The group count matching an independently measured figure,
and the exact −186 with zero self-merges, is real evidence that no merge collapsed two groups or moved a
posting twice. It is **not** evidence that the right postings were grouped — that rests on D-101's by-eye
audit of 20 sampled suppressions, and this slice adds no new precision evidence.

### Mutation check on the headline claim

Disabling the ranker's ledger check turned **4 of the 6** tests in
`tests/pipeline/test_ledger_advances_the_queue.py` red, including
`test_a_second_run_builds_a_DISJOINT_set_of_leads`. The two that survived are a pure unit test of the
zero-output guard and the filesystem cross-check, whose claims do not depend on suppression.

### Disk

The pre-migration backup `boardwatch.db.pre-p6-backup-20260810` (769 MB) is still in place. Root filesystem
is at **39%** with 18 GiB free, so the disk pressure that made deleting it worth considering has resolved
and it was left alone.

---

## Session — 2026-08-10 (later) · D-109, the program-index gate. No phase gate moved.

No pipeline run, so no funnel numbers and no Gate P6 movement. Recorded because the numbers below are the
evidence for D-109 and are otherwise unverifiable after the fact.

| Measure | Value |
|---|---|
| `make check` at `6064119` (tool + first docs commit) | **exit 0**, in a detached worktree pinned to the commit |
| `make check` at HEAD | **not run** — two later commits are ungated |
| `make index-check`, warm | 0.05 s (0.20 s cold) |
| `make generalization && make index-check` | 1.26 s |
| Index rows shifted by appending D-109's own row | 32 of 33 DECISIONS rows (the 33rd was the new row itself); 0 METRICS rows |
| `tests/unit/test_program_index.py` | 15 tests |

**Mutation results — 8 mutations, 8 caught.** Each derived from a test's stated claim, not from the code.
Committed before mutating and `__pycache__` cleared each time (both have faked a CAUGHT here before).

| Mutation | Tests red |
|---|---|
| Never notice a wrong index number | 4 |
| Drop the rule that the index's own heading owes no index row | 3 (incl. the real-docs test) |
| Never report a heading that has no index row | 2 |
| Perturb a real row to `D-103 \| 970` in `DECISIONS.md` | 1 real-docs test; `index-check` exit 1; `make reindex` restored a byte-identical file |
| Read fenced code blocks again | 1 |
| Anchor the index to the last row-shaped line anywhere | 1 |
| Duplicate heading keeps first-wins | 1 |
| Print "index is current" despite reported problems | 1 |
| *(both fence defences removed at once — proves the row-in-a-fence test is not vacuous)* | 3 |

**Review yield.** One code reviewer, one docs-only reviewer, both fresh-context. Code: 5 defects, all real,
all fixed. Docs: 4 MAJOR + 5 MINOR, of which the load-bearing one was that D-109's argument rested on a
docs-only `make check` exemption that **D-014 explicitly denies** — see D-109. The docs reviewer also found
three files enumerating `make check`'s contents that had gone stale (`CONTRIBUTING.md`, `AGENTS.md`,
`.github/PULL_REQUEST_TEMPLATE.md`), which is the fourth time a claim in this repo has needed fixing in more
places than the change that invalidated it touched.
