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
from sqlalchemy import Engine, event

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.extract_llm import extract_and_record
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.llm.cache import ResponseCache
from boardwatch.store.db import ensure_schema, get_engine
from tests.pipeline.test_llm_lane import EXPERIENCE_QUOTE, JD_5YR, _seed_posting_version

# experience_years pinned to `blocker` so it is an ENABLED family: build_identity then folds
# total_years_experience into profile_hash, which is what makes two different facts two
# different cache keys.
#
# That is also what this module used to leave UNCOVERED, and T99 closes it: `build_identity`
# drops a family's declared fields the moment its severity is `ignore`, while
# `_requirement_for_span` reads `facts.total_years_experience` regardless of any policy. So
# under the IGNORED policy below the years a disposition is computed from were invisible to
# the cache key — see the last test.
POLICY = Policy(families={"experience_years": "blocker"})
# `degree` must be ignored alongside `experience_years`: it DECLARES total_years_experience
# too (resolve.declared_fields), so leaving it enabled would fold the years back in.
IGNORED_POLICY = Policy(families={"degree": "ignore", "experience_years": "ignore"})
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


def _run(engine: Engine, cache: ResponseCache, client: CountingClient, catalog, facts, *,
         slug, policy: Policy = POLICY):
    pv_id = _seed_posting_version(engine, JD_5YR, slug=slug)
    with engine.begin() as conn:
        extract_and_record(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=policy,
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


def test_different_years_is_a_cache_miss_even_when_the_family_is_ignored(
    engine: Engine, cache: ResponseCache, tmp_path: Path
) -> None:
    """T99. `profile_hash` is not the whole judge-visible profile.

    With both families that declare `total_years_experience` set to `ignore`,
    `build_identity` drops the field and the two profiles hash identically — but
    `extract_llm._requirement_for_span` consults no severity policy at all and adjudicates
    the span against `facts.total_years_experience` anyway, so 0 -> 10 flips the disposition
    unmet -> met. Folding the facts key into the content_hash argument makes that a MISS.
    """
    catalog = load_rules(tmp_path / "no-cfg")
    client = CountingClient(BODY)
    _run(engine, cache, client, catalog, Facts(total_years_experience=0), slug="a",
         policy=IGNORED_POLICY)
    _run(engine, cache, client, catalog, Facts(total_years_experience=10), slug="b",
         policy=IGNORED_POLICY)
    assert client.calls == 2, (
        "an ignored family still reaches the disposition, so its fact must key the cache"
    )


# ---------------------------------------------------------------------------
# T108 — the gate lane's freshness key must fold in the MODEL that judged the row
# ---------------------------------------------------------------------------
#
# Same class of bug as every test above, one lane over. The gate lane has no `ResponseCache`;
# its cache is the ROW, and `read.current_gate_verdicts` is the lookup. The row identity is
# `(posting_version_id, profile_hash, rules_hash)` and the freshness read adds `engine_version`
# (D-512) and `facts_key` (T99) — none of which moves when `settings.gate.model` changes. So a
# verdict reached by the previous judge counted as current forever and a model switch reached
# NEW leads only.


def _gate_identity(catalog, facts: Facts, pv_id: int, policy: Policy = POLICY):
    from boardwatch.eligibility.hashing import build_identity
    from boardwatch.eligibility.resolve import declared_fields

    return build_identity(
        posting_version_id=pv_id, facts=facts, policy=policy, catalog=catalog,
        declared_fields=declared_fields(),
    )


def _record_gate(engine: Engine, catalog, facts: Facts, pv_id: int, label: int,
                 verdict_override=None, **kwargs) -> None:
    from boardwatch.eligibility.final_gate import record_gate_verdict
    from boardwatch.eligibility.oracle import OracleVerdict

    verdict = verdict_override or OracleVerdict(
        label=str(label), decision="eligible", reason=None, evidence="", confidence="high",
    )
    with engine.begin() as conn:
        record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=POLICY,
            catalog=catalog, verdict=verdict, **kwargs,
        )


def _collect(sink: list[str]):
    """A `before_cursor_execute` listener that records every statement the read emits."""

    def listener(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        sink.append(statement)

    return listener


def _posting_of(engine: Engine, pv_id: int) -> int:
    from sqlalchemy import select

    from boardwatch.store import tables

    with engine.connect() as conn:
        return int(conn.execute(
            select(tables.posting_versions.c.posting_id).where(
                tables.posting_versions.c.id == pv_id
            )
        ).scalar_one())


def _freshness_read(engine: Engine, catalog, facts: Facts, pv_id: int, **kwargs):
    from boardwatch.eligibility.final_gate import gate_engine_version, gate_facts_key
    from boardwatch.eligibility.read import current_gate_verdicts

    identity = _gate_identity(catalog, facts, pv_id)
    with engine.connect() as conn:
        return current_gate_verdicts(
            conn, [pv_id], identity.profile_hash, identity.rules_hash,
            engine_version=gate_engine_version(), facts_key=gate_facts_key(facts), **kwargs,
        )


def test_a_gate_row_judged_by_another_model_is_not_fresh(
    engine: Engine, tmp_path: Path
) -> None:
    """The bug, at the read that decides it: a row the OLD judge wrote must not count as
    already-judged once the configured model changes, or the switch reaches new leads only."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-a")
    _record_gate(engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="sonnet")

    assert _freshness_read(engine, catalog, facts, pv_id, model="haiku") == {}, (
        "a verdict reached by a different model is not a current verdict"
    )


def test_a_gate_row_from_the_same_model_is_still_fresh(engine: Engine, tmp_path: Path) -> None:
    """CONTROL, and the one that must not regress: the model narrowing must not defeat the
    never-re-judge filter (D-477 pt 5), which is worth one `claude` call per lead per day."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-b")
    _record_gate(engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="sonnet")

    hit = _freshness_read(engine, catalog, facts, pv_id, model="sonnet")
    assert hit == {_posting_of(engine, pv_id): "eligible"}


def test_a_legacy_gate_row_misses_a_model_but_still_reads_for_display(
    engine: Engine, tmp_path: Path
) -> None:
    """A row written before this shipped has `model IS NULL`, so it never matches a given
    model and its lead is re-judged ONCE. The DISPLAY read passes no model and must still
    serve that verdict — a superseded row is still the best thing known about the lead."""
    from boardwatch.eligibility.read import current_gate_verdicts

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-legacy")
    _record_gate(engine, catalog, facts, pv_id, 1)  # legacy shape: no provider, no model
    posting_id = _posting_of(engine, pv_id)

    assert _freshness_read(engine, catalog, facts, pv_id, model="sonnet") == {}
    identity = _gate_identity(catalog, facts, pv_id)
    with engine.connect() as conn:
        display = current_gate_verdicts(
            conn, [pv_id], identity.profile_hash, identity.rules_hash
        )
    assert display == {posting_id: "eligible"}


def test_the_display_read_is_unchanged_when_no_model_is_given(
    engine: Engine, tmp_path: Path
) -> None:
    """CONTROL for the four callers that pass no model (`runner`, `top_cmd`, and both
    `delivery_queries` reads): they must get exactly the rows they got before, over a store
    holding BOTH a legacy row and a model-stamped one, and the SQL must not mention the
    column at all."""
    from boardwatch.eligibility.read import current_gate_verdicts

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    legacy_pv = _seed_posting_version(engine, JD_5YR, slug="gate-display-legacy")
    stamped_pv = _seed_posting_version(engine, JD_5YR, slug="gate-display-stamped")
    _record_gate(engine, catalog, facts, legacy_pv, 1)
    _record_gate(engine, catalog, facts, stamped_pv, 2, provider="claude-code-agent",
                 model="sonnet")

    identity = _gate_identity(catalog, facts, legacy_pv)
    statements: list[str] = []
    with engine.connect() as conn:
        event.listen(conn, "before_cursor_execute", _collect(statements))
        rows = current_gate_verdicts(
            conn, [legacy_pv, stamped_pv], identity.profile_hash, identity.rules_hash
        )
    assert rows == {
        _posting_of(engine, legacy_pv): "eligible",
        _posting_of(engine, stamped_pv): "eligible",
    }
    assert statements, "the read emitted no SQL at all, so it asserted nothing"
    assert not any("model" in sql for sql in statements), (
        f"the display read must not narrow on the model column: {statements}"
    )


def test_an_older_row_from_the_configured_model_still_hits_under_a_newer_one(
    engine: Engine, tmp_path: Path
) -> None:
    """The narrowing must sit INSIDE the `max(id)` subquery, exactly where `facts_key`'s does:
    it filters before "latest" is picked, so a lead whose NEWEST row is from another judge
    still hits the older row that this judge reached. Outside the subquery, max(id) would pick
    the other model's row and the filter would then drop it — re-judging a lead this judge has
    already answered, which is the whole cost the never-re-judge filter exists to avoid.
    """
    from boardwatch.eligibility.final_gate import gate_engine_version, gate_facts_key
    from boardwatch.eligibility.oracle import OracleVerdict
    from boardwatch.eligibility.read import current_gate_verdicts

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-older")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="sonnet")
    _record_gate(
        engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="haiku",
        verdict_override=OracleVerdict(
            label=str(posting_id), decision="uncertain", reason=None, evidence="",
            confidence="low",
        ),
    )

    identity = _gate_identity(catalog, facts, pv_id)
    with engine.connect() as conn:
        older = current_gate_verdicts(
            conn, [pv_id], identity.profile_hash, identity.rules_hash,
            engine_version=gate_engine_version(), facts_key=gate_facts_key(facts),
            model="sonnet",
        )
        newest = current_gate_verdicts(
            conn, [pv_id], identity.profile_hash, identity.rules_hash,
            engine_version=gate_engine_version(), facts_key=gate_facts_key(facts),
            model="haiku",
        )
    assert older == {posting_id: "eligible"}
    assert newest == {posting_id: "uncertain"}


# ---------------------------------------------------------------------------
# T152 — what a stored body-seniority reading is keyed on
# ---------------------------------------------------------------------------
#
# `read.current_gate_seniority` feeds the `seniority_judged_above_band` hold. Nothing pinned its
# scoping at all (design §5): `test_gate_handshake`'s `rules_hash` pin is on
# `current_gate_verdicts` only.


def _senior(label: int) -> object:
    from boardwatch.eligibility.oracle import OracleVerdict

    return OracleVerdict(
        label=str(label), decision="eligible", reason=None, evidence="", confidence="high",
        seniority_fit="no",
    )


def _new_version_of(engine: Engine, pv_id: int) -> int:
    """A second, later body for the SAME posting — what a JD revision mints."""
    from sqlalchemy import insert

    from boardwatch.core.clock import utcnow
    from boardwatch.store import tables

    with engine.begin() as conn:
        return int(conn.execute(insert(tables.posting_versions).values(
            posting_id=_posting_of(engine, pv_id), content_hash=f"h-rev-{pv_id}",
            body_text=JD_5YR + "\nRevised.", captured_at=utcnow(), capture_reason="revised",
        )).inserted_primary_key[0])


def test_baseline_the_seniority_read_is_scoped_on_the_full_row_identity(
    engine: Engine, tmp_path: Path
) -> None:
    """BASELINE, committed before T152 changes the read: today a reading is found only under
    the exact `(posting_version_id, profile_hash, rules_hash)` it was written under."""
    from boardwatch.eligibility.read import current_gate_seniority

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-baseline")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, facts, pv_id, posting_id, verdict_override=_senior(posting_id))
    identity = _gate_identity(catalog, facts, pv_id)
    revised_pv = _new_version_of(engine, pv_id)

    with engine.connect() as conn:
        found = current_gate_seniority(conn, [pv_id], identity.profile_hash, identity.rules_hash)
        other_rules = current_gate_seniority(conn, [pv_id], identity.profile_hash, "other")
        other_body = current_gate_seniority(
            conn, [revised_pv], identity.profile_hash, identity.rules_hash
        )
    assert found == {posting_id: "no"}
    assert other_rules == {}
    assert other_body == {}
