"""Delivery-drought detector. Each firing test names the wrong-version it rejects.

A real schema on `tmp_path`, seeded through the FK chain (foreign_keys is ON, D20). One
`eligibility_inputs` row is shared by every evaluation; per-run rows are the cheap part.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.notify.delivery_drought import DELIVERY_DROUGHT_WINDOW, check_delivery_drought
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import RUN_OK
from boardwatch.store.run_funnel_queries import TAILORED_KIND


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _seed_input(engine: Engine) -> int:
    """The FK chain a candidate evaluation needs: company → job → posting → version → input."""
    now = utcnow()
    with engine.begin() as conn:
        company_id = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=False
            )
        ).inserted_primary_key[0]
        job_id = conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        posting_id = conn.execute(
            insert(tables.postings).values(
                company_id=company_id, provider_posting_id="p1", job_id=job_id,
                title="Backend Engineer", normalized_title="backend engineer",
                url="https://x.test/1", locations_json=["Remote"], remote_policy="remote",
                first_seen_at=now, last_seen_at=now, status="open", consecutive_missing=0,
                content_hash="h1", body_text="body",
            )
        ).inserted_primary_key[0]
        pv_id = conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash="h1", body_text="body",
                captured_at=now, capture_reason="new",
            )
        ).inserted_primary_key[0]
        input_id = conn.execute(
            insert(tables.eligibility_inputs).values(
                posting_version_id=pv_id, profile_hash="ph", profile_snapshot_json={},
                rules_hash="rh", rules_snapshot_json={}, input_fingerprint="fp", created_at=now,
            )
        ).inserted_primary_key[0]
    return int(input_id)


def _run(
    engine: Engine, input_id: int, *, candidates: int, delivered: int,
    verdict: str = "eligible", status: str = RUN_OK,
) -> int:
    """One run plus `candidates` candidate evaluations and `delivered` tailored artifacts."""
    now = utcnow()
    with engine.begin() as conn:
        run_id = int(
            conn.execute(
                insert(tables.runs).values(started_at=now, finished_at=now, status=status)
            ).inserted_primary_key[0]
        )
        for _ in range(candidates):
            conn.execute(
                insert(tables.eligibility_evaluations).values(
                    input_id=input_id, engine_kind="llm", engine_version="t",
                    verdict=verdict, created_at=now, run_id=run_id,
                )
            )
        for i in range(delivered):
            conn.execute(
                insert(tables.artifacts).values(
                    kind=TAILORED_KIND, uri=f"file://r{run_id}-{i}", created_at=now, run_id=run_id
                )
            )
    return run_id


def test_fires_when_every_run_found_candidates_but_shipped_nothing(engine: Engine) -> None:
    input_id = _seed_input(engine)
    ids = [_run(engine, input_id, candidates=2, delivered=0) for _ in range(3)]
    alert = check_delivery_drought(engine, window=3)
    assert alert is not None
    assert "0 leads" in alert
    for run_id in ids:
        assert str(run_id) in alert


def test_silent_when_a_run_in_the_window_delivered(engine: Engine) -> None:
    # Rejects dropping the delivered==0 check.
    input_id = _seed_input(engine)
    _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=2, delivered=1)  # newest shipped one
    assert check_delivery_drought(engine, window=3) is None


def test_silent_on_a_quiet_steady_state_run(engine: Engine) -> None:
    # The false-positive guard: a run that judged no new candidate (nothing new to show) must
    # not alert. Rejects dropping the candidate>0 guard, which would fire on every quiet day.
    input_id = _seed_input(engine)
    _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=0, delivered=0)  # nothing new judged
    assert check_delivery_drought(engine, window=3) is None


def test_silent_on_an_eligibility_collapse(engine: Engine) -> None:
    # Every run judged only ineligible postings — no candidate, so the detector abstains (that
    # is a corpus-regression signal, not a delivery drought). ineligible is not a candidate.
    input_id = _seed_input(engine)
    for _ in range(3):
        _run(engine, input_id, candidates=3, delivered=0, verdict="ineligible")
    assert check_delivery_drought(engine, window=3) is None


def test_abstains_below_the_window(engine: Engine) -> None:
    input_id = _seed_input(engine)
    _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=2, delivered=0)
    assert check_delivery_drought(engine, window=3) is None


def test_only_clean_runs_count(engine: Engine) -> None:
    # A later non-ok run (crashed/in-flight) is excluded, so the three clean droughts still
    # fire; and its delivery must not rescue the window. Rejects dropping the status filter.
    input_id = _seed_input(engine)
    for _ in range(3):
        _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=2, delivered=5, status="running")  # newest, not ok
    assert check_delivery_drought(engine, window=3) is not None


def test_default_window_is_three(engine: Engine) -> None:
    assert DELIVERY_DROUGHT_WINDOW == 3
    input_id = _seed_input(engine)
    _run(engine, input_id, candidates=2, delivered=0)
    _run(engine, input_id, candidates=2, delivered=0)
    assert check_delivery_drought(engine) is None
    _run(engine, input_id, candidates=2, delivered=0)
    assert check_delivery_drought(engine) is not None
