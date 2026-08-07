"""P1b task 2: the provenance veto slotted into run_tier_b_core, between the overmatch
filter and the judge. A fabricated reword must never reach the judge -- the veto has to
run BEFORE it, not after (a test that only checked the final `kept`/`drop_reason` could
still pass with the veto misplaced after the judge; the call-count assertion here is what
actually pins the ordering).
"""

from __future__ import annotations

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.equivalences import EquivalenceTable
from boardwatch.tailor.model import Bullet, Entry, Resume
from boardwatch.tailor.rewrite.lane import run_tier_b_core

_TABLE = EquivalenceTable(pairs=(), version="test")
_A_TEXT = "Built the service in Python"


def _resume(text: str = _A_TEXT) -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="Work",
                bullets=[Bullet(bullet_id="b1", text=text)],
            )
        ],
    )


class _CountingJudge:
    """A Judge callable (not a ModelClient) that records how many times it was invoked."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def __call__(self, a_text: str, candidate: str) -> str:
        self.calls += 1
        return self.reply


def test_fabricated_reword_vetoed_before_judge(tmp_path) -> None:
    # "quickly" is not in the source, not a connective, and not an equivalence image --
    # a fabrication that still passes the overmatch filter (no invented entity/skill/
    # number), so the provenance check is what has to catch it.
    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built the service in Python quickly"

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
    assert res.accepted == []
    row = res.rows[0]
    assert row.kept is False
    assert row.drop_reason == "provenance"
    assert row.filter_pass is True
    assert row.judge_verdict is None
    # The judge must never be called for a vetoed reword -- spending it would defeat the
    # point of running the check before the judge (saves the call, not just the outcome).
    assert judge.calls == 0


def test_clean_reword_still_reaches_the_judge(tmp_path) -> None:
    # Every token here traces to the source or the connective allowlist ("the"/"a") --
    # nothing new, so the veto must let it through to the judge as before.
    def propose(a_text: str, jd_skills: set[str]) -> str | None:
        return "Built the Python service"

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
    assert judge.calls == 1
    assert res.rows[0].kept is True
    assert res.rows[0].drop_reason is None
    assert res.accepted[0].text == "Built the Python service"
