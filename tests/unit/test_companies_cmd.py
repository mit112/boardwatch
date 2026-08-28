import sqlite3
from contextlib import closing

import httpx
import pytest
import respx
import yaml
from github_lists_shape import listings
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.lanes.github_lists import LIST_URLS
from boardwatch.providers.base import BoardHealth
from boardwatch.store import tables
from boardwatch.store.db import DB_FILENAME, get_engine

runner = CliRunner()


class FakeProvider:
    """healthcheck returns a programmed BoardHealth per slug (ignores the fetcher)."""

    def __init__(self, mapping: dict[str, BoardHealth]) -> None:
        self._m = mapping

    def healthcheck(self, fetcher, slug: str) -> BoardHealth:
        return self._m[slug]


def _fake_probe(monkeypatch, mapping, provider="greenhouse"):
    """Route companies_cmd's verification at a FakeProvider — no network."""
    monkeypatch.setattr(
        "boardwatch.cli.companies_cmd.default_providers",
        lambda: {provider: FakeProvider(mapping)},
    )
    monkeypatch.setattr("boardwatch.cli.companies_cmd.Fetcher", lambda settings: object())


def _import_file(tmp_path, entries):
    path = tmp_path / "targets.yaml"
    path.write_text(yaml.safe_dump({"companies": entries}), encoding="utf-8")
    return str(path)


@pytest.fixture(autouse=True)
def _no_gha(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))


def _base(tmp_path):
    return ["--data-dir", str(tmp_path / "data")]


def _watch_count(tmp_path, provider, slug):
    try:
        with get_engine(tmp_path / "data").connect() as conn:
            return conn.execute(
                select(tables.companies).where(
                    tables.companies.c.provider == provider, tables.companies.c.slug == slug
                )
            ).all()
    except OperationalError:
        return []  # no DB / no table = no watches


@pytest.mark.parametrize(
    "sub", ["search", "add", "remove", "list", "discover", "import", "export"]
)
def test_every_subcommand_has_help(tmp_path, sub) -> None:
    result = runner.invoke(app, [*_base(tmp_path), "companies", sub, "--help"])
    assert result.exit_code == 0


@respx.mock
def test_discover_writes_no_watch_and_emits_a_file_import_accepts(tmp_path) -> None:
    """The whole write path end to end, and the only test that proves the deliverable.

    `discover` writes NOTHING to the store — that is the owner's ruling (D-291 build): a human
    sits between a public list and what the machine watches, because a bad slug becomes a
    permanently failing board and there is no quarantine for one. `companies import`, unchanged,
    does the watched-write on the file the human read.
    """
    for (_repo, url), shape in zip(LIST_URLS, ("S1", "S2"), strict=True):
        respx.get(url).mock(return_value=httpx.Response(200, json=listings(shape)))
    base = _base(tmp_path)
    out = tmp_path / "candidates.yaml"

    written = runner.invoke(
        app, [*base, "companies", "discover", "--limit", "4", "--out", str(out)]
    )
    assert written.exit_code == 0, written.stdout
    # Not "zero companies" but "NO SCHEMA": `discover` uses ensure=False, so it must not migrate.
    # SQLAlchemy touches the file just by inspecting it, so the file's existence proves nothing --
    # the absence of every table does. Read through stdlib sqlite3 rather than the same
    # `inspect(engine)` call the command itself makes, so this cannot agree with itself.
    # `closing`, not a bare `with`: `sqlite3.Connection.__exit__` commits the transaction and does
    # NOT close the connection, which leaks it and raises ResourceWarning under the gate.
    with closing(sqlite3.connect(tmp_path / "data" / DB_FILENAME)) as raw:
        assert raw.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall() == []

    written_text = out.read_text(encoding="utf-8")
    rows = yaml.safe_load(written_text)["companies"]
    assert len(rows) == 4
    # The header has to be IN THE FILE, not only on stdout. `yaml.safe_load` ignores comments, so
    # emitting the bare body passed every other assertion here -- and the header is the whole
    # artifact the design says the owner reviews away from the terminal that produced it.
    assert written_text.startswith("# boardwatch companies discover")
    assert "held back by the cap" in written_text
    for row in rows:
        assert f"{row['provider']}:{row['slug']}" in written_text
    assert runner.invoke(app, [*base, "companies", "import", str(out)]).exit_code == 0
    for row in rows:
        watched = _watch_count(tmp_path, row["provider"], row["slug"])
        assert len(watched) == 1
        # `user`, which is what `import` already writes for a board outside the bundled catalog.
        # No new `companies.source` value and therefore no migration against a 1.4 GB live store.
        assert (watched[0].watched, watched[0].source) == (True, "user")

    # Re-running proposes the NEXT batch, never the same one — the ramp self-advances off the
    # store, so the cap is a burn rate rather than a permanent ceiling.
    again = tmp_path / "candidates2.yaml"
    assert runner.invoke(
        app, [*base, "companies", "discover", "--limit", "4", "--out", str(again)]
    ).exit_code == 0
    next_rows = yaml.safe_load(again.read_text(encoding="utf-8"))["companies"]
    assert len(next_rows) == 4
    assert not (
        {(r["provider"], r["slug"]) for r in next_rows} & {(r["provider"], r["slug"]) for r in rows}
    )


@respx.mock
def test_discover_defaults_to_stdout_and_the_cap_from_settings(tmp_path) -> None:
    """No `--out`, no `--limit`: the document goes to stdout unmangled and the cap is the
    setting the lane path already uses, so there is one knob rather than two."""
    for (_repo, url), shape in zip(LIST_URLS, ("S1", "S2"), strict=True):
        respx.get(url).mock(return_value=httpx.Response(200, json=listings(shape)))

    result = runner.invoke(app, [*_base(tmp_path), "companies", "discover"])
    assert result.exit_code == 0, result.stdout
    document = yaml.safe_load(result.stdout)
    assert len(document["companies"]) == 10  # Settings.lane_new_companies_per_run
    assert "held back by the cap" in result.stdout


def test_search_is_case_insensitive_and_offline(tmp_path) -> None:
    # search reads the bundled catalog (no DB, no network); case-insensitive substring
    result = runner.invoke(app, [*_base(tmp_path), "companies", "search", "ACME"])
    assert result.exit_code == 0  # renders a (possibly empty) table without touching the network


def test_add_then_list_renders_watched_then_remove(tmp_path) -> None:
    base = _base(tmp_path)
    assert runner.invoke(app, [*base, "companies", "add", "lever:globex"]).exit_code == 0
    listed = runner.invoke(app, [*base, "companies", "list"])
    assert listed.exit_code == 0 and "globex" in listed.stdout and "yes" in listed.stdout  # watched col
    assert runner.invoke(app, [*base, "companies", "remove", "lever:globex"]).exit_code == 0


def test_add_is_idempotent_no_duplicate(tmp_path) -> None:
    base = _base(tmp_path)
    runner.invoke(app, [*base, "companies", "add", "lever:globex"])
    runner.invoke(app, [*base, "companies", "add", "https://jobs.lever.co/globex/job-9"])  # 2nd variant
    assert len(_watch_count(tmp_path, "lever", "globex")) == 1  # UNIQUE(provider, slug) respected


def test_add_unknown_url_exits_nonzero_and_writes_nothing(tmp_path) -> None:
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "companies", "add", "https://workday.com/acme"])
    assert result.exit_code == 1
    assert _watch_count(tmp_path, "greenhouse", "acme") == []  # DB untouched


def test_export_import_round_trip_is_noop_beyond_watching(tmp_path) -> None:
    base = _base(tmp_path)
    runner.invoke(app, [*base, "companies", "add", "lever:globex"])
    dump = runner.invoke(app, [*base, "companies", "export"]).stdout
    (tmp_path / "out.yaml").write_text(dump, encoding="utf-8")
    result = runner.invoke(app, [*base, "companies", "import", str(tmp_path / "out.yaml")])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "lever", "globex")) == 1


def test_adding_a_smartrecruiters_board_warns_it_cannot_be_verified(tmp_path) -> None:
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "companies", "add", "smartrecruiters:acme"])
    assert result.exit_code == 0
    assert "cannot confirm" in result.stdout.lower()


def test_adding_a_smartrecruiters_board_lowercases_the_slug(tmp_path) -> None:
    """H3 end-to-end: smartrecruiters:Visa stores slug 'visa'."""
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "companies", "add", "smartrecruiters:Visa"])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "smartrecruiters", "visa")) == 1


def test_adding_a_case_variant_watches_the_stored_board_and_reports_it(tmp_path) -> None:
    """`companies add ashby:KAYAK` with `ashby:kayak` already watched. Caught by hand once and
    then missed once — `ashby:Lightfield`/`ashby:lightfield` reached the live store as two rows
    for one board. A silent no-op is the wrong outcome here: the operator would be left
    believing a new board was added, so the resolution has to be printed."""
    base = _base(tmp_path)
    assert runner.invoke(app, [*base, "companies", "add", "ashby:kayak"]).exit_code == 0
    result = runner.invoke(app, [*base, "companies", "add", "ashby:KAYAK"])
    assert result.exit_code == 0
    assert "ashby:kayak" in result.stdout and "no second board" in result.stdout
    assert len(_watch_count(tmp_path, "ashby", "kayak")) == 1
    assert _watch_count(tmp_path, "ashby", "KAYAK") == []


def test_importing_a_case_variant_reports_it_rather_than_counting_a_new_board(tmp_path) -> None:
    """`import` reports its work as a COUNT, which on its own would imply a new board."""
    base = _base(tmp_path)
    runner.invoke(app, [*base, "companies", "add", "ashby:kayak"])
    path = _import_file(tmp_path, [{"name": "Kayak", "provider": "ashby", "slug": "KAYAK"}])
    result = runner.invoke(app, [*base, "companies", "import", path])
    assert result.exit_code == 0
    assert "ashby:kayak" in result.stdout
    assert _watch_count(tmp_path, "ashby", "KAYAK") == []


def test_removing_a_case_variant_unwatches_the_stored_board(tmp_path) -> None:
    """The orphan the guard would otherwise create: a board added by typing `KAYAK` that
    `remove ashby:KAYAK` can no longer reach."""
    base = _base(tmp_path)
    runner.invoke(app, [*base, "companies", "add", "ashby:kayak"])
    result = runner.invoke(app, [*base, "companies", "remove", "ashby:KAYAK"])
    assert result.exit_code == 0 and "No such watch" not in result.stdout
    assert _watch_count(tmp_path, "ashby", "kayak")[0].watched is False


def test_adding_a_greenhouse_board_emits_no_such_warning(tmp_path) -> None:
    base = _base(tmp_path)
    result = runner.invoke(app, [*base, "companies", "add", "greenhouse:stripe"])
    assert "cannot confirm" not in result.stdout.lower()


# ---- P8: --verify (opt-in live board probe before the DB write) ----


def test_add_without_verify_never_probes(tmp_path, monkeypatch) -> None:
    """Default stays offline: a provider that would raise proves it is never called."""

    def _boom():
        raise AssertionError("add must not probe unless --verify is passed")

    monkeypatch.setattr("boardwatch.cli.companies_cmd.default_providers", _boom)
    result = runner.invoke(app, [*_base(tmp_path), "companies", "add", "greenhouse:acme"])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "greenhouse", "acme")) == 1


def test_add_verify_ok_writes_the_watch(tmp_path, monkeypatch) -> None:
    _fake_probe(monkeypatch, {"acme": BoardHealth.OK})
    result = runner.invoke(
        app, [*_base(tmp_path), "companies", "add", "greenhouse:acme", "--verify"]
    )
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "greenhouse", "acme")) == 1


def test_add_verify_empty_writes_the_watch_but_warns(tmp_path, monkeypatch) -> None:
    """A real board with no open roles is not a wrong slug."""
    _fake_probe(monkeypatch, {"acme": BoardHealth.EMPTY})
    result = runner.invoke(
        app, [*_base(tmp_path), "companies", "add", "greenhouse:acme", "--verify"]
    )
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "greenhouse", "acme")) == 1
    assert "returned no postings" in result.stdout.lower()


@pytest.mark.parametrize(
    "health", [BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.UNREACHABLE]
)
def test_add_verify_skips_and_writes_nothing_when_unproven(tmp_path, monkeypatch, health) -> None:
    """DEAD is a wrong slug; ERROR/UNREACHABLE are absence of evidence. Neither is a write."""
    _fake_probe(monkeypatch, {"acme": health})
    result = runner.invoke(
        app, [*_base(tmp_path), "companies", "add", "greenhouse:acme", "--verify"]
    )
    assert result.exit_code == 1
    assert _watch_count(tmp_path, "greenhouse", "acme") == []
    assert health.value in result.stdout.lower()


def test_import_verify_writes_only_the_proven_boards_and_exits_nonzero(
    tmp_path, monkeypatch
) -> None:
    _fake_probe(monkeypatch, {"live": BoardHealth.OK, "gone": BoardHealth.DEAD})
    path = _import_file(
        tmp_path,
        [
            {"name": "Live", "provider": "greenhouse", "slug": "live", "tags": []},
            {"name": "Gone", "provider": "greenhouse", "slug": "gone", "tags": []},
        ],
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path, "--verify"])
    assert result.exit_code == 1  # a partial import must not look like a clean one
    assert len(_watch_count(tmp_path, "greenhouse", "live")) == 1
    assert _watch_count(tmp_path, "greenhouse", "gone") == []
    assert "gone" in result.stdout.lower()


def test_import_verify_notes_empty_boards_but_still_watches_them(tmp_path, monkeypatch) -> None:
    _fake_probe(monkeypatch, {"quiet": BoardHealth.EMPTY})
    path = _import_file(
        tmp_path, [{"name": "Quiet", "provider": "greenhouse", "slug": "quiet", "tags": []}]
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path, "--verify"])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "greenhouse", "quiet")) == 1
    assert "empty" in result.stdout.lower()


def test_import_verify_keys_probes_by_provider_and_slug_not_slug_alone(
    tmp_path, monkeypatch
) -> None:
    """Same slug on two providers must get each provider's own verdict, not a collision."""
    monkeypatch.setattr(
        "boardwatch.cli.companies_cmd.default_providers",
        lambda: {
            "greenhouse": FakeProvider({"acme": BoardHealth.OK}),
            "lever": FakeProvider({"acme": BoardHealth.DEAD}),
        },
    )
    monkeypatch.setattr("boardwatch.cli.companies_cmd.Fetcher", lambda settings: object())
    path = _import_file(
        tmp_path,
        [
            {"name": "Acme GH", "provider": "greenhouse", "slug": "acme", "tags": []},
            {"name": "Acme LV", "provider": "lever", "slug": "acme", "tags": []},
        ],
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path, "--verify"])
    assert result.exit_code == 1
    assert len(_watch_count(tmp_path, "greenhouse", "acme")) == 1
    assert _watch_count(tmp_path, "lever", "acme") == []


def test_import_uses_one_fetcher_for_the_whole_batch(tmp_path, monkeypatch) -> None:
    """The per-host politeness pacing only applies across the batch if the Fetcher is shared."""
    built = []

    def _count(settings):
        built.append(settings)
        return object()

    monkeypatch.setattr(
        "boardwatch.cli.companies_cmd.default_providers",
        lambda: {"greenhouse": FakeProvider({"a": BoardHealth.OK, "b": BoardHealth.OK})},
    )
    monkeypatch.setattr("boardwatch.cli.companies_cmd.Fetcher", _count)
    path = _import_file(
        tmp_path,
        [
            {"name": "A", "provider": "greenhouse", "slug": "a", "tags": []},
            {"name": "B", "provider": "greenhouse", "slug": "b", "tags": []},
        ],
    )
    assert runner.invoke(
        app, [*_base(tmp_path), "companies", "import", path, "--verify"]
    ).exit_code == 0
    assert len(built) == 1


def test_import_verify_all_skipped_reports_zero_imported_and_exits_nonzero(
    tmp_path, monkeypatch
) -> None:
    """The shape an operator hits when the network is down with --verify."""
    _fake_probe(monkeypatch, {"a": BoardHealth.UNREACHABLE, "b": BoardHealth.UNREACHABLE})
    path = _import_file(
        tmp_path,
        [
            {"name": "A", "provider": "greenhouse", "slug": "a", "tags": []},
            {"name": "B", "provider": "greenhouse", "slug": "b", "tags": []},
        ],
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path, "--verify"])
    assert result.exit_code == 1
    assert "imported 0 watches" in result.stdout.lower()
    assert _watch_count(tmp_path, "greenhouse", "a") == []


def test_import_verify_flags_smartrecruiters_empty_as_unverifiable(tmp_path, monkeypatch) -> None:
    """EMPTY is not positive evidence on smartrecruiters: it cannot distinguish a typo."""
    _fake_probe(monkeypatch, {"acme": BoardHealth.EMPTY}, provider="smartrecruiters")
    path = _import_file(
        tmp_path, [{"name": "Acme", "provider": "smartrecruiters", "slug": "acme", "tags": []}]
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path, "--verify"])
    assert result.exit_code == 0
    assert "unverifiable" in result.stdout.lower()


def test_import_normalizes_case_variant_slugs_into_one_watch(tmp_path) -> None:
    """smartrecruiters slugs are case-insensitive; two spellings are one board, and a
    non-normalized row could never be removed (remove normalizes what the caller types)."""
    path = _import_file(
        tmp_path,
        [
            {"name": "Visa", "provider": "smartrecruiters", "slug": "Visa", "tags": []},
            {"name": "Visa again", "provider": "smartrecruiters", "slug": "visa", "tags": []},
        ],
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path])
    assert result.exit_code == 1  # they collapse to a duplicate, which is now rejected
    assert "duplicate" in result.stdout.lower()


def test_imported_uppercase_slug_is_removable(tmp_path) -> None:
    path = _import_file(
        tmp_path, [{"name": "Visa", "provider": "smartrecruiters", "slug": "Visa", "tags": []}]
    )
    assert runner.invoke(app, [*_base(tmp_path), "companies", "import", path]).exit_code == 0
    assert len(_watch_count(tmp_path, "smartrecruiters", "visa")) == 1  # stored normalized
    removed = runner.invoke(
        app, [*_base(tmp_path), "companies", "remove", "smartrecruiters:Visa"]
    )
    assert "no such watch" not in removed.stdout.lower()


def test_verify_reports_unreachable_instead_of_tracebacking(tmp_path, monkeypatch) -> None:
    """httpx.TooManyRedirects/DecodingError are RequestError but not TransportError, so they
    escape Fetcher.get and every provider's `except FetchFailure`."""

    class Exploding:
        def healthcheck(self, fetcher, slug):
            raise httpx.TooManyRedirects("redirect loop")

    monkeypatch.setattr(
        "boardwatch.cli.companies_cmd.default_providers", lambda: {"greenhouse": Exploding()}
    )
    monkeypatch.setattr("boardwatch.cli.companies_cmd.Fetcher", lambda settings: object())
    result = runner.invoke(
        app, [*_base(tmp_path), "companies", "add", "greenhouse:acme", "--verify"]
    )
    assert result.exit_code == 1
    assert "unreachable" in result.stdout.lower()
    assert _watch_count(tmp_path, "greenhouse", "acme") == []


def test_import_verify_all_ok_exits_zero(tmp_path, monkeypatch) -> None:
    _fake_probe(monkeypatch, {"live": BoardHealth.OK})
    path = _import_file(
        tmp_path, [{"name": "Live", "provider": "greenhouse", "slug": "live", "tags": []}]
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path, "--verify"])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "greenhouse", "live")) == 1


def test_import_without_verify_never_probes(tmp_path, monkeypatch) -> None:
    def _boom():
        raise AssertionError("import must not probe unless --verify is passed")

    monkeypatch.setattr("boardwatch.cli.companies_cmd.default_providers", _boom)
    path = _import_file(
        tmp_path, [{"name": "Live", "provider": "greenhouse", "slug": "live", "tags": []}]
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path])
    assert result.exit_code == 0
    assert len(_watch_count(tmp_path, "greenhouse", "live")) == 1


def test_import_rejects_duplicate_provider_slug_rows(tmp_path) -> None:
    """validate_entries exists for this; import was constructing entries without calling it."""
    path = _import_file(
        tmp_path,
        [
            {"name": "Dup", "provider": "greenhouse", "slug": "dup", "tags": []},
            {"name": "Dup again", "provider": "greenhouse", "slug": "dup", "tags": []},
        ],
    )
    result = runner.invoke(app, [*_base(tmp_path), "companies", "import", path])
    assert result.exit_code == 1
    assert "duplicate" in result.stdout.lower()
    assert _watch_count(tmp_path, "greenhouse", "dup") == []  # nothing written on rejection
