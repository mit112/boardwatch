"""Unit tests for `build_rewrite_request` (P7b task 4, agent lane step 1).

Pure logic only — no CLI, no DB. The CLI pipeline test lives alongside the other
`tailor` CLI tests in tests/unit/test_tailor_cmd_rewrite.py.
"""

from __future__ import annotations

from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.rewrite.agent_io import (
    Candidate,
    CandidatesFile,
    JudgeItem,
    Verdict,
    VerdictsFile,
)
from boardwatch.tailor.rewrite.agent_lane import (
    ScreenDrop,
    apply_agent_rewrites,
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
        candidates=[Candidate(bullet_id="b1", candidate="Built the Python service")],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert drops == []
    assert judge_req.request_id == "r1"
    assert judge_req.items == [
        JudgeItem(
            bullet_id="b1", a_text="Built a Python service", candidate="Built the Python service"
        )
    ]


def test_screen_drops_fabricated_reword_as_provenance(tmp_path) -> None:
    """The same veto run_tier_b_core applies, run here too: this step's whole point is to
    screen out candidates before an external judge agent call, and a fabricated reword is
    exactly the kind of call not worth spending."""
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        # "quickly" is not in the source, not a connective, not an equivalence image --
        # passes the overmatch filter (no invented entity/skill/number) but not provenance.
        candidates=[Candidate(bullet_id="b1", candidate="Built a Python service quickly")],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert judge_req.items == []
    assert ScreenDrop(bullet_id="b1", reason="provenance") in drops


def test_screen_drops_unknown_bullet_id(tmp_path) -> None:
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="nope", candidate="Anything")],
    )
    judge_req, drops = screen_candidates(tailored, candidates, _tax(tmp_path), request_id="r1")
    assert judge_req.items == []
    assert ScreenDrop(bullet_id="nope", reason="unknown_bullet") in drops


# --- apply_agent_rewrites (P7b task 6, agent lane step 3) -------------------------------


def test_apply_agent_rewrites_keeps_exact_entailed_verdict(tmp_path) -> None:
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="b1", candidate="Built the Python service")],
    )
    verdicts = VerdictsFile(
        request_id="r1", verdicts=[Verdict(bullet_id="b1", raw_reply="ENTAILED")]
    )
    result = apply_agent_rewrites(tailored, candidates, verdicts, _tax(tmp_path), {"python"})
    assert any(rw.bullet_id == "b1" for rw in result.accepted)
    row = next(r for r in result.rows if r.bullet_id == "b1")
    assert row.kept is True
    assert row.drop_reason is None


def test_apply_agent_rewrites_drops_non_canonical_verdict(tmp_path) -> None:
    """`ENTAILED (low confidence)` is not the exact token ENTAILED -- parse_verdict's
    exact-token contract must hold through the agent lane, same as the API lane."""
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="b1", candidate="Built the Python service")],
    )
    verdicts = VerdictsFile(
        request_id="r1",
        verdicts=[Verdict(bullet_id="b1", raw_reply="ENTAILED (low confidence)")],
    )
    result = apply_agent_rewrites(tailored, candidates, verdicts, _tax(tmp_path), {"python"})
    assert not any(rw.bullet_id == "b1" for rw in result.accepted)
    row = next(r for r in result.rows if r.bullet_id == "b1")
    assert row.kept is False
    assert row.drop_reason == "judge"


def test_apply_agent_rewrites_missing_verdict_and_missing_candidate_drop_closed(
    tmp_path,
) -> None:
    """b1 has a candidate but no verdict entry (judge never answered) -> dropped "judge"
    via the MISSING sentinel (fail-closed). b2 has no candidate at all -> dropped
    "no_candidate"."""
    tailored = _sample_tailored_resume()
    candidates = CandidatesFile(
        request_id="r1",
        candidates=[Candidate(bullet_id="b1", candidate="Built the Python service")],
    )
    verdicts = VerdictsFile(request_id="r1", verdicts=[])
    result = apply_agent_rewrites(tailored, candidates, verdicts, _tax(tmp_path), {"python"})

    row_b1 = next(r for r in result.rows if r.bullet_id == "b1")
    assert row_b1.kept is False
    assert row_b1.drop_reason == "judge"

    row_b2 = next(r for r in result.rows if r.bullet_id == "b2")
    assert row_b2.kept is False
    assert row_b2.drop_reason == "no_candidate"
