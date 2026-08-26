"""The answers panel — `boardwatch.delivery.answers`.

Every test below is aimed at one way a plausible implementation gets this wrong, and fails
against it:

* an implementation that treats an absent `answers.yaml` as an error gives a first-run user a
  broken page, so the missing-file case is the first test;
* an implementation that folds `note` into the answer text puts a "do not reuse as-is" warning
  on the clipboard, so the note test walks EVERY string reachable from the panel and asserts the
  marker appears at exactly one path;
* an implementation that lets `answers.yaml` shadow the stored eligibility facts, or that
  defaults an unanswered work-authorisation field, answers an employer's most consequential
  question wrongly;
* an implementation that skips a malformed `questions` entry returns a panel that is quietly
  short one answer, which is indistinguishable from a panel that is complete.

`tmp_path` throughout. Nothing here may reach the owner's real config directory.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from boardwatch.delivery.answers import (
    EDUCATION_FIELD,
    IDENTITY_FIELDS,
    WORK_AUTH_FIELDS,
    AnswersError,
    AnswersIssue,
    AnswersPanel,
    example_answers_text,
    load_answers,
)
from boardwatch.eligibility.facts import Facts, WorkAuthFact, facts_payload
from boardwatch.store.db import ensure_schema, get_engine, get_readonly_engine
from boardwatch.store.queries import save_eligibility, save_profile

# ---------------------------------------------------------------------------------------
# helpers


def write_answers(config_dir: Path, text: str) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "answers.yaml").write_text(text, encoding="utf-8")


RESUME_YAML = """\
header:
  - "Ada Lovelace"
  - "ada@example.com"
education:
  - "BSc Mathematics — Example University — 2018"
  - "MSc Computing — Example Institute — 2020"
skill_groups: []
entries: []
"""


def write_resume(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "resume.yaml").write_text(RESUME_YAML, encoding="utf-8")


def store(tmp_path: Path) -> Engine:
    """A real store with the real schema, so `get_profile` reads the production shape."""
    engine = get_engine(tmp_path / "store")
    ensure_schema(engine)
    return engine


def seed_profile(engine: Engine, facts: Facts | None) -> None:
    with engine.begin() as conn:
        save_profile(
            conn,
            text="Backend engineer.",
            target_titles=[],
            exclude_titles=[],
            locations=[],
            remote_only=False,
            skills=[],
            taxonomy_version="t",
            resume_max_pages=1,
        )
        if facts is not None:
            # Written through the production writer over the production fact model, so a
            # change to either shape fails here rather than passing over a stale literal.
            save_eligibility(conn, facts_json=facts_payload(facts), policy_json={})


def strings(value: object, path: str) -> Iterator[tuple[str, str]]:
    """Every string reachable from `value`, with the dotted path it was found at."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, f"{path}[{key}]")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            yield from strings(item, f"{path}[{index}]")
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from strings(getattr(value, field.name), f"{path}.{field.name}")


def every_expected_field() -> list[str]:
    return (
        [f"identity.{name}" for name in IDENTITY_FIELDS]
        + [f"work_auth.{name}" for name in WORK_AUTH_FIELDS]
        + [EDUCATION_FIELD]
    )


# ---------------------------------------------------------------------------------------
# 1. a missing file is not an error


def test_a_missing_answers_file_yields_an_empty_panel_naming_every_field(tmp_path: Path) -> None:
    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel == AnswersPanel(
        identity={}, work_auth={}, education=[], questions=[], missing=every_expected_field()
    )


def test_a_missing_answers_file_still_resolves_education(tmp_path: Path) -> None:
    """The absent file must not short-circuit the sources that are NOT in it."""
    write_resume(tmp_path)

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.education == [
        "BSc Mathematics — Example University — 2018",
        "MSc Computing — Example Institute — 2020",
    ]
    assert EDUCATION_FIELD not in panel.missing


def test_an_empty_answers_file_is_treated_as_no_answers(tmp_path: Path) -> None:
    write_answers(tmp_path, "\n# nothing declared yet\n")

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.missing == every_expected_field()


# ---------------------------------------------------------------------------------------
# 2. identity and questions


def test_identity_and_questions_load_from_the_file(tmp_path: Path) -> None:
    write_answers(
        tmp_path,
        """
identity:
  full_name: "Ada Lovelace"
  email: "ada@example.com"
questions:
  - q: "Notice period"
    a: "Two weeks"
""",
    )

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.identity == {"full_name": "Ada Lovelace", "email": "ada@example.com"}
    assert panel.questions[0].q == "Notice period"
    assert panel.questions[0].a == "Two weeks"
    assert panel.questions[0].note is None
    assert "identity.full_name" not in panel.missing
    assert "identity.phone" in panel.missing


def test_a_blank_answer_is_missing_rather_than_an_empty_value(tmp_path: Path) -> None:
    """An empty column reads as a value (design §6.4), so a blank is an absence."""
    write_answers(tmp_path, 'identity:\n  full_name: "   "\n  email: ""\n')

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.identity == {}
    assert "identity.full_name" in panel.missing
    assert "identity.email" in panel.missing


def test_a_non_string_scalar_answer_is_rendered_not_dropped(tmp_path: Path) -> None:
    write_answers(tmp_path, "identity:\n  phone: 5550100\n")

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.identity == {"phone": "5550100"}


# ---------------------------------------------------------------------------------------
# 3. `note` never reaches a copyable value


def test_a_note_appears_at_exactly_one_path_and_never_inside_an_answer(tmp_path: Path) -> None:
    marker = "DO-NOT-PASTE-THIS-ANYWHERE"
    write_answers(
        tmp_path,
        f"""
identity:
  full_name: "Ada Lovelace"
work_auth:
  status: "declared here"
questions:
  - q: "Salary expectation"
    a: "Open to discussion"
    note: "{marker}: two of these claims are contradicted by the source repo"
""",
    )
    write_resume(tmp_path)

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert [path for path, value in strings(panel, "panel") if marker in value] == [
        "panel.questions[0].note"
    ]
    assert panel.questions[0].a == "Open to discussion"


# ---------------------------------------------------------------------------------------
# 4. work_auth: profile first, file second, `missing` third, never invented


def test_work_auth_prefers_the_stored_eligibility_facts_over_the_file(tmp_path: Path) -> None:
    engine = store(tmp_path)
    seed_profile(
        engine,
        Facts(
            work_authorization=WorkAuthFact(
                status="permanent_resident", jurisdiction="US", needs_sponsorship=False
            )
        ),
    )
    write_answers(
        tmp_path,
        """
work_auth:
  status: "STALE FILE VALUE"
  jurisdiction: "STALE FILE VALUE"
  needs_sponsorship: true
""",
    )

    with engine.connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {
        "status": "permanent_resident",
        "jurisdiction": "US",
        "needs_sponsorship": "no",
    }
    assert not [name for name in panel.missing if name.startswith("work_auth.")]


def test_a_fact_the_profile_does_not_answer_falls_back_to_the_file(tmp_path: Path) -> None:
    engine = store(tmp_path)
    seed_profile(engine, Facts(work_authorization=WorkAuthFact(status="student_visa")))
    write_answers(
        tmp_path,
        """
work_auth:
  status: "STALE FILE VALUE"
  jurisdiction: "US"
""",
    )

    with engine.connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {"status": "student_visa", "jurisdiction": "US"}
    # Answered by neither source. Never defaulted: a wrong work-authorisation answer on a
    # real application is worse than a blank one.
    assert "work_auth.needs_sponsorship" in panel.missing


def test_a_work_auth_field_neither_source_answers_is_never_defaulted(tmp_path: Path) -> None:
    engine = store(tmp_path)
    seed_profile(engine, Facts())

    with engine.connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {}
    assert [name for name in panel.missing if name.startswith("work_auth.")] == [
        f"work_auth.{name}" for name in WORK_AUTH_FIELDS
    ]


def test_a_profile_row_carrying_no_eligibility_facts_falls_back_to_the_file(
    tmp_path: Path,
) -> None:
    engine = store(tmp_path)
    seed_profile(engine, None)
    write_answers(tmp_path, 'work_auth:\n  status: "from the file"\n')

    with engine.connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {"status": "from the file"}


def test_no_profile_row_at_all_falls_back_to_the_file(tmp_path: Path) -> None:
    engine = store(tmp_path)
    write_answers(tmp_path, 'work_auth:\n  status: "from the file"\n')

    with engine.connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {"status": "from the file"}


def test_a_needs_sponsorship_fact_of_true_renders_yes(tmp_path: Path) -> None:
    engine = store(tmp_path)
    seed_profile(engine, Facts(work_authorization=WorkAuthFact(needs_sponsorship=True)))

    with engine.connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {"needs_sponsorship": "yes"}


def test_a_boolean_in_the_file_renders_yes_or_no(tmp_path: Path) -> None:
    write_answers(tmp_path, "work_auth:\n  needs_sponsorship: false\n")

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.work_auth == {"needs_sponsorship": "no"}


# ---------------------------------------------------------------------------------------
# 5. conn=None degrades to file-only


def test_conn_none_degrades_to_file_only_without_raising(tmp_path: Path) -> None:
    write_answers(
        tmp_path,
        """
identity:
  full_name: "Ada Lovelace"
work_auth:
  status: "citizen"
  jurisdiction: "US"
  needs_sponsorship: false
questions:
  - q: "Notice period"
    a: "Two weeks"
""",
    )
    write_resume(tmp_path)

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.work_auth == {
        "status": "citizen",
        "jurisdiction": "US",
        "needs_sponsorship": "no",
    }
    assert panel.education
    assert panel.questions


# ---------------------------------------------------------------------------------------
# 6. education comes from resume.yaml and is never retyped here


def test_education_is_missing_when_there_is_no_resume_yaml(tmp_path: Path) -> None:
    write_answers(tmp_path, 'identity:\n  full_name: "Ada Lovelace"\n')

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.education == []
    assert EDUCATION_FIELD in panel.missing


def test_education_is_missing_when_the_resume_yaml_is_unreadable(tmp_path: Path) -> None:
    (tmp_path / "resume.yaml").write_text("header: [:\n", encoding="utf-8")

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.education == []
    assert EDUCATION_FIELD in panel.missing


def test_education_is_missing_when_the_resume_yaml_declares_none(tmp_path: Path) -> None:
    (tmp_path / "resume.yaml").write_text(
        'header:\n  - "Ada Lovelace"\n  - "ada@example.com"\n', encoding="utf-8"
    )

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.education == []
    assert EDUCATION_FIELD in panel.missing


def test_education_declared_in_answers_yaml_is_refused_not_used(tmp_path: Path) -> None:
    """Education is read from the résumé, never retyped (design §9). A second copy that could
    disagree with the document being sent is refused rather than silently ignored."""
    write_resume(tmp_path)
    write_answers(tmp_path, 'education:\n  - "BSc Something Else"\n')

    with pytest.raises(AnswersError) as excinfo:
        load_answers(config_dir=tmp_path, conn=None)

    assert excinfo.value.violation.issue is AnswersIssue.UNKNOWN_FIELD


# ---------------------------------------------------------------------------------------
# 7. malformed input is a typed refusal, never a partially-populated panel


@pytest.mark.parametrize(
    ("text", "issue"),
    [
        ("identity: [:\n", AnswersIssue.MALFORMED_YAML),
        ("- one\n- two\n", AnswersIssue.NOT_A_MAPPING),
        ('"just a string"\n', AnswersIssue.NOT_A_MAPPING),
        ("identity:\n  - full_name\n", AnswersIssue.SECTION_NOT_A_MAPPING),
        ('work_auth: "citizen"\n', AnswersIssue.SECTION_NOT_A_MAPPING),
        ('questions:\n  q: "Notice period"\n', AnswersIssue.QUESTIONS_NOT_A_SEQUENCE),
        ('questions:\n  - "Notice period"\n', AnswersIssue.QUESTION_NOT_A_MAPPING),
        ('questions:\n  - q: "Notice period"\n', AnswersIssue.QUESTION_MISSING_FIELD),
        ('questions:\n  - a: "Two weeks"\n', AnswersIssue.QUESTION_MISSING_FIELD),
        ('questions:\n  - q: "Notice"\n    a: "  "\n', AnswersIssue.QUESTION_MISSING_FIELD),
        ('questions:\n  - q: "Notice"\n    a: "Two weeks"\n    x: 1\n', AnswersIssue.UNKNOWN_FIELD),
        ('identity:\n  nickname: "Ada"\n', AnswersIssue.UNKNOWN_FIELD),
        ('work_auth:\n  visa_kind: "H-1B"\n', AnswersIssue.UNKNOWN_FIELD),
        ('identity:\n  email: ["a@example.com"]\n', AnswersIssue.UNEXPECTED_VALUE_KIND),
        ('questions:\n  - q: "Notice"\n    a: "ok"\n    note: [1]\n', AnswersIssue.UNEXPECTED_VALUE_KIND),
    ],
)
def test_malformed_input_raises_a_typed_refusal(
    tmp_path: Path, text: str, issue: AnswersIssue
) -> None:
    write_answers(tmp_path, text)

    with pytest.raises(AnswersError) as excinfo:
        load_answers(config_dir=tmp_path, conn=None)

    assert excinfo.value.violation.issue is issue


def test_a_refusal_names_where_it_happened(tmp_path: Path) -> None:
    write_answers(tmp_path, 'identity:\n  nickname: "Ada"\n')

    with pytest.raises(AnswersError) as excinfo:
        load_answers(config_dir=tmp_path, conn=None)

    assert excinfo.value.violation.where == "identity.nickname"


def test_a_dropped_question_would_be_indistinguishable_from_a_complete_panel(
    tmp_path: Path,
) -> None:
    """The second entry is malformed. An implementation that skipped it would return a panel
    holding one good question and no signal that a second one was lost."""
    write_answers(
        tmp_path,
        """
questions:
  - q: "Notice period"
    a: "Two weeks"
  - q: "Salary expectation"
""",
    )

    with pytest.raises(AnswersError):
        load_answers(config_dir=tmp_path, conn=None)


# ---------------------------------------------------------------------------------------
# 8. nothing here logs or prints a field value


def test_loading_logs_nothing_and_prints_no_field_value(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "Ada-Lovelace-0100-secret"
    write_answers(
        tmp_path,
        f"""
identity:
  full_name: "{secret}"
work_auth:
  status: "{secret}"
questions:
  - q: "{secret}"
    a: "{secret}"
    note: "{secret}"
""",
    )
    write_resume(tmp_path)

    with caplog.at_level(logging.DEBUG):
        panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.identity["full_name"] == secret
    captured = capsys.readouterr()
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    # Field NAMES are the only thing this module may emit, so a names-only diagnostic added
    # later stays green here; a line carrying a value does not. Verified by mutation: adding
    # `log.info("identity=%s", identity)` fails this test, `log.info("unresolved=%s", missing)`
    # does not.
    assert not [record for record in caplog.records if secret in record.getMessage()]


# ---------------------------------------------------------------------------------------
# 9. the shipped example holds placeholders only, and still parses


def test_the_shipped_example_parses_and_resolves_every_identity_field(tmp_path: Path) -> None:
    write_answers(tmp_path, example_answers_text())

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert sorted(panel.identity) == sorted(IDENTITY_FIELDS)
    assert not [name for name in panel.missing if name.startswith("identity.")]
    assert panel.questions
    assert any(question.note for question in panel.questions)


def test_the_shipped_example_ships_no_work_authorisation_answer(tmp_path: Path) -> None:
    """A copyable work-authorisation placeholder is the one field a first-run user must not
    inherit from a template: the example demonstrates the shape in comments instead."""
    write_answers(tmp_path, example_answers_text())

    panel = load_answers(config_dir=tmp_path, conn=None)

    assert panel.work_auth == {}
    assert [name for name in panel.missing if name.startswith("work_auth.")] == [
        f"work_auth.{name}" for name in WORK_AUTH_FIELDS
    ]


def test_the_shipped_example_passes_the_generalization_shape_rules() -> None:
    """R1 to R4 of `tools/generalization`, evaluated directly against the example's bytes.

    The gate only scans TRACKED files, so this asserts the same regexes here rather than
    trusting an eyeball. A real name, phone, LinkedIn slug or home path in the example would
    fail here before it could reach a public repository.
    """
    from tools.generalization.shape import (
        EMAIL_RE,
        HOME_PATH_RE,
        PHONE_RE,
        PROFILE_URL_RE,
        RESERVED_EMAIL_RE,
    )

    text = example_answers_text()

    assert HOME_PATH_RE.findall(text) == []
    assert PHONE_RE.findall(text) == []
    assert PROFILE_URL_RE.findall(text) == []
    emails = EMAIL_RE.findall(text)
    assert emails, "the example is expected to demonstrate an email placeholder"
    assert [hit for hit in emails if not RESERVED_EMAIL_RE.search(hit)] == []


# ---------------------------------------------------------------------------------------
# 10. the owner's real config directory is never consulted


def paths_touched(monkeypatch: pytest.MonkeyPatch, config_dir: Path) -> list[str]:
    """Every path `load_answers` probes or reads, in order."""
    seen: list[str] = []
    real_read_text = Path.read_text
    real_is_file = Path.is_file

    def read_spy(self: Path, *args: object, **kwargs: object) -> str:
        seen.append(str(self))
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    def is_file_spy(self: Path) -> bool:
        seen.append(str(self))
        return real_is_file(self)

    monkeypatch.setattr(Path, "read_text", read_spy)
    monkeypatch.setattr(Path, "is_file", is_file_spy)
    load_answers(config_dir=config_dir, conn=None)
    monkeypatch.undo()
    return seen


def test_nothing_is_read_from_outside_the_given_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`config_dir` is the only root. An implementation that fell back to platformdirs would
    read the owner's real answers on a machine that has them."""
    write_answers(tmp_path, 'identity:\n  full_name: "Ada Lovelace"\n')
    write_resume(tmp_path)

    seen = paths_touched(monkeypatch, tmp_path)

    assert seen
    assert all(path.startswith(str(tmp_path)) for path in seen), seen


def test_an_empty_config_dir_consults_no_other_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case a fallback would actually fire in: nothing is on disk under `config_dir`, so a
    platformdirs second chance would reach the owner's real answers. Nothing outside the given
    root may be probed, not even to test for existence."""
    empty = tmp_path / "empty"
    empty.mkdir()

    seen = paths_touched(monkeypatch, empty)

    assert seen
    assert all(path.startswith(str(empty)) for path in seen), seen


def test_the_panel_loads_over_a_read_only_connection(tmp_path: Path) -> None:
    """The web app hands this a read-only connection (design §7), so any write on this path —
    an `ensure_run`, a backfill, a cached-value UPDATE — would raise there rather than here."""
    writer = store(tmp_path)
    seed_profile(writer, Facts(work_authorization=WorkAuthFact(status="citizen")))

    with get_readonly_engine(tmp_path / "store").connect() as conn:
        panel = load_answers(config_dir=tmp_path, conn=conn)

    assert panel.work_auth == {"status": "citizen"}
    writer.dispose()
