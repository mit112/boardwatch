from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.rewrite.lane import run_tier_b

# No equivalence pairs are exercised by these tests (that's provenance.py's own test
# suite) -- an empty table isolates them from equivalences.yaml's real content.
_TABLE = EquivalenceTable(pairs=(), version="test")


class ScriptedClient:
    """Returns queued bodies in order; records call count."""

    def __init__(self, bodies: list[str]) -> None:
        self.bodies = list(bodies)
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return self.bodies.pop(0) if self.bodies else ""


class RaisingClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        raise RuntimeError("provider down")


def _resume() -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="Work",
                bullets=[
                    Bullet(bullet_id="b1", text="Built the service in Python"),
                ],
            )
        ],
    )


def _two_bullet_resume() -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="Work",
                bullets=[
                    Bullet(bullet_id="b1", text="Built the service in Python"),
                    Bullet(bullet_id="b2", text="Wrote unit tests for the API"),
                ],
            )
        ],
    )


def test_run_tier_b_scripted_client_is_stable(tmp_path):
    """Characterization test pinning current API-lane behavior before the
    run_tier_b_core/Proposer/Judge refactor: a two-bullet résumé where the
    first bullet's rewrite is ENTAILED (kept) and the second's is
    NOT_ENTAILED (dropped), with the exact accepted list, per-row drop
    reasons, and total call count."""
    client = ScriptedClient(
        [
            "Built the Python service",
            "ENTAILED",
            "Wrote unit tests for API",
            "NOT_ENTAILED",
        ]
    )
    res = run_tier_b(
        _two_bullet_resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert [r.bullet_id for r in res.accepted] == ["b1"]
    assert res.accepted[0].text == "Built the Python service"
    assert [r.kept for r in res.rows] == [True, False]
    assert [r.drop_reason for r in res.rows] == [None, "judge"]
    assert res.rows[0].judge_verdict == "ENTAILED"
    assert res.rows[1].judge_verdict == "NOT_ENTAILED"
    assert res.calls_made == 4


def test_good_rewrite_kept(tmp_path):
    client = ScriptedClient(["Built the Python service", "ENTAILED"])
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert [r.kept for r in res.rows] == [True]
    assert res.accepted[0].bullet_id == "b1"
    assert res.accepted[0].text == "Built the Python service"
    assert client.calls == 2


def test_filter_catch_drops_before_judge(tmp_path):
    client = ScriptedClient(["Built the service in Python, Kubernetes"])  # invented skill
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert res.accepted == []
    # The specific filter reason is carried, not the flat "filter", so the audit trail and
    # CLI can tell a prompt problem (e.g. "too_long") apart from a safety catch.
    assert res.rows[0].kept is False and res.rows[0].drop_reason == "filter:invented_skill"
    assert client.calls == 1  # judge never called


def test_unchanged_candidate_short_circuits_before_judge(tmp_path):
    """An echoed-back bullet (candidate == source) is not kept, is not sent to the judge,
    and is tagged distinctly from a real filter/judge drop so it can't be confused with a
    fallback failure in the CLI report."""
    client = ScriptedClient(["Built the service in Python"])  # byte-identical to the source
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert res.accepted == []
    assert res.rows[0].kept is False
    assert res.rows[0].drop_reason == "unchanged"
    assert client.calls == 1  # only the propose call — judge never spent on a no-op


def test_judge_not_entailed_drops(tmp_path):
    client = ScriptedClient(["Built the Python service", "NOT_ENTAILED"])
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "judge"


def test_provider_error_drops(tmp_path):
    res = run_tier_b(
        _resume(), RaisingClient(), ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "error"


def test_budget_exhaustion_drops(tmp_path):
    res = run_tier_b(
        _resume(), ScriptedClient(["x"]), ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=0,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "budget"
    assert res.calls_made == 0


def test_cache_hit_avoids_recall(tmp_path):
    cache = ResponseCache(tmp_path / "c")
    run_tier_b(
        _resume(), ScriptedClient(["Built the Python service", "ENTAILED"]),
        cache, jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    client2 = ScriptedClient([])  # would return "" on any real call
    r2 = run_tier_b(
        _resume(), client2, cache,
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m", budget=50,
    )
    assert r2.accepted[0].text == "Built the Python service"
    assert client2.calls == 0  # both propose and judge served from cache


def test_cache_identity_includes_provider_and_base_url(tmp_path):
    cache = ResponseCache(tmp_path / "c")
    run_tier_b(
        _resume(), ScriptedClient(["Built the Python service", "ENTAILED"]),
        cache, jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m",
        budget=50, provider="anthropic", base_url="https://api.anthropic.com",
    )

    # Same model string, different provider -> a real cache MISS: the second client
    # must be called, not silently served the first provider's cached replies.
    client_diff_provider = ScriptedClient(["Built the Python service", "ENTAILED"])
    r_diff_provider = run_tier_b(
        _resume(), client_diff_provider, cache,
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m",
        budget=50, provider="openai", base_url="https://api.anthropic.com",
    )
    assert client_diff_provider.calls == 2
    assert r_diff_provider.accepted[0].text == "Built the Python service"

    # Same model string, different base_url -> also a cache MISS.
    client_diff_url = ScriptedClient(["Built the Python service", "ENTAILED"])
    r_diff_url = run_tier_b(
        _resume(), client_diff_url, cache,
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m",
        budget=50, provider="anthropic", base_url="https://self-hosted.example.test",
    )
    assert client_diff_url.calls == 2
    assert r_diff_url.accepted[0].text == "Built the Python service"

    # Same identity (provider + base_url + model) -> still a cache HIT.
    client_same_identity = ScriptedClient([])
    r_same_identity = run_tier_b(
        _resume(), client_same_identity, cache,
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), table=_TABLE, model="m",
        budget=50, provider="anthropic", base_url="https://api.anthropic.com",
    )
    assert client_same_identity.calls == 0
    assert r_same_identity.accepted[0].text == "Built the Python service"
