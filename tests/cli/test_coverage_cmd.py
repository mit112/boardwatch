"""`boardwatch coverage` — the read-only report over per-board discovery coverage (D-271).

Fixture-derived from the actual `board_scans` schema (D-271's four coverage columns), not
named after the brief's unverified fixtures — see `tests/unit/test_scan_apply.py` for the
same `get_engine(tmp_path)` + `ensure_schema` setup this file follows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.store.coverage_queries import _resolve_censored
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.tables import board_scans, companies, jobs, postings


def _cli(data_dir: Path, args: list[str]):
    """Invocation shape copied from tests/cli/test_identities_cmd.py::_run."""
    return CliRunner().invoke(app, ["--data-dir", str(data_dir), *args])


def _add_company(engine: Engine, *, provider: str, slug: str, name: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(companies).values(
                name=name, provider=provider, slug=slug, source="user", watched=True,
            )
        )
        return int(result.inserted_primary_key[0])


def _scan_row(
    engine: Engine,
    *,
    run_id: int,
    company_id: int,
    status: str,
    board_reported_total: int | None = None,
    board_enumerated: int | None = None,
    detail_deferred: int | None = None,
    board_total_censored: int | None = None,
) -> None:
    now = utcnow()
    with engine.begin() as conn:
        conn.execute(
            insert(board_scans).values(
                run_id=run_id,
                company_id=company_id,
                started_at=now,
                finished_at=now,
                status=status,
                postings_listed=0,
                board_reported_total=board_reported_total,
                board_enumerated=board_enumerated,
                detail_deferred=detail_deferred,
                board_total_censored=board_total_censored,
            )
        )


def _add_posting(engine: Engine, *, company_id: int, provider_posting_id: str) -> None:
    now = utcnow()
    with engine.begin() as conn:
        # job_id is a real FK, NOT-NULL by trigger (D28) — every posting needs its own job row.
        job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        conn.execute(
            insert(postings).values(
                company_id=company_id,
                job_id=job_id,
                provider_posting_id=provider_posting_id,
                title="Software Engineer",
                normalized_title="software engineer",
                remote_policy="unknown",
                first_seen_at=now,
                last_seen_at=now,
                status="open",
                consecutive_missing=0,
                content_hash=f"h-{provider_posting_id}",
                body_text="body",
            )
        )


@pytest.fixture()
def seeded_coverage_store(tmp_path: Path) -> Path:
    """One watched board per bucket, plus a zero-total measured board and two boards whose
    `board_total_censored` is NULL (the default — nothing sets it) sitting right next to one
    that is explicitly censored, so a bug that treated NULL as `censored=True` would sweep the
    NULL boards into the wrong bucket and be caught immediately.

    lever    -> enumerated_only (no total at all)
    gh_a     -> measured        (500 held of 1,000 stated; NULL board_total_censored)
    gh_b     -> measured        (1 held of a stated 0; NULL board_total_censored)
    workday  -> censored        (board_total_censored=1, explicit)
    smartrec -> dark            (status=failed)
    ashby    -> stale           (status=unchanged)
    """
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    run_id = insert_run(engine)

    lever_id = _add_company(engine, provider="lever", slug="lever-co", name="Lever Co")
    _scan_row(engine, run_id=run_id, company_id=lever_id, status="complete", board_enumerated=3)

    gh_a_id = _add_company(engine, provider="greenhouse", slug="gh-a", name="Greenhouse A")
    _scan_row(
        engine, run_id=run_id, company_id=gh_a_id, status="complete",
        board_reported_total=1000, board_enumerated=1000,
    )
    for i in range(500):
        _add_posting(engine, company_id=gh_a_id, provider_posting_id=f"gh-a-{i}")

    gh_b_id = _add_company(engine, provider="greenhouse", slug="gh-b", name="Greenhouse B")
    _scan_row(
        engine, run_id=run_id, company_id=gh_b_id, status="complete",
        board_reported_total=0, board_enumerated=0,
    )
    _add_posting(engine, company_id=gh_b_id, provider_posting_id="gh-b-0")

    workday_id = _add_company(engine, provider="workday", slug="wd-co", name="Workday Co")
    _scan_row(
        engine, run_id=run_id, company_id=workday_id, status="complete",
        board_reported_total=2500, board_enumerated=2000, board_total_censored=1,
    )

    smartrec_id = _add_company(
        engine, provider="smartrecruiters", slug="sr-co", name="SmartRecruiters Co"
    )
    _scan_row(engine, run_id=run_id, company_id=smartrec_id, status="failed")

    ashby_id = _add_company(engine, provider="ashby", slug="ashby-co", name="Ashby Co")
    _scan_row(engine, run_id=run_id, company_id=ashby_id, status="unchanged")

    return data_dir


def test_coverage_report_prints_every_bucket_even_when_empty(seeded_coverage_store: Path) -> None:
    """A bucket that reads 0 is information. A bucket that is absent is a silent fold."""
    result = _cli(seeded_coverage_store, ["coverage", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["bucket_counts"]) == {
        "measured", "enumerated_only", "censored", "dark", "stale", "unscanned"
    }


def test_coverage_report_states_its_corpus_size_beside_the_ratio(
    seeded_coverage_store: Path,
) -> None:
    """D-268's rule: a ratio records its match rule AND its corpus size."""
    payload = json.loads(_cli(seeded_coverage_store, ["coverage", "--json"]).stdout)
    assert payload["corpus_boards"] == 6
    assert "measured_held" in payload
    assert "measured_total" in payload


def test_enumerated_only_board_has_null_ratio_in_output(seeded_coverage_store: Path) -> None:
    payload = json.loads(_cli(seeded_coverage_store, ["coverage", "--json"]).stdout)
    lever = next(b for b in payload["boards"] if b["provider"] == "lever")
    assert lever["bucket"] == "enumerated_only"
    assert lever["ratio"] is None


def test_measured_zero_total_board_is_excluded_from_the_rollup_but_still_counted(
    seeded_coverage_store: Path,
) -> None:
    """gh_b states a total of 0 and holds 1 posting: a real claim, kept in `measured`, but its
    ratio is undefined and it must not inflate the global roll-up's numerator or denominator."""
    payload = json.loads(_cli(seeded_coverage_store, ["coverage", "--json"]).stdout)
    gh_b = next(b for b in payload["boards"] if b["name"] == "Greenhouse B")
    assert gh_b["bucket"] == "measured"
    assert gh_b["ratio"] is None
    assert gh_b["shortfall"] == -1  # 0 stated - 1 held
    assert payload["measured_zero_total"] == 1
    # gh_a alone: 500 held of 1,000 stated. gh_b's 0/1 must not leak into this.
    assert payload["measured_held"] == 500
    assert payload["measured_total"] == 1000
    assert payload["global_ratio"] == 0.5


def test_censored_board_is_bucketed_censored_with_a_null_ratio(
    seeded_coverage_store: Path,
) -> None:
    payload = json.loads(_cli(seeded_coverage_store, ["coverage", "--json"]).stdout)
    workday = next(b for b in payload["boards"] if b["provider"] == "workday")
    assert workday["bucket"] == "censored"
    assert workday["ratio"] is None


def test_failed_and_unchanged_scans_are_dark_and_stale(seeded_coverage_store: Path) -> None:
    payload = json.loads(_cli(seeded_coverage_store, ["coverage", "--json"]).stdout)
    boards_by_provider = {b["provider"]: b for b in payload["boards"]}
    assert boards_by_provider["smartrecruiters"]["bucket"] == "dark"
    assert boards_by_provider["ashby"]["bucket"] == "stale"
    assert boards_by_provider["smartrecruiters"]["ratio"] is None
    assert boards_by_provider["ashby"]["ratio"] is None


def test_null_board_total_censored_does_not_route_a_measured_board_into_censored(
    seeded_coverage_store: Path,
) -> None:
    """gh_a and gh_b never have `board_total_censored` set (it defaults to NULL — nothing in
    this fixture writes it), yet they sit beside `workday`, whose flag is explicitly `1`. If
    NULL were read as truthy (or misread as "censored" by some other route), both greenhouse
    boards would land in `censored` instead of `measured` and this assertion would catch it.
    """
    payload = json.loads(_cli(seeded_coverage_store, ["coverage", "--json"]).stdout)
    boards_by_name = {b["name"]: b for b in payload["boards"]}
    assert boards_by_name["Greenhouse A"]["bucket"] == "measured"
    assert boards_by_name["Greenhouse B"]["bucket"] == "measured"


def test_resolve_censored_handles_the_three_states_explicitly() -> None:
    """Unit-level pin on the tri-state mapping itself: 0 and NULL both resolve to `False`
    (classify_board's `censored` parameter has no third state to give them), but the mapping
    is an explicit branch over {None, 0, 1} rather than a bare `bool()` coercion — proven here
    by the fact that an out-of-domain value raises instead of silently truthying through."""
    assert _resolve_censored(1) is True
    assert _resolve_censored(0) is False
    assert _resolve_censored(None) is False
    with pytest.raises(ValueError):
        _resolve_censored(2)


def test_coverage_report_table_mode_writes_nothing(seeded_coverage_store: Path) -> None:
    """The plain-table path must be exactly as read-only as --json: run it twice and confirm
    the second run's report is byte-identical, proving `coverage` mutated no state in between."""
    first = _cli(seeded_coverage_store, ["coverage", "--json"]).stdout
    result = _cli(seeded_coverage_store, ["coverage"])
    assert result.exit_code == 0
    second = _cli(seeded_coverage_store, ["coverage", "--json"]).stdout
    assert first == second
    assert json.loads(second)["corpus_boards"] == 6


def test_watched_board_with_no_scan_row_for_the_run_is_unscanned_not_dropped(
    tmp_path: Path,
) -> None:
    """Fix round 1, finding 1. `scan/coordinator.py`'s `run_scan(company=...)` mints a run_id
    containing rows for only the filtered subset — an INNER JOIN on board_scans silently
    dropped every other watched board from the corpus. A board with no board_scans row for the
    selected run must appear as `unscanned` and still be counted in `corpus_boards`."""
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    run_id = insert_run(engine)

    scanned_id = _add_company(engine, provider="lever", slug="scanned-co", name="Scanned Co")
    _scan_row(engine, run_id=run_id, company_id=scanned_id, status="complete", board_enumerated=5)

    # Watched, but this run never touched it (e.g. `scan --company scanned-co` excluded it).
    _add_company(engine, provider="greenhouse", slug="untouched-co", name="Untouched Co")

    payload = json.loads(_cli(data_dir, ["coverage", "--json", "--run", str(run_id)]).stdout)
    assert payload["corpus_boards"] == 2
    untouched = next(b for b in payload["boards"] if b["name"] == "Untouched Co")
    assert untouched["bucket"] == "unscanned"
    assert untouched["ratio"] is None
    assert payload["bucket_counts"]["unscanned"] == 1
    # The scanned board is unaffected by the fix.
    assert next(b for b in payload["boards"] if b["name"] == "Scanned Co")["bucket"] == (
        "enumerated_only"
    )


def test_coverage_against_an_uninitialized_data_dir_fails_cleanly(tmp_path: Path) -> None:
    """Fix round 1, finding 2. `ensure=False` (needed to stay read-only) means a never-`init`'d
    data dir has no tables at all. Must report and exit(1), like doctor's schema-ABSENT path —
    not leak a raw `sqlalchemy.exc.OperationalError` traceback out of the CLI."""
    data_dir = tmp_path / "data"
    result = _cli(data_dir, ["coverage"])
    assert result.exit_code == 1
    assert "OperationalError" not in result.output
    assert "no such table" not in result.output
    assert "schema" in result.output.lower()


def test_coverage_with_an_unknown_run_id_says_so(seeded_coverage_store: Path) -> None:
    """Fix round 1, minor 2: a typo'd --run must not read identically to "zero watched boards
    this run" — the LEFT JOIN fix means a bogus run id would otherwise render every watched
    board as `unscanned` with no indication the run itself does not exist."""
    result = _cli(seeded_coverage_store, ["coverage", "--run", "999999"])
    assert result.exit_code == 1
    assert "999999" in result.output
