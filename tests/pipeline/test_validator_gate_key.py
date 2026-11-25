"""T355: a stored validator is sent only under the listing gate it was learned under.

SmartRecruiters' list answers 304 exactly when `If-None-Match` matches, and a 304 skips the gate
and the board's inventory. Gate A rejects row R (an excluded title) unstored and the board's ETag
is persisted. Before this change a later scan under gate B, which keeps R, sent that ETag, got a
304 and never saw R. Each pass opens a fresh engine on the same store, as a new process would.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.providers.registry import build_providers
from boardwatch.scan.coordinator import run_scan
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "smartrecruiters"
SR = build_providers()["smartrecruiters"]
GH = build_providers()["greenhouse"]
R = "744000000000003"  # "Warehouse Associate": gate A excludes it, gate B keeps it
ETAG = '"v1"'


def test_a_provider_declares_gates_listings_exactly_when_it_applies_the_gate() -> None:
    for name, provider in build_providers().items():
        source = inspect.getsource(inspect.getmodule(provider))  # type: ignore[arg-type]
        gates = "apply_listing_gate(" in source
        assert bool(getattr(provider, "gates_listings", False)) == gates, name


def _store(data: Path, *, exclude: list[str]) -> None:
    engine = get_engine(data)
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(insert(tables.companies).values(
            name="Acme", provider="smartrecruiters", slug="acme", source="user", watched=True
        ))
        conn.execute(insert(tables.companies).values(
            name="Gh", provider="greenhouse", slug="gh", source="user", watched=True
        ))
        conn.execute(insert(tables.profile).values(
            text="Engineer.", exclude_titles_json=exclude, updated_at=utcnow()
        ))
    engine.dispose()


def _gate(data: Path, exclude: list[str]) -> None:
    engine = get_engine(data)
    with engine.begin() as conn:
        conn.execute(update(tables.profile).values(exclude_titles_json=exclude))
    engine.dispose()


def _pass(data: Path, *, gate: bool = True) -> dict[str, Any]:
    """One scan on a fresh engine. Returns what was sent and fetched."""
    listing = json.loads((FIXTURES / "list_normal.json").read_text())
    detail = json.loads((FIXTURES / "detail_normal.json").read_text())
    sent: dict[str, str | None] = {}

    def conditional(board: str, body: bytes):  # type: ignore[no-untyped-def]
        def respond(request: httpx.Request) -> httpx.Response:
            sent[board] = request.headers.get("If-None-Match")
            if sent[board] == ETAG:
                return httpx.Response(304)
            return httpx.Response(200, content=body, headers={"ETag": ETAG})
        return respond

    engine = get_engine(data)
    settings = load_settings(data_dir=data).model_copy(update={"listing_gate": gate})
    with respx.mock(assert_all_called=False) as mock:
        mock.get(SR.board_url("acme")).mock(
            side_effect=conditional("acme", json.dumps(listing).encode())
        )
        mock.get(GH.board_url("gh")).mock(side_effect=conditional("gh", json.dumps({"jobs": [
            {"id": 9, "title": "Engineer", "absolute_url": "https://example.test/9",
             "content": "Python."},
        ]}).encode()))
        details = {}
        for row in listing["content"]:
            body = {**detail, "id": row["id"], "name": row["name"], "location": row["location"]}
            url = f"https://api.smartrecruiters.com/v1/companies/acme/postings/{row['id']}"
            details[row["id"]] = mock.get(url).mock(return_value=httpx.Response(200, json=body))
        run_scan(engine, settings)
    with engine.connect() as conn:
        rows = conn.execute(select(tables.postings.c.provider_posting_id, tables.postings.c.status,
                                   tables.postings.c.consecutive_missing)).all()
    engine.dispose()
    return {
        "sent": sent,
        "details": {pid: route.call_count for pid, route in details.items()},
        "postings": {r.provider_posting_id: (r.status, r.consecutive_missing) for r in rows},
    }


def _unchanged_inventory(*passes: dict[str, Any]) -> None:
    for result in passes:
        assert all(state == ("open", 0) for state in result["postings"].values()), result


@pytest.mark.usefixtures("no_real_sleep")
def test_a_row_the_old_gate_rejected_is_recovered_on_the_next_pass_then_reused(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    _store(data, exclude=["warehouse"])

    first = _pass(data)  # gate A
    assert first["details"][R] == 0 and R not in first["postings"]

    _gate(data, [])  # gate B keeps R
    second = _pass(data)
    assert second["sent"]["acme"] is None  # learned under A: not sent under B
    assert second["details"][R] == 1 and R in second["postings"]  # recovered on the second pass

    third = _pass(data)
    assert third["sent"]["acme"] == ETAG  # learned under B: reused under B
    assert sum(third["details"].values()) == 0  # 304: no detail read at all
    _unchanged_inventory(first, second, third)


@pytest.mark.usefixtures("no_real_sleep")
def test_gate_on_then_off_sends_no_validator_on_the_first_ungated_pass(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _store(data, exclude=["warehouse"])
    _pass(data, gate=True)
    ungated = _pass(data, gate=False)
    assert ungated["sent"]["acme"] is None
    assert ungated["details"][R] == 1
    assert _pass(data, gate=False)["sent"]["acme"] == ETAG


@pytest.mark.usefixtures("no_real_sleep")
def test_a_legacy_row_with_no_key_is_read_in_full_once_then_reused(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _store(data, exclude=["warehouse"])
    _pass(data)
    engine = get_engine(data)
    with engine.begin() as conn:
        conn.execute(update(tables.http_cache).values(gate_key=None))
    engine.dispose()
    assert _pass(data)["sent"]["acme"] is None  # same gate, but the row predates the key
    assert _pass(data)["sent"]["acme"] == ETAG


@pytest.mark.usefixtures("no_real_sleep")
def test_a_non_gating_provider_keeps_its_validator_across_a_gate_change(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _store(data, exclude=["warehouse"])
    _pass(data)
    _gate(data, [])
    assert _pass(data)["sent"]["gh"] == ETAG  # Greenhouse stores every row: no gate to bind
