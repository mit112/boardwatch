"""The opt-in LLM lane: advisory, structurally non-blocking, never `ineligible`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.core.secrets import LLM_API_KEY_ENV
from boardwatch.core.settings import LLMTier, Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.extract_llm import LANE_VERSION, extract_and_record
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.factory import build_client
from boardwatch.llm.prompt import PROMPT_VERSION
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import get_evaluations, get_requirements

JD_5YR = (
    "We need a backend engineer with a minimum of 5 years of experience. "
    "Salary range: $100k-$150k."
)
EXPERIENCE_QUOTE = "minimum of 5 years"
SALARY_QUOTE = "Salary range: $100k-$150k"


class FakeClient:
    """A ModelClient that returns canned JSON without any network call."""

    def __init__(self, body: str, *, model: str = "fake-model", provider: str = "fake-provider"):
        self.body = body
        self.model = model
        self.provider = provider

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.body


class RaisingClient:
    """A ModelClient whose complete() always fails, simulating a provider error."""

    model = "fake-model"

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
        )
    assert eval_id is not None

    with engine.connect() as conn:
        rows = get_evaluations(conn, pv_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.engine_kind == "llm"
    assert row.engine_version == LANE_VERSION
    assert row.prompt_version == PROMPT_VERSION
    assert row.provider == "fake-provider"
    assert row.model == "fake-model"
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
