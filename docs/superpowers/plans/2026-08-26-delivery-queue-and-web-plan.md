# Implementation plan — delivery queue + local review web app

Design: `docs/superpowers/specs/2026-08-26-run-results-and-web-review-design.md` (rev 3).
Branch: `feat/delivery-queue-and-web`. Worktree: `~/dev/projectY/bw-delivery`.

**TDD throughout.** Write the failing test first, confirm it fails for the right reason, then implement.
`make check` is the only gate. Never pipe it through `head`/`tail`.

## Locked interfaces — do not deviate, other tasks are written against these

```python
# src/boardwatch/delivery/names.py   — PURE. No I/O, no Path.exists, no store import.
@dataclass(frozen=True)
class LeadNames:
    folder: str          # "Intel_EDA_Tools_Software_Engineer"
    pdf: str             # "Mit_Sheth_Intel_EDA_Tools_Software_Engineer.pdf"

def slug(value: str) -> str: ...

def plan_lead_names(*, root: Path, owner_name: str, company: str, title: str,
                    identity_hash: str) -> LeadNames: ...
# `root` is used ONLY to compute the byte budget; the function never touches the filesystem.
# Budget target is <root>/_skipped/<folder>/<pdf> — the longest final destination.
```

```python
# src/boardwatch/store/db.py   — APPEND ONLY. Do not modify get_engine.
def get_readonly_engine(data_dir: Path) -> Engine: ...
```

```python
# src/boardwatch/store/applications.py   — APPEND ONLY.
class MarkOutcome(StrEnum):
    CREATED = "created"; TRANSITIONED = "transitioned"; UNCHANGED = "unchanged"
    NO_POSTING = "no_posting"; NO_JOB = "no_job"

@dataclass(frozen=True)
class MarkResult:
    outcome: MarkOutcome
    job_id: int | None = None
    application_id: int | None = None

def mark_job_applied(conn: Connection, *, posting_id: int, source: str) -> MarkResult: ...
```

```python
# src/boardwatch/store/queue_state.py   — NEW. Skip state, on app_state. No migration.
SKIP_KEY_PREFIX = "queue.skipped."
def mark_job_skipped(conn: Connection, *, job_id: int, at: datetime) -> None: ...
def unmark_job_skipped(conn: Connection, *, job_id: int) -> None: ...
def skipped_job_ids(conn: Connection) -> dict[int, str]: ...   # job_id -> ISO timestamp
```

```python
# src/boardwatch/store/delivery_queries.py   — NEW. READ ONLY. Every function is a select.
@dataclass(frozen=True)
class QueueRow:
    posting_id: int; job_id: int; title: str; company: str
    location: str | None; remote_policy: str | None
    posted_days: int | None; first_seen: datetime
    status: str                      # "open" | "closed"
    verdict: str | None              # "eligible" | "uncertain" | "ineligible" | None
    apply_url: str | None
    delivered_run_id: int | None
    tex_uri: str; pdf_uri: str | None
    target_flag: bool | None

@dataclass(frozen=True)
class QueueDetail:
    row: QueueRow
    jd_body: str | None              # None = no current version; never "" for that case
    requirements: list[RequirementView]
    board_target: str | None

def delivered_unapplied(conn: Connection, *, skipped: set[int]) -> list[QueueRow]: ...
def queue_detail(conn: Connection, posting_id: int) -> QueueDetail | None: ...
```

```python
# src/boardwatch/delivery/queue.py
def sync_queue(conn, *, root: Path, owner_name: str) -> SyncReport: ...
def reconcile_queue(conn, *, root: Path) -> ReconcileReport: ...
```

## HTTP contract — the frontend is written against exactly this

All `/api/*` require `Authorization: Bearer <token>`. 401 without it. Loopback only. `Host` checked.

| Method | Path | Response |
|---|---|---|
| GET | `/api/queue` | `{ rows: QueueRow[], counts: { in_queue, eligible, uncertain, applied_ever, skipped, delivered_last_run, last_run_finished } }` |
| GET | `/api/queue/{posting_id}` | `QueueDetail` |
| GET | `/api/rest?limit&offset` | `{ rows: RestRow[], as_of: iso, total }` |
| GET | `/api/pdf/{posting_id}` | PDF bytes, `Content-Disposition: inline; filename="<human name>"` |
| POST | `/api/queue/{posting_id}/applied` | `{ outcome, job_id }` |
| POST | `/api/queue/{posting_id}/skipped` | `{ outcome }` |
| POST | `/api/queue/{posting_id}/unskip` | `{ outcome }` |
| POST | `/api/queue/{posting_id}/reveal` | `{ ok: bool, reason?: string }` |
| GET | `/api/answers` | `{ identity: {..}, work_auth: {..}, education: [..], questions: [{q,a,note}] }` |
| GET | `/api/runs` | `{ runs: [{ id, started, finished, status, boards_attempted, boards_complete, postings_seen, new_count, leads }] }` |
| GET | `/api/runs/{run_id}` | the run's funnel JSON, passed through |

`QueueRow` JSON adds three derived booleans the API computes, not the store:
`thin_jd`, `off_target`, `pdf_available`.

**Counts rule (D-312).** `eligible` is the affirmatively-eligible count and is the headline yield.
`uncertain` is its own visible bucket and is NEVER summed into it. `applied_ever`, not applied-today.

## Phase 1 — five tasks, fully parallel, disjoint files

| Task | Owns these files, and nothing else |
|---|---|
| **T1 names** | `src/boardwatch/delivery/__init__.py`, `src/boardwatch/delivery/names.py`, `tests/unit/test_delivery_names.py` |
| **T2 read-only engine** | `src/boardwatch/store/db.py` (append only), `tests/unit/test_readonly_engine.py` |
| **T3 applied + skip state** | `src/boardwatch/store/applications.py` (append only), `src/boardwatch/store/queue_state.py`, `tests/unit/test_mark_job_applied.py`, `tests/unit/test_queue_state.py` |
| **T4 queries** | `src/boardwatch/store/delivery_queries.py`, `tests/unit/test_delivery_queries.py` |
| **T5 frontend** | `web/**` only. No Python. |

## Phase 2 — after phase 1 lands

| Task | Owns |
|---|---|
| **T6 projection** | `src/boardwatch/delivery/queue.py`, `tests/unit/test_delivery_queue.py` |
| **T7 server + CLI** | `src/boardwatch/delivery/api.py`, `src/boardwatch/delivery/server.py`, `src/boardwatch/cli/web_cmd.py`, `src/boardwatch/cli/app.py` (registration line only), `tests/unit/test_web_server.py` |
| **T8 run hook** | `src/boardwatch/pipeline/runner.py` — ONE call to `sync_queue`, wrapped so a failure logs and never fails the run, mirroring `_emit_funnel`. Coordinate: another session also edits this file. |

## Non-negotiables for every task

- The dated output tree is **untouched**. Do not rename `_slug`, `tailored-<pid>.*`, the sidecars, or move
  anything under `~/boardwatch-applications/`. Do not write an `artifacts` row pointing into the queue.
- Queue folders contain **only** the copied PDF, the apply link file, `job_description.txt` and
  `details.json`. Never `resume.projected.yaml`, never `projection-manifest.json` — the fabrication
  audit counts directories by those two names and would silently pass over an empty set.
- `mypy --strict` clean. `ruff check .` clean. **Never run `ruff format`** — this repo is hand-formatted.
- No new runtime dependency. Standard library only on the Python side.
- Tests must fail against the wrong implementation. A test that passes either way is not done.
