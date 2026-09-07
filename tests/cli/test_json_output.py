"""`--json` on the read commands: one JSON object on stdout, everything readable on stderr.

The property under test is the pipe contract `boardwatch guide` states, not the shape of any one
payload: `json.loads(result.stdout)` on the WHOLE of stdout is the assertion, so a preflight
notice, a "nothing tracked yet" or a next-step hint leaking onto stdout fails the test by itself.
The human path is run beside each one so adding the flag changed nothing for a person.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import insert, update
from typer.testing import CliRunner, Result

from boardwatch.cli.app import app
from boardwatch.cli.profile_cmd import persist_profile
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import companies, jobs, postings, profile

NOW = utcnow()
runner = CliRunner()


@pytest.fixture()
def empty_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    ensure_schema(get_engine(data))
    return data


@pytest.fixture()
def store(empty_store: Path) -> tuple[Path, int]:
    """A profile, one watched board, one open posting, and one tracked application on it."""
    eng = get_engine(empty_store)
    settings = load_settings(data_dir=empty_store)
    persist_profile(
        eng,
        settings,
        text="python engineer",
        target_titles=[],
        exclude_titles=[],
        locations=[],
        remote_only=False,
    )
    with eng.begin() as conn:
        company = int(
            conn.execute(
                insert(companies).values(
                    name="Acme",
                    provider="greenhouse",
                    slug="acme",
                    source="user",
                    watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company,
                    job_id=job_id,
                    provider_posting_id="p1",
                    title="Python Engineer",
                    normalized_title="python engineer",
                    url="https://example.test/p1",
                    locations_json=["Remote"],
                    remote_policy="remote",
                    posted_at=NOW,
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                    status="open",
                    consecutive_missing=0,
                    content_hash="p1",
                    body_text="We hire python engineers.",
                )
            ).inserted_primary_key[0]
        )
    eng.dispose()
    added = _cli(empty_store, ["track", "add", str(posting_id)])
    assert added.exit_code == 0, added.output
    return empty_store, posting_id


def _cli(data_dir: Path, args: list[str]) -> Result:
    return runner.invoke(app, ["--data-dir", str(data_dir), *args])


def _json(data_dir: Path, args: list[str]) -> dict[str, Any]:
    result = _cli(data_dir, [*args, "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    ("args", "key"),
    [
        (["stats"], "qualified"),
        (["track", "list"], "rows"),
        (["track", "log", "1"], "rows"),
        (["companies", "list"], "rows"),
        (["profile", "show"], "skills"),
        (["ledger", "show"], "rows"),
        (["config", "show"], "llm.enabled"),
        # The `--json` surfaces that predate this branch. `top` is deliberately absent: it is
        # the one command that emits a bare array, which the guide's json section now says.
        (["coverage"], "bucket_counts"),
        (["seeds"], "unresolved"),
        (["identities", "leakage"], "window_days"),
    ],
)
def test_json_is_the_whole_of_stdout_and_the_human_path_still_works(
    store: tuple[Path, int], args: list[str], key: str
) -> None:
    data_dir, _ = store
    payload = _json(data_dir, args)
    assert key in payload, payload
    human = _cli(data_dir, args)
    assert human.exit_code == 0, human.output
    with pytest.raises(json.JSONDecodeError):
        json.loads(human.stdout)


def test_show_json_carries_the_posting_the_score_the_gates_and_the_audit(
    store: tuple[Path, int],
) -> None:
    data_dir, posting_id = store
    payload = _json(data_dir, ["show", str(posting_id)])
    assert payload["posting"]["title"] == "Python Engineer"
    assert payload["posting"]["company"] == "Acme"
    assert "components" in payload["score"]
    assert set(payload["gates"]) == {"role", "signal", "band", "hard_filter"}
    assert "eligibility" in payload and "llm_eligibility" in payload
    assert payload["body_text"] == "We hire python engineers."
    human = _cli(data_dir, ["show", str(posting_id)])
    assert human.exit_code == 0 and "Score" in human.stdout


def test_track_list_rows_and_log_events_are_real_rows(store: tuple[Path, int]) -> None:
    data_dir, posting_id = store
    rows = _json(data_dir, ["track", "list"])
    assert [row["posting_id"] for row in rows["rows"]] == [posting_id]
    assert rows["rows"][0]["title"] == "Python Engineer"
    events = _json(data_dir, ["track", "log", str(rows["rows"][0]["application_id"])])
    assert events["rows"], events
    assert {"event_type", "occurred_at"} <= set(events["rows"][0])


def test_an_empty_answer_is_still_one_object_and_the_words_go_to_stderr(
    empty_store: Path,
) -> None:
    result = _cli(empty_store, ["track", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"rows": []}
    assert "nothing tracked yet" in result.stderr
    ledger = _cli(empty_store, ["ledger", "show", "--json"])
    assert ledger.exit_code == 0
    assert json.loads(ledger.stdout) == {"rows": []}
    assert "ledger: nothing to show" in ledger.stderr


def _make_the_policy_column_unusable(data_dir: Path) -> None:
    """Store an `eligibility_policy_json` that is valid JSON but is not an object.

    `parse_policy` refuses it with `ProfileRowInvalid`, which is the one refusal `show` and
    `stats` reach through `refuse_unusable_profile_row` rather than through their own console —
    so it is the one that used to print two prose lines onto stdout under `--json`.
    """
    eng = get_engine(data_dir)
    with eng.begin() as conn:
        conn.execute(update(profile).values(eligibility_policy_json="garbage"))
    eng.dispose()


def test_an_unusable_profile_row_refuses_on_stderr_under_json(store: tuple[Path, int]) -> None:
    data_dir, posting_id = store
    _make_the_policy_column_unusable(data_dir)
    for args in (["show", str(posting_id)], ["stats"]):
        result = _cli(data_dir, [*args, "--json"])
        assert result.exit_code == 1, result.output
        assert result.stdout == "", (args, result.stdout)
        assert "profile row unusable — eligibility_policy_json" in result.stderr, args


def test_a_schema_or_argument_refusal_under_json_leaves_stdout_empty(
    store: tuple[Path, int],
) -> None:
    """The refusals `coverage` and `seeds` raise before they ever reach their `--json` branch."""
    data_dir, _ = store
    seeds = _cli(data_dir, ["seeds", "--limit", "-1", "--json"])
    assert seeds.exit_code == 1
    assert seeds.stdout == "", seeds.stdout
    assert "--limit must be non-negative" in seeds.stderr
    coverage = _cli(data_dir, ["coverage", "--run", "9999", "--json"])
    assert coverage.exit_code == 1
    assert coverage.stdout == "", coverage.stdout
    assert "no such run: 9999" in coverage.stderr


def test_config_show_json_gives_every_key_the_same_four_fields(empty_store: Path) -> None:
    """One accessor for every key. Three shapes here meant `payload[k]["value"]` raised
    `TypeError: string indices must be integers` on the llm flags and on both secrets."""
    payload = _json(empty_store, ["config", "show"])
    assert payload, payload
    for key, shown in payload.items():
        assert isinstance(shown, dict), (key, shown)
        assert set(shown) == {"value", "default", "units", "effect"}, (key, sorted(shown))
    assert payload["llm.api_key"]["value"] == "unset"
    assert payload["llm.api_key"]["default"] is None
    assert payload["notify.webhook_url"]["value"] == "unset"
    assert payload["weights.title_match"]["units"] == "[0,1]"


def test_a_refusal_under_json_leaves_stdout_empty(empty_store: Path) -> None:
    result = _cli(empty_store, ["track", "log", "99", "--json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "no application 99" in result.stderr
    profile = _cli(empty_store, ["profile", "show", "--json"])
    assert profile.exit_code == 1
    assert profile.stdout == ""
    assert "no profile yet" in profile.stderr
