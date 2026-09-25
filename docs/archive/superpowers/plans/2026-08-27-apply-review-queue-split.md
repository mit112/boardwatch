# Apply/Review Queue Split — Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, this session). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Route delivered `uncertain` jobs that are not blindly-appliable into a new `_review` lane, so the top-level apply queue holds only `eligible` + verified-`uncertain` jobs.

**Architecture:** Extend the existing D-321 verdict split in `delivery/queue.py` with a third destination. A pure `lane()` function re-checks the two ranker gates that fail open (location `unknown`, role `uncertain`) using the production classifiers on fields already carried by `QueueRow`. `_review` is a new drain dir; sync routes review rows into it and reconcile keeps it balanced. No engine change, no new eligibility plumbing.

**Tech Stack:** Python 3, `uv run` (ruff, mypy --strict, pytest -n auto), SQLite.

**Spec:** `docs/superpowers/specs/2026-08-27-apply-review-queue-split-design.md`

## Global Constraints

- **Gate:** `make check` only (generalization + index-check + ruff check + mypy --strict + pytest -n auto). Capture the real exit code; never pipe through head/tail. `generalization` scans TRACKED files — `git add` new files before running it.
- **Never `ruff format`** — the lint gate is `ruff check .` only.
- **Multi-tenant:** no user-specific constants; use `classify_location`, `role_verdict`, profile-driven data only.
- **No engine change in Phase 1** — do not touch `eligibility/rules.yaml` or `eligibility/catalog.py` (that is Phase 2). `engine_version` must not move.
- **Single source of truth for drains:** a lane dir MUST be in `names.DRAIN_DIRS` or `_child_dirs` reports it `unclassified`; the new destination MUST be added to `ReconcileReport.moved` or reconciliation silently stops balancing.
- **Contract:** DB authoritative; folders identified by `posting_id` in `details.json`, never by name; never delete an unclassifiable folder; writes staged then `os.replace`.
- **Program docs (STATE/METRICS/DECISIONS) are owned by #188** — do not touch. Take D-332 in this PR only after #188 lands.
- Verdicts of the on-disk queue have already moved from the 2026-08-27 facts; validate against a live re-read and again after run 126.

## File Structure

- **Create** `src/boardwatch/delivery/review_gate.py` — pure `lane()` + `REVIEW_DIR`. One responsibility: classify a delivered row into apply (`""`) or review (`"_review"`).
- **Modify** `src/boardwatch/delivery/names.py:39` — add `"_review"` to `DRAIN_DIRS`.
- **Modify** `src/boardwatch/store/delivery_queries.py` — add `review_job_ids(conn, *, skipped)`.
- **Modify** `src/boardwatch/delivery/queue.py` — `ReconcileReport.to_review` + `moved`; `_sync_locked` routing; `_reconcile_locked`/`_wanted_location` precedence; `_child_dirs` skip; `REVIEW_DIR` import/export.
- **Create** `tests/unit/test_review_gate.py` — `lane()` unit tests.
- **Modify** `tests/unit/test_delivery_queue.py` (or the existing queue reconcile test module) — `_review` sync + reconcile + count.

---

### Task 1: `lane()` classification (pure)

**Files:**
- Create: `src/boardwatch/delivery/review_gate.py`
- Test: `tests/unit/test_review_gate.py`

**Interfaces:**
- Produces: `REVIEW_DIR: str = "_review"`; `def lane(*, verdict: str | None, location: str | None, title: str) -> str` returning `""` (apply) or `REVIEW_DIR`.
- Consumes: `rank.location_gate.classify_location(str) -> "us"|"non_us"|"unknown"`; `rank.role_gate.role_verdict(str) -> "swe"|"not_swe"|"uncertain"`.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_review_gate.py
import pytest
from boardwatch.delivery.review_gate import REVIEW_DIR, lane

def test_eligible_always_applies():
    assert lane(verdict="eligible", location="Zhubei, Taiwan", title="Janitor") == ""

@pytest.mark.parametrize("loc,title", [
    ("San Jose, CA, United States", "Software Engineer"),
    ("Austin, TX", "Backend Engineer"),
])
def test_uncertain_us_swe_is_promoted(loc, title):
    assert lane(verdict="uncertain", location=loc, title=title) == ""

def test_uncertain_foreign_location_to_review():
    # Kaunas/Zhubei classify as unknown -> not positively US -> review
    assert lane(verdict="uncertain", location="Kaunas Office", title="Associate Java Software Engineer") == REVIEW_DIR

def test_uncertain_non_swe_role_to_review():
    assert lane(verdict="uncertain", location="Chicago, Illinois, United States", title="Front Office Agent") == REVIEW_DIR
    assert lane(verdict="uncertain", location="USA - NY (Remote)", title="Field Auto Appraiser") == REVIEW_DIR

def test_none_verdict_to_review():
    assert lane(verdict=None, location="Austin, TX", title="Software Engineer") == REVIEW_DIR
```

- [ ] **Step 2: Run — expect FAIL** `uv run pytest tests/unit/test_review_gate.py -v --no-cov -n 0` (import error).

- [ ] **Step 3: Implement**

```python
# src/boardwatch/delivery/review_gate.py
"""Delivery-time apply/review classification.

An `eligible` lead is always blindly-appliable. An `uncertain` lead reached the
queue by failing open at a ranker gate (location `unknown`, role `uncertain`).
Re-check those two positively; anything not positively US + software goes to the
review lane rather than blind-apply. `ineligible` is excluded upstream (D-321) and
never reaches here. No eligibility state is read — this is a pure re-derivation.
"""
from __future__ import annotations

from boardwatch.rank.location_gate import classify_location
from boardwatch.rank.role_gate import role_verdict

REVIEW_DIR = "_review"


def lane(*, verdict: str | None, location: str | None, title: str) -> str:
    """Return "" for the apply queue or REVIEW_DIR for the review lane."""
    if verdict == "eligible":
        return ""
    if verdict != "uncertain":
        return REVIEW_DIR
    if classify_location(location or "") != "us":
        return REVIEW_DIR
    if role_verdict(title or "") != "swe":
        return REVIEW_DIR
    return ""
```

- [ ] **Step 4: Run — expect PASS** (adjust the fixture location/title strings to match live classifier behavior if a case is off; classifiers are the source of truth).
- [ ] **Step 5: Commit** `git add src/boardwatch/delivery/review_gate.py tests/unit/test_review_gate.py && git commit -m "Add delivery-time apply/review lane classifier"`

---

### Task 2: register `_review` as a drain dir

**Files:** Modify `src/boardwatch/delivery/names.py:39`

- [ ] **Step 1:** Add a test asserting `"_review" in DRAIN_DIRS` and that byte-budget pricing still uses the longest drain (existing test in the names test module — extend it).
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3:** `DRAIN_DIRS: tuple[str, ...] = ("_applied", "_skipped", "_ineligible", "_review")`
- [ ] **Step 4:** Run — expect PASS. Confirm `names.py:209` `longest_drain` logic still holds (all four are 8-9 chars; `_ineligible` remains longest).
- [ ] **Step 5:** Commit `git add src/boardwatch/delivery/names.py tests/... && git commit -m "Add _review to the drain-dir set"`

---

### Task 3: `review_job_ids` query

**Files:** Modify `src/boardwatch/store/delivery_queries.py`; Test: extend the delivery_queries test module.

**Interfaces:**
- Produces: `def review_job_ids(conn: Connection, *, skipped: set[int]) -> set[int]` — job_ids whose delivered row classifies to `REVIEW_DIR` via `lane()`.
- Consumes: `delivered_unapplied(conn, skipped=...)` (`:252`) → `QueueRow(verdict, location, title, job_id, ...)`; `review_gate.lane`.

- [ ] **Step 1: Write failing test** — seed a store with two delivered rows (one US+SWE `uncertain`, one foreign `uncertain`), assert `review_job_ids` returns exactly the foreign one's job_id. Model the seed on the existing `delivered_unapplied` test fixtures.
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3: Implement** (mirror `ineligible_job_ids` `:231`):

```python
from boardwatch.delivery.review_gate import lane

def review_job_ids(conn: Connection, *, skipped: set[int]) -> set[int]:
    """Delivered, unapplied jobs whose verified-uncertain check routes them to review."""
    return {
        row.job_id
        for row in delivered_unapplied(conn, skipped=skipped)
        if lane(verdict=row.verdict, location=row.location, title=row.title) != ""
    }
```

- [ ] **Step 4:** Run — expect PASS.
- [ ] **Step 5:** Commit `git add ... && git commit -m "Add review_job_ids delivery query"`

---

### Task 4: wire `_review` into sync + reconcile

**Files:** Modify `src/boardwatch/delivery/queue.py`; Test: `tests/unit/test_delivery_queue.py` (reconcile/sync module).

**Interfaces:**
- Consumes: `review_gate.lane`, `REVIEW_DIR`, `delivery_queries.review_job_ids`.
- Produces: `ReconcileReport.to_review: int`; `_review` folders on disk.

Edits (each with the exact anchor):
- `ReconcileReport` (`:185-208`): add `to_review: int = 0`; `moved` returns `... + self.to_review + self.to_queue`.
- `queue.py:89` area: add `REVIEW_DIR = "_review"` (import from `review_gate` or define; keep one definition — import from `review_gate`). Add to `__all__` (`:863` block).
- `_sync_locked` (`:363-367`): keep `if row.verdict != "ineligible"`, then for each kept row compute `lane(...)`; rows with `lane != ""` are placed under `REVIEW_DIR` instead of the top level (mirror the ineligible exclusion + placement).
- `_reconcile_locked` (`:685-717`): add `REVIEW_DIR: 0` to the `counts` dict (`:690`), fetch `review_job_ids`, and set `to_review=counts[REVIEW_DIR]`.
- `_wanted_location` (`:724-743`): precedence applied > skipped > ineligible > **review** > queue root — return `REVIEW_DIR` when `job_id in review_ids` and not in the higher sets.
- `_child_dirs`/`_index` (`:816`): add `REVIEW_DIR` to the skip tuple so a `_review` folder is not reported `unclassified`.

- [ ] **Step 1: Write failing tests**
  - `test_uncertain_foreign_lead_synced_into_review`: seed a delivered foreign `uncertain` lead; `sync_queue`; assert its folder is under `_review/`, not the top level.
  - `test_uncertain_us_swe_lead_stays_in_apply_queue`: seed a US+SWE `uncertain` lead; assert top-level folder.
  - `test_reconcile_moves_lead_between_review_and_queue`: a lead that flips classification is moved and counted in `ReconcileReport.to_review`; `moved` includes it.
  - `test_review_folder_not_unclassified`: a `_review` folder is recognized (not counted as unclassified) by the index.
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3:** Apply the edits above.
- [ ] **Step 4:** Run the queue test module — expect PASS.
- [ ] **Step 5:** Commit `git add src/boardwatch/delivery/queue.py tests/unit/test_delivery_queue.py && git commit -m "Route non-verified uncertain leads into the _review lane"`

---

### Task 5: full gate + PR

- [ ] **Step 1:** `git add -A` the new files (generalization scans tracked files only).
- [ ] **Step 2:** Run the gate detached (it is 4.5-35 min; Bash clamps at ~10 min):
  `nohup sh -c 'export PATH=/opt/homebrew/bin:$PATH; cd ~/dev/projectY/<worktree>; make check > <scratch>/gate-<sha>.log 2>&1; echo $? > <scratch>/gate-<sha>.done' & disown`
  Gate on the sentinel file, not the launcher exit code. Cap concurrent gates at ~2.
- [ ] **Step 3:** On green (sentinel `0`), push and open a PR (base main). Do NOT touch program docs; note D-332 is owed after #188 lands.
- [ ] **Step 4:** Validate behavior: re-read the live queue's would-be split (read-only) and confirm the known leaks (Hyatt/Allstate → review; Zhubei/Kaunas → review) land in `_review`. Re-validate after run 126.

## Self-Review

- **Spec coverage:** `_review` lane (Tasks 2,4), verified-uncertain check location+role (Task 1), reconcile registration (Task 4), single-source drain (Tasks 2,4), no engine change (constraint). Stub-body check is intentionally deferred (location catches the known Cadence case; noted in spec). Web display deferred to Phase 1b. Phase 2 (experience reclassification) is out of scope here.
- **Placeholder scan:** none.
- **Type consistency:** `lane(verdict, location, title)` signature identical in Tasks 1, 3, 4; `REVIEW_DIR` single-defined in `review_gate`, imported elsewhere.
