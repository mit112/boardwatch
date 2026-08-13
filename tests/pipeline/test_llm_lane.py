"""The opt-in LLM lane: advisory, structurally non-blocking, never `ineligible`."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.core.settings import LLMTier, Settings
from boardwatch.eligibility.audit import load_llm_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.extract_llm import LANE_VERSION, extract_and_record
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import LaneDeathReason, LLMError, LLMLaneDeadError
from boardwatch.llm.factory import build_client
from boardwatch.llm.prompt import PROMPT_VERSION
from boardwatch.llm.run_client import RunScopedClient
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import get_evaluations, get_requirements
from boardwatch.store.queries import RUN_FAILED, RUN_OK

CLI_INIT_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"

JD_5YR = (
    "We need a backend engineer with a minimum of 5 years of experience. "
    "Salary range: $100k-$150k."
)
EXPERIENCE_QUOTE = "minimum of 5 years"
SALARY_QUOTE = "Salary range: $100k-$150k"


class FakeClient:
    """A ModelClient that returns canned JSON without any network call.

    Carries no `.model`/`.provider` attribute on purpose: extract_and_record must not
    duck-type provenance off the client (the real adapters don't carry `.provider`
    either), so provenance is passed explicitly by the caller instead.
    """

    def __init__(self, body: str):
        self.body = body

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.body


class RaisingClient:
    """A ModelClient whose complete() always fails, simulating a provider error."""

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise RuntimeError("provider unreachable")


def _seed_posting_version(engine: Engine, body: str, *, slug: str = "acme-llm") -> int:
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug=slug, source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=f"p-{slug}", title="Backend Engineer",
                    normalized_title="backend engineer", url="https://example.test/j",
                    locations_json=["Remote"], remote_policy="remote", first_seen_at=now,
                    last_seen_at=now, status="open", consecutive_missing=0,
                    content_hash=f"h-{slug}", body_text=body, job_id=job_id,
                )
            ).inserted_primary_key[0]
        )
        pv_id = int(
            conn.execute(
                insert(tables.posting_versions).values(
                    posting_id=posting_id, content_hash=f"h-{slug}", body_text=body,
                    captured_at=now, capture_reason="new",
                )
            ).inserted_primary_key[0]
        )
    return pv_id


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def catalog_and_policy(tmp_path: Path):
    catalog = load_rules(tmp_path / "no-such-cfg-dir")
    return catalog, Policy()


@pytest.fixture()
def cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(tmp_path / "cache")


def test_llm_row_written_with_provenance_and_never_ineligible(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR)
    body = json.dumps([{"family": "experience_years", "span_quote": EXPERIENCE_QUOTE}])
    facts = Facts(total_years_experience=10)

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
            catalog=catalog, client=FakeClient(body), cache=cache,
            provider="anthropic", model="claude-opus-4",
        )
    assert eval_id is not None

    with engine.connect() as conn:
        rows = get_evaluations(conn, pv_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.engine_kind == "llm"
    assert row.engine_version == LANE_VERSION
    assert row.prompt_version == PROMPT_VERSION
    # Provenance is recorded from the EXPLICIT provider/model params, never duck-typed
    # off the client (the real adapters carry no `.provider` attribute at all).
    assert row.provider == "anthropic"
    assert row.model == "claude-opus-4"
    assert row.verdict in ("eligible", "uncertain")
    assert row.verdict != "ineligible"


def test_out_of_family_span_is_unknown(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-2")
    body = json.dumps([{"family": "salary", "span_quote": SALARY_QUOTE}])
    facts = Facts()

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
            catalog=catalog, client=FakeClient(body), cache=cache,
        )
    assert eval_id is not None

    with engine.connect() as conn:
        reqs = get_requirements(conn, eval_id)
    assert len(reqs) == 1
    assert reqs[0].disposition == "unknown"
    assert reqs[0].requirement_text == SALARY_QUOTE


def test_structurally_non_blocking_even_when_unmet(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-3")
    body = json.dumps([{"family": "experience_years", "span_quote": EXPERIENCE_QUOTE}])
    facts = Facts(total_years_experience=2)  # short of the JD's 5-year ask

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
            catalog=catalog, client=FakeClient(body), cache=cache,
        )
    assert eval_id is not None

    with engine.connect() as conn:
        reqs = get_requirements(conn, eval_id)
        rows = get_evaluations(conn, pv_id)
    assert reqs[0].disposition == "unmet"
    assert rows[0].verdict == "uncertain"  # capped: never 'ineligible', even when unmet


def test_empty_extraction_is_uncertain_not_eligible(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    """A client returning no grounded spans (empty, malformed, or fully-fabricated
    output) must not read as vacuously 'eligible': zero requirements adjudicated
    means nothing was verified met, so the verdict must be 'uncertain'."""
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-empty")
    facts = Facts(total_years_experience=10)

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
            catalog=catalog, client=FakeClient("[]"), cache=cache,
        )
    assert eval_id is not None

    with engine.connect() as conn:
        reqs = get_requirements(conn, eval_id)
        rows = get_evaluations(conn, pv_id)
    assert reqs == []
    assert rows[0].verdict == "uncertain"
    assert rows[0].verdict != "ineligible"


def test_disabled_lane_skips_via_build_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")
    settings = Settings(
        data_dir=tmp_path / "data", config_dir=tmp_path / "cfg",
        llm=LLMTier(enabled=False),
    )
    assert build_client(settings) is None


def test_enabled_but_no_key_skips_via_build_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    settings = Settings(
        data_dir=tmp_path / "data", config_dir=tmp_path / "cfg",
        llm=LLMTier(enabled=True, provider="anthropic", model="claude-opus-4"),
    )
    assert build_client(settings) is None


def test_extract_and_record_with_no_client_is_skipped(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-4")
    facts = Facts()

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
            catalog=catalog, client=None, cache=cache,
        )
    assert eval_id is None

    with engine.connect() as conn:
        assert get_evaluations(conn, pv_id) == []


def test_provider_error_degrades_gracefully_with_no_row_written(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-5")
    facts = Facts()

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
            catalog=catalog, client=RaisingClient(), cache=cache,
        )
    assert eval_id is None

    with engine.connect() as conn:
        assert get_evaluations(conn, pv_id) == []


class RecordingClient:
    """A ModelClient that records whether .complete was ever called (for --dry-run)."""

    def __init__(self, body: str = "[]") -> None:
        self.body = body
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return self.body


runner = CliRunner()


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(cfg))
    monkeypatch.delenv(LLM_API_KEY_ENV, raising=False)
    return tmp_path / "data"


def _invoke(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def _write_llm_config(cfg_dir: Path, **fields: bool | str) -> None:
    """Write a minimal config.toml [llm] table for a CLI-invoked test.

    load_settings only reads llm.* from config.toml (never the environment), so a test
    that drives `eligibility extract` through the CLI must write this file rather than
    construct a Settings object directly.
    """
    lines = ["[llm]"]
    for key, value in fields.items():
        rendered = ("true" if value else "false") if isinstance(value, bool) else f'"{value}"'
        lines.append(f"{key} = {rendered}")
    (cfg_dir / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _posting_id_for_version(engine: Engine, pv_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(tables.posting_versions.c.posting_id).where(
                    tables.posting_versions.c.id == pv_id
                )
            ).scalar_one()
        )


def test_extract_skips_cleanly_when_extraction_disabled(cli_env: Path) -> None:
    """Both the extraction feature and the tier are off by default: extract must
    degrade to a one-line message, exit 0, and never touch a posting (no profile is
    even seeded here). The extraction gate is checked first, so its message is the
    one that surfaces here."""
    result = _invoke(cli_env, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert "llm eligibility extraction is off" in result.output.lower()


def test_extract_skips_cleanly_when_extraction_off_but_tier_on(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extraction is the feature gate, checked BEFORE the client is ever built: a tier
    that is enabled with a real credential still must not proceed, and must never
    reach build_client (so it can never make a model call), when
    llm.eligibility_extraction is False."""
    cfg_dir = cli_env.parent / "cfg"
    _write_llm_config(
        cfg_dir, enabled=True, provider="anthropic", model="claude-3-haiku",
        eligibility_extraction=False,
    )
    monkeypatch.setenv(LLM_API_KEY_ENV, "a-real-key")

    def _poison(settings: Settings) -> None:
        raise AssertionError("build_client must not be called when extraction is off")

    monkeypatch.setattr("boardwatch.cli.eligibility_cmd.build_client", _poison)

    result = _invoke(cli_env, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert "llm eligibility extraction is off" in result.output.lower()


def test_extract_dry_run_previews_without_calling_client(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_llm_config(cli_env.parent / "cfg", eligibility_extraction=True)
    engine = get_engine(cli_env)
    body = "We need a backend engineer. Distinctive posting body marker."
    _seed_posting_version(engine, body, slug="acme-dry-run")
    client = RecordingClient()
    monkeypatch.setattr("boardwatch.cli.eligibility_cmd.build_client", lambda settings: client)

    result = _invoke(cli_env, ["eligibility", "extract", "--dry-run"])
    assert result.exit_code == 0
    assert "Distinctive posting body marker" in result.output
    assert "Destination:" in result.output
    assert client.calls == 0  # dry-run never calls the model


def test_extract_runs_and_writes_an_advisory_llm_row(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_llm_config(cli_env.parent / "cfg", eligibility_extraction=True)
    assert _invoke(cli_env, ["init"], CLI_INIT_INPUT).exit_code == 0
    engine = get_engine(cli_env)
    body = JD_5YR
    pv_id = _seed_posting_version(engine, body, slug="acme-extract-run")
    body_json = json.dumps([{"family": "experience_years", "span_quote": EXPERIENCE_QUOTE}])
    client = RecordingClient(body_json)
    monkeypatch.setattr("boardwatch.cli.eligibility_cmd.build_client", lambda settings: client)

    result = _invoke(cli_env, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert "extracted 1 of 1 attempted" in result.output
    assert client.calls == 1

    with engine.connect() as conn:
        rows = get_evaluations(conn, pv_id)
    assert len(rows) == 1
    assert rows[0].engine_kind == "llm"


def test_show_labels_llm_rows_as_advisory(cli_env: Path) -> None:
    """A stored engine_kind='llm' row renders under an 'advisory (LLM)' label, distinct
    from the deterministic 'Eligibility:' verdict, which stays primary and untouched."""
    assert _invoke(cli_env, ["init"], CLI_INIT_INPUT).exit_code == 0
    engine = get_engine(cli_env)
    body = "We are hiring a backend engineer. A Bachelor's degree is required."
    pv_id = _seed_posting_version(engine, body, slug="acme-show-llm")
    posting_id = _posting_id_for_version(engine, pv_id)

    assert _invoke(cli_env, ["eligibility", "run"]).exit_code == 0  # deterministic row

    catalog = load_rules(cli_env / "no-such-cfg-dir")
    body_json = json.dumps([{"family": "degree", "span_quote": "Bachelor's degree"}])
    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=body, facts=Facts(), policy=Policy(),
            catalog=catalog, client=RecordingClient(body_json),
            cache=ResponseCache(cli_env / "llm-cache"),
        )
    assert eval_id is not None

    result = _invoke(cli_env, ["show", str(posting_id)])
    assert result.exit_code == 0
    out = result.stdout
    assert "Eligibility:" in out  # the deterministic verdict, still primary
    assert "advisory (LLM):" in out  # the opt-in lane's row, labeled distinct


def test_llm_audit_label_uses_requirement_text_on_catalog_mismatch(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    """load_llm_audit must never fall back to load_audit's rule_id label on a
    catalog-version mismatch: an LLM requirement always carries rule_id=None
    (extract_llm._requirement_for_span never sets one), so that fallback would render
    the literal 'None (catalog version no longer present)' instead of the grounded
    quote."""
    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-audit-label")
    posting_id = _posting_id_for_version(engine, pv_id)
    body = json.dumps([{"family": "experience_years", "span_quote": EXPERIENCE_QUOTE}])

    with engine.begin() as conn:
        eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=Facts(), policy=policy,
            catalog=catalog, client=FakeClient(body), cache=cache,
        )
    assert eval_id is not None

    # eligibility_inputs is append-only (trigger-guarded), so the mismatch is produced
    # by reading with a DIFFERENT catalog version rather than mutating the stored row.
    stale_catalog = dataclasses.replace(catalog, version="stale-version-that-cannot-match")

    with engine.connect() as conn:
        view = load_llm_audit(conn, posting_id, stale_catalog)
    assert view is not None
    assert view.catalog_version_matches is False
    assert view.requirements[0].label == EXPERIENCE_QUOTE  # requirement_text, never rule_id
    assert "None (catalog version" not in view.requirements[0].label


def test_load_llm_audit_ignores_final_gate_rows(
    engine: Engine, catalog_and_policy, cache: ResponseCache
) -> None:
    """Seed BOTH an extract_llm-style row ('llm:...') and a final-gate row
    ('final_gate:...') for the same posting version, gate row written LAST (so an
    id-desc/limit-1 read with no version scope would pick it). load_llm_audit must
    still return the advisory (llm:%) row, never the gate row — the two lanes share
    engine_kind='llm' but must never be conflated (D-071b's IDENTITY-JOIN concern)."""
    from boardwatch.eligibility import final_gate
    from boardwatch.eligibility.oracle import OracleVerdict

    catalog, policy = catalog_and_policy
    pv_id = _seed_posting_version(engine, JD_5YR, slug="acme-llm-vs-gate")
    body = json.dumps([{"family": "experience_years", "span_quote": EXPERIENCE_QUOTE}])

    with engine.begin() as conn:
        advisory_eval_id = extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=Facts(), policy=policy,
            catalog=catalog, client=FakeClient(body), cache=cache,
        )
    assert advisory_eval_id is not None

    verdict = OracleVerdict(
        label="1", decision="ineligible", reason="experience_years",
        evidence=EXPERIENCE_QUOTE, confidence="high",
    )
    with engine.begin() as conn:
        gate_eval_id = final_gate.record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=Facts(), policy=policy,
            catalog=catalog, verdict=verdict,
        )
    assert gate_eval_id is not None
    assert gate_eval_id > advisory_eval_id  # gate row is newer by id

    posting_id = _posting_id_for_version(engine, pv_id)
    with engine.connect() as conn:
        view = load_llm_audit(conn, posting_id, catalog)
    assert view is not None
    # The advisory lane never writes 'ineligible' (structurally non-blocking); the gate
    # row does. Getting 'ineligible' back here would mean the scope missed the gate row.
    assert view.verdict != "ineligible"


def _seed_extract_env(cli_env: Path, count: int, *, prefix: str) -> Path:
    """Make `eligibility extract` actually reach its loop, with `count` open postings.

    Three things are load-bearing here:

    - `_write_llm_config(eligibility_extraction=True)`, or the command short-circuits on
      the feature gate before building a client.
    - `init`, which writes the profile row. Without one the command exits 1 via
      `_no_profile()` before the loop, and every test below would pass or fail for the
      wrong reason.
    - **Distinct `body_text` per posting.** The response-cache key folds in the JD text,
      the profile hash and the rules hash, but NOT `posting_version_id` — so identical
      bodies share one cache entry, and posting 2 would be served from cache instead of
      reaching the client. A fresh data dir (which `cli_env` gives, being tmp_path
      scoped) is necessary for a cold cache but not sufficient.
    """
    _write_llm_config(cli_env.parent / "cfg", eligibility_extraction=True)
    assert _invoke(cli_env, ["init"], CLI_INIT_INPUT).exit_code == 0
    engine = get_engine(cli_env)
    for index in range(count):
        _seed_posting_version(
            engine, f"{JD_5YR} Posting number {index}.", slug=f"{prefix}-{index}"
        )
    return cli_env


@pytest.fixture()
def cli_env_with_postings(cli_env: Path) -> Path:
    """Two open postings — the second is what the partial-success test has to reach."""
    return _seed_extract_env(cli_env, 2, prefix="acme-lane")


@pytest.fixture()
def cli_env_with_many_postings(cli_env: Path) -> Path:
    """Strictly more open postings than llm.max_calls_per_run (50), so "stopped at the
    cap" is distinguishable from "ran out of work". With 50 or fewer the cap-regression
    test passes either way and guards nothing."""
    return _seed_extract_env(cli_env, 55, prefix="acme-cap")


class _DeadClient:
    """Every call reports the credential is unusable."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        raise LLMLaneDeadError("no credit", reason=LaneDeathReason.CREDIT_EXHAUSTED)


class _AlwaysFailingClient:
    """Ordinary, unclassified failure -- the swallowed kind."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        raise LLMError("network went away")


def test_dead_credential_stops_after_one_call_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings: Path
) -> None:
    # The fixture seeds 2 postings into a FRESH data dir: the cache is consulted before
    # the client, so a warm cache would mask the death. Reaching only the first proves
    # the loop stopped rather than ran out of work.
    inner = _DeadClient()
    client = RunScopedClient(inner)
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client", lambda settings: client
    )
    result = _invoke(cli_env_with_postings, ["eligibility", "extract"])
    flat = result.output.replace("\n", "")
    assert result.exit_code == 1
    # `attempted` is what catches a missing `break`. Delete the break in eligibility_cmd
    # and the loop reaches posting 2, so this reads "0 of 2" and fails.
    assert "extracted 0 of 1 attempted" in flat
    assert "credit_exhausted" in flat
    # NOT a second copy of the line above. `calls_attempted` is the WRAPPER's own tally, and
    # it stays 1 with the break deleted — `RunScopedClient.complete` raises on the latched
    # reason BEFORE incrementing — so on its own it would pass with that defect present. It
    # catches the opposite one: a lane that stopped counting rather than stopped calling.
    assert client.calls_attempted == 1
    # The independent counter: how many times the provider was really reached. Kept by the
    # fake, not self-reported by the code under test, so a wrapper that mis-tallies cannot
    # make this agree with it.
    assert inner.calls == 1


def _run_rows(data_dir: Path) -> list[tuple[str, object, object]]:
    with get_engine(data_dir).connect() as conn:
        return [
            (str(status), errors, finished_at)
            for status, errors, finished_at in conn.execute(
                select(
                    tables.runs.c.status,
                    tables.runs.c.errors_json,
                    tables.runs.c.finished_at,
                ).order_by(tables.runs.c.id)
            ).all()
        ]


def test_dead_credential_records_a_failed_run_row(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings: Path
) -> None:
    """The DURABLE ledger, not the terminal. `finish_run` was called with its
    `status=RUN_OK` default on every path, so the invocation the command exits 1 for left a
    row reading `ok`, no errors, zero evaluations — the honest report was the ephemeral one.
    Asserting a row EXISTS would have passed with that defect present; the status is the
    assertion."""
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client",
        lambda settings: RunScopedClient(_DeadClient()),
    )
    result = _invoke(cli_env_with_postings, ["eligibility", "extract"])
    assert result.exit_code == 1
    rows = _run_rows(cli_env_with_postings)
    assert len(rows) == 1
    status, errors, finished_at = rows[0]
    assert status == RUN_FAILED
    # Closed, not abandoned as `running` — the reaper must not have to guess at this row.
    assert finished_at is not None
    # The typed reason reaches the payload. `LaneDeathReason` is read off the exception
    # attribute upstream; this only checks it was carried through, not that it was parsed.
    assert errors is not None
    assert LaneDeathReason.CREDIT_EXHAUSTED.value in errors[0]


def test_a_provider_outage_that_is_not_lane_death_still_finishes_ok(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings: Path
) -> None:
    """The narrowness of the clause above. An unclassified failure is NOT the command
    declaring failure — it exits 0 — so its run row stays `ok` attributing zero rows, which
    `extract`'s minting comment deliberately blesses. Widening `failed` to "wrote nothing"
    would turn every flaky provider into a failed run."""
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client",
        lambda settings: _AlwaysFailingClient(),
    )
    result = _invoke(cli_env_with_postings, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert [(status, errors) for status, errors, _ in _run_rows(cli_env_with_postings)] == [
        (RUN_OK, None)
    ]


def test_partial_success_before_death_exits_0(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings: Path
) -> None:
    class _DiesOnSecond:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, *, system: str | None = None) -> str:
            self.calls += 1
            if self.calls == 1:
                return '{"requirements": []}'
            raise LLMLaneDeadError("no credit", reason=LaneDeathReason.CREDIT_EXHAUSTED)

    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client",
        lambda settings: RunScopedClient(_DiesOnSecond()),
    )
    result = _invoke(cli_env_with_postings, ["eligibility", "extract"])
    flat = result.output.replace("\n", "")
    assert result.exit_code == 0
    assert "extracted 1 of 2 attempted" in flat
    # A partial success really did succeed partially, so the ledger says `ok`. Together with
    # the failed-row test above this pins BOTH sides of the conjunction: death alone does not
    # fail the run, and zero-landed alone does not either.
    assert [(status, errors) for status, errors, _ in _run_rows(cli_env_with_postings)] == [
        (RUN_OK, None)
    ]


def test_cap_survives_unclassified_failures(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_many_postings: Path
) -> None:
    # REGRESSION GUARD for the two-counter split. `cli_env_with_many_postings`
    # seeds more than llm.max_calls_per_run open postings. If the cap were
    # keyed to successes, every one of them would be called.
    client = _AlwaysFailingClient()
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client", lambda settings: client
    )
    result = _invoke(cli_env_with_many_postings, ["eligibility", "extract"])
    assert result.exit_code == 0  # unclassified failure is NOT lane death
    assert client.calls == 50  # llm.max_calls_per_run default


def test_all_unclassified_failures_still_exit_0(
    monkeypatch: pytest.MonkeyPatch, cli_env_with_postings: Path
) -> None:
    # Zero-landed alone must never be fatal -- only death-observed AND zero.
    monkeypatch.setattr(
        "boardwatch.cli.eligibility_cmd.build_client",
        lambda settings: _AlwaysFailingClient(),
    )
    result = _invoke(cli_env_with_postings, ["eligibility", "extract"])
    flat = result.output.replace("\n", "")
    assert result.exit_code == 0
    assert "extracted 0 of" in flat
