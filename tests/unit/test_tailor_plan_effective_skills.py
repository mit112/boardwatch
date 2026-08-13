"""`effective_skills` is the one coverage primitive `build_plan` and projection share."""

from __future__ import annotations

import pytest

from boardwatch.extract.taxonomy import Taxonomy, TaxonomyPattern
from boardwatch.tailor import plan as plan_mod
from boardwatch.tailor.equivalences import EquivalencePair, EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.plan import build_plan, effective_skills


def _taxonomy(*names: str) -> Taxonomy:
    import re

    return Taxonomy(
        patterns=tuple(
            TaxonomyPattern(
                name=n,
                category="language",
                pattern=n,
                case_sensitive=False,
                regex=re.compile(n, re.IGNORECASE),
            )
            for n in names
        ),
        version="test-1",
        source="bundled",
    )


def _resume(*bullets: tuple[str, str]) -> Resume:
    return Resume(
        header=["Example Candidate", "candidate@example.com"],
        education=["Example University"],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="entry.one",
                heading="One",
                bullets=[Bullet(bullet_id=bid, text=text) for bid, text in bullets],
            )
        ],
    )


def test_effective_skills_returns_what_the_text_demonstrates() -> None:
    taxonomy = _taxonomy("python", "swift")
    found = effective_skills("Built a python service", {"python"}, EquivalenceTable((), "v"), taxonomy)
    assert found == {"python"}


def test_effective_skills_includes_swap_images_the_jd_makes_reachable() -> None:
    """The property that distinguishes this from a bare `taxonomy.extract`: an equivalence
    whose target the JD asks for counts as covered."""
    taxonomy = _taxonomy("golang")
    table = EquivalenceTable((EquivalencePair(from_phrase="golang", to_phrase="go"),), "v")
    found = effective_skills("Wrote golang services", {"go"}, table, taxonomy)
    assert found == {"golang", "go"}


def test_effective_skills_omits_a_swap_image_the_jd_never_asked_for() -> None:
    """Non-vacuity: the swap union is JD-gated, not unconditional."""
    taxonomy = _taxonomy("golang")
    table = EquivalenceTable((EquivalencePair(from_phrase="golang", to_phrase="go"),), "v")
    found = effective_skills("Wrote golang services", {"rust"}, table, taxonomy)
    assert found == {"golang"}


def test_build_plan_routes_through_effective_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drift test, scoped honestly.

    It asserts `build_plan` and projection score with ONE callable — not that the callable is
    the repo's only coverage implementation. It is not: `reports/tailor.py:255` and `:271` omit
    the swap union and `tailor/coverage.py:55-61` scores a different corpus, so folding those in
    would change their emitted audit values. Replacing the callable and observing `build_plan`
    change is what proves the routing, and it cannot pass if the closure is reinstated.
    """
    taxonomy = _taxonomy("python")
    resume = _resume(("b1", "Built a python service"), ("b2", "Wrote documentation"))

    calls: list[str] = []

    def fake(text: str, jd_skills: set[str], table: EquivalenceTable, tax: Taxonomy) -> set[str]:
        calls.append(text)
        return set()

    monkeypatch.setattr(plan_mod, "effective_skills", fake)
    result = build_plan(resume, {"python"}, EquivalenceTable((), "v"), taxonomy)

    assert calls, "build_plan never called effective_skills"
    # Every bullet scored 0 through the stub, so the all-zero early return fires.
    assert result.ops == ()


def test_the_empty_jd_skills_early_return_is_preserved() -> None:
    """P0's gate, arm 1. `plan.py:68-69`."""
    resume = _resume(("b1", "Built a python service"))
    assert build_plan(resume, set(), EquivalenceTable((), "v"), _taxonomy("python")).ops == ()


def test_the_all_zero_coverage_early_return_is_preserved() -> None:
    """P0's gate, arm 2. `plan.py:81-82`. The JD is non-empty and nothing matches."""
    resume = _resume(("b1", "Wrote documentation"))
    assert build_plan(resume, {"python"}, EquivalenceTable((), "v"), _taxonomy("python")).ops == ()
