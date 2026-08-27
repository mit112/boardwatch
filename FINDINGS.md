# Near-duplicate detection: measurement, design, and a refusal

**2026-08-27.** Investigation of `company_title_location` duplicate detection, authorised by the
owner as a possible reversal of D-283/D-295 ("only `exact_quad` counts as a duplicate").

**Headline: the measurement does NOT justify reversing D-283/D-295, and no suppression change is
shipped.** What IS shipped is the half the evidence fully supports and that deletes nothing: the
Gate P6 leakage metric stops hardcoding `exact_quad`, and reports the wider class as a separate,
never-folded, discriminator-vetoed **upper bound**.

Every ratio below states its match rule and its corpus size beside it. The live corpus grew during
the session (69,963 -> 70,573 open postings) because the daily driver runs every ~3h, so each figure
carries the corpus it was taken against rather than a single shared denominator.

---

## 1. The duplicate population, measured read-only from the live store

Match rule for every "ctl" figure: `postings.company_id` + `normalize_title(title)` +
`normalized_locations(locations_json)` -- the exact tuple `company_title_location` already hashes at
`p6.2`. Read via `sqlite3` `file:...?mode=ro`; nothing was written.

| key | corpus | identified | groups | redundant | rate |
|---|---:|---:|---:|---:|---:|
| `exact_quad` | 69,963 open | 69,897 | 68,058 | 1,839 | 2.63% |
| `company_title_location` | 69,963 open | 69,912 | 65,338 | 4,574 | **6.54%** |
| `content_hash_only` | 69,963 open | 69,963 | 60,857 | 9,106 | 13.02% |
| `cross_host` | 69,963 open | 69,912 | 65,013 | 4,899 | 7.01% |

The **residual class** -- what a wider rule would newly act on, i.e. ctl groups holding >=2 *distinct*
`exact_quad` keys -- is **1,974 groups / 2,735 redundant postings (3.91% of 69,963 open)**.

**Stored identities are not stale.** All 70,459 open postings were re-run through the shipped
`compute_identities`: **zero** stored-vs-recomputed mismatches on any kind. The hazard
`core/dedup._verify_quad` documents is real but is not currently firing, so none of the missed
redundancy is a staleness artefact.

## 2. True vs false duplicates -- the ratio that decides the design

### 2a. Corpus sample, n = 30 random residual pairs (seed 20260827)

Each pair adjudicated by reading a word-level diff of the two bodies, not by a score. Criterion:
would an applicant who applied to one gain anything by applying to the other?

**10 true duplicates / 30 = 33.3%. 20 genuinely distinct = 66.7%.**
(Match rule: ctl as above. Population: the 1,974-group / 2,735-posting residual class over 70,550
open postings.)

The 20 distinct ones are distinct for substantive reasons: two research topics under one Post-Doc
title (OSU), two UK service territories under one Field Service Engineer title (KION), Adobe Stock
backend vs observability tooling under one "Software Development Engineer" title, dentistry vs
nursing, Cisco 8000 router vs the DSE group, 5+ vs 8+ years at Broadcom.

This independently reproduces D-294's own count (103 near-identical of 269 = 38%) on a corpus that
has since doubled.

### 2b. The population the gate actually measures -- exhaustive, not sampled

Gate P6 counts jobs that reached `job_dispositions`. In the 7-day window there are **601 surfaced
jobs (600 identified, all `built`)**, and the ctl key puts **19 redundant jobs across 17 groups**
(3.17%). Small enough to adjudicate every one:

| verdict | groups | examples |
|---|---:|---|
| **true duplicate** | **3** | Citi `Regulatory Risk Officer C13` Jacksonville (bodies differ by ONE deleted word); Philips `Team Leader` Latham NY (differ by a req-number echo + `#eos`); Disney `Software Engineer` Orlando |
| genuinely distinct | 14 | Affirm x3 (different pay bands *and* years floors), LaunchDarkly, MongoDB Replication, Stripe (founding/senior), Verkada (1-3 vs 3+ yrs, $125-160k vs $150-300k), Adobe x2, Cisco x2, Broadcom (5+ vs 8+ yrs), Thomson Reuters, Intel |

**3 true of 17 groups = 17.6%.** Honest duplicate leakage on the delivered population is therefore
**3 / 600 = 0.50%** -- not the 0.00% the blind metric prints, and not the 3.17% a raw ctl count
would print. Both wrong numbers sit inside the <=5% gate, so the gate's *verdict* was never at risk;
its *readability* was.

**One hand adjudication was overturned by the shipped code, and the code was right.** Intel
`CPU Performance Architect` Austin (JR0285980 / JR0281596) was first read as a duplicate: the
word-diff showed only re-wordings. The salary discriminator then fired on it, and the two bodies do
state **$122,440.00-172,860.00** and **$141,910.00-232,190.00** -- the diff had been truncated
before the pay line. The table above is corrected. It also exposed a real extraction gap, since
fixed: `$122,440.00-172,860.00` carries one currency symbol for two figures, and dropping the top of
a band makes two bands MORE likely to look disjoint, which is the direction that shrinks the bound
on no evidence.

### 2c. Similarity floors still do not separate the populations

D-295 falsified a body-similarity floor. It stays falsified on this fresh population: the highest
distinct pair (Broadcom, **0.9726**) sits *between* two true duplicates (Philips 0.9974, Disney
0.9668). Do not re-propose a threshold.

## 3. What job-apps taught

The sibling `job-apps` checkout, read as evidence only; nothing copied, nothing committed. (Its
path is deliberately not written here: R1 of the generalization gate forbids a home path in a
tracked file, and this document is tracked.)

1. **job-apps already migrated away from the rule boardwatch is being asked to adopt.**
   `job_discovery._dedup_jobs_legacy` *is* company + similar-title + overlapping-location. The v2
   `enforce` path replaced it: *"only Tier-1 (exact identity) matches merge and **distinct exact
   identities are always kept (same-title/new-requisition priority)**"*.
2. **Its fuzzy near-duplicate layer annotates, never merges.** `dedup_jobs` sets
   `job["dedup_review"] = True` and keeps the row -- and only when *neither* side carries an exact
   identity. Its 135,665 typed `disposition_events` confirm the split: the fuzzy path produces
   `eligibility/review/dedup_review_quarantine` (1,304) and
   `cross_date_dedup/fuzzy_quarantined/suspected_duplicate_fuzzy` (158); **every** `skipped`
   duplicate reason (`duplicate_listing`, `duplicate_canonical`, `duplicate_prior_built`,
   `duplicate_cross_host`, ...) is an exact-identity reason.
3. **Its answer key agrees with section 2 on a corpus 2x ours.** Over 51,221 postings carrying a
   full company+title+location triple, ctl redundancy is **9.85%**, and of the 3,170 multi-member
   ctl groups, **1,423 (44.9%) have every member carrying a *distinct suppressible exact
   identity*** -- provably different requisitions, before anyone reads a body.
4. **Its `posting_identities.suppressible` column is boardwatch's `IdentityKindSpec.suppresses`.**
   The architecture already transferred; what did not transfer is a licence to widen it.
5. `autoapply/job_identity.py` keys on the board's own stable posting id and falls back to a
   *light URL normalization* -- the same "never guess" discipline. Its one transferable extractor is
   the **requisition slug inside the posting's own URL**, which is used below.

## 4. Design

### Rejected, with the measurement that rejects it

- **Make `company_title_location` suppress** (with or without discriminator gating): 66.7% of the
  corpus residual class and 82.4% of the delivered class are genuinely different jobs. Fail-safe
  direction for a suppression gate is *never silently delete a real job*; this deletes four for
  every one it collapses. Even with the discriminator veto in front of it, the bound still holds 3
  distinct groups it cannot prove -- suppression there would have deleted MongoDB's Replication
  team opening and two Cisco teams.
- **Any body-similarity floor**: section 2c.
- **A new suppressing `near_duplicate` kind keyed on an order- and punctuation-insensitive body
  token multiset.** This one is *exact* (a hash equality, no tunable constant) and its precision on
  inspection was perfect, so it was measured rather than dismissed: it collapses **56 additional
  redundant postings corpus-wide (0.08% of 70,550)** and **0 on the delivered population** -- it
  catches none of the four real duplicates in section 2b. It would cost an
  `IDENTITY_ALGORITHM_VERSION` bump, which turns suppression *off* until a 70k-posting backfill
  completes. Rejected on cost/benefit, not on principle.
- **"City named in the body" as a discriminator.** Its value is real (D-295's GE HealthCare
  Lubbock/Salt Lake/Chattanooga case), but every catalog-based extractor tried here was noisy -- a
  comma list of US states yields `california, co`; a degree list yields `bs, ms`. Shipping a noisy
  extractor into a gate metric is worse than not shipping it. Measured, rejected, recorded.

### Shipped

The defect that is real and that the evidence fully supports: **`identity_queries.py` hardcodes
`kind == "exact_quad"`, so Gate P6's leakage metric cannot see the wider class at all.** It reports
0.00% for a structural reason. Per CLAUDE.md, *a rule that cannot fire is a monitoring failure*.

1. `store/identity_queries.py`: the hardcoded literal becomes
   `load_surfaced_identities(conn, *, kind)`, validated against the closed catalog -- an
   out-of-catalog kind raises `UnknownIdentityKind` at the call site, never a new bucket.
   `load_surfaced_exact_quad` stays as a one-line wrapper because its `func.max` collapse is
   specific to that kind. Three small reads join it: `load_surfaced_keys` (one row per key,
   NOT collapsed -- see below), `load_surfaced_posting_ids`, and `load_near_duplicate_evidence`.

   `load_surfaced_keys` exists because `func.max` keeps only the lexicographically largest of a
   job's keys. For the gate clause that limitation is pre-existing and pinned by a test; for the
   bound it would hide a redundancy and read LOW, so the candidate path returns every key and an
   ambiguous job inflates the bound instead.
2. `core/near_duplicate.py` (new, pure): a **closed catalog of distinctness discriminators** and
   `distinguishing_evidence(a, b) -> tuple[str, ...]`, naming the discriminators that carry *proof*
   the two postings are different openings. Shipped discriminators, each with adjudicated evidence
   above:
   - `requisition_slug` -- the human-readable slug in the posting's own URL, req id stripped
     (job-apps' extractor; D-295's Capital One `...--Front-End` case; 3 live vetoes measured).
   - `salary_band` -- the structured `salary_min/max` columns, else the dollar figures stated in the
     body (Affirm x3, Verkada).
   - `experience_years` -- the years floors stated in the body (Affirm x3, Verkada, Broadcom).

   **The proof rule is disjointness, not inequality**: a discriminator fires only when *both* sides
   state something and the two stated sets share **nothing**. Mere inequality would fire on a JD
   that merely lists one extra figure, and that would shrink the reported bound on no evidence.
3. `reports/leakage.py`: `LeakageReport` gains a `candidate_*` bucket on
   `company_title_location`, **never folded into `identified`, `distinct_groups` or `rate`**. The
   gate clause continues to read the `exact_quad` rate. The candidate rate is labelled an upper
   bound and reports how many redundant surfacings the veto removed. `compute_leakage`'s new
   `candidates` argument is **required**, not defaulted: a default of `()` would silently report a
   zero bound for a caller that forgot it, and zero is the direction that makes the gate easier
   to pass. The bound's numerator is summed per group rather than as `identified - groups`,
   because a job carrying two keys makes that subtraction go negative.
4. `cli/identities_cmd.py`: prints both, never folded.

**Nothing new suppresses.** `SUPPRESSING_KINDS` is unchanged, `core/dedup.resolve_duplicates` is
untouched, and `core/near_duplicate` is deliberately not reachable from it. The existing injected
hash-collision test and the "ambiguous => nothing suppressed" suite keep passing unchanged, because
the suppression path did not move.

### Fail-safe direction, per gate

- **Suppression** (unchanged): fail-open. Never silently delete a real job. This is why the reversal
  is refused.
- **The candidate metric** (new): fail-*loud*. An unmeasurable or ambiguous pair stays IN the
  candidate bound, so the number can only be too high, never too low. This is the opposite direction
  from the suppression gate and it is deliberate: a metric that under-reports leakage makes a gate
  easier to pass, which is the one failure a gate must not have. That is also why the veto requires
  disjoint stated evidence rather than mere inequality -- the veto is the only thing that can shrink
  the bound, so it may only fire on proof.

### What this does to the Gate P6 number -- before and after, plainly

The gate is being read while the instrument changes, so both numbers are stated.

- **Before**: `leakage (last 7d): 0.00% (0 redundant of 600 identified across 600 distinct
  exact_quad groups; 1 unidentified excluded; 601 total reached leads)`. The 0.00% is true of
  `exact_quad` and says nothing about near-duplicates, because the query could not see them.
- **After**, run through the shipped code against the live store read-only (the CLI was never run
  against it -- `identities leakage` opens a writable engine):

  ```
  window_days 7 · surfaced_total 611 · unidentified 1 · identified 610
  distinct_groups 610 · redundant 0 · rate 0.0
  candidate_kind company_title_location · candidate_identified 610
  candidate_groups 604 · candidate_redundant 7 · candidate_distinguished 13
  candidate_rate 0.0115
  ```

  An independently written reconstruction over the same rows reproduces it: 20 raw redundant,
  13 proven distinct, **bound 7 / 610 = 1.15%**.
- **The gate clause and its verdict do not move**: `exact_quad` is still 0.00%.
- **Veto precision on the live delivered population: 13 of 13.** Every removal was inspected by
  hand; all thirteen are genuinely different openings (Affirm x2, LaunchDarkly, Stripe, Verkada,
  Adobe x2, Cisco, Intel, Thomson Reuters, Broadcom, KION). **Zero duplicates were vetoed out.**
- **Of the 6 groups left in the bound, 3 are true duplicates** (Philips, Citi, Disney = 3 redundant)
  and 3 are distinct pairs the veto could not prove (Affirm's Canada/US pair, which states pay with
  no currency symbol at all; Cisco x3; MongoDB = 4 redundant). So the instrument went from a
  structurally-guaranteed **0.00%** to a **1.15% bound over a 0.49% truth** -- honest, and wrong
  only in the safe direction.
- **The `unidentified` bucket is still never folded into either neighbour, and the candidate bucket
  is never folded either.**

### Non-vacuity

Every test was written and RUN before the code existed. The three new/extended suites failed at
import against `main` (`No module named 'boardwatch.core.near_duplicate'`; `cannot import name
'CandidateGroup'`; `cannot import name 'load_surfaced_identities'`). Because an import error is a
weak signal, each load-bearing rule was then re-checked against a deliberately wrong version of the
finished code:

| mutation | tests killed |
|---|---|
| disjointness -> inequality (`not (left & right)` -> `left != right`) | 5, incl. both "overlapping evidence is not proof" tests and all three "abstains" tests |
| keep digit-bearing words in the URL slug | 4, incl. the Citi and Philips duplicate pairs |
| delete the UUID guard | 1 |

The UUID guard round is worth recording: the first version of that test used two REAL Lever UUIDs
and passed with the guard deleted, because the digit-word strip already killed every hex chunk. The
test was rewritten around a constructed UUID whose chunks are digit-free, which is the case the
guard actually defends. A test that passes against the wrong version is a defect, not a pass.

Two real defects were found this way rather than by inspection: the salary extractor dropped the top
of a `$X-Y` range (found by the live-store validation overturning a hand adjudication), and
`candidate_identified` counted a two-key job twice, diluting the rate. Both were fixed test-first.

### Cost

No `IDENTITY_ALGORITHM_VERSION` bump (no normalizer, key tuple or host-class table changes;
`company_title_location` is already stored at `p6.2`). No `engine_version()` move -- this touches
none of `eligibility/{catalog,detect,resolve,engine}.py` -- so **no ledger drain is owed**. No
`Settings` field. No schema change.
