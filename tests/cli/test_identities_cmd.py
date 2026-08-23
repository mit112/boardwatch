"""backfill writes identities; verify catches a stale one (design §6.3, §7)."""

import json
from pathlib import Path

from sqlalchemy import update
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.regroup import job_anchors
from boardwatch.store.tables import postings


def _run(data_dir: Path, args: list[str]):
    """Invocation shape copied from tests/unit/test_top_accounting.py::_cli."""
    return CliRunner().invoke(app, ["--data-dir", str(data_dir), *args])


def test_backfill_then_verify_is_clean(seed_dedup):
    seed = seed_dedup(count=2)
    assert _run(seed.data_dir, ["identities", "backfill"]).exit_code == 0
    assert _run(seed.data_dir, ["identities", "verify"]).exit_code == 0


def test_verify_fails_when_a_posting_is_revised_without_recomputing_its_identity(seed_dedup):
    """The realistic staleness failure, and the one Path A structurally cannot see.

    Path A reads stored identity rows. Path B recomputes from postings. Mutating the title
    without recomputing makes them disagree — which is exactly what makes this a second
    path under D-028 rather than the same query grouped differently.
    """
    seed = seed_dedup(count=2)
    assert _run(seed.data_dir, ["identities", "backfill"]).exit_code == 0
    with seed.engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == seed.posting_ids[0])
            .values(
                title="Completely Different Title",
                normalized_title="completely different title",
            )
        )
    result = _run(seed.data_dir, ["identities", "verify"])
    assert result.exit_code != 0
    assert "stale" in result.output.lower()


def test_leakage_with_no_dispositions_is_not_measurable(seed_dedup):
    seed = seed_dedup(count=2)
    assert _run(seed.data_dir, ["identities", "backfill"]).exit_code == 0
    # A wide window: `seed_dedup`'s fixed P6_NOW is far in the past relative to wall-clock
    # `utcnow()`, which is what the CLI (unlike the pure-core tests) actually uses.
    result = _run(seed.data_dir, ["identities", "leakage", "--days", "36500"])
    assert result.exit_code == 0
    assert "not measurable" in result.output.lower()


def test_leakage_json_reports_the_collision_rate(seed_dedup):
    """End-to-end wiring check: two exact_quad duplicates, each surfaced under its own job,
    come back as a 50% leakage rate through the real CLI, not just through the pure core."""
    seed = seed_dedup(count=2, identical=True)
    assert _run(seed.data_dir, ["identities", "backfill"]).exit_code == 0
    with seed.engine.connect() as conn:
        anchors = job_anchors(conn, seed.posting_ids)
    with seed.engine.begin() as conn:
        for job_id in anchors.values():
            record_disposition(
                conn, job_id, disposition="built", reason="lead_built",
                policy_version="p1", now=seed.now,
            )
    result = _run(seed.data_dir, ["identities", "leakage", "--json", "--days", "36500"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["identified"] == 2
    assert payload["distinct_groups"] == 1
    assert payload["redundant"] == 1
    assert payload["rate"] == 0.5
