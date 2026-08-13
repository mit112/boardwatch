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
| METRICS.md | 100 | Run log |
| METRICS.md | 128 | Acceptance run |
| METRICS.md | 139 | Session — 2026-08-09/10 · P6 Slice 1 design + plan. **No build, no gate movement.** |
| METRICS.md | 165 | Session — 2026-08-10 · P6 Slice 1 BUILT (unattended run). Branch `p6-slice1`, not merged. |
| METRICS.md | 375 | 2026-08-10 — P6 Slice 1 on the LIVE store (first real backfill) + Gate P6 clause 4 |
| METRICS.md | 414 | Session 2026-08-10 (later) — P6 Slice 2: the durable decision ledger, its drain, and job regrouping |
| METRICS.md | 507 | Session — 2026-08-10 (later) · D-109, the program-index gate. No phase gate moved. |
| METRICS.md | 548 | Session — 2026-08-10 (later still) · The P6 Slice 2 review (D-110). No phase gate moved. |
| METRICS.md | 638 | Session — 2026-08-10 (later still ×2) · P6 Slice 3, items 5 and 6 (D-111). Gate P6 unchanged: still 2 of 4. |
| METRICS.md | 751 | Session — 2026-08-10 (later still ×3) · 0.3.0 cut and tagged (D-112). No phase gate moved. |
| METRICS.md | 802 | Session — 2026-08-10 (later still ×4) · The Slice 3 external review (D-113) + the CI dependency fix (D-114). No phase gate moved. |
| METRICS.md | 922 | Session — 2026-08-10 (later still ×5) · Gate A career-profile bundle, slices T1–T9 (D-115). No phase gate moved. |
| METRICS.md | 1011 | Session — 2026-08-10 (later still ×6) · The held commits are PUSHED; CI's first honest read (D-116, D-117). No phase gate moved. |
| METRICS.md | 1086 | Session — 2026-08-10 (later still ×7) · Gate A slice T10, semantic validation (D-118). No phase gate moved. |
| METRICS.md | 1267 | Session — 2026-08-10 · Gate A fix history reconciliation; independent T1–T10 review still owed. No phase gate moved. |
| METRICS.md | 1291 | Session — 2026-08-10 · Independent Gate A T1–T10 review sign-off; T11 permitted. |
| METRICS.md | 1329 | Session — 2026-08-11 · Gate A T11 implemented and reviewed. No phase gate moved. |
| METRICS.md | 1359 | Session — 2026-08-11 (later) · Gate A T12 implemented, NOT independently reviewed. No phase gate moved. |
| METRICS.md | 1420 | Session — 2026-08-11 (later ×2) · Gate A T12 reviewed TWICE, both REWORK, both rounds fixed. No phase gate moved. |
| METRICS.md | 1468 | Session — 2026-08-11 (later ×3) · Gate A T12 reviewed a THIRD time, REWORK again. T13 partially built on a branch. No phase gate moved. |
| METRICS.md | 1523 | Session — 2026-08-11 (later ×4) · T12 fixed through five reviews; T13 built. No phase gate moved. |
| METRICS.md | 1589 | Session — 2026-08-11 (later ×5) · T13 merged; T14 reviewed and partly fixed; T15 and T17 built. No phase gate moved. |
| METRICS.md | 1661 | Session — 2026-08-11 (later ×6) · T14 reviewed, fixed and MERGED; T15 reviewed twice and fixed; T17 reviewed. No phase gate moved. |
| METRICS.md | 1805 | Session — 2026-08-11 (later ×7) · The T14 and T15 FIX ROUNDS independently reviewed: REWORK. No phase gate moved. |
| METRICS.md | 1871 | Session — 2026-08-11 (later ×8) · The T14/T15 fix-round findings FIXED; T16 reviewed by three lenses. No phase gate moved. |
| METRICS.md | 1975 | Session 2026-08-12 (03:10 unattended) · the final Gate A integration gate — exit 0 · 5,906 passed · 95.63%. No phase gate moved. |
| METRICS.md | 2007 | Session — 2026-08-12 (working session) · T18 reviewed by two lenses and fixed; all nineteen slices merged into one tree. No phase gate moved. |
| METRICS.md | 2061 | Session — 2026-08-12 (later) · Gate A's review loop CLOSED at round five; all four gates green. No phase gate moved. |
| METRICS.md | 2135 | Session — 2026-08-12 (bonus window) · Gate A MERGED into main; two silent-success defects found and fixed after it. No phase gate moved. |
| METRICS.md | 2220 | Session — 2026-08-12 (continuation) · **Gate A MET.** Its last open question ruled and built (D-143), the track PUSHED, and the Windows matrix taken from never-ran to green (D-145). |
| METRICS.md | 1394 | Session — 2026-08-11 (later still) · The T12 independent review (D-121) and its fix. No phase gate moved. |
| METRICS.md | 2329 | Session — 2026-08-12 (P3 slice 5, task 7) · Records, retractions, and the gate — GATE_EXIT=0. No phase gate moved. |
| METRICS.md | 2374 | Session — 2026-08-12 (later still ×2) · Slice 5 pushed (`8c1b78f`); `d147-residuals` built, gated, reviewed — unmerged. No phase gate moved. |
| METRICS.md | 2427 | Session — 2026-08-12 (D-147 residuals) · R1, R2, R3 closed — GATE_EXIT=0 · 5,979 passed. No phase gate moved. |
| METRICS.md | 2499 | Session — 2026-08-13 · `d147-residuals` MERGED (not a fast-forward) — GATE_EXIT=0 · 5,979 passed. No phase gate moved. |
| METRICS.md | 2591 | Session — 2026-08-13 (later) · The gate parallelised: 16m13s → ~4m20s (D-150). No phase gate moved. |
| METRICS.md | 2658 | Session — 2026-08-13 (close) · CI cadence (D-151) and the CGPA retraction (D-152). No phase gate moved. |
| METRICS.md | 2711 | Session — 2026-08-13 (render + CI red) · First boardwatch résumé rendered; a red CI job fixed (D-153) and `top`'s 141 s floor removed (D-154). No phase gate moved. |
| METRICS.md | 2786 | Session — 2026-08-13 (push) · D-153's first fix was WRONG and a review caught it pre-push; six commits pushed. No phase gate moved. |
| METRICS.md | 2850 | Session — 2026-08-13 (roadmap review) · The program reorients onto the bundle path (D-155, D-156, D-157). No phase gate moved. |

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

## Session — 2026-08-11 (later) · Gate A T12 implemented, NOT independently reviewed. No phase gate moved.

This session implemented only Task 12 from the existing plan — deterministic enumeration, candidate
identity, and idempotent import (design §18, §18.1). T13 onward, Gate B, personal data, Resume/tailor
integration, schema/store/migrations, CLI work, `CHANGELOG.md`, and version tags remain out of scope
and were not started.

### T12 result

| Slice | Result |
|---|---|
| Adapters | `enumerators.py`: the closed version-1 table (`boardwatch_resume`/`boardwatch-resume-v1`, `markdown_document`/`markdown-blocks-v1`, `structured_objects`/`structured-objects-v1`, `repository_markdown`/`markdown-blocks-v1`), all version 1, plus the three adapters themselves. |
| Locators | NFC, trimmed, case-preserving, percent-encoded POSIX-relative locators; empty, absolute, `.` and `..` components refused; `is_normalized_locator` as a predicate rather than a re-normalization, because percent-encoding is not idempotent. |
| Identity | `derive_source_record_id` and `derive_candidate_id` over the exact canonical JSON arrays `["source-record", source_id, normalized_locator]` and `["candidate", source_record_id, predicate, canonicalized_typed_value]`. Both recomputed in the tests through a hand-rolled `hashlib`/`json` path, and both reproduce the packaged example's authored IDs unchanged. |
| Importer | `imports.py`: `enumerate_source` takes bytes and a typed scope (never a path or a repository), hands extraction an immutable `EnumeratedSource`, assigns every ID itself, accepts and ignores a proposed candidate ID, and merges idempotently — same digests collapse, a changed digest appends one occurrence, a changed canonical value creates a new candidate. |
| Validation | `validation/imports.py`: source-kind/enumerator pairing, approved-scope discriminant and locator shape, derived record identity, one record per `(source, locator)` pair, exclusion reconciliation, imported-record candidate ownership; plus two completeness blockers for `review_required` and for an approved source the ledger never enumerates. |
| Isolation | No import of `boardwatch.tailor` in either direction; the Boardwatch résumé source model is restated package-locally and deliberately does not run the tailor loader's bullet-whitespace normalization. |

### T12 verification

| Check | Result |
|---|---|
| Red first | `uv run pytest <the two T12 files> -q` before any implementation: exit **2**, `ModuleNotFoundError: No module named 'boardwatch.profile_bundle.enumerators'` — the plan's expected failure. |
| Targeted green | The same two files with `--no-cov`: exit **0**, **179 passed**. The plan's literal command without `--no-cov` exits **1** on the repo-wide `--cov-fail-under=85`, which two test files cannot reach; every test in it passes. |
| Mutation | **59** production checks were each inverted or disabled one at a time, run against a narrow test, and restored. **59 caught, 0 survived.** Four checks were found unable to fire and deleted (D-120); one was kept and given a test that makes it fire. |
| Full gate | Plain, unpiped `make check`: exit **0**, **5,086** selected tests, **95.39%** coverage. |

### Standing

T12 is implemented and mutation-verified **locally only**. It has **not** been independently
reviewed, and nothing here is sign-off. Gate A as a whole remains **not met** and **not fully
reviewed**: the later planned slices are unimplemented, and Gate B stays prohibited. **T13 is the
next task.** The pinned evidence-set digest is unchanged:
`sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`.

## Session — 2026-08-11 (later still) · The T12 independent review (D-121) and its fix. No phase gate moved.

The independent review of `b817709` returned **VERDICT: REWORK** with five BLOCKING findings, one
SHOULD-FIX and one NICE-TO-HAVE, every one reproduced by the reviewer. `ce0a8de` fixes all seven.

| Finding | Severity | Standing |
|---|---|---|
| Selected-section scope re-encoded an already-resolved heading path, so no heading containing a space could be imported | BLOCKING | fixed — validated, never re-encoded |
| `is_normalized_locator` accepted escapes no adapter emits (`%41`) | BLOCKING | fixed — now the encoder's exact inverse |
| Validation never rederived stored candidate IDs | BLOCKING | fixed — new `IMPORT_CANDIDATE_IDENTITY_MISMATCH` |
| `merge_candidate_package` ignored predicate and value canonicality | BLOCKING | fixed at both merge and validation |
| Ownership used `any`, so a record could name a foreign candidate | BLOCKING | fixed — every named candidate must be its own |
| Résumé entry/bullet uniqueness decided before trim/NFC | SHOULD-FIX | fixed — compared in the locator's own form |
| Re-enumeration in one interpreter cannot see hash-seed iteration | NICE-TO-HAVE | fixed — `PYTHONHASHSEED` subprocess test |

| Check | Result |
|---|---|
| Reproductions | 14 new tests, all red before the fix, all green after |
| Mutation | **67 caught, 0 survived, 0 broken.** Three first-pass survivors each found a real problem: a redundant guard (deleted per D-115), a test passing for the wrong reason, and a mis-specified mutation |
| Full gate | plain unpiped `make check` in a worktree pinned to `ce0a8de`: exit **0**, **5,111** passed, **95.40%**, 8m43s |

**T12 is NOT signed off.** The fix owes its own independent review — a retraction commit
characteristically reintroduces the class it cures — and that review is in flight. Gate A remains
not met and Gate B remains prohibited. The pinned evidence-set digest is unchanged:
`sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0`.

## Session — 2026-08-11 (later ×2) · Gate A T12 reviewed TWICE, both REWORK, both rounds fixed. No phase gate moved.

T12 was reviewed by an external reviewer, fixed, re-reviewed by the same reviewer at high reasoning
effort, checked independently by a fresh-context verification agent, and its decision record was
fact-checked by a separate docs reviewer. Every round found real defects. T13 onward, Gate B,
personal data, tailor integration, schema/store/migrations, CLI work, `CHANGELOG.md` and version
tags remain out of scope and were not started.

### What the two reviews found

| Round | Verdict | Findings | Outcome |
|---|---|---|---|
| Review 1 (`b817709`) | REWORK | 5 BLOCKING + 2 | All 7 fixed in `ce0a8de` (D-121). Worst: no valid import route existed for any Markdown heading containing a space. |
| Review 2 (`ce0a8de`) | REWORK | 4 BLOCKING + 2 SHOULD-FIX | 5 fixed, 1 judged-and-declined with the assumption stated (D-122). |
| Verification agent (`ce0a8de`) | — | 1 more | The round trip omitted the encoder's NFC and trim; four forged locator spellings validated and inflated the Gate B denominator 4→5 with **zero findings from any layer**. |
| Docs review (D-122 draft) | NEEDS CORRECTION | 5 blocking claims | Corrected before commit. One decline rested on a false premise and became a shipped check instead. |

### Round-two verification

| Check | Result |
|---|---|
| Red first | 11 reproductions for the review findings, then 6 more for the adapter grammar, each run before its fix: **11 failed / 133 passed**, then **5 failed / 73 passed**, then **6 failed**. One initially failed at parse time and one passed for the wrong reason; both were rewritten before being counted. |
| Mutation | **20 distinct** production checks inverted or disabled one at a time against a narrow test, then restored. **20 caught, 0 survived.** One survivor first: the `_root` refusal, whose test was passing because the new scope-containment check fired ahead of it — the test was narrowed to the `_root` diagnostic rather than the check being weakened. |
| Targeted green | The two T12 files with `--no-cov`: exit **0**, **254 passed**. |
| Full gate | Plain, unpiped `make check`: exit **0**, **5,200** selected tests, **95.40%** coverage, 9m38s. |

**A correction to this log.** The first draft of D-122 and one report to Mit both said "13 of 13
mutations caught". The driver's list held 13 entries but **12 distinct mutations** — one was
duplicated byte-for-byte and counted twice. The duplicate was seen in the output and dismissed as
harmless rather than corrected. The honest figures are 12 for the review fixes and 8 for the adapter
grammar: **20 distinct**.

### Gate time this session

`make check` ran three times for one commit. The first was SIGTERM'd at 38% after ~15 minutes with
two subagents reading the same tree; the second reached 37% in ~7 minutes once they finished and was
then killed deliberately, because the docs review showed a declined finding needed implementing. Only
the third counts. **Roughly 31 minutes of gate time produced one 9m38s result**, and the lesson is
recorded in `worktrees-for-parallel-work`: a worktree fixes file-state collisions, not CPU
contention, and it cannot gate uncommitted work at all.

### Standing

T12 is implemented, twice-reviewed, twice-fixed and mutation-verified. It is **not signed off** — a
retraction commit reintroduces the defect class it cures, so each one owes its own review, and a
third is owed before Gate B. Gate A as a whole remains **not met** and **not fully reviewed**. **T13
is the next task**, and its promoted-revision fixture is built and verified in a fresh interpreter.

## Session — 2026-08-11 (later ×3) · Gate A T12 reviewed a THIRD time, REWORK again. T13 partially built on a branch. No phase gate moved.

### The third T12 review (D-124)

| Item | Result |
|---|---|
| Reviewer | Same external reviewer, high reasoning effort, fresh worktree pinned at `126a268`. |
| Verdict | **REWORK** — the third consecutive one. |
| Findings | **4 BLOCKING + 1 SHOULD-FIX**, every one reproduced against all four validation layers. |
| Previous rounds | All round-one and round-two findings confirmed **closed**. |
| Where the new ones live | All four are in code written to close the previous round. |
| Reproduced independently | Yes — the `_root` namespace collision was reproduced in this session before the finding was accepted, and is worse than the review framed it: the emitter itself conflates pre-heading content with a heading named `_root`. |

Round-three fixes are **NOT started**, deliberately. Both previous fix rounds were authored by the
context that produced the defects, and that is the failure D-122 named and then repeated.

### T13 (partial, branch `t13-digest`, not merged)

| Slice | Result |
|---|---|
| `reports.py` | Report model, deterministic JSON + human renderings, §21 outcome and exit code. **30 tests.** |
| `validation/digest.py` | §20.6: bundle and evidence-set digests, directory/`COMPLETE`/`CURRENT` agreement, manifest state, the inverse candidate view, the final change's parent. Plus `CurrentPointer` + `read_current` + `read_complete` — the first readers of those files anywhere in `src/`. **40 tests.** |
| Fixture | `promote_example_tree` builds a genuinely promoted revision (name, `COMPLETE`, manifest and `CURRENT` all agree, digest recomputed from disk and confirmed in a **fresh interpreter**); `promote_next_revision` chains children. A three-revision chain was verified: distinct digests, correct parent links, appended ledgers, three retained directories. |
| Verification | `ruff` clean, `mypy --strict` clean, **70 targeted tests pass**. No full `make check` — T13 is incomplete. |
| Not written | `validation/completeness.py`, `validation/run.py`. |

**The fixture caught a defect in the layer it exists to test.** A child revision's candidate digest
folds in its parent's revision number and bundle digest, so recomputing without the parent snapshot
yields a different digest, not an approximation. The check compared it anyway, which would have
reported **every revision after the first** as a candidate mismatch on the ordinary
no-deep-parse-ancestors path §20.6 requires. Revision 1 is parentless and passed happily; only the
chain exposed it.

### Two facts recorded for T14

- `yaml.safe_dump` breaks **6 of the example's 27 documents**: the restricted loader refuses the plain
  scalars it emits for `2024-09`, `+1 555 0100 EXAMPLE`, `~120 items/s`, a bare hex digest, and two
  secret-scan regexes. T14's emitter must force-quote or the bundle it writes cannot be read back.
- `required_approval_decisions` takes the parent's **documents**; `candidate_content_digest` takes its
  manifest **envelope**. Passing one where the other belongs type-checks and then fails deep inside
  `build_index`.

### Gate time

`make check` ran three times for one commit: SIGTERM'd at 38% after ~15 minutes with two subagents
reading the same tree; then ~7 minutes to 37% once they finished, killed deliberately when the docs
review showed a declined finding needed implementing; then the real run, **exit 0, 5,200 tests,
95.40%, 9m38s**. Roughly 31 minutes of gate time for one result.

### Standing

Gate A **not met**, T12 **not signed off** after three reviews, Gate B **prohibited**. This session's
work is at `d360fa6` on `main` (a concurrent session then added `1fe4033`); nothing was pushed. T13 is
on `t13-digest`, unmerged. **Next: the four D-124 fixes, in fresh context.**

## Session — 2026-08-11 (later ×4) · T12 fixed through five reviews; T13 built. No phase gate moved.

### The round-three fix and the two reviews of it (D-125)

| Item | Result |
|---|---|
| D-124's findings | **4 BLOCKING + 1 SHOULD-FIX, all fixed.** Each fix removes a restatement of the emitter rather than patching an instance. |
| Reviews of that fix | **Two, run concurrently with different lenses** — runtime-forgery hunting and design conformance. Both returned **REWORK**. |
| What both found independently | The scope-locator gap: the byte-free grammar reached record locators and stopped, so an approved scope could name a shape no heading stack resolves to, validate clean, and fail every re-enumeration. |
| What only the conformance lens found | `SourceSpec`'s docstring still claimed a home-path refusal that landed nowhere — a sentence **D-122 had already recorded as false**. |
| New findings, round 4/5 | 1 BLOCKING + 5 SHOULD-FIX + 6 NOTE across the two. **All fixed** except two deliberate declines, both recorded in D-125. |
| Forgeries that passed all four layers | **0** after the fix, over 15 hand-built cases plus ~14,000 generated sources. |
| Encoder/predicate disagreement | **0** over ~580,000 generated encoder inputs; 0 reservation collisions. |
| Schema/model agreement | **124,497 inputs, 0 divergences**; the pattern is ECMA-262-valid. |
| Stored identity changed | **None.** The only text whose encoding changed is exactly `_root`/`.`/`..`; the packaged example's one `_root/paragraph-1` is the synthetic segment, which never passes through the encoder. |

### Mutation testing

| Round | Mutations | Caught | Survivor |
|---|---|---|---|
| 1 | 20 distinct | 19 | `_MAX_HEADING_LEVEL = 5` — every assertion about the cap read the same constant it was checking |
| 2 | 28 distinct | 27 | `is_emitted_segment`'s `.`/`..` guard — the escape had made it unreachable |
| 3 | 28 distinct | **28** | — |

**Both survivors were real defects, not driver noise.** The driver now aborts on a byte-identical
duplicate before running anything, which is the check D-122's inflated "13 of 13" needed.

### T13 (branch `t13-digest`, unmerged)

| Slice | Result |
|---|---|
| Already built | `reports.py`, `validation/digest.py`, the promoted-revision fixture — 70 tests, unchanged this session. |
| Built this session | `validation/completeness.py` (§20.5, plus ancestor traversal with a typed closed-fault reason) and `validation/run.py`. **59 new tests** — 48 completeness, 30 run. |
| Branch totals | **1,389 passed**, `ruff` clean, `mypy` clean. Three commits. |
| Owner ruling applied | `METRIC_REVIEW_MISSING` **deleted**; metrics get no review interval. A metric's freshness is its required `reviewed_at` date alone. |
| Two pre-existing defects fixed | `validate_history` derived owner gates against `parent=None`, reporting **~35 spurious `missing_owner_approval` errors** on every revision ≥ 2 — `validate` was unusable on any child revision. And `parse_error_diagnostics` had no arm for `UnsupportedSchemaVersionError`, so §21's typed code surfaced as `internal_error` (the exit code was right by coincidence, which is why nothing caught it). |
| Owed | An independent review, including of the judgement call below, and a merge. |

**One T13 judgement call needs the owner's eye.** The build extended Mit's D-115 deletion ruling from
`METRIC_REVIEW_MISSING` to `MISSING_PERSON_ENTITY` and `ENTITY_STATUS_UNDECLARED`, on the grounds
that both are equally unfireable. That was **not** what was ruled on. It also added two codes,
`FACT_VALUE_EXPIRED` and `COMPLETENESS_COUNTS`, leaving the catalog the same size. Reviewable and
reversible; recorded here because a catalog is closed and versioned, so changing it is not a detail.

### Gate

| Run | Result |
|---|---|
| 1 (`1bbdaf5`'s parent) | **Failed in ~1 minute** — `generalization` R7's content pin for `career-profile.schema.json`, working exactly as designed on a one-line schema change. Not a defect; the pin is the review prompt. |
| 2 (`1bbdaf5`) | **SIGTERM at 57%, deliberately** — the head moved past it when the round-4/5 findings arrived. Exit 144 is my `pkill`, not a failure. |
| 3 (`235f30e`, the final head) | **exit 0 · 5,260 passed · 1 deselected · 95.41% · 32m58s** |

`6cd8665` is docs-only and owes `generalization` + `index-check` only (D-116); both ran green before
it was committed.

Concurrent subagents drove load average to **21** and stretched a 65-second suite to eight minutes,
which is most of why run 3 took 33 minutes. The previous session's lesson holds and was paid for
again — but the parallelism bought two full review rounds and a completed T13 in the same window.

### Standing

Gate A **not met**. T12 has every finding from five reviews fixed and is **still not signed off** —
the round-four/five fix owes its own review. Gate B **prohibited**. Nothing pushed.

---

## Session — 2026-08-11 (later ×5) · T13 merged; T14 reviewed and partly fixed; T15 and T17 built. No phase gate moved.

An overnight autonomous run against Gate A, ended early by a session usage limit that killed five
subagents within seconds of each other. Recorded in D-127.

### What landed

| Slice | Where | Numbers |
|---|---|---|
| T13 | **merged to `main`** at `c0020e8` | Two reviews, both REWORK, all findings fixed. Gate: **exit 0 · 5,416 passed · 95.61% · 9m04s**. |
| T13 follow-up | `t13-followup` `4bd3c49`, unmerged | 3 commits, **1,509 passed**, ruff + mypy clean. **Ungated.** Adds `IssueCode.CANDIDATE_DIGEST_UNVERIFIED` (closed-catalog widening). |
| T14 | `t14-storage` `d681653` built, `d441e2d` fix | Build reviewed twice, both REWORK: **4 BLOCKING, 6 SHOULD-FIX**. Fix round **1,478 passed**, ruff clean, **UNVERIFIED and ungated**. |
| T15 | `t15-rebase` `e9ab3bc`, unmerged | Built: rebase, the shared `filelock` writer lock, the backup drain. 54 new tests, **1,511 passed**. **Unreviewed.** |
| T17 | `t17-schema` `7626d32`, unmerged | Built: schema-v1 bootstrap and the migration no-op. **Unreviewed.** |
| T16 | `t16-promotion`, identical to `t15-rebase` | **Not started** — the build agent died before its first edit. |

### The measurement that matters most this session

T13's BLOCKING was verified by the orchestrating session through a probe written from the finding's
claim rather than from the fix, with a revision-1 control firing in every run: pre-fix 0, post-fix 2,
fix-mutated 0. **The control is the whole point** — without it, the pre-fix zero would read as "the
forgery failed" instead of "the check never ran". Recorded in D-127.

### The stop

Five subagents — a T14 fix round, a T16 build, a T17 review and both T15 review lenses — failed
simultaneously with `You've hit your session limit`. Capacity does not return until 09:10 CDT.

**Two costs were paid and are worth pricing.** The T14 fix agent was killed *after* its last edit and
*before* its report, leaving 13 modified files with no account of what they addressed; the work is
green and was committed rather than discarded, but the findings-to-changes mapping now has to be
re-derived from the diff, which is strictly more expensive than having been told. And four of the five
agents had produced nothing yet, so their entire dispatch was wasted.

**The lesson is about dispatch width under an unknown remaining budget, not about parallelism.** Five
concurrent reviewers each spawning nested children is a multiple of five agents' worth of usage, and
the run had no reading of how much was left. The previous session's note — that concurrency bought two
review rounds and a completed T13 — still holds; what was missing is that a wide fan-out should be
sized against remaining budget, and that an agent's work should be committed by its author at each
finding rather than in one report at the end.

### Continued after the stop — main-thread work only

Subagents were unavailable for the rest of the session, but gates and merges are main-thread work, so
the chain continued.

| Step | Result |
|---|---|
| `t13-followup` gate (main merged in first) | **exit 0 · 5,436 passed · 1 deselected · 95.64% · 9m00s** |
| `t13-followup` merged to main | `b87fa06`. T13 is now complete. |
| `main` merged into `t14-storage` | **2 conflicts, 4 test failures** — none visible from either branch's own green suite. Resolved at `9d11d03`; 1,598 passed, ruff + mypy clean. |
| `t14-storage` gate | **exit 0 · 5,525 passed · 1 deselected · 95.69% · 10m10s** |

**The merge is the measurement worth keeping.** Both branches were independently green, and merging
them was not a formality: it produced two conflicts and four failures. One conflict was two
byte-identical helpers under two names (`errors.io_reason` and a private `_why`) — the duplication class
this package has spent five review rounds on, arriving this time through parallel branches rather than
through a restated rule. **Merge `main` into `t15-rebase`, `t16-promotion` and `t17-schema` before
gating any of them.**

The T14 fix round was audited against its findings list by the orchestrating session rather than by its
author, who was killed before reporting. All four BLOCKING and the two SHOULD-FIX items checked have a
corresponding change, and BLOCKING 1 landed as **one** refusal over `ROOT_MEMBERS` rather than four
per-directory guards. The audit deliberately does not claim more than that: it did not check that each
new check has a test that fails without it, and two SHOULD-FIX items were never examined.

### Standing

Gate A **not met**: 16 of 19 slices built, 14 merged. T15 and T17 are built and reviewed by nobody;
T16, T18 and T19 are not started. T14 is integrated and **green on a full gate but unreviewed**, which
is deliberately not enough to merge — three slices inherit it. Gate B **prohibited**. **Nothing pushed.**

## Session — 2026-08-11 (later ×6) · T14 reviewed, fixed and MERGED; T15 reviewed twice and fixed; T17 reviewed. No phase gate moved.

Resumed from the dispatch queue the previous session left when it hit a usage limit. Three reviews and
two fix rounds, dispatched three wide rather than five. Recorded in D-128.

### What landed

| Slice | Where | Numbers |
|---|---|---|
| T14 | **merged to `main`** at `aff1dc0` | Round-2 review: **1 BLOCKING, 4 SHOULD-FIX**, REWORK. Fix round 5 commits, one per finding. Gate: **exit 0 · 5,534 passed · 95.73% · 11m54s**. |
| T15 | **merged to `main`** at `f74be0e` | Reviewed by **two concurrent lenses, both REWORK**: **6 distinct BLOCKING, 6 SHOULD-FIX**, none covered by its own 54 green tests. Fix round 12 commits + 1 merge fix. Gate: **exit 0 · 5,611 passed · 95.83% · 13m18s**. |
| T17 | **merged to `main`** at `27879bb` | Light review: **APPROVE**, no BLOCKING and no SHOULD-FIX in its own diff. 9 tests green post-merge. |
| T16 | `t16-promotion`, reset onto `main` | **Build dispatched later in this session.** It had been byte-identical to the pre-fix `t15-rebase` and so carried all 6 of T15's BLOCKING defects, which is why it was gated behind T15 rather than started earlier. |

Gate A is **16 of 19 slices merged**. T16, T18, T19 remain; Gate A is NOT met and Gate B stays
prohibited. **[Corrected 2026-08-12 — the sentence that stood here was the one D-133 retracted.]**
`origin/main` is `88c5857` and carries **T11** (`git cat-file -e origin/main:…/imports.py` fails);
`v0.3.0` is `dc1ffec`, whose `profile_bundle` tree has no `imports.py`, `approvals.py`,
`effective.py` or `enumerators.py`, so the wheel is **T1–T10**. **Everything from T12 onward is
unpushed.** The retraction commit `999b443` amended `DECISIONS.md` and `STATE.md` and never touched
this file — the fourth recurrence of the class D-133 named, found by the docs reviewer it recommended.

### Review yield: 7 BLOCKING and 12 SHOULD-FIX in code whose suites were green

T15's 54 tests covered **none** of its six BLOCKING. The recurring cause is not a missing test but a
test that cannot fail:

- T14's confinement check was guarded by two tests that read the same `BLOBS_DIR`/`ROOT_MEMBERS`
  constants the check reads, so both agreed `blobs/` was the blob store when the store is
  `blobs/sha256`. Replacements locate the store **by content** — the one file whose name is the
  sha256 of its own bytes.
- Three separate mutations to `inspection.py` (`:190-198`, `:412-413`, `:569-579`) left the suite
  entirely green, so two-thirds of an earlier BLOCKING fix could have been deleted silently.
- Both fix rounds were held to: revert the check, watch the test go red, restore it. T14 reported 14
  of 18 reverted checks going red before the round; all five findings pinned after.

### The orchestrator's own instruction was wrong, and was caught by testing it

The T14 fix brief specified the confinement predicate as
`path.resolve().is_relative_to(bundle_root.resolve())`. The implementing agent declined it and shipped
the stronger equality `path.resolve() == resolved_root / path.relative_to(bundle_root)`, stating why.
Verified by weakening it back: `test_a_member_that_aliases_another_member_inside_the_root_is_refused`
fails with `DID NOT RAISE`. `is_relative_to` admits a member aliasing another member **inside** the
root, under which `drafts/` resolving to `revisions/` makes `inventory` report a revision directory as
a draft. Re-running the reviewer's own probes confirmed the escape cases flip to `symlink_refused`,
the inside-root alias stays refused, and a symlinked bundle root stays correctly allowed.

### Three measurement routes that lied, all caught before being reported

1. **A gate log containing `All checks passed!` at line 7** — emitted by the lint step while pytest was
   still at 73%. Reading it as the gate's verdict is a false green. Only `GATE_EXIT` and the pytest
   summary line are the result.
2. **A backgrounded pytest reported "exit code 0" that was `tail`'s exit code**, because the command
   was piped. The real result was `3 failed, 1634 passed, 47 errors`. Backgrounded gates must end with
   `exit $ec` and must not be piped.
3. **Two worktree venvs were silently corrupted mid-session**: the `.py` files under
   `alembic/autogenerate/compare/` disappeared from `t14-wt` and `t15-wt` at the identical mtime,
   leaving `ImportError: ... (unknown location)` and pytest exit 4. **The cause was the disk being full**
   (see the ENOSPC section below); an initial attribution to `uv` hardlinking from a shared cache was
   wrong and is retracted. Repaired with `uv sync --reinstall --all-groups`. T14's gate had finished 5 minutes
   before the corruption, checked by timestamp rather than assumed, so that result stands.

**A partial `uv sync` makes it worse:** `uv sync --reinstall-package alembic` fixed alembic and pruned
the dev group, so `pytest-cov` vanished and pytest failed with `unrecognized arguments: --cov`. Use
`--all-groups`.

### T15 took THREE gate runs, and only the full gate could have caught any of it

Round 1 failed with 2 tests red at 13m45s: one was a merge resolution that put `logical_path` on
`write_bytes` instead of `quoted_yaml`, one closing paren away — suspected at the time and wrongly
dismissed on the strength of a line-based grep that cannot distinguish the two. Round 2 failed at
**lint**, in 79 lines, because moving to the qualified import made it first-party and it needed
resorting. Round 3: **exit 0 · 5,611 passed · 95.83% · 13m18s**.

The second round-1 failure is the one worth keeping. `t15-rebase`'s new test module used a bare
`from conftest import ...`, which binds whichever `conftest.py` was imported as the top-level
`conftest` module first — under the full suite that is `tests/unit/conftest.py`, so `BLOB_SHA256` was
not found. **No run of `tests/profile_bundle` alone can produce that ImportError.** It came from the
original build commit `e9ab3bc`, which means it survived both review lenses *and* the fix round — and
it had to, because all three were instructed to keep runs narrow and never run `make check`. The
review stage is structurally blind to cross-suite collisions; only the gate sees them. Every sibling
module in that directory already imported from `tests.profile_bundle.conftest`.

### The merge that reported success and then failed

`main` → `t15-rebase` produced **2 conflicts** (both in `inspection.py` and its test, neither a logic
conflict) and **4** `quoted_yaml` call sites needing repair in a file `main` never saw, which therefore
never conflicted. Measured in advance on a throwaway worktree: `Automatic merge went well`, then
`TypeError: quoted_yaml() missing 1 required keyword-only argument: 'logical_path'`.

Two traps priced for next time. **A line-based grep for the broken signature reports false positives**
— multi-line calls carry the argument on a following line, so only the suite settles it. And **a
deletion on one side must be checked for a rename on the other**: `main` had deleted a test `t15`
still carried, and "safely" keeping both would have restored the hardcoded-`.tmp-draft-abc123` test
that T14's fix deliberately replaced with one reading `DRAFT_TEMP_PREFIX` from the writer.

Also: resolving conflict markers is not resolving the conflict. Both files sat at `UU` until an
explicit `git add`, which `git status` showed and the passing test run did not.

### Dispatch economics

Three agents, then two fix rounds, against the previous session's five-wide dispatch that lost four
agents to a single usage limit. Every reviewer was briefed to **append each finding to a file the
moment it is confirmed** (a read-only agent cannot commit, so a file is its only durable artefact) and
every fix agent to **commit per finding, not per report**. Both held: the T14 reviewer had 79 lines of
confirmed findings on disk well before it reported, and the T15 fix round's 12 commits were each
independently recoverable.

### The gate that failed because the machine was out of disk

`main`'s combined gate (T14+T15+T17) died at 3730 tests with
`OSError: [Errno 28] No space left on device` — 706 MiB free on a 228 GiB volume at 100%. That is
also the most likely cause of the "venv corruption" above, which had been attributed to `uv`
hardlinking from a shared cache; **that attribution was wrong**. Files vanishing from two venvs at an
identical mtime is what disk exhaustion looks like, and the symptom surfaces wherever the next write
lands, which is why it presented as three unrelated tooling faults.

Reclaimed ~950 MiB: seven merged/stale worktrees removed (each ~165 MiB) and `uv cache prune` freeing
646 MiB across 15,339 unused files. **A worktree per slice is not free at ~165 MiB each** — remove
them as their branches merge rather than at the end of the program.

Re-run clean: **exit 0 · 5,620 passed · 95.83% · 38m18s**. The wall-clock is inflated ~3x by a build
agent running concurrently; the same gate took 11m54s and 13m18s uncontended.

### T16 built and gated, not merged (same session, later)

`t16-promotion` (crash-consistent promotion, exact-target reuse, corrupt-parent recovery), 4 commits:
**exit 0 · 5,729 passed · 95.84% · 16m12s**. **Not merged — reviewed by nobody**, and it owes two
lenses plus a concurrency pass per the effort table.

A 23-mutation sweep run one at a time: **21 RED, 1 ambiguous anchor (RED on re-run), 1 GREEN**. The
green one was a staged-tree model-by-model comparison that could not fire — the digest is computed
*from* those models, so any difference moves it — deleted per D-115 with tests pinning each half where
it lands. Digest order was checked through two independent routes, one of them promoting revision 2 on
top of a **production-promoted** revision 1.

It found two pre-existing defects. **`build_approval_stamp` generated colliding approval IDs across
revisions**: numbering restarted at `001` per stamp while §8 requires global uniqueness, so any record
approved in two revisions made the second unpromotable — which blocks §6's recapture recovery outright.
And **no `profile_bundle` module was importable first in a fresh interpreter**, invisible to pytest and
the CLI because both import `validation` early; only a bare-interpreter crash worker walked into it.

---

## Session — 2026-08-11 (later ×7) · The T14 and T15 FIX ROUNDS independently reviewed: REWORK. No phase gate moved.

Both fix rounds had been merged on the orchestrator's own targeted verification. This session gave
them the review round they never had, read-only: nothing tracked was modified, nothing committed,
nothing pushed, and `make check` was never run (a gate and a build agent held the machine at load
16–21 throughout).

**Mutation testing without touching the worktree.** `src/` was copied to a scratchpad directory and
selected with `PYTHONPATH`, so each reverted check ran against a copy while the shared worktree
stayed clean. The driver restores the pristine file from the repo before every case, asserts the
anchor is present *and unique*, and asserts the edit was not a no-op — a no-op replacement and a
passing check are indistinguishable otherwise. `git status` was `?? docs/superpowers/` before,
during and after.

**16 of 16 mutations RED**, each caught by exactly the test written for it and by no other:

| Round | Mutations | Result |
|---|---|---|
| T14 | 4 (store path, store entries, the equality, the second `selection = None` arm) | all RED |
| T14 | 1 (the predicate reverted to `is_symlink()` over the same *set*) | GREEN — an equivalence, not a gap |
| T15 | 11 (backup-root symlink, both deletion arms, the `ValidationError` translation, the append-only dispatch and each of its two refusals separately, the collision raise, both draft-name caps, the lock message) | all RED |

So the round's stated question — *does every new check have a test that fails without it?* — is
answered **yes for both rounds**. The three new T14 tests find the blob store by hashing every file
under the root and keeping the one whose name is its own sha256, so they read no constant the check
reads. That is the fix for "a test derived from a constant agrees with itself", done properly.

**What the round still found: 1 BLOCKING, 5 SHOULD-FIX, 4 NOTE.** All are in `STATE.md`'s blocker
table with `.agent/T14-T15-FIXROUND-REVIEW.md` as the evidence. The blocking one is the
transferable lesson:

> **A fix verified only against the reviewer's own reproduction closes the arm the reproduction
> used.** T15's append-only ledger merge is correct, and `_merge_plan` reaches it only when the
> selected revision *also* touched the ledger — which is the arm Lens A's probe happened to
> exercise. For `conflicts/rulings.yaml` the other arm is the ordinary case, and there a draft that
> drops an inherited ruling installs at exit 0 with no diagnostic. Re-running the reviewer's probe
> could not have found this; driving `_merge_plan` directly, with the three append-only documents
> enumerated from `_APPEND_ONLY_SEQUENCES` rather than from the probe, did.

Its mirror, found the same way: the fix's *positive* test —
`test_the_rebased_draft_carries_the_selected_revisions_ledgers_as_a_prefix` — survives deleting the
entire fix (mutation T15-M5), because an untouched draft ledger merges identically either way. The
suite pins the two refusals and not the property they exist to protect, which is precisely why the
property being false on the common path went unnoticed.

**Two probe-hygiene facts worth carrying.** A probe whose "edit" was `model_copy(update=...)` on a
field the model does not have changed nothing and reported "no refusal" — a probe agreeing with
itself; it was caught only because every case carried a negative control. And a FIFO in the blob
store made `inventory` hang: 5.5 minutes elapsed against 2.4 s of CPU, `sample` showing the main
thread parked in `__open`. **No output is not a pass** — the elapsed-versus-CPU check is what
distinguishes a hang from a slow machine.

**Measured cost of the T14 fix, recorded because `perf` is a CI job `make check` never runs:**

| blobs in the store | `require_confined_root` |
|---|---|
| 0 | 2.9 ms |
| 100 | 63.8 ms |
| 1,000 | 503.4 ms |
| 5,000 | 3,366 ms |
| 20,000 | 8,738 ms |

Upper bounds (load average 16–21), but linear in the store, on every command that resolves a
selection. `is_symlink()` over the same 5,000 entries: 296 ms against 1,800 ms for the equality.


## Session — 2026-08-11 (later ×8) · The T14/T15 fix-round findings FIXED; T16 reviewed by three lenses. No phase gate moved.

**Gate A: still 16 of 19 slices merged. Gate A NOT met; Gate B stays prohibited.** Nothing was pushed.

### What was fixed on `main` — six commits, one per finding, each with a test that fails without it

The independent review of the T14 and T15 fix rounds (D-130 recorded it as OWED; it returned REWORK
with 1 BLOCKING + 5 SHOULD-FIX) is now discharged. Detail in **D-131**.

| Finding | Closed by |
|---|---|
| BLOCKING: `_merge_plan` short-cut bypassed the append-only merge | one condition, reading `diff`'s own mapping |
| symlink loop escaped uncaught | refusal stated over `is_symlink()`, which every interpreter agrees on |
| `record_ids: []` on a 12-record document | IDs attached at the raise site |
| a draft name `inventory` prints that no command accepts | addressing uses the segment grammar; creating keeps the short cap |
| one `realpath` per stored blob per command | one `lstat` per entry |
| a FIFO in the store blocked `open()` forever | the same `lstat` refuses a non-regular entry |

Suite after the fixes, on `main`: **1,697 passed** (`tests/profile_bundle/`), ruff clean, mypy
`--strict` clean on 245 files. The combined `make check` was deliberately deferred to the integration
branch — see the process note below.

### The interpreter divergence, measured

`Path.resolve()` on a self-referential symlink, same code, same input:

| CPython | behaviour |
|---|---|
| 3.11.14 | raises `RuntimeError` |
| 3.12.12 | raises `RuntimeError` |
| 3.13.12 | returns the loop's own path — which **satisfies** the confinement equality |

CI runs all three. The local venv was 3.12, so the first version of this fix passed here and would
have gone red in CI; on 3.13 the loop was not merely misreported but **admitted**. Found only because
a fresh worktree resolved a different interpreter than the repo's own venv.

### Confinement cost, before and after, at the same load

The previous session's figures were taken at load average 16–21 and flagged as an upper bound. Both
predicates re-measured on this machine at **load 3.1**, minutes apart, the pre-fix one restored into a
copy of `src/` selected by `PYTHONPATH`:

| blobs in the store | `resolve()` per entry | one `lstat` per entry |
|---|---|---|
| 100 | 4.9 ms | 2.3 ms |
| 1,000 | 46.1 ms | 19.5 ms |
| 5,000 | 240.0 ms | 101.2 ms |
| 20,000 | 975.8 ms | 430.3 ms |

**Two corrections.** The gain is **2.3×**, not the ~6× the review estimated — that figure came from a
micro-benchmark of the two predicates alone, and end to end they sit inside a walk they share. And the
same *pre-fix* code costs 976 ms at 20,000 blobs here, not 8.7 s: the earlier absolutes were inflated
about ninefold by load. A figure taken under one load and compared against one taken under another is
not a comparison.

### T16 reviewed by three lenses — REWORK, REWORK, APPROVE (D-132)

| Lens | Verdict | BLOCKING | SHOULD-FIX | NOTE |
|---|---|---|---|---|
| adversarial runtime | REWORK | 1 | 3 | 4 |
| design conformance | REWORK | 1 (the same one) | 3 | 5 |
| concurrency and real crashes | **APPROVE** | 0 | 1 | 14 |

T16's own gate had been **exit 0 · 5,729 passed · 95.84% · 16m12s** with a 23-mutation sweep behind
it. **Both independent lenses found the same BLOCKING separately** — `_parent`'s `if not quarantined:`
disabling the entire parent digest recomputation — which the slice's own test for that exact scenario
could not see, because it edits a ledger that a different check catches without blob bytes at all.

The concurrency pass is the cheapest and most durable of the three: 20 write boundaries **enumerated
from `promotion.py` rather than from the author's test list** (seven more than the tests name), a real
`SIGKILL` at each against a fresh bundle, 10 two-promoter races and 5 three-way races. Its negative
control is what makes the result mean anything — the same kills against a mutant with steps 7 and 8
swapped leave `current_pointer_mismatch`, and a reader hammering across that mutant reported **690 bad
reads of 842** against **0 of 148** on the real thing.

### Process — one gate instead of four

`main`'s fixes, T16 and T18 were put on one integration branch (`t18-cli`) rather than gated
separately. The merge of T16 onto the corrected `main` was verified at **1,806 passed**, ruff and mypy
clean, on Python **3.13**, before any T18 work began — so the base is known-good independently of what
T18 does to it. `make check` is ~13 minutes and CPU-bound; four of them is an hour of wall clock spent
re-proving the same tree.

The T18 build worktree is deliberately left on **3.13** while the repo's venv is 3.12. A worktree on a
different matrix entry is free cross-version coverage for a gate that otherwise only ever runs one,
and it has already paid for itself once today.


### Late in the session — the numbers the record above was written without

| Branch | Result |
|---|---|
| `t16-promotion` (T16 + its 11-commit fix round, `735dfe7`) | 1,822 passed · ruff · mypy `--strict` clean. **`make check` NOT run.** |
| `t18-cli` (main's fixes + T16 **as built** + T18's 9 commits, `d64af3c`) | **`make check` GATE_EXIT=0 · 5,811 passed · 1 deselected · 95.55% · 16m08s** |

So `main`'s eight fix commits are gate-verified, through `t18-cli` rather than on `main` itself.
**T16's fix round is not in that gate** — `t18-cli` merged T16 before those commits existed. Re-merge
and re-gate; that is the one number this session did not get.

Read from `GATE_EXIT` and the pytest summary. `All checks passed!` appears early from the lint step
while pytest is still running and is not the verdict — the trap held again on this run.

---

## Session 2026-08-12 (03:10 unattended) · the final Gate A integration gate — exit 0 · 5,906 passed · 95.63%. No phase gate moved.

Recovered, not re-run: the gate the 01:38 session started outlived it. Detail in D-135, evidence at
`.agent/GATE-A-FINAL-GATE.md`.

| Field | Value |
|---|---|
| Branch / sha | `t18-cli` **`a64e6fa`** — all nineteen Gate A slices |
| `GATE_EXIT` | **0** |
| pytest | **5,906 passed · 1 deselected · 1,465 warnings** |
| Wall clock | **1002.17s (16m42s)** |
| Coverage | **95.63%** — 16,125 stmts · 562 miss · 4,478 branch · 311 partial |
| Interpreter | **Python 3.13.12** (repo venv is 3.12 — deliberate cross-version coverage) |
| generalization · index-check · ruff · mypy `--strict` | OK · current · passed · 248 files clean |

Gate progression across the three integration gates:

| Sha | Carries | Result |
|---|---|---|
| `e4d79aa` | everything except both fix rounds' late work and T19 | exit 0 · 5,831 passed · 95.59% · 18m26s |
| `d64af3c` | main's fixes + T16 **as built** + T18's 9 commits | exit 0 · 5,811 passed · 95.55% · 16m08s |
| **`a64e6fa`** | **all 19 slices** — adds T16's 11-commit and T18's 10-commit fix rounds, `t19-contract`, `t16-validate-quarantine`, the `digest.py` fix, the rewritten CHANGELOG | **exit 0 · 5,906 passed · 95.63% · 16m42s** |

**`main` is not an ancestor of `a64e6fa`** — three docs-only commits (`26176c9`, `e30da5e`,
`d3a3127`) sit outside this gate and owe only `generalization` + `index-check` under D-116. Every
line of Gate A **code** is inside it. `t18-cli` is 48 commits ahead of `main`; `main` is 3 ahead.

**A green gate is not a review.** Gate A remains NOT met: T18's fix round is unreviewed, the
authoring guide is unwritten, T19's docs-only reviewer has not run, and `evidence_link_asymmetry`
awaits Mit. This session added **no** review evidence and no new precision evidence.


## Session — 2026-08-12 (working session) · T18 reviewed by two lenses and fixed; all nineteen slices merged into one tree. No phase gate moved.

Detail in D-134 (the tier ruling), D-135 (the gate) and D-136 (the T18 review, its fix round and the
integration merge). This session merged the last four branches into one tree and measured it once.

### The gate, and the two before it

| Tree | What it carried | Result |
|---|---|---|
| `d64af3c` | main's fixes + T16 **as built** + T18 | exit 0 · 5,811 passed · 95.55% · 16m08s |
| `e4d79aa` | + T16's 11-commit fix round + the merge resolution | exit 0 · 5,831 passed · 95.59% · 18m26s |
| **`a64e6fa`** | **+ T18's 10-commit fix round + T19 + the `digest.py` fix — all nineteen slices** | **exit 0 · 5,906 passed · 1 deselected · 95.63% · 16m42s** |

Read from `GATE_EXIT` and the pytest summary, never from the `All checks passed!` the lint step
prints early. Python 3.13.12 throughout. The middle run took **18m26s against 16m42s for a larger
tree** — three subagents were contending for CPU, which is the measurable cost of parallelising
around the gate rather than a property of the suite.

`main` is **not** an ancestor of `a64e6fa`; it carries docs-only commits the gate did not see, which
per D-116 owe `generalization` + `index-check` rather than a full gate.

### Review

| Slice | Lenses | Verdict | Findings |
|---|---|---|---|
| T18 | adversarial-runtime | REWORK | 1 BLOCKING · 4 SHOULD-FIX · 2 NOTE |
| T18 | boundary / tailor | REWORK | 1 BLOCKING · 3 SHOULD-FIX · 1 ruling · 2 NOTE |

Each lens found a BLOCKING the other did not, and **both independently upheld** the uniform JSON
envelope while ruling §19's design text wrong. The fix round was **10 commits**, one per finding,
each quoting its red-without-fix output; four findings were declined with arguments, two of which Mit
accepted.

**The review loop is NOT closed.** D-126 ends a slice's loop when a round finds no BLOCKING that is
either a silent identity/data-integrity fault or a legitimate input the system refuses. Both lenses
found exactly that, so T18's fix round owes its own independent review — as T14's, T15's and T16's
each did, and **every one of those found something the fixer missed**.

### What one fix measured that no reviewer reported

Threading `quarantined=` into `validation/digest.py` closed lens A's T16 finding 2. Mutation-checking
it against a `PYTHONPATH`-selected copy of `src/` showed the gap had **two** arms, not one: besides
the silently-unreported forgery under a *missing* blob, the pre-fix code **accused an untampered
revision of forgery** when the blob was digest-mismatched — telling an owner on the supported
recapture path that their revision had been tampered with. Four scenes, two of them previously wrong.

### Cost

`STATE.md` at 313 lines against a ~170 target. Disk fell 39 GB → 19 GB across five concurrent
worktrees and their venvs (~600 MB each with dependencies, not the ~165 MB the tree alone costs);
reclaimed on merge. One gate was killed at 42% and restarted because an agent committed a tenth
commit after nine had been merged.


## Session — 2026-08-12 (later) · Gate A's review loop CLOSED at round five; all four gates green. No phase gate moved.

Detail in D-137. This session ran the last two review rounds, fixed everything they found, wrote the
authoring guide, and established CI equivalence for the first time on this track.

### The final tree, against the whole CI surface

`t18-cli` **`17574c3`** — all nineteen slices plus five rounds of fixes.

| Gate | Result |
|---|---|
| `make check` | **exit 0** · 5,913 passed · 1 deselected · 95.59% · 16m35s |
| `gitleaks` (`origin/main..t18-cli`) | exit 0 · 144 commits · no leaks |
| `gitleaks` (`origin/main..main`) | exit 0 · 101 commits · no leaks |
| `perf` (CI-only) | exit 0 |

Gate progression across the session, each read from `GATE_EXIT` and the pytest summary line:

| sha | passed | coverage | elapsed |
|---|---|---|---|
| `a64e6fa` | 5,906 | 95.63% | 16m42s |
| `08967e6` | 5,907 | 95.60% | 17m28s |
| `60218ac` | 5,912 | 95.59% | 16m33s |
| **`17574c3`** | **5,913** | **95.59%** | **16m35s** |

Every increment is accounted for: +1 the torn-write test, +5 the closing-review fixes' arms, +1 the
inventory drain. A test count that moves by an unexplained amount is the cheapest available signal
that something else changed.

### Review yield, five rounds on one slice

| Round | Scope | Verdict | BLOCKING | Other |
|---|---|---|---|---|
| 1 | T18 build, adversarial-runtime lens | REWORK | 1 | 4 SHOULD-FIX · 2 NOTE |
| 2 | T18 build, boundary lens | REWORK | 1 | 3 SHOULD-FIX · 1 ruling · 2 NOTE |
| 3 | T18's 10-commit fix round | REWORK | 1 | 1 SHOULD-FIX · 3 NOTE |
| 4 | the 2 fix-of-fix commits | REWORK | 2 | 2 SHOULD-FIX · 1 NOTE |
| 5 | the 4 closing commits | **APPROVE** | **0** | 4 SHOULD-FIX · 1 NOTE |
| — | T19 guide, docs-only | **APPROVE** | **0** | 3 SHOULD-FIX · 2 NOTE |

**Every round found a defect in the round before it.** Rounds 1 and 2 shared no findings, which is the
argument for concurrent lenses rather than sequential rounds. Round 5's mutation table is the durable
artefact: **11 of 12 red**, and the one green was a pin that asserted everything about a diagnostic
except the field a consumer branches on.

### Two docs reviews, and what they cost

A docs-only reviewer against this session's own records found **1 BLOCKING + 5 SHOULD-FIX + 2 NOTE**
against **66 claims verified TRUE**. Its BLOCKING was the fourth recurrence of the class D-133 named:
the claim D-133 retracted was still asserted as fact in `METRICS.md`, because the retraction commit
amended `DECISIONS.md` and `STATE.md` and never touched this file. The guide's reviewer verified 37
claims and confirmed all seven the author had disclosed as unreproduced — finding a named constant
(`blobs.MAX_REVISION_EVIDENCE_BYTES`) the author had searched for and missed.

### Corrections this session made to standing facts

- **The CI-only job count is two, not three.** `make check` runs `generalization` (`Makefile:2`), the
  identical command CI runs. STATE had said three for as long as D-117 has existed.
- **The YAML `!!`-tag content-addressing bypass is CLOSED**, not open. Verified by probe (`!!omap`
  duplicate-key smuggling and `!!python/object/apply` both refused) and by mutation: disabling the
  guard turns 12 tests red. The memory entry calling it an OPEN BLOCKER was stale.
- **`DATA_SUFFIXES` has eleven members**, not four, so D-116's cheap-pair discount applies to `.md`
  but not to `.toml`, `.txt` or `.tex`.

### Cost

Three commits were made *before* reading a check's exit code — one shipped an absolute `$HOME` path
into a tracked file, one a stale index, one a ruff failure. All three were caught and fixed in a
follow-up, and the habit changed to putting the commit inside an `if` guarded by the check. `STATE.md`
is 332 lines against a ~170 target. Six worktrees were live at peak; disk fell 39 GB → 19 GB and was
reclaimed as branches merged.

---

## Session — 2026-08-12 (bonus window) · Gate A MERGED into main; two silent-success defects found and fixed after it. No phase gate moved.

Detail in D-138 … D-142. The session Mit asked to spend on "anything extra we could/should be doing"
after the Gate A checkpoint. It merged the track, then went looking for defects in it and found two.

### Gate A merged, and all four gates re-run on the result

`main` `70a6d76` — nineteen slices, five review rounds, plus this session's three fixes.

| Gate | Result |
|---|---|
| `make check` | **exit 0** · 5,919 passed · 1 deselected · **95.65%** · 16m22s |
| `gitleaks` (`origin/main..HEAD`) | **exit 0** · 165 commits · no leaks |
| `perf` (CI-only) | **exit 0** · top-path 0.245–0.268 s |
| acceptance (`.agent/gate-a/acceptance.sh`) | **8 PASS / 0 FAIL**, re-run after the fixes |

The integration merge moved only three `.md` files relative to the already-gated tree, so it owed
`generalization` + `index-check` (D-116) — both green. **Gate A is still NOT met**: the merge is done,
and the only remaining item is Mit's `evidence_link_asymmetry` ruling.

**The test count is accounted for end to end**: 5,913 → +2 → +1 → +3 = **5,919**. Coverage 95.59% →
95.65%.

### Two defects, both "no flags" standing in for cleared

- **A mistyped `--bundle` had four different answers, and `inventory`'s was `clean` at exit 0** (D-138).
  Three commands mis-explained it as `no_current_revision`; `promote` said `draft_not_found`. Now
  `bundle_not_found` on all twelve, exit 1.
- **A FIFO in place of a bundle document hung `validate --draft` and `promote` forever** (D-141),
  `promote` while holding the bundle lock. Measured at `timeout 20` → **exit 124, no output**; after
  the fix, exit 1 in about a second. This was the **third and last** site of that class. The defect
  underneath it: `discover_source_files` classified entries by elimination, so its last branch made
  every filesystem object nobody had thought of into a document.

### The review of this session's own fix: REWORK, and what it caught

**1 MAJOR · 3 MINOR · 0 BLOCKING · 7 checks clean.** Numbers worth keeping:

- **The fix reached 8 of 12 commands and claimed 12.** `add-evidence`, `resolve-conflict` and `approve`
  take mandatory click `FILE` arguments, so the author's probe died at argument parsing before reaching
  the bundle; `validate --draft` answered through a different function. **A probe that cannot reach an
  arm prints the same nothing as an arm that passes.** The claim shipped in the code, in D-138 and in
  `STANDING-FACTS.md` before it was corrected (D-142).
- **1 of 5 mutations came back GREEN**, and it mattered: `is_dir()` weakened to `exists()` left
  **1,954 tests passing** while restoring the original defect for a regular-file root. Both of the
  fix's new tests had used a *nonexistent* path.
- **1 of 5 was a behavioural no-op**, which is its own finding: `STATE_REFUSAL_CODES` has **no
  production reader**, so all thirteen memberships are documentation.
- **An unclaimed fix**: at the parent, a symlink loop at the root escaped as `RuntimeError` past every
  handler, **leaking an absolute path**.

### `STATE.md` cut 340 → 149 lines (D-139)

Its own header asked for ~170 and it was double that, which is *why* three of its rows had gone false
(T18's fix round recorded as unreviewed after five rounds closed it; the guide as unwritten after it
was written and reviewed; a gate cited against a superseded sha). The 168 lines of reference material
moved verbatim to `docs/program/STANDING-FACTS.md`, six sections behind a "read this before touching X"
table — D-108's pattern, third application.

### Corrections this session made to standing facts

- **D-116's premise was false and its conclusion survives** (D-140). Two tests *do* read the real
  `docs/` tree — `test_real_tree.py` asserts `run(REPO_ROOT) == []`, and `test_program_index.py`
  asserts the index checker exits 0 there. Each asserts exactly what one of the two owed commands
  asserts, which is the real reason the docs-only discount is sound. The expiry condition is now one
  you can grep for.
- **D-138's "across the surface" is corrected to eight of twelve**, and the refusal is documented as
  living at **three** sites rather than one.

### Cost, and two process failures

- **A bullet count is not a diff.** The `STATE.md` split's commit message claimed "nothing was dropped
  — 140 → 174 bullets" and had lost one fact; the seven added masked it. `comm -23` over normalised
  bullet leads found it immediately, with no false positives. The claim was retracted in the commit
  that restored the fact.
- **A read-only review lens has no write tool.** It was briefed to append each finding on confirmation,
  which was unfollowable; it ran **56 minutes with nothing on disk**, and D-138 shipped citing a report
  path that did not exist. The orchestrator transcribed the findings afterwards.
- One gate was started speculatively beside the running reviewer and had to be killed at 58% when the
  review returned REWORK; under that contention it was running at roughly half speed (58% in 37
  minutes, against 16m22s for the whole run once alone). The re-run is the one recorded above.
- The `EXIT=0` read off a piped `head` recurred once more, in a doc transcript. Re-measured unpiped.

---

## Session — 2026-08-12 (continuation) · **Gate A MET.** Its last open question ruled and built (D-143), the track PUSHED, and the Windows matrix taken from never-ran to green (D-145).

Two owner rulings at session start, both acted on: `add-evidence` writes the back-citation (D-143),
and the unpushed track goes to `origin/main`.

### The push, and what it revealed

`88c5857..8c3dd9f` pushed after re-running `gitleaks` over the range (exit 0, captured **unpiped** —
the first attempt read `$?` through a pipe and, in zsh, `${PIPESTATUS[0]}` is empty so it reported
`tail`'s code). The remote answered **"Bypassed rule violations — 6 of 6 required status checks are
expected"**: it went straight to `main` past branch protection, so CI ran *on* `main` rather than
gating the push.

CI then failed on **all three Windows jobs** while macOS and Linux passed. `os.geteuid` does not exist
on Windows and three `@pytest.mark.skipif(os.geteuid() == 0, …)` decorators evaluate at import, so
collection raises before any test runs; two further calls sat in test bodies. `88c5857`, the previous
remote head, was green, so this entered with the Gate A range and **no local `make check` on macOS
could ever have seen it**. Fixed in `32a109f`; necessary and **provably not sufficient to
declare Windows green**: the completed job log reads `1 deselected, 2 errors in 14.96s`, so collection
aborted and **no test has ever executed on Windows in this range**. Removing the blocker is what lets
CI find out; only CI can.

### Gates

| Gate | Result |
|---|---|
| `make check` @ `cc489ac` | **exit 2** · 5,925 passed · **1 failed** · 16m34s |
| `make check` @ `cd76bb8` | **exit 0** · 5,928 passed · 1 deselected · 16m35s |
| `make check` @ `7038989` (final) | **exit 0** · 5,930 passed · 1 deselected · **95.65%** · 16m23s |
| `gitleaks` (`origin/main..HEAD`) | **exit 0** · no leaks, captured unpiped |
| CI on the pushed `8c3dd9f` | **9 of 12 green** · the three Windows jobs error at COLLECTION |

The red gate is the point: the failing test was `test_add_evidence_records_the_capture_and_revalidates`,
which asserts the revalidation's code set **whole**. The change was developed against the authoring
tests, which pass either way. **A behaviour change verified only by the test file the commit itself
edits ships red.**

### Review: three lenses, two REWORK

Design conformance **CONFORMS** (§12 quoted verbatim; §19 silent on whether `add-evidence` may write
other records, so the change is the more faithful reading). Docs accuracy **REWORK**: a console
transcript whose evidence ID and supported fact disagreed — it was real CLI output, from a record whose
own naming was inconsistent — plus two sites still describing the old two-document behaviour, the
six-mirror-sites pattern again. Adversarial runtime **REWORK**, and it earned its 22 minutes:

- The **"twelve fact-bearing documents" claim was not test-locked.** A hard-coded four-class list
  passed all 98 tests that reach `add_evidence` while covering **5 of 13** documents. D-142's shape,
  inside the fix that cites D-142.
- The **write order was wrong**, and its comment argued the wrong case at length. Manifest-last gave
  every citing document a failure position carrying `evidence_set_digest_mismatch`.
- **D-144**: grounding checks read `evidence_ids` raw, so a contextualizing source satisfied a
  predicate's evidence contract. Predates D-143.

### Mutation results

| Mutation | Outcome |
|---|---|
| back-citation disabled entirely | **caught** (6 failed) |
| only `supports` linked | **caught** |
| write order: records before manifest | **caught**, by the test added for it |
| gates ignore the record documents | **caught** |
| document catalog hard-coded to four classes | **caught**, by the test added for it — and by nothing else |
| `supports` filter removed from grounding | **caught**, one test per arm |
| **fact/metric prefix filter removed** | **SURVIVED — 29 passed** |

The survivor is a real finding and is owed a deletion: the filter cannot change behaviour, because
fact-bearing documents hold only `fact.*` IDs and the metrics document only `metric.*`. Two
independent readings agree it is inert.

### The Windows matrix, once it could run at all

Pushing exposed that **no Gate A test had ever executed on Windows** — collection aborted on
`os.geteuid` for ~180 commits. Behind that: ~130 failures, one line causing about a hundred
(`conftest._seal_revision` writing `CURRENT`/`COMPLETE` with `write_text`, whose `\r\n` no byte-exact
reader accepts; production writes binary and was never affected). Full account in D-145.

| Class | Count | Fix |
|---|---|---|
| `current_pointer_mismatch` cascade | ~100 | `write_bytes` in the fixture |
| `signal.SIGKILL` absent | ~30 | module skipped (`promotion_crashes`) |
| `os.mkfifo` absent | 2 | skipped, matching the guard the third already had |
| mode-bit denial | 1 | skipped |
| path separator in a test helper | 1 | `as_posix()` — introduced this session |

**Closed: CI is green on all twelve jobs (`8475319`).** Two fix rounds, ~130 → 2 → 0.

| Round | Windows result |
|---|---|
| before | `1 deselected, 2 errors` — collection aborted, **no test ran** |
| after `dbb57ef` | 5,881 passed · 47 skipped · **2 failed** · 1:05:37 |
| after `f8d89e6` | **5,883 passed · 48 skipped · 0 failed · 1:18:03** |

The Windows suite is ~4–5x the 16-minute local gate. Slow, not hanging — worth knowing before reading
a long Windows job as a hang. Both round-two survivors repeated classes already fixed once, which is
why that round converted **all eighteen** marker/pointer writes rather than the one that failed: the
passing sites were the dangerous ones, taking a byte mismatch from CRLF instead of from the defect
they were written for.

### Cost

- A `git checkout --` inside a mutation loop **restored `authoring.py` to HEAD and silently wiped
  three uncommitted fixes.** The next test run caught it. Commit before mutating, or mutate a copy —
  the copy is what the later D-144 mutation used.
- One gate (`ffb5f46`) was killed at 38% when the review superseded the tree it was testing.
- `set -- $spec` does not word-split in zsh, so a probe over four files failed four times before the
  shape was recognised. Second time this trap has cost a measurable amount.

---

## Session — 2026-08-12 (P3 slice 5, task 7) · Records, retractions, and the gate — GATE_EXIT=0. No phase gate moved.

Task 7 of P3 slice 5 (LLM lane-death): PROGRAM.md's item 10 retracted, D-146 appended, the
`max_calls_per_run` docstring corrected, STATE.md and CHANGELOG.md updated, and the full gate run
against the merged tree.

### What was measured

The full gate (`make check`) was run against `ba13dea` (the merge of all six code tasks into
`p3-slice5-llm-lane-death`) **plus** this task's pending document edits (`CHANGELOG.md`,
`docs/program/DECISIONS.md`, `docs/program/PROGRAM.md`, `docs/program/STATE.md`,
`src/boardwatch/core/settings.py`) already in the working tree when it ran — the `src/` docstring
change is gated by this run, correctly.

| Gate | Result |
|---|---|
| `make check` @ `ba13dea` + pending doc edits | **exit 0** · 5,975 passed · 1 deselected · 1494 warnings · 18m28s (1108.34s) |

A first attempt at this same gate raced its own `make reindex`: `make check` was launched in the
background while `docs/program/DECISIONS.md`'s index row for the newly-appended D-146 was still
being corrected by a concurrent `make reindex`, so `index-check` read a stale row mid-write and the
gate exited 2 on `index-check` alone (`generalization: OK` had already passed; `lint`/`type`/`test`
never ran). Not a code defect — a self-inflicted ordering error, fixed by finishing every document
edit and running `make reindex` to completion *before* launching the gate a second time, cleanly,
which produced the exit-0 result above.

### Discrepancy between the task-7 drafts and the provider evidence

The pre-written D-146 draft text repeated the design spec's §5.1 justification that "Anthropic
returns 403 for both `billing_error` and `permission_error`." Provider-error-body research completed
after the drafts were written (`.superpowers/sdd/2026-08-12-p3-slice5-llm-lane-death/provider-error-bodies.md`)
reconfirmed, by quoting Anthropic's own current error-codes documentation in full, that `billing_error`
is paired with **402** and `permission_error` with **403** — two types on two different statuses, never
both on 403. The code was already corrected in-slice (`a7b504e`, `185a66b`); D-146 as committed
states the corrected mapping and records that the spec's stated justification was falsified during
implementation, replacing it with the true justification (`error.type` is the provider's own typed
signal; HTTP status is a coarser channel an intermediary can rewrite). D-146 also records three things
the drafts did not cover: the accepted Azure false-latch (owner-gated, not fixed), `credit_balance_exhausted`
added additively alongside `insufficient_quota`, and the `lane_dead` out-of-catalog tripwire in
`run_funnel.py` (unreachable today, verified via `pipeline/runner.py:522-529`; whoever wires Tier B
into the pipeline owes the catalog row and its test in the same change). No other discrepancy found
between the drafts and the files they described.

---

## Session — 2026-08-12 (later still ×2) · Slice 5 pushed (`8c1b78f`); `d147-residuals` built, gated, reviewed — unmerged. No phase gate moved.

P3 slice 5 (D-146) shipped and is **pushed**: `origin/main` is `8c1b78f`, 21 commits. Its four
residuals are D-147.

### Gates measured

| Gate | Result |
|---|---|
| `make check` on the merged tree | **exit 0** · 5,975 passed · 1 deselected · 18m28s (1108.34s) |
| `make check` after the final fix wave | **exit 0** · 5,978 passed · 1 deselected · 17m30s (1050.11s) |
| `gitleaks git --log-opts=origin/main..HEAD` | **exit 0**, captured unpiped |

The same suite took **38m21s** when a second agent was competing for CPU, against ~17-18m alone —
worth recording once: the gate is CPU-bound, so parallelising around it roughly doubles it.

### CI on `8c1b78f` (run 31663735766) — still running at session end

**Do not read this as green.** At the moment of writing, 9 of 12 jobs had completed success:
`generalization`, `gitleaks`, `perf`, and all six macOS/Linux test jobs (3.11/3.12/3.13 × macos/ubuntu).
The three Windows jobs were still `in_progress`, consistent with their known ~1h18m runtime.

One CI fact worth keeping: the previous run, on `428ec76`, failed `test (3.12, ubuntu-latest)` with
`curl: (22) The requested URL returned error: 503` — an infrastructure fault on a download step, not a
code defect. That same job **passed** on `8c1b78f`, confirming the diagnosis.

`main` carries one unpushed commit (`0134632`, docs-only), held deliberately so it would not start a
second CI run while the first was in flight.

### `d147-residuals` — built, gated, independently reviewed, unmerged

Worktree `../bw-wt/d147`, four commits (`8a71064`, `01086e3`, `86a0632`, `95f3125`), based directly on
`main`'s head so the merge is a fast-forward. It closes D-147's R1/R2/R3 and adds D-148 and D-149.

| Gate | Result |
|---|---|
| `make check` on `d147-residuals` | **exit 0** · 5,979 passed · 16m47s |

R4 stays open by choice: the real fix is a shared frozen `DropReason` catalog read by both
`tailor/rewrite/lane.py` and `reports/run_funnel.py`, ~13 call sites, deserving its own decision.

The independent review of that branch found one Important defect, since corrected in `95f3125`:
D-149 asserted that `cited_back` was recorded nowhere but `STATE.md`. A re-run grep returned two
external records — `docs/profile-bundle-authoring.md:631` and `STATE.md:130` — the first present at
the branch's own base. The ruling was unaffected (findings 1 and 2 hold, and `CHANGELOG.md` genuinely
has zero hits, so the owed CHANGELOG bullet is real), so only the claim was narrowed. It also graded
its own mutation evidence honestly: one of three arms was masked by a pre-existing assertion that
trips first, so it proved nothing about the new line.

No phase gate moved this session. P3's gate is still NOT MET.

---

## Session — 2026-08-12 (D-147 residuals) · R1, R2, R3 closed — GATE_EXIT=0 · 5,979 passed. No phase gate moved.

D-147's residuals from P3 slice 5. R1 (the durable-ledger defect in `tailor run --tier-b`), R2 (a
README over-claim) and R3 (the `ARTIFACT_VERSION` comment, which also mis-cited D-031) are closed as
D-148. R4 stays open by choice. The `STATE.md` trim was attempted, found blocked, and recorded as D-149.

### The gate

Run against `0134632` plus this session's working-tree changes to `src/boardwatch/reports/tailor.py`,
`src/boardwatch/cli/tailor_cmd.py`, `src/boardwatch/reports/run_funnel.py`,
`tests/unit/test_tailor_cmd_tier_b.py` and `README.md`.

| Gate | Result |
|---|---|
| `make check` @ `0134632` + the source changes | **exit 0** · 5,979 passed · 1 deselected · 1511 warnings · 16m47s (1007.36s) |
| `make generalization index-check` (the document edits) | **exit 0** · `generalization: OK`, both indexes current |

**5,978 → 5,979 is exactly the one test added** (`test_unclassified_provider_failure_keeps_the_run_ok`).
The count reconciles against slice 5's 5,978; it was not read as "about the same".

The document edits were made *after* the gate was launched, so its `index-check` read the pre-append
tree — `generalization`, `index-check`, `ruff` and `mypy --strict` (249 files) had all passed before
`pytest` started. Rather than infer the doc edits were covered, they were gated separately by the two
fast checks D-116 assigns to a `*.md` diff, and that exit code is reported as its own row above. This is
the same trap as slice 5 task 7's first attempt, approached from the other side: there the gate raced a
concurrent `make reindex`; here the edits simply landed behind it. **Finish every document edit and run
`make reindex` to completion before launching the gate.**

### Mutation testing — three arms, each against the assertion meant to catch it

The fix's claim is that the ledger row and the exit code cannot disagree. A test asserting only that a
`runs` row exists would pass against the defect, so each arm was mutated and the catching assertion
recorded:

| Mutation | Caught by | Result |
|---|---|---|
| `status=RUN_OK` unconditionally — literally the pre-fix code | the new `RUN_FAILED` assertion | **caught**, reproducing the defect verbatim: `assert 'ok' == 'failed'` on a run that exited 1 |
| `lane_death_fatal = True` — drops the zero-kept conjunct | the partial-success **exit-code** assertion, which already existed | **caught**, but by a pre-existing assertion, not a new one |
| `status=RUN_FAILED if lane_death_reason is not None` — ledger disagrees with the exit while every exit code stays correct | the partial-success **ledger** assertion, and nothing else | **caught** |

The third is the one worth keeping: it is precisely the disagreement class D-148 closes, it leaves the
CLI's behaviour indistinguishable from correct, and only the new assertion sees it. The second is worth
recording for the opposite reason — **a pre-existing assertion masked its own arm**, so a ledger
assertion added there without mutating would have looked redundant while proving nothing.

### What was verified rather than assumed

- **Run ownership, before placing the fix.** `cli/tailor_cmd.py:149` passes no `run_id`, so
  `owns_run` is `True` on every CLI invocation; `pipeline/runner.py:522` passes `run_id=run_id`, so the
  pipeline keeps the terminal status and one dead-credential lead cannot fail a whole run.
- **The agent lane cannot reach the new branch.** `agent_lane.py`'s `propose`/`judge` are dict lookups
  over the agent's JSON and cannot raise `LLMLaneDeadError`, so no `tb_override` row is ever
  `lane_dead`. Read in the code, because a reachable-looking `else None` invites someone to handle it.
- **The reindex diff.** `make reindex` rewrote all 71 `DECISIONS.md` index rows (+1 each, since the new
  row pushed the table down). Proved lossless with `comm -23` over the sorted index block — every entry
  present in both, only line numbers differing, no title changed. Not a row count.

### The `STATE.md` trim: attempted, blocked, not done

`STATE.md` was 187 lines against a target near 170 and is now 200. The Gate A narration was the
reviewer's trim candidate on the premise that it is all already held in D-137…D-145. **The premise is
false in three places** (D-149): D-143 states a write order `authoring.py:236,251` contradicts, D-145
explicitly forbids the Windows-green claim it is cited for, and `CHANGELOG.md` never mentions
`cited_back` at all — outside `docs/profile-bundle-authoring.md`, `STATE.md` is the only prose record.
Each was confirmed by reading the code, not a summary of it. Nothing was deleted; D-149 lists the four
things the trim owes first. One false claim was corrected in place — `__subclasses__()` is the test's
mechanism, production asks `isinstance(document, FactBearingDocument)`. *(D-149's third finding was
itself corrected before merge: a mis-scoped grep had missed `profile-bundle-authoring.md`'s own
pre-existing `cited_back` hit.)*

---

## Session — 2026-08-13 · `d147-residuals` MERGED (not a fast-forward) — GATE_EXIT=0 · 5,979 passed. No phase gate moved.

`d147-residuals` (`95f3125`, four commits) is merged into `main` as `5c28e8c`. D-148 and D-149 are now
on `main`; D-147's R1/R2/R3 are closed there, R4 stays open by choice.

### It was NOT a fast-forward, and the previous session's record said it would be

The "later still ×2" entry above and `STATE.md` both described the branch as "based directly on
`main`'s head so the merge is a fast-forward". True when written, false when read: `main` had moved
`0134632` → `b7fa572` on three docs-only commits, so the merge base sat two commits back and
`git merge-tree` reported two conflicts. **A "this will fast-forward" note is a claim about a pair of
shas, not a property of a branch** — it decays the moment either side moves, so re-derive it with
`git merge-base` rather than trusting the record.

### The two conflicts, and why a mechanical resolution would have shipped a false file

| File | Resolution |
|---|---|
| `METRICS.md` | Union — both new index rows, both appended session sections. `make reindex` then corrected **34** rows |
| `STATE.md` | **Not a union.** Neither side's text was true after the merge |

`STATE.md` is the one worth recording. `main`'s side said the residuals were "still unmerged" and that
a docs commit was being held back to avoid a second CI run; `d147`'s side carried a next-action list
written against a `main` that had already moved past it. Taking either side, or both, yields a
read-first file asserting that the branch it just absorbed is unmerged. Three regions were rewritten to
the merged truth: the slice-5 paragraph, the phase-status P3 row, and the gaps table — which drops the
R1 row this branch fixes in favour of the R4 row it leaves open. The sha `8c1b78f` was **kept** in the
slice-5 paragraph against the usual "no shas in a read-first doc" rule, with a clause saying why: it is
the tree CI ran the twelve green jobs on, not a claim about `main`'s head, and unbinding a gate result
from its sha is the failure that rule exists to prevent.

### Verified lossless by diff, not by counting

`comm -23` in both directions, run **twice** — once on the resolved tree and again after `make reindex`
renumbered every row — and split so a line-number shift could not disguise a dropped entry: index rows
compared **by title** with the `| FILE | NNNN | ` prefix stripped, body prose compared with index rows
excluded. All four comparisons empty. A row count would have agreed with itself and proved nothing.

### Gates measured

| Gate | Result |
|---|---|
| `make generalization index-check` (the doc resolution) | **exit 0** · `generalization: OK`, both indexes current |
| `make check` @ `5c28e8c` | **exit 0** · 5,979 passed · 1 deselected · **95.71%** · 16m13s (973.19s) |
| `gitleaks git --log-opts=origin/main..HEAD` | **exit 0** · 7 commits, no leaks, captured unpiped |

**5,978 + 1 = 5,979 reconciles exactly.** `main` was 5,978, its three commits were docs-only and added
no tests, and the branch added exactly one (`test_unclassified_provider_failure_keeps_the_run_ok`). The
gate result is bound to the sha four ways: an exit-code file, the task exit status, `GATE_SHA` equal to
`HEAD` at read time, and the pytest summary line.

### Checked through a second path

- **The merge preserved the branch's code exactly.** `git diff HEAD d147-residuals -- src tests
  README.md CHANGELOG.md` is empty, so the merge differs from the branch *only* in the two program
  logs — a different route to the conclusion than reading the conflict resolution.
- **CI's `success` on `8c1b78f` was read from the API** (`gh run list --branch main`), not recalled.
- **The running gate was confirmed alive by `ps`** (pytest at 98.5% CPU), not inferred from a quiet log.

### Measured: the gate is ~99% one single-threaded pytest process

Recorded so it is not re-derived. Timed from the gate log's own phase ordering on an M4 Mac mini
(`Mac16,10`, **10 cores** — 4 performance + 6 efficiency — 16 GB):

| Phase | Cost |
|---|---|
| `generalization`, `index-check`, `ruff`, `mypy --strict` (249 files, warm cache) | **~2 s combined** |
| `pytest` | **973 s** |

`addopts` is `-m 'not perf' --cov=boardwatch --cov-fail-under=85` with `branch = true`; there is no
`-n`, **`pytest-xdist` is not installed**, `MAKEFLAGS` is empty, and the loaded plugins are only
`cov`, `respx` and `anyio`. So the gate runs ~6,000 tests on one core of ten, at roughly 10% machine
utilisation, and **every minute of it is pytest** — optimising the other four phases is worthless.

Two stackable candidates, neither attempted yet: `pytest-xdist -n` (realistically 4–6×, not 10×, since
six cores are efficiency cores), and `COVERAGE_CORE=sysmon` (Python is 3.12.12 and coverage 7.14.1, so
both prerequisites for `sys.monitoring` branch coverage are already present). **Neither is free of
risk**: xdist reshuffles execution order, this suite has no `pytest-randomly`, so order-dependence has
never been exercised and is *hidden rather than absent* — the `from conftest import` collision already
recorded in this program is exactly that failure mode. A parallel gate that flakes is strictly worse
than a slow one in a repo whose doctrine is that `make check` is the only gate, so the change owes an
exact 5,979 match and repeat runs, not one green run.

### Housekeeping and still owed

Four worktrees removed after confirming each branch is an ancestor of `HEAD` (`d147`, `integrate`,
`p3-slice5`, `p3-slice5-t6`); disk was at 86%. D-149's four prerequisites for the `STATE.md` trim are
untouched and re-verified as still open — `CHANGELOG.md` still has **zero** `cited_back` hits.
`STATE.md` is 199 lines against a target near 170.

---

## Session — 2026-08-13 (later) · The gate parallelised: 16m13s → ~4m20s (D-150). No phase gate moved.

Prompted by Mit asking why sessions keep spending 17 minutes in the gate on a machine that is barely
working. The premise was right and the cause was not what anyone assumed.

### Where the 973 seconds actually went

| Phase | Cost |
|---|---|
| `generalization`, `index-check`, `ruff`, `mypy --strict` (249 files, warm cache) | **~2 s combined** |
| `pytest` | **973 s** |

`pytest` was ~99% of the gate and ran on **one core of ten** (M4 Mac mini, 4 performance + 6
efficiency): no `-n`, `pytest-xdist` not installed, `MAKEFLAGS` empty. Full rationale and the rejected
alternatives are D-150.

### Measured

| Configuration | Result |
|---|---|
| serial baseline @ `5c28e8c` | exit 0 · 5,979 passed · 1 deselected · 95.71% · **973s** |
| `-n 8` | exit 0 · 5,979 passed · 95.71% · **255s** |
| `-n auto` (10 workers) | exit 0 · 5,979 passed · 95.71% · **225s** |
| `-n auto` repeat | exit 0 · 5,979 passed · 95.71% · **252s** |
| `-n auto` + `COVERAGE_CORE=sysmon` (fell back; a fourth sample) | exit 0 · 5,979 passed · 95.71% · **219s** |
| full `make check`, wired in | exit 0 · 5,979 passed · 95.71% · **254s** |
| full `make check`, after the politeness fix | exit 0 · 5,979 passed · 95.71% · **279s** |

Six parallel runs, **every one exactly 5,979 and 95.71%**. `COVERAGE_CORE=sysmon` is a dead end here
and was measured rather than assumed — it cannot measure branches on this Python, silently falls back,
and adds eleven warnings.

### The review's finding, and the honest grading of the fix

An independent review cleared the isolation questions (no fixed-path writes, no global env mutation,
no port binding, session fixtures safe to rebuild per worker, coverage combination genuine) and found
one assertion whose margin was thinner than the noise parallelism adds: the host-overlap test's
`elapsed < 0.7` against a 0.8 s serialized time. Resized so the threshold sits at the midpoint of the
two outcomes; the global-lock mutation still fails it at 2.009 s, so it is not vacuous.

**The predicted flake was never reproduced.** Thirty runs of that test against a concurrent full
`-n auto` suite spanned **1.0022–1.0128 s**, ~11 ms of spread, which the old threshold would also have
survived. Recorded as insurance for the 3–4 core CI runners this machine cannot imitate — **not** as a
fix for an observed failure.

### CI timings, measured per step rather than assumed

From run `31663735766` on `8c1b78f`, the two 3.12 jobs:

| Step | Windows | Ubuntu |
|---|---|---|
| checkout + uv + typesetting + sync + ruff + mypy | ~38 s | ~44 s |
| `uv run pytest` | **4,610 s** | **2,822 s** |

Setup is negligible on both; it is all pytest. **Windows is only 1.63× Ubuntu** — the larger gap is
that a 4-vCPU runner is ~3× slower than this M4, not that Windows is uniquely broken. The twelve jobs
run concurrently, so **the run's wall clock is the slowest job**: trimming the matrix would save runner
minutes but not time, whereas `-n auto` should take the Windows job from ~77 min to roughly 25–30.
That number is not yet measured — the first CI run carrying the change will produce it.

### Carried

xdist's summary drops the `1 deselected` tally; the count-reconciliation habit now reads the
`[N items]` figure, which still moves if the `-m 'not perf'` filter is ever dropped.

---

## Session — 2026-08-13 (close) · CI cadence (D-151) and the CGPA retraction (D-152). No phase gate moved.

Closing record for the session whose main work is above.

### Shipped after the gate entry above

| Change | Gate |
|---|---|
| Windows off the per-push path, nightly + `workflow_dispatch` instead (D-151) | `make check` **exit 0** · 5,979 passed · 95.71% · 274s; `actionlint` clean; `gitleaks` exit 0 |
| CGPA retraction (D-152) — live config only, no repo change | n/a — `{config_dir}` is not in the repo |

**The D-151 expression was verified through the API, not read off the YAML**: the push run for
`c633b33` shows **6 test jobs (ubuntu + macos × 3 Python) and 0 Windows**. A nested GitHub Actions
ternary is exactly the kind of thing that silently evaluates to the wrong branch, so it was checked
against what actually ran.

### Two CI numbers are still PREDICTIONS, not measurements

Both were in flight at session close and neither should be quoted as fact:

- **Windows post-D-150**: predicted ~25–30 min against a measured serial 4,610 s. Run `31679881787`
  (`e629ea1`) carries it — the last run that will include Windows on a push.
- **A push without Windows**: predicted ~20 min. Run `31680928825` (`c633b33`) carries it.

For the serial baseline they are measured against, run `31676184386` (`b159053`) recorded macOS
27–39 min and Ubuntu 38–46 min.

### Résumé track REACTIVATED, and a framing error corrected

Mit's 2026-08-11 deprioritisation of the résumé content work **no longer applies**. Two corrections
worth carrying, both of them mine:

1. I framed the next step as "port the job-apps Aug 12 content into `resume.yaml`". **Wrong.** Mit:
   the job-apps résumés are *a benchmark boardwatch has to at least match*, the goal is for boardwatch
   to be **superior**, and the content discovery already done here must not be re-done. Copying the
   benchmark would cap the system at parity with the thing it exists to beat — and parity was already
   retired as a goal by D-008.
2. I told him the unattended runner is a macOS LaunchAgent and that posix-only code sits in the tree.
   **Both false** — there is no scheduling code in `src/` at all (README documents cron, launchd and
   systemd), and every `os.name != "posix"` guard is in `tests/`. Retracted in `STATE.md`.

**The next session opens with a render, not an edit** — Mit has not yet seen a boardwatch-produced
résumé and wants to before any content work. What he will see first is the *untailored master*, because
three over-length bullets make `validate_layout` fail-safe to it; that must be said out loud rather
than letting an untailored artifact be mistaken for the tailoring output.

### Still owed, unchanged by this session

D-149's four prerequisites for the `STATE.md` trim; `pdfinfo`'s silent failure (open Q3, and **not** a
Windows problem — it degrades any OS into "every lead failed to tailor"); the `export --format csv`
Windows crash (open Q3). `boardwatch doctor` **timed out at 2 minutes** during this session and was not
diagnosed — noted because a diagnostic command that slow on a daily driver is worth a look.

## Session — 2026-08-13 (render + CI red) · First boardwatch résumé rendered; a red CI job fixed (D-153) and `top`'s 141 s floor removed (D-154). No phase gate moved.

### The first boardwatch-produced résumé exists

Rendered for posting **19541** (Coinbase, "Software Engineer, Data Platform Team"):
`{config_dir}/tailored/untailored-19541.pdf` — 1 page, letter, 43,501 bytes. Mit has now seen it.

**It is the floor, not the tailoring**, and two independent things caused that:

1. `degraded: untailored fallback, reason=bullet_too_long`. Confirmed in code at
   `reports/tailor.py:565-599`: a `LayoutViolation` never reaches tectonic and the untailored master
   ships, deliberately without a layout gate of its own.
2. **Even with the gate passing, this JD would have repositioned almost nothing.** The plan was
   `kept 13 · dropped 0 · swaps 0`, with **11 of 13 bullets scoring "no jd skills"** — only `gl-2`
   (Docker) and `crop-1` (Python) matched. The JD wanted Airflow, Snowflake, ETL/ELT, Java, SQL, ML
   against an iOS/Swift-weighted résumé. The posting was chosen for a clean title, not for profile fit,
   which was a poor choice for judging tailoring.

Re-measured against the live file rather than trusted from the record — both held: the three
over-gate bullets are `nio-coop` b0 **245**, `streaksync` b0 **234**, b1 **232** (two more sit close at
218 and 215), and CGPA reads **8.5/10** in both `resume.yaml` and `resume_template.tex:98`, so D-152's
fix is in the artifact.

Mit's call: **the résumé content work gets its own session.** `tailor run` itself is fast (< 45 s).

### The two predicted CI numbers, now MEASURED — and one is RED

Both runs completed. **Both FAILED, on the same single job: `test (3.12, ubuntu-latest)`.**

| Run | Commit | Test-job spread | Verdict |
|---|---|---|---|
| `31679881787` | `e629ea1` | macOS 17m49s–22m51s · Ubuntu 25m44s–27m23s · **Windows all 3 green** | 8 of 9 green, ubuntu-3.12 **failed** · `1 failed, 5978 passed in 1608.60s` |
| `31680928825` | `c633b33` | 6 test jobs, **0 Windows** (D-151 confirmed again) | 5 of 6 green, ubuntu-3.12 **failed** · `1 failed, 5978 passed in 1417.83s` |

Against the serial baselines (macOS 27–39 min, Ubuntu 38–46 min), xdist helps in CI but far less than
the 3.6x measured locally — the runners are 4-worker, this machine is 10.

**Not a flake**: the same test on two commits. Cause and fix in D-153. The local gate is the same Python
(3.12.12) as the failing job, so only the environment differed.

### `top`'s ~134 s floor was real, and is measured at 141.54 s → 0.14 s

See D-154. Timed on a **copy** of the live store, not Mit's database. `pending_rows=4655` identical on
both sides, so the index changed speed and not results.

### Gate

| Gate | Result |
|---|---|
| `make check` (first run, pre-head-bump) | **exit 2** · `1 failed, 5978 passed in 258.07s` — `test_head_is_the_job_dispositions_table`, the head pin the new migration is supposed to trip |
| `make check` (after the head bump) | **exit 0** · **5,979 passed** · **95.71%** · mypy clean on 250 files · `All checks passed!` · 381.28s |
| `make reindex` | D-153 → 5013, D-154 → 5069; METRICS index already current |

Reconciled against the `10 workers [5979 items]` line, not the summary — xdist drops the `deselected`
tally (D-150).

### Found while measuring, NOT fixed

- **Three `runs` rows are stuck in `status='running'`** with `finished_at` NULL (ids 15, 16, 17). Id 15
  (07:45:57Z) **predates every command this session ran**, so this is the carried dangling-row gap
  observed live rather than theorised. `top` is what opens them. Row 16's timestamp could not be
  accounted for against the two invocations made here and is not guessed at.
- **`boardwatch top` marks postings `seen` by default**; `--no-record` is opt-in. Two timed-out
  exploratory invocations therefore advanced the queue — relevant to the clean 7-day window Gate P6's
  duplicate-leakage clause needs.
- **`boardwatch doctor`'s 2-minute timeout is now explained but unfixed.** `doctor_cmd.py:120` →
  `scan/health.py:41-70` probes **all 135 watched boards serially** through a fetcher with 1.0 s
  per-host pacing, a 30 s timeout and 3 retries: the shared-host boards alone force ≥ 85 s of pure
  sleep, and each dead board can add 90 s. It also runs `PRAGMA integrity_check` on an 803 MB database,
  and `subprocess.run(["tectonic","--version"])` at `doctor_cmd.py:55` has **no timeout**. The module
  docstring's stated budget ("~15 boards ≈ seconds when healthy") is stale by ~9x. Which of the two
  multi-minute stages consumed the budget was **not** measured; `doctor --offline` discriminates.
- **`ANALYZE` has never run on the live store** (`sqlite_stat1` absent), so every plan is chosen with
  zero statistics.

## Session — 2026-08-13 (push) · D-153's first fix was WRONG and a review caught it pre-push; six commits pushed. No phase gate moved.

### The red job is deterministic: THREE runs, always the same one

| Run | Commit | ubuntu-3.12 | Every other test job |
|---|---|---|---|
| `31679881787` | `e629ea1` | **failure** | green (incl. all 3 Windows) |
| `31680928825` | `c633b33` | **failure** | green |
| `31681809603` | `88e9223` | **failure** | green |

Three for three, and **never** ubuntu-3.11 or ubuntu-3.13. So the environment difference is specific to
that one matrix cell. What it actually sets was never read; the fix is immune to both candidate variables.

### The first fix traded one failure for three — the review is what caught it

D-153's first attempt pinned `TERM=xterm` in an autouse fixture. It passed the full local gate (exit 0,
5,979 passed) because the hostile variable is not set locally — **the same blind spot D-153 itself
describes, walked into while writing it.**

`is_dumb_terminal` gates **colour as well as width**. Under `TERM=xterm FORCE_COLOR=1`:

| Test | Failure |
|---|---|
| `test_applied_state_suppression.py:124` | `assert "1 hidden as already applied to" in out` — ANSI wraps the leading `1` |
| `test_applied_state_suppression.py:142` | same shape |
| `test_the_JSON_path_names_every_bucket_too` | **`JSONDecodeError`** — escape codes inside `--json` output |

**The review named the first two; running it found the third.** That is the arm-enumeration rule paying
off again: a review's probe closes the arms it reaches, not the ones it does not.

**A fixture cannot fix this**, which is the transferable detail: `Console.__init__` resolves
`_color_system` eagerly and this program builds module-level consoles at import, so a hostile ambient env
bakes colour in before any fixture runs. Measured: **4 failures** with the env cleared in a fixture,
**0** with it cleared at conftest import time.

Verified across **five** hostile environments, 47/47 relevant tests in each: `TERM=xterm FORCE_COLOR=1`,
`TERM=dumb FORCE_COLOR=1`, `TTY_COMPATIBLE=1 TERM=dumb`, `TTY_COMPATIBLE=1 TERM=xterm`, `FORCE_COLOR=true`.

### Gate and push

| Gate | Result |
|---|---|
| `make check` (corrected fix) | **exit 0** · **5,979 passed** · **95.71%** · mypy clean on 250 files · 259.51s |
| `make check` (attempt 3) | **exit 2** — ruff `I001` import sort only; **lint runs BEFORE tests, so the suite never ran.** A short-circuited gate is not a test result |
| `gitleaks` (`origin/main..HEAD`) | **exit 0** · no leaks · 6 commits scanned |
| migration up / down / re-up on a fresh DB | index appears, disappears, reappears; `schema_revision()` is the SCRIPT head, not the DB revision |
| `index-check`, `generalization` | exit 0 both |

**Pushed `88e9223..cb4db79`** (6 commits), remote reporting "Bypassed rule violations — 6 of 6 required
status checks are expected" as always. **Verification run `31686855081` (`cb4db79`) was IN PROGRESS at
session end** — whether ubuntu-3.12 actually goes green is therefore *not yet measured*. Check it before
treating D-153 as confirmed.

### Also corrected this session

- **`STATE.md:28`** asserted present-tense that the schema head is `p6_job_dispositions`. D-154 moved it.
  Found by grepping the string, which is the only reliable way; every other hit is historical.
- **One measurement was quoted three ways** — "~134 s", "~5.8 ms x 23,455", and the measured 141.54 s —
  across `tables.py`, the migration docstring and D-154. Now all cite the measurement.
- **"even when no posting was pending" was an inference presented as a measurement.** The timing ran with
  4,655 rows pending on both sides. Restated as an inference from the plan.

---

## Session — 2026-08-13 (roadmap review) · The program reorients onto the bundle path (D-155, D-156, D-157). No phase gate moved.

**What this session was:** the broad roadmap review Mit asked for, which turned into a reorientation and a
design. No code shipped; four documents and one design did.

### The review's findings, measured not recalled

| Fact | Value |
|---|---|
| Job applications ever produced | **0** (`applications` 0 rows, `application_events` 0) |
| Unattended days accumulated toward Gate P3's 7 | **0** |
| Acceptance days | **0** — table holds one `_(not started)_` row |
| Run log rows | **3**, all 2026-08-06, all `--no-scan` against a copy |
| Postings ever tailored, all time | **18** |
| Commits on `main` | 754, of which **570 landed in the 8 days since 2026-08-06** |
| Source / tests / coverage | 45,909 lines · 5,979 tests · 95.71% |
| CLI surface | **61 executable commands** across 15 groups |
| Live store | 803 MB · 24,073 postings (23,455 open) · 135 watched boards |

**The shape of it: the machine is close to fully built and has almost never been run.** P0/P1/P2/P5 gates
MET; P3/P4/P6 NOT MET and all three waiting on the same thing — daily runs that never accumulated.

### The premise that was false (D-155)

`STANDING-FACTS.md` carried *"Nothing is generating Mit's résumés daily right now."* Measured against
`~/dev/Job apps/resumes/`:

| Date | Folders | PDFs |
|---|---:|---:|
| 2026-08-09 | 3 | 8 |
| 2026-08-10 | 3 | 28 |
| 2026-08-11 | 5 | 24 |
| 2026-08-12 | 4 | 18 |

`STAGE1_ONLY=1` **is** in the launchd plist, so the automated 08:30 run does stop after discovery — the
résumés get made anyway. `PROGRAM.md` §2's output-side-first ordering argument rested on the false
premise. Corrected in `STANDING-FACTS.md`.

### The import path, measured against the live file

`BoardwatchResumeEnumerator` (the shipped `boardwatch-resume-v1` adapter) run against
`{config_dir}/resume.yaml`:

```
SOURCE RECORDS ENUMERATED: 81
  header: 2 · education: 2 · skill-groups: 58 · entries/metadata: 6 · entries/bullets: 13
```

That is Gate B's source-record denominator for that source. **`profile-bundle init` was smoke-tested in a
sandbox config dir: exit 0, full tree created.** The import machinery (~1,400 lines across
`enumerators.py` + `imports.py`) has **no CLI command**.

### The projection design and its two external reviews

Revision 1 (`ce1efde`) → GPT and DeepSeek, independently, in-repo, with executable probes and negative
controls. **Both VERDICT: REWORK.** GPT: 9 BLOCKING + 1 SHOULD-FIX. DeepSeek: 3 BLOCKING + 3 SHOULD-FIX +
3 NOTE. Reviews kept at `.agent/REVIEW-R1-GPT.md` and `.agent/REVIEW-R1-DEEPSEEK.md`.

**All seven premises the design stated were confirmed by both reviewers.** The fatal defect was an eighth
the design never wrote down: `LatexRenderer.emit` never reads `Resume.header` or `Resume.education`
(`reports/resume_gate.py:237-242` says so verbatim). Verified independently before accepting.

**The three reviewer disagreements, all resolved against the code, all in GPT's favour:**

| Disagreement | Resolution |
|---|---|
| Is `tech_tags` inert? | **GPT.** `reports/tailor.py:430` hashes `master.model_dump_json()` deliberately — tags are lineage-significant |
| Can entry scoring inherit `build_plan`'s behaviour with `plan.py` unchanged? | **GPT.** `_applicable_swaps` is private (`plan.py:51`); the two claims cannot both hold |
| Is the two-stage split real? | **GPT.** `Entry` has no `pinned` field, so a serialized `Resume` cannot carry the handoff |

Revision 2 dispositions all eighteen findings (spec §13). Verified independently for it: 0 float
environments in `resume_base.tex` (so the budget loop's termination guarantee holds), and
`_pdf_page_count` returns `None` on missing `pdfinfo` (so the `COMPILE_FAILED` arm is real).

### CI — D-153's fix FAILED

Run `31686855081` (`cb4db79`) → `test (3.12, ubuntu-latest)` **FAILED**. **Fourth consecutive failure on
that exact job**, identical assertion. `STATE.md`'s claim that D-153 fixed it was wrong and is corrected.
The constraint no diagnosis has yet satisfied: **3.11 and 3.13 pass on the identical runner image**, so an
environment-variable explanation cannot be the root cause. Investigation dispatched to worktree branch
`fix/ubuntu-312-abstain`.

### Gates run this session

| Run | Result |
|---|---|
| `make check` (D-155 docs) | **exit 0** · 5,979 passed · 95.71% · 286.29s |
| `make check` (D-156 docs) | **exit 0** · 5,979 passed · 95.71% · 305.76s |
| `make reindex` | exit 0, both files current |

### D-149's trim prerequisites CLEARED (D-157)

All four discharged, so **`STATE.md`'s Gate A trim is unblocked and done**: the manifest write order is
now recorded outside `STATE.md`; D-145's Windows prohibition is discharged citing the CI run that closed
it; `cited_back` is in `CHANGELOG.md`; and the review-loop caveat is carried verbatim into the rewritten
file. **`STATE.md` went 255 → 146 lines**, under its ~170 target for the first time since D-139.
