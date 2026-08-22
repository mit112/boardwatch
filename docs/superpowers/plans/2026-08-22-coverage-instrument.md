# Coverage Instrument Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every board's discovery coverage a first-class, per-run number, so a gap can never again be silent — and raise `DEFAULT_TOP_N` from 8 to 40.

**Architecture:** The scan already enumerates every board and already parses a server-stated total in two providers; none of it reaches the database. This adds three nullable fields to `BoardSnapshot`, persists them on `board_scans`, and reports coverage as a **five-bucket partition** (`measured` / `enumerated_only` / `censored` / `dark` / `stale`) that never folds a bucket into a neighbour. Zero new HTTP requests: Workday's uncapped facet sum arrives in the response it already fetches.

**Tech Stack:** Python 3.11–3.13, Pydantic v2 (frozen models), SQLAlchemy Core, Alembic, Typer CLI, pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-coverage-assurance-design.md` (decisions D-271, D-272)

## Global Constraints

- **`make check` is the only gate.** pytest + ruff + mypy passing individually is NOT green. Run it in plain mode, capture the real exit code, never pipe through `head`/`tail` (SIGPIPE gives a false negative).
- **Launch `make check` DETACHED.** The Bash tool clamps `timeout` to 10 minutes and the gate takes 4½–35; a longer run reads as `Error 143`. Double-fork + `setsid`, poll the log.
- **`make reindex` after touching any program doc**, and `make check` fails on a stale index (D-109).
- **Typed violations at the raise site.** Never classify behaviour by string-matching a message. `detail_deferred` exists precisely so the number stops living inside `board_scans.error` prose.
- **A default on a frozen Pydantic model is a serialization decision.** `None` means *the board stated no total*. It must never be silently backfilled with `len(...)`.
- **Never fold a bucket into a neighbour.** Same invariant as `ABSTAIN`. A board that cannot be measured is its own bucket, never counted as 100%.
- **A ratio records its match rule AND its corpus size** (D-268).
- **Test against a known positive** — a check that has only ever seen agreement has not been shown to detect disagreement.
- **No AI attribution** in commits, PRs, branches or tags. No `Co-Authored-By`, no "Generated with" lines.
- Alembic head is currently **`p_seniority_band`**. New migrations chain from it.
- The funnel artifact already has a key named `coverage` meaning *résumé keyword coverage* (`tailor/coverage.py`). The new section is **`board_coverage`**. Do not reuse the name.

---

### Task 1: `BoardSnapshot` carries the three coverage numbers

**Files:**
- Modify: `src/boardwatch/core/models.py` (class `BoardSnapshot`, currently line 61)
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BoardSnapshot.board_reported_total: int | None`, `BoardSnapshot.board_enumerated: int | None`, `BoardSnapshot.detail_deferred: int | None`. All default `None`. Every later task reads these exact names.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models.py
from boardwatch.core.models import BoardSnapshot


def test_board_snapshot_coverage_fields_default_to_none() -> None:
    """None means the board stated no total. It must NEVER be backfilled with len(postings)."""
    snap = BoardSnapshot(status="complete", postings=[], url="https://x/y")
    assert snap.board_reported_total is None
    assert snap.board_enumerated is None
    assert snap.detail_deferred is None


def test_board_snapshot_coverage_fields_round_trip() -> None:
    snap = BoardSnapshot(
        status="partial", postings=[], url="https://x/y",
        board_reported_total=4589, board_enumerated=2214, detail_deferred=1614,
    )
    assert snap.model_dump()["board_reported_total"] == 4589
    assert BoardSnapshot(**snap.model_dump()).detail_deferred == 1614
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models.py -k coverage_fields -v --no-cov -n 0`
Expected: FAIL — `ValidationError: Extra inputs are not permitted` on the round-trip test, and `AttributeError` on the defaults test.

- [ ] **Step 3: Write minimal implementation**

Add to `BoardSnapshot` immediately after `listed_ids`, before the `@model_validator`:

```python
    # Coverage instrument (D-271). None means the board stated no total — NEVER backfill
    # with len(postings); an unfailable ratio is worse than no ratio.
    board_reported_total: int | None = None
    # Distinct posting ids we LISTED this run, before the detail budget truncated anything.
    board_enumerated: int | None = None
    # Listed but not materialised because detail_fetch_budget was exceeded. Typed here so the
    # number stops living only as English inside board_scans.error.
    detail_deferred: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models.py -k coverage_fields -v --no-cov -n 0`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/core/models.py tests/unit/test_models.py
git commit -m "Add coverage fields to BoardSnapshot (D-271)"
```

---

### Task 2: Migration — three nullable columns on `board_scans`

**Files:**
- Create: `src/boardwatch/store/migrations/versions/p_board_coverage.py`
- Modify: `src/boardwatch/store/tables.py:150-164` (the `board_scans` Table)
- Test: `tests/unit/test_migration_board_coverage.py`

**Interfaces:**
- Consumes: Task 1's field names.
- Produces: `board_scans.board_reported_total`, `board_scans.board_enumerated`, `board_scans.detail_deferred`, all `Integer, nullable=True`. Alembic revision id `p_board_coverage`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_migration_board_coverage.py
from sqlalchemy import inspect

from boardwatch.store.engine import get_engine
from boardwatch.store.schema import ensure_schema


def test_board_scans_has_nullable_coverage_columns(tmp_path) -> None:
    """Nullable is load-bearing: an existing row has no total and must not read as zero."""
    engine = get_engine(tmp_path / "t.db")
    ensure_schema(engine)
    cols = {c["name"]: c for c in inspect(engine).get_columns("board_scans")}
    for name in ("board_reported_total", "board_enumerated", "detail_deferred"):
        assert name in cols, f"{name} missing from board_scans"
        assert cols[name]["nullable"] is True, f"{name} must be nullable, not 0-defaulted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_migration_board_coverage.py -v --no-cov -n 0`
Expected: FAIL — `AssertionError: board_reported_total missing from board_scans`

- [ ] **Step 3: Write minimal implementation**

Create `src/boardwatch/store/migrations/versions/p_board_coverage.py`:

```python
"""D-271: per-board coverage numbers the scan already computes and threw away.

Three additive nullable columns. NULL is meaningful and is not zero: it means the board stated
no total (lever/ashby/workable have no count field at all), or the row predates this migration.
A zero default would make every historic row read as a board with nothing on it.

ALTER TABLE ADD COLUMN with no table rebuild; downgrade uses native DROP COLUMN (SQLite >= 3.35),
the path p_seniority_band takes.

These do NOT enter the run manifest hash — they are observations about a scan, not inputs to a
verdict. Contrast detail_fetch_budget, which is currently classified "throughput" in
reports/manifest.py and arguably should not be; that is a separate decision.
"""

from alembic import op

revision = "p_board_coverage"
down_revision = "p_seniority_band"
branch_labels = None
depends_on = None

_COLUMNS = ("board_reported_total", "board_enumerated", "detail_deferred")


def upgrade() -> None:
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE board_scans ADD COLUMN {name} INTEGER")


def downgrade() -> None:
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE board_scans DROP COLUMN {name}")
```

Then in `src/boardwatch/store/tables.py`, inside the `board_scans` Table, after
`Column("error", Text, nullable=True),`:

```python
    # Coverage instrument (D-271). Nullable: NULL means the board stated no total, which is
    # not the same claim as zero.
    Column("board_reported_total", Integer, nullable=True),
    Column("board_enumerated", Integer, nullable=True),
    Column("detail_deferred", Integer, nullable=True),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_migration_board_coverage.py -v --no-cov -n 0`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/store/migrations/versions/p_board_coverage.py \
        src/boardwatch/store/tables.py tests/unit/test_migration_board_coverage.py
git commit -m "Persist per-board coverage columns on board_scans (D-271)"
```

---

### Task 3: `_scan_row` writes the three numbers

**Files:**
- Modify: `src/boardwatch/scan/apply.py` (`_scan_row` at line 351; its four call sites at lines 65, 68, 81)
- Test: `tests/unit/test_scan_apply.py`

**Interfaces:**
- Consumes: Task 1's fields, Task 2's columns.
- Produces: `_scan_row(conn, run_id, company_id, started_at, status, listed, error, *, snapshot: BoardSnapshot | None = None)`. Passing `snapshot=None` (the `failed`/`unchanged` paths) writes NULL for all three.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_apply.py
from sqlalchemy import select

from boardwatch.core.models import BoardSnapshot
from boardwatch.scan.apply import apply_board
from boardwatch.store.tables import board_scans


def test_apply_board_persists_coverage_numbers(scan_conn, company_id, run_id) -> None:
    snap = BoardSnapshot(
        status="partial", postings=[], url="https://x/y",
        board_reported_total=4589, board_enumerated=2214, detail_deferred=1614,
    )
    apply_board(scan_conn, snap, company_id=company_id, run_id=run_id)
    row = scan_conn.execute(select(board_scans)).one()
    assert row.board_reported_total == 4589
    assert row.board_enumerated == 2214
    assert row.detail_deferred == 1614


def test_failed_board_writes_null_not_zero(scan_conn, company_id, run_id) -> None:
    """A dark board's coverage is UNDEFINED. Zero would claim the board is empty."""
    snap = BoardSnapshot(status="failed", postings=[], url="https://x/y", error="HTTP 401")
    apply_board(scan_conn, snap, company_id=company_id, run_id=run_id)
    row = scan_conn.execute(select(board_scans)).one()
    assert row.board_reported_total is None
    assert row.board_enumerated is None
    assert row.detail_deferred is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_scan_apply.py -k coverage_numbers -v --no-cov -n 0`
Expected: FAIL — `AssertionError: assert None == 4589`

- [ ] **Step 3: Write minimal implementation**

Change the signature and body of `_scan_row`:

```python
def _scan_row(
    conn: Connection,
    run_id: int,
    company_id: int,
    started_at: datetime,
    status: str,
    listed: int,
    error: str | None,
    *,
    snapshot: BoardSnapshot | None = None,
) -> None:
    conn.execute(
        insert(board_scans).values(
            run_id=run_id,
            company_id=company_id,
            started_at=started_at,
            finished_at=utcnow(),
            status=status,
            postings_listed=listed,
            error=error,
            # NULL, not 0, when there is no snapshot: a failed board's coverage is undefined.
            board_reported_total=None if snapshot is None else snapshot.board_reported_total,
            board_enumerated=None if snapshot is None else snapshot.board_enumerated,
            detail_deferred=None if snapshot is None else snapshot.detail_deferred,
        )
    )
```

At the `complete`/`partial` call site (line 81), pass the snapshot:

```python
        _scan_row(
            conn, run_id, company_id, started_at, snapshot.status,
            len(snapshot.postings), snapshot.error, snapshot=snapshot,
        )
```

Leave the `failed` (line 65) and `unchanged` (line 68) call sites unchanged — they must write NULL.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_scan_apply.py -v --no-cov -n 0`
Expected: PASS, and no existing test in the file regresses.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/scan/apply.py tests/unit/test_scan_apply.py
git commit -m "Write per-board coverage numbers on every scan row (D-271)"
```

---

### Task 4: Workday reports its real board size via the facet sum

**Files:**
- Modify: `src/boardwatch/providers/workday.py` (the offset=0 branch near line 295–298; `fetch_board`)
- Test: `tests/contract/test_workday.py`
- Create: `tests/fixtures/workday/list_censored_with_facets.json`

**Interfaces:**
- Consumes: Task 1's fields.
- Produces: `_uncapped_total(payload: dict[str, Any]) -> tuple[int | None, bool]` returning `(total, censored)`. `censored is True` when `payload["total"] == 2000`. `fetch_board` sets all three `BoardSnapshot` coverage fields.

**Why this is the highest-value task:** measured live on 2026-08-22, Citi reports `total: 2000` while its facets sum to **4,589**; NVIDIA reports 2000 against **2,656**. On four uncensored boards the facet sum equals `total` exactly (Adobe 740, Intel 645, Regeneron 592, Fidelity 565) — that agreement is the known-positive control and it must be a test.

- [ ] **Step 1: Write the failing test**

Create `tests/fixtures/workday/list_censored_with_facets.json`:

```json
{
  "total": 2000,
  "jobPostings": [],
  "facets": [
    {"facetParameter": "jobFamilyGroup",
     "values": [{"id": "a", "descriptor": "Eng", "count": 3000},
                {"id": "b", "descriptor": "Ops", "count": 1589}]},
    {"facetParameter": "timeType",
     "values": [{"id": "ft", "descriptor": "Full time", "count": 4589}]},
    {"facetParameter": "locationMainGroup",
     "values": [{"id": "z", "descriptor": "Zero facet", "count": 0}]}
  ],
  "userAuthenticated": false
}
```

```python
# tests/contract/test_workday.py
import json
from pathlib import Path

from boardwatch.providers.workday import _uncapped_total

FIX = Path(__file__).parents[1] / "fixtures" / "workday"


def test_facet_sum_beats_the_2000_censor() -> None:
    """Workday caps `total` at 2000; facets are aggregated by another path and are not capped."""
    payload = json.loads((FIX / "list_censored_with_facets.json").read_text())
    total, censored = _uncapped_total(payload)
    assert censored is True
    assert total == 4589


def test_uncensored_board_agrees_with_total() -> None:
    """KNOWN-POSITIVE CONTROL. Verified live: Adobe 740/740, Intel 645/645, Regeneron 592/592.

    Without this the censor detection could return anything and no test would notice."""
    payload = {
        "total": 740, "jobPostings": [],
        "facets": [{"facetParameter": "jobFamilyGroup",
                    "values": [{"id": "a", "descriptor": "Eng", "count": 740}]}],
    }
    total, censored = _uncapped_total(payload)
    assert censored is False
    assert total == 740


def test_missing_facets_falls_back_to_total_and_is_not_invented() -> None:
    total, censored = _uncapped_total({"total": 512, "jobPostings": [], "facets": []})
    assert (total, censored) == (512, False)


def test_absent_total_yields_none_never_zero() -> None:
    """None means the board stated nothing. Zero would be a claim we cannot support."""
    assert _uncapped_total({"jobPostings": []}) == (None, False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/contract/test_workday.py -k "facet_sum or uncensored or missing_facets or absent_total" -v --no-cov -n 0`
Expected: FAIL — `ImportError: cannot import name '_uncapped_total'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/boardwatch/providers/workday.py`, above `fetch_board`:

```python
# Workday censors `total` at exactly this value and wraps the pager past it. The facets block
# is aggregated server-side by a different path and is NOT capped — measured 2026-08-22:
# Citi total=2000 / facets=4589, NVIDIA total=2000 / facets=2656, while four uncensored boards
# agreed exactly (Adobe 740, Intel 645, Regeneron 592, Fidelity 565). See D-271.
_TOTAL_CENSOR = 2000


def _uncapped_total(payload: dict[str, Any]) -> tuple[int | None, bool]:
    """Return (board_total, censored). None means the board stated no total — never 0.

    When `total` reads exactly _TOTAL_CENSOR the real size is unknown and >= it, so we take the
    largest non-zero facet dimension instead. Every dimension partitions the same corpus, so
    they agree; `locationMainGroup` can sum to 0 on some tenants and is skipped rather than
    dragging the maximum down.
    """
    raw = payload.get("total")
    if raw is None:
        return None, False
    total = max(0, int(raw))
    censored = total == _TOTAL_CENSOR
    if not censored:
        return total, False
    sums = [
        sum(int(v.get("count", 0)) for v in (facet.get("values") or []))
        for facet in (payload.get("facets") or [])
    ]
    non_zero = [s for s in sums if s > 0]
    return (max(non_zero) if non_zero else total), True
```

In `fetch_board`'s offset=0 branch, where `total = max(0, int(payload["total"]))` currently sits (line ~298), also capture the uncapped figure:

```python
                    total = max(0, int(payload["total"]))
                    board_total, board_censored = _uncapped_total(payload)
```

Initialise `board_total: int | None = None` and `board_censored = False` beside the existing
`facets: list[Any] = []` (line ~259), and set the three coverage fields on every
`BoardSnapshot` this method returns for a `complete`/`partial` board:

```python
            board_reported_total=board_total,
            board_enumerated=len(listed_ids),
            detail_deferred=max(0, len(unseen_before_truncation) - request.detail_budget),
```

where `unseen_before_truncation` is the `unseen` list captured **before** the existing
`unseen = unseen[: request.detail_budget]` slice. Bind it immediately above that slice:

```python
                unseen_before_truncation = unseen
```

If `board_censored`, append the existing-style note to `errors` so the censor is visible in the
run log as well as in the column:

```python
    if board_censored:
        errors.append(
            f"board total censored at {_TOTAL_CENSOR}; facet sum reports {board_total}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/contract/test_workday.py -v --no-cov -n 0`
Expected: PASS, all existing Workday contract tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/providers/workday.py tests/contract/test_workday.py \
        tests/fixtures/workday/list_censored_with_facets.json
git commit -m "Read Workday's uncapped facet sum past the 2000 total censor (D-271)"
```

---

### Task 5: SmartRecruiters reports the total it already parses

**Files:**
- Modify: `src/boardwatch/providers/smartrecruiters.py` (`fetch_board`; `total` is parsed at line 103)
- Test: `tests/contract/test_smartrecruiters.py`

**Interfaces:**
- Consumes: Task 1's fields.
- Produces: nothing new. `fetch_board` sets the three coverage fields from values it already holds.

Note: zero SmartRecruiters boards are currently watched, so this has no live evidence. It ships for correctness and because the code path is identical in shape to Workday's.

- [ ] **Step 1: Write the failing test**

```python
# tests/contract/test_smartrecruiters.py
def test_smartrecruiters_reports_totalfound_as_board_total(sr_fetcher, sr_request) -> None:
    """totalFound is the board's own count; the contract pins totalFound == len(content)."""
    snap = SmartRecruitersProvider().fetch_board(sr_fetcher, sr_request)
    assert snap.board_reported_total == 3
    assert snap.board_enumerated == 3
    assert snap.detail_deferred == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/contract/test_smartrecruiters.py -k totalfound -v --no-cov -n 0`
Expected: FAIL — `assert None == 3`

- [ ] **Step 3: Write minimal implementation**

Capture the unseen list before the budget slice, exactly as in Task 4:

```python
            unseen_before_truncation = unseen
            if len(unseen) > request.detail_budget:
                ...
                unseen = unseen[: request.detail_budget]
```

and on the returned `BoardSnapshot`:

```python
            board_reported_total=total,
            board_enumerated=len(listed),
            detail_deferred=max(0, len(unseen_before_truncation) - request.detail_budget),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/contract/test_smartrecruiters.py -v --no-cov -n 0`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/providers/smartrecruiters.py tests/contract/test_smartrecruiters.py
git commit -m "Report SmartRecruiters totalFound as the board total (D-271)"
```

---

### Task 6: The four single-request providers

**Files:**
- Modify: `src/boardwatch/providers/greenhouse.py`, `lever.py`, `ashby.py`, `workable.py`
- Test: `tests/contract/test_greenhouse.py`, `tests/contract/test_lever.py`, `tests/contract/test_ashby.py`, `tests/contract/test_workable.py`

**Interfaces:**
- Consumes: Task 1's fields.
- Produces: Greenhouse sets `board_reported_total` from `meta.total`. Lever, Ashby and Workable set it **explicitly to `None`**. All four set `board_enumerated=len(postings)` and `detail_deferred=0`.

**Why the explicit `None` matters:** Lever returns a bare JSON array and Ashby/Workable envelopes carry no count field. Their only available "total" is our own array length, so a ratio would read 100% by arithmetic on every run forever — the exact failure that killed `SourceTotal` (D-028). These boards are genuinely fully enumerated in one request, so 100% happens to be *true*; it is still not *evidence*, and Task 7 reports them as `enumerated_only`.

- [ ] **Step 1: Write the failing test**

```python
# tests/contract/test_greenhouse.py
def test_greenhouse_reports_meta_total(gh_fetcher, gh_request) -> None:
    """Confirmed live 2026-08-22: stripe meta.total=576, databricks 818."""
    snap = GreenhouseProvider().fetch_board(gh_fetcher, gh_request)
    assert snap.board_reported_total == 5   # tests/fixtures/greenhouse/normal.json
    assert snap.board_enumerated == 5
    assert snap.detail_deferred == 0
```

```python
# tests/contract/test_lever.py  (mirror in test_ashby.py, test_workable.py)
def test_lever_states_no_board_total() -> None:
    """A bare JSON array has no count field. None is a CLAIM: the board stated nothing.

    Backfilling len(postings) here would make coverage 100% by arithmetic, forever."""
    snap = LeverProvider().fetch_board(lever_fetcher, lever_request)
    assert snap.board_reported_total is None
    assert snap.board_enumerated == len(snap.postings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/contract/test_greenhouse.py tests/contract/test_lever.py tests/contract/test_ashby.py tests/contract/test_workable.py -k "meta_total or no_board_total" -v --no-cov -n 0`
Expected: FAIL — `assert None == 5` for Greenhouse; the three `None` tests pass vacuously (the field already defaults to `None`), which is fine — they are regression locks, not drivers.

- [ ] **Step 3: Write minimal implementation**

In `greenhouse.py`, after `jobs = payload["jobs"]`:

```python
            # meta.total is present on both the content=true board URL and the cheaper
            # _health_url shape (confirmed live: stripe 576, databricks 818). Absent on some
            # tenants, so .get() — and None means "stated nothing", never 0.
            meta = payload.get("meta")
            board_total = int(meta["total"]) if isinstance(meta, dict) and "total" in meta else None
```

and on the returned success `BoardSnapshot`:

```python
            board_reported_total=board_total,
            board_enumerated=len(postings),
            detail_deferred=0,
```

In `lever.py`, `ashby.py` and `workable.py`, on the success `BoardSnapshot` only:

```python
            # This API states no total. None, deliberately — see D-271 and D-028.
            board_reported_total=None,
            board_enumerated=len(postings),
            detail_deferred=0,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/contract/ -v --no-cov -n 0`
Expected: PASS across all six provider contract suites.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/providers/greenhouse.py src/boardwatch/providers/lever.py \
        src/boardwatch/providers/ashby.py src/boardwatch/providers/workable.py tests/contract/
git commit -m "State a board total where the API gives one, None where it does not (D-271)"
```

---

### Task 7: The five-bucket coverage partition

**Files:**
- Create: `src/boardwatch/reports/board_coverage.py`
- Test: `tests/unit/test_board_coverage.py`

**Interfaces:**
- Consumes: the `board_scans` columns from Task 2.
- Produces:
  - `CoverageBucket = Literal["measured", "enumerated_only", "censored", "dark", "stale"]`
  - `@dataclass(frozen=True) BoardCoverage` with fields `company_id: int`, `name: str`, `provider: str`, `bucket: CoverageBucket`, `held: int`, `board_reported_total: int | None`, `board_enumerated: int | None`, `detail_deferred: int | None`, `shortfall: int | None`, `ratio: float | None`
  - `classify_board(*, status: str, board_reported_total: int | None, board_enumerated: int | None, held: int, censored: bool) -> CoverageBucket`
  - `@dataclass(frozen=True) CoverageReport` with `boards: list[BoardCoverage]`, `bucket_counts: dict[CoverageBucket, int]`, `measured_held: int`, `measured_total: int`, `global_ratio: float | None`, `corpus_boards: int`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_board_coverage.py
import pytest

from boardwatch.reports.board_coverage import classify_board, build_report, BoardCoverage


def test_a_board_with_no_stated_total_never_gets_a_ratio() -> None:
    """THE unfailable-ratio guard. lever/ashby/workable state no total, so held/held == 1.0
    would be true on every run for every board and could never detect a leak."""
    assert classify_board(status="complete", board_reported_total=None,
                          board_enumerated=120, held=120, censored=False) == "enumerated_only"


def test_censored_board_is_its_own_bucket() -> None:
    assert classify_board(status="partial", board_reported_total=4589,
                          board_enumerated=2214, held=600, censored=True) == "censored"


def test_failed_board_is_dark_not_zero_coverage() -> None:
    assert classify_board(status="failed", board_reported_total=None,
                          board_enumerated=None, held=0, censored=False) == "dark"


def test_unchanged_board_is_stale_not_measured() -> None:
    assert classify_board(status="unchanged", board_reported_total=None,
                          board_enumerated=None, held=430, censored=False) == "stale"


def test_measured_board_gets_a_ratio_and_an_absolute_shortfall() -> None:
    rep = build_report([
        BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=740, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=600 / 740),
    ])
    assert rep.bucket_counts["measured"] == 1
    assert rep.global_ratio == pytest.approx(600 / 740)
    assert rep.boards[0].shortfall == 140


def test_global_ratio_ignores_unmeasurable_boards_but_still_counts_them() -> None:
    """A dark board must not be averaged in as 100%, and must not vanish from the denominator."""
    rep = build_report([
        BoardCoverage(company_id=1, name="Adobe", provider="workday", bucket="measured",
                      held=600, board_reported_total=740, board_enumerated=740,
                      detail_deferred=140, shortfall=140, ratio=600 / 740),
        BoardCoverage(company_id=2, name="Snowflake", provider="workday", bucket="dark",
                      held=0, board_reported_total=None, board_enumerated=None,
                      detail_deferred=None, shortfall=None, ratio=None),
    ])
    assert rep.global_ratio == pytest.approx(600 / 740)
    assert rep.corpus_boards == 2
    assert rep.bucket_counts["dark"] == 1


def test_over_full_coverage_is_reported_not_clamped() -> None:
    """Measured live: Regeneron 101.4%, Fidelity 106.2%. We hold postings the board dropped,
    because a permanently `partial` board never runs _process_missing. Clamping to 1.0 would
    hide the defect."""
    rep = build_report([
        BoardCoverage(company_id=3, name="Fidelity", provider="workday", bucket="measured",
                      held=600, board_reported_total=565, board_enumerated=565,
                      detail_deferred=104, shortfall=-35, ratio=600 / 565),
    ])
    assert rep.global_ratio > 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_board_coverage.py -v --no-cov -n 0`
Expected: FAIL — `ModuleNotFoundError: No module named 'boardwatch.reports.board_coverage'`

- [ ] **Step 3: Write minimal implementation**

Create `src/boardwatch/reports/board_coverage.py`:

```python
"""Per-board discovery coverage as a five-bucket partition (D-271).

Coverage is NOT one number. A board whose total we cannot obtain gets its own bucket and is
never folded into a neighbour — the same invariant that makes ABSTAIN load-bearing in the
eligibility engine. Folding `enumerated_only` into `measured` would print a ratio that is 100%
by arithmetic on every run forever, which is the failure that killed the per-board SourceTotal
check (D-028).

The global ratio is a weighted roll-up over `measured` ONLY, published beside the counts of the
other four buckets. It is board-scoped, not job-scoped: one Workday tenant can serve several
sites, so summing board totals into a "job universe" would double-count.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

CoverageBucket = Literal["measured", "enumerated_only", "censored", "dark", "stale"]

_ALL_BUCKETS: tuple[CoverageBucket, ...] = (
    "measured", "enumerated_only", "censored", "dark", "stale",
)


@dataclass(frozen=True)
class BoardCoverage:
    company_id: int
    name: str
    provider: str
    bucket: CoverageBucket
    held: int
    board_reported_total: int | None
    board_enumerated: int | None
    detail_deferred: int | None
    # Absolute, signed, and reported BESIDE the ratio: a 1-posting shortfall on a 1,129-posting
    # board is 99.91% and reads as noise, but it is a real id-less-row parse defect.
    shortfall: int | None
    ratio: float | None


@dataclass(frozen=True)
class CoverageReport:
    boards: list[BoardCoverage]
    bucket_counts: dict[CoverageBucket, int]
    measured_held: int
    measured_total: int
    global_ratio: float | None
    corpus_boards: int


def classify_board(
    *,
    status: str,
    board_reported_total: int | None,
    board_enumerated: int | None,
    held: int,
    censored: bool,
) -> CoverageBucket:
    """Order matters: dark and stale are properties of the SCAN and win over any stored total."""
    if status == "failed":
        return "dark"
    if status == "unchanged":
        return "stale"
    if censored:
        return "censored"
    if board_reported_total is None:
        return "enumerated_only"
    return "measured"


def build_report(boards: list[BoardCoverage]) -> CoverageReport:
    counts = Counter(b.bucket for b in boards)
    measured = [b for b in boards if b.bucket == "measured"]
    held = sum(b.held for b in measured)
    total = sum(b.board_reported_total or 0 for b in measured)
    return CoverageReport(
        boards=boards,
        bucket_counts={b: counts.get(b, 0) for b in _ALL_BUCKETS},
        measured_held=held,
        measured_total=total,
        # None, not 1.0, when nothing is measurable. An empty average is not full coverage.
        global_ratio=(held / total) if total > 0 else None,
        corpus_boards=len(boards),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_board_coverage.py -v --no-cov -n 0`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/reports/board_coverage.py tests/unit/test_board_coverage.py
git commit -m "Classify board coverage as a five-bucket partition (D-271)"
```

---

### Task 8: `boardwatch coverage` — the read-only report

**Files:**
- Create: `src/boardwatch/cli/coverage_cmd.py`
- Create: `src/boardwatch/store/coverage_queries.py`
- Modify: `src/boardwatch/cli/app.py` (register the command)
- Test: `tests/cli/test_coverage_cmd.py`

**Interfaces:**
- Consumes: `build_report`, `classify_board`, `BoardCoverage` from Task 7.
- Produces: `load_board_coverage(conn, *, run_id: int | None = None) -> list[BoardCoverage]` in `coverage_queries.py`; CLI `boardwatch coverage [--run N] [--json]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_coverage_cmd.py
import json


def test_coverage_report_prints_every_bucket_even_when_empty(cli_runner, seeded_store) -> None:
    """A bucket that reads 0 is information. A bucket that is absent is a silent fold."""
    result = cli_runner.invoke(app, ["coverage", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["bucket_counts"]) == {
        "measured", "enumerated_only", "censored", "dark", "stale"
    }


def test_coverage_report_states_its_corpus_size_beside_the_ratio(cli_runner, seeded_store) -> None:
    """D-268's rule: a ratio records its match rule AND its corpus size."""
    payload = json.loads(cli_runner.invoke(app, ["coverage", "--json"]).stdout)
    assert payload["corpus_boards"] == 135
    assert "measured_held" in payload and "measured_total" in payload


def test_enumerated_only_board_has_null_ratio_in_output(cli_runner, seeded_store) -> None:
    payload = json.loads(cli_runner.invoke(app, ["coverage", "--json"]).stdout)
    lever = next(b for b in payload["boards"] if b["provider"] == "lever")
    assert lever["bucket"] == "enumerated_only"
    assert lever["ratio"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_coverage_cmd.py -v --no-cov -n 0`
Expected: FAIL — `No such command 'coverage'` (exit code 2)

- [ ] **Step 3: Write minimal implementation**

`src/boardwatch/store/coverage_queries.py`:

```python
"""Read-only: join the latest board_scans row per board to what the store actually holds."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from boardwatch.reports.board_coverage import BoardCoverage, classify_board
from boardwatch.store.tables import board_scans, companies, postings

_CENSOR_NOTE = "board total censored at"


def load_board_coverage(conn: Connection, *, run_id: int | None = None) -> list[BoardCoverage]:
    if run_id is None:
        run_id = conn.execute(select(func.max(board_scans.c.run_id))).scalar_one_or_none()
    held_by_company = dict(
        conn.execute(
            select(postings.c.company_id, func.count())
            .where(postings.c.status == "open")
            .group_by(postings.c.company_id)
        ).all()
    )
    rows = conn.execute(
        select(
            companies.c.id, companies.c.name, companies.c.provider,
            board_scans.c.status, board_scans.c.error,
            board_scans.c.board_reported_total, board_scans.c.board_enumerated,
            board_scans.c.detail_deferred,
        )
        .select_from(companies.join(board_scans, board_scans.c.company_id == companies.c.id))
        .where(board_scans.c.run_id == run_id)
        .where(companies.c.watched.is_(True))
    ).all()
    out: list[BoardCoverage] = []
    for r in rows:
        held = int(held_by_company.get(r.id, 0))
        # The censor is recorded by the provider as a typed number plus a note; we detect it
        # structurally, not by parsing the note, so the string is never load-bearing.
        censored = r.board_reported_total is not None and (r.error or "").find(_CENSOR_NOTE) >= 0
        bucket = classify_board(
            status=str(r.status), board_reported_total=r.board_reported_total,
            board_enumerated=r.board_enumerated, held=held, censored=censored,
        )
        measured = bucket == "measured"
        out.append(
            BoardCoverage(
                company_id=int(r.id), name=str(r.name), provider=str(r.provider),
                bucket=bucket, held=held,
                board_reported_total=r.board_reported_total,
                board_enumerated=r.board_enumerated,
                detail_deferred=r.detail_deferred,
                shortfall=(r.board_reported_total - held) if measured else None,
                ratio=(held / r.board_reported_total)
                if measured and r.board_reported_total else None,
            )
        )
    return out
```

`src/boardwatch/cli/coverage_cmd.py`:

```python
"""`boardwatch coverage` — what each board says it has, against what we hold. Read-only."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from boardwatch.reports.board_coverage import build_report
from boardwatch.store.coverage_queries import load_board_coverage
from boardwatch.store.engine import get_engine


def coverage(
    run: int | None = typer.Option(None, "--run", help="Scan run to report. Default: latest."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    with get_engine().begin() as conn:
        report = build_report(load_board_coverage(conn, run_id=run))
    if as_json:
        typer.echo(json.dumps({
            "bucket_counts": report.bucket_counts,
            "measured_held": report.measured_held,
            "measured_total": report.measured_total,
            "global_ratio": report.global_ratio,
            "corpus_boards": report.corpus_boards,
            "boards": [asdict(b) for b in report.boards],
        }, indent=2))
        return
    for b in sorted(report.boards, key=lambda x: (x.ratio is None, x.ratio or 0.0)):
        pct = "     —" if b.ratio is None else f"{100 * b.ratio:5.1f}%"
        short = "" if b.shortfall is None else f"  short {b.shortfall:+,}"
        typer.echo(f"{pct}  {b.bucket:<16}{b.name:<28}{b.held:>7,}{short}")
    typer.echo("")
    for bucket, n in report.bucket_counts.items():
        typer.echo(f"  {bucket:<16}{n:>4}")
    ratio = "not measurable" if report.global_ratio is None else f"{100 * report.global_ratio:.1f}%"
    typer.echo(
        f"\nmeasured coverage {ratio} "
        f"({report.measured_held:,} held of {report.measured_total:,} stated) "
        f"over {report.bucket_counts['measured']} of {report.corpus_boards} watched boards"
    )
```

Register it in `src/boardwatch/cli/app.py` alongside the existing leaf commands:

```python
from boardwatch.cli.coverage_cmd import coverage

app.command("coverage")(coverage)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_coverage_cmd.py -v --no-cov -n 0`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/cli/coverage_cmd.py src/boardwatch/store/coverage_queries.py \
        src/boardwatch/cli/app.py tests/cli/test_coverage_cmd.py
git commit -m "Add a read-only boardwatch coverage report (D-271)"
```

---

### Task 9: A behaviour test this change did not author

**Files:**
- Create: `tests/integration/test_coverage_detects_a_shrinking_board.py`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

**Why this task exists:** every test so far was written alongside the code it checks, so each one agrees with its author. This one asserts an end-to-end behaviour nobody wrote code against: when a board's stated total rises and our holdings do not, coverage must **fall**. If it cannot fall, the instrument is decorative.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_coverage_detects_a_shrinking_board.py
from sqlalchemy import select

from boardwatch.reports.board_coverage import build_report
from boardwatch.store.coverage_queries import load_board_coverage


def test_coverage_falls_when_a_board_grows_and_we_do_not(store_conn, board_factory) -> None:
    """The instrument must be able to REPORT A LOSS. A metric that only ever prints 100% has
    not been shown to detect anything."""
    board = board_factory(provider="workday", name="Citi")
    board.scan(run_id=1, status="partial", board_reported_total=1000,
               board_enumerated=1000, detail_deferred=400, held=600)
    before = build_report(load_board_coverage(store_conn, run_id=1))

    board.scan(run_id=2, status="partial", board_reported_total=4589,
               board_enumerated=2214, detail_deferred=1614, held=600)
    after = build_report(load_board_coverage(store_conn, run_id=2))

    assert before.global_ratio == 0.6
    assert after.global_ratio < before.global_ratio
    assert after.boards[0].shortfall == 3989


def test_a_board_that_goes_dark_does_not_read_as_full_coverage(store_conn, board_factory) -> None:
    board = board_factory(provider="workday", name="Snowflake")
    board.scan(run_id=1, status="failed", board_reported_total=None,
               board_enumerated=None, detail_deferred=None, held=0)
    report = build_report(load_board_coverage(store_conn, run_id=1))
    assert report.bucket_counts["dark"] == 1
    assert report.global_ratio is None
    assert report.corpus_boards == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_coverage_detects_a_shrinking_board.py -v --no-cov -n 0`
Expected: FAIL — `fixture 'board_factory' not found`

- [ ] **Step 3: Write minimal implementation**

Add `board_factory` to `tests/integration/conftest.py`. It inserts a `companies` row, then one `board_scans` row plus `held` open `postings` rows per `scan()` call. No production code changes — if any production change is needed to make these pass, that is a real defect found by the test and it should be fixed in the relevant task above.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_coverage_detects_a_shrinking_board.py -v --no-cov -n 0`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_coverage_detects_a_shrinking_board.py tests/integration/conftest.py
git commit -m "Assert the coverage instrument can report a loss (D-271)"
```

---

### Task 10: `DEFAULT_TOP_N` 8 → 40

**Files:**
- Modify: `src/boardwatch/pipeline/runner.py:96`
- Test: `tests/pipeline/test_runner.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DEFAULT_TOP_N = 40`. Read by `cli/run_cmd.py:57` and `cli/eligibility_cmd.py:692,752`, all of which pick it up automatically.

**Evidence:** run 67 discarded **3,502 postings that cleared every gate** to show 8. job-apps' comparable median is 42/day and is a natural yield with no top-N anywhere. Ruled by Mit in D-272. Note the cost is real and is the *render*, not the fetch: 40 leads means 40 tailored résumés and 40 PDFs per run.

- [ ] **Step 1: Write the failing test**

```python
# tests/pipeline/test_runner.py
from boardwatch.pipeline.runner import DEFAULT_TOP_N


def test_default_top_n_is_forty() -> None:
    """D-272. The cap is a DISPLAY limit, not a filter — run 67 cut 3,502 qualifying postings.
    It also gates P7, whose rule 'judge a source by leads over >=3 runs' cannot run while the
    numerator is fixed at 8 by construction."""
    assert DEFAULT_TOP_N == 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_runner.py -k default_top_n -v --no-cov -n 0`
Expected: FAIL — `assert 8 == 40`

- [ ] **Step 3: Write minimal implementation**

In `src/boardwatch/pipeline/runner.py`, replace line 96:

```python
# D-272. Was 8, which discarded 3,502 postings per run that had cleared every gate. A display
# limit, never a filter: everything beyond it is counted into `capped_by_top_n` and stays
# status='open'. 40 matches job-apps' measured median of 42/day. The cost is the render — 40
# leads means 40 tailored résumés and 40 PDFs.
DEFAULT_TOP_N = 40
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipeline/test_runner.py -v --no-cov -n 0`
Expected: PASS. Any test asserting a lead count of 8 will now fail — those are real and must be updated to the new cap, not worked around.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/pipeline/runner.py tests/pipeline/test_runner.py
git commit -m "Raise DEFAULT_TOP_N from 8 to 40 (D-272)"
```

---

### Task 11: Full gate, then the funnel section decision

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/program/STATE.md`, `docs/program/METRICS.md`

**Interfaces:**
- Consumes: everything.
- Produces: a green `make check` and an updated program record.

- [ ] **Step 1: Run the full gate, detached**

From the repo root:

```bash
( setsid nohup sh -c 'make check >/tmp/bw-check.log 2>&1; echo "EXIT=$?" >>/tmp/bw-check.log' \
  </dev/null >/dev/null 2>&1 & )
```

Poll with `tail -5 /tmp/bw-check.log` until `EXIT=` appears. Do NOT pipe `make check` through `head`/`tail` directly — SIGPIPE kills the run and you will read a false negative.

- [ ] **Step 2: Confirm the gate is genuinely green**

Expected: `EXIT=0` in `/tmp/bw-check.log`. A failed command is not a negative result — confirm the line is present before reading silence as success.

- [ ] **Step 3: Update CHANGELOG and the program docs**

Add a CHANGELOG entry under Unreleased naming the `boardwatch coverage` command, the three new `board_scans` columns, the Workday facet-sum censor detection, and the cap change. Then update `STATE.md`'s standing (the coverage instrument is now built) and append a `METRICS.md` session row with the first real coverage numbers from `boardwatch coverage --json`.

- [ ] **Step 4: Reindex and re-gate**

Run: `make reindex && make index-check` — expected exit 0 for both. `make check` fails on a stale index (D-109).

- [ ] **Step 5: Commit and open the PR**

```bash
git add CHANGELOG.md docs/program/STATE.md docs/program/METRICS.md
git commit -m "Record the coverage instrument and the cap change"
git push -u origin <branch>
gh pr create --base main --title "Ship the coverage instrument and raise the cap (D-271, D-272)"
```

**Owner-gated, do NOT do unilaterally:** adding a `board_coverage` section to the funnel artifact requires an `artifact_version` bump. That is a shipped-schema change and is Mit's call, the same class as D-267's `locations` on `Lead`. The CLI report in Task 8 delivers the value without it; raise the bump separately.

---

## Self-Review

**1. Spec coverage.** §3.1 five-bucket partition → Task 7. §3.2 steps 1–4 → Tasks 1, 2, 3, 4, 5, 6. §3.2 step 5 (facet sum) → Task 4. §3.2 step 6 (CLI report) → Task 8; the funnel section is deliberately deferred and flagged owner-gated in Task 11. §3.3 risks: unfailable ratio → Task 7 test 1 and Task 6; 2,000 censor → Task 4; counting semantics → `shortfall` in Task 7; dark denominator → Task 7 test 5; staleness → `classify_board` "unchanged" branch; rounding → `shortfall` reported beside the ratio; not-independent → docstring wording in Task 4; known positive → Task 4 test 2 and Task 9. §3.4 testing → Task 9. Track 2 → Task 10. **Gap found and closed:** the spec's "age-stamp every total, refuse a ratio older than N runs" is only partly served — `load_board_coverage` reads a single run, so a carried-forward stale total cannot arise yet. Recorded rather than built, because building the refusal before there is a carry-forward path would be a check that cannot fire.

**2. Placeholder scan.** No TBD, no "add error handling", no "similar to Task N". Every code step has real code. Task 9 step 3 describes a fixture rather than showing it — acceptable because the fixture shape depends on the existing `tests/integration/conftest.py`, which the executor will read; the assertions it must satisfy are fully specified in step 1.

**3. Type consistency.** `board_reported_total` / `board_enumerated` / `detail_deferred` are spelled identically in Tasks 1–8. `classify_board` keyword-only signature in Task 7 matches its call in Task 8. `BoardCoverage` field order in Task 7's dataclass matches every construction site. `CoverageBucket` literals match the `_ALL_BUCKETS` tuple and the CLI test's expected key set.
