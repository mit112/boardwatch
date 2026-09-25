"""`python -m tools.workday_locations_backfill` (T250): re-run the Workday adapter over each stored
posting's own `raw_json`, dry-run by default.

Rows are seeded through `apply_board` with the locations the adapter stored BEFORE T250 (the
primary location only), beside the very detail it parsed them from — the state every Workday
posting already in the store is in, and which the known-id skip means no scan will ever repair.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, insert, select, update

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.posting_identity import compute_identities
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.identity_queries import load_identities, load_identity_inputs
from boardwatch.store.queries import insert_run
from tools.workday_locations_backfill import main

SLUG = "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"


def _detail(location: str, country: str | None, additional: list[str] | None) -> dict[str, Any]:
    info: dict[str, Any] = {"title": "Engineer", "location": location, "jobDescription": "x"}
    if country is not None:
        info["country"] = {"descriptor": country, "id": "0" * 32}
    if additional is not None:
        info["additionalLocations"] = additional
    return {"jobPostingInfo": info}


def _pre_t250(
    pid: str, location: str, country: str | None, additional: list[str] | None = None
) -> RawPosting:
    listed = {"title": "Engineer", "externalPath": f"/job/X/Engineer_{pid}",
              "locationsText": "2 Locations"}
    return RawPosting(
        provider_posting_id=pid, title="Engineer", url=f"https://h/{pid}",
        locations=[location], body_text=f"body {pid}",
        raw_json={"listed": listed, "detail": _detail(location, country, additional)},
    )


def _company(engine: Engine, provider: str, slug: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name=slug, provider=provider, slug=slug, source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )


@pytest.fixture()
def store(tmp_path: Path) -> Engine:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    workday = _company(engine, "workday", SLUG)
    apply_board(
        engine,
        BoardSnapshot(
            status="complete", url="u", postings=[
                _pre_t250("R1", "ACM IV", "Romania", ["Cluj, Romania"]),  # unknown -> non_us
                _pre_t250("R2", "ACM HQ", "United States of America"),  # unknown -> us
                _pre_t250("R3", "Reynosa, Mexico", "United States of America"),  # text decides
                _pre_t250("R4", "ACM IV", None),                         # nothing to add
                _pre_t250("R5", "ACM IV", "Romania"),                    # closed below
            ],
        ),
        workday,
        insert_run(engine),
    )
    # A closed Workday posting that reopens is re-listed, never re-parsed, so the backfill is
    # the only thing that will ever bring its row and its identities into line.
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.provider_posting_id == "R5")
            .values(status="closed")
        )
    # A non-Workday row with the same office-code shape must never be touched.
    greenhouse = _company(engine, "greenhouse", "acme")
    apply_board(
        engine,
        BoardSnapshot(status="complete", url="u", postings=[_pre_t250("G1", "ACM IV", "Romania")]),
        greenhouse,
        insert_run(engine),
    )
    return engine


def _locations(engine: Engine) -> dict[str, list[str]]:
    with engine.connect() as conn:
        return {
            str(r.provider_posting_id): list(r.locations_json)
            for r in conn.execute(
                select(tables.postings.c.provider_posting_id, tables.postings.c.locations_json)
            )
        }


BEFORE = {
    "R1": ["ACM IV"], "R2": ["ACM HQ"], "R3": ["Reynosa, Mexico"], "R4": ["ACM IV"],
    "R5": ["ACM IV"], "G1": ["ACM IV"],
}


def test_the_dry_run_reports_transitions_and_writes_nothing(
    store: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "workday postings: 5 · no stored detail: 0 · unparseable: 0 · locations changed: 3" in out
    assert "closed  unknown -> non_us: 1" in out
    assert "open    unknown -> non_us: 1" in out
    assert "open    unknown -> us: 1" in out
    assert "dry run: nothing written" in out
    assert _locations(store) == BEFORE


def test_apply_rewrites_locations_and_identities_and_is_idempotent(
    store: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--data-dir", str(tmp_path), "--apply"]) == 0
    assert "applied: 3 postings" in capsys.readouterr().out
    assert _locations(store) == {
        **BEFORE,
        "R1": ["ACM IV, Romania", "Cluj, Romania"],
        "R2": ["ACM HQ, United States of America"],
        "R5": ["ACM IV, Romania"],
    }
    # Verified through a different path than the writer: identities recomputed from the rows
    # as they now stand must equal what is stored, or dedup keys on a location no row holds.
    with store.connect() as conn:
        stored = load_identities(conn)
        for inputs in load_identity_inputs(conn, open_only=False):
            assert set(stored[inputs.posting_id]) == set(compute_identities(inputs))
    assert main(["--data-dir", str(tmp_path)]) == 0
    assert "locations changed: 0" in capsys.readouterr().out


def test_a_missing_store_is_exit_2(tmp_path: Path) -> None:
    assert main(["--data-dir", str(tmp_path / "absent")]) == 2
    assert main(["--data-dir", str(tmp_path / "absent"), "--apply"]) == 2
    assert not (tmp_path / "absent").exists()
