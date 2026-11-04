"""`boardwatch companies discover-crawl` end to end, on a fake crawl source and fake providers.

The properties: a slug already stored under ANOTHER CASE is dropped before it is probed; the
command writes no row and creates no table; the output is a file `companies import` accepts; and
the cap counts admitted boards, not probes. `BOARDWATCH_CONFIG_DIR` is pinned so the role taxonomy
is the one written here, never the operator's.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import inspect, text
from typer.testing import CliRunner

from boardwatch.cli import companies_cmd
from boardwatch.cli.app import app
from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.lanes.common_crawl import Block
from boardwatch.registry.validate import CompanyEntry, validate_entries
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import upsert_watch

runner = CliRunner()
BLOCK = Block("cdx-00000.gz", 0, 10)


def _posting(title: str, *locations: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=title, title=title, url="https://x.test/1", locations=list(locations),
        body_text="", raw_json={},
    )


ENGINEER = _posting("Software Engineer", "Austin, TX")
BOARDS = {
    "lightfield": [ENGINEER],  # stored as `Lightfield`: must be dropped as known
    "newco": [ENGINEER, _posting("Backend Engineer", "Austin, TX")],
    "sales": [_posting("Account Executive", "Austin, TX")],
    "second": [ENGINEER],
}


class FakeAshby:
    name = "ashby"
    board_hosts: tuple[str, ...] = ()
    probed: list[str] = []

    def board_url(self, slug: str) -> str:
        return f"https://api.test/{slug}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        FakeAshby.probed.append(request.slug)
        postings = BOARDS.get(request.slug)
        if postings is None:
            return BoardSnapshot(status="failed", postings=[], url=request.url, dead=True)
        return BoardSnapshot(status="complete", postings=postings, url=request.url)

    def healthcheck(self, fetcher: Fetcher, slug: str) -> Any:
        raise NotImplementedError


class FakeSource:
    def newest_collection(self) -> str:
        return "CC-TEST"

    def cluster_lines(self, collection: str) -> Any:
        yield f"com,ashbyhq,jobs)/a 20261001000000\t{BLOCK.cdx_file}\t0\t10\t1\n"

    def block(self, collection: str, block: Block) -> bytes:
        keys = ["Lightfield", "newco", "sales", "second", "ghost", "embed"]
        lines = "".join(f"com,ashbyhq,jobs)/{k}/1 20261001000000 {{}}\n" for k in keys)
        return gzip.compress(lines.encode())


@pytest.fixture(autouse=True)
def _wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "cfg"
    config.mkdir()
    (config / "role-taxonomy.yaml").write_text("version: 1\nfield: software\nbundled: true\n")
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    FakeAshby.probed = []
    monkeypatch.setattr(companies_cmd, "HttpCrawlSource", FakeSource)
    monkeypatch.setattr(companies_cmd, "build_providers", lambda: {"ashby": FakeAshby()})


def _run(tmp_path: Path, *args: str) -> Any:
    return runner.invoke(
        app, ["--data-dir", str(tmp_path / "data"), "companies", "discover-crawl", *args]
    )


def _store(tmp_path: Path, *rows: tuple[str, str]) -> None:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    with engine.begin() as conn:
        for provider, slug in rows:
            upsert_watch(conn, provider=provider, slug=slug, name=slug, source="user")
    engine.dispose()


def _row_counts(tmp_path: Path) -> dict[str, int]:
    engine = get_engine(tmp_path / "data")
    with engine.connect() as conn:
        counts = {
            t: int(conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one())
            for t in inspect(engine).get_table_names()
        }
    engine.dispose()
    return counts


def test_a_known_slug_in_another_case_is_dropped_and_never_probed(tmp_path: Path) -> None:
    _store(tmp_path, ("ashby", "Lightfield"))

    result = _run(tmp_path, "--provider", "ashby", "--limit", "10")

    assert result.exit_code == 0, result.output
    entries = yaml.safe_load(result.stdout)["companies"]
    assert sorted(e["slug"] for e in entries) == ["newco", "second"]
    assert "lightfield" not in FakeAshby.probed
    # Enumerated: lightfield, newco, sales, second, ghost (`embed` is chrome). One is known.
    assert "enumerated 5 | already stored 1 | probed 4 | dead 1 | failed 0 | empty 0" in result.stdout
    assert "no qualifying posting 1 | admitted 2 | held back by the cap 0" in result.stdout
    validate_entries([CompanyEntry(**e) for e in entries])


def test_the_evidence_line_is_checkable_in_one_line(tmp_path: Path) -> None:
    result = _run(tmp_path, "--provider", "ashby")

    assert (
        "#   ashby:newco | https://api.test/newco | 2 open | 2 qualifying "
        "| e.g. Software Engineer; Backend Engineer"
    ) in result.stdout


def test_the_command_writes_no_row_and_creates_no_table(tmp_path: Path) -> None:
    _store(tmp_path, ("ashby", "Lightfield"))
    before = _row_counts(tmp_path)

    assert _run(tmp_path, "--provider", "ashby").exit_code == 0

    assert _row_counts(tmp_path) == before
    assert before["companies"] == 1


def test_a_fresh_machine_with_no_schema_still_runs_and_stays_schemaless(tmp_path: Path) -> None:
    result = _run(tmp_path, "--provider", "ashby")

    assert result.exit_code == 0, result.output
    assert _row_counts(tmp_path) == {}
    assert "lightfield" in FakeAshby.probed  # nothing stored, so nothing is known


def test_the_cap_counts_admitted_boards_not_probes(tmp_path: Path) -> None:
    result = _run(tmp_path, "--provider", "ashby", "--limit", "1")

    entries = yaml.safe_load(result.stdout)["companies"]
    assert [e["slug"] for e in entries] == ["lightfield"]
    # Probing stopped at the first admission, in slug order: ghost (dead), then lightfield.
    assert FakeAshby.probed == ["ghost", "lightfield"]
    assert "admitted 1 | held back by the cap 0 | not probed 3" in result.stdout


def test_admissions_past_the_cap_are_refused_and_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two providers' workers can each finish an in-flight probe past the cap; `select` is the
    backstop. Simulated by probing with a looser cap than the command's."""
    real = companies_cmd.probe_candidates
    monkeypatch.setattr(
        companies_cmd, "probe_candidates", lambda *a, **k: real(*a, **{**k, "cap": 99})
    )

    result = _run(tmp_path, "--provider", "ashby", "--limit", "1")

    entries = yaml.safe_load(result.stdout)["companies"]
    assert [e["slug"] for e in entries] == ["lightfield"]
    # lightfield, newco and second all qualify; the cap keeps the first in slug order.
    assert "admitted 1 | held back by the cap 2 | not probed 0" in result.stdout


def test_no_role_taxonomy_is_refused_rather_than_dropping_every_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "empty-cfg"))

    result = _run(tmp_path, "--provider", "ashby")

    assert result.exit_code == 1
    assert FakeAshby.probed == []


def test_an_unsupported_provider_is_refused(tmp_path: Path) -> None:
    assert _run(tmp_path, "--provider", "lever").exit_code == 1
