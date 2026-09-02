"""The lane-body quarantine AND its drain, in one file because they ship in one change.

The standing rule this file exists to satisfy: *every quarantine needs a drain, designed in the
same change as the quarantine, running on both sides of the gate. A bucket without a scheduled
re-entry path is a leak.* A test that only proved rows go IN would be exactly that leak, so the
two drain tests below are written to FAIL if `drain_quarantine` is never called — each asserts
`reopened_at` is set and that the released body was judged in the SAME pass.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.settings import Settings
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.lanes import quality
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from tests.unit.test_lane_body_precondition import JOBRIGHT_PAGE

CLEAN_BODY = """About the role
We are hiring a backend engineer to build payment services.
Responsibilities
Design and ship APIs used by every internal team.
Requirements
Strong Python. Experience operating production systems.
"""

_T0 = datetime(2026, 1, 1)


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    with eng.begin() as conn:
        conn.execute(
            insert(tables.profile).values(
                id=1, text="Backend engineer", skills_json=["Python"],
                taxonomy_version="v1", target_titles_json=[], exclude_titles_json=[],
                locations_json=[], remote_only=False, updated_at=_T0,
            )
        )
        conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
            )
        )
    return eng


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    return Settings(data_dir=tmp_path / "data", config_dir=cfg)


def _seed(engine: Engine, pid: str, body: str) -> tuple[int, int]:
    """One posting and its first version. Returns (posting_id, posting_version_id)."""
    with engine.begin() as conn:
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=_T0)).inserted_primary_key[0]
        )
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=1, job_id=job_id, provider_posting_id=pid, title="Backend Engineer",
                    normalized_title="backend engineer", url="https://example.test/j",
                    locations_json=["Remote"], remote_policy="remote", first_seen_at=_T0,
                    last_seen_at=_T0, status="open", consecutive_missing=0,
                    content_hash=f"h-{pid}", body_text=body,
                )
            ).inserted_primary_key[0]
        )
        version_id = int(
            conn.execute(
                insert(tables.posting_versions).values(
                    posting_id=posting_id, content_hash=f"h-{pid}", body_text=body,
                    captured_at=_T0, capture_reason="new",
                )
            ).inserted_primary_key[0]
        )
    return posting_id, version_id


def _append_version(engine: Engine, posting_id: int, body: str) -> int:
    """What `scan/apply.py` does when a re-fetch moves the content hash."""
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.posting_versions).values(
                    posting_id=posting_id, content_hash=f"h2-{posting_id}", body_text=body,
                    captured_at=_T0 + timedelta(days=1), capture_reason="revised",
                )
            ).inserted_primary_key[0]
        )


def _evaluated_versions(engine: Engine) -> set[int]:
    with engine.connect() as conn:
        return {
            int(v)
            for v in conn.execute(select(tables.eligibility_inputs.c.posting_version_id)).scalars()
        }


def _quarantine_rows(engine: Engine) -> dict[int, tuple[list[str], datetime | None]]:
    with engine.connect() as conn:
        return {
            int(row.posting_version_id): (list(row.markers_json), row.reopened_at)
            for row in conn.execute(select(tables.quarantined_bodies)).all()
        }


def test_a_foreign_body_is_withheld_from_the_rules_and_the_clean_one_is_not(
    engine: Engine, settings: Settings
) -> None:
    _, foreign_version = _seed(engine, "foreign", JOBRIGHT_PAGE)
    _, clean_version = _seed(engine, "clean", CLEAN_BODY)

    stats = run_eligibility(engine, settings)

    assert stats.quarantined == 1
    # The withheld body produced NO evaluation, so it can never contribute a quoted span.
    assert _evaluated_versions(engine) == {clean_version}
    markers, reopened_at = _quarantine_rows(engine)[foreign_version]
    assert reopened_at is None
    assert "h1b sponsor likely" in markers  # the markers are stored AS DATA


def test_the_posting_itself_is_untouched_by_the_quarantine(
    engine: Engine, settings: Settings
) -> None:
    """Fail-safe direction, asserted rather than described: closed for the VERDICT, open for
    the POSTING. A false positive must not silently delete or suppress a real job."""
    posting_id, _ = _seed(engine, "foreign", JOBRIGHT_PAGE)
    run_eligibility(engine, settings)
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.postings).where(tables.postings.c.id == posting_id)
        ).one()
        dispositions = conn.execute(select(tables.job_dispositions)).all()
    assert row.status == "open"
    assert row.closed_at is None
    assert dispositions == []


def test_a_held_body_is_not_re_refused_on_every_later_run(
    engine: Engine, settings: Settings
) -> None:
    """`stats.quarantined` counts NEW refusals, not the standing bucket.

    The `~quarantined` anti-join in `_pending` is what makes this true. Without it the held
    body is re-loaded and re-refused every run, so the number an operator reads could never
    distinguish a fresh defect from the nine that were already there — and the batch the
    process pool is sized from would carry rows nothing intends to judge.
    """
    _seed(engine, "foreign", JOBRIGHT_PAGE)
    assert run_eligibility(engine, settings).quarantined == 1
    assert run_eligibility(engine, settings).quarantined == 0


def test_the_drain_releases_a_body_re_fetched_from_the_employers_own_board(
    engine: Engine, settings: Settings
) -> None:
    """DRAIN GUARD 1 — re-entry condition: a newer version exists.

    Fails if `drain_quarantine` never runs: `reopened_at` stays NULL and the bucket keeps a row
    that is no longer withholding anything.
    """
    posting_id, foreign_version = _seed(engine, "foreign", JOBRIGHT_PAGE)
    assert run_eligibility(engine, settings).quarantined == 1
    assert _evaluated_versions(engine) == set()

    clean_version = _append_version(engine, posting_id, CLEAN_BODY)
    stats = run_eligibility(engine, settings)

    assert stats.released == 1
    _markers, reopened_at = _quarantine_rows(engine)[foreign_version]
    assert reopened_at is not None, "the drain never ran: the bucket has no re-entry path"
    # Released AND judged in the SAME pass — the drain runs on both sides of the gate.
    assert _evaluated_versions(engine) == {clean_version}


def test_the_drain_releases_a_false_positive_when_the_catalog_is_corrected(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DRAIN GUARD 2 — re-entry condition: the catalog that refused it no longer does.

    Without this path a marker withdrawn after a false positive would leave every row it caused
    held forever, because their bodies never change. Fails if `drain_quarantine` never runs.
    """
    _, foreign_version = _seed(engine, "foreign", JOBRIGHT_PAGE)
    assert run_eligibility(engine, settings).quarantined == 1
    assert _evaluated_versions(engine) == set()

    # The operator's correction: the markers that misjudged this body leave the closed catalog.
    monkeypatch.setattr(quality, "_FOREIGN_BODY_MARKERS", ())
    stats = run_eligibility(engine, settings)

    assert stats.released == 1
    _markers, reopened_at = _quarantine_rows(engine)[foreign_version]
    assert reopened_at is not None, "the drain never ran: a false positive is held forever"
    assert _evaluated_versions(engine) == {foreign_version}


def test_a_released_row_is_re_held_if_the_catalog_refuses_it_again(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain is not a one-way door, and releasing never DELETES the row.

    `record_quarantine` upserts and clears `reopened_at`, so the audit trail of a body having
    been held survives a release-and-re-hold cycle.
    """
    _, foreign_version = _seed(engine, "foreign", JOBRIGHT_PAGE)
    run_eligibility(engine, settings)
    monkeypatch.setattr(quality, "_FOREIGN_BODY_MARKERS", ())
    run_eligibility(engine, settings)
    assert _quarantine_rows(engine)[foreign_version][1] is not None

    monkeypatch.undo()
    # A fresh version, so the body is pending again under the restored catalog.
    _append_version(engine, _posting_of(engine, foreign_version), JOBRIGHT_PAGE)
    stats = run_eligibility(engine, settings)

    assert stats.quarantined == 1
    rows = _quarantine_rows(engine)
    assert len(rows) == 2, "a release must not delete the row it released"


def _posting_of(engine: Engine, version_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(tables.posting_versions.c.posting_id).where(
                    tables.posting_versions.c.id == version_id
                )
            ).scalar_one()
        )
