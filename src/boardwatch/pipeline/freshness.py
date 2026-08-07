"""Freshness, not existence — PROGRAM.md §3.P3 **item 2**.

A `<date>/` output folder existing, and even carrying a `funnel-<run_id>.md`, does not by
itself prove the artifacts inside are from a genuine, finished run of that calendar date. A run
that crashed before `finish_run` ran, a folder retried under a later date's directory, or a
tailor loop that wrote fewer lead folders than the store thinks it did, would all leave a
funnel file behind and still be stale. This module checks the three facts that, together, rule
those cases out — and it checks them independently of each other, not as one combined boolean,
so a caller can say WHICH clause failed.

No new schema. `runs.status`/`started_at`/`finished_at` (D-029) and `count_tailored_artifacts`
(P0 item 1) are both reused as-is. The one new comparison is the folder count: every OTHER
directory entry under `day_dir` is counted from the filesystem and checked against the store's
row count for `run_id` — independent of the in-memory `PipelineSummary` that produced them,
per `CLAUDE.md`'s "count the deliverable through a different path than the one that produced
it," and this is the first place that verification runs against the FILESYSTEM rather than a
second store query (§3.P3 item 6, "filesystem-truth counts").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, select

from boardwatch.store.queries import RUN_FAILED, RUN_OK
from boardwatch.store.run_funnel_queries import count_tailored_artifacts
from boardwatch.store.tables import runs

# The two terminal statuses `finish_run` ever writes. `running` (the column's default) is
# excluded on purpose: `store/queries.py`'s own docstring names that as meaning only "nothing
# ever closed this row" — in flight, killed, or a standalone lane that raised uncaught — and
# none of those three is a real run this artifact can vouch for.
TERMINAL_STATUSES = frozenset({RUN_OK, RUN_FAILED})


@dataclass(frozen=True)
class Freshness:
    """Whether `day_dir`'s artifacts for `run_id` are genuinely from a finished run of that
    calendar date. Every clause is recorded, not just the combined verdict, so `reasons` can
    name which one failed without the caller re-deriving it.
    """

    run_id: int
    date: str
    funnel_present: bool
    status: str | None
    dated_to_folder: bool
    folder_count: int
    artifact_rows: int

    @property
    def reconciles(self) -> bool:
        """The filesystem's lead-folder count against the store's artifact-row count for this
        run_id — the same quantity the funnel's `tailored` cross-check already recounts
        in-memory-vs-store, now recounted filesystem-vs-store."""
        return self.folder_count == self.artifact_rows

    @property
    def fresh(self) -> bool:
        return (
            self.funnel_present
            and self.status in TERMINAL_STATUSES
            and self.dated_to_folder
            and self.reconciles
        )

    @property
    def reasons(self) -> tuple[str, ...]:
        """Every failing clause, named. Empty exactly when `fresh` is True."""
        reasons: list[str] = []
        if not self.funnel_present:
            reasons.append(f"no funnel-{self.run_id}.md in {self.date}/")
        if self.status is None:
            reasons.append(f"run {self.run_id} has no runs row")
        elif self.status not in TERMINAL_STATUSES:
            reasons.append(f"run {self.run_id} status is {self.status!r}, not terminal")
        if self.status is not None and not self.dated_to_folder:
            reasons.append(f"run {self.run_id} was not started AND finished on {self.date}")
        if not self.reconciles:
            reasons.append(
                f"{self.folder_count} lead folder(s) on disk vs {self.artifact_rows} tailored "
                f"artifact row(s) in the store for run {self.run_id}"
            )
        return tuple(reasons)


def check_run_freshness(engine: Engine, run_id: int, day_dir: Path) -> Freshness:
    """Read-only. `day_dir` is the dated output folder (`<out_root>/<date>/`) the run wrote
    into; `date` is taken from `day_dir.name`, the same string `run_pipeline` derived it from.
    """
    date_str = day_dir.name
    funnel_present = (day_dir / f"funnel-{run_id}.md").exists()
    folder_count = sum(1 for p in day_dir.iterdir() if p.is_dir()) if day_dir.is_dir() else 0

    with engine.connect() as conn:
        row = conn.execute(
            select(runs.c.status, runs.c.started_at, runs.c.finished_at).where(
                runs.c.id == run_id
            )
        ).one_or_none()
        artifact_rows = count_tailored_artifacts(conn, run_id).rows

    status = row.status if row is not None else None
    dated_to_folder = (
        row is not None
        and row.started_at is not None
        and row.started_at.date().isoformat() == date_str
        and (row.finished_at is None or row.finished_at.date().isoformat() == date_str)
    )

    return Freshness(
        run_id=run_id,
        date=date_str,
        funnel_present=funnel_present,
        status=status,
        dated_to_folder=dated_to_folder,
        folder_count=folder_count,
        artifact_rows=artifact_rows,
    )


__all__ = ["TERMINAL_STATUSES", "Freshness", "check_run_freshness"]
