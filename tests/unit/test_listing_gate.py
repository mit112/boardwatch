"""D-663: the listing gate saves a fetch and a row, and never a lead or a closure.

Fixture titles are chosen by what the ranker's own vetoes say of them, so a clause's wording can
move without these moving, but the gate cannot start rejecting what the ranker keeps.
"""

import importlib
import json
from pathlib import Path

import httpx
import pytest
import respx
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, insert, select, text

from boardwatch.core.models import BoardRequest, BoardSnapshot, GatedListing
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider, _listing_fields
from boardwatch.rank.heuristic import ProfileView, hard_filter_verdict
from boardwatch.rank.listing_gate import build_listing_gate
from boardwatch.rank.role_gate import taxonomy_role_verdict
from boardwatch.rank.role_taxonomy import ROLE_TAXONOMY_FILE, RoleTaxonomy, parse_role_taxonomy
from boardwatch.reports.manifest import config_hash
from boardwatch.scan.coordinator import ScanSummary, _armed_listing_gate, _record_gated, run_scan
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import board_scans, companies, postings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "smartrecruiters"
PROVIDER = SmartRecruitersProvider()
BOARD = "https://api.smartrecruiters.com/v1/companies/acme/postings"
LIST_URL = f"{BOARD}?limit=100&offset=0"
KEEP_ID = "keep-1"
GATED_ID = "gated-1"


SOFTWARE = parse_role_taxonomy({"version": 1, "field": "software", "bundled": True})


def _profile(**overrides: object) -> ProfileView:
    fields: dict[str, object] = {
        "skills": frozenset(), "target_titles": (), "exclude_titles": ("Accountant",),
        "locations": (), "remote_only": False, "target_countries": ("USA",),
    }
    return ProfileView(**{**fields, **overrides})  # type: ignore[arg-type]


def _gate(taxonomy: RoleTaxonomy | None = None, mode: str = "hard", **overrides: object):  # type: ignore[no-untyped-def]
    return build_listing_gate(_profile(**overrides), taxonomy, mode)


@pytest.mark.parametrize(
    ("title", "locations", "remote", "reason"),
    [
        ("Senior Accountant", ["Austin, TX, USA"], "unknown", "excluded_title"),
        ("Software Engineer", ["Bengaluru, Karnataka, India"], "unknown", "non_us_location"),
        ("Software Engineer", ["Austin, TX, USA"], "unknown", None),
        # A listing that cannot say where the job is keeps the job.
        ("Software Engineer", ["2 Locations"], "unknown", None),
        ("Software Engineer", [], "unknown", None),
        ("", ["Bengaluru, Karnataka, India"], "unknown", None),
    ],
)
def test_the_gate_answers_from_the_listing_and_keeps_what_it_cannot_read(
    title: str, locations: list[str], remote: str, reason: str | None
) -> None:
    assert _gate()(title, locations, remote) == reason


def test_the_location_clause_stays_inert_in_soft_mode() -> None:
    assert _gate(mode="soft")("Software Engineer", ["Bengaluru, Karnataka, India"], "unknown") is None


def test_a_remote_only_profile_keeps_a_listing_that_does_not_state_its_remote_policy() -> None:
    gate = _gate(remote_only=True)
    assert gate("Software Engineer", ["Austin, TX, USA"], "unknown") is None
    assert gate("Software Engineer", ["Austin, TX, USA"], "onsite") == "remote_only"


def test_a_foreign_ad_marker_waits_for_the_location_only_the_detail_may_state() -> None:
    title = "Software Engineer (m/f/d)"
    profile = _profile(exclude_titles=())
    # The ranker's veto fires on this listing, and the detail's US location would rescue the job.
    assert hard_filter_verdict(title, [], "unknown", profile, "hard") is not None
    assert hard_filter_verdict(title, ["Austin, TX, USA"], "unknown", profile, "hard") is None
    assert build_listing_gate(profile, None, "hard")(title, [], "unknown") is None


def test_a_missing_taxonomy_abstains_rather_than_gates() -> None:
    title = "Registered Nurse"
    assert taxonomy_role_verdict(title, SOFTWARE)[0] == "out_of_field"
    assert _gate(taxonomy=None)(title, ["Austin, TX, USA"], "unknown") is None
    assert _gate(taxonomy=SOFTWARE)(title, ["Austin, TX, USA"], "unknown") == "out_of_field"


def test_the_gate_never_rejects_a_title_the_ranker_keeps() -> None:
    profile = _profile()
    for title in ("Software Engineer", "Member of Technical Staff", "Data Engineer I"):
        locations = ["Austin, TX, USA"]
        assert hard_filter_verdict(title, locations, "unknown", profile, "hard") is None
        assert build_listing_gate(profile, SOFTWARE, "hard")(title, locations, "unknown") is None


def _listing(posting_id: str, name: str) -> dict[str, object]:
    return {"id": posting_id, "name": name, "location": {"city": "Austin", "region": "TX", "country": "USA"}}


def _mock_board() -> dict[str, respx.Route]:
    content = [_listing(GATED_ID, "Senior Accountant"), _listing(KEEP_ID, "Software Engineer")]
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json={"totalFound": 2, "content": content})
    )
    detail = json.loads((FIXTURES / "detail_normal.json").read_text())
    routes = {}
    for entry in content:
        routes[str(entry["id"])] = respx.get(f"{BOARD}/{entry['id']}").mock(
            return_value=httpx.Response(200, json={**detail, **entry})
        )
    return routes


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_a_gated_listing_costs_no_fetch_no_budget_and_no_closure(tmp_path: Path) -> None:
    routes = _mock_board()
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)
    # A budget of ONE sits behind the gated row in listing order: spending it there starves the keeper.
    snap = PROVIDER.fetch_board(
        Fetcher(settings),
        BoardRequest(
            provider="smartrecruiters", slug="acme", url=LIST_URL, detail_budget=1,
            listing_gate=_gate(),
        ),
    )
    assert not routes[GATED_ID].called
    assert routes[KEEP_ID].called
    assert [p.provider_posting_id for p in snap.postings] == [KEEP_ID]
    assert snap.listed_ids == {GATED_ID, KEEP_ID}  # listed, so apply_board cannot close it
    assert snap.status == "complete"
    assert snap.detail_deferred == 0
    assert [(g.provider_posting_id, g.title, g.reason) for g in snap.gated_listings] == [
        (GATED_ID, "Senior Accountant", "excluded_title")
    ]


def _store(tmp_path: Path, exclude: list[str]) -> Engine:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        if conn.execute(select(companies.c.id)).first() is None:
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="smartrecruiters", slug="acme", source="user", watched=True
                )
            )
    _set_excludes(engine, exclude)
    return engine


def _set_excludes(engine: Engine, exclude: list[str]) -> None:
    with engine.begin() as conn:
        save_profile(
            conn, text="", target_titles=[], exclude_titles=exclude, locations=[], remote_only=False,
            skills=[], taxonomy_version="t", resume_max_pages=1, target_countries=["USA"],
        )


def _stored_ids(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(select(postings.c.provider_posting_id))}


@pytest.mark.usefixtures("no_real_sleep")
def test_changing_the_profile_drains_what_the_gate_held_back(tmp_path: Path) -> None:
    """The drain: nothing remembers a gated posting, so the next scan judges it afresh."""
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, per_host_delay_seconds=0.25,
        listing_gate=True, location_filter_mode="hard",
    )
    engine = _store(tmp_path, ["Accountant"])
    with respx.mock:
        routes = _mock_board()
        run_scan(engine, settings)
    assert not routes[GATED_ID].called
    assert _stored_ids(engine) == {KEEP_ID}
    with engine.connect() as conn:
        assert conn.execute(select(board_scans.c.listing_gated)).scalar_one() == 1
    audit = [json.loads(line) for line in (tmp_path / "listing_gated.jsonl").read_text().splitlines()]
    assert audit == [{
        "provider": "smartrecruiters", "slug": "acme", "provider_posting_id": GATED_ID,
        "title": "Senior Accountant", "reason": "excluded_title",
    }]

    _set_excludes(engine, [])
    with respx.mock:
        routes = _mock_board()
        run_scan(engine, settings)
    assert routes[GATED_ID].called
    assert _stored_ids(engine) == {GATED_ID, KEEP_ID}
    assert (tmp_path / "listing_gated.jsonl").read_text() == ""


@pytest.mark.usefixtures("no_real_sleep")
def test_an_unreadable_taxonomy_disarms_the_gate_rather_than_the_scan(tmp_path: Path) -> None:
    (tmp_path / ROLE_TAXONOMY_FILE).write_text("role_families: [")
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, per_host_delay_seconds=0.25,
        listing_gate=True,
    )
    engine = _store(tmp_path, ["Accountant"])
    with respx.mock:
        routes = _mock_board()
        run_scan(engine, settings)
    assert routes[GATED_ID].called
    assert _stored_ids(engine) == {GATED_ID, KEEP_ID}


@pytest.mark.usefixtures("no_real_sleep")
def test_a_fresh_install_gates_nothing_and_writes_no_audit_file(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, per_host_delay_seconds=0.25
    )
    assert settings.listing_gate is False
    engine = _store(tmp_path, ["Accountant"])
    with respx.mock:
        routes = _mock_board()
        run_scan(engine, settings)
    assert routes[GATED_ID].called
    assert _stored_ids(engine) == {GATED_ID, KEEP_ID}
    assert not (tmp_path / "listing_gated.jsonl").exists()
    with engine.connect() as conn:
        assert conn.execute(select(board_scans.c.listing_gated)).scalar_one() == 0


def test_the_provider_gives_the_gate_the_listings_location() -> None:
    row = _listing("india", "Software Engineer")
    row["location"] = {"city": "Bengaluru", "region": "Karnataka", "country": "India"}
    _, title, locations, remote = _listing_fields(row)
    assert locations == ["Bengaluru, Karnataka, India"]
    assert _gate()(title, locations, remote) == "non_us_location"


def test_the_provider_does_not_invent_a_remote_policy_the_listing_left_out() -> None:
    _, title, locations, remote = _listing_fields(_listing("unknown", "Software Engineer"))
    assert remote == "unknown"
    assert _gate(remote_only=True)(title, locations, remote) is None


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_a_known_posting_is_neither_judged_nor_fetched(tmp_path: Path) -> None:
    routes = _mock_board()
    snap = PROVIDER.fetch_board(
        Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)),
        BoardRequest(
            provider="smartrecruiters", slug="acme", url=LIST_URL,
            known_posting_ids=frozenset({GATED_ID}), listing_gate=_gate(),
        ),
    )
    assert not routes[GATED_ID].called
    assert snap.gated_listings == ()
    assert GATED_ID in snap.listed_ids


def test_no_profile_leaves_the_gate_unarmed(tmp_path: Path) -> None:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, listing_gate=True)
    with engine.connect() as conn:
        assert _armed_listing_gate(conn, settings) is None
    assert not (tmp_path / "listing_gated.jsonl").exists()


def test_the_scan_builds_the_gate_with_the_configured_location_mode(tmp_path: Path) -> None:
    engine = _store(tmp_path, [])
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, listing_gate=True, location_filter_mode="soft"
    )
    with engine.connect() as conn:
        gate = _armed_listing_gate(conn, settings)
    assert gate is not None
    assert gate("Software Engineer", ["Bengaluru, Karnataka, India"], "unknown") is None


def test_the_audit_keeps_every_boards_rows_and_counts_them_by_reason(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path)
    summary = ScanSummary()
    snap = BoardSnapshot(
        status="complete", postings=[], url=LIST_URL,
        gated_listings=(GatedListing("1", "Accountant", "excluded_title"),),
    )
    _record_gated(settings, summary, "first", "smartrecruiters", snap)
    _record_gated(settings, summary, "second", "smartrecruiters", snap)
    audit = (tmp_path / "listing_gated.jsonl").read_text().splitlines()
    assert [json.loads(line)["slug"] for line in audit] == ["first", "second"]
    assert summary.listing_gated == {"excluded_title": 2}


@pytest.mark.usefixtures("no_real_sleep")
def test_a_failed_board_records_its_gated_count_as_not_measured(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1, per_host_delay_seconds=0.25,
        listing_gate=True,
    )
    engine = _store(tmp_path, ["Accountant"])
    with respx.mock:
        respx.get(LIST_URL).mock(return_value=httpx.Response(500))
        run_scan(engine, settings)
    with engine.connect() as conn:
        row = conn.execute(select(board_scans.c.status, board_scans.c.listing_gated)).one()
    assert row.status == "failed"
    assert row.listing_gated is None


def test_the_migration_leaves_old_scans_unmeasured_and_reverses(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    cfg = Config()
    cfg.set_main_option("script_location", "src/boardwatch/store/migrations")
    cfg.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)
    command.upgrade(cfg, "p_corpus_indexes")
    t = "2026-01-01 00:00:00"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO runs (id, started_at, boards_attempted) VALUES (1, :t, 0)"), {"t": t}
        )
        conn.execute(
            text(
                "INSERT INTO companies (id, name, provider, slug, source, watched) "
                "VALUES (1, 'Acme', 'smartrecruiters', 'acme', 'user', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO board_scans (run_id, company_id, started_at, finished_at, status, "
                "postings_listed, scan_kind) VALUES (1, 1, :t, :t, 'complete', 1, 'board')"
            ),
            {"t": t},
        )
    command.upgrade(cfg, "p_listing_gated")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT listing_gated FROM board_scans")).scalar_one() is None
    command.downgrade(cfg, "p_corpus_indexes")
    with engine.connect() as conn:
        columns = {r[1] for r in conn.execute(text("PRAGMA table_info(board_scans)"))}
    assert "listing_gated" not in columns


def test_arming_the_gate_does_not_move_the_config_hash(tmp_path: Path) -> None:
    off = Settings(data_dir=tmp_path, config_dir=tmp_path, listing_gate=False)
    on = Settings(data_dir=tmp_path, config_dir=tmp_path, listing_gate=True)
    assert config_hash(off) == config_hash(on)


@pytest.mark.usefixtures("no_real_sleep")
@respx.mock
def test_a_malformed_listing_reaches_detail_and_fails_nothing_else(tmp_path: Path) -> None:
    routes = _mock_board()
    malformed = {"id": "bad", "name": "Software Engineer", "location": "Austin"}
    content = [malformed, _listing(GATED_ID, "Senior Accountant"), _listing(KEEP_ID, "Software Engineer")]
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(200, json={"totalFound": 3, "content": content})
    )
    detail = json.loads((FIXTURES / "detail_normal.json").read_text())
    route = respx.get(f"{BOARD}/bad").mock(
        return_value=httpx.Response(200, json={**detail, "id": "bad", "name": "Software Engineer"})
    )
    snap = PROVIDER.fetch_board(
        Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1)),
        BoardRequest(provider="smartrecruiters", slug="acme", url=LIST_URL, listing_gate=_gate()),
    )
    assert route.called
    assert routes[KEEP_ID].called
    assert not routes[GATED_ID].called
    assert {p.provider_posting_id for p in snap.postings} == {"bad", KEEP_ID}


def test_an_audit_file_it_cannot_write_disarms_the_gate(tmp_path: Path) -> None:
    (tmp_path / "listing_gated.jsonl").mkdir()  # any write to this path raises an OSError
    engine = _store(tmp_path, ["Accountant"])
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, listing_gate=True)
    with engine.connect() as conn:
        assert _armed_listing_gate(conn, settings) is None


def test_a_taxonomy_it_cannot_read_disarms_the_gate(tmp_path: Path) -> None:
    (tmp_path / ROLE_TAXONOMY_FILE).write_bytes(b"\xff\xfe")
    engine = _store(tmp_path, ["Accountant"])
    settings = Settings(data_dir=tmp_path, config_dir=tmp_path, listing_gate=True)
    with engine.connect() as conn:
        assert _armed_listing_gate(conn, settings) is None


def test_an_audit_write_that_fails_costs_the_trace_and_not_the_scan(tmp_path: Path) -> None:
    (tmp_path / "listing_gated.jsonl").mkdir()
    summary = ScanSummary()
    snap = BoardSnapshot(
        status="complete", postings=[], url=LIST_URL,
        gated_listings=(GatedListing("1", "Accountant", "excluded_title"),),
    )
    _record_gated(Settings(data_dir=tmp_path, config_dir=tmp_path), summary, "s", "p", snap)
    assert summary.listing_gated == {"excluded_title": 1}
    assert [e.split(":")[0] for e in summary.errors] == ["listing gate audit"]


@pytest.mark.parametrize(
    ("name", "row"),
    [
        ("workday", ("1", {})),
        ("oraclehcm", {"Id": "1"}),
        ("eightfold", {"id": "1"}),
        ("phenom", ("1", {})),
        ("apple", {"positionId": "1"}),
        ("smartrecruiters", {"id": "1"}),
    ],
)
def test_a_listing_that_states_nothing_gives_the_gate_nothing_to_veto(
    name: str, row: object
) -> None:
    fields = importlib.import_module(f"boardwatch.providers.{name}")._listing_fields(row)
    assert fields == ("1", "", [], "unknown")
