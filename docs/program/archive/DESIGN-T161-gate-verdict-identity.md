# T161 — What a stored gate VERDICT legitimately depends on, for the lane read

**Status: SHIPPED 2026-09-23 as #430 (D-569), both halves, judge holds kept (the owner's ruling, D-566). The build also moved two callers this note missed: the run's lane split (`runner._lead_lanes`) and the ranker's hide (`top_cmd`).** Original status: DESIGN, no code. Needed the owner's read before it was built (D-556; T161's ticket: "Moves
D-537/D-547 territory, so it needs a design note and the owner's read before it's built"). Written
2026-09-22 (session 22f). It is the verdict-side sibling of `DESIGN-T152-seniority-reading-identity.md`:
same question, same test, applied to `current_gate_verdicts`' LANE callers instead of
`current_gate_seniority`.

---

## 0. The ticket's "check first", answered

**Q: does `accept_oracle_verdict(verdict, jd_text, catalog)` make a persisted verdict
catalog-dependent?** Only in one narrow way (`eligibility/oracle.py:accept_oracle_verdict`):
- the catalog is read ONLY through `is_allowed_reason`, which asks whether the judge's `reason` is a
  family id in `catalog.families`;
- it ONLY runs for `decision == "ineligible"`, downgrading to `uncertain` when the reason is not a
  family. `eligible` and `uncertain` pass through untouched;
- the keystone span downgrade after it (`gate_handshake.apply_gate_verdicts`: `ineligible` with no
  span becomes `uncertain`) reads the BODY, never the catalog.

So **a persisted `eligible` or `uncertain` is catalog-independent**. A persisted `ineligible`
depends on the catalog's **family-id set** only, not on patterns, versions or `rules.yaml` bytes.
The eligibility batch (D-555) moved `rules_hash` and left the family set unchanged: 7 families
before and after (`clearance, contract_not_fte, degree, experience_years, internship,
student_status, work_auth`, `ccb52912` vs `6146a41c`).

## 1. The problem

`store/delivery_queries.py:delivered_unapplied` and the detail read (`queue_detail`) call
`current_gate_verdicts(conn, version_ids, profile_hash, rules_hash)`. That read is scoped on
`eligibility_inputs.profile_hash == …` AND `rules_hash == …`, with the display prefix
`engine_version LIKE 'final_gate:%'`. So every rules-only re-key darkens every standing gate
verdict until the T113 refresh re-judges it at 130/run.

**Measured 2026-09-22 (read-only, production `standing_queue_rows`, `.agent/2026-09-22f-session/
t161_measure.py`):**

| read | standing leads with a readable verdict | eligible / ineligible / uncertain |
|---|---|---|
| live identity (today, run 471) | **833 of 970** | 750 / 44 / 39 |
| post-batch identity (run 472 onward) | **0** | — |
| **T161's key (§2)** | **833 of 970** | **750 / 44 / 39**, identical to live |

The dark verdicts cut BOTH ways, which is D-537's lesson:
- the 750 `eligible` are the 0-B promotions. D-556 replayed the lane at 529 → ~206;
- the 44 `ineligible` are judge HOLDS, and they RELEASE under a re-key (D-537's direction).

T161 keeps both. Of the other 137 standing leads, 44 have no gate row at all and 93 have only
legacy rows with `model IS NULL`. T161's key does not resurrect them, correctly: they name no judge.

## 2. Which components a stored verdict legitimately depends on

The same test as DESIGN-T152 §2: *could a change to this component change the correct answer to the
question the judge was asked?* The judge is sent the JD body and `facts_payload(facts)` under a fixed
all-blocker policy (D-461). It is never sent the catalog, the policy severities, or the band.

| component | keep? | why |
|---|---|---|
| `posting_version_id` | **YES** | the verdict is a reading of this immutable body |
| `facts_key` (`gate_facts_key(facts)`) | **YES** | digests the EXACT fact payload the judge was sent. Change a fact and the correct answer can change |
| `model` | **YES** | a different model is a different judge (T108; D-537's 11.2% floor) |
| EXACT gate `engine_version` | **YES** | the prompt/policy the verdict was produced under, not the display prefix |
| `effort` | **NO** | the owner's T155 ruling: a level is a calibration of the same judge, so its old readings stay visible until the refresh replaces them. That is the same rule T152 already applies to seniority |
| `rules_hash` | **NO** | the judge never sees the catalog. Its one catalog dependence is handled at READ time (§3) |
| `profile_hash` | **NO** | it folds in policy severities and the declared-field subset. The judge sees neither: it sees every fact (in `facts_key`) under an all-blocker policy |

**Key: `(posting_version_id, facts_key, model, exact gate engine_version)`.** That is T152's key,
with `facts_key` in place of `years`. The verdict depends on every fact; seniority depends only on
years.

## 3. The one catalog dependence, handled at read time

A persisted `ineligible` whose recorded reason (`raw_output_json.$.gate_verdict.reason`) is not in
the CURRENT catalog's family-id set is read as `uncertain`. That is the same downgrade
`accept_oracle_verdict` would apply today, in the fail-open direction. It costs one set membership
per `ineligible` row, and it makes a family removal (the only catalog change that could invalidate
a stored verdict) exact rather than stranding every verdict. A family ADDITION invalidates nothing:
the stored `ineligible`s were accepted under a subset.

## 4. The pairing the current comment protects, and why it survives

`delivered_unapplied` says: *"Same identity and same version list again, so a lead's lane can never
be decided by a gate verdict from a different evaluation than the requirement summary it is
releasing."* T161 deliberately breaks the SAME-IDENTITY half, so the argument has to be made:
- the requirement flags (`no_requirements_found`, `experience_requirement`) ARE catalog-dependent,
  and stay identity-scoped. After a re-key they are the CURRENT reading;
- the judge's verdict is a statement about (body, facts, judge, prompt), and none of those moved.
  Pairing the current flags with a verdict whose inputs are unchanged is exactly as coherent as
  pairing them with a fresh re-judge of the same inputs, which is what T113 buys at 130/run;
- the same-VERSION half (both keyed on the current `posting_version_id`) is kept. That is the half
  that prevents a verdict about an old body from releasing a new body's flags.

## 5. What changes, and what does not

- **Lane reads only:** `delivered_unapplied` and the detail pane's read. The FRESHNESS read
  (`gate_judge._current_gate_rows`, the never-re-judge filter) keeps its current narrowing
  (`facts_key`, `model`, `effort`, exact version). **T162's switch-back asymmetry is untouched and
  stays parked.**
- **A rules-only re-key no longer dips the apply lane, and no longer releases judge holds.** That
  is the T152 ruling, which the owner already accepted for seniority (D-555: "T152 keeps all 833
  standing seniority readings through the re-key"), extended to the verdict.
- **The re-judge SPEND is NOT ended by the lane-only form.** The freshness read
  (`gate_judge._current_gate_rows` → `current_gate_verdicts(..., *identity, engine_version=…,
  facts_key=…, model=…, effort=…)`) is ALSO scoped on `(profile_hash, rules_hash)`. So after a
  rules-only re-key, the T113 refresh still sees every standing verdict as stale and re-judges it at
  130/run, and the daily gate still re-sends its whole slate (D-547's +8 min). The lane-only form
  keeps the lane lit WHILE that happens; it does not stop it. See §8 for the two-half option.
- **No migration.** Every row since T108/T155 records `model` and `facts_key`. Legacy rows
  (`model IS NULL`) match nothing, exactly as they already match nothing in the freshness read.
- **No `engine_version` or `rules_hash` move.** `read.py` and `delivery_queries.py` are not
  digested: `engine_version()` hashes exactly `catalog.py`, `detect.py`, `resolve.py` and
  `engine.py` (`eligibility/engine.py`). No re-judge, no drain.

## 6. Ordering: why T161 goes before T163 and any engine bump

T163 (a duplicate `preferred` row) edits the detector, which is a digested engine module. That
re-keys `engine_version`, which re-keys every evaluation. **The next re-key after run 472 dips the
lane again unless T161 has landed.** So T161 lands before T163, and before any other engine change.

## 7. Tests the build must carry (red first)

1. **The re-key, red on current code.** Standing lead, judge `eligible` under identity (P, R1); the
   catalog re-keys to R2 with the family set unchanged. The lane read still returns `eligible`, and
   the lead stays in the apply lane.
2. **Facts changed:** a different `facts_key` means no verdict (the lead falls back to review).
   **Model changed:** no verdict. **Version changed:** no verdict.
3. **Family removal:** stored `ineligible` with reason `internship`, the catalog drops
   `internship`, and the read returns `uncertain`. Control: the reason is still in the catalog and
   the read stays `ineligible`.
4. **Effort changed:** the verdict is still read (the T155 ruling, pinned from the lane side).
5. **Freshness unchanged:** `run_gate_stage`'s never-re-judge filter still narrows on
   `facts_key`/`model`/`effort`/version. Pin that T161 did not route it through the new key.
6. **Parity:** the list row and the detail pane return the same gate verdict for one lead (the T127
   property).

## 8. For the owner

- **Build T161 (recommended)?** It ends the dip on this and every later rules-only re-key, keeps the
  44 judge holds a re-key would release, and costs no LLM spend.
- **Lane-only, or lane + freshness?** The lane-only form ends the dip. Also keying the FRESHNESS read
  on the same judge inputs (identity dropped; `facts_key`, `model`, `effort`, exact version kept)
  ALSO ends the wasted re-judge on every rules-only re-key: no 130/run refresh of unchanged inputs,
  and no +8 min gate cache re-send. It touches T108's pinned freshness read, but not its narrowing
  inside `max(id)`, which is T162's separate asymmetry. Recommended: **both halves**, since the spend
  buys verdicts on byte-identical inputs.
- **The judge-hold half is a real choice.** On 2026-09-22 (D-537) you chose NOT to restore released
  holds, because haiku's seniority readings had an 11.2% entry-level false-negative floor. The
  judge is now `sonnet`, whose apply-lane precision is unmeasured (D-548), and T152 already keeps
  its SENIORITY holds through a re-key. T161 would do the same for its `ineligible` verdicts (44
  today). If you want verdict holds to keep releasing on a re-key, T161 can key only the `eligible`
  and `uncertain` readings, at the cost of a split rule.
