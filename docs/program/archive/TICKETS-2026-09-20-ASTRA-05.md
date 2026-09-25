# Tickets from astra review 05 (discovery strategy) — verified, measured, ranked

Source: `.agent/astra/findings/05-discovery-strategy.md` (gitignored; written at checkout
`a7bb381a`, 2026-09-20). Consumed against `main` `488f1ce3` — the one intervening commit touches
two lines of `STATE.md`, so no reviewed code moved.

**How this was verified.** Every `file:symbol` was opened by a read-only Opus verifier on the
enterprise seat (`.agent/astra/verify/05-report.md`, **70 turns, $5.19**). **All seven findings
CONFIRMED or PARTIAL; nothing refuted.** No cited line was off except one symbol that does not
exist anywhere: F2's `death_probe._population_predicate` — the real symbol is
`death_probe.py:265 unreachable_by_the_scanner`. Live populations were measured read-only against
the store (`sqlite3 ?mode=ro`) by the orchestrating session, each probe with a control.

One PR per wave, `make check` on the integrated branch. **Every ticket's acceptance test had to
FAIL against the current code before the fix counted.**

**Re-key rule.** NOTHING in review 05 touches the four digested engine modules or `rules.yaml`.
**No ticket here moves `engine_version`, `rules_hash` or `profile_hash`, none owes a ledger drain,
and none restarts a confirm clock.** Watching a company changes CORPUS MEMBERSHIP, not engine
identity (D-522 §2; `reports/manifest.py:_CONFIG_IRRELEVANT`).

## The measurement that reorders this list

**The severity ranking inverts for the THIRD review running** (cf. D-525, D-526).

| finding | astra | live population | the control that makes it a result |
|---|---|---|---|
| **F1 promotion gap** | **improvement** | **120 unwatched scannable boards; +12 in the 2 ticks since the import closed** | 119 of the 120 have been lane-touched at least once; the same first-seen probe over WATCHED boards spans 16 distinct dates |
| F2 scheduler | design-limit | n/a — owner ruled DO NOT BUILD | D-522 measured a LARGER fleet running faster |
| **F3 hiring.cafe all-late discard** | **wrong-now** | **0 of 468 runs** | the only hiringcafe lane failure ever recorded is run 57's all-EMPTY branch; "after its first page" appears in 0 runs |
| F4 Gate 1 instrument | design-limit | code-only | `by_ct` is built for every posting (`:138`) and unioned unconditionally (`:148`) |
| F5 LinkedIn ordering | improvement | not authorized | tracks stay closed |
| **F6 grnh prefix** | **wrong-now** | **249 of 449 seeds unreachable at the default** | `lane_seeds` holds 191 rows at `attempts=1` and 83 at `attempts=3` — the column is dead on THIS path only |
| **F7 admitted ≠ reach** | **wrong-now** | **214 / 1,342 = 15.9%, 27 of 27 funnels** | 0 funnels overcount the other way; a `LIKE` over all of `companies` finds no row on any provider for 11 of run 467's 12 misses |

**Astra's flagship `wrong-now` (F3) has ZERO live population. The finding it filed as
`improvement` (F1) is the one actively refilling.** Run 467 — the program's headline expansion
measurement, cited in D-522 §6 — reports **19 new companies admitted** and **7** of those 19 exist
as company rows.

Two apparatus notes, both recorded before the numbers were used. (1) The F7 probe is a lower bound
on persistence — a row created then deleted would read as an overcount; **27 of 27 funnels in the
same direction** is what makes it a result rather than noise. (2) **B8's volume could NOT be
re-derived from the store**: `job_dispositions` holds only `built` (1,007) and `seen` (219), and
`built` is **40 on every run** — the `--top 40` slate cap, not apply-lane volume. The recorded
9-of-14 stands as the only evidence, which is why Q1 was put to the owner rather than answered.

## What the verifier found that astra did not

1. **F7 has a THIRD call site.** `lanes/jsonld.py:772` settles every admission in one pass before
   any body is fetched, then `:781-785` defers and `:808` emits nothing. Astra named only linkedin
   and hiringcafe, and T140 inherited that. **T140's fix landed in `_apply_lane`, which
   `_apply_lanes:831` calls for every lane, so jsonld is covered by construction** — verified at
   review, not assumed.
2. **F3 is narrower than astra implies, and the identical branch elsewhere is PINNED.** Any facet
   failing on page 0 takes the `except` at `hiringcafe.py:556-568`, which increments `failed`, not
   `late_failures` — so the discard needs EVERY facet to get page 0 and then lose a later page.
   And `lanes/indeed.py:871-897` is the same pattern, where
   `tests/unit/test_indeed_lane.py:1422 test_every_facet_failing_after_its_first_page_raises`
   **asserts the discard**. A shared fix breaks that test deliberately or not at all.
3. **F1's mechanism already ships, so the fix was wiring.** Four writers can set `watched=True`,
   and `lanes/indeed.py:829` already produces `watch=True` for tier-1 convergence — but the Indeed
   lane is dead (`lanes_enabled` defaults to `()`). So no ARMED emitter promoted. Astra's "if
   `companies import` is the only one" is not the case.
4. **`store/queries.py:619 upsert_watched_company` has ZERO callers** anywhere in `src/`, `tests/`,
   `tools/` or `web/` — a dead wrapper. Left in place; flagged, not removed.
5. **F3's blast radius is bounded**, confirming astra's "nonfatal to healthy board scans":
   `runner.py:789-795` catches it, the lane is absent from `reports` rather than present with
   zeros, and the board scan is untouched.
6. **Nothing counted persisted new companies anywhere**, and `companies` has no created-at column
   (`tables.py:42-54`), so before T140 the number was not derivable from the store at all.

## Owner rulings (Mit, 2026-09-20), all priced before asking

- **Q2 promotion gap — CENSUS + AUTO-WATCH.** Reverses D-521/D-522's stage-2/3 refusal for this one
  case. Ships as **T142** (census) + **T143** (auto-watch).
- **Q4 scheduler — DO NOT BUILD.** Scan runtime is not a product constraint.
- **Q3 pizza board — LEAVE IT.** `smartrecruiters:dominos` is company 139, **already `watched=0`**,
  801 postings all `status='open'` = **0.31%** of the 260,306-row open corpus. Astra's main ask is
  already the state; the rows can never close (D-314) and cost 0.31% of eligibility work.
- **Q1 job-apps — GATE 1 MET as recorded, B8 HELD OPEN.** M4's last condition discharged with the
  instrument's stated limitation. No retirement today.

## THE RULING'S REACH IS SMALLER THAN THE GAP — found at review, not in the ticket

**T143's gate can only promote the four BODY-INLINED providers**, because `board is not None` draws
from `_body_inlined_providers()`, which is `build_providers().items()` filtered to
`_BodyInlinedProvider`: **ashby, greenhouse, lever, workable**. Measured against the live store:

| class | providers | unwatched | route |
|---|---|---:|---|
| body-inlined | ashby, greenhouse, lever, workable | **51** | **T143 auto-watch** |
| registry but not body-inlined | workday 44, eightfold 9, oraclehcm 8, smartrecruiters 8 | **69** | **T142 census + human import ONLY** |
| no adapter | jazzhr 84, breezy 15, icims 1 | 100 | correctly excluded, never proposed |
| placeholder | jobapps 1,083, linkedin 757, indeed 710 | 2,550 | never scannable |

**The ongoing leak IS fully closed:** all 12 scannable arrivals since the import were
greenhouse (9) / ashby (1) / lever (1) / workable (1) — exactly the promotable four. The 69 are a
standing one-time backlog for the owner's review, not a leak.

Fleet arithmetic: **1,807 → ~1,858** as hiring.cafe re-encounters the 51 (109 of the 120 were
lane-touched on 09-19 or 09-20, so within a run or two), at ~3.2s/board/run.

---

# SHIPPED — one gated wave on branch `astra05`

- **T140 — F7.** `LaneReport` gains `persisted_new`, the approved subset whose snapshots actually
  landed. `admitted`/`refused` keep their meaning and their names — four tests plus
  `web/src/api/types.ts:560` and `web/src/fixtures/runs.ts:134,159` read `admitted`, so a rename
  was forbidden. Computed in `_apply_lane` as `budget.admitted ∩ {snapshot keys}`, which is an
  intersection rather than a store round-trip and is reached only after `_apply_snapshots` returned
  cleanly. **Intersecting rather than counting snapshots is load-bearing**: an already-stored
  company also lands a snapshot and belongs in neither number. Both false sentences corrected
  (`run_funnel.py:1085-1087`, `:2488-2489`) plus a third the ticket did not name, found by the
  executor: `cli/run_cmd.py:65`. Rendered in the Markdown lane block and the JSON payload.
- **T141 — F6.** `companies discover-grnh` reports its coverage — how many seeds were selectable,
  how many it followed, how many it did not examine — in the document header AND on the terminal,
  and `--limit 0` reads the whole queue. **The executor declined the resume cursor the ticket
  offered, and was right:** the command writes nothing, so a resume token has nowhere to live but
  the operator's hands, and a shifted `(attempts, id)` order would silently skip a batch — the
  exact failure class the ticket exists to close. `_selectable` is shared between the select and
  the new `unresolved_seed_count`, so "not examined" can never mean "the count and the select
  disagree about what is eligible". `limit=None` rather than `0`/`-1` because both of those are
  budgets a caller's arithmetic can produce by accident.
- **T142 — F1, census half.** New `companies unscanned`: read-only, emits the registry format
  `companies import` accepts, `source='user'` rows held back in a review block rather than
  proposed, case-variant and Workday-slice folds so one board is proposed once. **Its mutation #2
  initially did NOT fire, and that found a real defect** — a self-matching `superseded` EXISTS let
  a row match itself as a watched peer, making `watched IS FALSE` redundant; fixed with
  `peer.c.id != companies.c.id` so each clause is independently load-bearing. **Round-tripping
  through the importer's own validator found a second real problem**: a lane-written Workday slug
  the parser refuses would abort the import of the whole file, so refused rows go to an
  `UNIMPORTABLE` review block with the parser's verbatim reason.
- **T143 — F1, the owner ruling.** `hiringcafe.py:collect` sets `watch=True`. The three gate
  conditions are established by code above the line rather than re-checked: **scannable** (`board`
  comes from `_body_inlined_providers()`, keyed by `build_providers()` — the SAME dict
  `scan/coordinator.py:402` looks a watched row up in before appending `unknown provider` to every
  run's errors, so there is no second catalog free to drift from the error site it exists to
  prevent), **not a placeholder** (`LANE_PROVIDER` is not a registry name, so it fails condition 1),
  and **proven live** (`if postings:` — a board that resolved but served nothing is not proven
  live; stage 1's live probe caught 14 dead boards including `greenhouse:embed`). Monotonic:
  `upsert_lane_company` never unwatches on this flag and leaves `name`/`source` alone.

# TICKETED, NOT SHIPPED

- **T144 — F3.** hiring.cafe discards usable partial discovery and conceals lesser degradation.
  **Zero live population in 468 runs, which is why it is not in the wave.** Two halves, and the
  second is the valuable one: (a) return usable entries plus structured per-search health instead
  of raising; (b) record partial degradation at all — `_search` drops the `late_failure` bool at
  `:570`, and `_facet_pages`' own docstring (`:624-625`) admits a facet that fails every page after
  the first is "indistinguishable from one whose results genuinely ended there". `is_silent_outage`
  cannot see it either, because surviving facets resolve bodies. **Constraint:**
  `lanes/indeed.py:871-897` is the identical branch and `tests/unit/test_indeed_lane.py:1422`
  ASSERTS the discard. LinkedIn is unaffected (`linkedin.py:451-453` has no late-failure concept).
  Do not transplant the LinkedIn length/heading body floor onto provider JSON bodies
  (`RETIREMENT-PLAN.md:§7`'s false-positive trap).
- **T145 — F2, reference only.** Owner ruled DO NOT BUILD. What survives as recorded fact: no
  due-time condition on `get_watched_companies`; no interval state on `companies` or `board_scans`;
  `coverage_queries.load_board_coverage` left-joins every watched board to one run, so a
  deliberately skipped board would read as unscanned; **never toggle `watched` to implement
  cadence** — `death_probe.unreachable_by_the_scanner` (`:265`, NOT `_population_predicate`) routes
  `watched=False` open postings into a different liveness mechanism. Revisit only if scan runtime
  becomes a product constraint with a stated discovery-delay budget.
- **T146 — F4.** The Gate 1 recall instrument credits equivalent-role matches as exact recall:
  `per_source_recall_v2.py:148` unions the company/title bucket after and regardless of the
  URL/`by_ident` lookups, and `:138` builds `by_ct` for every posting. For future readings publish
  exact-identity and equivalent-role rates separately, and where BOTH sides carry supported ATS
  identities, do not let a title match rescue a different requisition id. **This does not
  retroactively fail the recorded pass** — Gate 1 is met as recorded under the owner's ruling.
- **T147 — F5.** LinkedIn stays as recorded: Track 1 closed (D-482), Track 2 disarmed (D-437),
  Track 3 refuted (D-453), JobSpy refused again on identical capability. If LinkedIn ever earns an
  experimental allocation, reorder the cards already obtained inside the SAME budget before
  spending one extra request; a metadata score is not eligibility and needs a deterministic
  rotating control. The ~423 refusal count is an opportunity set, not a count of missing useful jobs.
- **T148 — the dead wrapper.** `store/queries.py:619 upsert_watched_company` has zero callers.
  Remove it, or give it the one caller it was written for. Not done here: it is not traceable to
  any review-05 finding and removing it would have widened four executors' diffs.

## Seat spend

**$25.83 over five dispatches** on the enterprise seat: verifier $5.19 (70 turns), T140 $5.01
(76), T141 $5.26 (62), T142 $6.17 (75), T143 $4.19 (61).
