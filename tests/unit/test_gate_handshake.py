"""TDD for the `eligibility gate request` / `gate apply` handshake (pure logic).

See .superpowers/sdd/plan-p5-final-gate/task-2-brief.md. Mirrors test_final_gate_
persistence.py's seeding helper and test_eligibility_cmd.py's CliRunner pattern.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.eligibility.catalog import RulesCatalog, load_rules
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.gate_handshake import (
    ApplyGateResult,
    apply_gate_verdicts,
    build_gate_request,
)
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import CurrentVersion, get_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

runner = CliRunner()

INIT_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"


def _catalog(tmp_path: Path) -> RulesCatalog:
    return load_rules(tmp_path / "no-such-cfg-dir")


def seed_posting_version(conn: Connection, *, body_text: str, slug: str = "acme-gate") -> tuple[int, int]:
    """Mirrors test_final_gate_persistence.py's helper; returns (posting_id, posting_version_id)."""
    now = utcnow()
    company_id = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=slug, source="user", watched=True,
    )).inserted_primary_key[0])
    job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
    posting_id = int(conn.execute(insert(postings).values(
        company_id=company_id, job_id=job_id, provider_posting_id=f"p-{slug}",
        title="Eng", normalized_title="eng", first_seen_at=now, last_seen_at=now,
        status="open", consecutive_missing=0, content_hash=f"h-{slug}", body_text=body_text,
    )).inserted_primary_key[0])
    posting_version_id = int(conn.execute(insert(posting_versions).values(
        posting_id=posting_id, content_hash=f"h-{slug}", body_text=body_text,
        captured_at=now, run_id=None, capture_reason="new",
    )).inserted_primary_key[0])
    return posting_id, posting_version_id


@dataclass(frozen=True)
class _FakeRankedPosting:
    """Duck-types the one attribute build_gate_request reads off a RankedPosting,
    without importing cli.top_cmd into a unit test of pure eligibility logic."""

    posting_id: int


# ---------------------------------------------------------------------------
# Step 1: build_gate_request shape
# ---------------------------------------------------------------------------


def test_build_gate_request_one_item_per_visible_posting_label_is_posting_id(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    ranked_visible = [_FakeRankedPosting(posting_id=1), _FakeRankedPosting(posting_id=2)]
    versions = {
        1: CurrentVersion(posting_version_id=10, posting_id=1, body_text="JD one", captured_at=utcnow()),
        2: CurrentVersion(posting_version_id=20, posting_id=2, body_text="JD two", captured_at=utcnow()),
    }
    facts = Facts(highest_degree="bachelor")

    request = build_gate_request(ranked_visible, versions, facts, catalog, request_id="req-1")

    assert request["request_id"] == "req-1"
    items = request["items"]
    assert len(items) == 2
    labels = {item["label"] for item in items}
    assert labels == {"1", "2"}
    by_label = {item["label"]: item for item in items}
    assert by_label["1"]["jd_text"] == "JD one"
    assert by_label["2"]["jd_text"] == "JD two"
    for item in items:
        assert "expected_verdict" not in item
        assert "hint" not in item


def test_build_gate_request_skips_a_posting_missing_from_versions(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    ranked_visible = [_FakeRankedPosting(posting_id=1), _FakeRankedPosting(posting_id=99)]
    versions = {
        1: CurrentVersion(posting_version_id=10, posting_id=1, body_text="JD one", captured_at=utcnow()),
    }
    facts = Facts()

    request = build_gate_request(ranked_visible, versions, facts, catalog, request_id="req-2")

    assert [item["label"] for item in request["items"]] == ["1"]


# ---------------------------------------------------------------------------
# Step 5: apply_gate_verdicts
# ---------------------------------------------------------------------------


def test_apply_gate_verdicts_demotes_a_high_confidence_provenanced_ineligible(tmp_path: Path) -> None:
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    jd = "This position requires an active Top Secret security clearance."
    evidence = "requires an active Top Secret security clearance"
    with engine.begin() as conn:
        posting_id, pv_id = seed_posting_version(conn, body_text=jd)
    versions = {posting_id: CurrentVersion(
        posting_version_id=pv_id, posting_id=posting_id, body_text=jd, captured_at=utcnow(),
    )}
    verdict = OracleVerdict(
        label=str(posting_id), decision="ineligible", reason="clearance",
        evidence=evidence, confidence="high",
    )

    with engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, [verdict], versions=versions, facts=Facts(),
            policy=Policy(families={}), catalog=catalog,
        )

    assert isinstance(result, ApplyGateResult)
    assert result.judged == 1
    assert result.ineligible == 1
    assert result.downgraded == 0
    assert result.demoted_labels == (str(posting_id),)


def test_apply_gate_verdicts_does_not_demote_a_low_confidence_ineligible(tmp_path: Path) -> None:
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    jd = "This position requires an active Top Secret security clearance."
    evidence = "requires an active Top Secret security clearance"
    with engine.begin() as conn:
        posting_id, pv_id = seed_posting_version(conn, body_text=jd)
    versions = {posting_id: CurrentVersion(
        posting_version_id=pv_id, posting_id=posting_id, body_text=jd, captured_at=utcnow(),
    )}
    verdict = OracleVerdict(
        label=str(posting_id), decision="ineligible", reason="clearance",
        evidence=evidence, confidence="low",
    )

    with engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, [verdict], versions=versions, facts=Facts(),
            policy=Policy(families={}), catalog=catalog,
        )

    assert result.judged == 1
    assert result.ineligible == 0
    assert result.downgraded == 1
    assert result.demoted_labels == ()


def test_apply_gate_verdicts_skips_a_verdict_for_a_posting_not_in_versions(tmp_path: Path) -> None:
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    verdict = OracleVerdict(
        label="999", decision="ineligible", reason="clearance",
        evidence="whatever", confidence="high",
    )

    with engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, [verdict], versions={}, facts=Facts(),
            policy=Policy(families={}), catalog=catalog,
        )

    assert result.judged == 0
    assert result.ineligible == 0
    assert result.demoted_labels == ()


def test_apply_gate_verdicts_writes_under_the_supplied_facts_and_policy(tmp_path: Path) -> None:
    """Ties the write to build_identity's inputs: a persisted evaluation row must exist
    (record_gate_verdict was actually called with these facts/policy), matching Task 1's
    identity-join contract rather than duplicating its own test."""
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    ensure_schema(engine)
    catalog = _catalog(tmp_path)
    jd = "We require U.S. citizenship for this role."
    with engine.begin() as conn:
        posting_id, pv_id = seed_posting_version(conn, body_text=jd)
    versions = {posting_id: CurrentVersion(
        posting_version_id=pv_id, posting_id=posting_id, body_text=jd, captured_at=utcnow(),
    )}
    verdict = OracleVerdict(
        label=str(posting_id), decision="eligible", reason=None,
        evidence="", confidence="high",
    )

    with engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, [verdict], versions=versions, facts=Facts(highest_degree="bachelor"),
            policy=Policy(families={}), catalog=catalog,
        )
    assert result.judged == 1
    from boardwatch.store.tables import eligibility_evaluations
    with engine.connect() as conn:
        rows = conn.execute(select(eligibility_evaluations.c.verdict)).all()
    assert [r.verdict for r in rows] == ["eligible"]


# ---------------------------------------------------------------------------
# Step 10: CLI smoke test
# ---------------------------------------------------------------------------


def _run(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def test_gate_request_cli_writes_a_well_formed_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = tmp_path / "data"
    assert _run(data_dir, ["init"], INIT_INPUT).exit_code == 0
    engine = get_engine(data_dir)
    with engine.begin() as conn:
        seed_posting_version(conn, body_text="We seek a Backend Engineer with Python skills.")

    out_path = tmp_path / "gate_request.json"
    result = _run(data_dir, ["eligibility", "gate", "request", "--out", str(out_path)])

    assert result.exit_code == 0, result.output
    assert out_path.is_file()
    import json

    payload = json.loads(out_path.read_text())
    assert len(payload["items"]) == 1
    assert payload["items"][0]["label"] == "1"
    assert "hint" not in payload["items"][0]


def test_gate_apply_cli_demotes_the_expected_posting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = tmp_path / "data"
    assert _run(data_dir, ["init"], INIT_INPUT).exit_code == 0
    engine = get_engine(data_dir)
    jd = "This position requires an active Top Secret security clearance."
    with engine.begin() as conn:
        posting_id, _pv_id = seed_posting_version(conn, body_text=jd)
    with engine.connect() as conn:
        assert get_profile(conn) is not None

    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(
        f'[{{"label": "{posting_id}", "decision": "ineligible", "reason": "clearance", '
        f'"evidence": "requires an active Top Secret security clearance", '
        f'"confidence": "high"}}]',
        encoding="utf-8",
    )

    result = _run(data_dir, ["eligibility", "gate", "apply", "--verdicts", str(verdicts_path)])

    assert result.exit_code == 0, result.output
    assert "judged 1" in result.output
    assert "ineligible 1" in result.output
    assert str(posting_id) in result.output
