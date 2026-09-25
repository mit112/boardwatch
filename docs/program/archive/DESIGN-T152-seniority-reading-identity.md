# T152 — What a stored body-seniority reading legitimately depends on

**Status: DESIGN, no code.** Required by D-539 and by T152's own acceptance contract: *"A design
document exists naming: which identity components a body reading legitimately depends on, what
happens to a reading whose body has since changed, and the migration for the ~2,131 existing rows.
**No code before that document.**"*

**Read this first if you are about to change `read.py`.** Three claims in the ticket text are wrong
against the code and are corrected in §0. The design itself starts at §1.

---

## 0. Corrections to the ticket text, made before designing against it

1. **D-380 does not contain the sentence the ticket attributes to it.** The ticket quotes
   *"absent reads `unclear`, never `no`"* as D-380's direction. That string lives in **code**, at
   `src/boardwatch/eligibility/read.py:255-259`, and it is **D-537** that quotes it back while
   attributing it to D-380 (`DECISIONS.md:30634-30636`). D-380's own direction sentence is
   `DECISIONS.md:19019-19021` and is about **requirement flags**, not `seniority_fit` — which did
   not exist until 2026-09-13. The fail-open direction is real and it stands; the citation is not.
   **Cite `read.py:255-259` for the direction and D-537 for the diagnosis.**
2. **`target_seniority_band` is in NO hash, and the judge is never told it.** The ticket frames a
   seniority reading as being "about the JD body and the target band". Today it is not: the band is
   a `profile` column (`store/tables.py:248`), is absent from `Facts`
   (`eligibility/facts.py:85-116`), and therefore cannot reach `facts_payload`, `profile_hash` or
   `gate_facts_key`. The seniority prompt (`oracle.py:106-116`) asks a **band-free** question — "is
   this an entry-level / new-grad / early-career role for a candidate with the `facts`' years of
   experience". So the stored reading is a function of **(body, `total_years_experience`,
   prompt/policy version, model)**. The band is applied later, by the consumer. Any design that
   folds the band into a stored key must first reckon with `rank/title_band.py:16-20`, which rules
   that **the band is computed on every read and never persisted**, precisely so that narrowing the
   target re-routes already-delivered leads.
3. **The reading is simultaneously OVER-keyed and UNDER-keyed.** The ticket only names the
   over-keying. `current_gate_seniority` (`read.py:241`) scopes on `rules_hash` — which it should
   not — but, unlike its sibling `current_gate_verdicts` (`read.py:299`), it accepts **no**
   `facts_key` and **no** `model` narrowing (`read.py:302-303`, `:362-368`). So a `highest_degree`
   edit kills the reading while a **judge swap does not**, and the judge is the input D-537 priced
   at an 11.2% entry-level false-negative rate. **A design that only removes `rules_hash` fixes the
   smaller half.**

---

## 1. The problem, stated precisely

`current_gate_seniority` finds a stored reading only when **all five** of these hold
(`read.py:264-277`):

| # | condition | line |
|---|---|---|
| 1 | `posting_version_id IN (…)` | `:270` |
| 2 | `profile_hash == …` | `:271` |
| 3 | `rules_hash == …` | `:272` |
| 4 | `engine_kind == "llm"` | `:273` |
| 5 | `engine_version LIKE 'final_gate:%'` | `:274` |

A miss is not an error: the posting id is simply **absent from the returned dict**, and the
consumer defaults it to `"unclear"` (`delivery_queries.py:1168`, `:1608`; `runner.py:1526-1528`).
That default is the fail-open direction and **is not in scope**. What is in scope is condition 3.

**The measured consequence.** All 2,131 stored `engine_kind='llm'` rows carry one `rules_hash`,
stable 2026-09-06 → 2026-09-21, which does not match the live identity (D-537,
`DECISIONS.md:30638-30640`). Every one of them is unreadable, so every seniority hold they
supported has silently released — **117 leads measured moving out of `_review` into the apply
lane**. This session moved `rules_hash` twice more (D-540/D-541, and again if T105 ever lands), so
the condition is not hypothetical maintenance: it fires on ordinary catalog work.

---

## 2. Which identity components a body reading legitimately depends on

The test applied to each candidate: **could a change to this component change the correct answer to
the question the judge was actually asked?**

| component | keep? | why |
|---|---|---|
| `posting_version_id` | **YES — mandatory** | The reading is a reading *of this body*. `posting_versions` is immutable (`tables.py:582-586`), so a new version is a new body and the old reading is genuinely dead. This is the one component that is unambiguously correct today. |
| `total_years_experience` | **YES — and it is MISSING today** | The prompt asks the question *relative to the candidate's years* (`oracle.py:109-110`). Change the years, and the correct answer changes. It reaches the key only incidentally, via `profile_hash`, and **only while `experience_years` severity is not `ignore`** (`hashing.py:85-92`) — so the reading is under-keyed on its own stated input. |
| judge prompt/policy version | **YES — and only as a PREFIX today** | `engine_version` is `final_gate:{POLICY_VERSION}:{PROMPT_VERSION}` (`final_gate.py:29-30`) but the read matches `LIKE 'final_gate:%'`. A reading produced under `p5-oracle-1`, before `seniority_fit` existed, therefore still matches and reads `unclear` (`oracle.py:47-51` records 434 of 505 leads in exactly that state). A prompt change that alters the seniority question should invalidate and today does not. |
| judge **model** | **YES — and it is MISSING today** | A different model returns a different verdict for the same JD; the repo already asserts this for the *verdict* lane (`read.py:367-368`, T108) and `manifest.py:173-178` puts `gate.model` in `config_hash` with exactly that comment. D-537's 11.2% floor is a statement about *which model answered*. Omitting it is the gap T153 rides on. |
| `rules_hash` | **NO — remove** | `catalog.version` is a sha256 over the whole parsed `rules.yaml` (`hashing.py:97-98`). The seniority prompt references **no catalog vocabulary at all** — no family, no `implies`, no `requirement_text` — and the question is asked under a fixed all-blocker judging policy (`final_gate.py:41-43`, D-461). A one-line regex edit for `sponsorship_available` cannot change whether a body reads as a senior role. |
| rest of `profile_hash` | **NO — remove** | `work_authorization`, `security_clearance`, `highest_degree`, `field_of_study`, `employment_type_preference`, `internship_preference`, `education_timing` (`facts.py:88-116`) are eligibility inputs. None can change what a body says about seniority. |
| `target_seniority_band` | **NO — deliberately out** | Not an input to the reading (§0.2) and ruled never-persisted (`title_band.py:16-20`). The band belongs to the consumer, which recomputes it per read so that narrowing the target re-routes delivered leads. Folding it in would freeze the very thing that must stay live. |

### The proposed key

> **A stored seniority reading is valid for `(posting_version_id, years_key, judge_key)`**, where
> `years_key` digests only `total_years_experience`, and `judge_key` digests the judge model plus an
> exact seniority prompt/policy version.

It is **narrower** than today's key on the catalog and **wider** on the two inputs that actually
determine the answer. That is the whole design.

---

## 3. What happens to a reading whose body has since changed

**Nothing, and that is already correct — do not change it.** `posting_version_id` is in the key,
`posting_versions` rows are immutable, and a revision mints a new version. The old reading stays
attached to the body it described and simply stops being found for the new one. The lead then reads
`unclear` and is not held — fail-open, per `read.py:255-259`.

The *separate* question "was this résumé built against a body that has since moved?" is **already
answered elsewhere** and must not be folded in here: T119's `revised_since_build`
(`delivery_queries.py:1174+`) holds such a lead for review on its own. Two mechanisms, two
questions; merging them would make a stale-artifact hold look like a seniority finding.

---

## 4. Migration for the ~2,131 existing rows

**The hard constraint, and it decides the design:** the four eligibility tables carry
`BEFORE UPDATE/DELETE RAISE(ABORT)` triggers, so **a row can only ever be superseded, never
corrected — there is no backfill path** (`hashing.py:139-141`). Any migration that hopes to rewrite
`eligibility_inputs.rules_hash` on 2,131 rows is not implementable.

Three options, with the recommendation.

**(a) Re-judge — rejected.** Spends the one re-judge D-537 reserved for after T153, and spends it
on rows whose *content* is fine. It also does not fix the class: the next catalog edit re-creates
it.

**(b) Read-side widening only — rejected as the whole answer, kept as the first step.** Drop
`rules_hash` from the WHERE clause and the 2,131 rows become readable immediately, with no write of
any kind. This is genuinely attractive and is the entire benefit at near-zero cost. Rejected as a
*complete* answer because it leaves the reading under-keyed on model and years, so it would make
D-537's 11.2%-error holds readable again **without** the judge swap that justifies trusting them —
the precise ordering D-537 forbids ("re-judge ONCE after it").

**(c) Recommended: a stored, self-describing key, written forward only.**
1. Record the new key components **into `raw_output_json`** at write time — the column is already
   the home for gate-side provenance (`final_gate.py:105-107` already writes `gate_facts_key`
   there), it is not trigger-protected against new keys inside the JSON, and it requires **no
   schema migration**.
2. Read by preferring the new key when present and **falling back to absent** when it is not. Old
   rows then read `unclear` — which is where they already are today, so **the migration is a no-op
   by construction and cannot regress anything**.
3. Fill forward naturally: the next ordinary judging pass writes the new key for the leads that
   matter, at `gate.depth` per tick.

**Ordering, which is load-bearing:** T153 (the judge swap) **before** T152's read-side change.
Landing (b) or (c)'s read-side half first would restore 117 holds derived from the model D-537
measured at an 11.2% false-negative rate against the target population. Swap the judge, re-judge
once, *then* make the readings durable.

---

## 5. Acceptance, when code is eventually written

- A test that a `rules_hash` change **no longer** hides a seniority reading — with the inverse arm
  (a `posting_version_id` change still does), because a read that finds everything is as broken as
  one that finds nothing.
- A test that a **model** change **does** hide one, mirroring
  `test_a_gate_row_judged_by_another_model_is_not_fresh`
  (`tests/pipeline/test_llm_cache_identity.py:222-235`) and its same-model control at `:237-248`.
- A test that `total_years_experience` changing hides one, while an unrelated fact
  (`highest_degree`) does not. **This pair is the design's whole claim** and neither arm exists
  today.
- There is **no** `tests/unit/test_eligibility_read.py`; the nearest pin is
  `tests/unit/test_gate_handshake.py:198-255`, which asserts `under_wrong == {}` for a mismatching
  `rules_hash` — **on `current_gate_verdicts` only**. Nothing pins the seniority read's scoping at
  all, so the first commit should add the missing baseline before changing behaviour.
