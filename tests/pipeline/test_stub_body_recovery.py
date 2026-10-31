"""D-659: recovery evidence is a precondition, never an eligibility rule."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, select, update

from boardwatch.core.models import BoardSnapshot, RawPosting
from boardwatch.core.normalize import normalize_body
from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.gate_handshake import apply_gate_verdicts, build_gate_request
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.lanes.quality import MIN_BODY_LINES, meets_body_floor
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.queries import current_posting_versions, insert_run
from tests.pipeline import test_body_quarantine_drain as fixtures

engine = fixtures.engine
settings = fixtures.settings

EMPLOYER_URL = "https://boards.greenhouse.io/acme/jobs/123"


def stub(size: int) -> str:
    # Derived from the live quality floor: the 525-char specimen MUST clear it, catching a
    # detector that only reuses the floor (or the old thin_jd heuristic).
    heading = "Requirements\n" + "Python\n" * (MIN_BODY_LINES - 1)
    text = heading[:size] if len(heading) >= size else heading + "x" * (size - len(heading))
    assert len(normalize_body(text)) < size + 1
    assert len(text) == size
    if size == 525:
        assert meets_body_floor(text)
    return text


def seed(engine: Engine, body: str = "", *, evidence: bool = True) -> int:
    raw = RawPosting(
        provider_posting_id="jobapps-stable", title="Backend Engineer",
        url="https://jobright.ai/jobs/info/0123456789abcdef01234567",
        body_text=body or stub(525), locations=["Remote"],
        raw_json={"jobapps": {"posting_id": "jobapps-stable", **(
            {"employer_url": EMPLOYER_URL} if evidence else {}
        )}},
    )
    apply_board(engine, BoardSnapshot(status="partial", url="file:///fixture", postings=[raw]),
                1, insert_run(engine), scan_kind="lane", lane="jobapps")
    with engine.connect() as conn:
        return int(conn.execute(select(tables.postings.c.id).where(
            tables.postings.c.provider_posting_id == "jobapps-stable"
        )).scalar_one())


@pytest.mark.parametrize("origin", ["jobapps", "indeed", "stored_url"])
@pytest.mark.parametrize("size", [144, 53, 525])
def test_stub_is_held_before_deterministic_judging(
    engine: Engine, settings: Settings, size: int, origin: str,
) -> None:
    seed(engine, stub(size), evidence=origin == "jobapps")
    with engine.begin() as conn:
        if origin == "indeed":
            conn.execute(update(tables.postings).values(
                raw_json={"job": {"recruit": {"viewJobUrl": EMPLOYER_URL}}},
            ))
        elif origin == "stored_url":
            conn.execute(update(tables.companies).values(source="lane"))
            conn.execute(update(tables.postings).values(raw_json={}, url=EMPLOYER_URL))
    stats = run_eligibility(engine, settings)
    assert stats.quarantined == 1
    assert stats.evaluated == 0


def test_gate_send_cannot_judge_stub(engine: Engine, settings: Settings) -> None:
    pid = seed(engine)
    with engine.connect() as conn:
        versions = current_posting_versions(conn)
    request = build_gate_request([SimpleNamespace(posting_id=pid)], versions, Facts(),
                                 load_rules(settings.config_dir), request_id="stub", target_band="any")
    assert request["items"] == []


def test_gate_apply_cannot_clear_stub(engine: Engine, settings: Settings) -> None:
    pid = seed(engine)
    with engine.begin() as conn:
        result = apply_gate_verdicts(conn, [OracleVerdict(
            label=str(pid), decision="eligible", reason="none", evidence="", confidence="high",
        )], versions=current_posting_versions(conn), facts=Facts(), policy=Policy(),
            catalog=load_rules(settings.config_dir))
    assert result.judged == 0


def test_prior_eligible_cannot_bypass_delivery_hold(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from boardwatch.eligibility.read import (
        current_gate_verdicts,
        current_requirement_flags,
        current_verdicts,
    )

    pid = seed(engine, evidence=False)
    from boardwatch.eligibility.engine import EvaluationResult

    monkeypatch.setattr("boardwatch.eligibility.preflight.evaluate",
                        lambda *args: EvaluationResult(verdict="eligible", requirements=()))
    stats = run_eligibility(engine, settings)
    with engine.begin() as conn:
        apply_gate_verdicts(conn, [OracleVerdict(
            label=str(pid), decision="eligible", reason="none", evidence="", confidence="high",
        )], versions=current_posting_versions(conn), facts=Facts(), policy=Policy(),
            catalog=load_rules(settings.config_dir))
        conn.execute(update(tables.postings).values(raw_json={"jobapps": {"employer_url": EMPLOYER_URL}}))
        vids = [v.posting_version_id for v in current_posting_versions(conn).values()]
        verdicts = current_verdicts(conn, vids, stats.profile_hash, stats.rules_hash)
        flags = current_requirement_flags(conn, vids, stats.profile_hash, stats.rules_hash)
        gate = current_gate_verdicts(conn, vids, Facts(), load_rules(settings.config_dir),
                                     model=None, effort=None, target_band=None)
    assert gate[pid] == "uncertain"
    assert verdicts[pid] == "uncertain"
    assert flags[pid].eligibility_unconfirmed

EMPLOYER_BODY = "\n".join([
    "About the role", "Build backend services.", "Responsibilities", "Ship Python APIs.",
    "Requirements", "Applicants must be US citizens.", "Benefits", "Health insurance.",
])


def test_next_run_recovers_standing_copy_and_judges_employer_jd(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardwatch.pipeline import runner
    from boardwatch.providers.greenhouse import GreenhouseProvider

    pid = seed(engine)
    assert run_eligibility(engine, settings).evaluated == 0
    with engine.begin() as conn:
        conn.execute(update(tables.profile).values(
            eligibility_facts_json={"work_authorization": {"status": "needs_sponsorship", "jurisdiction": "us"}},
            eligibility_policy_json={"families": {"work_auth": "blocker"}},
        ))
    monkeypatch.setattr(runner, "_fetch_lanes", lambda *args: ([], []))
    from sqlalchemy import event

    active = set()
    event.listen(engine, "begin", lambda conn: active.add(conn))
    event.listen(engine, "commit", lambda conn: active.discard(conn))
    event.listen(engine, "rollback", lambda conn: active.discard(conn))
    calls: list[str] = []

    def fetch(self, fetcher, slug, ref):
        assert not active, "HTTP must run outside store transactions"
        calls.append(ref)
        return RawPosting(provider_posting_id=ref, title="Backend Engineer", url=EMPLOYER_URL,
                          locations=[], body_text=EMPLOYER_BODY, raw_json={"id": ref})

    monkeypatch.setattr(GreenhouseProvider, "fetch_posting", fetch)
    runner._run_lanes(engine, settings, insert_run(engine))
    with engine.connect() as conn:
        current = current_posting_versions(conn)[pid]
    assert current.body_text == EMPLOYER_BODY
    assert calls == ["123"]
    stats = run_eligibility(engine, settings)
    assert stats.quarantined == 0
    with engine.connect() as conn:
        assert conn.execute(select(tables.quarantined_bodies.c.reopened_at)).scalar_one() is not None
        evaluation = conn.execute(select(tables.eligibility_evaluations)).one()
        quoted = conn.execute(select(tables.eligibility_requirements.c.jd_locator_json)).scalars().all()
    assert evaluation.verdict == "ineligible"
    assert any("US citizens" in current.body_text[quote["span"][0]:quote["span"][1]]
               for quote in quoted), quoted


def test_reingestion_keeps_jobapps_key_evidence_and_recovered_body(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardwatch.pipeline import runner
    from boardwatch.providers.greenhouse import GreenhouseProvider

    pid = seed(engine)
    monkeypatch.setattr(runner, "_fetch_lanes", lambda *args: ([], []))
    monkeypatch.setattr(GreenhouseProvider, "fetch_posting", lambda self, fetcher, slug, ref: RawPosting(
        provider_posting_id=ref, title="Backend Engineer", url=EMPLOYER_URL,
        locations=[], body_text=EMPLOYER_BODY, raw_json={},
    ))
    _, errors = runner._run_lanes(engine, settings, insert_run(engine))
    assert errors == []
    seed(engine, evidence=False)
    with engine.connect() as conn:
        row = conn.execute(select(tables.postings)).one()
        sources = conn.execute(select(tables.posting_version_sources)).all()
    assert row.body_text == EMPLOYER_BODY
    assert row.id == pid and row.provider_posting_id == "jobapps-stable"
    assert row.raw_json["jobapps"]["employer_url"] == EMPLOYER_URL
    assert len(sources) == 2 and sources[-1].source_record_id == "123"


@pytest.mark.parametrize("failure", ["timeout", "unsupported", "wrong_id", "budget"])
def test_recovery_failure_is_counted_and_cannot_reuse_old_eligible(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    from boardwatch.core.politeness import FetchFailure
    from boardwatch.eligibility.engine import EvaluationResult
    from boardwatch.eligibility.read import current_verdicts
    from boardwatch.pipeline import runner
    from boardwatch.providers.greenhouse import GreenhouseProvider

    pid = seed(engine, evidence=False)
    monkeypatch.setattr("boardwatch.eligibility.preflight.evaluate",
                        lambda *args: EvaluationResult(verdict="eligible", requirements=()))
    stats = run_eligibility(engine, settings)
    url = EMPLOYER_URL
    with engine.begin() as conn:
        conn.execute(update(tables.postings).values(raw_json={"jobapps": {"employer_url": url}}))
    monkeypatch.setattr(runner, "_fetch_lanes", lambda *args: ([], []))

    calls: list[str] = []

    def fetch(self, fetcher, slug, ref):
        calls.append(ref)
        if failure in {"timeout", "budget"}:
            raise FetchFailure("timeout")
        return RawPosting(provider_posting_id="wrong" if failure == "wrong_id" else ref,
                          title="Backend Engineer", url=EMPLOYER_URL, locations=[], body_text=EMPLOYER_BODY, raw_json={})

    monkeypatch.setattr(GreenhouseProvider, "fetch_posting", fetch)
    if failure == "budget":
        # Exhaust jobapps' existing budget with a failure ahead of this standing copy.
        settings = settings.model_copy(update={"lane_posting_budget": 1})
        with engine.begin() as conn:
            conn.execute(update(tables.postings).values(provider_posting_id="oldest"))
        seed(engine)
        with engine.begin() as conn:
            conn.execute(update(tables.postings).where(
                tables.postings.c.provider_posting_id == "jobapps-stable"
            ).values(raw_json={"jobapps": {"employer_url": EMPLOYER_URL.replace("123", "456")}}))
    from boardwatch.scan import employer_body

    if failure == "unsupported":
        from boardwatch.providers.base import RefetchUnsupported

        def unsupported(provider):
            raise RefetchUnsupported("fixture provider has no posting refetch")

        monkeypatch.setattr(employer_body, "posting_refetcher", unsupported)

    typed_counts = {}
    recover = employer_body.recover_employer_bodies

    def capture(*args, **kwargs):
        result = recover(*args, **kwargs)
        typed_counts.update(result)
        return result

    monkeypatch.setattr(employer_body, "recover_employer_bodies", capture)
    _, errors = runner._run_lanes(engine, settings, insert_run(engine))
    assert len(errors) == 1, "every unresolved recovery must be counted"
    outcome = employer_body.RecoveryOutcome
    expected = {"timeout": outcome.UNAVAILABLE, "unsupported": outcome.UNSUPPORTED,
                "wrong_id": outcome.WRONG_IDENTITY, "budget": outcome.BUDGET}[failure]
    assert typed_counts[expected] == 1
    if failure == "budget":
        assert typed_counts[outcome.UNAVAILABLE] == 1
        runner._run_lanes(engine, settings, insert_run(engine))
        assert calls == ["123", "456"], "retry the oldest pending before repeating a failed read"
    with engine.connect() as conn:
        versions = current_posting_versions(conn)
        verdicts = current_verdicts(conn, [v.posting_version_id for v in versions.values()],
                                    stats.profile_hash, stats.rules_hash)
    assert verdicts[pid] == "uncertain"
    assert versions[pid].body_text == stub(525)


def test_longer_local_revision_does_not_release_pending_hold(engine: Engine, settings: Settings) -> None:
    pid = seed(engine)
    run_eligibility(engine, settings)
    seed(engine, stub(1500))
    with engine.begin() as conn:
        conn.execute(update(tables.postings).values(raw_json={}))
    run_eligibility(engine, settings)
    with engine.connect() as conn:
        version = current_posting_versions(conn)[pid]
        reopened = conn.execute(select(tables.quarantined_bodies.c.reopened_at)).scalars().all()
    assert version.employer_body_pending
    assert reopened and all(stamp is None for stamp in reopened)


def test_native_board_body_releases_converged_lane_copy(engine: Engine, settings: Settings) -> None:
    pid = seed(engine)
    with engine.begin() as conn:
        conn.execute(update(tables.postings).values(provider_posting_id="123", url=EMPLOYER_URL))
        conn.execute(update(tables.companies).values(source="lane"))
    run_eligibility(engine, settings)
    from boardwatch.providers.greenhouse import GreenhouseProvider

    apply_board(engine, BoardSnapshot(
        status="partial", url=GreenhouseProvider().board_url("acme"),
        postings=[RawPosting(provider_posting_id="123", title="Backend Engineer",
                             locations=[], url=EMPLOYER_URL, body_text=EMPLOYER_BODY, raw_json={"id": 123})],
    ), 1, insert_run(engine))
    with engine.connect() as conn:
        version = current_posting_versions(conn)[pid]
    assert not version.employer_body_pending


def test_source_for_another_requisition_cannot_release_hold(engine: Engine, settings: Settings) -> None:
    from boardwatch.core.clock import utcnow
    from boardwatch.core.normalize import content_hash
    from boardwatch.store.body_revision import record_body_revision
    from boardwatch.store.sources import record_version_source

    pid = seed(engine)
    run_eligibility(engine, settings)
    with engine.begin() as conn:
        vid = record_body_revision(conn, posting_id=pid, body_text=EMPLOYER_BODY,
                                   content_hash=content_hash(EMPLOYER_BODY), captured_at=utcnow())
        record_version_source(conn, posting_version_id=vid, run_id=None,
                              source_url=EMPLOYER_URL.replace("123", "456"), source_record_id="456",
                              observed_at=utcnow(), payload_hash=content_hash(EMPLOYER_BODY))
        version = current_posting_versions(conn)[pid]
    assert version.employer_body_pending


def test_each_employer_read_consumes_existing_lane_budget(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardwatch.core.politeness import Fetcher
    from boardwatch.pipeline import runner
    from boardwatch.providers.greenhouse import GreenhouseProvider

    seed(engine)
    settings = settings.model_copy(update={"lane_posting_budget": 1})
    monkeypatch.setattr(runner, "_fetch_lanes", lambda *args: ([], []))
    reads: list[str] = []
    monkeypatch.setattr(Fetcher, "_dispatch", lambda self, method, url, *args: reads.append(url))

    def fetch(self, fetcher, slug, ref):
        fetcher.get(EMPLOYER_URL)
        fetcher.get(EMPLOYER_URL)
        return RawPosting(provider_posting_id=ref, title="Backend Engineer", url=EMPLOYER_URL,
                          locations=[], body_text=EMPLOYER_BODY, raw_json={})

    monkeypatch.setattr(GreenhouseProvider, "fetch_posting", fetch)
    runner._run_lanes(engine, settings, insert_run(engine))
    assert len(reads) == 1
