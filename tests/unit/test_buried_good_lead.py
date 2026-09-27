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


def _verdict(
    engine: Engine, posting_id: int, *, decision: str = "eligible", seniority: str = "yes",
    model: str | None = None, target_band: str = "entry",
) -> None:
    """One more final-gate row on the posting's current version. `model` defaults to the
    configured judge — the CURRENT key; any other model is an OLDER key the current read skips."""
    settings = load_settings()
    with engine.begin() as conn:
        version = current_posting_versions(conn, [posting_id])[posting_id]
        final_gate.record_gate_verdict(
            conn, posting_version_id=version.posting_version_id, jd_text=JD,
            facts=as_engine_reads(FACTS, settings.config_dir), policy=Policy(),
            catalog=load_rules(settings.config_dir),
            verdict=OracleVerdict(
                label=str(posting_id), decision=decision,
                reason="work_auth" if decision == "ineligible" else None,
                evidence=EVIDENCE if decision == "ineligible" else "", confidence="high",
                seniority_fit=seniority,
            ),
            model=settings.gate.model if model is None else model,
            effort=final_gate.gate_effort_key(settings.gate.effort), target_band=target_band,
        )


def _posting(
    engine: Engine, *, decision: str = "eligible", seniority: str = "yes",
    closed_at: datetime | None = None, built: bool = False, model: str | None = None,
) -> int:
    """One posting with one final-gate verdict on its current version, as the daily stage writes
    it. `built` records the job's `built` disposition; `model` as in `_verdict`."""
    n = next(_counter)
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
        conn.execute(insert(posting_versions).values(
            posting_id=posting_id, content_hash=f"h{n}", body_text=JD, captured_at=NOW,
            run_id=None, capture_reason="new",
        ))
        if built:
            record_disposition(
                conn, job_id, disposition="built", reason="lead_built", policy_version="v1",
                now=NOW,
            )
    _verdict(engine, posting_id, decision=decision, seniority=seniority, model=model)
    return posting_id


def _run(
    engine: Engine, *, finished_at: datetime, status: str = RUN_OK, pipeline: bool = True
) -> int:
    """A run row. `pipeline` stamps the corpus counts only the funnel writer writes; without it
    the row is a manual command's (`ensure_run`) or a run that died before its funnel."""
    corpus = {"corpus_open": 1, "corpus_evaluated": 1, "corpus_candidates": 1} if pipeline else {}
    with engine.begin() as conn:
        return int(conn.execute(insert(runs).values(
            started_at=finished_at - timedelta(minutes=30), finished_at=finished_at,
            status=status, **corpus,
        )).inserted_primary_key[0])


def _alert(engine: Engine, *, run_id: int) -> str | None:
    """The alert over the population the funnel would read now."""
    with engine.connect() as conn:
        buried = buried_good_leads(conn, load_settings())
    return check_buried_good_lead(engine, buried, run_id=run_id)


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
    assert buried.stale_open == () and buried.stale_closed == {}


OLD = "an-older-judge"


def test_the_read_counts_a_lead_cleared_only_under_an_older_key(engine: Engine) -> None:
    """Rejects, one each: dropping the older-key population (both leak out), testing ANY old row
    rather than the NEWEST (the later-held posting leaks in), dropping its `eligible` or seniority
    test, dropping the built exclusion, and swapping its halves."""
    stale_open = _posting(engine, model=OLD)
    stale_closed = _posting(engine, model=OLD, closed_at=NOW)
    later_held = _posting(engine, model=OLD)
    _verdict(engine, later_held, decision="ineligible", model=OLD)
    _posting(engine, model=OLD, seniority="no")
    _posting(engine, model=OLD, decision="uncertain")
    _posting(engine, model=OLD, built=True)

    with engine.connect() as conn:
        buried = buried_good_leads(conn, load_settings())

    assert buried.stale_open == (stale_open,)
    assert buried.stale_closed == {stale_closed: NOW}
    assert buried.open == () and buried.closed == {}


def test_a_lead_with_a_current_key_verdict_is_never_counted_as_stale(engine: Engine) -> None:
    """Old-key `eligible`/`yes` plus ANY current-key verdict: the current key owns the posting.
    Rejects dropping the "no current-key verdict" test — the re-cleared lead would be counted in
    BOTH numbers and the re-held one would read cleared. Both current-key rows are OLDER than the
    old-key rows, so the newest-row selection alone cannot exclude them."""
    re_cleared = _posting(engine)
    _verdict(engine, re_cleared, model=OLD)
    re_held = _posting(engine, decision="uncertain")
    _verdict(engine, re_held, model=OLD)

    with engine.connect() as conn:
        buried = buried_good_leads(conn, load_settings())

    assert buried.open == (re_cleared,)
    assert buried.stale_open == () and buried.stale_closed == {}


def test_a_verdict_on_a_superseded_body_is_not_a_current_key_verdict(engine: Engine) -> None:
    """The current key includes the CURRENT version. A body revision after the verdict leaves no
    current-key verdict, so the lead is stale, not current. Rejects reading any version but the
    newest (the old version's verdict would read current)."""
    posting_id = _posting(engine)
    with engine.begin() as conn:
        conn.execute(insert(posting_versions).values(
            posting_id=posting_id, content_hash="revised", body_text=JD + " Revised.",
            captured_at=NOW + timedelta(days=1), run_id=None, capture_reason="revised",
        ))
    with engine.connect() as conn:
        buried = buried_good_leads(conn, load_settings())
    assert buried.open == ()
    assert buried.stale_open == (posting_id,)


def test_an_older_key_asked_under_band_any_clears_on_the_verdict_alone(engine: Engine) -> None:
    """The band exception, on the row's OWN recorded band. Rejects dropping it."""
    posting_id = _posting(engine, model=OLD, seniority="unclear")
    _verdict(engine, posting_id, model=OLD, seniority="unclear", target_band="any")
    with engine.connect() as conn:
        buried = buried_good_leads(conn, load_settings())
    assert buried.stale_open == (posting_id,)


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
    assert buried.stale_open == () and buried.stale_closed == {}


# --------------------------------------------------------------------------- the alert


def test_the_alert_fires_only_on_a_closure_since_the_previous_pipeline_run(
    engine: Engine,
) -> None:
    """Rejects firing on the standing closed count (the old closure would fire every run), and
    comparing against the wrong run (a failed run that never reached its funnel, or the current
    run itself)."""
    previous = _run(engine, finished_at=NOW)
    _run(engine, finished_at=NOW + timedelta(hours=12), status="failed", pipeline=False)
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    _posting(engine, closed_at=NOW - timedelta(days=3))  # lost before `previous`: reported then
    _posting(engine)  # still open

    assert _alert(engine, run_id=current) is None

    lost = _posting(engine, closed_at=NOW + timedelta(hours=6))
    alert = _alert(engine, run_id=current)
    assert alert is not None
    assert f"posting {lost})" in alert
    assert "1 judge-cleared lead(s) closed" in alert
    assert "1 more are eligible" in alert
    # The previous run itself sees neither loss as its own: nothing before it to compare with.
    assert _alert(engine, run_id=previous) is None


def test_a_manual_command_run_between_two_pipeline_runs_does_not_hide_a_closure(
    engine: Engine,
) -> None:
    """A manual `scan` mints an `ok` run row with no funnel. Rejects anchoring on the newest `ok`
    run of any kind: the closure before the manual run would never be alerted."""
    _run(engine, finished_at=NOW)
    _run(engine, finished_at=NOW + timedelta(hours=12), pipeline=False)  # e.g. a manual scan
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    lost = _posting(engine, closed_at=NOW + timedelta(hours=6))
    alert = _alert(engine, run_id=current)
    assert alert is not None and f"(posting {lost})" in alert


def test_a_closure_a_failed_pipeline_run_reported_is_not_reported_again(engine: Engine) -> None:
    """A failed pipeline run still reached its funnel and this alert. Rejects anchoring on clean
    runs only: the next run would re-report the loss the failed run already did."""
    _run(engine, finished_at=NOW)
    _posting(engine, closed_at=NOW + timedelta(hours=6))
    failed = _run(engine, finished_at=NOW + timedelta(hours=12), status="failed")
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    assert _alert(engine, run_id=failed) is not None, "guard: the failed run reported it"
    assert _alert(engine, run_id=current) is None


def test_an_unread_population_abstains(engine: Engine) -> None:
    """`None` is a funnel that was not collected. Rejects reading it as a fault or re-reading."""
    _run(engine, finished_at=NOW)
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    _posting(engine, closed_at=NOW + timedelta(hours=6))
    assert check_buried_good_lead(engine, None, run_id=current) is None


def test_the_alert_ignores_a_closed_posting_that_was_delivered(engine: Engine) -> None:
    """Rejects an alert that reads raw closures rather than the buried population."""
    _run(engine, finished_at=NOW)
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    _posting(engine, closed_at=NOW + timedelta(hours=6), built=True)
    _posting(engine, closed_at=NOW + timedelta(hours=6), seniority="no")
    assert _alert(engine, run_id=current) is None


def test_the_alert_fires_on_an_older_key_closure_and_names_it_apart(engine: Engine) -> None:
    """Rejects an alert that reads only the current-key closed count, one that reads the older
    key's standing closed set, and one that folds the two into one unlabelled number."""
    _run(engine, finished_at=NOW)
    current = _run(engine, finished_at=NOW + timedelta(days=1))
    _posting(engine, model=OLD, closed_at=NOW - timedelta(days=3))  # lost before: reported then
    _posting(engine, model=OLD)  # still open
    assert _alert(engine, run_id=current) is None

    lost = _posting(engine, model=OLD, closed_at=NOW + timedelta(hours=6))
    alert = _alert(engine, run_id=current)
    assert alert is not None
    assert "judge-cleared lead(s) closed" not in alert, "an older-key loss was named current-key"
    assert "1 lead(s) cleared under an older judge key and never re-judged" in alert
    assert f"(posting {lost})" in alert
    assert "1 more are still open" in alert
