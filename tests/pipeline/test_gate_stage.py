"""T42 red-first tests: the headless final-eligibility-gate judge stage on the daily path.

Every test drives a fake `claude` on PATH — real headless claude is never invoked from the
suite. The fake MUST NOT read stdin (a stdin-reading fake would hang the suite forever); it
exits immediately, reading its canned behaviour from environment variables the test sets.

Fails open at every seam (D-074): the fake's failure modes below (`exit1`, `garbage`,
`wrongcount`) each drop exactly one BATCH's verdicts and must never make the run fatal or
drop a real lead from the slate.

The `fenced` mode is NOT a failure mode -- it is the shape real headless haiku actually
returned on run 4, and it must be JUDGED, not failed open. It exists because this fake
returned bare `json.dumps(verdicts)` and therefore modelled a response the live model does
not reliably produce, which is how an armed judge reached production judging nothing.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from tests.conftest import write_test_resume_template
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli

# A different, richer body than test_pipeline_run's shared BODY: the "ineligible" tests need a
# literal substring to cite as evidence (`resolve_provenance` requires a raw JD substring), and
# the sentence is deliberately something none of the SEVEN deterministic catalog families would
# match — the deterministic engine must clear this posting so it reaches `ranked.visible` and
# the GATE is the only thing that later demotes it.
BODY = (
    "We are hiring a backend engineer to work on Python and PostgreSQL services. "
    "Relocation to our Antarctica research base is mandatory within 30 days of starting."
)
EVIDENCE = "Relocation to our Antarctica research base is mandatory within 30 days of starting."

FAKE_CLAUDE = '''#!/usr/bin/env python3
import json, os, re, sys

sentinel = os.environ.get("GATE_FAKE_SENTINEL")
if sentinel:
    with open(sentinel, "a", encoding="utf-8") as fh:
        fh.write("called\\n")

mode = os.environ.get("GATE_FAKE_MODE", "ok")
if mode == "exit1":
    sys.stderr.write("fake claude: simulated failure\\n")
    sys.exit(1)

prompt = sys.argv[-1]
match = re.search(r"ITEMS:\\n(.*)$", prompt, re.S)
items = json.loads(match.group(1)) if match else []
labels = [item["label"] for item in items]

if mode == "garbage":
    print("not json at all {{{")
    sys.exit(0)

if mode == "wrongcount":
    verdicts = (
        [{"label": labels[0], "decision": "eligible", "reason": None, "evidence": "",
          "confidence": "high"}]
        if labels else []
    )
elif mode == "nospan":
    verdicts = [
        {"label": l, "decision": "ineligible", "reason": "work_auth",
         "evidence": "this sentence does not appear anywhere in the jd text",
         "confidence": "high"}
        for l in labels
    ]
elif mode == "ineligible_span":
    target = os.environ.get("GATE_FAKE_TARGET_LABEL")
    evidence = os.environ.get("GATE_FAKE_EVIDENCE", "")
    verdicts = []
    for l in labels:
        if l == target:
            verdicts.append({"label": l, "decision": "ineligible", "reason": "work_auth",
                              "evidence": evidence, "confidence": "high"})
        else:
            verdicts.append({"label": l, "decision": "eligible", "reason": None,
                              "evidence": "", "confidence": "high"})
else:
    verdicts = [
        {"label": l, "decision": "eligible", "reason": None, "evidence": "",
         "confidence": "high"}
        for l in labels
    ]

result_text = json.dumps(verdicts)
if mode == "fenced":
    # Byte-shape of what real haiku returned on run 4: a ```json fence around the array,
    # despite the output contract forbidding fences.
    result_text = "```json" + chr(10) + result_text + chr(10) + "```"
envelope = {"is_error": False, "result": result_text}
print(json.dumps(envelope))
'''


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pins BOTH config_dir (env) and data_dir (explicit arg, below) to scratch — this ticket
    adds a write path, and the suite must never reach a real user root."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


@pytest.fixture()
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Installs the fake `claude` at the FRONT of PATH. Never reads stdin — see module
    docstring. Returns the sentinel path (not yet created); a test that expects the fake NOT
    to run asserts this path is absent, and one that expects it TO run asserts it exists."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    script = bindir / "claude"
    script.write_text(FAKE_CLAUDE, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    sentinel = tmp_path / "fake-claude-called.log"
    monkeypatch.setenv("GATE_FAKE_SENTINEL", str(sentinel))
    return sentinel


#: The FIXTURE above is POSIX-only, not the stage. It installs an extensionless script named
#: `claude`, and Windows' CreateProcess appends only `.exe` to an extensionless command, so
#: `_call_claude`'s `subprocess.run(["claude", ...])` raises `FileNotFoundError` and the gate
#: fails open before the fake runs at all -- which silently turns every mode below into the
#: same "judge unavailable" path. A `.cmd`/`.bat` shim would not be found either, for the same
#: reason. Tests that need the fake only to be ABSENT are NOT marked: they assert a request was
#: never made, which is meaningful on every platform.
_needs_an_executable_fake = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the fake `claude` is an extensionless POSIX script and Windows cannot spawn it; "
    "the gate stage itself is platform-neutral",
)


def _ready(data_dir: Path) -> None:
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    write_test_resume_template(load_settings(data_dir=data_dir).config_dir)


def _seed(data_dir: Path, *, slug: str = "acme-gate1", body: str = BODY) -> int:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(conn.execute(insert(tables.companies).values(
            name="Acme", provider="greenhouse", slug=slug, source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0])
        posting_id = int(conn.execute(insert(tables.postings).values(
            company_id=company_id, provider_posting_id=f"p-{slug}",
            title="Backend Engineer", normalized_title="backend engineer",
            url="https://example.test/j", locations_json=["Remote"],
            remote_policy="remote", first_seen_at=now, last_seen_at=now,
            status="open", consecutive_missing=0, content_hash=f"h-{slug}",
            body_text=body, job_id=job_id,
        )).inserted_primary_key[0])
        conn.execute(insert(tables.posting_versions).values(
            posting_id=posting_id, content_hash=f"h-{slug}", body_text=body,
            captured_at=now, capture_reason="new",
        ))
    return posting_id


def _arm_gate(data_dir: Path, *, batch_size: int = 13) -> None:
    config_dir = load_settings(data_dir=data_dir).config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        f"[gate]\nenabled = true\nmodel = \"sonnet\"\nbatch_size = {batch_size}\n"
        "call_timeout_s = 30\n",
        encoding="utf-8",
    )


def _pipeline(data_dir: Path, out_root: Path):
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
    )


def _current_gate_verdict(data_dir: Path, posting_id: int) -> str | None:
    from boardwatch.eligibility.preflight import current_identity
    from boardwatch.eligibility.read import current_gate_verdicts
    from boardwatch.store.queries import current_posting_versions

    settings = load_settings(data_dir=data_dir)
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        assert identity is not None
        versions = current_posting_versions(conn, [posting_id])
        verdicts = current_gate_verdicts(
            conn, [v.posting_version_id for v in versions.values()], *identity
        )
    return verdicts.get(posting_id)


# ---------------------------------------------------------------------------
# (a) happy path: ineligible + a raw-substring span
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_ineligible_with_span_excludes_the_lead_and_persists_final_gate_ineligible(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TWO postings, on purpose. Run 5 (2026-09-05) was the first run on which the judge
    WORKED — 40 judged, 10 rejected — and it went FATAL: "cohort incomplete: 10 shortlisted
    candidates unaccounted", because a judge rejection was not a terminal state the cohort
    guard knew about. This test had ONE posting, so the rejection emptied the slate and the
    empty-day guard fired instead; and it never asserted `summary.fatal`, so it was green on
    the exact run that failed. With a second lead that stays, the cohort guard is the guard
    that runs, and the fatal assertion is the one that matters.
    """
    _ready(env)
    posting_id = _seed(env)
    kept_id = _seed(env, slug="acme-gate-kept")
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "ineligible_span")
    monkeypatch.setenv("GATE_FAKE_TARGET_LABEL", str(posting_id))
    monkeypatch.setenv("GATE_FAKE_EVIDENCE", EVIDENCE)

    summary = _pipeline(env, tmp_path / "apps")

    assert fake_claude.exists(), "the gate never called the fake claude at all"
    tailored_ids = [lead.posting_id for lead in summary.tailored]
    assert posting_id not in tailored_ids, (
        "a lead the gate demoted to ineligible must never be tailored"
    )
    assert kept_id in tailored_ids, "the lead the judge passed must still be delivered"
    assert summary.gate_judged == 2
    assert summary.gate_ineligible == 1
    assert summary.gate_failed_open == 0
    assert _current_gate_verdict(env, posting_id) == "ineligible"
    assert summary.fatal is None, summary.fatal
    assert summary.gate_excluded_ids == [posting_id]


# ---------------------------------------------------------------------------
# (b) non-zero exit: fail open, not fatal, gate_failed_open counted, digest carries it
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_nonzero_exit_fails_open_and_is_not_fatal(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")

    out_root = tmp_path / "apps"
    summary = _pipeline(env, out_root)

    assert fake_claude.exists(), "the gate never attempted a call"
    assert summary.fatal is None, "a down judge must never make the run fatal"
    assert summary.gate_failed_open == 1
    assert summary.gate_judged == 0
    # The lead is unchanged: still tailored, exactly as it would be with the gate off.
    assert posting_id in [lead.posting_id for lead in summary.tailored]
    assert any("gate" in e and "failed open" in e for e in summary.errors), summary.errors
    assert summary.morning is not None
    digest_text = summary.morning.markdown_path.read_text(encoding="utf-8")
    assert "failed open" in digest_text, "the soft alert never reached the digest"


# ---------------------------------------------------------------------------
# garbage/unparseable output: fails open the same way
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_garbage_output_fails_open(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "garbage")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None
    assert summary.gate_failed_open == 1
    assert summary.gate_judged == 0
    assert posting_id in [lead.posting_id for lead in summary.tailored]


# ---------------------------------------------------------------------------
# a FENCED response is the real model's shape and must be judged, not failed open
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_judges_a_response_wrapped_in_a_markdown_fence(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run 4, the first armed run, judged NOTHING: all four haiku batches came back as
    ```json\n[...]\n``` and all four failed open on a JSONDecodeError at character 0.

    The suite was green throughout, because the fake returned an unfenced array — a shape the
    live model does not reliably produce. This test pins the live shape, and the assertion is
    on `gate_judged`, not merely on `gate_failed_open == 0`: a stage that fails open silently
    also reports zero judged, so only the positive count distinguishes "parsed it" from
    "never called".
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "fenced")

    summary = _pipeline(env, tmp_path / "apps")

    assert fake_claude.exists(), "the gate never attempted a call"
    assert summary.gate_failed_open == 0, summary.errors
    assert summary.gate_judged == 1
    assert summary.gate_eligible == 1
    assert posting_id in [lead.posting_id for lead in summary.tailored]


# ---------------------------------------------------------------------------
# wrong item count: fails open the whole batch, never trusts a partial response
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_wrong_item_count_fails_open(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    first = _seed(env, slug="acme-gate-a")
    second = _seed(env, slug="acme-gate-b")
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "wrongcount")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None
    assert summary.gate_failed_open == 1
    assert summary.gate_judged == 0
    tailored_ids = [lead.posting_id for lead in summary.tailored]
    assert first in tailored_ids and second in tailored_ids


# ---------------------------------------------------------------------------
# (c) ineligible with NO resolvable span: persisted uncertain, STILL delivered, end to end
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_ineligible_with_no_span_persists_uncertain_and_the_lead_is_still_delivered(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "nospan")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.gate_ineligible == 0, "a span-less ineligible must downgrade, not persist"
    assert summary.gate_uncertain == 1
    assert summary.gate_failed_open == 0
    assert posting_id in [lead.posting_id for lead in summary.tailored], (
        "the keystone's fail-open downgrade must still deliver the lead"
    )
    assert _current_gate_verdict(env, posting_id) == "uncertain"


# ---------------------------------------------------------------------------
# (d) enabled=False: no subprocess spawned at all
# ---------------------------------------------------------------------------


def test_gate_disabled_spawns_no_subprocess(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    posting_id = _seed(env)
    # No _arm_gate(env) call: gate.enabled defaults False.
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")  # would be an obvious tell if ever invoked

    summary = _pipeline(env, tmp_path / "apps")

    assert not fake_claude.exists(), "gate.enabled=False must never spawn claude"
    assert summary.gate_judged == 0
    assert summary.gate_eligible == 0
    assert summary.gate_ineligible == 0
    assert summary.gate_uncertain == 0
    assert summary.gate_failed_open == 0
    assert posting_id in [lead.posting_id for lead in summary.tailored]


# ---------------------------------------------------------------------------
# (e) never re-judge: a lead with a current gate row is not in any request
# ---------------------------------------------------------------------------


def test_gate_never_rejudges_a_lead_with_a_current_gate_row(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from boardwatch.eligibility.catalog import load_rules
    from boardwatch.eligibility.facts import parse_facts, parse_policy
    from boardwatch.eligibility.final_gate import record_gate_verdict
    from boardwatch.eligibility.oracle import OracleVerdict
    from boardwatch.store.queries import current_posting_versions, get_profile

    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)

    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    catalog = load_rules(settings.config_dir)
    with engine.connect() as conn:
        versions = current_posting_versions(conn, [posting_id])
        profile_row = get_profile(conn)
    assert profile_row is not None
    facts = parse_facts(profile_row.eligibility_facts_json)
    policy = parse_policy(profile_row.eligibility_policy_json)
    current = versions[posting_id]
    # Plant a CURRENT gate row for this exact identity, as though a prior run already judged
    # it — the whole point of "never re-judge" is that this run must skip straight past it.
    with engine.begin() as conn:
        record_gate_verdict(
            conn,
            posting_version_id=current.posting_version_id,
            jd_text=current.body_text,
            facts=facts,
            policy=policy,
            catalog=catalog,
            verdict=OracleVerdict(
                label=str(posting_id), decision="eligible", reason=None, evidence="",
                confidence="high",
            ),
        )

    # If this ran, it would tell the fake to fail the WHOLE batch and the test would still
    # need to distinguish "never called" from "called and its one item excluded" — exit1
    # makes that unambiguous: any call at all would show up as gate_failed_open.
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")

    summary = _pipeline(env, tmp_path / "apps")

    assert not fake_claude.exists(), "a lead with a current gate row must never reach a request"
    assert summary.gate_judged == 0
    assert summary.gate_failed_open == 0
    assert posting_id in [lead.posting_id for lead in summary.tailored]
