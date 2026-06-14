from datetime import datetime

import pytest
from sqlalchemy import func, insert, select, text, update
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.registry.validate import CompanyEntry
from boardwatch.scan.health import probe_health
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

runner = CliRunner()


class FakeProvider:
    """healthcheck returns a programmed BoardHealth per slug (ignores the fetcher)."""
    def __init__(self, mapping: dict[str, BoardHealth]) -> None:
        self._m = mapping
    def healthcheck(self, fetcher, slug: str) -> BoardHealth:
        return self._m[slug]


def _engine(tmp_path):
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _watch(eng, provider, slug, last_ok_at=None):
    with eng.begin() as conn:
        conn.execute(insert(tables.companies).values(
            name=slug, provider=provider, slug=slug, source="user",
            watched=True, last_ok_at=last_ok_at,
        ))


def _settings(tmp_path):
    return Settings(data_dir=tmp_path, config_dir=tmp_path)


def _ok_at(eng, slug):
    with eng.connect() as conn:
        return conn.execute(
            select(tables.companies.c.last_ok_at).where(tables.companies.c.slug == slug)
        ).scalar_one()


def test_all_http_error_reachable_nonzero_preserves_last_ok_at(tmp_path) -> None:
    eng = _engine(tmp_path)
    from datetime import datetime
    prior = datetime(2026, 1, 1)
    _watch(eng, "greenhouse", "acme", last_ok_at=prior)
    providers = {"greenhouse": FakeProvider({"acme": BoardHealth.ERROR})}
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    assert report.actionable is True                              # ERROR is actionable
    assert report.connectivity[0].reachable is True               # a 500 still answered
    assert _ok_at(eng, "acme") == prior                           # preserved on ERROR


def test_all_transport_error_unreachable_nonzero(tmp_path) -> None:
    eng = _engine(tmp_path)
    _watch(eng, "lever", "globex")
    providers = {"lever": FakeProvider({"globex": BoardHealth.UNREACHABLE})}
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    assert report.actionable is True
    assert report.connectivity[0].reachable is False


def test_ok_and_empty_advance_last_ok_at(tmp_path) -> None:
    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "live")
    _watch(eng, "greenhouse", "blank")
    providers = {"greenhouse": FakeProvider({"live": BoardHealth.OK, "blank": BoardHealth.EMPTY})}
    probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    assert _ok_at(eng, "live") is not None and _ok_at(eng, "blank") is not None


def test_all_healthy_exit_zero_and_writes(tmp_path) -> None:
    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "acme")
    providers = {"greenhouse": FakeProvider({"acme": BoardHealth.OK})}
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    assert report.actionable is False
    assert _ok_at(eng, "acme") is not None  # OK wrote last_ok_at


def test_dead_board_is_actionable(tmp_path) -> None:
    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "acme")
    providers = {"greenhouse": FakeProvider({"acme": BoardHealth.DEAD})}
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    assert report.actionable is True
    assert report.connectivity[0].reachable is True  # a 404 still answered


def test_mixed_one_dead_one_ok_provider_reachable(tmp_path) -> None:
    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "dead1")
    _watch(eng, "greenhouse", "ok1")
    providers = {"greenhouse": FakeProvider({"dead1": BoardHealth.DEAD, "ok1": BoardHealth.OK})}
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    assert report.connectivity[0].reachable is True  # ≥1 HTTP-backed ⇒ reachable


def test_offline_writes_nothing(tmp_path) -> None:
    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "acme")
    providers = {"greenhouse": FakeProvider({"acme": BoardHealth.OK})}
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers, offline=True)
    assert report.board_health == {} and _ok_at(eng, "acme") is None  # no probe, no write


@pytest.fixture()
def _one_starter(monkeypatch):
    # zero-watch fallback probes the first starter catalog entry per provider
    monkeypatch.setattr(
        "boardwatch.scan.health.load_catalog",
        lambda *a, **k: [CompanyEntry(name="Seed", provider="ashby", slug="seed", tags=["starter"])],
    )
    monkeypatch.setattr(
        "boardwatch.scan.health.starter_entries", lambda entries: list(entries)
    )


@pytest.mark.parametrize(
    ("status", "actionable"),
    [(BoardHealth.UNREACHABLE, True), (BoardHealth.DEAD, False), (BoardHealth.ERROR, False)],
)
def test_zero_watch_fallback_no_writes(tmp_path, _one_starter, status, actionable) -> None:
    # provider 'ashby' has zero watches → fallback probe; ZERO DB writes in every case;
    # UNREACHABLE ⇒ actionable; DEAD/ERROR ⇒ informational (exit zero absent other failures),
    # explicitly contrasted with a watched-board ERROR which IS actionable (asserted above)
    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "acme")  # a different provider has a watch; ashby has none
    providers = {
        "greenhouse": FakeProvider({"acme": BoardHealth.OK}),
        "ashby": FakeProvider({"seed": status}),
    }
    report = probe_health(eng, _settings(tmp_path), fetcher=object(), providers=providers)
    ashby_line = next(c for c in report.connectivity if c.provider == "ashby")
    assert ashby_line.from_fallback is True
    assert (report.actionable is True) == actionable  # greenhouse OK is non-actionable; fallback rule
    # ISOLATED no-write claim: the fallback probes a catalog entry with NO watched row, so it must
    # create/touch NO ashby company row (the watched greenhouse row IS written by its own OK probe)
    assert _provider_row_count(eng, "ashby") == 0


def _provider_row_count(eng, provider):
    with eng.connect() as conn:
        return conn.execute(
            select(func.count()).select_from(tables.companies)
            .where(tables.companies.c.provider == provider)
        ).scalar_one()


def test_scan_complete_and_unchanged_are_not_health_writers(tmp_path) -> None:
    # sole-writer guarantee (complements state test c): NEITHER a complete NOR an unchanged scan
    # touches last_health/last_ok_at. Reuse the run_scan + respx harness.
    import json

    import httpx
    import respx

    from boardwatch.providers.greenhouse import GreenhouseProvider
    from boardwatch.scan.coordinator import run_scan

    eng = _engine(tmp_path)
    _watch(eng, "greenhouse", "acme")
    settings = _settings(tmp_path)
    url = GreenhouseProvider().board_url("acme")
    with respx.mock:  # scan 1: a complete inventory (empty board), with validators
        respx.get(url).mock(return_value=httpx.Response(
            200, content=json.dumps({"jobs": []}).encode(), headers={"ETag": 'W/"x"'}))
        run_scan(eng, settings)
    with respx.mock:  # scan 2: 304 → unchanged
        respx.get(url).mock(return_value=httpx.Response(304))
        run_scan(eng, settings)
    with eng.connect() as conn:
        row = conn.execute(
            select(tables.companies.c.last_health, tables.companies.c.last_ok_at)
            .where(tables.companies.c.slug == "acme")
        ).one()
    assert row.last_health is None and row.last_ok_at is None  # doctor is the ONLY writer


def test_cli_stale_board_is_informational_not_failure(tmp_path, monkeypatch) -> None:
    # a board with an OLD last-complete scan renders, but staleness ALONE does not fail (exit 0)
    def old_scan(eng):
        with eng.begin() as conn:
            run = conn.execute(insert(tables.runs).values(
                started_at=datetime(2025, 1, 1), finished_at=datetime(2025, 1, 1))).inserted_primary_key[0]
            cid = conn.execute(select(tables.companies.c.id)
                               .where(tables.companies.c.slug == "acme")).scalar_one()
            conn.execute(insert(tables.board_scans).values(
                run_id=run, company_id=cid, started_at=datetime(2025, 1, 1),
                finished_at=datetime(2025, 1, 1), status="complete", postings_listed=0))
    result = _cli(tmp_path, monkeypatch, {"acme": BoardHealth.OK}, extra=old_scan)
    assert result.exit_code == 0  # OK probe + only stale → not actionable
    assert "ago" in result.stdout  # the stale age is rendered as a duration ("…d ago")


def test_cli_integrity_failure_exits_nonzero(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("boardwatch.cli.doctor_cmd._integrity_check", lambda conn: "malformed")
    result = _cli(tmp_path, monkeypatch, {"acme": BoardHealth.OK})
    assert result.exit_code == 1 and "malformed" in result.stdout


# ---- CLI: exit code, mid-scan render, schema mismatch ----
def _cli(tmp_path, monkeypatch, mapping, *, extra=None):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    eng = _engine(data)
    _watch(eng, "greenhouse", "acme")
    if extra:
        extra(eng)
    monkeypatch.setattr(
        "boardwatch.scan.health.default_providers",
        lambda: {"greenhouse": FakeProvider(mapping)},
    )
    monkeypatch.setattr("boardwatch.scan.health.Fetcher", lambda settings: object())
    return runner.invoke(app, ["--data-dir", str(data), "doctor"])


@pytest.mark.parametrize(("status", "exit_code"), [(BoardHealth.OK, 0), (BoardHealth.DEAD, 1)])
def test_cli_exit_code(tmp_path, monkeypatch, status, exit_code) -> None:
    result = _cli(tmp_path, monkeypatch, {"acme": status})
    assert result.exit_code == exit_code


def test_cli_renders_mid_scan(tmp_path, monkeypatch) -> None:
    def open_run(eng):
        with eng.begin() as conn:
            conn.execute(insert(tables.runs).values(started_at=datetime(2026, 1, 1), finished_at=None))
    result = _cli(tmp_path, monkeypatch, {"acme": BoardHealth.OK}, extra=open_run)
    assert "in progress" in result.stdout


def test_cli_schema_mismatch_exits_nonzero(tmp_path, monkeypatch) -> None:
    def corrupt(eng):
        with eng.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = 'deadbeef'"))
    result = _cli(tmp_path, monkeypatch, {"acme": BoardHealth.OK}, extra=corrupt)
    assert result.exit_code == 1 and "MISMATCH" in result.stdout


def test_cli_offline_renders_not_checked_and_stored(tmp_path, monkeypatch) -> None:
    def seed(eng):
        with eng.begin() as conn:
            conn.execute(update(tables.companies).where(tables.companies.c.slug == "acme")
                         .values(last_health="ok", last_ok_at=datetime(2026, 1, 1)))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    eng = _engine(data)
    _watch(eng, "greenhouse", "acme")
    seed(eng)
    result = runner.invoke(app, ["--data-dir", str(data), "doctor", "--offline"])
    assert result.exit_code == 0
    assert "not checked" in result.stdout and "stored" in result.stdout
