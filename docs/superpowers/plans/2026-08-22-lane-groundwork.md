# Lane groundwork (JD acquisition, phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land every persistence, attribution and failure-reporting guarantee a JD-acquisition
lane needs, so that the first lane's client code is the only thing left to write.

**Architecture:** A lane is not a seventh `Provider`. It is a separate protocol that returns the
same `BoardSnapshot` — always `status="partial"` — and goes through the existing `apply_board`, so
it inherits every persistence invariant instead of restating them. Around that seam this plan adds
a closed catalog of acquisition outcomes with a counter per value, per-source stub attribution, and
a hard per-run cap on newly created companies.

**Tech Stack:** Python 3.11–3.13, pydantic v2 frozen models, SQLAlchemy Core, pytest. No new
runtime dependency.

**Spec:** `docs/superpowers/specs/2026-08-22-jd-acquisition-design.md` (owner rulings in D-278)

## Global Constraints

- `make check` is the only gate. Launch it detached with a done-sentinel; the Bash tool clamps
  `timeout` to 10 minutes and a foreground run reads as `Error 143`. Narrow runs: `--no-cov -n 0`.
- **A lane is never a registered `Provider`.** `tests/unit/test_provider_registry.py::test_build_providers_one_instance_per_class_keyed_by_name`
  asserts `set(built) ==` the six names — a set *equality* — and fixture rule R13 in
  `tools/generalization/fixtures.py` demands a flat pinned fixture dir per registered provider,
  both directions.
- **Every lane snapshot is `status="partial"`.** `_process_missing` and `_persist_validators` run on
  `"complete"` only, and `BoardSnapshot` permits an empty `complete`, which sets
  `effective = frozenset()`, marks every open posting of that company missing, and closes them after
  `CLOSE_AFTER_MISSES = 2` consecutive scans.
- **`listed_ids` stays empty for a lane.** `_reset_listed_but_unrefreshed` returns immediately on an
  empty set (`scan/apply.py:266`); a non-empty one would assert a board enumeration the lane never did.
- `postings.job_id` is nullable with an ABORT trigger (`postings_job_required_insert`) — insert into
  `jobs` first, as `_apply_listed` does.
- `_write_posting_identity` is mandatory for every open posting. Skipping one makes
  `identities_complete()` False, which turns suppression off **corpus-wide** and degrades every
  `SourceOutcome.unique` to `None`.
- `companies.source` has `CheckConstraint("source IN ('registry','user')")`.
- `board_scans.status` must be one of the four `SnapshotStatus` values, or
  `reports/board_coverage.classify_board` raises `UnknownScanStatus` and takes down the whole
  coverage report.
- Coverage fields (`board_reported_total`, `board_enumerated`, `detail_deferred`,
  `board_total_censored`) stay `None` on a lane snapshot. Never backfill with `len(postings)` — an
  unfailable ratio is worse than no ratio.
- Out-of-catalog is a failure, never a new bucket. Typed violations raised at the site that knows.
- Politeness stays boardwatch's: `PER_HOST_DELAY_FLOOR = 0.25`, default
  `per_host_delay_seconds = 1.0`, per-host lock held for the request's duration.
- Honest UA (`boardwatch/{version} (+https://github.com/mit112/boardwatch)`) stays on the six ATS
  providers. A browser UA applies only to new aggregator fetches.
- Surgical diffs. No reformatting of adjacent code.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/boardwatch/lanes/__init__.py` | New package marker. Nothing else. |
| `src/boardwatch/lanes/outcomes.py` | The closed acquisition-outcome catalog and its tally. Pure; no I/O. |
| `src/boardwatch/lanes/base.py` | The `Lane` protocol and `lane_snapshot()`, the only way to build a lane's `BoardSnapshot`. |
| `src/boardwatch/lanes/admission.py` | The per-run new-company cap and its typed refusals. |
| `src/boardwatch/store/run_funnel_queries.py` | Modify: per-company stub counts, and a `stubs` field on `SourceOutcome`. |
| `tests/unit/test_lane_outcomes.py` | Catalog closure, counter completeness, silent-outage detection. |
| `tests/unit/test_lane_snapshot.py` | A lane cannot express `complete`; the six-provider registry is unchanged. |
| `tests/pipeline/test_lane_apply.py` | `apply_board` on a lane snapshot does not close a company's other postings, and the `complete` counterexample that proves the test can fail. |
| `tests/unit/test_lane_admission.py` | The cap admits, refuses, and reports; existing companies are free. |
| `tests/unit/test_stub_attribution.py` | Per-source stub counts sum to the corpus count. |

Phase 1 deliberately contains **no network code**. See "Not in this plan" at the end.

---

## Task 1: Body-less postings never earn a suppressing identity

**Status: COMPLETE this session** on branch `fix/bodyless-exact-quad`. Recorded here because the
spec (§4.3) makes it a precondition for any lane row, so a reader of this plan must not re-do it.

**Files:**
- Modified: `src/boardwatch/core/posting_identity.py` — added `body_evidence()`, gated `exact_quad`
- Modified: `src/boardwatch/core/dedup.py` — `_verify_quad` requires body PRESENCE, not equality
- Test: `tests/unit/test_posting_identity.py`, `tests/unit/test_dedup_resolver.py`

What it fixed: `content_hash("")` and `content_hash("   \n\t ")` are both the SHA-256 of the empty
string, that hash is a component of `exact_quad` (the only suppressing kind), and `_verify_quad`
re-verified with `normalize_body(a) == normalize_body(b)` where `"" == ""` passes. Two genuinely
different body-less postings at one company sharing a normalized title and locations suppressed
each other, verifier agreeing. Demonstrated before the fix as
`Suppression(posting_id=2, survivor_posting_id=1, kind='exact_quad')`.

No `IDENTITY_ALGORITHM_VERSION` bump: no normalizer, key tuple or host-class table changed. The
stored rows written before the check are neutralised by the `_verify_quad` presence test, and
`write_identities` drops each one as an unwanted kind the next time that posting is written.

---

## Task 2: The acquisition-outcome catalog

Ten outcomes, each with its own counter, so a tier that recovers nothing is a reportable condition
rather than an exit-0 silence. This is job-apps' 11-day invisible outage inverted: there, a missing
dependency, a timeout and an empty page were all one empty string behind `except Exception: return ""`.

**Files:**
- Create: `src/boardwatch/lanes/__init__.py`
- Create: `src/boardwatch/lanes/outcomes.py`
- Test: `tests/unit/test_lane_outcomes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AcquisitionOutcome` (Literal of ten strings), `ACQUISITION_OUTCOMES: tuple[str, ...]`,
  `UnknownAcquisitionOutcome(ValueError)`, `AcquisitionTally` with
  `.record(outcome: str) -> None`, `.counts -> Mapping[str, int]` (all ten keys always present),
  `.attempted -> int`, `.resolved -> int`, `.is_silent_outage -> bool`.

- [ ] **Step 1: Write the failing test**

```python
"""The acquisition-outcome catalog (JD-acquisition spec §4.4)."""

import pytest

from boardwatch.lanes.outcomes import (
    ACQUISITION_OUTCOMES,
    AcquisitionTally,
    UnknownAcquisitionOutcome,
)


def test_the_catalog_is_the_ten_outcomes_the_spec_names():
    assert set(ACQUISITION_OUTCOMES) == {
        "body_inline",
        "body_fetched",
        "fetch_refused",
        "fetch_gone",
        "fetch_unavailable",
        "dependency_missing",
        "extracted_empty",
        "rejected_login_wall",
        "rejected_quality_gate",
        "not_attemptable",
    }


def test_an_out_of_catalog_outcome_raises_at_the_recording_site():
    """Out-of-catalog is a failure, never a new bucket."""
    tally = AcquisitionTally()
    with pytest.raises(UnknownAcquisitionOutcome) as excinfo:
        tally.record("body_probably_fine")
    assert excinfo.value.name == "body_probably_fine"


def test_every_outcome_carries_a_counter_even_at_zero():
    """A zero must be present and readable, not absent.

    An absent key is what let job-apps run 11 scheduled days at zero recoveries without
    anyone noticing. Every one of the ten is instrumented, so 0 here is a measured zero.
    """
    tally = AcquisitionTally()
    tally.record("body_inline")
    assert set(tally.counts) == set(ACQUISITION_OUTCOMES)
    assert tally.counts["body_inline"] == 1
    assert tally.counts["fetch_refused"] == 0


def test_attempted_partitions_into_the_ten_counters():
    tally = AcquisitionTally()
    for outcome in ("body_inline", "body_inline", "fetch_gone", "rejected_login_wall"):
        tally.record(outcome)
    assert tally.attempted == 4
    assert sum(tally.counts.values()) == tally.attempted


def test_resolved_counts_only_the_two_body_bearing_outcomes():
    tally = AcquisitionTally()
    for outcome in ("body_inline", "body_fetched", "extracted_empty", "fetch_refused"):
        tally.record(outcome)
    assert tally.resolved == 2


def test_a_tier_that_resolved_nothing_from_real_attempts_is_a_reportable_condition():
    tally = AcquisitionTally()
    for _ in range(53):
        tally.record("fetch_unavailable")
    assert tally.is_silent_outage


def test_a_tier_with_no_attempts_at_all_is_not_an_outage():
    """Nothing to do is not the same as everything failing."""
    assert not AcquisitionTally().is_silent_outage


def test_one_resolution_clears_the_outage_condition():
    tally = AcquisitionTally()
    tally.record("fetch_unavailable")
    tally.record("body_inline")
    assert not tally.is_silent_outage
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/unit/test_lane_outcomes.py --no-cov -n 0 -q`
Expected: collection error, `ModuleNotFoundError: No module named 'boardwatch.lanes'`

- [ ] **Step 3: Write minimal implementation**

`src/boardwatch/lanes/__init__.py`:

```python
"""JD-acquisition lanes (JD-acquisition spec §4). A lane is not a Provider — see base.py."""
```

`src/boardwatch/lanes/outcomes.py`:

```python
"""The closed catalog of JD-acquisition outcomes (JD-acquisition spec §4.4).

Every outcome is a distinct typed value with its own counter, raised at the site that knows
which one applies. The specification for this is job-apps' failure mode inverted: its
`fetch_rendered_jd` wraps everything in `except Exception: return ""`, so a missing browser
dependency, a timeout and a login wall are one empty string. Its browser tier then ran 11
consecutive scheduled runs recovering exactly zero without failing anything.

`is_silent_outage` exists so that condition is reportable. A tier that attempted work and
resolved nothing is not a benign zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

AcquisitionOutcome = Literal[
    # A body arrived with the listing itself. No extra request. Indeed's search response.
    "body_inline",
    # A body arrived from a second request against a resolvable posting URL.
    "body_fetched",
    # 401 / 403. The host knows who we are and said no.
    "fetch_refused",
    # 404 / 410. The posting is gone; this is not a fetch defect.
    "fetch_gone",
    # Timeout, 5xx, transport error. Retryable in principle, absent in fact.
    "fetch_unavailable",
    # A dependency the tier needs is not installed. NEVER folded into a fetch failure —
    # this is the exact confusion that hid job-apps' outage for 11 days.
    "dependency_missing",
    # A response arrived and extraction produced nothing substantive.
    "extracted_empty",
    # The two-sided login-wall test fired (spec §4.5): >=2 wall markers AND zero real-JD
    # section markers. One-sided fails — nearly every real posting says "Sign in" in a footer.
    "rejected_login_wall",
    # Extracted, but below the quality floor, or the body declared a different role family.
    "rejected_quality_gate",
    # No resolvable posting URL existed to attempt. Counted, not skipped silently.
    "not_attemptable",
]

ACQUISITION_OUTCOMES: tuple[str, ...] = get_args(AcquisitionOutcome)

# The only two outcomes that produced a usable body. Named rather than derived by exclusion
# so that adding an outcome cannot silently make it count as a success.
_RESOLVED: frozenset[str] = frozenset({"body_inline", "body_fetched"})


class UnknownAcquisitionOutcome(ValueError):
    """Raised at the recording site for an outcome outside the closed catalog."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown acquisition outcome: {name!r}")
        self.name = name


class AcquisitionTally:
    """Counts every acquisition attempt by outcome, with all ten keys always present."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = dict.fromkeys(ACQUISITION_OUTCOMES, 0)

    def record(self, outcome: str) -> None:
        if outcome not in self._counts:
            raise UnknownAcquisitionOutcome(outcome)
        self._counts[outcome] += 1

    @property
    def counts(self) -> Mapping[str, int]:
        return dict(self._counts)

    @property
    def attempted(self) -> int:
        return sum(self._counts.values())

    @property
    def resolved(self) -> int:
        return sum(count for name, count in self._counts.items() if name in _RESOLVED)

    @property
    def is_silent_outage(self) -> bool:
        """Attempts were made and none produced a body.

        Not `resolved == 0` alone: a tier with nothing to do is not an outage, and reporting
        one would train the reader to ignore the signal.
        """
        return self.attempted > 0 and self.resolved == 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/unit/test_lane_outcomes.py --no-cov -n 0 -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/lanes/__init__.py src/boardwatch/lanes/outcomes.py tests/unit/test_lane_outcomes.py
git commit -m "Add the closed acquisition-outcome catalog and its tally"
```

---

## Task 3: The `Lane` protocol, and a lane that cannot express `complete`

**Files:**
- Create: `src/boardwatch/lanes/base.py`
- Test: `tests/unit/test_lane_snapshot.py`
- Test: `tests/integration/test_lane_apply.py`

**Interfaces:**
- Consumes: `AcquisitionTally` from Task 2.
- Produces: `lane_snapshot(postings: list[RawPosting], url: str) -> BoardSnapshot`,
  `LaneCompanySnapshot(company_name: str, snapshot: BoardSnapshot)`,
  `LaneResult(snapshots: tuple[LaneCompanySnapshot, ...], tally: AcquisitionTally)`,
  and the `Lane` protocol with `name: str` and `collect(self, fetcher: Fetcher) -> LaneResult`.
  The lane does NOT take the company budget: it collects, and the caller admits companies
  against `CompanyBudget` (Task 5). Keeping admission out of the lane is what lets one budget
  bound every lane in a run rather than each lane holding its own.

- [ ] **Step 1: Write the failing unit test**

```python
"""A lane returns BoardSnapshots and is not a Provider (JD-acquisition spec §4.1, §4.2)."""

import pytest

from boardwatch.core.models import RawPosting
from boardwatch.lanes.base import lane_snapshot
from boardwatch.providers.registry import build_providers


def _raw(pid: str = "in-1") -> RawPosting:
    return RawPosting(
        provider_posting_id=pid,
        title="Software Engineer, New Grad",
        url=f"https://example.test/jobs/{pid}",
        locations=["Seattle, WA"],
        body_text="we are hiring a new grad engineer",
        raw_json={},
    )


def test_a_lane_snapshot_is_always_partial():
    """`complete` is unexpressible. An empty `complete` closes a company's whole board."""
    assert lane_snapshot([_raw()], "https://example.test/search").status == "partial"
    assert lane_snapshot([], "https://example.test/search").status == "partial"


def test_a_lane_snapshot_never_claims_a_board_enumeration():
    snapshot = lane_snapshot([_raw()], "https://example.test/search")
    assert snapshot.listed_ids == frozenset()
    assert snapshot.board_reported_total is None
    assert snapshot.board_enumerated is None
    assert snapshot.detail_deferred is None
    assert snapshot.board_total_censored is None


def test_the_provider_registry_still_holds_exactly_the_six_ats_families():
    """A lane must never be registered: fixture rule R13 fires on a provider with no fixtures."""
    assert set(build_providers()) == {
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "workable",
        "workday",
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest tests/unit/test_lane_snapshot.py --no-cov -n 0 -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'boardwatch.lanes.base'`

- [ ] **Step 3: Write the implementation**

```python
"""The Lane protocol (JD-acquisition spec §4.1, §4.2).

A lane is NOT a seventh Provider, for two verified reasons: the provider registry test
asserts set EQUALITY against the six names, and fixture rule R13 requires a flat pinned
fixture dir per registered provider in both directions. A lane also does not fit the
protocol — `Provider` declares board_url / fetch_board / healthcheck and no fetch_posting,
and `registry` duck-types five further undeclared members.

What a lane does instead is return the same `BoardSnapshot` that a provider returns, so it
reuses `scan.apply.apply_board` and inherits every persistence invariant rather than
restating them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.lanes.outcomes import AcquisitionTally


def lane_snapshot(postings: list[RawPosting], url: str) -> BoardSnapshot:
    """The only sanctioned way to build a lane's snapshot. Always `partial`.

    `partial` rather than `complete` is load-bearing, not conservative: `_process_missing`
    runs on `complete` only, and `BoardSnapshot` permits an EMPTY `complete`, which sets
    `effective = frozenset()` and marks every open posting of that company missing — two
    consecutive such scans close them all (`CLOSE_AFTER_MISSES = 2`). A lane never
    enumerates a whole board, so it can never make that claim truthfully.

    `listed_ids` stays empty for the same reason. `_reset_listed_but_unrefreshed` returns
    immediately on an empty set, which is the correct behaviour here; a non-empty set would
    assert an enumeration the lane did not perform.

    The coverage fields stay None. `board_reported_total` must never be backfilled from
    `len(postings)` — D-271 records that an unfailable ratio is worse than no ratio.
    """
    return BoardSnapshot(status="partial", postings=postings, url=url)


@dataclass(frozen=True)
class LaneCompanySnapshot:
    """One company's postings from this lane. `apply_board` is per-company."""

    company_name: str
    snapshot: BoardSnapshot


@dataclass(frozen=True)
class LaneResult:
    snapshots: tuple[LaneCompanySnapshot, ...]
    tally: AcquisitionTally


class Lane(Protocol):
    name: str

    def collect(self, fetcher: Fetcher) -> LaneResult: ...
```

- [ ] **Step 4: Run it to verify it passes**

Run: `./.venv/bin/python -m pytest tests/unit/test_lane_snapshot.py --no-cov -n 0 -q`
Expected: 3 passed

- [ ] **Step 5: Write the test that proves the invariant holds through `apply_board`**

This is the test worth having. Step 1 proves the status string; only this proves the
consequence the spec warns about. Fixtures below are the ones `tests/unit/test_scan_apply.py`
already uses — `get_engine(tmp_path)` + `ensure_schema`, a locally inserted company, and
`insert_run`. Do not add a parallel fixture set.

Create `tests/pipeline/test_lane_apply.py`:

```python
"""A lane snapshot must not close the postings it did not mention (spec §4.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.lanes.base import lane_snapshot
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _insert_company(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def _raw(pid: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=pid,
        title="Software Engineer, New Grad",
        url=f"https://boards.greenhouse.io/acme/jobs/{pid}",
        locations=["Seattle, WA"],
        body_text="we are hiring a new grad engineer",
        raw_json={},
    )


def _open_ids(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row.provider_posting_id
            for row in conn.execute(
                select(tables.postings.c.provider_posting_id, tables.postings.c.status)
            ).all()
            if row.status == "open"
        }


def test_two_consecutive_lane_scans_do_not_close_a_companys_other_postings(engine: Engine) -> None:
    """CLOSE_AFTER_MISSES is 2, so ONE scan would not have proved this."""
    company_id = _insert_company(engine)
    seeded = BoardSnapshot(
        status="complete",
        postings=[_raw("a"), _raw("b"), _raw("c")],
        url="https://boards.greenhouse.io/acme",
    )
    apply_board(engine, seeded, company_id, insert_run(engine))
    assert _open_ids(engine) == {"a", "b", "c"}

    only_one = lane_snapshot([_raw("a")], "https://example.test/search")
    apply_board(engine, only_one, company_id, insert_run(engine))
    apply_board(engine, only_one, company_id, insert_run(engine))

    assert _open_ids(engine) == {"a", "b", "c"}


def test_the_same_two_scans_marked_complete_would_have_closed_them() -> None:
    """The counterexample, so the test above cannot pass for the wrong reason.

    Without it, `test_two_consecutive...` passes even if `apply_board` never closes anything
    at all — a test that cannot distinguish the fix from a no-op. Build the identical scans
    with status="complete" and assert b and c close, proving `partial` is what saved them.
    """
```

Write the second test's body by copying the first and swapping `lane_snapshot(...)` for a
`BoardSnapshot(status="complete", postings=[_raw("a")], url=...)`, then asserting
`_open_ids(engine) == {"a"}`. If that assertion does NOT hold, stop: either
`CLOSE_AFTER_MISSES` is not 2 on this build or the seed did not persist, and the first test's
pass means nothing until you know which.

- [ ] **Step 6: Run it, then commit**

```bash
./.venv/bin/python -m pytest tests/pipeline/test_lane_apply.py --no-cov -n 0 -q
git add src/boardwatch/lanes/base.py tests/unit/test_lane_snapshot.py tests/pipeline/test_lane_apply.py
git commit -m "Add the Lane protocol and prove a lane snapshot closes nothing"
```

---

## Task 4: Per-source stub attribution

Required to land with the first lane. `count_stub_postings` is corpus-wide with no source filter
and `SourceOutcome` has no stub field, so today a lane's stub rate moves the global number with
nothing naming the lane — and P7 judges a source by leads over >=3 runs.

**Files:**
- Modify: `src/boardwatch/store/run_funnel_queries.py` (beside `count_stub_postings`, line 149,
  and `SourceOutcome`, line 379)
- Test: `tests/unit/test_stub_attribution.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `count_stub_postings_by_company(conn) -> dict[int, int]`, and
  `SourceOutcome.stubs: int` — instrumented, so 0 is a measured zero and never `None`.

- [ ] **Step 1: Write the failing test**

```python
"""Per-source stub attribution (JD-acquisition spec §4.4)."""


def test_per_company_stub_counts_sum_to_the_corpus_count(conn_with_postings):
    """Counted through a different path than the corpus number, per CLAUDE.md."""
    conn = conn_with_postings  # 2 companies; company A has 2 stubs, company B has 1
    per_company = count_stub_postings_by_company(conn)
    assert sum(per_company.values()) == count_stub_postings(conn)


def test_a_company_with_no_stubs_reports_zero_not_absent(conn_with_postings):
    """It is instrumented, so 0 is honest. Absence would read as 'not measured'."""
    per_company = count_stub_postings_by_company(conn_with_postings)
    assert per_company[COMPANY_WITH_NO_STUBS] == 0


def test_a_whitespace_only_body_counts_as_a_stub_not_just_an_empty_string(conn):
    """SQLite's one-arg trim strips spaces ONLY; tabs and newlines must be in the strip set."""
    insert_posting(conn, body_text="\t\n  ")
    assert sum(count_stub_postings_by_company(conn).values()) == 1
```

`tests/unit/test_run_funnel_queries.py` is the module that already tests `count_stub_postings`
— put these tests there instead of a new file, and reuse its store fixtures and constants. Drop
`tests/unit/test_stub_attribution.py` from the file list if that module's fixtures fit, which
they should; a second fixture set for the same table is how the two drift apart.

- [ ] **Step 2: Run it to verify it fails**

Expected: `ImportError: cannot import name 'count_stub_postings_by_company'`

- [ ] **Step 3: Implement**

```python
def count_stub_postings_by_company(conn: Connection) -> dict[int, int]:
    """Open stub postings per company — the per-source numerator (spec §4.4).

    Sources ARE company_id in this schema (see SourceOutcome's docstring), so a per-company
    count is a per-source count. Every company with an open posting appears, at 0 if it has
    no stubs: this counter is instrumented, so 0 is a measurement, and an absent key would
    read as "not measured" — the distinction D-022/D-023 record as nearly having cost
    job-apps a working adapter.

    The two-arg `trim` names the strip set explicitly, exactly as `count_stub_postings`
    does: SQLite's one-arg `trim` removes spaces ONLY, so a body of tabs or newlines would
    otherwise pass as non-empty.
    """
    rows = conn.execute(
        select(
            postings.c.company_id,
            func.sum(
                case((func.trim(postings.c.body_text, " \t\n\r\f\v") == "", 1), else_=0)
            ),
        )
        .where(postings.c.status == "open")
        .group_by(postings.c.company_id)
    ).all()
    return {int(company_id): int(stubs or 0) for company_id, stubs in rows}
```

Then add `stubs: int` to `SourceOutcome` and populate it in the function that builds
`SourceOutcome` rows, joining on `company_id`. Extend `SourceOutcome`'s docstring with one
sentence: `stubs` is instrumented and reports 0, unlike `assisted`, which reports `None`
because no mechanism could count one.

- [ ] **Step 4: Run the funnel tests, not just the new file**

Run: `./.venv/bin/python -m pytest tests/unit/test_stub_attribution.py tests/unit/test_run_funnel_queries.py --no-cov -n 0 -q`
Expected: all pass. A new required field on `SourceOutcome` breaks every constructor call —
find them with `grep -rn "SourceOutcome(" src tests` and fix each.

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/store/run_funnel_queries.py tests/unit/test_stub_attribution.py
git commit -m "Attribute stub postings per source"
```

---

## Task 5: The per-run new-company cap

**Owner ruling (D-278):** adding a company's whole board IS breadth, so it is permitted only under
an explicit per-run cap, with every addition reported. Unbounded, one Simplify pull adds 5,695
companies.

**Files:**
- Create: `src/boardwatch/lanes/admission.py`
- Test: `tests/unit/test_lane_admission.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CompanyBudget(limit: int)` with `.admit(company_name: str) -> bool`,
  `.admitted -> tuple[str, ...]`, `.refused -> tuple[str, ...]`, and
  `DEFAULT_NEW_COMPANIES_PER_RUN: int`.

**Open decision this task must record, not decide silently:** `companies.source` is constrained to
`('registry','user')`. A lane-discovered company is neither — it was not shipped in the registry and
the user did not type it. Use `'registry'` (it is program-discovered) and record the choice in
`DECISIONS.md`; the alternative is a migration adding a third value, which is a schema change and
therefore the owner's call.

- [ ] **Step 1: Write the failing test**

```python
"""The per-run new-company cap (JD-acquisition spec §4.6, owner ruling in D-278)."""

import pytest

from boardwatch.lanes.admission import DEFAULT_NEW_COMPANIES_PER_RUN, CompanyBudget


def test_the_default_cap_is_ten_per_run():
    assert DEFAULT_NEW_COMPANIES_PER_RUN == 10


def test_the_cap_admits_up_to_its_limit_and_refuses_the_rest():
    budget = CompanyBudget(limit=2)
    assert [budget.admit(name) for name in ("a", "b", "c", "d")] == [True, True, False, False]


def test_every_refusal_is_named_not_merely_counted():
    """A silently dropped company is indistinguishable from one never seen."""
    budget = CompanyBudget(limit=1)
    for name in ("kept", "dropped_1", "dropped_2"):
        budget.admit(name)
    assert budget.admitted == ("kept",)
    assert budget.refused == ("dropped_1", "dropped_2")


def test_readmitting_the_same_company_does_not_consume_budget_twice():
    """Two postings from one new employer are one company, not two."""
    budget = CompanyBudget(limit=1)
    assert budget.admit("acme") is True
    assert budget.admit("acme") is True
    assert budget.admitted == ("acme",)


def test_a_zero_cap_admits_nothing_and_is_not_an_error():
    """The off switch. A lane with a zero budget still reports what it would have added."""
    budget = CompanyBudget(limit=0)
    assert budget.admit("acme") is False
    assert budget.refused == ("acme",)


def test_a_negative_cap_is_rejected_at_construction():
    with pytest.raises(ValueError):
        CompanyBudget(limit=-1)
```

- [ ] **Step 2: Run it to verify it fails**

Expected: `ModuleNotFoundError: No module named 'boardwatch.lanes.admission'`

- [ ] **Step 3: Implement**

```python
"""The per-run cap on companies a lane may add (JD-acquisition spec §4.6).

Owner ruling (D-278): adding a company's whole board IS breadth, and breadth is last. So a
lane may add companies only under an explicit per-run cap, and every addition is reported.
Unbounded, one Simplify pull adds 5,695 companies; the largest single non-six company in
those lists is a UK grocer with 1,639 postings that the US-only gate discards anyway.

Refusals are NAMED, not merely counted. A company dropped silently is indistinguishable
from one the lane never saw, and the difference is the whole diagnostic value.
"""

from __future__ import annotations

DEFAULT_NEW_COMPANIES_PER_RUN = 10


class CompanyBudget:
    """Admits at most `limit` distinct new companies, recording both sides."""

    def __init__(self, limit: int) -> None:
        if limit < 0:
            raise ValueError(f"company budget cannot be negative: {limit}")
        self._limit = limit
        self._admitted: list[str] = []
        self._refused: list[str] = []

    def admit(self, company_name: str) -> bool:
        if company_name in self._admitted:
            # Already paid for. Two postings from one employer are one company.
            return True
        if len(self._admitted) >= self._limit:
            self._refused.append(company_name)
            return False
        self._admitted.append(company_name)
        return True

    @property
    def admitted(self) -> tuple[str, ...]:
        return tuple(self._admitted)

    @property
    def refused(self) -> tuple[str, ...]:
        return tuple(self._refused)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `./.venv/bin/python -m pytest tests/unit/test_lane_admission.py --no-cov -n 0 -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/boardwatch/lanes/admission.py tests/unit/test_lane_admission.py
git commit -m "Cap the companies a lane may add in one run"
```

---

## Task 6: Gate the whole phase

- [ ] **Step 1: Stage everything.** The generalization checker scans TRACKED files only, so an
  unstaged new file is invisible to it and passes vacuously.

```bash
git add -- src/boardwatch/lanes tests/unit/test_lane_outcomes.py tests/unit/test_lane_snapshot.py \
  tests/unit/test_lane_admission.py tests/unit/test_stub_attribution.py \
  tests/pipeline/test_lane_apply.py src/boardwatch/store/run_funnel_queries.py
```

- [ ] **Step 2: Run the only gate, detached, with a sentinel.**

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/Library/TeX/texbin:$PATH"
nohup sh -c 'cd <worktree> && make check > /tmp/check.log 2>&1; echo $? > /tmp/check.done' &
```

Gate on `/tmp/check.done` containing `0`. Never on the launcher's own exit code — the launcher
returns immediately and its 0 says nothing about the gate.

- [ ] **Step 3: Open the PR.** Never push to `main` directly; it permits a silent admin bypass.
  No AI attribution anywhere in the commits, branch name, or PR body.

---

## Not in this plan, and why

**The Indeed client itself.** The spec rules Indeed first because `description { html }` is a field
of its GraphQL search query, so the body costs zero extra requests. Writing that client needs the
exact GraphQL document, the endpoint, and the required headers. A previous session verified those
against the live endpoint; this plan's author did not. Transcribing a request contract from a
summary would put fiction into a no-placeholder plan, so the client gets its own plan whose first
step is a single probe that pins the document, the headers and one recorded response as a fixture.
Everything phase 1 builds is what that client then plugs into.

**JobSpy as the client library.** `python-jobspy` 1.1.82 pins `NUMPY==1.26.3`, whose newest wheel
is `cp312`. boardwatch is `requires-python = ">=3.11"` and CI tests 3.13, and the dev venv is
3.13.12 — so the library cannot install on a supported interpreter, and adding it would break the
published package for 3.13 users. It also fetches through its own `requests`/`tls-client` stack,
which the per-host politeness lock cannot reach, and the spec itself notes its per-posting
description fetches sit outside even its own throttle. Assumption recorded: call Indeed with the
`httpx` client and `Fetcher` boardwatch already ships. This reverses the spec's "via JobSpy"
phrasing while keeping every ruling it rests on — the body is still free in the search response.

**Spec §4.5's four quality controls** — the two-sided login-wall test, boundary extraction,
`role_body_mismatch()`, and the write-back assertion. Every one of them operates on a fetched
body, so all four belong to the client plan, not here. They are not optional there: §4.5 is
labelled "the good part" of the prior art for a reason.

**Spec §4.7's browser UA.** `Fetcher.__init__` sets the honest UA in its constructor
(`core/politeness.py:69`) and accepts an injected `httpx.Client`, so the aggregator exception is
a second `Fetcher` built with a browser-UA client — no change to the six providers, which is
what the ruling requires. Note the consequence to design around: per-host pacing state
(`_last_request_at`) lives per `Fetcher`, so two instances do not share a delay for the same
host. Harmless while the aggregator hosts are disjoint from the ATS hosts; it stops being
harmless the moment they overlap.

**The stub bucket's drain.** Spec §4.5 requires a boardwatch stub bucket to ship with its drain,
running on both sides of the gate, and cites job-apps' 2,201 quarantined folders — 1,462 of which
now have a full body and can never re-enter — as what happens otherwise. Phase 1 adds stub
*attribution* only; nothing is quarantined yet, so there is nothing to drain. The first lane that
quarantines a posting owes the drain in the same change.

**hiring.cafe and the GitHub lists.** Lanes 2 and 3. Order is settled (D-278); nothing about them
changes phase 1.

**Oracle Cloud HCM and iCIMS as providers.** Owner-gated, open question 1 in the spec.
