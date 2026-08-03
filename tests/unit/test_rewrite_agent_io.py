"""Tests for agent-lane JSON payload types (agent_io.py).

Validates round-trip serialization and the critical invariant: JudgeRequest
is JD-blind by construction (no jd_skills field in the judge).
"""

from pathlib import Path

from src.boardwatch.tailor.rewrite.agent_io import (
    BulletRef,
    Candidate,
    CandidatesFile,
    JudgeItem,
    JudgeRequest,
    RewriteRequest,
    Verdict,
    VerdictsFile,
    dump_json,
    load_json,
)


def test_judge_request_has_no_jd_field():
    """JudgeRequest and JudgeItem must NOT have a jd_skills field.

    This is the critical invariant: the judge is JD-blind by construction.
    """
    assert "jd_skills" not in JudgeRequest.model_fields
    assert "jd" not in JudgeRequest.model_json_schema()["$defs"]["JudgeItem"]["properties"]


def test_rewrite_request_round_trips(tmp_path: Path):
    """RewriteRequest round-trips through JSON serialization."""
    r = RewriteRequest(
        request_id="r1",
        jd_skills=["python", "kubernetes"],
        bullets=[
            BulletRef(bullet_id="b1", entry_id="e1", a_text="Built X"),
            BulletRef(bullet_id="b2", entry_id="e2", a_text="Led Y"),
        ],
    )
    p = tmp_path / "req.json"
    dump_json(r, p)
    loaded = load_json(RewriteRequest, p)
    assert loaded == r


def test_candidates_file_round_trips(tmp_path: Path):
    """CandidatesFile round-trips through JSON serialization."""
    cf = CandidatesFile(
        request_id="r1",
        candidates=[
            Candidate(bullet_id="b1", candidate="Designed resilient X"),
            Candidate(bullet_id="b2", candidate="Orchestrated Y"),
        ],
    )
    p = tmp_path / "candidates.json"
    dump_json(cf, p)
    loaded = load_json(CandidatesFile, p)
    assert loaded == cf


def test_judge_request_is_jd_free(tmp_path: Path):
    """JudgeRequest is JD-free and round-trips correctly."""
    judge_req = JudgeRequest(
        request_id="r1",
        items=[
            JudgeItem(bullet_id="b1", a_text="Built X", candidate="Designed resilient X"),
            JudgeItem(bullet_id="b2", a_text="Led Y", candidate="Orchestrated Y"),
        ],
    )
    p = tmp_path / "judge.json"
    dump_json(judge_req, p)
    loaded = load_json(JudgeRequest, p)
    assert loaded == judge_req


def test_verdicts_file_round_trips(tmp_path: Path):
    """VerdictsFile round-trips through JSON serialization."""
    vf = VerdictsFile(
        request_id="r1",
        verdicts=[
            Verdict(bullet_id="b1", raw_reply="yes"),
            Verdict(bullet_id="b2", raw_reply="partial"),
        ],
    )
    p = tmp_path / "verdicts.json"
    dump_json(vf, p)
    loaded = load_json(VerdictsFile, p)
    assert loaded == vf
