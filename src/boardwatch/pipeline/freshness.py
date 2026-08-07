"""Freshness, not existence — PROGRAM.md §3.P3 **item 2**.

A `<date>/` output folder existing, and even carrying a `funnel-<run_id>.md`, does not by
itself prove the artifacts inside are from a genuine, finished run of that calendar date. A run
that crashed before `finish_run` ran, a folder retried under a later date's directory, or a
tailor loop that wrote fewer lead folders than the store thinks it did, would all leave a
funnel file behind and still be stale. This module checks the three facts that, together, rule
those cases out — and it checks them independently of each other, not as one combined boolean,
so a caller can say WHICH clause failed.

No new schema. `runs.status`/`started_at`/`finished_at` (D-029) and `count_tailored_artifacts`
(P0 item 1) are both reused as-is. The one new comparison is the folder count — and it MUST be
scoped to this run_id's own artifact rows, never to "every directory under `day_dir`": two
`boardwatch run`s on the same calendar date is a legitimate case (it is WHY every artifact is
suffixed by run_id), and counting every subdirectory in the shared day folder would count the
OTHER run's lead folders too, making both runs read as unreconciled the moment a second run adds
its own. Per run_id's `resume_tailored` artifact ROWS are read from the store, each row's `uri`
(the `.typ` path) is resolved to its parent lead folder, and existence is checked per row — the
same per-run population `count_tailored_artifacts` already counts, verified against the
FILESYSTEM instead of a second store query (§3.P3 item 6, "filesystem-truth counts"; CLAUDE.md:
"count the deliverable through a different path than the one that produced it").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, select

from boardwatch.store.queries import RUN_FAILED, RUN_OK
from boardwatch.store.run_funnel_queries import TAILORED_KIND, count_tailored_artifacts
from boardwatch.store.tables import artifacts, runs

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
    # Both counted over THIS run_id's own `resume_tailored` rows only — never over every
    # subdirectory in the shared day folder, which would also count a second same-day run's
    # leads and make both runs read as unreconciled the moment either one adds folders.
    folder_count: int
    artifact_rows: int

    @property
    def reconciles(self) -> bool:
        """Every one of THIS run_id's `resume_tailored` rows resolves (via its `uri`'s parent)
        to a lead folder that actually exists on disk — the same per-run population the
        funnel's `tailored` cross-check already recounts in-memory-vs-store, now recounted
        filesystem-vs-store, and scoped to run_id exactly as that cross-check is."""
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


def _existing_lead_folders(conn: Connection, run_id: int) -> int:
    """How many of run_id's OWN `resume_tailored` artifact rows resolve to a lead folder that
    actually exists on disk. `uri` stores the `.typ` path (`run_funnel_queries.py`'s own
    docstring); its parent directory is the `<slug>/` folder the tailor loop created. Checked
    per row, not deduplicated into a folder set first, so a row whose folder went missing is
    caught even if another row for the same run happens to share a folder.
    """
    uris = conn.execute(
        select(artifacts.c.uri).where(
            artifacts.c.run_id == run_id, artifacts.c.kind == TAILORED_KIND
        )
    ).scalars().all()
    return sum(1 for uri in uris if Path(str(uri)).parent.is_dir())


def check_run_freshness(engine: Engine, run_id: int, day_dir: Path) -> Freshness:
    """Read-only. `day_dir` is the dated output folder (`<out_root>/<date>/`) the run wrote
    into; `date` is taken from `day_dir.name`, the same string `run_pipeline` derived it from.
    """
    date_str = day_dir.name
    funnel_present = (day_dir / f"funnel-{run_id}.md").exists()

    with engine.connect() as conn:
        row = conn.execute(
            select(runs.c.status, runs.c.started_at, runs.c.finished_at).where(
                runs.c.id == run_id
            )
        ).one_or_none()
        artifact_rows = count_tailored_artifacts(conn, run_id).rows
        folder_count = _existing_lead_folders(conn, run_id)

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
