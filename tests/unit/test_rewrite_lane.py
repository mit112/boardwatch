from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.rewrite.lane import run_tier_b


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


def test_good_rewrite_kept(tmp_path):
    client = ScriptedClient(["Shipped the service in Python", "ENTAILED"])
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=50,
    )
    assert [r.kept for r in res.rows] == [True]
    assert res.accepted[0].bullet_id == "b1"
    assert res.accepted[0].text == "Shipped the service in Python"
    assert client.calls == 2


def test_filter_catch_drops_before_judge(tmp_path):
    client = ScriptedClient(["Built the service in Python and Kubernetes"])  # invented skill
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=50,
    )
    assert res.accepted == []
    assert res.rows[0].kept is False and res.rows[0].drop_reason == "filter"
    assert client.calls == 1  # judge never called


def test_judge_not_entailed_drops(tmp_path):
    client = ScriptedClient(["Shipped the service in Python", "NOT_ENTAILED"])
    res = run_tier_b(
        _resume(), client, ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=50,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "judge"


def test_provider_error_drops(tmp_path):
    res = run_tier_b(
        _resume(), RaisingClient(), ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=50,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "error"


def test_budget_exhaustion_drops(tmp_path):
    res = run_tier_b(
        _resume(), ScriptedClient(["x"]), ResponseCache(tmp_path / "c"),
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=0,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "budget"
    assert res.calls_made == 0


def test_cache_hit_avoids_recall(tmp_path):
    cache = ResponseCache(tmp_path / "c")
    run_tier_b(
        _resume(), ScriptedClient(["Shipped the service in Python", "ENTAILED"]),
        cache, jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=50,
    )
    client2 = ScriptedClient([])  # would return "" on any real call
    r2 = run_tier_b(
        _resume(), client2, cache,
        jd_skills=set(), taxonomy=load_taxonomy(tmp_path), model="m", budget=50,
    )
    assert r2.accepted[0].text == "Shipped the service in Python"
    assert client2.calls == 0  # both propose and judge served from cache
