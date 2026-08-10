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
| METRICS.md | 71 | Run log |
| METRICS.md | 99 | Acceptance run |
| METRICS.md | 110 | Session — 2026-08-09/10 · P6 Slice 1 design + plan. **No build, no gate movement.** |
| METRICS.md | 136 | Session — 2026-08-10 · P6 Slice 1 BUILT (unattended run). Branch `p6-slice1`, not merged. |
| METRICS.md | 346 | 2026-08-10 — P6 Slice 1 on the LIVE store (first real backfill) + Gate P6 clause 4 |
| METRICS.md | 385 | Session 2026-08-10 (later) — P6 Slice 2: the durable decision ledger, its drain, and job regrouping |
| METRICS.md | 478 | Session — 2026-08-10 (later) · D-109, the program-index gate. No phase gate moved. |
| METRICS.md | 519 | Session — 2026-08-10 (later still) · The P6 Slice 2 review (D-110). No phase gate moved. |
| METRICS.md | 609 | Session — 2026-08-10 (later still ×2) · P6 Slice 3, items 5 and 6 (D-111). Gate P6 unchanged: still 2 of 4. |
| METRICS.md | 722 | Session — 2026-08-10 (later still ×3) · 0.3.0 cut and tagged (D-112). No phase gate moved. |
| METRICS.md | 773 | Session — 2026-08-10 (later still ×4) · The Slice 3 external review (D-113) + the CI dependency fix (D-114). No phase gate moved. |

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
| Schema head after | `p6_job_dispositions` — **in the REPO.** The live store is still at `p6_posting_identities` and has no `job_dispositions` table; the live figures elsewhere in this section are Slice 1's |

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
| `make check` at `d6291ba` (after the review fixes) | **exit 0** — 3837 passed, 1 deselected, coverage 95.08%, 4m49s |
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
docs-only `make check` exemption the repo does not actually grant. Stated precisely, because D-109 itself
declines to resolve it: D-014 is about program docs being subject to the generalization checker, and reading
it as "no docs-only exemption" is D-109's inference, not D-014's stated choice. **The repo contradicts itself
here and neither entry resolves it** — that is Mit's call, still open. The docs reviewer also found
three files enumerating `make check`'s contents that had gone stale (`CONTRIBUTING.md`, `AGENTS.md`,
`.github/PULL_REQUEST_TEMPLATE.md`), which is the fourth time a claim in this repo has needed fixing in more
places than the change that invalidated it touched.

---

## Session — 2026-08-10 (later still) · The P6 Slice 2 review (D-110). No phase gate moved.

**Gates run.** Three full `make check` runs, each in a detached worktree pinned to its commit.

| Commit | What it covered | Result |
|---|---|---|
| `b4d18b4` | baseline before any fix — the reviewed tree as built | **exit 0** · 3837 passed, 1 deselected, coverage 95.08%, 5m04s |
| `769ceb8` | the code fixes | **exit 0** · 3845 passed, 1 deselected, coverage 95.06%, 4m47s |
| final | code fixes + docs + the three reconciled tests | recorded below |

The `769ceb8` run is +8 tests on the baseline and −0.02pp coverage; the new tests are 3 regroup/ledger store
cases, 3 parametrised refusal-classification cases and 2 caller cases.

**One gate failure worth recording, because it was self-inflicted.** The first attempt at the final gate
exited **2** on `generalization: 2 violation(s)` — a home-directory absolute path in
`docs/superpowers/specs/…-design-review.md`. Those files were pre-existing **untracked** working material from
the previous session, and a `git add -A` in this session committed them. Untracked and gitignored are not the
same thing, and `add -A` does not know the difference. Fixed by `git rm --cached` + amend; the files are back
to untracked and still on disk. **The generalization checker caught working material entering the repo, which
is exactly its job** — worth noting as the check earning its keep rather than as noise.

**Review yield — four reviewers, all fresh-context, dispatched concurrently.**

| Reviewer | Raised | Real | Wrong / rejected |
|---|---|---|---|
| diff (whole code range) | 7 | 7 | 0 — but its "regrouping is unreachable" reasoning was half wrong (see below) |
| ranker-callers tracer | 5 + 4 test findings | all | 0 |
| schema / hot-path auditor | 6 | 6 | 0 BLOCKER/MAJOR found; its value was 3 **corrections to claims** |
| docs-only | 5 MAJOR + 11 MINOR | all | 0 |

**Two BLOCKERs and five MAJORs were real.** The two BLOCKERs — `eligibility gate request` consuming the
shortlist it judges, and a transient `tectonic` failure earning a permanent `skipped` — were each found
independently by two reviewers. The `bwd` breakage (zero folders built per day, for seven days) came only from
the callers tracer, which was the reviewer given the narrowest brief.

**Measured, not asserted.**

- The permanence CHECK: **12/12** shapes agree with intent on **both** an Alembic-migrated and a
  `create_all` database, by raw `sqlite3` INSERT, with rejections attributed by constraint name. The rendered
  `CREATE TABLE` text is character-identical for all three CHECKs. **And D-103's stated reason for that form
  was wrong** — a truth table against a real naive-CHECK table shows the shape it names is *rejected*
  (`0 = 1`), while what the naive form admits is `(seen, NULL, NULL)`, a `seen` row that never expires and
  that `stale_dispositions` cannot list. See D-110.
- The identity write in the scan hot path, N=3000 (Workday's own `_MAX_PAGES 150 × _PAGE_LIMIT 20`), 4.2 KB
  bodies, statements counted with a `before_cursor_execute` hook:

  | path | wall | queries | Δ |
  |---|---|---|---|
  | INSERT, identity OFF | 1.717 s | 15,002 (5.00/posting) | — |
  | INSERT, identity ON | 2.204 s | 21,002 (7.00/posting) | **+0.487 s (+28.4%), +2.00 q/posting** |
  | REVISE, identity OFF | 1.401 s | 12,002 (4.00/posting) | — |
  | REVISE, identity ON | 3.441 s | 21,002 (7.00/posting) | **+2.039 s (+145.5%), +3.00 q/posting** |

  `EXPLAIN QUERY PLAN` confirms the per-posting read is an index SEARCH on
  `UNIQUE(posting_id, kind, algorithm_version)`, so the cost is O(postings this board listed × log corpus) and
  does **not** scale with the corpus. D-105's cost claim holds. +2 s on the worst board against a
  network-bound scan is not material.
- Failure modes executed against the scan path: empty/whitespace/symbol-only title, empty body, `[]` and
  `["", "  "]` locations, 500 locations, a 2 MB body, emoji/RTL/NFD unicode — **all OK**. Lone surrogates
  raise `UnicodeEncodeError` but did so **before** this change too (verified by monkeypatching the identity
  write to a no-op), so nothing newly reachable.
- The regroup refusal guard, six scenarios in a migrated store: control merges; non-survivor tracked refuses
  `tracked_job` with **0** events written and both anchors unchanged; survivor tracked refuses nothing;
  non-survivor artifact refuses; artifact with NULL `job_id` does not protect; missing anchor refuses
  `missing_job_anchor`. All four D-104 claims verified.
- The two defects this session found itself were **reproduced in isolated stores before and after the fix**:
  a `built` decision orphaned on a job nothing anchors, and a trail event written for an `UPDATE` that matched
  0 rows.

**Mutation checks.** Ignoring the fatal in the `seen` gate → the fatal test goes red. Restoring `gate
request`'s consume → its test goes red. Recording `skipped` for every `LeadArtifactError` → 2 of the 3
parametrised refusal cases go red. **A `git checkout` during that work discarded four uncommitted `runner.py`
fixes** — the trap already on record — and they were re-applied. Commit before mutating.

**Corrections to previously-recorded numbers**, all verified against the repo: D-108's index read-back was
**108/108**, not 107/107 (the paragraph whose point is that an unchecked generated number is what bites this
repo); the post-split `DECISIONS.md` was **1,235** lines, not 1,175 (`DECISIONS.md`) or 1,234 (`CHANGELOG.md`);
the pre-rewrite `STATE.md` was **1,386** lines, not 1,387; D-103's blast radius was four tests in **three**
modules, not four; `record_artifact` has **three** call sites in `src/`, not two. The archive split itself
re-verified clean and independently: entry bodies 322,260 bytes / SHA-1 `472dec65…`, METRICS 96,063 bytes /
SHA-1 `adcca125…`, identical D-number sets, nothing lost or duplicated.

**Both external second opinions produced nothing.** GPT-5.x via the Codex runtime returned no content
(zero assistant messages in the session transcript), and DeepSeek `deepseek-v4-flash` consumed its entire
`max_tokens` as `reasoning_tokens` twice — 8,000 then 32,000 — emitting an empty `content` both times.
Recorded so the next session does not spend the same time on them; per Mit, hand him a review prompt to run
manually instead.

---

## Session — 2026-08-10 (later still ×2) · P6 Slice 3, items 5 and 6 (D-111). Gate P6 unchanged: still 2 of 4.

**Gate.** `make check` in a detached worktree pinned to a commit, three times.

| Run | Commit | Exit | Passed | Coverage |
|---|---|---|---|---|
| Baseline, before any edit | `5f0150d` | **0** | 3,845 | 95.06% |
| Build complete, pre-review | slice head | **0** | 3,890 | 95.03% |
| After the review's fixes | `1ab3a48` | **0** | **3,908** | **95.07%** |

The baseline matters: main was green first, so anything red afterwards was this session's.
**+63 tests over the session**, 45 from the build and 18 from the review's fixes.

### Applied-state suppression (item 5) — the population, measured read-only

| Table | Rows | Consequence |
|---|---|---|
| `applications` | **0** | No live population. The tests are the evidence for this item, not a run |
| `application_events` | **0** | `track` has never been used, on any store |

Suppressing set = `APPLIED_STATUSES` = `applied`, `interviewing`, `offer`, `rejected`. `interested` and
`withdrawn` deliberately outside it; `withdrawn` is the drain.

### Liveness (item 6) — every number below is re-derivable from the live store read-only

| Measure | Value | What it means |
|---|---|---|
| `postings` open / closed | **23,455** / 618 | |
| Open postings stale > 30 d | **0** | And > 7 d is also **0** — but see the caveat below; this is weaker evidence than it looks |
| Oldest open `last_seen_at` | **6.1 days** | `min(last_seen_at)` on an open row is `2026-08-04 06:47`, measured at ~10:13 on 08-10. An earlier draft said "5 days" — it floored against midnight rather than the measurement time |
| Open at `consecutive_missing = 1` | **216** | The real population for this check: seen, then absent once |
| Open postings with a NULL/blank URL | **0** | The nullable-URL path is latent, not unreachable |
| Open postings with an empty body | 17 | |

**The closed-phrase catalog, measured and rejected.** Nine candidate phrases against `body_text` of open
postings:

| Phrase | Matches | Genuine |
|---|---|---|
| `no longer available` | 2 | **0** — Workday boilerplate: *"If the job posting is no longer available then all roles have been filled"* |
| `requisition … closed` | 8 | **0** — eight JDs for roles that process purchase requisitions |
| `not accepting applications` | 1 | **0** — *"not accepting applications of candidates outside of New York"*, a location restriction |
| `no longer accepting` · `has been filled` · `position is closed` · `applications are closed` · `has expired` · `no longer open` | 0 each | — |
| **Total** | **11 of 23,455** | **0** |

**Caveat on the staleness figure, added by the docs review.** "0 open postings stale beyond 7 days" is
*not* direct evidence that `CLOSE_AFTER_MISSES = 2` fires. Corpus-wide `max(last_seen_at)` is
`2026-08-07 04:17` and the open range is `08-04 … 08-07`, so maximum observable staleness is bounded at
~6 days by **scan recency alone**. The actual evidence the rule fires is the **618 `closed` rows**. The
conclusion — staleness is not the leak, so Slice 3 should not re-implement it — is unchanged.

Precision **0/11**. A high-precision catalog matches **0** rows. This supersedes the earlier
"3 open postings contain a closed phrase" figure, which was recorded without its catalog — and the number
that mattered was never its size but its precision. Structural reason in D-111: every provider builds
`body_text` from the payload's description field alone, so page chrome cannot reach that column.

**The 404 signal, probed live (12 URLs, 2026-08-10, ~2 s apart).** Small and reported as such.

| Cohort | n | 404 | 200 | 403 |
|---|---|---|---|---|
| Already-closed postings | 8 | **1** | 7 | 0 |
| Open, `consecutive_missing = 1` | 4 | **1** | 2 | 1 |

Two findings, both load-bearing. **Recall is low** — 7 of 8 known-dead Workday/Ashby URLs still answer 200,
so the probe supplements the scanner and never replaces it. **Fail-open is not hypothetical** —
`pinterestcareers.com` answered **403** for a live posting, so reading 403 as gone would silently blacklist
whole employers. The probe did find a genuinely dead **open** posting (`jobs.lever.co/palantir/…`,
`consecutive_missing = 1`), which is exactly the between-scans window it exists for.

### Mutation checks — 10, all caught by the intended test

| Mutation | Caught by |
|---|---|
| `applied_job_ids` returns `{}` | 9 of 12 applied-suppression tests |
| `APPLIED_STATUSES` widened with `interested`/`withdrawn` | the two boundary tests + the drain test |
| applied checked *after* the ledger | `…outranks_a_live_ledger_disposition` |
| funnel `Drop` for `hidden_applied` deleted | the shortlist-reconciliation test |
| `GONE_STATUSES` widened with 403 | 3 core tests incl. the catalog pin |
| gone-branch dropped from the `FetchFailure` path (**the path that actually runs**) | `…arriving_as_a_FAILURE_still_withholds` |
| withheld lead left in `surfaced_job_ids` | `…is_not_recorded_seen` |
| dead probe writes `status='closed'` | `…is_not_closed_in_the_store` |
| `hidden_applied` dropped from `_shortlist_line` | `…summary_line_names_both_new_buckets` — the site **nothing else checks** |
| `--check-liveness` default flipped to False | `…run_COMMAND_actually_wires_a_prober_in` |

### The review — 3 reviewers, 2 BLOCKERs, both found by RUNNING the code

| Reviewer | Raised | Real | Wrong / rejected |
|---|---|---|---|
| diff (whole slice) | 1 BLOCKER + 1 MAJOR + 3 MINOR | all 5 | 0 — and it *executed* the pipeline to prove the BLOCKER |
| test-quality auditor | 3 MAJOR + 3 MEDIUM + 4 MINOR | all | 0; it mutation-tested every claim it made |
| docs-only | 2 BLOCKER + 5 MAJOR + 2 MINOR | all | 0 — it re-derived every live number independently and they matched |

Both BLOCKERs were invisible to reading: the funnel's tailor stage silently stopped reconciling whenever a
lead was withheld (breaking **Gate P0**, not P6), and `build_prober` — the entire production probe path —
had no test, so a change breaking `FetchFailure.status_code` would have disabled the probe permanently
with the suite green. Both fixes were mutation-checked, and so were the two sites the review showed were
covered by nothing — see the table above.

**The `git checkout` trap fired again.** Two review fixes were written, then mutation-tested, and the
`git checkout` that reverts each mutation destroyed them. "Commit before mutation-testing" was followed
for the first round and was too narrow: the rule is **commit before every mutation round**. Caught
immediately by a red suite.

### Standing corrections

- The live store is **still not regrouped**: `alembic_version` = `p6_posting_identities`, no
  `job_dispositions` table, `postings` = 24,073 and `count(distinct job_id)` = **24,073**, exactly 1:1.
  Re-verified read-only this session. A regrouped store would read 23,887.
- `PROGRAM.md` §3.P6 item 5 cites "§6, correction 3", but §6 is now *Program machinery* and carries no
  numbered corrections. The cross-reference is stale; the item text stands on its own.

---

## Session — 2026-08-10 (later still ×3) · 0.3.0 cut and tagged (D-112). No phase gate moved.

**Gate.** `make check` in a detached worktree, twice more as the release changed: **exit 0, 3,908 passed,
95.07%** on the doc-corrected slice, then **exit 0, 3,911 passed, 95.07%** on the final release commit
(`0834f81`). Session total **+66 tests** over the `5f0150d` baseline of 3,845.

### The changelog merge

| | Before | After |
|---|---|---|
| Subsections in the release section | **14** (`Added` ×5, `Changed` ×5, `Fixed` ×4) | **3** |
| Top-level bullets | 70 | **67** (3 removed as internal-only) |

The bullet count was **asserted equal** across the merge rather than eyeballed, and the merge refused
outright if any content sat outside a subsection. The 3 removed described the docs-index tooling, a
`docs/program/` markdown file, and the decision-log archive split — none of which is in the wheel
(`hatchling` builds `src/boardwatch` only).

### Release verified through a different path than the one that produced it

`make check` proves the source tree, not the artifact. So: `uv build` → both artifacts named `0.3.0` →
wheel installed into a **fresh isolated venv** → it reported `0.3.0` and carried `top --include-applied`
and `run --no-check-liveness`. That is the check that would have caught a version bump that did not
propagate.

### What cutting the release found — 3 defects, none of them in the changelog

| Defect | Evidence |
|---|---|
| `README.md` + `docs/configuration.md` still described **Typst** | `--format typst` does not exist (real value `latex`, `cli/tailor_cmd.py:106`); PDF called "best-effort" when P1a made it a hard gate; output named `.{typ,pdf}`, actually `.{tex,pdf}`. Replaced by tectonic in D-058/D-060, **11 decisions earlier** |
| `config show`/`set` reached **4 of 10** scalar settings | `seen_ttl_days` — shipped in this release — was invisible and unsettable. So were `busy_timeout_ms`, `reap_stale_after_hours`, `location_filter_mode`, `zero_skill_coverage_prior`, `recency_half_life_days` |
| 6 changelog claims falsified by the release itself | "nothing writes identities yet", "dedup has never run", "until dedup lands in P6", "the zero-output guard is not built here", "needs the reaper that P3 owns", and a stale Gate P6 line |

The `config` fix's own test found a **sixth** missing key after five had been listed by hand — which is
the argument for the detector over the care. **Third hand-maintained mirror to bite in one session**,
after the ranker's six drop sites and the funnel's tailor stage.

### The tag, and a prediction that was wrong

`v0.3.0` → `426f45c`, pushed by Mit at **17:08 UTC**. This session predicted the release workflow would
**queue forever** like `ci.yml`; it **acquired a runner within seconds**. The CI failure is specific to
`ci.yml`, not repo-wide. At ~13 min the run was still in `build + smoke test` and
`pypi.org/pypi/boardwatch/0.3.0/json` answered **404**, so the publish outcome is **unconfirmed** —
verify on PyPI, not in the Actions tab.

**One self-inflicted gate failure**, recorded so it is not read as a code failure: a `make check` exited 2
with `FileNotFoundError: /private/tmp/bw-gate-rel2` and **zero test failures**, because the worktree was
removed while its own run was still in flight. Remove a gate worktree only after its run exits.

---

## Session — 2026-08-10 (later still ×4) · The Slice 3 external review (D-113) + the CI dependency fix (D-114). No phase gate moved.

### The review — 3 findings from Codex, all real, all fixed

| # | Severity as reported | Finding | Standing |
|---|---|---|---|
| 1 | BLOCKER | `Fetcher` follows redirects, so a `302 → 404` chain reads as the posting itself being gone and withholds a live lead | **Fixed.** `FetchFailure.redirected` forwarded; redirected gone ⇒ `unknown` under the new signal `refetch_gone_after_redirect` |
| 2 | MAJOR | `Liveness` validated verdict and signal independently, so `dead` + `refetch_error` constructed and withheld a timed-out posting | **Fixed.** `SIGNAL_VERDICTS` is total; `ContradictoryLiveness` raised at construction |
| 3 | MINOR | `top`'s empty-result early return printed before the `hidden_applied` notice and its drain | **Fixed, and wider than reported** — the same return swallowed `hidden_duplicate` and `hidden_handled` too |

Reviewer's own verification, taken at face value only where it is checkable: it reviewed `5f0150d..18bfecc`
(not the "three commits" the prompt named), ran 111 focused tests, and reported `make check` green at a
source-identical commit with 3,908 tests / 95.07% coverage — consistent with this session's own runs. It
made no repository changes.

### Mutation checks — 4, one per new claim, all CAUGHT

Each derived from the test's stated claim, run after committing, with `__pycache__` cleared between rounds.

| # | Mutation | Result |
|---|---|---|
| 1 | Redirect rule ignored — a gone-status is `dead` however it was reached | CAUGHT (3 failed) |
| 2 | `Fetcher` never sets `FetchFailure.redirected` | CAUGHT (1 failed) |
| 3 | Verdict/signal coherence check disabled | CAUGHT (1 failed) |
| 4 | Empty-result notice call deleted from `top` | CAUGHT (2 failed) |

**#2 is the one that matters.** #1 and #3 test a decision that is visible by reading; #2 is the only one
that proves the plumbing between two modules, and it is the half a reader would have assumed rather than
checked.

### Gate runs — three, each pinned to a commit, so no commit is gated by a run that predates it

| Commit | Covers | Result |
|---|---|---|
| `70004b7` | the three review fixes | exit 0 · 3,918 passed · 95.10% · 298.84 s |
| `f713ce6` | + docs (D-113, D-114, STATE, METRICS, CHANGELOG) | exit 0 · 3,918 passed · 95.10% · 300.85 s |
| `f0a0f54` | + the second review round's fixes | exit 0 · 3,923 passed · 95.12% · 302.97 s |
| `861ea74`+`a729609` cherry-picked onto `cefd13e` | + the Windows encoding fix, **in isolation** | exit 0 · **3,924 passed** · **95.12%** · 293.03 s |

The last row is gated in isolation on purpose. A **concurrent session** was committing `profile_bundle`
work into the same clone, and the combined tree is **red**: `test_the_secret_scan_document_records_the_
builtin_v1_rows` imports `boardwatch.profile_bundle.secret_scan`, which exists only as an *untracked*
working-tree file. Those commits therefore pass on this machine and fail in any clean checkout — which is
what a detached worktree pinned to a commit exists to reveal, and what a `make check` run in the main tree
structurally cannot. Not this session's code and not this session's to fix; recorded so the next reader
does not attribute the red gate to D-113/D-114.

3,911 at `0834f81` → 3,923: **12 new tests** — 2 core-liveness redirect cases, 1 catalog-coherence case,
2 real-`Fetcher` redirect cases, 3 CLI notice cases (human empty-result ×2, JSON path ×1), 2 liveness
counter cases (summary + artifact), 2 `pdfinfo` probe cases. The workflow YAML is covered by none of
them — `make check` does not read `.github/`, which is the entire reason the 0.3.0 build failed.

### Mutation checks, round 2 — 5, all CAUGHT

| # | Mutation | Result |
|---|---|---|
| 5 | `gone_after_redirect` counter always 0 | CAUGHT (2 failed) |
| 6 | Counter computed but never passed to the funnel | CAUGHT (1 failed) |
| 7 | Redirect count subtracted from `alive` (folded into the partition) | CAUGHT (1 failed) |
| 8 | `pdfinfo` probe always reports present | CAUGHT (1 failed) |
| 9 | JSON path prints no notices | CAUGHT (1 failed) |

**Nine mutations this session, nine caught.**

### The CI dependency gap, closed

| Fact | Number |
|---|---|
| Tests failing on every runner before the fix | **33** (54 `tectonic binary not found` + 8 `_pdf_page_count` → None across their tracebacks) |
| Workflows that installed either binary | **0** of 3 |
| Days the gap was invisible because CI acquired no runners | **3** (D-058/D-060 landed 2026-08-07) |
| Runner OSes now installing both | **3** of 3 |
| Chocolatey `poppler` executables shipped | **0** (891 files, all source) |
| Tectonic bundle cache after one trivial compile | 42 MB |

### The review OF the review — 2 in-session reviewers, 5 more findings

Run on the fix itself, in fresh context, one code and one docs-only.

| Severity | Finding | Standing |
|---|---|---|
| BLOCKER | The CI action wrote tectonic's ~43 MB bundle cache inside the workspace, where `release.yml`'s `uv build` sweeps it into the published sdist | **Fixed** before the review landed (cache + warm-up moved to `RUNNER_TEMP`); the reviewer reproduced it by building a real sdist and finding `.tectonic-cache/` inside |
| MAJOR ×2 | `refetch_gone_after_redirect` was emitted and consumed by nothing — `grep -rn '\.signal' src` found no reader outside its own module | **Fixed.** Counted as a subset of `unknown`, on the run line and in the artifact. Both reviewers found this independently |
| MAJOR | Re-pushing `v0.3.0` unmoved re-runs the identical failure — that tag names `426f45c`, which has no `setup-typesetting` | **Fixed in STATE**, which now says the tag must land on a commit containing the fix |
| MAJOR | `doctor` probed `tectonic` and not `pdfinfo`, though a missing `pdfinfo` refuses **every** lead | **Fixed.** `check_pdfinfo` added, contributes to doctor's exit code, README names both prerequisites |
| MAJOR ×2 | Two false claims in the new docs: "the `--json` path was already correct" (it named 2 of 5 buckets) and "every liveness test but one injects a fake prober" (an entire 10-test module drives the real `Fetcher`) | **Both corrected**; the JSON path was also fixed rather than only re-described |
| MINOR | `RUN_CONTRACT.md` still named `TypstUnavailableError`, a class that does not exist | **Fixed** → `RenderToolMissingError`. D-112's claim that the Typst retraction "swept `docs/program/`" was false |
| MINOR | The redirect rule keys off "a redirect happened", so `http→https` and trailing-slash canonicalization also forgive an authoritative 404 | **Accepted, measured.** No host in the live 24,073 both redirects and 404s; fail-open direction; now observable through the new counter |

**The reviewers disagreed with the author on one point and were right:** `ARTIFACT_VERSION` was bumped
4→5 for the new key and then **reverted to 4** — every prior bump signalled a new top-level *section*, and
D-031 set the precedent for declining one on an additive key. The convention was found by grepping the
archive, not remembered.

### First real runner result — `ci.yml` run 31421520836 on `cefd13e`

| Lane | Result |
|---|---|
| test × ubuntu-latest × py3.11/3.12/3.13 | **success** ×3 |
| test × macos-latest × py3.11/3.12/3.13 | **success** ×3 |
| test × windows-latest × py3.11/3.12/3.13 | **1 failed, 3,922 passed** ×3 — the install worked; the failure is unrelated |
| gitleaks · perf · generalization | success |

**33 → 0 tectonic/`pdfinfo` failures on all three OSes.** The single Windows failure is
`test_the_real_program_indexes_are_current`: `read_text()` with no encoding decoded the logs as cp1252,
mangling the em-dash the decision-heading regex matches, so all **114** index rows reported "no heading".
Pre-existing, and previously unreachable — the suite died at tectonic before getting there. Fixed, plus a
tenth mutation (the encoding argument removed) CAUGHT by a new `EncodingWarning`-as-error test.

**Ten mutations this session, ten caught.**

**Not yet measured on a runner:** What *was* executed locally, on arm64 macOS, is the whole
macOS branch end to end — pinned URL, flat archive layout, `TECTONIC_CACHE_DIR` honoured (41 MB written
there and nowhere else), warm-up compile, and `pdfinfo` reading `Pages: 1` back. The Linux binary was run
in a container; asset checksums are verified for all five targets. **The Windows commands are constructed
from a verified zip layout and have never been run.** The push is the experiment, and Windows is the part
of it that can genuinely fail.
