"""P4 item 3b: the requirement-echo gate slotted into run_tier_b_core, same fail-safe-
revert-to-Tier-A shape as overmatch/register -- see test_rewrite_lane_overmatch.py's
module docstring for the convention this file follows.

`qualification_sentences` is computed ONCE per résumé by the caller (`run_tier_b`/
`apply_agent_rewrites`, via `jd_qualification_sentences`), not derived here -- these
tests supply it directly, the same way test_rewrite_lane_register.py supplies `register`
directly rather than loading register.yaml.
"""

from __future__ import annotations

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.register import RegisterTable
from boardwatch.tailor.rewrite.lane import run_tier_b_core

_TABLE = EquivalenceTable(pairs=(), version="test")
_REGISTER = RegisterTable(
    banned_phrases=(),
    buzzwords=(),
    buzzword_density_ceiling=0,
    qualification_cues=("experience with", "experience building"),
    version="test",
)
_QUAL_SENTENCES = (
    "You have experience building scalable REST APIs in Python or a similar framework.",
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


def test_echo_rewrite_is_dropped_to_tier_a_before_the_judge(tmp_path) -> None:
    # Source bullet already carries every content word the echo candidate below uses,
    # so provenance stays clean and the requirement-echo gate is what's under test.
    a_text = (
        "Built scalable REST APIs using Python and Django, drawing on experience "
        "building distributed systems for the team"
    )

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Experience with building scalable REST APIs using Python and Django"

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
        qualification_sentences=_QUAL_SENTENCES,
    )
    assert res.accepted == []
    row = res.rows[0]
    assert row.kept is False
    assert row.drop_reason == "requirement_echo"
    assert row.filter_pass is True
    assert row.judge_verdict is None
    assert judge.calls == 0
    assert res.calls_made == 1  # only the propose call, never the judge


def test_clean_rewrite_still_reaches_the_judge_and_ships(tmp_path) -> None:
    a_text = "Built the backend service for checkout, cutting latency significantly"

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built the backend service for checkout"

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
        qualification_sentences=_QUAL_SENTENCES,
    )
    assert judge.calls == 1
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert res.accepted[0].text == "Built the backend service for checkout"


def test_missing_qualification_sentences_defaults_to_a_safe_no_op(tmp_path) -> None:
    """Existing callers that predate P4 item 3b (no `qualification_sentences` passed)
    must keep working: with no corroboration material, an echo can never be flagged."""
    a_text = (
        "Built scalable REST APIs using Python and Django, drawing on experience "
        "building distributed systems for the team"
    )

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Experience with building scalable REST APIs using Python and Django"

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
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert judge.calls == 1


def test_register_gates_run_before_requirement_echo(tmp_path) -> None:
    """A candidate hitting BOTH banned-register and requirement-echo must drop with the
    earlier-checked reason -- an implementation-order pin, not a correctness requirement
    (both gates fail-safe-revert identically)."""
    a_text = (
        "Was responsible for building scalable REST APIs using Python and Django, "
        "drawing on experience building distributed systems for the team"
    )
    register = RegisterTable(
        banned_phrases=("responsible for",),
        buzzwords=(),
        buzzword_density_ceiling=0,
        qualification_cues=("experience with", "experience building"),
        version="test",
    )

    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Was responsible for building scalable REST APIs using Python and Django"

    judge = _CountingJudge("ENTAILED")
    res = run_tier_b_core(
        _resume(a_text),
        propose=propose,
        judge=judge,
        taxonomy=load_taxonomy(tmp_path),
        table=_TABLE,
        jd_skills=set(),
        budget=50,
        register=register,
        qualification_sentences=_QUAL_SENTENCES,
    )
    assert res.rows[0].drop_reason == "banned_register"
    assert judge.calls == 0
