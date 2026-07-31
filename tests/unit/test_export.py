"""export is data portability plus the eligibility identity (A6).

A6 narrowed the contract: this is a FLAT SNAPSHOT carrying the evaluation identity, not
full audit portability. Every row carries the posting, the funnel state, and the
(profile_hash, rules_hash, verdict) triple it was computed under. Only data reaches
stdout: preflight chatter goes to stderr (A3), so `boardwatch export --format jsonl | jq`
stays clean. Selection is open postings plus every tracked posting, closed or not (A6.1).
"""

import csv
import io
import json
from pathlib import Path

import pytest
from sqlalchemy import insert, update
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.reports.export import CSV_COLUMNS
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.events import append_event
from boardwatch.store.queries import insert_run
from boardwatch.store.tables import companies, jobs, posting_versions, postings

runner = CliRunner()

# The company slug must NOT collide with seeded_events' (greenhouse, acme): `init`
# upserts greenhouse:acme-p5, then the fixture's plain INSERT of greenhouse:acme is a
# different row, so the two can coexist (the plan's "acme" collided and the seed
# crashed with an IntegrityError; same fix as test_top_new.py).
PROFILE_INPUT = "3\nacme-p5\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def _json_rows(data_dir: Path) -> list[dict]:
    result = _run(data_dir, ["export", "--format", "jsonl"])
    assert result.exit_code == 0, result.stdout + result.stderr
    return [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Plan tests (9): the stdout contract and the funnel status join.
# ---------------------------------------------------------------------------


def test_empty_is_still_a_valid_jsonl_document(env: Path) -> None:
    result = _run(env, ["export", "--format", "jsonl"])
    assert result.exit_code == 0
    assert not [ln for ln in result.stdout.splitlines() if ln.strip()]


def test_csv_empty_is_still_a_header_row(env: Path) -> None:
    result = _run(env, ["export", "--format", "csv"])
    assert result.exit_code == 0
    assert result.stdout == ",".join(CSV_COLUMNS) + "\n"


def test_jsonl_to_stdout(env: Path, seeded_events) -> None:
    seeded_events(env)
    rows = _json_rows(env)
    assert len(rows) >= 4  # alpha, beta, gamma, delta are open; epsilon/zeta closed
    for row in rows:
        assert "posting_id" in row
        assert "title" in row


def test_csv_to_stdout(env: Path, seeded_events) -> None:
    seeded_events(env)
    result = _run(env, ["export", "--format", "csv"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert len(lines) >= 2  # header plus at least one data row


def test_jsonl_to_a_file(env: Path, tmp_path: Path, seeded_events) -> None:
    seeded_events(env)
    out = tmp_path / "dump.jsonl"
    result = _run(env, ["export", "--format", "jsonl", "--out", str(out)])
    assert result.exit_code == 0
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8").splitlines()[0])["posting_id"]
    assert "{" not in result.stdout  # data goes to the file, not stdout


def test_export_carries_the_funnel_status(env: Path, seeded_events) -> None:
    alpha = seeded_events(env).posting_ids["alpha"]
    assert _run(env, ["track", "add", str(alpha), "--status", "applied"]).exit_code == 0
    rows = _json_rows(env)
    tracked = [r for r in rows if r["posting_id"] == alpha]
    assert tracked[0]["application_status"] == "applied"


def test_untracked_postings_have_a_null_funnel_status(env: Path, seeded_events) -> None:
    seeded_events(env)
    rows = _json_rows(env)
    assert any(r["application_status"] is None for r in rows)


def test_export_carries_the_eligibility_identity_when_a_profile_exists(
    env: Path, seeded_events
) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    rows = _json_rows(env)
    assert rows
    assert all("eligibility_verdict" in r for r in rows)
    assert all("rules_hash" in r for r in rows)
    assert all("profile_hash" in r for r in rows)


def test_an_unknown_format_is_rejected(env: Path) -> None:
    result = _run(env, ["export", "--format", "xml"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# A3 (2): stdout must carry ONLY data while the preflight chatter goes to stderr.
# ---------------------------------------------------------------------------


def test_jsonl_stdout_is_clean_when_evaluations_are_pending(env: Path, seeded_events) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    result = _run(env, ["export", "--format", "jsonl"])
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert lines  # four open postings are evaluated and exported
    for line in lines:
        json.loads(line)  # preflight chatter on stdout would make this raise
    assert "evaluating" not in result.stdout


def test_csv_stdout_starts_with_exact_header(env: Path, seeded_events) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    result = _run(env, ["export", "--format", "csv"])
    assert result.exit_code == 0
    assert result.stdout.splitlines()[0] == ",".join(CSV_COLUMNS)


# ---------------------------------------------------------------------------
# A6 (5): the predicate, the identity strength, and the CSV quoting contract.
# ---------------------------------------------------------------------------


def test_export_includes_closed_tracked_posting(env: Path, seeded_events) -> None:
    """A6.1 positive control: a tracked posting stays in the export after it closes."""
    epsilon = seeded_events(env).posting_ids["epsilon"]  # epsilon is seeded closed
    assert _run(env, ["track", "add", str(epsilon)]).exit_code == 0
    rows = _json_rows(env)
    assert any(r["posting_id"] == epsilon for r in rows)


def test_hashes_and_verdicts_are_non_null_with_profile(env: Path, seeded_events) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    rows = _json_rows(env)
    assert rows
    for row in rows:
        assert row["profile_hash"] is not None
        assert row["rules_hash"] is not None
    open_rows = [r for r in rows if r["status"] == "open"]
    assert open_rows
    for row in open_rows:
        assert row["eligibility_verdict"] is not None


def test_csv_data_row_includes_quoted_field(env: Path, seeded_events) -> None:
    seed = seeded_events(env)
    with get_engine(env).begin() as conn:
        conn.execute(update(companies).values(name="Acme, Inc."))
    assert seed.posting_ids["alpha"]
    result = _run(env, ["export", "--format", "csv"])
    assert result.exit_code == 0
    reader = csv.reader(io.StringIO(result.stdout))
    header = next(reader)
    assert tuple(header) == CSV_COLUMNS
    company_idx = CSV_COLUMNS.index("company")
    data_rows = [r for r in reader if r]
    assert data_rows
    assert any(r[company_idx] == "Acme, Inc." for r in data_rows)
    assert '"Acme, Inc."' in result.stdout  # the comma forces CSV quoting


def test_multi_attempt_funnel_shows_highest_attempt(env: Path, seeded_events) -> None:
    alpha = seeded_events(env).posting_ids["alpha"]
    assert _run(env, ["track", "add", str(alpha)]).exit_code == 0
    assert _run(env, ["track", "add", str(alpha), "--new-attempt"]).exit_code == 0
    rows = _json_rows(env)
    alpha_rows = [r for r in rows if r["posting_id"] == alpha]
    assert alpha_rows
    assert alpha_rows[0]["application_attempt"] == 2  # highest attempt wins the row


def _seed_grouped_job(data_dir: Path) -> tuple[int, int]:
    """One job anchoring two postings: A open (min id), B closed (tracked, non-min)."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    run_id = insert_run(engine)
    a_id: int | None = None
    b_id: int | None = None
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme G", provider="greenhouse", slug="acme-g",
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        for title, status in (("A Role", "open"), ("B Role", "closed")):
            posting_id = int(
                conn.execute(
                    insert(postings).values(
                        company_id=company_id, job_id=job_id,
                        provider_posting_id=f"gp-{title[0].lower()}", title=title,
                        normalized_title=title.lower(), url=f"https://example.test/{title.lower()}",
                        locations_json=["Remote"], remote_policy="remote",
                        first_seen_at=now, last_seen_at=now,
                        status=status, closed_at=now if status == "closed" else None,
                        consecutive_missing=0, content_hash=f"gh-{title.lower()}",
                        body_text=f"We are hiring a {title}.",
                    )
                ).inserted_primary_key[0]
            )
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id, content_hash=f"gh-{title.lower()}",
                    body_text=f"We are hiring a {title}.", captured_at=now,
                    capture_reason="new",
                )
            )
            append_event(conn, posting_id, "new", run_id)
            if title == "A Role":
                a_id = posting_id
            else:
                b_id = posting_id
    assert a_id is not None and b_id is not None and a_id < b_id
    return a_id, b_id


def test_grouped_job_shows_correct_tracked_posting(env: Path) -> None:
    """A6: one job, two postings; the tracked NON-minimum posting is the one exported.

    B is closed, so only the open-or-tracked predicate (A6.1) keeps it in the export;
    a min-per-job projection would show only A.
    """
    a_id, b_id = _seed_grouped_job(env)
    assert _run(env, ["track", "add", str(b_id), "--status", "applied"]).exit_code == 0
    rows = _json_rows(env)
    b_rows = [r for r in rows if r["posting_id"] == b_id]
    assert b_rows  # the tracked posting appears even though it is closed
    assert b_rows[0]["application_status"] == "applied"
    assert b_rows[0]["application_id"] is not None
    assert any(r["posting_id"] == a_id for r in rows)  # the open sibling is not lost
