"""CLI round-trip for the oracle-judge labeling handshake (P5b task 6).

`eligibility label request` mints a judge request from every unlabeled worksheet row,
`eligibility label apply` merges hand-written verdicts back into the worksheet in place
(preserving every other column), and `eligibility score` reports precision against the
resulting labeled set plus the mechanical audited-coverage drain (M1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app

runner = CliRunner()

JD = "About us. We are great. Active TS/SCI required. Apply now."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str]):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def _seed_worksheet(ws_dir: Path) -> None:
    ws_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "label": "skip/aud-1",
            "expected_verdict": None,
            "hint": "secret guess",
            "company": "Acme",
            "facts": {"total_years_experience": 1},
            "body_text": JD,
        },
        {
            "label": "applied/x",
            "expected_verdict": None,
            "facts": {},
            "body_text": JD,
        },
    ]
    (ws_dir / "candidates.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def test_label_request_writes_only_unlabeled_items(env: Path, tmp_path: Path) -> None:
    ws_dir = tmp_path / "worksheet"
    _seed_worksheet(ws_dir)
    req_path = tmp_path / "request.json"

    result = _run(
        env,
        ["eligibility", "label", "request", "--worksheet", str(ws_dir), "--out", str(req_path)],
    )
    assert result.exit_code == 0, result.stdout
    assert req_path.exists()

    payload = json.loads(req_path.read_text(encoding="utf-8"))
    assert len(payload["items"]) == 2
    assert {item["label"] for item in payload["items"]} == {"skip/aud-1", "applied/x"}
    assert "hint" not in payload["items"][0]  # independence: no prior guess leaks to judge
    assert payload["request_id"]
    assert payload["request_id"] in result.stdout
    assert "2 unlabeled" in result.stdout


def test_label_apply_fills_worksheet_and_preserves_columns(env: Path, tmp_path: Path) -> None:
    ws_dir = tmp_path / "worksheet"
    _seed_worksheet(ws_dir)
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(
        json.dumps(
            [
                {
                    "label": "skip/aud-1",
                    "decision": "ineligible",
                    "reason": "clearance",
                    "evidence": "Active TS/SCI required.",
                    "confidence": "high",
                },
                {
                    "label": "applied/x",
                    "decision": "ineligible",
                    "reason": "clearance",
                    "evidence": "Active TS/SCI required.",
                    "confidence": "high",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = _run(
        env,
        [
            "eligibility", "label", "apply",
            "--worksheet", str(ws_dir),
            "--verdicts", str(verdicts_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "labeled 2" in result.stdout
    # H1: applied/-prefixed hard negative accepted as ineligible is a WARNING, not silent.
    assert "applied/x" in result.stdout

    lines = (ws_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    by_label = {r["label"]: r for r in rows}
    assert by_label["skip/aud-1"]["expected_verdict"] == "ineligible"
    # M5: every other column survives the merge.
    assert by_label["skip/aud-1"]["hint"] == "secret guess"
    assert by_label["skip/aud-1"]["company"] == "Acme"
    assert by_label["applied/x"]["expected_verdict"] == "ineligible"


def test_score_reports_audited_coverage_warning_and_drains_on_unaudited_ineligible(
    env: Path, tmp_path: Path
) -> None:
    ws_dir = tmp_path / "worksheet"
    _seed_worksheet(ws_dir)
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(
        json.dumps(
            [
                {
                    "label": "skip/aud-1",
                    "decision": "ineligible",
                    "reason": "clearance",
                    "evidence": "Active TS/SCI required.",
                    "confidence": "high",
                },
                {
                    "label": "applied/x",
                    "decision": "ineligible",
                    "reason": "clearance",
                    "evidence": "Active TS/SCI required.",
                    "confidence": "high",
                },
            ]
        ),
        encoding="utf-8",
    )
    apply_result = _run(
        env,
        [
            "eligibility", "label", "apply",
            "--worksheet", str(ws_dir),
            "--verdicts", str(verdicts_path),
        ],
    )
    assert apply_result.exit_code == 0, apply_result.stdout

    result = _run(env, ["eligibility", "score", "--worksheet", str(ws_dir)])
    assert "audited: 0%" in result.stdout
    assert "NOT integrity-anchored; run the audit before shipping B1-B4" in result.stdout
    # M1: at least one reference-ineligible label + unmet ship gate (0% audited) -> exit 1.
    assert result.exit_code == 1


def test_label_request_missing_worksheet_dir_errors_loudly(env: Path, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = _run(
        env,
        ["eligibility", "label", "request", "--worksheet", str(missing)],
    )
    assert result.exit_code != 0
    # rich may hard-wrap a long path across lines in a non-tty test runner; newlines carry
    # no content of their own, so stripping them before the substring check is safe.
    flattened = result.stdout.replace("\n", "")
    assert "worksheet directory not found" in flattened
    assert str(missing) in flattened


def test_score_missing_worksheet_dir_errors_loudly(env: Path, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = _run(env, ["eligibility", "score", "--worksheet", str(missing)])
    assert result.exit_code != 0
    flattened = result.stdout.replace("\n", "")
    assert "worksheet directory not found" in flattened
    assert str(missing) in flattened
