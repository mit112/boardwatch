"""P4 item 1: the overmatch (verbatim-lift / unusual-caps) veto slotted into
run_tier_b_core, immediately AFTER the provenance veto and before the judge. Order matters:
a bullet must be both fact-safe (provenance) and lift-free (overmatch) to ship (D-048).

Word choice in these fixtures deliberately avoids boardwatch's real taxonomy.yaml skill
terms (e.g. "distributed systems", "Python") so the unrelated overmatch filter/invented-
skill check never fires and masks what these tests are actually pinning.
"""

from __future__ import annotations

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.rewrite.lane import run_tier_b_core

_TABLE = EquivalenceTable(pairs=(), version="test")
_A_TEXT = "Built the launch plan"
_JD = "You will collaborate closely with cross functional partners to launch new features fast"

# A résumé bullet that happens to substantially overlap the JD's own phrasing -- every word
# in `_LIFT_REWRITE` traces back to `_LIFT_A_TEXT` (so provenance passes it), but the
# rewrite still lifts a verbatim >=7-token span shared with `_LIFT_JD`, which is exactly the
# style/lift overmatch exists to catch on top of provenance's fact check.
_LIFT_A_TEXT = "Built the plan to collaborate closely with cross functional partners to launch features"
_LIFT_REWRITE = "Built plan to collaborate closely with cross functional partners to launch features"
_LIFT_JD = "Our team will collaborate closely with cross functional partners to launch new products fast"


def _resume(text: str = _A_TEXT) -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(entry_id="e1", heading="Work", bullets=[Bullet(bullet_id="b1", text=text)]),
        ],
    )


class _CountingJudge:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def __call__(self, a_text: str, candidate: str) -> str:
        self.calls += 1
        return self.reply


def test_verbatim_jd_lift_is_dropped_to_tier_a_before_the_judge(tmp_path) -> None:
    # "collaborate closely with cross functional partners to" is a verbatim 7-gram lift
    # shared with _LIFT_JD, and every token in the rewrite traces to _LIFT_A_TEXT (so
    # provenance would pass it) -- overmatch is what has to catch it.
    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return _LIFT_REWRITE

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(_LIFT_A_TEXT),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        jd_text=_LIFT_JD,
        canonical=frozenset(),
    )
    assert res.accepted == []
    row = res.rows[0]
    assert row.kept is False
    assert row.drop_reason == "overmatch"
    assert row.filter_pass is True
    assert row.judge_verdict is None
    # The judge must never be called for an over-matching rewrite -- same fail-safe shape
    # as the provenance veto: the shipped bullet reverts to Tier-A's own text.
    assert judge.calls == 0


def test_studlycaps_copy_from_jd_is_dropped_to_tier_a(tmp_path) -> None:
    # FooBarWidget already appears in the Tier-A bullet (so the deterministic overmatch
    # FILTER's invented-entity check does not fire) -- the reword just carries it through
    # unchanged while ALSO copying the JD's identical unusual capitalization verbatim,
    # which is exactly what this guard exists to catch.
    a_text = "Built the FooBarWidget launch plan"
    jd = "Experience with our in-house FooBarWidget platform is required for this role"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built FooBarWidget launch plan"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        jd_text=jd,
        canonical=frozenset(),
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "overmatch"
    assert judge.calls == 0


def test_canonical_token_is_exempt_from_the_caps_veto(tmp_path) -> None:
    a_text = "Built the GraphQL launch plan"
    jd = "Experience with GraphQL is strongly preferred for this position"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built GraphQL launch plan"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        jd_text=jd,
        canonical=frozenset({"graphql"}),
    )
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert judge.calls == 1


def test_clean_rewrite_still_reaches_the_judge_and_ships(tmp_path) -> None:
    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built launch plan"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        jd_text=_JD,
        canonical=frozenset(),
    )
    assert judge.calls == 1
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert res.accepted[0].text == "Built launch plan"


def test_overmatch_drop_counts_one_call_against_budget(tmp_path) -> None:
    """The propose call already spent one unit of budget before the veto fires; the
    dropped bullet must not spend a second (no judge call)."""

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return _LIFT_REWRITE

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(_LIFT_A_TEXT),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        jd_text=_LIFT_JD,
        canonical=frozenset(),
    )
    assert res.calls_made == 1


def test_provenance_runs_before_overmatch(tmp_path) -> None:
    """A candidate that fails BOTH checks must drop with drop_reason="provenance", not
    "overmatch" -- pinning that the fact gate is evaluated first (D-048's stated order).
    "FooBarWidget" is copied verbatim from the JD with the JD's own unusual capitalization
    (an overmatch hit) AND the candidate adds "definitely", an unjustified token with no
    equivalence-table image and no place in the source or connective allowlist (a
    provenance miss). If overmatch ran first, this would drop as "overmatch" instead.
    """
    a_text = "Built the FooBarWidget launch plan"
    jd = "Experience with our in-house FooBarWidget platform is required for this role"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built the FooBarWidget launch plan definitely"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        jd_text=jd,
        canonical=frozenset(),
    )
    assert res.rows[0].drop_reason == "provenance"
    assert judge.calls == 0


def test_missing_jd_text_and_canonical_default_to_a_safe_no_op(tmp_path) -> None:
    """Existing callers that predate P4 item 1 (no jd_text/canonical passed) must keep
    working: an empty jd_text can never produce a verbatim lift or a caps-copy match."""

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built launch plan"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
    )
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
