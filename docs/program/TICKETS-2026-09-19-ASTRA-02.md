# Tickets from astra review 02 (the apply-lane stack) — verified, ranked, PR-sized

Source: `.agent/astra/findings/02-apply-lane-stack.md` (gitignored; the review of checkout
`b7a9c3ab`, written 2026-09-19). Consumed per STATE 2026-09-19b: both falsifiers were re-run by the
orchestrating session (`02-gate-probes.py`, `02-judge-probes.py`, exit 0 — **every table reproduced
byte for byte**), and every cited `file:symbol` was opened by a read-only Opus verifier on the
enterprise seat (`.agent/astra/verify/02-report.md`, 54 turns, $3.56). **All eight findings are
CONFIRMED against the code.** Numbering continues the sequence (T105 was the last from review 01).

One PR per ticket, one worktree per PR, `make check` per PR. **Every ticket's acceptance test must
FAIL against the current code before the fix is counted** — and for T106, T108 and T112 the red was
re-run INDEPENDENTLY by the orchestrating session against unchanged `main`, not taken from the
executor's own report (9 failed / 15 passed, 12 failed / 18 passed, 15 failed / 285 passed).

**Re-key rule.** NOTHING in review 02 touches the four digested engine modules (`catalog.py`,
`detect.py`, `resolve.py`, `engine.py`) or `rules.yaml` — verified: `engine.py:58` returns exactly
those four, all `eligibility/`-local. **So none of these tickets moves `engine_version`,
`rules_hash` or `profile_hash`, none owes a ledger drain, and none restarts a confirm clock.** They
move two other things instead, and the file says which each time: the GATE lane's freshness key
(costing one bounded re-judge) and ROUTING (which lane a delivered lead lands in), the second of
which the manifest cannot currently see at all — T111.

| # | ticket | finding | size | tier | moves |
|---|---|---|---|---|---|
| **T106 SHIPPED** | the gate judge fails open at every seam it claims to | F2 | M | seat | nothing — no re-judge |
| T107 *(in flight)* | item/field coverage counters, and a partial outage escalates | F4 | M | seat | reporting only |
| **T108 SHIPPED** | the gate row carries the judge MODEL; the freshness read requires it | F1 (model half) | S-M | seat | gate freshness key; ONE re-judge, collapses into T99's |
| T109 *(in flight)* | standing delivery gets the title-seniority hold AND the judge's negative | F3 | M | seat | routing only |
| T110 | B8 reads the FINAL lane cohort, not the render denominator | F6 (counter half) | S-M | cheap+spec | reporting only |
| T111 | a lane-policy fingerprint, separate from the disposition identity | F6 (fingerprint half) | M | orchestrator design | adds a sixth manifest value; moves no existing hash |
| **T112 SHIPPED** | three lexical normalizations: Unicode accents, F/H order, level separators | F5 (narrow) | S | seat | routing only, invisible until T111 |
| T113 | stale gate negatives get a bounded refresh instead of suppressing their own repair | F1 (reachability half) | L | orchestrator design | gate rows; a new budgeted queue |

**F7** (a targeted second reading, revisiting D-477's never-rejudge rule) and **F8** (portability)
are not tickets. Both are ruled in §3.

---

## 1. What was verified, and what was MEASURED here

Both falsifiers reproduced exactly on `b7a9c3ab`, including every row of astra's five tables. The
verifier's per-symbol table is in `.agent/astra/verify/02-report.md`.

**What astra missed (all four change a ticket, none changes a verdict):**

- **F1 — the one manual repair path is blocked by the very filter F1 names, so the finding is
  STRONGER.** `cli/eligibility_cmd.py:739-791` (`eligibility gate request`) sources its population
  from `rank_open_postings(...).visible` (`:779-781`) — i.e. through the same `== "ineligible"` hide
  and the same `include_handled=False`. The verifier's full caller census found **no nightly
  refresh, no drain and no web action that re-judges anything**. A stale gate negative genuinely
  cannot reach its own repair.
- **F2 — a SECOND uncaught raise site, and it fires AFTER the write commits.**
  `_tally_eligible_and_uncertain` calls `accept_oracle_verdict` again at `gate_judge.py:373` (from
  `:344`), outside the transaction that has already committed. Astra named only
  `apply_gate_verdicts`. Folded into T106.
- **F2 — the blast radius is NARROWER than astra states.** `run_pipeline`'s `finally:`
  (`runner.py:2652`) still runs the form sweep, the funnel, the queue sync and the morning digest.
  What an escaping exception actually costs is the day's tailoring/render, its NEW deliveries, the
  `seen` dispositions and the heartbeat. The direction (fail-open reversed) stands; the stated
  consequence overshoots. T106 says so.
- **F3 — a FIFTH omitted argument.** `delivery/api.py:436-446` (`_row_json`) omits `posting_closed`
  as well as `seniority_above_band`, so the detail pane can never report `_closed`. Folded into T109.
- **F6 — a final-lane cohort already EXISTS in one place.** `delivery_queries.apply_lane_placements`
  (`:824-838`) already re-runs `lane` against today's state and is documented as doing so. It is not
  wired to B8, but it is not absent. **This makes T110 materially cheaper** — reuse it, do not build
  a second one.

**Measured here, on the live store, read-only (`sqlite3 ?mode=ro`), with a null control:**

- **F6 did NOT bite run 467, and B8's `25` stands.** The probe first reproduced the funnel exactly
  (40 `resume_tailored` artifacts, 15 `pending_tailor`, **25 rendered** — the funnel's `pdf 25 -> 25`).
  Of those 25, **7 have a fetched application form and 0 match a form hard stop**; the 15 review-lane
  leads carry 3 fetched forms and 0 hits. **Null control:** the same `match_questions` call over all
  **48** fetched forms in the store returns **3** hits (`citizen_or_green_card`, `us_person_export`,
  `citizenship_required` — the three T91 leads of 2026-09-17), so the zero is a real zero, not a
  broken apparatus. The base rate is ~6% of fetched forms, so the defect WILL bite — T110 is still
  owed — but **run 467's B8 volume reading of 25 against the bar of 20 is not an overcount**, and
  next-action 3 can be ruled on the number as recorded.
- **F3's judge-negative half is 12 leads, today.** Under the current identity, **45** delivered
  posting-versions carry a current judge `ineligible`; **17** of those also carry a deterministic
  `eligible`, which short-circuits `review_gate.classify` at row 9 into the APPLY lane and cannot be
  held by anything below it. Of the 17, **12 are open and unapplied** (5 are closed and drain
  elsewhere). This is the same shape D-511 recorded as 19; it is still live.
- Delivered-lead gate coverage under the current identity: 632 eligible · 210 uncertain ·
  45 ineligible · 97 with no current-identity gate row at all (887 of 984 covered).

Not re-derived: D-511's and D-514's percentages, the live prevalence of any F5 lexical defect, and
astra's judge-repeatability arithmetic.

---

## 2. Tickets

### T106 — the gate judge fails open at every seam it claims to (F2)

`llm/gate_judge.py`'s docstring promises D-074's contract at every seam; three classes of external
defect escape it and abort the run, reversing D-477's fail-open direction. Reproduced: outer `[]` or
`null` raises `AttributeError` out of `_judge_batch` (`envelope.get` at `:180` precedes any mapping
check, and `AttributeError` is not in the `:237` catch tuple); `decision="move"` clears the parser
and raises `OracleVerdictError` from `accept_oracle_verdict` (`oracle.py:236`) inside
`with engine.begin()` at `:335` **and again after the commit at `:344`/`:373`**;
`PermissionError(EACCES)` and `OSError(E2BIG)` escape the three-clause process catch at `:228-234`;
`confidence="nonsense"` is accepted and persisted.

Fix: establish the envelope is a mapping before reading it; validate `decision` and `confidence`
against the existing closed vocabularies INSIDE the batch boundary, raising the already-caught
`OracleVerdictError`; widen the process catch to the `OSError` family while keeping the three
readable notes; and run `accept_oracle_verdict` over every verdict BEFORE `engine.begin()` so one bad
item cannot unwind three good batches or abort after the commit. Do NOT touch `_seniority_fit` —
its leniency is deliberate (`gate_judge.py:148-154`) and T107 counts it instead. Do NOT broadly
swallow store failures.

**No `POLICY_VERSION`/`PROMPT_VERSION` bump, deliberately.** Nothing already persisted is wrong:
`confidence` is consulted only on the `ineligible` path where `high` is already required, and a bad
`decision` never reached the store — it aborted the run. A bump would buy a full re-judge for no
correction. Controls that must stay green: `tests/pipeline/test_gate_stage.py:278,307,329,361,383,410`.

**The tightening's risk is measured at NIL.** Over **1,999** stored gate verdicts in the live store
`confidence` takes only `high` (1,430), `medium` (526) and `low` (43) — 1,999 exactly — and
`decision` only the three catalog members. The production judge has never once spelled either field
outside its catalog, so the "a batch of 13 could fail open on a spelling" objection is theoretical.
T107's counters are what will show it the first time it is not.

### T107 — item/field coverage counters, and a partial outage escalates (F4)

`run_gate_stage` increments `failed_batches` only on a whole-batch `None` (`:322-328`); a partial
answer appends a note and counts nothing, and `_seniority_fit` (`:156-157`) folds absent and
out-of-catalog answers into `unclear` with no record. `GateCounters` (`run_funnel.py:711-716`) has no
due/sent/cached/missing fields, so zero judgments cannot be told from full cache coverage. And the
gate stage's notes land on `summary.errors` at `runner.py:2222-2229`, **562 lines before**
`escalatable_from = len(summary.errors)` at `:2784` — so only the whole-batch alert at `:2966` is
inside the escalated slice.

**This is not hypothetical: run 467 recorded `batch 5/7 partly failed open, 1 of 13 verdicts missing
(label 302235)` and `gate_failed_open` stayed 0.** No escalatable alert fired for it.

Fix: reconcile candidate-level counts (`candidates`, `cached`, `sent`, `missing_items`, and a
seniority split that keeps a REAL explicit `unclear` apart from an absent or invalid one); carry them
to `GateCounters` and the funnel's gate block; add ONE soft alert in `runner.py` between `:2784` and
`_emit_morning` at `:2986`, beside the one at `:2966`. Coverage is measured against `sent`, never
total leads; `sent == 0` abstains. Delivery stays fail-open; no run becomes fatal. New counters are
ABSENT rather than `0` on a pre-instrumentation funnel.

### T108 — the gate row carries the judge MODEL (F1, model half) — **land this BEFORE the model move**

`record_gate_verdict` writes `provider=None, model=None` (`final_gate.py:102`) into columns that
already exist; `gate_engine_version()` is policy+prompt only (`:29-30`); `gate_facts_key` is facts
only; `build_identity` takes no model. So **nothing in the gate row key varies with
`settings.gate.model`.** `_GATE_RELEVANT` does include `model` (`manifest.py:162-167`), so changing
the judge moves `config_hash` — and invalidates not one gate row.

**Consequence for STATE next-action 4:** the pending judge-model change would reach NEW leads only.
Every standing lead already judged stays "fresh" forever, so the migration is silently partial and
no per-row provenance exists to audit which model decided which lead.

Fix, mirroring T99 exactly: `record_gate_verdict` writes the configured provider/model to the
existing columns (not `raw_output_json` — `facts_key` went there only because eight display readers
join on the deterministic identity; `model` has a real column and no such constraint);
`current_gate_verdicts` gains a keyword-only `model`, narrowed INSIDE the `max(id)` subquery exactly
as `facts_key` is, defaulting to `None` so every display reader's SQL stays byte-identical;
`run_gate_stage` passes `settings.gate.model`. `gate_engine_version()` itself must NOT change or the
`LIKE 'final_gate:%'` prefix reads start fragmenting.

**Cost, and the reason to land it tonight: T99 already forces exactly one re-judge of the delivered
slate on the next run, for the same legacy-row reason. If T108 lands first, the two collapse into
one.** Controls: `tests/pipeline/test_gate_stage.py:458,952,796,920`;
`tests/unit/test_final_gate_persistence.py:101,134,55,79`.

### T109 — standing delivery gets the title hold AND the judge's negative (F3) — **RULED**

`_lead_lanes` computes `seniority_above_band` and passes it (`runner.py:1449-1456`). The four
standing call sites — `queue.py:425-436`, `api.py:436-446`, `delivery_queries.py:768-779` and
`:825-836` — all omit it, and it defaults `False` (`review_gate.py:151`). `api._row_json` omits
`posting_closed` too. All four also reduce the judge to `judge_eligible=row.judge_verdict ==
"eligible"`: `classify`'s signature has **no judge-negative parameter at all**, so a current,
high-confidence, span-carrying rejection cannot hold anything.

**Owner's ruling, 2026-09-19 22:3x: a current judge `ineligible` HOLDS a standing lead in review,
under its own `ReviewReason` member.** It is never equated with a deterministic deletion and never
dropped — D-380's fail-open direction. **Live size: 12 open, unapplied leads today** (measured
above); the daily arrival number is unaffected, because `top_cmd` already hides fresh gate-ineligible
postings from the shortlist.

Design: one identity-scoped lane input carrying title-band state and the full active judge result,
built once per read and passed to every caller; **remove the `= False` defaults from `classify` for
the production-relevant inputs** so mypy, not prose, enforces that a caller cannot silently drop one.
The title band is config- and profile-dependent (leveling catalog, per-company schemes, target band,
field tier — `runner.py:1428-1441`), so it must be COMPUTED live, never persisted: the whole point is
that a later band change re-routes standing leads. `sync_queue(conn, *, root, owner_name)` has no
settings today — plumbing them is the bulk of the ticket. Preserve the current hold ordering
(closure, then form, then the rest) and the `eligible` short-circuit's position.

The AST guard `tests/unit/test_review_gate.py:783/:821` must be extended to require the title
argument and `posting_closed`, but the BEHAVIOURAL tests are the proof: flip a delivered fixture's
target band from `any` to `entry` and assert pre-tailor classification, queue placement, API reason
and `apply_lane_placements` all agree on its senior title; independently persist a current judge
rejection on a standing deterministic-`eligible` fixture and assert a review hold everywhere. Controls:
an eligible judge, an uncertain judge and an absent row must each behave as today
(`test_review_gate.py:632,865,80`).

### T110 — B8 reads the FINAL lane cohort (F6, counter half)

`pdf.entered = apply_lane_tailored = sum(not lead.pending_tailor)` (`run_funnel.py:1417`, `:1820`),
and `pending_tailor` is written once at `runner.py:3543` before the tailor loop and never rewritten —
while `_sweep_form_questions` runs at `:2752`, after the render and before the funnel at `:2786`. A
lead rendered into the apply lane and then form-hard-stopped in the same run is still counted.
`METRICS.md:12924` records `pdf.entered` as B8's daily instrument.

**Cheaper than astra thought:** `delivery_queries.apply_lane_placements` already re-runs `lane` over
today's state. Wire B8's volume to a final-lane cohort built from it, keep `pdf.entered` as the
render-stage denominator it correctly is, and record the cohort's posting/job ids and review reasons
so audit sampling draws from the same population B8 counts. Add a B8 volume diagnostic distinct from
`check_apply_lane_drought`, which is a ZERO-detector (`apply_lane_drought.py:156-159`) and cannot see
a 19.

**Measured: this did not bite run 467** (0 hard-stop hits among its 25 rendered leads, against a
store-wide base rate of 3 in 48 fetched forms). Fix the instrument; do not re-open the 25.

### T111 — a lane-policy fingerprint, separate from the disposition identity (F6) — **RULED**

`_GATE_IRRELEVANT` (`manifest.py:168-187`) excludes `seniority_hold` and `batch_size`; the probe
confirms flipping `seniority_hold` leaves `config_hash` byte-identical. Two runs can therefore carry
identical five-hash manifests and route every lead differently — and B8's 14-day evidence is read
against those manifests.

**Owner's ruling, 2026-09-19 22:3x: a SEPARATE fingerprint, not a reclassification.** Record a sixth
value beside the five hashes covering the routing knobs (`seniority_hold`, the lane caps, and the
rank/review gate modules, which `digested_modules` deliberately excludes). Permanent dispositions keep
their current identity, so changing a hold reopens nothing; B8's evidence gains a field to segment on.
`tests/unit/test_manifest.py:57` already fails closed on an unclassified field — extend that closure
to the new set. **T112 lands before this and is invisible until it exists; note that in the record.**

### T112 — three lexical normalizations in the rank gates (F5, narrow)

Reproduced: `Montréal` reads `unknown` and an otherwise eligible SWE lead reaches APPLY, while
`Montreal` reads `non_us` and routes to review (`location_gate.py:101-102` casefolds and never
normalizes; the module imports no `unicodedata`); `Software Engineer (F/H)` carries no foreign marker
while `(H/F)` does (`foreign_ad_gate.py:56` is H/F-only and `_DACH_GENDER_MARKER`'s class excludes
`h`); `Level-5` and `Level: 5` read `in_band` while `Level 5` reads `above_band`
(`seniority_gate.py:49` requires `\s+`). Fix each at the pattern, with paired metamorphic tests.

**Measured AFTER it shipped, and it matters: the level-separator half has NO live population.**
Across 261,626 open postings the old pattern matches 1,010 titles and the widened one 1,011 —
**one new match, and it is a false positive** (`Relationship Banker - (multi- level - 35 hrs)`), on
a title the role gate vetoes long before the ladder is read. Kept, because the asymmetry is a latent
defect and `above_band` holds for review rather than dropping — but **it is not a win and must never
be cited as one.** The 33/33 measured-unambiguous figure behind the original pattern was taken on
the whitespace form only and this does not re-establish it.

**Out of scope, deliberately:** the composite-title role asymmetry (`Software Quality Engineer` →
`swe` but `Quality Engineer, Software` → `uncertain`, and the right-only `(?!.*\bsoftware\b)`
lookahead). Magnitude unmeasured; astra itself says a parser rewrite is not justified by the examples.
Measure it before designing it.

### T113 — stale gate negatives get a bounded refresh (F1, reachability half) — design first

`top_cmd.py:540-545` reads `current_gate_verdicts` with NEITHER freshness argument, then hides on
`== "ineligible"` at `:724-728` and promotes to tier 0 on `== "eligible"` at `:700-703`.
`run_pipeline` ranks (`:2083`) before it judges (`:2222`), so T99's exact freshness check only ever
sees the leads the historical read already let through. An old-policy `ineligible` therefore
suppresses its own repair indefinitely, and the one manual path (`eligibility gate request`) reads
through the same hide.

This explicitly disagrees with **D-512's classification of `top_cmd` and `_lead_lanes` as display
readers** — both HIDE and PROMOTE on that read, which is a decision — and narrows D-512's claim that
every lead becomes reachable after a bump.

Design sketch: one shared ACTIVE-gate read keyed by version, facts and model (T108's key), consumed
by ranking and lane promotion; historical verdicts stay readable for display with their provenance
and freshness status. A stale negative becomes a REVIEW HOLD pending re-read rather than a
suppression, and feeds a separately bounded refresh queue that consumes part of the existing judge
budget — never a whole-corpus scan. Existing coverage to respect:
`tests/unit/test_rank_gate_filter.py:142`, `:116`; `tests/unit/test_rank_verdict_tiers.py:107,136,153`.
**97 of 984 delivered posting-versions currently have no current-identity gate row at all** — size the
queue against that, not against the corpus.

---

## 3. Owner decisions — all three RULED 2026-09-19

1. **A current judge `ineligible` holds a standing lead in review, under its own reason.** Folded
   into T109. 12 open unapplied leads today.
2. **A separate lane-policy fingerprint**, not a reclassification of `_GATE_IRRELEVANT`. T111.
3. **F7's targeted second reading: NOT NOW — ship the judge-model move first.** One variable at a
   time; the move needs T108 anyway; re-read repeatability on the new model before pricing a second
   reading. 65.6% self-agreement is not evidence that 34.4% are wrong, and if production becomes the
   same model used to audit it, the experiment loses its independent arm.

**F8 (portability) is DROPPED, not deferred — D-477 point 4 already rules it: done is single-tenant,
portability is v2.** All seven hardcoded assumptions are confirmed at the quoted lines (hard location
means US; delivery enforces US even in soft mode; `catalog.fields["software"]` is unconditional;
`GENERIC_TITLE_TOKENS` is mechanism; the judge's body-seniority question is always early-career; the
`citizen_or_green_card` form surface carries no US qualifier while its sibling `citizenship_required`
does; the production judge reuses the answer-key's all-blocker policy). **Record them as the concrete
v2 boundary; build nothing now.** Astra's ≤1-year-ceiling concern is NOT a code leak —
`Policy.near_miss_years_ceiling` is per-user data (D-479/D-480).

---

## 4. Recorded, not ticketed

**Astra's one ranking proposal, from its "checked and sound" section.** It found no case for a
learned ranker, an employer-size proxy or a provider-prestige penalty, and confirmed that recency,
the generic-token title guard and the pseudo-count skill prior already work as documented
(`rank/explain.py` distinguishes assumed coverage from observed matches; zero recognised skills take
the neutral prior rather than a renormalisation bonus). Its single testable suggestion: **rank on
CURRENT APPLY READINESS — the existing requirement/gate/hold state — within eligibility tiers, with
an explicit bounded review allocation so unresolved leads still drain.** Compare blind usable yield
at equal `top`/judge budget before adopting it. Not ticketed: it is a hypothesis with no measurement
behind it, and T109/T110 change the very state it would rank on. Revisit after both land.

**F5's composite-title asymmetry needs a MEASUREMENT before it needs a design.** `Software Quality
Engineer` reads `swe` (the rescue matches `software` within 40 chars of the role noun), `Quality
Engineer, Software` reads `uncertain` (the rescue is left-only), a long qualifier between them reads
`not_swe`, and the inverse reads `uncertain` again because `_DENY_DISCIPLINE`'s
`(?!.*\bsoftware\b)` lookahead is right-only. Only the third is harmful — it HIDES the lead. Count
that class on the open corpus first; astra itself says a parser rewrite is not justified by the
examples alone.
