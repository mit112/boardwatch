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
from collections.abc import Iterator
from contextlib import contextmanager
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
    """One gate row in the daily stage's write shape, which always records an effort (T155):
    `gate_effort_key(None)` unless the caller names a level, or passes `effort=None` for a row
    that recorded none."""
    from boardwatch.eligibility.final_gate import gate_effort_key, record_gate_verdict
    from boardwatch.eligibility.oracle import OracleVerdict

    verdict = verdict_override or OracleVerdict(
        label=str(label), decision="eligible", reason=None, evidence="", confidence="high",
    )
    kwargs.setdefault("effort", gate_effort_key(None))
    with engine.begin() as conn:
        record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=JD_5YR, facts=facts, policy=POLICY,
            catalog=catalog, verdict=verdict, **kwargs,
        )


def _posting_of(engine: Engine, pv_id: int) -> int:
    from sqlalchemy import select

    from boardwatch.store import tables

    with engine.connect() as conn:
        return int(conn.execute(
            select(tables.posting_versions.c.posting_id).where(
                tables.posting_versions.c.id == pv_id
            )
        ).scalar_one())


def _freshness_read(engine: Engine, facts: Facts, pv_id: int, *, model: str,
                    effort: str | None = None):
    """The never-re-judge filter's read. `effort` defaults to the unset level, which is what
    `_record_gate` records unless told otherwise."""
    from boardwatch.eligibility.final_gate import gate_effort_key
    from boardwatch.eligibility.read import fresh_gate_verdicts

    with engine.connect() as conn:
        return fresh_gate_verdicts(
            conn, [pv_id], facts, model=model,
            effort=gate_effort_key(None) if effort is None else effort,
        )


def _value_read(engine: Engine, catalog, facts: Facts | None, pv_ids: list[int], *,
                model: str = "sonnet"):
    """The one VALUE read every lane, pane and ranker caller makes (T161)."""
    from boardwatch.eligibility.read import current_gate_verdicts

    with engine.connect() as conn:
        return current_gate_verdicts(conn, pv_ids, facts, catalog, model=model)


def test_a_gate_row_judged_by_another_model_is_not_fresh(
    engine: Engine, tmp_path: Path
) -> None:
    """The bug, at the read that decides it: a row the OLD judge wrote must not count as
    already-judged once the configured model changes, or the switch reaches new leads only."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-a")
    _record_gate(engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="sonnet")

    assert _freshness_read(engine, facts, pv_id, model="haiku") == {}, (
        "a verdict reached by a different model is not a current verdict"
    )


def test_a_gate_row_from_the_same_model_is_still_fresh(engine: Engine, tmp_path: Path) -> None:
    """CONTROL, and the one that must not regress: the model narrowing must not defeat the
    never-re-judge filter (D-477 pt 5), which is worth one `claude` call per lead per day."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-b")
    _record_gate(engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="sonnet")

    hit = _freshness_read(engine, facts, pv_id, model="sonnet")
    assert hit == {_posting_of(engine, pv_id): "eligible"}


def test_a_legacy_gate_row_naming_no_model_is_neither_fresh_nor_read(
    engine: Engine, tmp_path: Path
) -> None:
    """A row written before T108 has `model IS NULL`, so it never matches a given model: its lead
    is re-judged ONCE. Since T161 the VALUE read keys on the model too, so it serves nothing
    either — a verdict that names no judge holds and releases nothing (the T152 rule). CONTROL: a
    model-stamped row on a second posting IS read, so the empty result is the model narrowing
    and not a read that finds nothing at all."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="gate-model-legacy")
    stamped_pv = _seed_posting_version(engine, JD_5YR, slug="gate-model-stamped")
    # legacy shape: no provider, no model, no effort
    _record_gate(engine, catalog, facts, pv_id, 1, effort=None)
    _record_gate(engine, catalog, facts, stamped_pv, 2, provider="claude-code-agent",
                 model="sonnet")

    assert _freshness_read(engine, facts, pv_id, model="sonnet") == {}
    assert _value_read(engine, catalog, facts, [pv_id, stamped_pv]) == {
        _posting_of(engine, stamped_pv): "eligible"
    }


def test_an_older_row_from_the_configured_model_still_hits_under_a_newer_one(
    engine: Engine, tmp_path: Path
) -> None:
    """The narrowing must sit INSIDE the `max(id)` subquery, exactly where `facts_key`'s does:
    it filters before "latest" is picked, so a lead whose NEWEST row is from another judge
    still hits the older row that this judge reached. Outside the subquery, max(id) would pick
    the other model's row and the filter would then drop it — re-judging a lead this judge has
    already answered, which is the whole cost the never-re-judge filter exists to avoid.
    """
    from boardwatch.eligibility.oracle import OracleVerdict

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

    older = _freshness_read(engine, facts, pv_id, model="sonnet")
    newest = _freshness_read(engine, facts, pv_id, model="haiku")
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


def _seniority(engine: Engine, pv_ids: list[int], facts: Facts, *, model: str = "sonnet"):
    from boardwatch.eligibility.read import current_gate_seniority

    with engine.connect() as conn:
        return current_gate_seniority(conn, pv_ids, facts, model=model)


def _record_legacy(engine: Engine, catalog, facts: Facts, pv_id: int, label: int, *,
                   model: str | None = "sonnet", engine_version: str | None = None) -> None:
    """A gate row in the shape written BEFORE T152: no `years` key. Written through
    `record_evaluation` because `record_gate_verdict` now always records the years."""
    from boardwatch.eligibility.final_gate import gate_engine_version, gate_facts_key
    from boardwatch.eligibility.oracle import PROMPT_VERSION
    from boardwatch.store.eligibility import record_evaluation

    identity = _gate_identity(catalog, facts, pv_id)
    with engine.begin() as conn:
        record_evaluation(
            conn, posting_version_id=pv_id,
            profile_hash=identity.profile_hash, profile_snapshot=identity.profile_snapshot,
            rules_hash=identity.rules_hash, rules_snapshot=identity.rules_snapshot,
            input_fingerprint=identity.input_fingerprint, engine_kind="llm",
            engine_version=engine_version or gate_engine_version(), verdict="eligible",
            score=None, requirements=[], provider="claude-code-agent", model=model,
            prompt_version=PROMPT_VERSION, idempotency_key=None,
            raw_output={"gate_verdict": _senior(label).__dict__,
                        "facts_key": gate_facts_key(facts)},
        )


def test_a_rules_hash_change_no_longer_hides_a_seniority_reading(
    engine: Engine, tmp_path: Path
) -> None:
    """Test 1 (design §5). The prompt names no catalog vocabulary, so a catalog re-key cannot
    change whether a body reads senior — and scoping on it released every stored hold (D-537).
    INVERSE arm: a new `posting_version_id` is a new body, and its reading is genuinely absent."""
    catalog = load_rules(tmp_path / "no-cfg")
    rekeyed = dataclasses.replace(catalog, version="a-different-catalog-version")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-rules")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, rekeyed, facts, pv_id, posting_id, verdict_override=_senior(posting_id),
                 provider="claude-code-agent", model="sonnet")
    assert (_gate_identity(rekeyed, facts, pv_id).rules_hash
            != _gate_identity(catalog, facts, pv_id).rules_hash)
    revised_pv = _new_version_of(engine, pv_id)

    assert _seniority(engine, [pv_id], facts) == {posting_id: "no"}
    assert _seniority(engine, [revised_pv], facts) == {}


def test_a_seniority_reading_from_another_model_is_hidden(engine: Engine, tmp_path: Path) -> None:
    """Test 2, mirroring `test_a_gate_row_judged_by_another_model_is_not_fresh`: a different
    model is a different judge (D-537's 11.2% floor), so its reading is not this judge's."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-model")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, facts, pv_id, posting_id, verdict_override=_senior(posting_id),
                 provider="claude-code-agent", model="sonnet")

    assert _seniority(engine, [pv_id], facts, model="haiku") == {}


def test_a_seniority_reading_from_the_same_model_is_found(engine: Engine, tmp_path: Path) -> None:
    """CONTROL for test 2, mirroring `test_a_gate_row_from_the_same_model_is_still_fresh`."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-model-same")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, facts, pv_id, posting_id, verdict_override=_senior(posting_id),
                 provider="claude-code-agent", model="sonnet")

    assert _seniority(engine, [pv_id], facts, model="sonnet") == {posting_id: "no"}


def test_a_years_change_hides_a_seniority_reading_and_an_unrelated_fact_does_not(
    engine: Engine, tmp_path: Path
) -> None:
    """Test 3, the design's whole claim, on NEW-key rows. The judge is asked the question
    relative to the candidate's years, so a years change must hide the reading; `highest_degree`
    is an eligibility input the seniority question never reads, so changing it must not — even
    though it moves `facts_key` and, under this policy, `profile_hash` too."""
    from boardwatch.eligibility.final_gate import gate_facts_key

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    degree_edit = Facts(total_years_experience=5, highest_degree="bachelors")
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-years")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, facts, pv_id, posting_id, verdict_override=_senior(posting_id),
                 provider="claude-code-agent", model="sonnet")
    # Not vacuous: the degree edit moves both keys the OLD read and the legacy fallback use.
    assert gate_facts_key(degree_edit) != gate_facts_key(facts)
    assert (_gate_identity(catalog, degree_edit, pv_id).profile_hash
            != _gate_identity(catalog, facts, pv_id).profile_hash)

    assert _seniority(engine, [pv_id], Facts(total_years_experience=6)) == {}
    assert _seniority(engine, [pv_id], degree_edit) == {posting_id: "no"}


def test_a_seniority_reading_recorded_with_no_years_matches_only_no_years(
    engine: Engine, tmp_path: Path
) -> None:
    """A profile without years writes a JSON null, which must match a years-less profile and
    nothing else — and must not be mistaken for a legacy row (no key at all)."""
    catalog = load_rules(tmp_path / "no-cfg")
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-no-years")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, Facts(), pv_id, posting_id,
                 verdict_override=_senior(posting_id), provider="claude-code-agent",
                 model="sonnet")

    assert _seniority(engine, [pv_id], Facts(highest_degree="bachelors")) == {posting_id: "no"}
    assert _seniority(engine, [pv_id], Facts(total_years_experience=0)) == {}


def test_a_legacy_seniority_reading_is_found_only_on_its_exact_judge_and_facts(
    engine: Engine, tmp_path: Path
) -> None:
    """Test 4. A row written before `years` was recorded counts only when model, EXACT
    engine_version and `facts_key` all match — strictly narrower than the new key, which is why
    the degree-edit arm here misses where test 3's hits."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pvs = [_seed_posting_version(engine, JD_5YR, slug=f"senior-legacy-{n}") for n in range(5)]
    posting = {pv: _posting_of(engine, pv) for pv in pvs}
    matching, other_model, other_version, no_model, other_facts = pvs
    _record_legacy(engine, catalog, facts, matching, posting[matching])
    _record_legacy(engine, catalog, facts, other_model, posting[other_model], model="haiku")
    _record_legacy(engine, catalog, facts, other_version, posting[other_version],
                   engine_version="final_gate:p5-oracle-1:v1")
    _record_legacy(engine, catalog, facts, no_model, posting[no_model], model=None)
    _record_legacy(engine, catalog, Facts(total_years_experience=5, highest_degree="bachelors"),
                   other_facts, posting[other_facts])

    assert _seniority(engine, pvs, facts) == {posting[matching]: "no"}


def test_a_seniority_reading_under_an_older_gate_policy_is_not_found(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 5, design §2's `p5-oracle-1` case: the read matches the EXACT gate engine_version,
    not the display prefix, so a reading judged before the seniority question existed — or
    under any superseded prompt/policy — is not this judge's answer."""
    from boardwatch.eligibility import final_gate

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="senior-old-policy")
    posting_id = _posting_of(engine, pv_id)
    with monkeypatch.context() as patch:
        patch.setattr(final_gate, "POLICY_VERSION", "p5-oracle-1")
        _record_gate(engine, catalog, facts, pv_id, posting_id,
                     verdict_override=_senior(posting_id), provider="claude-code-agent",
                     model="sonnet")

    assert _seniority(engine, [pv_id], facts) == {}


# ---------------------------------------------------------------------------
# T155 — the gate freshness key must fold in the EFFORT a row was judged at
# ---------------------------------------------------------------------------
#
# T108's shape for a second input: `settings.gate.effort` reaches the headless call and
# `config_hash`, but no gate row recorded it, so a change of level never read as stale.


def _judged_at(engine: Engine, catalog, facts: Facts, slug: str, effort: str | None) -> int:
    pv_id = _seed_posting_version(engine, JD_5YR, slug=slug)
    _record_gate(engine, catalog, facts, pv_id, 1, provider="claude-code-agent", model="sonnet",
                 effort=effort)
    return pv_id


def test_a_gate_row_judged_at_another_effort_is_not_fresh(engine: Engine, tmp_path: Path) -> None:
    """A `medium` reading is not current under `high`; under `medium` it is (the control)."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _judged_at(engine, catalog, facts, "gate-effort-medium", "medium")

    assert _freshness_read(engine, facts, pv_id, model="sonnet", effort="high") == {}
    assert _freshness_read(engine, facts, pv_id, model="sonnet", effort="medium") == {
        _posting_of(engine, pv_id): "eligible"
    }


def test_a_gate_row_that_recorded_no_effort_is_fresh_under_no_level(
    engine: Engine, tmp_path: Path
) -> None:
    """Every row before T155 (and every `eligibility gate apply` row) recorded no level, so the
    level it was judged at is unknown — not fresh under `medium`, NOR under the unset level."""
    from boardwatch.eligibility.final_gate import gate_effort_key

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _judged_at(engine, catalog, facts, "gate-effort-legacy", None)

    assert _freshness_read(engine, facts, pv_id, model="sonnet", effort="medium") == {}
    assert _freshness_read(
        engine, facts, pv_id, model="sonnet", effort=gate_effort_key(None)
    ) == {}


def test_a_gate_row_judged_at_the_unset_level_is_fresh_only_under_the_unset_level(
    engine: Engine, tmp_path: Path
) -> None:
    """`gate.effort = None` is a real level (the calibrated argv), recorded distinctly from
    "never recorded": fresh under `None`, not under `medium`."""
    from boardwatch.eligibility.final_gate import gate_effort_key

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _judged_at(engine, catalog, facts, "gate-effort-unset", gate_effort_key(None))

    assert _freshness_read(
        engine, facts, pv_id, model="sonnet", effort=gate_effort_key(None)
    ) == {_posting_of(engine, pv_id): "eligible"}
    assert _freshness_read(engine, facts, pv_id, model="sonnet", effort="medium") == {}


# ---------------------------------------------------------------------------
# T161 — what a stored gate VERDICT is keyed on, for the value reads and for freshness
# ---------------------------------------------------------------------------
#
# The verdict-side twin of the T152 section above. `read.current_gate_verdicts` feeds the queue,
# the pane, the run's lane split and the ranker; `read.fresh_gate_verdicts` is the never-re-judge
# filter. Both used to scope on `(profile_hash, rules_hash)`, which the judge never sees. The
# caller-level tests are in `test_delivery_queue.py` (the lanes), `test_rank_gate_filter.py` (the
# ranker) and `test_gate_stage.py` (the spend); these pin the key at the read itself.

#: An `internship` hard stop the judge can quote: `INTERN_EVIDENCE` is a raw substring of the body,
#: so `accept_oracle_verdict` accepts it and the row persists `ineligible` with a span.
INTERN_JD = "This is a twelve week summer internship program for current university students."
INTERN_EVIDENCE = "twelve week summer internship program for current university students"


@contextmanager
def rekeyed(config_dir: Path, kind: str) -> Iterator[None]:
    """A REAL re-key that leaves the judge's inputs alone, held for the body of the `with`.

    `rules_hash` is a RULES-ONLY re-key, the D-555 shape minus the batch: a `rules.yaml` override
    that differs from the bundled catalog in its top-level `version` key and nothing else.
    `catalog.version` digests the parsed document, so `rules_hash` moves while every pattern —
    hence every deterministic verdict and the family set — is byte-identical.

    `engine_version` moves the deterministic engine's digest, as a `detect.py` edit (T163) does.
    Restored by hand on exit rather than by monkeypatch: `engine_version` is lru_cached, so its
    cache has to be cleared AFTER the restore, and monkeypatch restores at teardown — after every
    assertion, leaving the bumped version cached for later tests (the reason
    `test_the_derived_version_is_cached_and_the_cache_is_clearable` does the same).
    """
    from boardwatch.eligibility import engine as engine_mod
    from boardwatch.eligibility.catalog import bundled_rules_text

    if kind == "rules_hash":
        text = bundled_rules_text()
        assert text.startswith("version: 1\n"), "the bundled catalog's first line moved"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "rules.yaml").write_text(text.replace("version: 1", "version: 2", 1),
                                               encoding="utf-8")
        yield
        return
    assert kind == "engine_version", kind
    before = engine_mod.engine_version()
    original = engine_mod.ENGINE_SEMANTIC
    engine_mod.ENGINE_SEMANTIC = f"{original}-t161"
    engine_mod.engine_version.cache_clear()
    try:
        assert engine_mod.engine_version() != before
        yield
    finally:
        engine_mod.ENGINE_SEMANTIC = original
        engine_mod.engine_version.cache_clear()


def _record_intern(engine: Engine, catalog, facts: Facts, pv_id: int, label: int) -> None:
    from boardwatch.eligibility.final_gate import gate_effort_key, record_gate_verdict
    from boardwatch.eligibility.oracle import OracleVerdict

    with engine.begin() as conn:
        record_gate_verdict(
            conn, posting_version_id=pv_id, jd_text=INTERN_JD, facts=facts, policy=POLICY,
            catalog=catalog, provider="claude-code-agent", model="sonnet",
            effort=gate_effort_key(None),
            verdict=OracleVerdict(
                label=str(label), decision="ineligible", reason="internship",
                evidence=INTERN_EVIDENCE, confidence="high",
            ),
        )


def test_a_rules_only_rekey_no_longer_hides_a_gate_verdict(engine: Engine, tmp_path: Path) -> None:
    """Test 1 at the read (design §2). A row written under another catalog is read, and is fresh,
    under this one: the judge never saw either. INVERSE arm: a new `posting_version_id` is a new
    body, and its verdict is genuinely absent from both reads."""
    catalog = load_rules(tmp_path / "no-cfg")
    rekeyed = dataclasses.replace(catalog, version="a-different-catalog-version")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug="t161-rules")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, rekeyed, facts, pv_id, posting_id, provider="claude-code-agent",
                 model="sonnet")
    assert (_gate_identity(rekeyed, facts, pv_id).rules_hash
            != _gate_identity(catalog, facts, pv_id).rules_hash)
    revised_pv = _new_version_of(engine, pv_id)

    assert _value_read(engine, catalog, facts, [pv_id]) == {posting_id: "eligible"}
    assert _freshness_read(engine, facts, pv_id, model="sonnet") == {posting_id: "eligible"}
    assert _value_read(engine, catalog, facts, [revised_pv]) == {}
    assert _freshness_read(engine, facts, revised_pv, model="sonnet") == {}


@pytest.mark.parametrize("changed", ["unchanged", "facts", "model", "gate_version"])
def test_a_verdict_reached_on_other_inputs_is_not_read(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    """Test 4 at the read. Each of the three judge inputs, changed alone, hides the verdict: a
    changed fact changes what the judge was asked, another model is another judge, and another
    EXACT gate version is another prompt or policy. `unchanged` is the control."""
    from boardwatch.eligibility import final_gate
    from boardwatch.eligibility.oracle import OracleVerdict

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug=f"t161-{changed}")
    posting_id = _posting_of(engine, pv_id)
    verdict = OracleVerdict(label=str(posting_id), decision="eligible", reason=None, evidence="",
                            confidence="high")
    with monkeypatch.context() as patch:
        if changed == "gate_version":
            patch.setattr(final_gate, "POLICY_VERSION", "p5-oracle-1")
        _record_gate(
            engine, catalog, Facts(total_years_experience=6) if changed == "facts" else facts,
            pv_id, posting_id, verdict_override=verdict, provider="claude-code-agent",
            model="haiku" if changed == "model" else "sonnet",
        )

    expected = {posting_id: "eligible"} if changed == "unchanged" else {}
    assert _value_read(engine, catalog, facts, [pv_id]) == expected


def test_an_effort_change_leaves_the_verdict_read_and_makes_it_stale(
    engine: Engine, tmp_path: Path
) -> None:
    """Test 5, both sides of the owner's T155 ruling at once: a level is a calibration of the SAME
    judge, so the value read keeps serving a `medium` reading under the unset level, while the
    freshness read counts it stale and the refresh re-judges it."""
    from boardwatch.eligibility.final_gate import gate_effort_key

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _judged_at(engine, catalog, facts, "t161-effort", "medium")
    posting_id = _posting_of(engine, pv_id)

    assert _value_read(engine, catalog, facts, [pv_id]) == {posting_id: "eligible"}
    assert _freshness_read(
        engine, facts, pv_id, model="sonnet", effort=gate_effort_key(None)
    ) == {}
    assert _freshness_read(engine, facts, pv_id, model="sonnet", effort="medium") == {
        posting_id: "eligible"
    }


def test_a_stored_ineligible_whose_family_left_the_catalog_reads_uncertain(
    engine: Engine, tmp_path: Path
) -> None:
    """Test 6 (design §3). The verdict's one catalog dependence: the reason an `ineligible` cites
    must be a family of the CURRENT catalog, or it reads `uncertain` — the downgrade
    `accept_oracle_verdict` would make today. CONTROL: the same row under a catalog that still has
    the family reads `ineligible`. The freshness read serves the stored value, undowngraded: it
    answers "already judged?", and the lead was."""
    catalog = load_rules(tmp_path / "no-cfg")
    assert "internship" in {family.id for family in catalog.families}
    without = dataclasses.replace(
        catalog, families=tuple(f for f in catalog.families if f.id != "internship")
    )
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, INTERN_JD, slug="t161-family")
    posting_id = _posting_of(engine, pv_id)
    _record_intern(engine, catalog, facts, pv_id, posting_id)

    assert _value_read(engine, catalog, facts, [pv_id]) == {posting_id: "ineligible"}
    assert _value_read(engine, without, facts, [pv_id]) == {posting_id: "uncertain"}
    assert _freshness_read(engine, facts, pv_id, model="sonnet") == {posting_id: "ineligible"}


@pytest.mark.parametrize("newer_differs_in", ["model", "effort", "facts", "gate_version"])
def test_every_freshness_narrowing_filters_before_max_id(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, newer_differs_in: str
) -> None:
    """Test 8. T108's placement, for all four narrowings the freshness read keeps: each sits INSIDE
    the `max(id)` subquery, so a NEWER row reached on other inputs never hides the older row this
    judge reached on these. Outside it, max(id) would pick the newer row and the filter would then
    drop it — re-judging a lead that was already answered."""
    from boardwatch.eligibility import final_gate
    from boardwatch.eligibility.oracle import OracleVerdict

    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, JD_5YR, slug=f"t161-older-{newer_differs_in}")
    posting_id = _posting_of(engine, pv_id)
    _record_gate(engine, catalog, facts, pv_id, posting_id, provider="claude-code-agent",
                 model="sonnet")
    newer = OracleVerdict(label=str(posting_id), decision="uncertain", reason=None, evidence="",
                          confidence="low")
    with monkeypatch.context() as patch:
        if newer_differs_in == "gate_version":
            patch.setattr(final_gate, "POLICY_VERSION", "p5-oracle-9")
        _record_gate(
            engine, catalog,
            Facts(total_years_experience=6) if newer_differs_in == "facts" else facts,
            pv_id, posting_id, verdict_override=newer, provider="claude-code-agent",
            model="haiku" if newer_differs_in == "model" else "sonnet",
            **({"effort": "high"} if newer_differs_in == "effort" else {}),
        )

    assert _freshness_read(engine, facts, pv_id, model="sonnet") == {posting_id: "eligible"}


def test_no_profile_reads_no_gate_verdict(engine: Engine, tmp_path: Path) -> None:
    """Test 9 at the read: `facts is None` is a store with no profile, and nothing is found — the
    fail-open direction, as `current_gate_seniority`. CONTROL: the same row is found under the
    facts it was judged on."""
    catalog = load_rules(tmp_path / "no-cfg")
    facts = Facts(total_years_experience=5)
    pv_id = _seed_posting_version(engine, INTERN_JD, slug="t161-no-profile")
    posting_id = _posting_of(engine, pv_id)
    _record_intern(engine, catalog, facts, pv_id, posting_id)

    assert _value_read(engine, catalog, facts, [pv_id]) == {posting_id: "ineligible"}
    assert _value_read(engine, catalog, None, [pv_id]) == {}
