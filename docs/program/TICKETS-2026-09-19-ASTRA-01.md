# Tickets from astra review 01 (the deterministic eligibility engine) — verified, ranked, PR-sized

Source: `.agent/astra/findings/01-eligibility-engine.md` (gitignored; the review of checkout
`029f638d`, written 2026-09-19). Consumed per STATE 2026-09-19b: every falsifier was re-run by the
orchestrating session (all six probes reproduce, exit 0), and every cited `file:symbol` was opened
by a read-only Opus verifier on the enterprise seat (`.agent/astra/verify/01-report.md`, 55 turns,
$4.73). **All ten findings are CONFIRMED against the code.** Three things astra missed change the
cost of two fixes and are folded into the tickets below. Numbering continues the sequence (T97 was
the last merged).

One PR per ticket, one worktree per PR, `make check` per PR. **Every ticket's acceptance test must
FAIL against the current code before the fix is counted.** Tier as in `TICKETS-2026-09-17.md`.

**Re-key rule.** `catalog.py`, `detect.py`, `resolve.py`, `engine.py` are digested into
`engine_version`; `rules.yaml` is `rules_hash`. Any ticket marked **engine batch** moves one or both,
re-keys the ledger, owes a drain, and restarts the confirm clock — so they land TOGETHER with STATE
next-action 4 (the Sonnet judge move, T92, `education_timing`) as ONE bump, never one at a time.
T98 and T99 move neither and may ship first.

| # | ticket | finding | size | tier | re-keys |
|---|---|---|---|---|---|
| T98 | abstain monitor: drop the two obsolete "structurally undecidable" exemptions, render rates from counts | F8 | S | cheap+spec | nothing |
| T99 | the final-gate cache identity covers every fact the judge reads | F7 | M | orchestrator (design below), cheap+spec to build | gate version only; rejudge the current slate |
| T100 | resolvers validate the four consumed catalog-choice members; out-of-catalog abstains | F5 | S-M | cheap+spec | `engine_version` — **engine batch** |
| T101 | two work-auth patterns require an applicant obligation; a years span followed by its own subject is not a bar | F3 | S-M | cheap+spec | `rules_hash` (+`engine_version` if `detect.py` moves) — **engine batch** |
| T102 | the export-control "US person" predicate gets its own `implies`; EAD without sponsorship need abstains | F6 | S | cheap+spec | `rules_hash` + `engine_version` — **engine batch** |
| T103 | same-span duplicate parses are subsumed, not treated as a contradiction | F2 (narrow) | M | orchestrator spec, cheap+spec to build | `engine_version` — **engine batch** |
| T104 | the two document-scoped degree escapes get bounded reach | F4 | M | orchestrator (design below) | `rules_hash` + `engine_version` — **engine batch** |
| T105 | bounded heading context for bullet lists: requiredness, negation, jurisdiction, explicit OR | F1 | L (three PRs) | orchestrator | `engine_version` (+`rules_hash`) — **engine batch or the one after** |

F9's ten regressions are not a ticket: each is the red-first test of the ticket it maps to (§2.1).
F10 (a verdict-neutral coverage sidecar) is an owner call (§3), not a ticket.

---

## 1. What was verified

Every table in the findings file reproduced byte for byte on `0d6a80a6` under the review's profile
P (EAD, needs sponsorship, 1 year, master's in CS, no clearance and not obtainable, FTE only,
internships excluded; all seven families blockers; years ceiling 1 — which IS the live value per
STATE 2026-09-18). The verifier's per-symbol table is in `.agent/astra/verify/01-report.md`; the
three F9 distribution numbers it could not compute (857 distinct bodies, median 46 chars, 53/60
patterns observed) were measured by the orchestrator's own run of `corpus_measure.py`.

**What astra missed (raises cost, changes no verdict):**

- **F2.** `tests/unit/test_eligibility_engine.py::test_an_exclusive_group_keeps_presence_semantics`
  pins the two-sentence obtainable-clearance pair as `uncertain`. Astra's full canonicalization
  contradicts it. T103 is therefore scoped to SAME-SPAN duplicates only, which leaves that test,
  `test_a_three_member_group_conflicts_on_any_two_distinct_values`, m0079 and m0171 untouched.
- **F6.** Corpus m1018 pins EAD + `needs_sponsorship=True` under the ITAR predicate as `ineligible`,
  on the catalog's own reasoning (a refugee/asylee EAD holder would not need sponsorship). Astra's
  proposal would flip it. T102 keeps it: only EAD with `needs_sponsorship` False or absent abstains.
- **F3.** `us_citizen_predicate_required` declares no `suppressed_by_sentence` at all; the working
  EEO control survives only through the clause-scoped `not` cue. T101 adds the obligation
  requirement rather than more escapes.
- **F7.** Nothing mitigating: the gate row key is `(posting_version_id, profile_hash, rules_hash,
  engine_kind, engine_version)` and `gate_engine_version()` is policy+prompt only. No facts hash,
  no request hash, `idempotency_key=None`. The finding stands exactly as written.
- **F1 and F4 are one missing layer.** The only document-scoped reach in `detect.py` is
  `suppressed_by` / `abstain_by` over `body_text` — which is what F4 complains about — and there is
  no heading inheritance anywhere — which is what F1 complains about. T104 bounds the first; T105
  adds the second; neither should be designed without the other in view.

Not re-derived: live prevalence of any defect. Astra measured none and the executors cannot read
the store; the orchestrator measures the verdict delta on the ledger re-evaluation when the engine
batch lands (that is the drain's own readout).

---

## 2. Tickets

### 2.1 The ten regressions (F9) and where each lands

| # | text | expected | ticket |
|---|---|---|---|
| 1 | `Nice to have:\n- 5 years of experience.` | eligible, preferred/unmet | T105a |
| 2 | `You must meet either of the following:\n- A master's degree.\nOR\n- 5 years of experience.` | eligible | T105c |
| 3 | `We welcome applicants who are US citizens, permanent residents, and visa holders.` | uncertain, no rows | T101 |
| 4 | `We welcome applicants with or without sponsorship.` | uncertain, no rows | T101 |
| 5 | `Due to ITAR export control regulations, applicants must be a U.S. person.` (EAD, no sponsorship need) | uncertain | T102 |
| 6 | `Must have a Ph.D. in Physics.` (doctorate, computer_science) | ineligible | T103 |
| 7 | `Ability to obtain a clearance is required.` (obtainable=False) | ineligible | T103 |
| 8 | `10 years of experience required. A bachelor's degree or 2 years of experience is required.` | ineligible | T104 |
| 9 | `A PhD is required. A bachelor's degree or equivalent experience is preferred.` | ineligible | T104 |
| 10 | `This is an internship position.` (internship_preference=`spelling_error` via `parse_facts`) | uncertain | T100 |

All ten currently disagree with the expected column (orchestrator's probe run). Each is added to
`tests/pipeline/test_eligibility_corpus.py::CASES` by its ticket, moving the 1,060 pin in
`tools/generalization/fixtures.py:CORPUS_ROWS`. Every ticket also carries its controls: the
inline/list pair must agree, the explicit restrictions (`Applicants must be US citizens.`,
`Must be authorized to work in the US without sponsorship.`) must still reject P, and a JD with
inclusive boilerplate AND a separate real restriction must still reject.

## T98 — abstain monitor: remove the obsolete exemptions, rates from counts (F8)

`reports/abstain.py:STRUCTURALLY_UNDECIDABLE` still names `experience_years:scoped_years_minimum`
and `clearance:clearable_required`; both decide today (`resolve.py:333-339`, `:379-392`) and the
probe produces real `unmet` rows that the report renders at rate 0.0 with the flag set, while
unknown-only rows for the same ids vanish from `fully_abstaining_fixable`. Fix: empty the set (keep
the mechanism — D-253's distinction is sound), and require a decisive-witness check in the test
before any future member is added. Rewrite
`tests/unit/test_abstain_report.py::test_a_structurally_undecidable_rule_is_reported_apart_from_the_fixable_ones`
so it no longer pins the two ids as a literal. Red first: observed decisive rows must render `0%`,
unknown-only rows must count as actionable, zero observations stay never-fired. Reporting only;
no identity moves; ships now.

## T99 — the final-gate cache identity covers every fact the judge reads (F7)

`hashing.py:build_identity` folds a family's declared fields into `profile_hash` only when the
live policy severity is not `ignore`; `gate_handshake.py:build_gate_request` sends ALL facts under
the all-blocker `JUDGING_POLICY`; `final_gate.py:record_gate_verdict` keys the verdict by the
live-policy identity; `gate_judge.py:run_gate_stage` treats a current row at that identity as
fresh. Changing an ignored-but-judged fact therefore keeps a stale clear. The advisory lane has the
same shape for years when `degree` and `experience_years` are both ignored.

Design: the gate's identity is built with an all-blocker policy (the policy the judge actually
applies), not the live one — one call-site change in `final_gate.py` and the matching reader in
`read.py`/`preflight.py:current_identity`, plus the advisory lane's writer in `extract_llm.py`.
Bump `POLICY_VERSION` so old rows are not read as fresh. Red first, isolated store: record a gate
answer, change an ignored-but-judged fact, require a miss and a new request; the unchanged-facts
control must still hit (extend `tests/pipeline/test_llm_cache_identity.py`, whose header says why
the `ignore` case is uncovered today). Cost: every current delivered lead is re-judged once
(~40 leads, ~3 batched calls on the enterprise seat, D-477's bound). No deterministic identity
moves. Ships outside the engine batch; run the rejudge on a night with no other change.

## T100 — resolvers validate the four consumed catalog-choice members (F5)

`facts.py` types `work_authorization.status`, `security_clearance.level`,
`employment_type_preference` and `internship_preference` as bare `str`; the resolvers end in
affirmative fallthroughs (`resolve.py:203`, `:472`, `:579`, `:431-435`), so a typo-valued fact
through `parse_facts` reaches `met`. The verifier confirms the blast radius is exactly these four:
`highest_degree` and `field_of_study` are already guarded by catalog lookup. Fix at the resolver
(the authoritative boundary): compare against the family's `FieldSpec.choices`; an out-of-catalog
value returns `unknown(missing_profile_field:<field>)`. Keep `eligibility_cmd.py:_coerce` as is.
Red first: the four probe rows become `uncertain`; valid choices, including the EAD sponsorship
declarations and a removed-by-override formerly valid value, keep their results.

## T101 — two work-auth patterns require an applicant obligation (F3)

`rules.yaml:303` `us_citizen_predicate_required` fires on `who\s+(?:are|must\s+be)` and
`rules.yaml:419` `no_sponsorship_without_clause` fires on bare `without … sponsorship`, with
`without…sponsorship` an idiom document-wide (`rules.yaml:67-68`), so `_cue_outside` cannot drop
it. Narrow both to an obligation or exclusion surface (`must be`, `only`, `required`, `eligible
only if` …); do NOT add a document-wide `welcome` suppressor. Separately, a years span whose own
sentence continues with a non-applicant subject (`25 years of experience is what our team brings`)
is not a bar: extend the `before_only` subject check in `detect.py:312-315` to look after the span
within the unit. Red first: regressions 3 and 4 plus the subject case; controls: the two explicit
restrictions still reject P, and the mixed-JD control still rejects.

## T102 — the export-control predicate gets its own `implies` (F6)

`rules.yaml:245-249` says the US-person surface admits citizens, LPRs AND protected individuals,
then sets `implies: citizen_or_lpr_required`, whose resolver branch (`resolve.py:221-224`) reads
status alone. Fix: new implies value `us_person_required`; resolver: citizen/LPR → met; EAD with
`needs_sponsorship=True` → unmet (the catalog's own inference, keeps m1018 and D-322); EAD with
`needs_sponsorship` False or absent → `unknown` (the protected-individual arm is undeclared);
needs_sponsorship status → unmet. No new fact. Red first: regression 5; m1018/m1019 unchanged;
the same EAD profile still fails `Applicants must be US citizens.`

## T103 — same-span duplicate parses are subsumed (F2, narrow)

`engine.py:252-257` tests `len(overlap) >= 2` over document-wide implies values and rewrites every
member unknown. When two group members match the SAME span (`Ph.D. in Physics` →
`doctorate_required` + `doctorate_in_field_required`; `Ability to obtain a clearance` →
`clearable_required` + `clearable_leveled_required` + `generic_clearance_required`), that is one
requirement parsed twice, not a contradiction. Spec: before stage 1, within a family, when two
detections in the same exclusive group share a span (equal or one contained in the other), keep
the more specific one (field-qualified over level-only; obtainability over active) and drop the
other. Different-span members keep today's presence semantics — this is what preserves
`test_an_exclusive_group_keeps_presence_semantics`, the three-member two-sentence test, m0079 and
m0171. Red first: regressions 6 and 7 (ineligible), plus the matching-field doctorate (eligible)
and obtainable=True (eligible). The executor runs the whole corpus and reports EVERY golden that
moves; the expected answer is none (m0583, m0430–m0436, m0847 stay uncertain because the surviving
member abstains on the absent fact).

## T104 — the two document-scoped degree escapes get bounded reach (F4)

`total_years_minimum.abstain_by` (`rules.yaml:552-553`) and `doctorate_required.abstain_by`
(`:1352-1353`) are searched over the whole body (`detect.py:317-320`), so an alternative in one
sentence waives an unrelated bar in another. `rules.yaml:674-678` already argues the case for the
scoped-years rule, which uses `abstain_by_sentence`. Astra warns against making every escape
sentence-local because `A master's degree is required. Equivalent experience may be substituted.`
is a real adjacent waiver. Design: a third reach, `abstain_by_adjacent` — the escape may sit in the
same unit or the immediately following unit, never further. Move both escapes to it. Red first:
regressions 8 and 9 (ineligible); the adjacent waiver stays uncertain; reordering unrelated
requirements cannot change which one is waived. Measure the live verdict delta on the batch's
re-evaluation before the ruling is recorded.

## T105 — bounded heading context for bullet lists (F1) — three PRs, orchestrator design first

The highest-leverage finding and the only structural one. `split_units` (`detect.py:105-127`)
returns isolated `(offset, piece)` strings; a heading unit is gone by the time its bullets are
read. Design sketch, to be specified before any executor sees it:

- **T105a — requiredness and negation inherit from a heading.** A unit ending in `:` whose text
  is a catalog introducer cue (`nice to have`, `preferred`, `not required`, `requirements`) sets a
  context that the following bullet units inherit until the next heading or a blank-line
  paragraph break. Regression 1; control: a later `Requirements:` heading ends the inheritance.
- **T105b — jurisdiction inherits from a heading.** `Canada roles:` sets the jurisdiction the
  sponsorship rows are scoped to, so the US profile abstains instead of reading `met`.
- **T105c — an explicit OR between bullets forms an alternative group** rolled up as any-of
  (met dominates, then unknown). Regression 2. Explicit AND stays all-of; an unresolved relation
  stays unknown — never guessed.
- Tables stay out of scope: zero rows → `uncertain` is the fail-safe direction, and F10's sidecar
  is the instrument that would surface them.

Each PR moves `engine_version`; T105a/T105c also add catalog vocabulary (`rules_hash`).

---

## 3. Owner decisions — not picked by default

1. **Sequencing.** Recommendation: T98 and T99 now; T100–T104 join next-action 4's batched engine
   landing as one bump; T105 is designed during that batch and lands in it if the design is ready,
   otherwise in the one after. The alternative — land each as it is ready — costs one ledger
   re-key and confirm-clock restart per ticket.
2. **m0079** (`Active Secret clearance required; candidates must be able to obtain a clearance.`
   → `uncertain`). Ordinary conjunction says ineligible. T103 does not touch it; the question only
   becomes live if F2 is ever widened beyond same-span subsumption. Record the convention or leave
   the golden as is — either is a ruling, not a default.
3. **F10, the verdict-neutral coverage sidecar.** Astra's case: row count cannot express
   coverage (`Must be authorized to work in the US.` + an uncatalogued ten-year bar reads
   `eligible` with one met row). Its proposal changes no verdict and no identity. Build it as an
   analysis instrument, or leave the 33.9% zero-row class measured by the funnel alone.
4. **The shared-resolver extractor pilot (F10's second half)** is a hypothesis astra itself says
   must beat "current judge plus targeted regex fixes" on a labeled full-JD set before activation.
   Not ticketed; revisit after T101–T105 have been measured.
