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
| METRICS.md | 77 | Run log |
| METRICS.md | 105 | Acceptance run |
| METRICS.md | 116 | Session — 2026-08-09/10 · P6 Slice 1 design + plan. **No build, no gate movement.** |
| METRICS.md | 142 | Session — 2026-08-10 · P6 Slice 1 BUILT (unattended run). Branch `p6-slice1`, not merged. |
| METRICS.md | 352 | 2026-08-10 — P6 Slice 1 on the LIVE store (first real backfill) + Gate P6 clause 4 |
| METRICS.md | 391 | Session 2026-08-10 (later) — P6 Slice 2: the durable decision ledger, its drain, and job regrouping |
| METRICS.md | 484 | Session — 2026-08-10 (later) · D-109, the program-index gate. No phase gate moved. |
| METRICS.md | 525 | Session — 2026-08-10 (later still) · The P6 Slice 2 review (D-110). No phase gate moved. |
| METRICS.md | 615 | Session — 2026-08-10 (later still ×2) · P6 Slice 3, items 5 and 6 (D-111). Gate P6 unchanged: still 2 of 4. |
| METRICS.md | 728 | Session — 2026-08-10 (later still ×3) · 0.3.0 cut and tagged (D-112). No phase gate moved. |
| METRICS.md | 779 | Session — 2026-08-10 (later still ×4) · The Slice 3 external review (D-113) + the CI dependency fix (D-114). No phase gate moved. |
| METRICS.md | 899 | Session — 2026-08-10 (later still ×5) · Gate A career-profile bundle, slices T1–T9 (D-115). No phase gate moved. |
| METRICS.md | 988 | Session — 2026-08-10 (later still ×6) · The held commits are PUSHED; CI's first honest read (D-116, D-117). No phase gate moved. |
| METRICS.md | 1063 | Session — 2026-08-10 (later still ×7) · Gate A slice T10, semantic validation (D-118). No phase gate moved. |
| METRICS.md | 1244 | Session — 2026-08-10 · Gate A fix history reconciliation; independent T1–T10 review still owed. No phase gate moved. |
| METRICS.md | 1268 | Session — 2026-08-10 · Independent Gate A T1–T10 review sign-off; T11 permitted. |
| METRICS.md | 1306 | Session — 2026-08-11 · Gate A T11 implemented and reviewed. No phase gate moved. |

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

---

## Session — 2026-08-10 (later still ×5) · Gate A career-profile bundle, slices T1–T9 (D-115). No phase gate moved.

A parallel track, not a P0–P7 phase. **No program gate moved and none was expected to** — Gate A is the
career-profile bundle's own gate, it is **not met**, and it additionally requires an independent review
before Gate B may begin.

### What exists — 9 of 19 slices, one commit each

| Commit | Slice |
|---|---|
| `24e850f` | T1 dependency floor, package boundary, paths, typed outcomes |
| `d83e507` | T2 restricted YAML loader + closed 33-document grammar |
| `672e0bc` | T3 entity/contact/fact/relation/skill models |
| `c978324` | T4 policy catalogs, evidence, metrics, claims |
| `81ea7f9` | T5 manifests, history, imports, documents, JSON Schema export |
| `6586093` | T6 comprehensive synthetic example + package-data proof |
| `0ce6736` | T7 canonical serializer, evidence set, bundle/candidate identity, hash isolation |
| `d6a2fc1` | T8 document loading, global index, structural + referential validation |
| `fa532a8` | T9 blobs, redactions, byte budgets, versioned secret scanning |

**T10–T19 do not exist:** semantics, owner-gate derivation and approval stamps, deterministic import,
completeness/digest/reports, storage, rebase, promotion, migrations, the CLI, docs/audit.

### The gate — one run, on the final tree

| | |
|---|---|
| `make check` | **exit 0**, plain and unpiped, 392.53s (6m32s) |
| stages executed | generalization `OK` · program-index `--check` · `ruff check .` · `mypy --strict src tools` · pytest |
| pytest | **4,764 passed, 1 deselected** |
| coverage | **95.20%** (floor 85%) |
| `tests/profile_bundle` alone | **838 passed** |

### Negative tests confirmed by reverting the check, not by assuming

Each validation layer was disabled and the suite re-run, so a passing negative test is a measured result:

| Layer | Tests that went red without it |
|---|---|
| structural | **2 of 31** |
| referential | **11 of 24** |
| evidence | **29 of 36** |

The low structural number is itself a finding, not a gap: most structural violations are unrepresentable
because the document models refuse them at parse time (D-115).

### What `make check` caught that nothing else did

ruff, `mypy --strict`, and **838 green profile-bundle tests** — and `make check` still exited **2**.
**6 generalization violations**, all in the session's own new test fixtures: 4 × R1 literal home paths,
2 × R2 `example.test` addresses. This is the third recorded instance of the standing rule that
pytest + ruff + mypy passing individually is not green.

The first fix attempt added 2 reviewed `HOME_PATH_EXCEPTIONS` entries and **broke 31 shape tests** —
those tests run the checker over synthetic trees where any entry reports as stale. Reverted;
`allowlists.py` ends the session **unchanged**. The convention the repo already had is runtime assembly
of the fixture string, so the literal never exists on disk.

### Second-path verification, where it was available

- **Bundle identity:** design §7 steps 2–3 were implemented a **second** time in a throwaway generator.
  Both implementations independently produce `evidence_set_digest`
  `sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`.
- **Package data:** the real wheel was built and its contents listed — all **33** example documents plus
  the 145 KB JSON Schema ship, verified through the build rather than through the manifest that declares it.
- **Serializer isolation:** a characterization test pins the exact bytes of `eligibility/hashing.py` and
  all three `_version_of` helpers against accidental consolidation, using one non-ASCII payload that
  exposes both the `ensure_ascii` and the NFC differences at once.

### Defects found in the session's own code, by its own tests

| Defect | Why no test would have caught it later |
|---|---|
| index dispatched on **field name** | catalog rows indexed as records; a **correct** bundle reported duplicate IDs |
| evidence symmetry compared `supports` only | would have forced every legitimate contextual attachment to overstate itself |
| `SUPPORTED_RULESET_VERSIONS` bound **by name** at import | §12.2's stronger-ruleset rescan could not observe a new catalog version — it would have failed the day a v2 shipped, silently |

### Carried gaps, stated

- **Gate A not met; T10–T19 not built.** No `profile-bundle` CLI command exists.
- **No bundle-to-`Resume` bridge, deliberately.** `tailor_cmd._resume_path` still returns
  `settings.config_dir / "resume.yaml"`; nothing under `src/boardwatch/tailor/` imports the package.
- **Fixture gap:** the packaged "comprehensive" example carries **no redaction**, so the redaction-marker
  check is covered only by constructed cases. A test asserts the absence so the gap cannot silently
  close or widen. Fixing it moves `evidence_set_digest` and every digest pinned against it.
- **13 commits unpushed** on `main` at session end — 9 from this track, 4 from the concurrent P6 session.

---

## Session — 2026-08-10 (later still ×6) · The held commits are PUSHED; CI's first honest read (D-116, D-117). No phase gate moved.

The session's whole job was to unblock a push that had been held because two writers' commits were
interleaved and one writer's tree was red in a clean checkout. It also produced the first CI run in this
project's history that could be believed, and that run immediately found something no local check covers.

### The push blocker, resolved by measurement rather than by argument

| Question | How it was answered | Answer |
|---|---|---|
| Is the concurrent writer's tree self-contained? | `git ls-tree -r HEAD` for `profile_bundle/secret_scan.py` | **Yes** — tracked, landed in `fa532a8` |
| Does it survive a clean checkout? | `make check` in a **detached worktree** at `bed9b64`, so untracked files on disk cannot mask a gap | **exit 0** · 4,764 passed · 95.20% · 375 s |
| Is the docs-only tip safe too? | `make generalization index-check` in a second detached worktree at `1cdcd66` | **exit 0** |
| Independent corroboration | The peer session's own run, reported separately | 4,764 / 95.20% — **agrees exactly** |

`pytest` *collection* succeeding is the specific evidence, since the red tree was red at import time. The
two figures matching is the second path: the peer's run and mine shared no state.

**Pushed `cefd13e..1cdcd66`** — 15 commits, 5 P6/release and 10 Gate A.

### What CI found that nothing local did

| Job | On `cefd13e` (before) | Cause | Standing |
|---|---|---|---|
| `test` ubuntu ×3, macOS ×3 | **green** | — | tectonic/poppler fix confirmed: **33 → 0** |
| `test` windows ×3 | **red** — 1 failed, 3,922 passed | program-index gate decoded logs as cp1252, reported **all 114 rows** headless | fixed by `861ea74`, now pushed |
| `gitleaks` | green on `cefd13e`, **red on `1cdcd66`** | 2 synthetic Gate A fixtures written as literals | fixed by assembling at runtime (D-117) |

**`gitleaks`, `perf` and `generalization` are CI jobs that `make check` does not run**, and `gitleaks` is not
installed by any project tooling. A green `make check` is therefore not a green CI. This is the first time
that gap has cost anything.

### The gitleaks fix, verified in both directions

| Scan | Before | After |
|---|---|---|
| `gitleaks git --log-opts=cefd13e..HEAD` | **2 leaks** | **0** |
| `gitleaks dir .` (working tree) | 2 leaks | **no leaks found** |
| `gitleaks dir .` after clearing `__pycache__`/`.pytest_cache` | 3 leaks (1 stale `.pyc`, 2 `.pytest_cache`) | **no leaks found** — all three were gitignored, so CI never saw them |
| `tests/profile_bundle/test_profile_bundle_secret_scan.py` | 40 passed | **40 passed** — behaviour unchanged |

The `.gitleaksignore` was confirmed to **fire**, not assumed: the same commit range read 2 before the file
existed and 0 after.

### The new drift detector, confirmed by mutation

| Check | Result |
|---|---|
| `tests/unit/test_typesetting_pin.py` as-is | 1 passed |
| Same test with `Dockerfile`'s `ARG TECTONIC_VERSION` mutated to `0.18.0` | **1 failed** — the detector fires |
| `Dockerfile` restored | pin back at `0.17.0` |

### Final gates

| Tree | Command | Exit | Tests | Coverage |
|---|---|---|---|---|
| `bed9b64`, detached worktree | `make check` | **0** | 4,764 passed, 1 deselected | 95.20% |
| `1cdcd66`, detached worktree | `make generalization index-check` | **0** | — | — |
| `738d7df`, detached worktree | `make check` | **0** | 4,765 passed, 1 deselected | 95.20% |

### Carried gaps, stated

- **Gate A is gate-green but NOT reviewed.** Its commits being on `origin/main` is not sign-off, and the
  independent review is still owed before Gate B may start.
- ~~**The 0.3.0 re-tag has not been executed.**~~ **Done later the same night — 0.3.0 is PUBLISHED**
  (D-119). `v0.3.0` moved `426f45c` → `dc1ffec`; `ci.yml` run `31442555052` was **12 of 12 green**, the
  first fully green run in the project's history. Verified on all three targets through paths independent
  of the workflow's report: PyPI JSON API lists `0.3.0` (wheel 618,554 B, sdist 1,395,850 B), the GitHub
  Release carries both assets at **matching byte sizes**, and the GHCR manifest answers 200 as an OCI
  index over amd64 + arm64.
- **No local pre-push check for the three CI-only jobs.** `gitleaks git --log-opts=origin/main..HEAD` is
  the cheap mitigation and was not wired in.

---

## Session — 2026-08-10 (later still ×7) · Gate A slice T10, semantic validation (D-118). No phase gate moved.

Gate A is now **10 of 19 slices**. Still NOT met, still NOT reviewed, still wired to nothing.

### The gate

| Tree | Command | Exit | Tests | Coverage |
|---|---|---|---|---|
| `08d5c96`, detached worktree | `make check` | **0** | 4,866 passed, 1 deselected | 95.20% |
| `08d5c96` | `gitleaks git --log-opts=origin/main..HEAD` | **0** | 1 commit, ~147 KB in 86 ms | no leaks found |

The slice adds **101** tests across four files — `pytest --collect-only` on the four reports 101 — and
moves coverage not at all, 95.20% before and after, which is what a layer arriving with its own tests
looks like. **The arithmetic runs from 4,765, not the 4,764 recorded at `bed9b64`:** `738d7df` added the
tectonic-pin detector in between, so 4,765 + 101 = 4,866. An earlier draft of this record said "T9
closed at 4,764" and "adds 102 tests"; both were wrong, and the +102 delta was the reason the second
one looked right.

### Every semantic check was disabled and confirmed to take a test with it

Each of the thirteen error checks was removed from `validate_semantic`'s tuple in turn, and
`semantic_completeness` was stubbed to return `()`. The slice was committed first, so the restore was
safe; the tree was confirmed byte-identical afterwards. **Zero missed.**

| Check disabled | Tests that failed |
|---|---:|
| `_predicate_contracts_hold` | 7 |
| `_effective_facts_meet_their_predicate_evidence_contract` | 3 |
| `_cardinality_and_exclusivity_hold_over_effective_facts` | 4 |
| `_competing_single_valued_facts_are_inside_a_conflict_group` | 1 |
| `_fact_states_agree_with_supersession_edges` | 2 |
| `_assertion_tag_statuses_are_holdable` | 1 |
| `_skills_are_categorised_and_grounded` | 5 |
| `_metrics_use_the_revisions_unit_catalog` | 2 |
| `_metric_wordings_carry_their_protected_tokens` | 2 |
| `_application_only_facts_do_not_widen` | 2 |
| `_claims_reference_eligible_records` | 6 |
| `_claim_tags_are_known_and_authorised` | 10 |
| `_claim_text_traces_to_its_metrics` | 11 |
| `semantic_completeness` | 1 |

### What the packaged example turned out to prove, and what it cannot

The example validated semantically **clean on the first run** — 0 errors, 1 blocker
(`metric.packet-pantry.legacy-score.001`'s disqualifying caveat, which is the tier §11 asks for).
That is a real result rather than a vacuous one, because the fixture independently carries: a
superseded correction on a cardinality-`one` predicate, two `unresolved` candidates in one declared
conflict group, all three caveat severities, all six evidence classes, entities of all eleven kinds,
and six of the twelve assertion tags including three high-risk ones.

**Two things it cannot cover, both asserted so they cannot change silently:**

| Gap | The assertion that pins it |
|---|---|
| No `rendered` metric mention — every mention is `qualitative_only` | `test_the_example_declares_no_rendered_metric_mention` |
| No numeral in any claim text, so the strict figure rule is never exercised by the fixture | `test_no_approved_claim_in_the_example_carries_a_numeral` |

Closing either moves `evidence_set_digest` and every digest pinned against it, so both are deliberate
fixture changes rather than omissions — the same standing as D-115's redaction gap.

### The predicate sweep is derived from the catalog, not from a list

`test_a_conforming_fact_is_accepted_for_every_shipped_predicate` reads
`policy/predicates.yaml` out of the packaged example and synthesises, for each of the **41** rows, a
fact satisfying every column: a legal subject kind resolved to a real entity of that kind, the first
legal value type, a legal usage context, the full legal surface set, a legal basis with the strongest
state that basis may establish, and evidence records of the classes the row's cheapest
`minimum_evidence` alternative names. All 41 accepted. A new predicate row becomes a new case with no
test edit; a changed column changes what the case is built from.

### Wheel contents measured by the concurrent release session — and the ruling that followed

Not this session's command, and recorded because it bears on the track: the wheel built at `dc1ffec`
carries **65 `profile_bundle` entries** — 31 modules, 33 example YAML documents, 1 JSON Schema — and
the `## [0.3.0]` changelog section names none of them. So T1–T10 publish to PyPI unreviewed under an
irreversible version.

**Mit ruled: ship as-is (D-119).** He was offered "hold 0.3.0 until Gate A is reviewed" as an explicit
option and declined it — the package is inert (no CLI, no `Resume` bridge, both asserted, nothing in a
shipped code path imports it), `gitleaks` and `generalization` are green on it in CI, changelogs do not
normally enumerate internal packages, and no commit on `main` carries the CI fix without it. So this is
**not** an open question and this record should not be read as one. What did not change: **the Gate A
review is still owed, its scope is now T1–T10 rather than T1–T9, and Gate B stays prohibited.**

### The Gate A T1–T10 review: STARTED, STOPPED EARLY, and partly salvaged

Dispatched three fresh-context Opus reviewers, then **stopped two of them on Mit's instruction** —
"at this rate, we'll run out of usage." Recorded honestly because a half-run review that is
remembered as a whole one is worse than no review.

**What ran to completion:** nothing I dispatched directly. The foundations reviewer had fanned out into
its own nested sub-agents, and **three of those grandchildren finished after their parent was killed**,
which is where every finding below comes from. A "3-wide" review was in fact **11 agents**; Mit
stopped the remaining 7 outright. Cost estimates must assume nesting.

**Still owed:** the code-running review of T10 (killed before it reported), canonical identity vs §7,
blobs and secret scanning, the dead-check sweep, the packaged-example fixture audit, the
metric/evidence and conflict/claim/tag catalog checks, and the docs-only pass. **Roughly two thirds of
the intended review did not happen.**

#### Verified, with negative controls

| Claim checked | Result |
|---|---|
| 9 closed catalogs (§9 entity kinds + 10 status catalogs, §10.1 value types, §10.2 states/bases, §10.1 contexts, §10.3 surfaces, §9 channel types, §8 prefixes) | **exact match**, member for member, order included |
| All **41** predicate rows × **14** columns against §10.4's two tables | **0 disagreements**; catalog order matches design order |
| `PredicateSpec` has no parser default on any of its 15 keys | verified by dropping each key in turn |
| No shipped predicate uses `owner_attestation_authority: verified` | verified |
| The shipped JSON Schema is in enum parity with all 17 catalogs | verified |

Both diffs were **negative-controlled**: mutating a copy of the catalog produced 24 flagged rows with
exact column names, so `0 / 41` is a real negative rather than a vacuous parser.

#### Findings

| Severity | Where | Defect |
|---|---|---|
| **MAJOR** | `models/policy.py:124-171` | §10.4's cross-column rule — "every legal verification basis must be backed by its corresponding evidence class" — is **not validated at catalog level**. `BASIS_EVIDENCE_CLASSES` exists (`models/evidence.py:310`) but is consulted only per *fact*. A tenant-authored `policy/predicates.yaml` can declare a basis no `minimum_evidence` alternative can satisfy; accepted by construction. Shipped data conforms, so it is latent. Impact is an unreachable evidence route, not an eligibility leak |
| MINOR | `models/policy.py:147` | `legal_surfaces` accepts `[]` while every other required list carries `min_length=1`. An empty maximum is a predicate no fact may ever project. Latent — no shipped row is empty |
| MINOR | `models/base.py:200-205` | The docstring justifying `id_pattern`'s longest-first sort states a **false premise**: regex backtracking already handles `approval` vs `approval-stamp`. The sort is harmless (0/278 behavioural difference) but its stated reason is wrong |
| MINOR | `test_profile_bundle_entity_models.py:113,147` | The two tests defending that sort **cannot fail** — removing the sort leaves both passing. "A check that cannot fire reads as coverage", in the tests this time |
| MINOR | `models/entities.py:239` | `SHIPPED_PROJECT_STATUSES` is dead: its only reader is a test asserting it equals its own literal. The real `shipped` authorization is catalog data. Its comment overstates the wiring |
| MINOR (owed, not wrong) | `models/policy.py:97-110` | `expiry` / `review_interval_days` are required, correct, and **consumed by nothing** — no `as_of` exists anywhere in `src/boardwatch/profile_bundle/`. Consistent with 10 of 19 slices; flagged so the column's presence is not read as enforcement |

#### The restricted YAML loader: 2 BLOCKERs, and both break content addressing

The single highest-value finding of the session, and it lands on **T2**, not on T10.

**BLOCKER — an explicit YAML 1.1 tag bypasses the entire restricted-loader contract**
(`yaml_loader.py:65-97`). `resolve()` narrows only *implicit* scalars; nothing inspects `node.tag`, so
`!!bool`, `!!int`, `!!float`, `!!timestamp`, `!!binary`, `!!set`, `!!omap` and `!!pairs` all reach the
stock `SafeConstructor` untouched. Anchors are refused; tags are not. Every clause of §7's narrowing is
evadable in one keystroke — `!!bool yes` → `True`, `!!int 0123` → `83` (octal), `!!timestamp 2026-08-10`
→ a `date`, and `!!omap` bypasses `construct_mapping` so **duplicate keys survive**.

**Demonstrated end-to-end against the real packaged bundle: four byte-different spellings of one record
produce the identical `bundle_digest`.** `value: true` versus `value: !!bool yes` / `!!bool on` /
`!!bool TRUE`, and `reviewed_at: '2026-08-10'` versus `!!timestamp 2026-08-10`, all accepted, all
hashing the same. `schema_version: 1` versus `!!int 0x1` / `!!int 001` / `!!binary MQ==` likewise. This
is precisely the harm the module's own docstring says justifies refusing anchors wholesale: "they make
one logical record expressible in two byte sequences, which is exactly what content addressing must not
have to reason about."

Pydantic does **not** backstop it: `StrictModel` sets `extra="forbid"` and `frozen=True` but not
`strict=True`, so `IntegerValue` accepts `!!binary MzE=` as `31`.

**BLOCKER — untyped builtin exceptions escape `load_documents`** (`yaml_loader.py:145-150` guards only
`yaml.YAMLError`). PyYAML's tag constructors raise raw builtins: `!!bool y` → `KeyError`, `!!int abc` →
`ValueError`, `!!timestamp nope` → `AttributeError`, `!!set x` → `ValueError`. None is a
`ProfileBundleError`, and `validation/context.py:113` catches only `RestrictedYamlError`, so a traceback
leaves the package and defeats §21's exit contract. Reachable from ordinary authored content, since
§19's workflow has an agent writing draft YAML that `validate --draft` then reads.

**One fix closes both:** reject any explicitly-written node tag in `compose_node`, where the anchor
check already lives and already has the event in hand.

| Severity | Where | Defect |
|---|---|---|
| **MAJOR** | `errors.py:387`, `yaml_loader.py` | One `RestrictedYamlError` covers 8+ distinct violations, distinguishable only by message text, and `context.py` collapses them all to `RESTRICTED_YAML_VIOLATION`. Consequence: **`IssueCode.INVALID_YAML` is referenced nowhere but its own definition** — permanently dead — and `INVALID_UTF8` never fires for a document. Violates `CLAUDE.md`'s "typed violations at the raise site, never classify by string-matching a message" |
| **MAJOR** | `yaml_loader.py:37-45` | Out-of-contract scalars are caught by a **2-pattern blocklist** where §20.1 implies an allowlist. `0x1f` is refused but `0xZZ` is not; `0123` is refused but `1e3` is not. Sharpest case: `YearMonthValue` accepts both `'2026-08'` and unquoted `2026-08` to the **same digest**, while the neighbouring `DateValue` refuses the unquoted form |
| MINOR | `yaml_loader.py:38,47` | `+0`/`-0`/`0` and `null`/`~`/empty each collapse to one canonical value — same byte-multiplicity class, but explicit choices. `a: -` is refused while `a: +` is accepted as `'+'` |
| MINOR | design §7 line 302 | The design says the loader "removes" YAML 1.1's coercions; it keeps the resolvers and consults them as an ambiguity oracle. The implementation is the better design — the *design text* wants the correction, so nobody "fixes" the code toward the spec |

**Verified correct (no finding):** all 17 requested cases behave per design for *plain* scalars —
duplicate keys in six positions, anchors, aliases, merge keys both spellings, leading-zero and
base-prefixed integers, sexagesimal `12:30:00` refused as an int, every quoted form surviving as an
exact `str`, non-finite floats, BOM handling, multi-document refusal, and non-UTF-8. The
`pyyaml>=6.0,<7.0` pin is present in both `pyproject.toml` and `uv.lock` (resolved 6.0.3), so §7's
dependency precondition is **MET**. No loader bypass exists anywhere in the package.

**None of these were fixed in this session** — a code fix owes a full `make check` (~7.5 min), and
batching them behind one gate is cheaper than paying it per finding. They are open work, not history.

#### One self-inflicted incident, recorded because it nearly produced a false finding

Stopping the docs reviewer mid-mutation-round left `validation/semantic.py` **mutated** in the working
tree — `_claim_text_traces_to_its_metrics` removed from `validate_semantic`'s tuple, with no restore.
A third reviewer was reading that same file at the time. Caught by `git status` immediately after the
stop, restored from `HEAD`, `__pycache__` cleared, 101/101 re-confirmed, and the surviving reviewer
told about the contamination window. Safe only because the slice was committed first.

## Session — 2026-08-10 · Gate A fix history reconciliation; independent T1–T10 review still owed. No phase gate moved.

This is a documentation reconciliation, not a Gate A review. The live repository is `main` at
`bbec2c0`, and `origin/main` points to the same commit. The five Gate A fix commits are implemented
and pushed:

| Commit | Subject | Standing |
|---|---|---|
| `1de10c7` | reject explicit YAML tags | implemented and pushed; not independently reviewed |
| `20ff50c` | type restricted YAML failures | implemented and pushed; not independently reviewed |
| `8d32294` | validate predicate evidence routes | implemented and pushed; not independently reviewed |
| `9d78450` | allowlist plain YAML scalars | implemented and pushed; not independently reviewed |
| `bbec2c0` | tighten minor model contracts | implemented and pushed; not independently reviewed |

Gate A remains **not met and not independently reviewed**. The earlier partial review covered roughly
one third of the intended T1–T10 scope; roughly two thirds remains owed. In particular, the required
code-running T10 pass, canonical identity against design §7, blobs and secret scanning, dead-check
sweep, packaged-example audit, metric/evidence and conflict/claim/tag catalog checks, and docs-only
pass have not been treated as complete merely because these fix commits are present or prior
`make check` runs were green.

The pinned evidence-set digest remains the review target:
`sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`.

## Session — 2026-08-10 · Independent Gate A T1–T10 review sign-off; T11 permitted.

This is the completed independent review of the five Gate A fix commits (`1de10c7`, `20ff50c`,
`8d32294`, `9d78450`, and `bbec2c0`) and the untracked design correction. The review used the live
code, the original findings above, targeted executable reproductions, negative controls, and the
packaged example. It did not treat prior `make check` output or test names as review evidence.

### Verdict

**INDEPENDENT REVIEW SIGN-OFF: PASS.** No unresolved BLOCKING or SHOULD-FIX findings remain, so the
hard gate permits T11. This does **not** mark Gate A implementation complete: T11 is the next planned
slice, Gate B remains prohibited, and T12 onward was not started.

### Findings

| Severity | Finding | Resolution and verification |
|---|---|---|
| SHOULD-FIX | `yaml_loader.load_yaml_bytes` classified an unexpected internal parser exception as `INVALID_YAML`, contrary to §21's internal-failure path. | **Fixed** in `dfa655e`. The test was run red first (the injected `ValueError` produced the wrong typed failure), then the loader test passed and plain unpiped `make check` exited 0. |
| SHOULD-FIX | `_ABSOLUTE_PERSONAL_PATH_RE` required two backslashes in its Windows branch, so ordinary `C:\\Users\\...` text escaped the §12.2 personal-path scan. | **Fixed** in `f166d18`. The new regression was run red first, then the focused evidence suite passed and plain unpiped `make check` exited 0. |
| BLOCKING | None. | No unresolved blocker after re-review. |
| NICE-TO-HAVE | None material to the reviewed Gate A scope. | No action required. |

### Executed review evidence

| Area | Result |
|---|---|
| Restricted YAML | Explicit standard/custom tags refused; invalid UTF-8, malformed YAML, and restricted scalars returned typed codes; plain scalar allowlist negative controls refused `0xZZ`, `1e3`, `2026-08`, `123abc`, `+`, and `089`; quoted forms remained strings. |
| Predicate contracts | All 41 shipped rows accepted a conforming fact through the real loader and semantic validator. Negative controls reached `unknown_predicate`, `predicate_surface_illegal`, and `evidence_contract_unmet`. Unreachable basis routes and empty `legal_surfaces` were refused. |
| Identity | The packaged example produced the pinned evidence digest and a stable bundle digest. Formatting/key-order, relocation, sidecar, and blob-path controls were stable; evidence content and blob-byte changes moved identity. |
| Evidence and secrets | Blob tampering raised `BlobDigestMismatchError` without altering the corrupt bytes. Clean captures stayed clean; secret hits exposed rule IDs and UTF-8 byte ranges only, with correct non-ASCII offsets and no matched text. |
| Packaged example | 33 documents loaded through the production loader; structural, referential, evidence, and semantic validation each returned zero findings; the pinned digest remained `sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`. |
| T10/catalog pass | Direct code-running sweep plus focused semantic, metric, claim, surface, evidence, referential, canonical, blob, and secret suites: 269 focused tests passed with `--no-cov`; the full repository gate passed with 4,897 tests. Removed dead checks and `SHIPPED_PROJECT_STATUSES` have no remaining source references. |
| Docs-only pass | STATE/METRICS status and indexes were reconciled; no new decision ID was needed. |

The review therefore closes the prior partial-review carryover and authorizes the exact T11 scope in
the implementation plan. The pinned evidence-set digest remains:
`sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`.

## Session — 2026-08-11 · Gate A T11 implemented and reviewed. No phase gate moved.

The hard gate from the preceding review sign-off was met, so this session implemented only Task 11
from the existing plan. T12 onward, personal data, Resume integration, schema/store/migrations,
CHANGELOG.md, the v0.3.0 tag, and Gate B remain out of scope.

### T11 result

| Slice | Result |
|---|---|
| Pure owner-gate derivation | Added `required_approval_decisions` for fact, contact, evidence sufficiency, claim, metric surfaces, joined source scope, source-record exclusion, and conflict-ruling authorization. |
| Approval stamp | Added pure `build_approval_stamp`; it performs no TTY interaction or filesystem writes and rejects wrong target kinds/states through the typed entry model. |
| Reusable fixture | Added a deliberate promoted-revision fixture containing a `RevisionManifest`, one `ChangeRecord`, and one `ApprovalStamp` with the candidate's required owner entries, reusable by later history/promotion slices. |
| History | Added append-only change/approval/ruling prefix checks, exact one-change/one-stamp promotion append checks, manifest binding checks, required owner-entry checks, target-content digest checks, and owner-derived `authorized_by` enforcement. |
| Scope | T11 files only; no T12+ implementation was started. |

### T11 verification and findings

The initial T11 slice is commit `645046e`; its plain unpiped `make check` exited 0 with 4,906 selected
tests. A post-commit self-review found one SHOULD-FIX gap: forged `authorized_by` was not rejected by
history validation. TDD was run red by removing the guard, the guard was restored, and commit
`402de97` fixed it; its plain unpiped `make check` exited 0 with 4,907 selected tests. No unresolved
BLOCKING or SHOULD-FIX findings remain. The T11 focused suite passed 9 tests before the final fix and
6 history tests after it.

The independent review remains signed off, T11 is complete, and Gate A as a whole remains **not met**
because the later planned slices have not been implemented or reviewed. The pinned evidence-set digest
remains:
`sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`.
