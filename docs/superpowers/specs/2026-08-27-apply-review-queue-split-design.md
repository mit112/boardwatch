# Apply / Review queue split — design

**Date:** 2026-08-27
**Status:** approved in chat (owner: Mit), pending spec review
**Branch:** `feat/apply-review-queue-split`

## Problem

The delivery queue (`~/boardwatch-queue`, the D-318 copy layer) is meant to be a
**blindly-appliable** list. It is not. A live read of the on-disk queue found **383 folders,
only 27 `verdict=eligible`; 314 (82%) are `uncertain`**. Reading random JDs, roughly one in three
was clearly not appliable — e.g. Hyatt "Front Office Agent" (hotel front desk), Allstate "Field Auto
Appraiser" (auto-collision estimating), KAYAK "Associate Java" (Kaunas, Lithuania), Cadence
"Principle Software Engineer" (253-char stub body, located Zhubei, Taiwan).

**Root cause:** the queue already excludes `ineligible` (D-321), but `uncertain` rides along with
`eligible` into the apply queue. The delivery layer has no notion of "not sure — you should look
before applying."

Owner rulings (2026-08-27):
- Apply queue = `eligible` ∪ **verified** `uncertain`.
- Non-verified `uncertain` → a **review lane** the owner skims, never blind-apply.
- Borderline early-career (2-3yr) roles belong in the **review lane** (Phase 2).
- Do **not** loosen the `experience_years` gate wholesale (high blast radius; D-319/D-320 already
  tuned it). Phase 2 reclassifies only *low* thresholds to `preference`.

## Approach

Add a **third destination on the same predicate** that already splits the queue, rather than a
second cleanup loop. Today `_sync_locked` builds the on-disk queue from `delivered_unapplied` and
drops `ineligible` into `_ineligible` (`queue.py:363-367`). We extend exactly that classification:
an `uncertain` row is routed to a new `_review` lane unless it passes a "blindly-appliable" check.

Rejected alternatives:
- **Expand the verdict catalog** (e.g. add `uncertain_appliable`) upstream — `verdict` is a closed,
  keystone-governed set (eligible/uncertain/ineligible). Do not widen it.
- **A separate post-sync move loop** — two sources of truth over the same rows; the module docstring
  makes DB-authoritative single-source a contract.

**Key simplification:** after the 2026-08-27 facts (`security_clearance.obtainable=false`,
`field_of_study`, `degree=blocker`, plus D-322 citizenship), clearance / experience / work-auth /
citizenship all resolve as blockers → `ineligible` → already excluded by D-321. The uncertain leaks
that remain are the **ranker fail-opens**: location `unknown` passes the hard US gate
(`location_gate.py` fails open on unclassifiable, by Mit's visa ruling), and role `uncertain` passes
(`top_cmd.py`). Both are recomputable at delivery time with pure functions — **no new eligibility
plumbing for Phase 1.**

## Phase 1 — the apply/review split (no engine change)

### Classification
A new pure function decides the lane for a delivered row:

```
lane(verdict, locations, title) -> "" (apply) | "_review"
  eligible                          -> ""          # always apply
  ineligible                        -> "_review"   # excluded upstream; defensive
  uncertain OR None (unevaluated):                 # None treated like uncertain (see below)
     classify_location(locations) == "non_us"  -> "_review"   # CONFIRMED foreign only; fail open on unknown
     role_verdict(title)[0] != "swe"           -> "_review"   # not positively software (Hyatt/Allstate)
     otherwise                                 -> ""          # verified-enough -> apply
```

**Location fails open on `unknown`.** Only a *confirmed* `non_us` lead is demoted; a bare
`"Remote"` (and any location the classifier cannot place) reads `unknown` and stays in the apply
queue — the same visa-ruling fail-open the hard US gate uses (never blind-drop/blind-demote an
unplaced lead; "Remote" is most of the SWE set). A genuinely foreign city the classifier does not
recognise (e.g. an unlisted "Kaunas Office", "Zhubei") reads `unknown` and slips through here; that
is a `rank/location_data` coverage gap to close with the D-294 curated-signal pattern (validated on
run 126, since it also changes what the hard gate drops), NOT a reason to demote every remote lead.
`role_verdict("...")` returns a `(verdict, reason)` tuple — read `[0]`. The stub-body check was
dropped from Phase 1 (the location check already catches the known Cadence case; a body signal would
need new plumbing).

Notes:
- `classify_location` (`rank/location_gate.py:148`) and `role_verdict` (`rank/role_gate.py:449`) are
  pure and already the production classifiers — derive, never store, a location class (D-323: a
  stored class beside stored locations can drift).
- Seniority is **not** re-checked here: `above_band` is already hidden at rank
  (`top_cmd.py:431`), and seniority-`uncertain` (ambiguous "Level 3") is left shortlisted by owner
  ruling.
- `_is_stub` is the least critical check (Cadence is also caught by the location check); include a
  conservative body-length floor so a US+SWE stub still routes to review.

### Code touch-points (verified line numbers, `feat/apply-review-queue-split` @ 3619546)
- `delivery/names.py:39` — add `"_review"` to `DRAIN_DIRS` (single source; `_LOCATIONS`
  `queue.py:113` and `_ensure_root` pick it up automatically; a lane dir NOT in `DRAIN_DIRS` is
  reported `unclassified` — `queue.py:816`).
- `delivery/queue.py:185-208` — `ReconcileReport`: add `to_review`; include it in the `moved` sum
  (line 208) or reconciliation silently stops balancing.
- `delivery/queue.py:363-367` — `_sync_locked` row filter: keep `verdict != "ineligible"` and, for
  the kept rows, compute `lane(row)`; only `lane == ""` rows get a top-level folder (mirror the
  ineligible-exclusion comment at 357-359).
- `delivery/queue.py:690-717,724-743` — `_reconcile_locked` / `_wanted_location`: add `_review` to
  the counts dict and the precedence (applied > skipped > ineligible > **review** > queue root).
- `delivery/store/delivery_queries.py` — `QueueRow` (`:84`) gains `body_len` (or `body_present`);
  `delivered_unapplied` (`:252`) selects it. `verdict` and `location` already present; `title` already
  present.
- `delivery/queue.py:501-523` — `_payload`: add `"lane"` (or keep implicit via folder) so the web app
  can label. Adding a field re-writes every folder ONCE (idempotence keyed on `details.json`
  `content_hash`) — expected.

### Contracts to preserve (module docstring calls these contractual)
1. **DB authoritative both directions.** The review lane is DB-derived; a folder is identified only by
   `posting_id` inside `details.json`, never by folder name. Never delete a folder that cannot be
   classified.
2. **Staged then `os.replace`**, idempotence keyed on `content_hash`.
3. Queue folder = exactly the known files; `_child_dirs` (`queue.py:816`) must skip `_review`.

### Web surfacing — DEFERRED to Phase 1b (the split is filesystem-only in Phase 1)
Phase 1 splits the on-disk folder tree only. The web app (`delivery/api.py::queue_payload`) builds
its list from `delivered_unapplied` minus `ineligible` and **deliberately still lists `uncertain`
and `not_swe` leads, flagged `off_target`** — the documented "uncertain is not a veto" design
(`api.py` docstring §off_target). So after Phase 1 the `boardwatch web` apply page still shows the
review-lane leads; only the folder tree is clean. Making the web apply list match the folder split
is **Phase 1b**, and it is a real decision, not a tweak: it reverses "uncertain is not a veto" for
the apply list (or reframes `off_target` as a review-lane badge) and needs a review **section** in
the React UI (a frontend + bundle-rebuild change) so the demoted leads stay visible. The owner can
browse `~/boardwatch-queue/_review/` directly in the meantime. UI work follows `design-guardrails`
(WCAG 2.2 AA). **Do not silently exclude review leads from `queue_payload`** without the review
section, or they vanish from the web surface entirely.

### Testing
- Unit tests for `lane(...)`: each check in isolation (US vs unknown location; swe vs uncertain role;
  stub vs real body; eligible always-apply), on fixtures derived from live config / fingerprinted so
  drift fails the test (repo rule).
- `reconcile_queue` tests: a row that becomes review is moved into `_review`, un-drained when it
  clears, and counted in `ReconcileReport.moved`.
- Full `make check` is the gate (never a passing subset; never piped through head/tail).

## Phase 2 — 2-3yr early-career recall (separate PR, engine-affecting)

Reclassify **low** `experience_years` thresholds (≈≤3yr) from `blocker` to `preference` in
`eligibility/rules.yaml` (family `experience_years`, `:300`). Effect: a 2-3yr role becomes
`uncertain` instead of `ineligible`, so it is delivered and — via Phase 1 — routed to review, giving
the owner the recall opportunity (~1,171 clean entry-SWE suspects measured on run 119) without
polluting blind-apply.

This **moves `engine_version`** (content-pinned catalog, `catalog.py`), so:
- Measure the blast radius on run 126 (new engine) **before** merging — confirm the reclassification
  only moves low-threshold rows and creates no new `eligible`.
- A ledger drain is owed after any `engine_version` change — follow the standing rule (subject to the
  D-331-style precondition check: only if a permanent disposition could differ).
- Phase 1's `lane()` gains an experience check so a promoted-to-uncertain 2-3yr role routes to
  **review**, not apply (otherwise Phase 2 would put them in blind-apply, against the ruling). This
  check needs the experience evidence (a `experience_above_profile` signal from the current
  evaluation) — the only new plumbing, added in Phase 2.

## Multi-tenancy

All checks read versioned data (`location_gate`, `role_gate`, `rules.yaml`) and the user's profile;
no Mit-specific constants. The review lane and the reclassification are generic mechanism.

## Sequencing / validation

- Phase 1 has **no engine change** and can land independently. Validate against a re-read of the
  live queue (verdicts already moved from tonight's facts) and again after run 126.
- Phase 2 waits on the run-126 re-baseline.
- Program docs (STATE/METRICS/DECISIONS) are owned by #188; take **D-332** in this PR only after #188
  lands.

## Risks

- Forgetting to register `_review` in `DRAIN_DIRS` / `ReconcileReport.moved` → silent `unclassified`
  or a reconcile that stops balancing. (Guarded by tests.)
- **Over-demoting remote leads.** An early `!= "us"` check sent every `unknown`/`"Remote"` lead to
  review — most of the SWE set — and was caught by `test_delivery_queue_hook` (a `["Remote"]` lead).
  Fixed: the check demotes only confirmed `non_us`, failing open on `unknown`. Phase 1 does NOT
  change `classify_location`.
- `details.json` did not gain a field in Phase 1 (the lane is encoded by the folder location), so
  there is no content_hash re-write.
- The web app is unchanged in Phase 1 (see Web surfacing): the `boardwatch web` apply page still
  lists review-lane leads until Phase 1b. Filesystem apply queue is clean; web apply page is not.
