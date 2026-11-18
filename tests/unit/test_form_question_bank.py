"""T312: the form-question bank counts what open, eligible postings ask, and whether it is answered.

Expected values are worked out by hand from the fixture below, never from the query.

Fixture (every posting is its own job; `ph`/`rh` is the identity the verdicts are written under):
  A  open, eligible     "First Name", "Are you authorized?", "How did you hear about us?"
  B  open, eligible     "are  you AUTHORIZED?", "How did you hear about us?", "How did you hear about us? "
  H  open, eligible     "How did you hear about us?"
  C  open, uncertain    "Are you authorized?", "Abstain only"
  D  open, ineligible   "Ineligible only"
  E  closed, eligible   "Closed only"
  F  open, eligible     "Superseded only", on a version a NEWER version replaced (see `_superseded`)
  G  open, no verdict   "Unevaluated only"
So 8 stored forms: 3 eligible, 1 abstain, 1 ineligible, 1 unevaluated, 1 closed, 1 superseded.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text

from boardwatch.eligibility.engine import ENGINE_KIND, engine_version
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.form_question_bank_queries import TOP_QUESTIONS, form_question_bank
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    jobs,
    posting_form_questions,
    postings,
)

T0 = datetime(2026, 11, 1, 12, 0, 0)
IDENTITY = ("ph", "rh")


@pytest.fixture(autouse=True)
def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(conn: Connection) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
            )
        ).inserted_primary_key[0]
    )


def _posting(conn: Connection, company: int, key: str, status: str = "open") -> int:
    job = int(conn.execute(insert(jobs).values(created_at=T0)).inserted_primary_key[0])
    return int(
        conn.execute(
            insert(postings).values(
                company_id=company,
                job_id=job,
                provider_posting_id=key,
                title="Engineer",
                normalized_title="engineer",
                remote_policy="remote",
                first_seen_at=T0,
                last_seen_at=T0,
                status=status,
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )


def _version(conn: Connection, posting: int, captured: str) -> int:
    """A posting version whose `captured_at` is written as text, so it can carry an offset."""
    return int(
        conn.execute(
            text(
                "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at,"
                " capture_reason) VALUES (:p, :h, 'body', :c, 'new')"
            ),
            {"p": posting, "h": f"v-{posting}-{captured}", "c": captured},
        ).lastrowid
    )


def _form(conn: Connection, version: int, labels: list[str]) -> None:
    conn.execute(
        insert(posting_form_questions).values(
            posting_version_id=version,
            questions_json=[
                {"label": label, "description": None, "options": []} for label in labels
            ],
            fetched_at=T0,
        )
    )


def _verdict(conn: Connection, version: int, verdict: str) -> None:
    """A current deterministic evaluation of `version` under `IDENTITY`."""
    input_id = int(
        conn.execute(
            insert(eligibility_inputs).values(
                posting_version_id=version,
                profile_hash=IDENTITY[0],
                profile_snapshot_json={},
                rules_hash=IDENTITY[1],
                rules_snapshot_json={},
                input_fingerprint=f"fp-{version}",
                created_at=T0,
            )
        ).inserted_primary_key[0]
    )
    conn.execute(
        insert(eligibility_evaluations).values(
            input_id=input_id,
            engine_kind=ENGINE_KIND,
            engine_version=engine_version(),
            verdict=verdict,
            created_at=T0,
        )
    )


def _seed(conn: Connection) -> None:
    company = _company(conn)

    def posting(key: str, verdict: str | None, labels: list[str], status: str = "open") -> int:
        pid = _posting(conn, company, key, status)
        version = _version(conn, pid, "2026-11-01 12:00:00")
        _form(conn, version, labels)
        if verdict is not None:
            _verdict(conn, version, verdict)
        return pid

    posting("A", "eligible", ["First Name", "Are you authorized?", "How did you hear about us?"])
    posting(
        "B",
        "eligible",
        ["are  you AUTHORIZED?", "How did you hear about us?", "How did you hear about us? "],
    )
    posting("H", "eligible", ["How did you hear about us?"])
    posting("C", "uncertain", ["Are you authorized?", "Abstain only"])
    posting("D", "ineligible", ["Ineligible only"])
    posting("E", "eligible", ["Closed only"], status="closed")
    posting("G", None, ["Unevaluated only"])
    # F: the form sits on the OLDER version by instant. By TEXT the old stamp sorts last
    # ("13:00:00" > "09:00:00-05:00"), so text order would call it current; by instant it is
    # 13:00Z against 14:00Z, and the newer version has no form.
    f = _posting(conn, company, "F")
    old = _version(conn, f, "2026-11-01 13:00:00")
    _version(conn, f, "2026-11-01 09:00:00-05:00")
    _form(conn, old, ["Superseded only"])
    _verdict(conn, old, "eligible")


def test_counts_and_orders_the_bank_by_hand(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        got = form_question_bank(
            conn, identity=IDENTITY, answered=["  how DID you hear   about us? "]
        )

    assert got["forms"] == {
        "stored": 8,
        "eligible": 3,
        "abstain": 1,
        "ineligible": 1,
        "unevaluated": 1,
        "closed": 1,
        "superseded": 1,
        "no_questions": 0,
    }
    # "Are you authorized?" is asked by A and B (C abstains and is not counted); "How did you hear
    # about us?" by A, B and H, once each even though B repeats it. "First Name" is a built-in.
    # The answered one is MORE common (3 against 2) and still comes last: unanswered first.
    assert got["questions"] == [
        {"question": "Are you authorized?", "count": 2, "answered": False},
        {"question": "How did you hear about us?", "count": 3, "answered": True},
    ]
    assert (got["distinct"], got["unanswered"], got["answers_readable"]) == (2, 1, True)


def test_a_near_match_is_not_an_answer(engine: Engine) -> None:
    """Only whitespace and case are normalised: a missing question mark is a different question."""
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        got = form_question_bank(conn, identity=IDENTITY, answered=["Are you authorized"])
    assert [row["answered"] for row in got["questions"]] == [False, False]


def test_an_unreadable_answers_file_claims_neither_state(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        got = form_question_bank(conn, identity=IDENTITY, answered=None)
    assert got["answers_readable"] is False
    assert got["unanswered"] is None
    # By count alone: 3 before 2.
    assert [(r["count"], r["answered"]) for r in got["questions"]] == [(3, None), (2, None)]


def test_no_profile_means_every_form_is_unevaluated(engine: Engine) -> None:
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        got = form_question_bank(conn, identity=None, answered=[])
    assert got["questions"] == []
    # F's form is on a replaced version and E's posting is closed whatever the profile says.
    assert got["forms"]["unevaluated"] == 6
    assert got["forms"]["eligible"] == 0


def test_the_cap_keeps_unanswered_questions_over_a_more_common_answered_one(
    engine: Engine,
) -> None:
    labels = [f"Unanswered {i:02d}" for i in range(TOP_QUESTIONS + 2)]
    with engine.begin() as conn:
        company = _company(conn)
        for i, label in enumerate(labels):
            pid = _posting(conn, company, f"u{i}")
            version = _version(conn, pid, "2026-11-01 12:00:00")
            _form(conn, version, [label])
            _verdict(conn, version, "eligible")
        for i in range(5):
            pid = _posting(conn, company, f"a{i}")
            version = _version(conn, pid, "2026-11-01 12:00:00")
            _form(conn, version, ["Answered"])
            _verdict(conn, version, "eligible")
    with engine.connect() as conn:
        got = form_question_bank(conn, identity=IDENTITY, answered=["Answered"])
    assert len(got["questions"]) == TOP_QUESTIONS
    assert all(row["answered"] is False for row in got["questions"])
    assert got["distinct"] == TOP_QUESTIONS + 3
    assert got["unanswered"] == TOP_QUESTIONS + 2
    # Equal counts fall to text order, so the first rows are the lowest numbers.
    assert got["questions"][0]["question"] == "Unanswered 00"


def test_the_payload_has_no_room_for_answer_text(engine: Engine) -> None:
    """The bank is handed question texts only; nothing of an answer can be in what it returns."""
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        got = form_question_bank(conn, identity=IDENTITY, answered=["How did you hear about us?"])
    assert set(got) == {
        "forms",
        "answers_readable",
        "distinct",
        "unanswered",
        "standard_fields",
        "questions",
    }
    assert all(set(row) == {"question", "count", "answered"} for row in got["questions"])
    json.dumps(got)  # serialisable as-is


def test_a_board_with_no_form_is_not_counted_as_a_form(engine: Engine) -> None:
    """One eligible posting with a form (one question), one whose cached form is `[]`."""
    with engine.begin() as conn:
        company = _company(conn)
        real = _version(conn, _posting(conn, company, "r"), "2026-11-01 12:00:00")
        _form(conn, real, ["Why us?"])
        _verdict(conn, real, "eligible")
        empty = _version(conn, _posting(conn, company, "e"), "2026-11-01 12:00:00")
        _form(conn, empty, [])
        _verdict(conn, empty, "eligible")
    with engine.connect() as conn:
        got = form_question_bank(conn, identity=IDENTITY, answered=[])
    assert (got["forms"]["eligible"], got["forms"]["no_questions"]) == (1, 1)
