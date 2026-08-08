"""The LLM eligibility lane's cache key must fold in profile + catalog identity.

`ResponseCache.key(content_hash, prompt_version, model)` is keyed by the JD text alone.
Reused unchanged for the eligibility lane, a cached raw response would replay across a
CHANGED profile or a CHANGED rule catalog — the same JD adjudicated against different facts
or a different catalog version would wrongly HIT. The lane folds `profile_hash` + `rules_hash`
into the `content_hash` argument at its own call site so either change is a cache MISS.

The tailor rewrite lane (`tailor/rewrite/lane.py`) shares `ResponseCache.key` but is bullet
rewording, not eligibility, and must keep its identity-free key — so the fix is at the call
site, never in `ResponseCache.key` itself.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import Engine

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.extract_llm import extract_and_record
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.llm.cache import ResponseCache
from boardwatch.store.db import ensure_schema, get_engine
from tests.pipeline.test_llm_lane import EXPERIENCE_QUOTE, JD_5YR, _seed_posting_version

# experience_years pinned to `blocker` so it is an ENABLED family: build_identity then folds
# total_years_experience into profile_hash, which is what makes two different facts two
# different cache keys.
POLICY = Policy(families={"experience_years": "blocker"})
BODY = json.dumps([{"family": "experience_years", "span_quote": EXPERIENCE_QUOTE}])


class CountingClient:
    """A ModelClient that counts how many times the provider was actually called."""

    def __init__(self, body: str) -> None:
        self.body = body
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return self.body


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(tmp_path / "cache")


def _run(engine: Engine, cache: ResponseCache, client: CountingClient, catalog, facts, *, slug):
    pv_id = _seed_posting_version(engine, JD_5YR, slug=slug)
    with engine.begin() as conn:
        extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=POLICY,
            catalog=catalog, client=client, cache=cache, provider="anthropic", model="m",
        )


def test_same_jd_but_different_profile_is_a_cache_miss(
    engine: Engine, cache: ResponseCache, tmp_path: Path
) -> None:
    """The bug: the old content-only key would HIT and replay the first profile's response
    for the second profile. With profile_hash folded in, the second call MISSES and the
    provider is called again."""
    catalog = load_rules(tmp_path / "no-cfg")
    client = CountingClient(BODY)
    _run(engine, cache, client, catalog, Facts(total_years_experience=5), slug="a")
    _run(engine, cache, client, catalog, Facts(total_years_experience=10), slug="b")
    assert client.calls == 2


def test_same_jd_and_profile_and_catalog_is_a_cache_hit(
    engine: Engine, cache: ResponseCache, tmp_path: Path
) -> None:
    """The fix must not defeat caching: identical JD, facts, and catalog still HIT on the
    second call, so the provider is called exactly once."""
    catalog = load_rules(tmp_path / "no-cfg")
    client = CountingClient(BODY)
    facts = Facts(total_years_experience=5)
    _run(engine, cache, client, catalog, facts, slug="a")
    _run(engine, cache, client, catalog, facts, slug="b")
    assert client.calls == 1


def test_same_jd_but_different_catalog_version_is_a_cache_miss(
    engine: Engine, cache: ResponseCache, tmp_path: Path
) -> None:
    """rules_hash folds in catalog.version, so the SAME JD and facts against a different
    catalog version is a MISS — a stale response is never replayed across a rule change."""
    catalog = load_rules(tmp_path / "no-cfg")
    other = dataclasses.replace(catalog, version="a-different-catalog-version")
    client = CountingClient(BODY)
    facts = Facts(total_years_experience=5)
    _run(engine, cache, client, catalog, facts, slug="a")
    _run(engine, cache, client, other, facts, slug="b")
    assert client.calls == 2


def test_response_cache_key_stays_identity_free(cache: ResponseCache) -> None:
    """No regression for the tailor rewrite lane, which shares ResponseCache.key and MUST
    keep an identity-free key. The key signature is unchanged: three parts joined by '|',
    hashed — nothing about a profile or catalog is baked into the method itself."""
    content_hash = hashlib.sha256(b"jd").hexdigest()
    expected = hashlib.sha256(f"{content_hash}|v1|model".encode()).hexdigest()
    assert cache.key(content_hash, "v1", "model") == expected
