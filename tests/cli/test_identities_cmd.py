"""backfill writes identities; verify catches a stale one (design §6.3, §7)."""

from pathlib import Path

from sqlalchemy import update
from typer.testing import CliRunner

from boardwatch.cli.app import app
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
