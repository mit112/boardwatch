"""Unit tests for `build_rewrite_request` (P7b task 4, agent lane step 1).

Pure logic only — no CLI, no DB. The CLI pipeline test lives alongside the other
`tailor` CLI tests in tests/unit/test_tailor_cmd_rewrite.py.
"""

from __future__ import annotations

from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.rewrite.agent_io import Candidate, CandidatesFile, JudgeItem
from boardwatch.tailor.rewrite.agent_lane import (
    ScreenDrop,
    build_rewrite_request,
    screen_candidates,
)


def _sample_tailored_resume() -> Resume:
    return Resume(
        header=["Jane Doe"],
        education=["BSc CS"],
        skill_groups=[SkillGroup(label="Languages", items=["Python"])],
        entries=[
            Entry(
                entry_id="acme-sre",
                heading="Senior Engineer — Acme",
                bullets=[
                    Bullet(bullet_id="b1", text="Built a Python service"),
                    Bullet(bullet_id="b2", text="Led a migration to Rust"),
                ],
            )
        ],
    )


def test_build_rewrite_request_lists_kept_bullets() -> None:
    req = build_rewrite_request(_sample_tailored_resume(), {"python"}, request_id="r1")
    assert req.request_id == "r1"
    assert sorted(req.jd_skills) == ["python"]
    assert {b.bullet_id for b in req.bullets} == {"b1", "b2"}


def test_build_rewrite_request_carries_entry_id_and_text() -> None:
    req = build_rewrite_request(_sample_tailored_resume(), {"python"}, request_id="r1")
    by_id = {b.bullet_id: b for b in req.bullets}
    assert by_id["b1"].entry_id == "acme-sre"
    assert by_id["b1"].a_text == "Built a Python service"
    assert by_id["b2"].entry_id == "acme-sre"
    assert by_id["b2"].a_text == "Led a migration to Rust"


def test_build_rewrite_request_sorts_jd_skills_deterministically() -> None:
    req = build_rewrite_request(
        _sample_tailored_resume(), {"rust", "python", "kubernetes"}, request_id="r2"
    )
    assert req.jd_skills == ["kubernetes", "python", "rust"]


def test_build_rewrite_request_empty_entries_yields_no_bullets() -> None:
    empty = Resume(header=[], education=[], skill_groups=[], entries=[])
    req = build_rewrite_request(empty, set(), request_id="r3")
    assert req.bullets == []
    assert req.jd_skills == []


# --- screen_candidates (P7b task 5, agent lane step 2) ---------------------------------


def _tax(tmp_path):
    from boardwatch.extract.taxonomy import load_taxonomy

    return load_taxonomy(tmp_path)


def test_screen_drops_filter_rejects_invented_brand(tmp_path) -> None:
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[
            Candidate(bullet_id="b1", candidate="Built a Python service for Google"),
        ],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert judge_req.items == []
    assert ScreenDrop(bullet_id="b1", reason="filter:invented_entity") in drops


def test_screen_drops_unchanged_candidate(tmp_path) -> None:
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="b1", candidate="Built a Python service")],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert judge_req.items == []
    assert ScreenDrop(bullet_id="b1", reason="unchanged") in drops


def test_screen_keeps_passing_candidate_with_cli_a_text(tmp_path) -> None:
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="b1", candidate="Shipped a Python service")],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert drops == []
    assert judge_req.request_id == "r1"
    assert judge_req.items == [
        JudgeItem(
            bullet_id="b1", a_text="Built a Python service", candidate="Shipped a Python service"
        )
    ]


def test_screen_drops_unknown_bullet_id(tmp_path) -> None:
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="nope", candidate="Anything")],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert judge_req.items == []
    assert ScreenDrop(bullet_id="nope", reason="unknown_bullet") in drops
