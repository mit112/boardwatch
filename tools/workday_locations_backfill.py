"""One-time backfill: recompute stored Workday postings' `locations_json` from their stored
`raw_json`, through the adapter's own `parse_posting` (T250).

`parse_posting` now appends a detail's `country` to an office-code primary location and adds
`additionalLocations`. That fix reaches only postings whose detail is fetched after it lands:
details are fetched for UNSEEN postings only, and a known posting is re-listed without being
re-parsed, so every row already in the store keeps the location it was first stored with. The
detail each of them was parsed from is still in `raw_json`, so this re-runs the same function
over it instead of re-fetching anything.

Dry-run by DEFAULT: the store is opened read-only and the tool prints, per posting status, how
many rows move from each location class to each other one. `--apply` writes, in ONE
transaction, `locations_json` and the posting's identities for every changed row — identities
key on locations, and the scan path writes the two together for the same reason. Run `--apply`
only while no pipeline run is in flight.

The classes printed are `classify_location`'s, the US reading the run funnel reports; what the
new locations MEAN for a tenant is still decided by its own target countries at rank time.

    python -m tools.workday_locations_backfill [--data-dir DIR] [--apply]

Exit codes: 0 done, 2 the store could not be read.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.posting_identity import compute_identities
from boardwatch.core.settings import load_settings
from boardwatch.providers.workday import parse_posting, split_target
from boardwatch.rank.location_gate import LocationClass, classify_location
from boardwatch.store.db import (
    DB_FILENAME,
    get_engine,
    get_readonly_engine,
    write_connection,
)
from boardwatch.store.identity_queries import load_identity_inputs, write_identities
from boardwatch.store.tables import companies, postings


@dataclass(frozen=True)
class Change:
    posting_id: int
    status: str
    old: list[str]
    new: list[str]


@dataclass
class Plan:
    scanned: int = 0
    no_detail: int = 0
    unparseable: int = 0
    changes: tuple[Change, ...] = ()

    def transitions(self) -> Counter[tuple[str, LocationClass, LocationClass]]:
        return Counter(
            (c.status, classify_location(c.old), classify_location(c.new)) for c in self.changes
        )


def plan(conn: Connection) -> Plan:
    """Every stored Workday posting whose recomputed locations differ from its stored ones.

    A row whose `raw_json` holds no `listed` + `detail` pair is not the adapter's record (a lane
    can write one under a Workday company) and has nothing to recompute from, so it is counted
    and left alone. So is one `parse_posting` refuses, which it does only on a missing path or
    title — neither of which the scan could have stored.
    """
    result = Plan()
    changes: list[Change] = []
    rows = conn.execute(
        select(
            postings.c.id, postings.c.status, postings.c.locations_json, postings.c.raw_json,
            companies.c.slug,
        )
        .join(companies, postings.c.company_id == companies.c.id)
        .where(companies.c.provider == "workday")
        .order_by(postings.c.id)
    )
    for row in rows:
        result.scanned += 1
        raw: Any = row.raw_json
        listed = raw.get("listed") if isinstance(raw, dict) else None
        detail = raw.get("detail") if isinstance(raw, dict) else None
        if not isinstance(listed, dict) or not isinstance(detail, dict):
            result.no_detail += 1
            continue
        try:
            host, _tenant, site, _facet = split_target(str(row.slug))
            new = parse_posting(host, site, listed, detail).locations
        except ValueError:
            result.unparseable += 1
            continue
        old = list(row.locations_json) if isinstance(row.locations_json, list) else []
        if new != old:
            changes.append(Change(int(row.id), str(row.status), old, new))
    result.changes = tuple(changes)
    return result


def apply(conn: Connection, changes: Sequence[Change]) -> int:
    """Write each change's locations and rewrite its identities; returns identity rows written."""
    now = utcnow()
    for change in changes:
        conn.execute(
            update(postings)
            .where(postings.c.id == change.posting_id)
            .values(locations_json=change.new)
        )
    written = 0
    # Closed rows too: a Workday posting that reopens is re-listed, not re-parsed, so nothing
    # else would ever bring its identities back in line with the row.
    for inputs in load_identity_inputs(
        conn, [c.posting_id for c in changes], open_only=False
    ):
        written += write_identities(conn, inputs.posting_id, compute_identities(inputs), now=now)
    return written


def report(result: Plan) -> str:
    lines = [
        f"workday postings: {result.scanned:,} · no stored detail: {result.no_detail:,} · "
        f"unparseable: {result.unparseable:,} · locations changed: {len(result.changes):,}",
        "status  old -> new: count",
    ]
    for (status, old, new), count in sorted(result.transitions().items()):
        lines.append(f"{status:<7} {old} -> {new}: {count:,}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.workday_locations_backfill")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--apply", action="store_true", help="Write the changes. Without it nothing is written."
    )
    args = parser.parse_args(argv)
    data_dir: Path = args.data_dir or load_settings().data_dir
    if not args.apply:
        try:
            engine = get_readonly_engine(data_dir)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 2
        with engine.connect() as conn:
            print(report(plan(conn)))
        print("dry run: nothing written (pass --apply to write)")
        return 0
    if not (data_dir / DB_FILENAME).is_file():
        print(f"no store at {data_dir}", file=sys.stderr)
        return 2
    with write_connection(get_engine(data_dir)) as conn, conn.begin():
        result = plan(conn)
        written = apply(conn, result.changes)
    print(report(result))
    print(f"applied: {len(result.changes):,} postings, {written:,} identity rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
