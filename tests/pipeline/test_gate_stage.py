"""T42 red-first tests: the headless final-eligibility-gate judge stage on the daily path.

Every test drives a fake `claude` on PATH — real headless claude is never invoked from the
suite. The fake MUST NOT read stdin (a stdin-reading fake would hang the suite forever); it
exits immediately, reading its canned behaviour from environment variables the test sets.

Fails open at every seam (D-074): the fake's failure modes below (`exit1`, `garbage`) each
drop exactly one BATCH's verdicts and must never make the run fatal or drop a real lead from
the slate. `wrongcount` answers ONE lead of the batch: the answered lead is judged and the
rest stay unjudged on the slate — a skipped lead fails open, a batch that skipped one does
not (runs 45 and 48 each lost 13 leads to a 12-verdict answer before this).

The `fenced` mode is NOT a failure mode -- it is the shape real headless haiku actually
returned on run 4, and it must be JUDGED, not failed open. It exists because this fake
returned bare `json.dumps(verdicts)` and therefore modelled a response the live model does
not reliably produce, which is how an armed judge reached production judging nothing.
"""

from __future__ import annotations

import json
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

if mode == "empty":
    verdicts = []
elif mode == "wrongcount":
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
    # 0-B (D-489): a judge `eligible` now RELEASES the two requirement holds, so with this mode's
    # default a review-lane lead in the same batch is promoted out of review. A caller that needs
    # the lead to stay held names it here -- `uncertain` is a real gate outcome (run 9 judged 37:
    # 31 eligible, 1 ineligible, 5 uncertain) and it is the one that clears nothing.
    unsure = os.environ.get("GATE_FAKE_UNCERTAIN_LABEL")
    evidence = os.environ.get("GATE_FAKE_EVIDENCE", "")
    verdicts = []
    for l in labels:
        if l == target:
            verdicts.append({"label": l, "decision": "ineligible", "reason": "work_auth",
                              "evidence": evidence, "confidence": "high"})
        elif l == unsure:
            verdicts.append({"label": l, "decision": "uncertain", "reason": None,
                              "evidence": "", "confidence": "low"})
        else:
            verdicts.append({"label": l, "decision": "eligible", "reason": None,
                              "evidence": "", "confidence": "high"})
else:
    verdicts = [
        {"label": l, "decision": "eligible", "reason": None, "evidence": "",
         "confidence": "high"}
        for l in labels
    ]

seniority = os.environ.get("GATE_FAKE_SENIORITY")
if seniority:
    for verdict in verdicts:
        verdict["seniority_fit"] = seniority

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


def _arm_gate(
    data_dir: Path,
    *,
    batch_size: int = 13,
    model: str = "sonnet",
    seniority_hold: bool = False,
) -> None:
    config_dir = load_settings(data_dir=data_dir).config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        f"[gate]\nenabled = true\nmodel = \"{model}\"\nbatch_size = {batch_size}\n"
        f"call_timeout_s = 30\nseniority_hold = {str(seniority_hold).lower()}\n",
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

    **The one-posting path is no longer a hole to dodge: T131 made a valid gate rejection an
    explainer of the empty-day guard**, and `tests/pipeline/test_zero_output_guard.py` covers it
    directly. The second posting stays because it is what points this test at the COHORT guard,
    which is still the thing it was written to pin — not because the other path is unsafe.
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


@_needs_an_executable_fake
def test_a_slate_the_gate_rejected_ENTIRELY_is_not_an_empty_day(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T131, end to end: ONE posting, validly rejected, so the slate empties.

    This is the path the test above was given a second posting to avoid. The empty-day guard
    subtracted handled/applied/duplicate/dead but not gate exclusions, so a run where the judge
    worked perfectly went FATAL — which also withholds the heartbeat. A gate `ineligible`
    carrying a quoted span from the frozen JD is an honest suppression by the guard's own
    standard, and is now its fifth explainer.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "ineligible_span")
    monkeypatch.setenv("GATE_FAKE_TARGET_LABEL", str(posting_id))
    monkeypatch.setenv("GATE_FAKE_EVIDENCE", EVIDENCE)

    summary = _pipeline(env, tmp_path / "apps")

    assert fake_claude.exists(), "the gate never attempted a call"
    assert summary.gate_excluded_ids == [posting_id]
    assert not summary.tailored, "the only candidate was rejected, so nothing may be delivered"
    assert summary.fatal is None, (
        "a slate the judge validly emptied is not an unexplained empty day: " f"{summary.fatal}"
    )


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
    assert summary.gate_failed_open == 0, "a batch that answered some leads did not fail"
    assert summary.gate_judged == 1, "the one answered lead is judged on its own label"
    tailored_ids = [lead.posting_id for lead in summary.tailored]
    assert first in tailored_ids and second in tailored_ids
    partial = [e for e in summary.errors if "partly failed open" in e]
    assert len(partial) == 1, summary.errors
    assert "1 of 2 verdicts missing" in partial[0]


@_needs_an_executable_fake
def test_an_empty_verdict_array_fails_the_whole_batch_open(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[]` answers nobody. Label-keyed parsing (2026-09-12) would read it as "every label
    missing" and call the batch PARTIAL, leaving `failed_open_batches` at 0 — which silences the
    one alert whose job is to say the judge never ran. It must count as a failed batch."""
    _ready(env)
    first = _seed(env, slug="acme-gate-a")
    second = _seed(env, slug="acme-gate-b")
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "empty")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None
    assert summary.gate_failed_open == 1, "an empty answer is a failed batch, not a partial one"
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
    # Under `_arm_gate`'s own model, because a row naming a DIFFERENT judge (or none) is not
    # current either (T108), and this control is about the unchanged case.
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
            provider="claude-code-agent",
            model=settings.gate.model,
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


# ---------------------------------------------------------------------------
# (f) T63 — judge DEPTH: the judge sees more leads than the run tailors
# ---------------------------------------------------------------------------


def _arm_gate_with_depth(data_dir: Path, *, depth: int) -> None:
    config_dir = load_settings(data_dir=data_dir).config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        '[gate]\nenabled = true\nmodel = "sonnet"\nbatch_size = 13\n'
        f"call_timeout_s = 30\ndepth = {depth}\n",
        encoding="utf-8",
    )


def _dispositions(data_dir: Path) -> dict[int, str]:
    """`job_id -> disposition` for every row in the store. Read through the TABLE rather than
    through anything the runner returns: the claim under test is what the ledger holds, and a
    summary field would only re-report the code that wrote it."""
    from sqlalchemy import select

    engine = get_engine(data_dir)
    with engine.connect() as conn:
        return {
            int(row.job_id): str(row.disposition)
            for row in conn.execute(
                select(tables.job_dispositions.c.job_id, tables.job_dispositions.c.disposition)
            )
        }


def _job_of(data_dir: Path, posting_ids: list[int]) -> dict[int, int]:
    from boardwatch.store.regroup import job_anchors

    engine = get_engine(data_dir)
    with engine.connect() as conn:
        return job_anchors(conn, posting_ids)


def _depth_pipeline(data_dir: Path, out_root: Path, *, top_n: int):  # type: ignore[no-untyped-def]
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
    )


@_needs_an_executable_fake
def test_gate_depth_judges_deeper_than_the_run_tailors_and_queues_the_surplus(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T63. FIVE postings, `--top 2`, `gate.depth = 5`.

    The judge must see all five while the tailor sees two, and the three it did not deliver
    must leave NO trace in `job_dispositions` — not a `seen` row, not anything. A `seen` row
    would bury a lead nobody was ever shown for the whole TTL (D-103), which would make the
    verdict this run paid for unusable.

    RED against the pre-change runner on `summary.gate_judged == 5`: `depth` was not a field
    on `GateTier`, `Settings` drops an unknown `[gate]` key silently, and the ranker was called
    with `limit=top_n`, so the judge was handed 2.
    """
    _ready(env)
    ids = [_seed(env, slug=f"acme-depth-{n}") for n in range(5)]
    _arm_gate_with_depth(env, depth=5)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")  # every lead comes back `eligible`

    summary = _depth_pipeline(env, tmp_path / "apps", top_n=2)

    assert summary.fatal is None, summary.fatal
    assert summary.gate_judged == 5, "the judge must see the whole depth slate, not the shortlist"
    assert summary.gate_eligible == 5
    assert summary.gate_beyond_slate == 3
    delivered = [lead.posting_id for lead in summary.tailored]
    assert len(delivered) == 2, f"the tailor must see only --top, got {delivered}"

    # Exactly the two delivered jobs carry a row; the other three carry none AT ALL.
    anchors = _job_of(env, ids)
    dispositions = _dispositions(env)
    assert {anchors[pid] for pid in delivered} == set(dispositions), dispositions
    for posting_id in ids:
        if posting_id not in delivered:
            assert anchors[posting_id] not in dispositions, (
                f"posting {posting_id} was judged but never presented; it must carry no "
                f"disposition, or it is buried for the seen TTL"
            )

    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["reconciles"] is True, [
        (stage["name"], stage) for stage in payload["stages"] if stage.get("reconciled") is False
    ]
    assert payload["gate"]["judged"] == 5
    assert payload["gate"]["beyond_slate"] == 3

    # ---- second run, same store, same stub: the surplus is a QUEUE, not a re-judge.
    summary2 = _depth_pipeline(env, tmp_path / "apps2", top_n=2)

    assert summary2.fatal is None, summary2.fatal
    assert summary2.gate_judged == 0, "a lead with a current gate row must never be re-judged"
    queued = set(ids) - set(delivered)
    delivered2 = {lead.posting_id for lead in summary2.tailored}
    assert len(delivered2) == 2
    assert delivered2 <= queued, (
        "run 2 must deliver leads run 1 judged and did not tailor — that is the queue"
    )
    for posting_id in delivered2:
        assert _current_gate_verdict(env, posting_id) == "eligible"
    assert summary2.gate_beyond_slate == 1  # three queued, two delivered


@_needs_an_executable_fake
def test_gate_depth_never_judges_a_lead_liveness_withheld(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The depth slate is liveness-checked BEFORE it is judged, so seat time is never spent on
    a posting that has already 404'd. The whole slate is probed (five), and the judge is handed
    what survived (four).

    RED against the pre-change runner on `summary.liveness_checked == 5`: it probed `top_n`
    leads, so this read 2.
    """
    from boardwatch.core.liveness import Liveness

    _ready(env)
    ids = [_seed(env, slug=f"acme-live-{n}") for n in range(5)]
    _arm_gate_with_depth(env, depth=5)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    dead_id = ids[0]

    def probe(posting_id: int, url: str) -> Liveness:
        if posting_id == dead_id:
            return Liveness(posting_id, "dead", "refetch_gone", "HTTP 404")
        return Liveness(posting_id, "alive", "refetch_ok", "HTTP 200")

    settings = load_settings(data_dir=env)
    summary = run_pipeline(
        get_engine(env),
        settings,
        console=Console(quiet=True),
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=2,
        liveness_prober=probe,
    )

    assert summary.fatal is None, summary.fatal
    assert summary.liveness_checked == 5, "the DEPTH slate is what gets probed, not the shortlist"
    assert summary.liveness_dead == 1
    assert summary.gate_judged == 4, "a withheld lead must never cost a judge call"
    assert _current_gate_verdict(env, dead_id) is None
    assert summary.gate_beyond_slate == 2  # four alive, two delivered


def _persisted_ranks(data_dir: Path) -> dict[int, int | None]:
    """Each judged posting id -> the `shortlist_rank` its gate row recorded (None = absent).

    Read through `raw_output_json` because that is where the rank lives; a rank in `score`
    would mean the column's documented meaning (the engine's confidence) had been overloaded.
    """
    from sqlalchemy import func, select

    from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX

    engine = get_engine(data_dir)
    ranks: dict[int, int | None] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                tables.posting_versions.c.posting_id,
                func.json_extract(
                    tables.eligibility_evaluations.c.raw_output_json, "$.shortlist_rank"
                ),
            )
            .select_from(tables.eligibility_evaluations)
            .join(
                tables.eligibility_inputs,
                tables.eligibility_inputs.c.id == tables.eligibility_evaluations.c.input_id,
            )
            .join(
                tables.posting_versions,
                tables.posting_versions.c.id
                == tables.eligibility_inputs.c.posting_version_id,
            )
            .where(
                tables.eligibility_evaluations.c.engine_version.like(
                    f"{GATE_VERSION_PREFIX}%"
                )
            )
        ).all()
    for posting_id, rank in rows:
        ranks[int(posting_id)] = None if rank is None else int(rank)
    return ranks


@_needs_an_executable_fake
def test_the_gate_row_records_the_leads_shortlist_rank(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T72. Every judged lead's gate row carries its 1-based rank in the depth slate, so
    conversion can be read BY RANK BAND — the measurement D-493's addendum found impossible
    because `score` is NULL on every judge row and no table carried a rank.

    RED against the pre-change code on `set(ranks.values()) == {1, 2, 3, 4, 5}`: it recorded
    no rank at all, so every value read `None`.
    """
    _ready(env)
    ids = [_seed(env, slug=f"acme-rank-{n}") for n in range(5)]
    _arm_gate_with_depth(env, depth=5)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _depth_pipeline(env, tmp_path / "apps", top_n=2)

    assert summary.fatal is None, summary.fatal
    assert summary.gate_judged == 5
    ranks = _persisted_ranks(env)
    assert set(ranks) == set(ids), "every judged lead owes a rank, not just the delivered ones"
    assert set(ranks.values()) == {1, 2, 3, 4, 5}, (
        f"a depth-5 slate must record ranks 1..5 exactly once each, got {ranks}"
    )


@_needs_an_executable_fake
def test_the_recorded_rank_is_the_rankers_own_and_not_a_post_liveness_index(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rank is captured off `ranked.visible`, BEFORE the liveness sweep removes anything.

    This is the whole reason `run_gate_stage` takes the map from its caller instead of
    enumerating the `leads` list it is handed: by then the sweep has already dropped the dead
    postings, so an index taken there is short of the true rank by however many leads above it
    were withheld — and it would silently renumber the survivors into a gapless 1..4.

    RED against an implementation that enumerates inside the gate stage on
    `sorted(ranks.values()) != [1, 2, 3, 4]`: the withheld lead's rank must be MISSING from
    the survivors' ranks, not closed up.
    """
    from boardwatch.core.liveness import Liveness

    _ready(env)
    ids = [_seed(env, slug=f"acme-rankgap-{n}") for n in range(5)]
    _arm_gate_with_depth(env, depth=5)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    dead_id = ids[0]

    def probe(posting_id: int, url: str) -> Liveness:
        if posting_id == dead_id:
            return Liveness(posting_id, "dead", "refetch_gone", "HTTP 404")
        return Liveness(posting_id, "alive", "refetch_ok", "HTTP 200")

    settings = load_settings(data_dir=env)
    summary = run_pipeline(
        get_engine(env),
        settings,
        console=Console(quiet=True),
        out_root=tmp_path / "apps",
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=2,
        liveness_prober=probe,
    )

    assert summary.fatal is None, summary.fatal
    assert summary.gate_judged == 4
    ranks = _persisted_ranks(env)
    assert dead_id not in ranks, "a withheld lead is never judged, so it owes no gate row"
    assert sorted(ranks.values()) != [1, 2, 3, 4], (
        "the survivors were renumbered 1..4, which means the rank was taken AFTER the "
        f"liveness sweep instead of off the ranker's own slate: {ranks}"
    )
    assert set(ranks.values()) < {1, 2, 3, 4, 5}
    assert len(set(ranks.values())) == 4, f"ranks must stay distinct: {ranks}"


# ---------------------------------------------------------------------------
# (i) a SUPERSEDED gate row is not "already judged" — D-512
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_gate_rejudges_a_lead_whose_only_gate_row_is_a_superseded_policy(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The converse of (e), and the case that shipped broken.

    `run_gate_stage`'s never-re-judge filter used to share the DISPLAY read, which matches
    `engine_version LIKE 'final_gate:%'`. So a row written under a superseded
    `oracle.POLICY_VERSION` counted as already judged and the lead could never be re-judged —
    `p5-oracle-2` added `seniority_fit` on 2026-09-13 and 434 of 505 standing apply-lane leads
    were still holding `p5-oracle-1` rows, reading `unclear` forever. The freshness test is now
    keyed on the EXACT `gate_engine_version()`, so a superseded row no longer blocks a re-judge
    while staying readable everywhere else.
    """
    from boardwatch.eligibility import final_gate as final_gate_mod
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

    stale_version = f"{final_gate_mod.GATE_VERSION_PREFIX}p5-oracle-0:p5-oracle-1"
    with monkeypatch.context() as patched:
        # Plant the row as a PRIOR POLICY would have written it. Patched on `final_gate` rather
        # than `oracle` because `gate_engine_version` closes over this module's own binding.
        patched.setattr(final_gate_mod, "POLICY_VERSION", "p5-oracle-0")
        assert final_gate_mod.gate_engine_version() == stale_version
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
    assert final_gate_mod.gate_engine_version() != stale_version, "patch must not leak"

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert fake_claude.exists(), (
        "a lead whose only gate row is a SUPERSEDED policy must reach a request — sharing the "
        "prefix-matched display read here is what stranded 434 leads on p5-oracle-1"
    )
    assert summary.gate_judged == 1, summary.gate_judged

    # And the superseded row stays readable: the DISPLAY read is unchanged, still prefix-matched.
    assert _current_gate_verdict(env, posting_id) is not None


# ---------------------------------------------------------------------------
# (j) the freshness check must see every fact the JUDGE reads — T99
# ---------------------------------------------------------------------------


def _store_eligibility(data_dir: Path, *, work_auth_status: str) -> None:
    """Pin the stored profile to `work_auth: ignore` plus one work-authorization status.

    `ignore` is the whole point: `hashing.build_identity` folds a family's declared fields
    into `profile_hash` only while its severity is not `"ignore"`, so under this policy the
    status below is INVISIBLE to the gate row's key — while `build_gate_request` still sends
    it to the judge, which reads it under an all-blocker policy (D-461).
    """
    from boardwatch.store.queries import save_eligibility

    with get_engine(data_dir).begin() as conn:
        save_eligibility(
            conn,
            facts_json={"work_authorization": {"status": work_auth_status}},
            policy_json={"families": {"work_auth": "ignore"}},
        )


def _plant_current_gate_row(
    data_dir: Path, posting_id: int, *, model: str | None = None
) -> None:
    """One `eligible` gate row at the CURRENT engine_version, under whatever facts+policy
    the store holds right now. `model` names the judge that wrote it; the default `None` is
    the LEGACY shape, which every row written before T108 has and no backfill can change —
    the ledger is append-only."""
    from boardwatch.eligibility.catalog import load_rules
    from boardwatch.eligibility.facts import parse_facts, parse_policy
    from boardwatch.eligibility.final_gate import record_gate_verdict
    from boardwatch.eligibility.oracle import OracleVerdict
    from boardwatch.store.queries import current_posting_versions, get_profile

    settings = load_settings(data_dir=data_dir)
    engine = get_engine(data_dir)
    catalog = load_rules(settings.config_dir)
    with engine.connect() as conn:
        current = current_posting_versions(conn, [posting_id])[posting_id]
        profile_row = get_profile(conn)
    assert profile_row is not None
    with engine.begin() as conn:
        record_gate_verdict(
            conn,
            posting_version_id=current.posting_version_id,
            jd_text=current.body_text,
            facts=parse_facts(profile_row.eligibility_facts_json),
            policy=parse_policy(profile_row.eligibility_policy_json),
            catalog=catalog,
            verdict=OracleVerdict(
                label=str(posting_id), decision="eligible", reason=None, evidence="",
                confidence="high",
            ),
            provider=None if model is None else "claude-code-agent",
            model=model,
        )


@_needs_an_executable_fake
def test_gate_rejudges_when_a_fact_the_judge_reads_changed_under_an_ignored_family(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cache contract, and it was broken in the direction that clears a barred lead.

    Under `Policy(families={"work_auth": "ignore"})` the row identity cannot see
    `work_authorization.status` at all, but the judge is sent every fact. So `citizen` ->
    `needs_sponsorship` left `(posting_version_id, profile_hash, rules_hash, engine_kind,
    engine_version)` byte-identical while changing the request — and a clear the judge gave a
    citizen on a no-sponsorship JD stayed "already judged" forever after the fact that decides
    it moved. `raw_output.facts_key` digests the exact payload the judge is sent, and the
    freshness read now requires it to match.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    _store_eligibility(env, work_auth_status="citizen")
    _plant_current_gate_row(env, posting_id, model="sonnet")
    # The one line that differs from the control below.
    _store_eligibility(env, work_auth_status="needs_sponsorship")
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert fake_claude.exists(), (
        "a lead whose judge-visible facts changed must reach a request — the row identity "
        "drops every family the live policy ignores, so it cannot see this on its own"
    )
    assert summary.gate_judged == 1, summary.gate_judged


def test_gate_still_never_rejudges_when_the_judge_visible_facts_are_unchanged(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL for the test above, green before and after: identical setup minus the fact
    change. The facts key must not defeat the never-re-judge filter (D-477 pt 5) — a run that
    re-judged an unchanged lead would spend a `claude` call per lead per day forever.

    `exit1` so a call cannot be mistaken for a skip: any call at all surfaces as
    `gate_failed_open`.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    _store_eligibility(env, work_auth_status="citizen")
    _plant_current_gate_row(env, posting_id, model="sonnet")
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")

    summary = _pipeline(env, tmp_path / "apps")

    assert not fake_claude.exists(), "an unchanged lead must never reach a request"
    assert summary.gate_judged == 0
    assert summary.gate_failed_open == 0


# ---------------------------------------------------------------------------
# (k) the freshness check must see WHICH MODEL judged the row — T108
# ---------------------------------------------------------------------------


def _persisted_judge(data_dir: Path) -> set[tuple[str | None, str | None]]:
    """Every gate row's `(provider, model)` pair, read from the columns that hold them."""
    from sqlalchemy import select

    from boardwatch.eligibility.final_gate import GATE_VERSION_PREFIX

    with get_engine(data_dir).connect() as conn:
        rows = conn.execute(
            select(
                tables.eligibility_evaluations.c.provider,
                tables.eligibility_evaluations.c.model,
            ).where(
                tables.eligibility_evaluations.c.engine_version.like(f"{GATE_VERSION_PREFIX}%")
            )
        ).all()
    return {(row.provider, row.model) for row in rows}


@_needs_an_executable_fake
def test_gate_rejudges_a_lead_whose_gate_row_names_no_model(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every row written before this shipped has `model IS NULL`, and the ledger is
    append-only — there is no backfill. So the FIRST run after this lands re-judges the
    standing slate once (bounded by `--top`, D-477 pt 1) and comes back keyed. This is also
    the only test that can see `run_gate_stage` passing a model at all: with the argument
    dropped, a null-model row would still read as fresh.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    _store_eligibility(env, work_auth_status="citizen")
    _plant_current_gate_row(env, posting_id)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert fake_claude.exists(), (
        "a gate row that names no model can never be attributed to the configured judge, "
        "so it must not count as already judged"
    )
    assert summary.gate_judged == 1, summary.gate_judged


@_needs_an_executable_fake
def test_gate_rejudges_a_lead_whose_gate_row_was_judged_by_a_different_model(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case that made a judge switch reach NEW leads only.

    Nothing the freshness read compared moved with `settings.gate.model`: the row identity is
    `(posting_version_id, profile_hash, rules_hash)`, `gate_engine_version()` carries the policy
    and prompt versions, and `facts_key` digests the judge's request. The run manifest's
    `config_hash` does move — `_GATE_RELEVANT` includes `model` — but a `config_hash` invalidates
    no gate row, so every lead the old judge cleared stayed "fresh" under the new one forever.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    _store_eligibility(env, work_auth_status="citizen")
    _plant_current_gate_row(env, posting_id, model="sonnet")
    # The one line that differs from the control below.
    _arm_gate(env, model="haiku")
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert fake_claude.exists(), (
        "a lead whose only gate row was judged by a DIFFERENT model must reach a request — "
        "otherwise a judge switch reaches new leads only and the migration is silently partial"
    )
    assert summary.gate_judged == 1, summary.gate_judged


def test_gate_still_never_rejudges_when_the_configured_model_is_unchanged(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL for the test above: identical setup minus the model change. The model narrowing
    must not defeat the never-re-judge filter (D-477 pt 5) — a run that re-judged an unchanged
    lead would spend a `claude` call per lead per day forever.

    `exit1` so a call cannot be mistaken for a skip: any call at all surfaces as
    `gate_failed_open`.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    _store_eligibility(env, work_auth_status="citizen")
    _plant_current_gate_row(env, posting_id, model="sonnet")
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")

    summary = _pipeline(env, tmp_path / "apps")

    assert not fake_claude.exists(), "an unchanged lead must never reach a request"
    assert summary.gate_judged == 0
    assert summary.gate_failed_open == 0


@_needs_an_executable_fake
def test_a_gate_row_records_the_provider_and_model_that_judged_it(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-row provenance, in the two columns that already existed for it and sat empty:
    without it there is no way to audit which judge decided which lead across a switch."""
    _ready(env)
    _seed(env)
    _arm_gate(env, model="haiku")
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert summary.gate_judged == 1, summary.gate_judged
    assert _persisted_judge(env) == {("claude-code-agent", "haiku")}


# ---------------------------------------------------------------------------
# (l) T107 — item- and field-level coverage, and a PARTIAL outage that escalates
#
# Run 467 (2026-09-19, the live 04:00 tick) recorded `batch 5/7 partly failed open, 1 of 13
# verdicts missing (label 302235)`. `gate_failed_open` stayed 0, the note was appended at the
# GATE stage — below `escalatable_from` — and so the only artifact that carried it was the
# morning digest. Posting 302235 is still open, still deterministic `uncertain`, and carries
# zero gate rows. Nothing alerted.
# ---------------------------------------------------------------------------


def _escalated(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Captures the ESCALATION SLICE — `summary.errors[escalatable_from:]`. `escalatable_from`
    is a local in `run_pipeline` and the slice is observable nowhere else, so a spy on
    `escalate_alerts` is the only way to assert an alert is ABOVE the mark rather than merely
    somewhere in `summary.errors` (where every routine stage error also lands)."""
    import boardwatch.pipeline.runner as runner_mod

    captured: list[tuple[str, ...]] = []

    def spy(run_id: int, alerts: tuple[str, ...], **_k: object) -> None:
        captured.append(tuple(alerts))
        return None

    monkeypatch.setattr(runner_mod, "escalate_alerts", spy)
    return captured


def _funnel_gate(summary: object) -> dict[str, object]:
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    gate: dict[str, object] = payload["gate"]
    return gate


@_needs_an_executable_fake
def test_a_one_of_thirteen_answer_raises_one_item_coverage_alert_the_owner_can_see(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run 467's exact shape: a batch of 13 answered once.

    Twelve leads come back with no verdict at all, and today that costs ONE note appended at
    the gate stage — below `escalatable_from`, so it reaches the digest and stops. The
    whole-batch counter stays 0 because `batch_verdicts is not None`.
    """
    _ready(env)
    ids = [_seed(env, slug=f"acme-partial-{n}") for n in range(13)]
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "wrongcount")
    escalated = _escalated(monkeypatch)

    summary = _depth_pipeline(env, tmp_path / "apps", top_n=13)

    assert summary.fatal is None, summary.fatal
    assert summary.gate_candidates == 13
    assert summary.gate_sent == 13
    assert summary.gate_judged == 1
    assert summary.gate_missing_items == 12
    assert summary.gate_failed_open == 0, "a partly answered batch is not a failed batch"
    # Every lead survives: the judge cleared one and answered for none of the other twelve.
    assert summary.gate_excluded_ids == []
    assert {lead.posting_id for lead in summary.tailored} == set(ids)

    coverage = [error for error in summary.errors if "came back with no verdict" in error]
    assert len(coverage) == 1, summary.errors
    assert "12 of 13" in coverage[0], coverage[0]
    assert escalated, "escalation never ran"
    assert coverage[0] in escalated[-1], (
        "the coverage alert is below `escalatable_from`, exactly where run 467's note was"
    )
    assert summary.morning is not None
    digest = summary.morning.markdown_path.read_text(encoding="utf-8")
    assert "came back with no verdict" in digest

    gate = _funnel_gate(summary)
    assert gate["sent"] == 13
    assert gate["missing_items"] == 12


def test_every_lead_already_current_sends_nothing_and_that_is_not_a_coverage_failure(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sent == 0` ABSTAINS. Zero fresh judgments is ambiguous today — an all-cache run and a
    missing prerequisite produce identical zeros — so the funnel has to say which it was."""
    _ready(env)
    ids = [_seed(env, slug=f"acme-cached-{n}") for n in range(2)]
    _arm_gate(env)
    _store_eligibility(env, work_auth_status="citizen")
    for posting_id in ids:
        _plant_current_gate_row(env, posting_id, model="sonnet")
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")  # any call at all would be an obvious tell
    escalated = _escalated(monkeypatch)

    summary = _depth_pipeline(env, tmp_path / "apps", top_n=13)

    assert not fake_claude.exists(), "a fully cached slate must never reach a request"
    assert summary.gate_candidates == 2
    assert summary.gate_cached == 2
    assert summary.gate_sent == 0
    assert summary.gate_missing_items == 0
    assert not [error for error in summary.errors if "came back with no verdict" in error]
    assert escalated and not [alert for alert in escalated[-1] if alert.startswith("gate:")]

    gate = _funnel_gate(summary)
    assert gate["instrumented"] is True, "the gate WAS armed — that is not the disarmed case"
    assert gate["cached"] == 2
    assert gate["sent"] == 0
    body = summary.funnel.markdown_path.read_text(encoding="utf-8")
    assert "nothing was sent to the judge" in body, (
        "the funnel must distinguish 'nothing was due' from 'the judge answered nothing'"
    )


@_needs_an_executable_fake
def test_a_seniority_field_absent_from_every_answer_raises_a_field_coverage_alarm(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure that reads as a wholly successful run: every `seniority_fit` absent.

    `_seniority_fit` folds an absent answer to `"unclear"`, which holds nothing and is also
    what a judge that genuinely could not tell returns — so a systematic omission of the field
    that drives the seniority hold produces no signal whatsoever. The fake omits the field by
    default, which is exactly the pre-`p5-oracle-2` judge's shape.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env, seniority_hold=True)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    escalated = _escalated(monkeypatch)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert summary.gate_judged == 1
    assert summary.gate_seniority_unreadable == 1
    assert summary.gate_seniority_unclear == 0, "an absent answer is not an explicit `unclear`"
    assert summary.gate_seniority_answered == 0
    # No hold: the reading still fails safe, which is why this is invisible without the alarm.
    assert posting_id in [lead.posting_id for lead in summary.tailored]

    alarm = [error for error in summary.errors if "seniority_fit" in error]
    assert len(alarm) == 1, summary.errors
    assert escalated and alarm[0] in escalated[-1]
    assert summary.morning is not None
    assert "seniority_fit" in summary.morning.markdown_path.read_text(encoding="utf-8")


@_needs_an_executable_fake
def test_the_seniority_alarm_is_silent_when_the_hold_is_not_armed(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL. With `gate.seniority_hold` off the field drives nothing — `delivery_queries`
    leaves the column inert — so an unreadable answer costs nothing and must not alarm. The
    counter still records it: the measurement is unconditional, only the alert is gated."""
    _ready(env)
    _seed(env)
    _arm_gate(env)  # seniority_hold defaults False
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.gate_seniority_unreadable == 1
    assert not [error for error in summary.errors if "seniority_fit" in error], summary.errors


@_needs_an_executable_fake
def test_an_explicit_unclear_is_a_real_answer_and_is_never_counted_malformed(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL, and the reason the split is three-way rather than two-way.

    Of 1,999 stored gate verdicts, 215 carry an explicit `"unclear"`. Counting those as a
    parse failure would report a real answer as malformed on a seventh of the corpus and
    would fire this alarm on a judge doing exactly what it was asked.
    """
    _ready(env)
    _seed(env)
    _arm_gate(env, seniority_hold=True)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    monkeypatch.setenv("GATE_FAKE_SENIORITY", "unclear")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.gate_judged == 1
    assert summary.gate_seniority_unclear == 1
    assert summary.gate_seniority_unreadable == 0
    assert not [error for error in summary.errors if "seniority_fit" in error], summary.errors


@_needs_an_executable_fake
def test_a_clean_batch_raises_neither_alert_and_leaves_the_existing_gate_numbers_intact(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL. Every item answered, every `seniority_fit` in catalog, the hold armed: no
    coverage alert, no field alarm, and the six gate numbers the funnel already published
    read exactly what they read before this instrumentation existed."""
    _ready(env)
    _seed(env)
    _arm_gate(env, seniority_hold=True)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    monkeypatch.setenv("GATE_FAKE_SENIORITY", "yes")
    escalated = _escalated(monkeypatch)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert not [error for error in summary.errors if "came back with no verdict" in error]
    assert not [error for error in summary.errors if "seniority_fit" in error]
    assert escalated and not [alert for alert in escalated[-1] if alert.startswith("gate:")]

    gate = _funnel_gate(summary)
    assert {key: gate[key] for key in (
        "judged", "eligible", "ineligible", "uncertain", "failed_open_batches", "beyond_slate",
    )} == {
        "judged": 1, "eligible": 1, "ineligible": 0, "uncertain": 0,
        "failed_open_batches": 0, "beyond_slate": 0,
    }
    assert gate["seniority_answered"] == 1
    assert gate["seniority_unclear"] == 0
    assert gate["seniority_unreadable"] == 0
    assert gate["missing_items"] == 0
    assert gate["refused_items"] == 0


# ---------------------------------------------------------------------------
# (l) T151 — the gate reading going BLIND is now reported
# ---------------------------------------------------------------------------
#
# D-537's finding had no instrument. A stored gate row is scoped on `profile_hash` AND
# `rules_hash` and the read FAILS OPEN, so a re-key does not merely fail to add a hold -- it
# RELEASES every hold those rows carried, silently. 117 leads were measured moving out of
# `_review` into the apply lane that way and no run reported it. `gate.readings_absent` is the
# count, taken at the lane split beside the read it describes.


@_needs_an_executable_fake
def test_a_run_whose_gate_readings_are_all_absent_reports_and_alarms(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE NON-ZERO ARM. A lead reaching the apply lane with no readable gate reading.

    The judge is made unavailable, so the gate stage writes no row and the lane split's read
    finds nothing — the same observable state a catalog re-key produces, which is the state
    D-537 measured and which nothing reported.
    """
    _ready(env)
    posting_id = _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")
    escalated = _escalated(monkeypatch)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert posting_id in [lead.posting_id for lead in summary.tailored]
    # The COUNT, and it is the whole claim.
    assert summary.gate_readings_absent == 1
    alarm = [error for error in summary.errors if "no readable gate reading" in error]
    assert len(alarm) == 1, summary.errors
    assert escalated and alarm[0] in escalated[-1]


@_needs_an_executable_fake
def test_a_healthy_run_reports_zero_absent_gate_readings_and_stays_silent(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE ZERO ARM, and it is not optional: a counter only ever seen non-zero is untested.

    The gate judges the lead, so the lane split -- which runs AFTER the gate stage -- finds a
    readable row under the live identity. This is also the proof that the healthy path is silent:
    the alert must not fire on every run, or it is noise rather than a signal.
    """
    _ready(env)
    _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert summary.gate_judged == 1
    assert summary.gate_readings_absent == 0
    assert not [e for e in summary.errors if "no readable gate reading" in e], summary.errors


@_needs_an_executable_fake
def test_the_gate_staleness_alarm_reaches_the_MORNING_DIGEST(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE POSITION PIN. Asserting on `summary.errors` cannot discriminate.

    Every soft alert in the finalize block must sit ABOVE `_emit_morning` (D-477 point 7):
    below it the alert still fires and is still recorded in `summary.errors`, but is invisible
    in the one artifact an unattended owner actually reads. Only the RENDERED digest can tell
    the two apart, which is why this reads the file.
    """
    _ready(env)
    _seed(env)
    _arm_gate(env)
    monkeypatch.setenv("GATE_FAKE_MODE", "exit1")

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.morning is not None
    digest = summary.morning.markdown_path.read_text(encoding="utf-8")
    assert "no readable gate reading" in digest


@_needs_an_executable_fake
def test_the_staleness_alarm_is_silent_when_the_gate_is_not_armed(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL. With `gate.enabled` false NOTHING writes gate rows, so absence is the expected
    state rather than a fault and must not alarm — the same shape as the seniority control.

    The COUNT is still taken: the measurement is unconditional and only the alert is gated, so a
    disarmed run still records how many leads carry no reading.
    """
    _ready(env)
    _seed(env)
    # deliberately NOT armed

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.gate_readings_absent >= 1
    assert not [e for e in summary.errors if "no readable gate reading" in e], summary.errors
