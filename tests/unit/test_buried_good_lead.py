"""The buried-good-lead read and its soft alert. Each test names the wrong version it rejects.

A real schema on `tmp_path`, with verdicts written through `final_gate.record_gate_verdict` under
the stored profile's facts and the configured judge — the exact key `current_gate_verdicts` and
`current_gate_seniority` read on — so the read is exercised through the lane's own seams.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, update

from boardwatch.core.settings import load_settings
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact, facts_payload
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.notify.buried_good_lead import check_buried_good_lead
from boardwatch.store.buried_queries import buried_good_leads
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import record_disposition
from boardwatch.store.queries import (
    RUN_OK,
    current_posting_versions,
    save_eligibility,
    save_profile,
)
from boardwatch.store.tables import (
    companies,
    job_dispositions,
    jobs,
    posting_versions,
    postings,
    profile,
    runs,
)
from tests.conftest import as_engine_reads, write_bundled_role_taxonomy

NOW = datetime(2026, 9, 26, 4, 0, 0)
FACTS = Facts(
    work_authorization=WorkAuthFact(status="citizen", jurisdiction="us", needs_sponsorship=False)
)
JD = "Software engineer. Applicants must be U.S. citizens."
EVIDENCE = "must be U.S. citizens"


@pytest.fixture(autouse=True)
def _scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    write_bundled_role_taxonomy(tmp_path / "config")


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    with eng.begin() as conn:
        save_profile(
            conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
            locations=["Boston, MA"], remote_only=False, skills=["python"],
            taxonomy_version="v1", resume_max_pages=1, target_seniority_band="entry",
        )
        save_eligibility(
            conn, facts_json=facts_payload(FACTS), policy_json=Policy().model_dump(mode="json")
        )
    return eng


_counter = iter(range(1, 10_000))


def _posting(
    engine: Engine, *, decision: str = "eligible", seniority: str = "yes",
    closed_at: datetime | None = None, built: bool = False,
) -> int:
    """One posting with one final-gate verdict on its current version, as the daily stage writes
    it. `built` records the job's `built` disposition."""
    n = next(_counter)
    settings = load_settings()
    with engine.begin() as conn:
        company_id = int(conn.execute(insert(companies).values(
            name=f"Co{n}", provider="greenhouse", slug=f"co{n}", source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(conn.execute(insert(postings).values(
            company_id=company_id, job_id=job_id, provider_posting_id=f"p{n}", title="Eng",
            normalized_title="eng", first_seen_at=NOW, last_seen_at=NOW,
            status="open" if closed_at is None else "closed", closed_at=closed_at,
            consecutive_missing=0, content_hash=f"h{n}", body_text=JD,
        )).inserted_primary_key[0])
        version_id = int(conn.execute(insert(posting_versions).values(
            posting_id=posting_id, content_hash=f"h{n}", body_text=JD, captured_at=NOW,
            run_id=None, capture_reason="new",
        )).inserted_primary_key[0])
        final_gate.record_gate_verdict(
            conn, posting_version_id=version_id, jd_text=JD,
            facts=as_engine_reads(FACTS, settings.config_dir), policy=Policy(),
            catalog=load_rules(settings.config_dir),
            verdict=OracleVerdict(
                label=str(posting_id), decision=decision,
                reason="work_auth" if decision == "ineligible" else None,
                evidence=EVIDENCE if decision == "ineligible" else "", confidence="high",
                seniority_fit=seniority,
            ),
            model=settings.gate.model, effort=final_gate.gate_effort_key(settings.gate.effort),
            target_band="entry",
        )
        if built:
            record_disposition(
                conn, job_id, disposition="built", reason="lead_built", policy_version="v1",
                now=NOW,
            )
    return posting_id


def _run(engine: Engine, *, finished_at: datetime, status: str = RUN_OK) -> int:
    with engine.begin() as conn:
        return int(conn.execute(insert(runs).values(
            started_at=finished_at - timedelta(minutes=30), finished_at=finished_at,
            status=status,
        )).inserted_primary_key[0])


# --------------------------------------------------------------------------- the read


def test_the_read_splits_open_from_closed_and_excludes_every_other_case(engine: Engine) -> None:
    """Rejects, one each: dropping the `eligible` test (the ineligible posting leaks in), dropping
    the seniority test (the `no` and `unclear` postings leak in), dropping the built exclusion
    (the built posting leaks in), and splitting on `status` alone or swapping the halves (the
    closed posting lands in `open`)."""
    buried_open = _posting(engine)
    buried_closed = _posting(engine, closed_at=NOW)
    _posting(engine, built=True)
    _posting(engine, built=True, closed_at=NOW)
    _posting(engine, decision="ineligible")
    _posting(engine, decision="uncertain")
    _posting(engine, seniority="no")
    _posting(engine, seniority="unclear")

    with engine.connect() as conn:
        buried = buried_good_leads(conn, load_settings())

    assert buried.open == (buried_open,)
    assert buried.closed == {buried_closed: NOW}


def test_a_reopened_built_job_still_counts_as_delivered(engine: Engine) -> None:
    """Rejects keying "built" on a LIVE disposition: the drain reopening a delivered job does
    not make it undelivered."""
    posting_id = _posting(engine, built=True)
    with engine.begin() as conn:
        conn.execute(update(job_dispositions).values(reopened_at=NOW))
        buried = buried_good_leads(conn, load_settings())
    assert posting_id not in buried.open


def test_band_any_clears_on_the_verdict_alone(engine: Engine) -> None:
    """Under band `any` the seniority question is never asked, so requiring `yes` would mute the
    read for that tenant forever. Rejects dropping the band exception."""
    posting_id = _posting(engine, seniority="unclear")
    with engine.begin() as conn:
        conn.execute(update(profile).values(target_seniority_band="any"))
    # The verdict above was recorded under `entry`; re-record it under `any`, as the refresh would.
    settings = load_settings()
    with engine.begin() as conn:
        version = current_posting_versions(conn, [posting_id])[posting_id]
        final_gate.record_gate_verdict(
            conn, posting_version_id=version.posting_version_id, jd_text=JD,
            facts=as_engine_reads(FACTS, settings.config_dir), policy=Policy(),
            catalog=load_rules(settings.config_dir),
            verdict=OracleVerdict(label="x", decision="eligible", reason=None, evidence="",
                                  confidence="high", seniority_fit="unclear"),
            model=settings.gate.model, effort=final_gate.gate_effort_key(settings.gate.effort),
            target_band="any",
        )
        buried = buried_good_leads(conn, settings)
    assert buried.open == (posting_id,)


def test_no_profile_reads_nothing(tmp_path: Path) -> None:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    with eng.connect() as conn:
        buried = buried_good_leads(conn, load_settings())
    assert buried.open == () and buried.closed == {}


# --------------------------------------------------------------------------- the alert


def test_the_alert_fires_only_on_a_closure_since_the_previous_clean_run(engine: Engine) -> None:
    """Rejects firing on the standing closed count (the old closure would fire every run), and
    comparing against the wrong run (the failed run in between, or the current run itself)."""
    previous = _run(engine, finished_at=NOW)
    _run(engine, finished_at=NOW + timedelta(hours=12), status="failed")
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    _posting(engine, closed_at=NOW - timedelta(days=3))  # lost before `previous`: reported then
    _posting(engine)  # still open

    assert check_buried_good_lead(engine, load_settings(), run_id=current) is None

    lost = _posting(engine, closed_at=NOW + timedelta(hours=6))
    alert = check_buried_good_lead(engine, load_settings(), run_id=current)
    assert alert is not None
    assert f"posting {lost})" in alert
    assert "1 judge-cleared lead(s) closed" in alert
    assert "1 more are eligible" in alert
    # The previous run itself sees neither loss as its own: nothing before it to compare with.
    assert check_buried_good_lead(engine, load_settings(), run_id=previous) is None


def test_the_alert_ignores_a_closed_posting_that_was_delivered(engine: Engine) -> None:
    """Rejects an alert that reads raw closures rather than the buried population."""
    _run(engine, finished_at=NOW)
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    _posting(engine, closed_at=NOW + timedelta(hours=6), built=True)
    _posting(engine, closed_at=NOW + timedelta(hours=6), seniority="no")
    assert check_buried_good_lead(engine, load_settings(), run_id=current) is None
