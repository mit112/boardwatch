"""The apply route: which list a lead belongs in, from its apply URL and the owner's own ledgers.

Expected values come from the owner's rulings (2026-11-03), never from the classifier: a known fill
host is `auto`; an unchecked job-board link is `unresolved`; a finished check with no employer link
is `auto` on a board with its own form; a moved lead stays by hand whatever its host.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext, queue_payload
from boardwatch.delivery.apply_routes import ApplyRoute, load_apply_routes
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queue_state import mark_job_manual
from boardwatch.store.tables import postings
from tests.unit.test_web_server import NOW, _deliver

NONE_LINK, AGGREGATOR_LINK, LIVE_LINK, UNCHECKED = 21, 22, 23, 24


def _configure(config_dir: Path, *, extra: str = "") -> None:
    # A path goes in a TOML literal string ('...'): in a basic string ("...") the backslashes of a
    # Windows path read as escapes (`\U` is a Unicode escape) and the file does not parse.
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "links.json").write_text(
        json.dumps(
            {
                str(NONE_LINK): {"company_status": "none"},
                str(AGGREGATOR_LINK): {"company_status": "aggregator"},
                str(LIVE_LINK): {"company_status": "live"},
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "apply-routes.toml").write_text(
        f"""
auto_hosts = ["ashbyhq.com", "job-boards.greenhouse.io"]
unresolved_hosts = ["linkedin.com", "jobright.ai"]
unresolved_url_markers = ["gh_jid="]
native_fill_hosts = ["linkedin.com"]
link_ledgers = ['{config_dir / "links.json"}']
no_employer_statuses = ["none", "aggregator"]
{extra}
""",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("posting_id", "url", "expected"),
    [
        (1, "https://jobs.ashbyhq.com/acme/1", ApplyRoute.AUTO),
        (1, "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=1", ApplyRoute.AUTO),
        (1, "https://acme.wd5.myworkdayjobs.com/x/job/1", ApplyRoute.HAND),
        (1, "https://app.joinhandshake.com/jobs/12345678", ApplyRoute.HAND),
        # A host only counts as itself or its own subdomain, never by resembling one.
        (1, "https://notashbyhq.com/x", ApplyRoute.HAND),
        (1, "https://evil.example/?u=https://jobs.ashbyhq.com/acme/1", ApplyRoute.HAND),
        # The marker means a company page embedding an ATS. On a fill host the form is right there.
        (1, "https://job-boards.greenhouse.io/acme/jobs/1?gh_jid=1", ApplyRoute.AUTO),
        (1, "https://acme.com/careers/1?gh_jid=9", ApplyRoute.UNRESOLVED),
        # The check finished without finding the form behind the company page: only the owner can apply.
        (NONE_LINK, "https://acme.com/careers/1?gh_jid=9", ApplyRoute.HAND),
        # A job board is unresolved until its check finishes with no employer link.
        (UNCHECKED, "https://www.linkedin.com/jobs/view/1", ApplyRoute.UNRESOLVED),
        (LIVE_LINK, "https://www.linkedin.com/jobs/view/1", ApplyRoute.UNRESOLVED),
        (NONE_LINK, "https://www.linkedin.com/jobs/view/1", ApplyRoute.AUTO),
        (AGGREGATOR_LINK, "https://www.linkedin.com/jobs/view/1", ApplyRoute.AUTO),
        # No employer link, and this board has no form of its own: only the owner can apply.
        (NONE_LINK, "https://jobright.ai/jobs/info/1", ApplyRoute.HAND),
        (1, None, ApplyRoute.UNRESOLVED),
        (1, "not a url", ApplyRoute.UNRESOLVED),
        (1, "https://[bad/", ApplyRoute.UNRESOLVED),
    ],
)
def test_the_route_of_a_lead(
    tmp_path: Path, posting_id: int, url: str | None, expected: ApplyRoute
) -> None:
    _configure(tmp_path)
    routes = load_apply_routes(tmp_path)
    assert routes.problem is None
    assert routes.route(posting_id=posting_id, apply_url=url) is expected


@pytest.mark.skipif(
    sys.platform == "win32", reason="a Windows file name cannot contain a backslash"
)
def test_a_config_dir_whose_path_has_backslashes_still_loads(tmp_path: Path) -> None:
    """On POSIX a backslash is an ordinary file-name character, so this builds the path shape a
    Windows runner has (`C:\\Windows\\...`) and guards `_configure`'s TOML quoting on every other OS."""
    config_dir = tmp_path / r"C:\Windows\Temp\Runner"
    _configure(config_dir)
    routes = load_apply_routes(config_dir)
    assert routes.problem is None
    assert routes.route(posting_id=NONE_LINK, apply_url="https://www.linkedin.com/jobs/view/1") is (
        ApplyRoute.AUTO
    )


def test_no_file_is_unconfigured_and_routes_nothing_automatically(tmp_path: Path) -> None:
    routes = load_apply_routes(tmp_path)
    assert (routes.configured, routes.problem) == (False, None)
    assert routes.route(posting_id=1, apply_url="https://jobs.ashbyhq.com/a/1") is ApplyRoute.HAND


def test_a_misspelled_key_is_reported_rather_than_ignored(tmp_path: Path) -> None:
    _configure(tmp_path, extra='auto_host = ["x.example"]')
    routes = load_apply_routes(tmp_path)
    assert not routes.configured
    assert "auto_host" in (routes.problem or "")


def test_an_unreadable_link_ledger_leaves_its_leads_unresolved_and_says_so(tmp_path: Path) -> None:
    _configure(tmp_path)
    (tmp_path / "links.json").write_text("{broken", encoding="utf-8")
    routes = load_apply_routes(tmp_path)
    assert "links.json" in (routes.problem or "")
    url = "https://www.linkedin.com/jobs/view/1"
    assert routes.route(posting_id=NONE_LINK, apply_url=url) is ApplyRoute.UNRESOLVED


@pytest.fixture()
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Engine, ApiContext, Path]:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    (tmp_path / "out").mkdir()
    (tmp_path / "queue").mkdir()
    ctx = ApiContext(
        settings=load_settings(),
        out_root=(tmp_path / "out").resolve(),
        queue_root=(tmp_path / "queue").resolve(),
        owner_name="Example Owner",
        platform="darwin",
    )
    return engine, ctx, config_dir


def _deliver_on(engine: Engine, key: str, url: str, *, moved: bool = False) -> int:
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, key)
        conn.execute(postings.update().where(postings.c.id == posting_id).values(url=url))
        if moved:
            mark_job_manual(conn, job_id=job_id, at=NOW)
    return posting_id


def test_the_queue_serves_each_row_its_route_and_a_moved_lead_stays_by_hand(
    served: tuple[Engine, ApiContext, Path],
) -> None:
    engine, ctx, config_dir = served
    auto = _deliver_on(engine, "auto", "https://jobs.ashbyhq.com/a/1")
    moved = _deliver_on(engine, "moved", "https://jobs.ashbyhq.com/a/2", moved=True)
    _configure(config_dir)

    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)

    assert [r["posting_id"] for r in payload["manual"]] == [moved]
    assert payload["manual"][0]["apply_route"] == "hand"
    row = next(r for r in payload["rows"] + payload["review"] if r["posting_id"] == auto)
    assert row["apply_route"] == "auto"
    assert payload["apply_routes"] == {"configured": True, "problem": None}


def test_the_queue_without_the_file_serves_the_fresh_machine_default(
    served: tuple[Engine, ApiContext, Path],
) -> None:
    engine, ctx, _ = served
    posting = _deliver_on(engine, "plain", "https://jobs.ashbyhq.com/a/1")
    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)
    row = next(r for r in payload["rows"] + payload["review"] if r["posting_id"] == posting)
    assert row["apply_route"] == "hand"
    assert payload["apply_routes"] == {"configured": False, "problem": None}


# ------------------------------------------------------------------- account walls (plan 02)

WALL_HOST = "wall.example"


def test_an_account_wall_host_routes_by_hand_and_says_why(tmp_path: Path) -> None:
    """A host the owner listed as an account wall is by hand, and the viewer can say which host."""
    _configure(tmp_path, extra=f'account_wall_hosts = ["{WALL_HOST}"]')
    routes = load_apply_routes(tmp_path)
    assert routes.problem is None
    url = "https://acme.wd5.wall.example/x/job/1"
    assert routes.route(posting_id=1, apply_url=url) is ApplyRoute.HAND
    assert routes.reason(posting_id=1, apply_url=url) == f"needs an account on {WALL_HOST}"


@pytest.mark.parametrize(
    ("url", "is_wall"),
    [
        ("https://acme.wall.example/x/job/1", True),  # the listed host itself
        ("https://acme.wd5.wall.example/x/job/1", True),  # a subdomain of it
        ("https://notwall.example/x/job/1", False),  # resembling it is not being it
        ("https://wall.example.evil.example/x", False),  # nor is it a prefix of a longer name
        ("https://jobs.ashbyhq.com/acme/1", False),
    ],
)
def test_only_the_listed_host_or_its_subdomains_is_a_wall(tmp_path: Path, url: str, is_wall: bool) -> None:
    _configure(tmp_path, extra=f'account_wall_hosts = ["{WALL_HOST}"]')
    routes = load_apply_routes(tmp_path)
    assert (routes.reason(posting_id=1, apply_url=url) is not None) is is_wall


def test_an_account_wall_host_that_is_also_a_fill_host_is_refused(tmp_path: Path) -> None:
    """One host, two contradictory answers: `route()` and `is_direct_auto()` would disagree."""
    _configure(tmp_path, extra=f'account_wall_hosts = ["{WALL_HOST}", "ashbyhq.com"]')
    routes = load_apply_routes(tmp_path)
    assert not routes.configured
    assert "ashbyhq.com" in (routes.problem or "")


def test_an_account_wall_host_that_is_also_an_unresolved_host_is_refused(tmp_path: Path) -> None:
    """A host named as both unresolved and walled is the same ambiguity, against the other list."""
    _configure(tmp_path, extra=f'account_wall_hosts = ["{WALL_HOST}", "linkedin.com"]')
    routes = load_apply_routes(tmp_path)
    assert not routes.configured
    assert "linkedin.com" in (routes.problem or "")


def test_a_wall_subdomain_that_shadows_a_fill_host_is_refused_too(tmp_path: Path) -> None:
    """`route()` and `is_direct_auto()` would disagree about this config, so it never loads."""
    (tmp_path / "apply-routes.toml").write_text(
        'auto_hosts = ["example.com"]\naccount_wall_hosts = ["careers.example.com"]\n',
        encoding="utf-8",
    )
    routes = load_apply_routes(tmp_path)
    assert not routes.configured
    assert "careers.example.com" in (routes.problem or "")
    # A refused config routes nothing automatically, even on the host that would have been `auto`.
    assert routes.route(posting_id=1, apply_url="https://jobs.example.com/a/1") is ApplyRoute.HAND


def test_a_wall_parent_that_shadows_a_fill_subdomain_is_refused_too(tmp_path: Path) -> None:
    """The overlap is asked both ways: a wall parent covers a fill host below it."""
    (tmp_path / "apply-routes.toml").write_text(
        'auto_hosts = ["careers.example.com"]\naccount_wall_hosts = ["example.com"]\n',
        encoding="utf-8",
    )
    routes = load_apply_routes(tmp_path)
    assert not routes.configured
    assert "example.com" in (routes.problem or "")


def test_a_wall_host_wins_over_an_unresolved_embedding_marker(tmp_path: Path) -> None:
    """Without the wall branch this URL is UNRESOLVED (an embed marker with no finished check)."""
    _configure(tmp_path, extra=f'account_wall_hosts = ["{WALL_HOST}"]')
    routes = load_apply_routes(tmp_path)
    url = f"https://acme.{WALL_HOST}/careers/1?gh_jid=9"
    assert routes.route(posting_id=UNCHECKED, apply_url=url) is ApplyRoute.HAND


def test_no_account_wall_list_means_no_wall_and_no_reason(tmp_path: Path) -> None:
    _configure(tmp_path)
    routes = load_apply_routes(tmp_path)
    url = "https://acme.wd5.wall.example/x/job/1"
    assert routes.route(posting_id=1, apply_url=url) is ApplyRoute.HAND
    assert routes.reason(posting_id=1, apply_url=url) is None


def test_the_manual_list_carries_the_reason_too(
    served: tuple[Engine, ApiContext, Path],
) -> None:
    """A lead the owner moved by hand keeps the reason, so the list never reads as unexplained."""
    engine, ctx, config_dir = served
    walled = _deliver_on(engine, "moved-wall", f"https://acme.wd5.{WALL_HOST}/x/job/1", moved=True)
    _configure(config_dir, extra=f'account_wall_hosts = ["{WALL_HOST}"]')
    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)
    row = next(r for r in payload["manual"] if r["posting_id"] == walled)
    assert row["apply_route"] == "hand"
    assert row["apply_route_reason"] == f"needs an account on {WALL_HOST}"


def test_the_queue_serves_the_reason_on_the_row_that_has_one(
    served: tuple[Engine, ApiContext, Path],
) -> None:
    engine, ctx, config_dir = served
    walled = _deliver_on(engine, "walled", f"https://acme.wd5.{WALL_HOST}/x/job/1")
    plain = _deliver_on(engine, "plain", "https://jobs.ashbyhq.com/a/1")
    _configure(config_dir, extra=f'account_wall_hosts = ["{WALL_HOST}"]')

    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)

    rows = {row["posting_id"]: row for row in payload["rows"] + payload["review"]}
    assert rows[walled]["apply_route"] == "hand"
    assert rows[walled]["apply_route_reason"] == f"needs an account on {WALL_HOST}"
    assert rows[plain]["apply_route"] == "auto"
    assert rows[plain]["apply_route_reason"] is None
