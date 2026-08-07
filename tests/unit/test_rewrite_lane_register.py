"""P4 item 3a: the two per-bullet register gates (banned-register, buzzword-density)
slotted into run_tier_b_core, in the same fail-safe-revert-to-Tier-A shape as
overmatch/provenance -- see test_rewrite_lane_overmatch.py's module docstring for the
convention this file follows.

Word choice deliberately avoids boardwatch's real taxonomy.yaml skill terms so the
unrelated invented-skill filter never fires and masks what these tests are pinning.
"""

from __future__ import annotations

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.register import RegisterTable
from boardwatch.tailor.rewrite.lane import run_tier_b_core

_TABLE = EquivalenceTable(pairs=(), version="test")
_REGISTER = RegisterTable(
    banned_phrases=("responsible for", "synergy"),
    buzzwords=("innovative", "seamless"),
    buzzword_density_ceiling=1,
    qualification_cues=(),
    version="test",
)


def _resume(text: str) -> Resume:
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


def test_banned_phrase_in_rewrite_is_dropped_to_tier_a_before_the_judge(tmp_path) -> None:
    a_text = "Was responsible for the launch plan"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Was responsible for the launch"  # subset of a_text -> provenance-clean

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        register=_REGISTER,
    )
    assert res.accepted == []
    row = res.rows[0]
    assert row.kept is False
    assert row.drop_reason == "banned_register"
    assert row.filter_pass is True
    assert row.judge_verdict is None
    assert judge.calls == 0
    assert res.calls_made == 1  # only the propose call, never the judge


def test_buzzword_density_over_ceiling_is_dropped_to_tier_a(tmp_path) -> None:
    a_text = "Built an innovative and seamless system for users"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built an innovative and seamless system"  # 2 buzzwords, ceiling is 1

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        register=_REGISTER,
    )
    assert res.accepted == []
    assert res.rows[0].drop_reason == "buzzword_density"
    assert judge.calls == 0


def test_clean_rewrite_still_reaches_the_judge_and_ships(tmp_path) -> None:
    a_text = "Built the launch plan for a growing team"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built the launch plan"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        register=_REGISTER,
    )
    assert judge.calls == 1
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert res.accepted[0].text == "Built the launch plan"


def test_missing_register_defaults_to_a_safe_no_op(tmp_path) -> None:
    """Existing callers that predate P4 item 3a (no `register` passed) must keep working:
    an empty catalog can never flag a banned phrase or buzzword cluster."""
    a_text = "Was responsible for the launch plan"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Was responsible for the launch"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
    )
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert judge.calls == 1


def test_provenance_runs_before_the_register_gates(tmp_path) -> None:
    """A candidate that fails BOTH provenance and banned-register must drop with
    drop_reason="provenance", not "banned_register" -- pinning that the fact gate is
    evaluated first, same ordering discipline as overmatch's own test of this shape."""
    a_text = "Built the plan with the team"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        # "synergy" is a banned phrase AND has no source/connective/equivalence
        # justification of its own -- a provenance miss.
        return "Built the plan with synergy"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        register=_REGISTER,
    )
    assert res.rows[0].drop_reason == "provenance"
    assert judge.calls == 0


def test_banned_register_runs_before_buzzword_density(tmp_path) -> None:
    """A candidate hitting both gates must drop with the earlier-checked reason
    ("banned_register") -- an implementation-order pin, not a correctness requirement
    (both gates fail-safe-revert identically)."""
    a_text = "Was responsible for an innovative and seamless launch plan"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Was responsible for an innovative and seamless launch"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        register=_REGISTER,
    )
    assert res.rows[0].drop_reason == "banned_register"
