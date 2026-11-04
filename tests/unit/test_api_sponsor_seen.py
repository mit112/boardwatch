"""`sponsor_seen` on a served queue row: what the badge's tooltip needs, else null.

Null for no record, for a profile that does not declare `needs_sponsorship`, and for a missing or
unusable index. A present value is evidence an employer filed, never a promise to sponsor; its
absence is evidence of nothing. Counts below are the fixture's own numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext, detail_payload, queue_payload
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact
from boardwatch.rank.sponsors import SPONSORS_FILENAME
from boardwatch.store.db import ensure_schema, get_engine
from tests.unit.test_web_server import _deliver

NEEDS = Facts(work_authorization=WorkAuthFact(
    status="ead_or_similar", jurisdiction="us", needs_sponsorship=True))
NOT_NEEDED = Facts(work_authorization=WorkAuthFact(
    status="citizen", jurisdiction="us", needs_sponsorship=False))
UNDECLARED = Facts(work_authorization=WorkAuthFact(status="ead_or_similar", jurisdiction="us"))
EXPECTED = {"computing_rows": 7, "computing_low_wage_rows": 2, "latest_decision": "2026-03-01"}


@pytest.fixture()
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Engine, ApiContext, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
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


def _index(config_dir: Path, *keys: str) -> None:
    record = {
        "name": "Acme hit Inc.", "feins": ["11-1111111"], "certified_rows": 9,
        "computing_rows": 7, "computing_new_employment_rows": 3,
        "computing_low_wage_rows": 2, "secondary_entity_rows": 0, "naics2": "54",
        "state": "CA", "latest_decision": "2026-03-01",
    }
    (config_dir / SPONSORS_FILENAME).write_text(json.dumps(
        {"format": 1, "built": "2026-11-04", "sources": [],
         "employers": {key: record for key in keys}}))


def _deliver_pair(engine: Engine, facts: Facts) -> tuple[int, int]:
    with engine.begin() as conn:
        hit, _ = _deliver(conn, "hit", facts=facts, policy=Policy())
        miss, _ = _deliver(conn, "miss", facts=facts, policy=Policy())
    return hit, miss


def _served(engine: Engine, ctx: ApiContext) -> dict[int, dict[str, object]]:
    with engine.connect() as conn:
        payload = queue_payload(conn, ctx)
    return {r["posting_id"]: r for r in payload["rows"] + payload["review"] + payload["manual"]}


def test_exact_hit_carries_the_counts_and_a_miss_is_null(
    served: tuple[Engine, ApiContext, Path],
) -> None:
    engine, ctx, config_dir = served
    hit, miss = _deliver_pair(engine, NEEDS)
    # "acme hitter" is a longer name: an exact match must not reach it, nor "acme miss".
    _index(config_dir, "acme hit", "acme hitter")
    rows = _served(engine, ctx)
    assert rows[hit]["sponsor_seen"] == EXPECTED
    assert rows[miss]["sponsor_seen"] is None


def test_the_detail_row_carries_it_too(served: tuple[Engine, ApiContext, Path]) -> None:
    engine, ctx, config_dir = served
    hit, miss = _deliver_pair(engine, NEEDS)
    _index(config_dir, "acme hit")
    with engine.connect() as conn:
        found = detail_payload(conn, ctx, hit)
        missed = detail_payload(conn, ctx, miss)
    assert found is not None and found["row"]["sponsor_seen"] == EXPECTED
    assert missed is not None and missed["row"]["sponsor_seen"] is None


@pytest.mark.parametrize("facts", [NOT_NEEDED, UNDECLARED])
def test_null_when_the_profile_does_not_need_sponsorship(
    served: tuple[Engine, ApiContext, Path], facts: Facts
) -> None:
    engine, ctx, config_dir = served
    hit, _ = _deliver_pair(engine, facts)
    _index(config_dir, "acme hit")
    assert _served(engine, ctx)[hit]["sponsor_seen"] is None


@pytest.mark.parametrize("content", [None, "{broken"])
def test_null_when_the_index_is_missing_or_unusable(
    served: tuple[Engine, ApiContext, Path], content: str | None
) -> None:
    engine, ctx, config_dir = served
    hit, miss = _deliver_pair(engine, NEEDS)
    if content is not None:
        (config_dir / SPONSORS_FILENAME).write_text(content)
    rows = _served(engine, ctx)
    assert rows[hit]["sponsor_seen"] is None
    assert rows[miss]["sponsor_seen"] is None
