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
lane(row) -> "" (apply) | "_review"
  eligible                       -> ""            # always apply
  uncertain and                                    # ineligible is already excluded upstream
     classify_location(row.location) == "us"       # positively US (catches Zhubei/Kaunas: unknown -> review)
     and role_verdict(row.title) == "swe"          # positively software (catches Hyatt/Allstate: uncertain -> review)
     and not _is_stub(row.body_len)                # real JD captured (catches Cadence stub)
                                  -> ""            # verified uncertain -> apply
  otherwise                      -> "_review"
```

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

### Web surfacing
The web UI (`delivery/server.py`) reads the main queue. `_review` is a drain (excluded from the
apply top-level like `_ineligible`), so it will not clutter blind-apply. Showing `_review` as its own
section in the web app is a small server + frontend addition; the owner can also browse the `_review/`
folder directly. UI work follows `design-guardrails` (WCAG 2.2 AA). Scope this as Phase 1b if it grows.

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

- One-time re-write of every queue folder when `details.json` gains a field (content_hash change).
- Forgetting to register `_review` in `DRAIN_DIRS` / `ReconcileReport.moved` → silent `unclassified`
  or a reconcile that stops balancing.
- Over-aggressive location classification would drop real US jobs; Phase 1 does NOT change
  `classify_location`, it only routes `unknown` to review (reversible, visible), preserving the
  fail-open visa ruling.
