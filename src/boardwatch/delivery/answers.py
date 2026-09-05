"""`{config_dir}/answers.yaml` — the read-and-copy answers panel (design §9).

The owner refills the same dozen fields into every employer's application form. This module
assembles them once, from the places they already live, so the web app can render a panel whose
values are copied to the clipboard by a human.

**It is not auto-fill.** Nothing here types into an employer's page: auto-apply, auto-fill and
browser automation are out of scope repo-wide, and copy-to-clipboard keeps the owner as the actor.

Three fields, three sources, and the split is the point:

* `identity` comes from `answers.yaml`. It is the only section with no other structured home —
  the résumé header is free text ("Ada Lovelace" / "ada@example.com · example.com/ada"), and
  splitting those lines into seven named fields would be guesswork.
* `work_auth` prefers the profile's stored eligibility facts and falls back to `answers.yaml`.
  A field neither source answers is reported in `missing` and **never defaulted**: a wrong
  work-authorisation answer on a real application is worse than a blank one, and the facts model
  exists precisely because a bare boolean answers the question backwards for an EAD holder
  (`eligibility/facts.py`).
* `education` is read from `{config_dir}/resume.yaml` through the projection's own
  header/education reader. It is never retyped here — a second copy that could disagree with the
  document being sent is the failure this avoids, so an `education:` key in `answers.yaml` is
  refused rather than ignored.

So in practice the file only ever holds `identity` and `questions`.

**`note` is a separate field so it cannot reach the clipboard.** The equivalent file in the prior
art carries a twenty-line "do not reuse as-is, two of these claims are contradicted by the source
repo" warning on its most important answer. Pasting that into an employer's form would be
catastrophic, and there has to be somewhere to put it. `Question.note` is shown in the panel and
is never part of `Question.a`.

**A missing `answers.yaml` is not an error.** This tool ships to other people; a first-run user has
no such file and must still get a working page, with every unresolved field named in `missing`.
Everything else malformed is a typed refusal: an implementation that skipped a bad `questions`
entry would return a panel that is quietly one answer short, which on screen is indistinguishable
from a complete one.

**Nothing in this module logs or prints.** A log line here would put an address, a phone number or
a salary expectation into a file the owner does not think of as sensitive. If that ever changes,
field NAMES are the only thing that may be emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import NoReturn

import yaml
from sqlalchemy import Connection

from boardwatch.eligibility.facts import parse_facts
from boardwatch.projection.errors import ProjectionError
from boardwatch.projection.shell import load_shell
from boardwatch.store.queries import get_profile

#: The owner's copy, never committed.
ANSWERS_FILENAME = "answers.yaml"
#: The placeholder-only copy that ships with the package.
EXAMPLE_FILENAME = "answers.example.yaml"
#: The authored résumé, resolved exactly as every other caller resolves it
#: (`cli/tailor_cmd.py:56`, `cli/run_cmd.py:169`): `{config_dir}/resume.yaml`.
RESUME_FILENAME = "resume.yaml"

#: Closed catalog, from design §9. An out-of-catalog key is refused, never a new bucket.
IDENTITY_FIELDS: tuple[str, ...] = (
    "full_name",
    "email",
    "phone",
    "city_state",
    "linkedin",
    "github",
    "portfolio",
)

#: One name per stored work-authorisation fact (`eligibility.facts.WorkAuthFact`), so the panel
#: restates the profile rather than deriving anything from it. "Are you authorised to work in
#: the US?" is deliberately NOT a field here: that answer is an inference over status and
#: jurisdiction, and inferring it is what `WorkAuthFact` was built to stop.
WORK_AUTH_FIELDS: tuple[str, ...] = ("status", "jurisdiction", "needs_sponsorship")

#: Closed catalog over the eligibility catalog's declared `work_auth.status` choices
#: (`eligibility/rules.yaml`), mapping each to the words an employer's form expects. The panel
#: exists to be COPIED, and `ead_or_similar` pasted into "what is your work authorization status?"
#: is a token from this program's vocabulary, not an answer a human wrote.
#:
#: Deliberately generic: `status` is jurisdiction-RELATIVE and `jurisdiction` is its own field, so
#: nothing here names a country. A value the catalog does not declare is a failure, never a new
#: bucket — `_status_words` refuses it rather than letting it reach the clipboard. Coverage of the
#: catalog is asserted in `tests/unit/test_web_server.py`, against the catalog rather than a
#: retyped list, so a sixth member cannot ship without words.
WORK_AUTH_STATUS_WORDS: dict[str, str] = {
    "citizen": "Citizen",
    "ead_or_similar": "EAD or similar (work authorization document)",
    "needs_sponsorship": "Requires visa sponsorship",
    "permanent_resident": "Permanent resident",
    "prefer_not_to_say": "Prefer not to say",
}

#: `missing` names `education` as a whole, not per line: the résumé is the unit that is present
#: or absent.
EDUCATION_FIELD = "education"

_SECTIONS: dict[str, tuple[str, ...]] = {
    "identity": IDENTITY_FIELDS,
    "work_auth": WORK_AUTH_FIELDS,
}
_QUESTION_FIELDS = frozenset({"q", "a", "note"})
_TOP_LEVEL_FIELDS = frozenset({*_SECTIONS, "questions"})

# Both halves are required. An entry carrying one of them would render as half a row, and
# guessing the other half is exactly what this module must never do.
_MISSING_Q = "is missing 'q', the question text"
_MISSING_A = "is missing 'a', the answer. A question with no answer is not an answer"


class AnswersIssue(StrEnum):
    """Everything the answers panel can refuse for. Closed — a condition not named here is a
    defect in this file, never a new bucket. A missing file is deliberately absent: it is the
    first-run state, not a refusal."""

    UNREADABLE = "unreadable"
    MALFORMED_YAML = "malformed_yaml"
    NOT_A_MAPPING = "not_a_mapping"
    SECTION_NOT_A_MAPPING = "section_not_a_mapping"
    QUESTIONS_NOT_A_SEQUENCE = "questions_not_a_sequence"
    QUESTION_NOT_A_MAPPING = "question_not_a_mapping"
    QUESTION_MISSING_FIELD = "question_missing_field"
    #: A key outside the closed catalog. Refused rather than dropped: a silently ignored
    #: `education:` or a mistyped `phonr:` is an answer the owner believes is on the panel.
    UNKNOWN_FIELD = "unknown_field"
    #: A list or mapping where one copyable string belongs. Refused rather than stringified —
    #: `"['a@example.com']"` on an employer's form is worse than a blank.
    UNEXPECTED_VALUE_KIND = "unexpected_value_kind"
    #: A stored `work_auth.status` the eligibility catalog does not declare. Refused rather than
    #: copied through: the raw token is what this panel's words mapping exists to keep off an
    #: employer's form, and a blank would hide a corrupt profile row behind an empty field.
    UNKNOWN_WORK_AUTH_STATUS = "unknown_work_auth_status"


@dataclass(frozen=True)
class AnswersViolation:
    """One refusal. `where` is the dotted field path, or the filename for a whole-file fault.

    Deliberately carries no VALUE — this type crosses into an HTTP response and a terminal.
    """

    issue: AnswersIssue
    message: str
    where: str


class AnswersError(Exception):
    """A typed refusal, following `ProjectionError`: the reason is an enum member on the
    exception, never prose a caller string-matches."""

    def __init__(self, violation: AnswersViolation) -> None:
        super().__init__(f"{violation.issue}: {violation.message} ({violation.where})")
        self.violation = violation


@dataclass(frozen=True)
class Question:
    """One recurring application question.

    `note` is separate from `a` so it cannot reach the clipboard. It is shown in the panel.
    """

    q: str
    a: str
    note: str | None = None


@dataclass(frozen=True)
class AnswersPanel:
    """Everything the panel renders, plus what it could not resolve.

    `missing` is not decoration. A field that resolved to nothing and a field nobody asked for
    look identical in a dict, and an empty value on screen reads as an answer — so the names of
    the unresolved fields are carried explicitly, in catalog order.
    """

    identity: dict[str, str] = field(default_factory=dict)
    work_auth: dict[str, str] = field(default_factory=dict)
    education: list[str] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def example_answers_text() -> str:
    """The packaged `answers.example.yaml`, read the way every other shipped data file is read
    (`eligibility/catalog.py:181`) — a `__file__`-relative path is not reachable in every
    installed layout."""
    return (files("boardwatch.delivery") / EXAMPLE_FILENAME).read_text(encoding="utf-8")


def load_answers(*, config_dir: Path, conn: Connection | None) -> AnswersPanel:
    """Assemble the panel. `conn=None` degrades to file-only, raising nothing.

    `config_dir` is the only root consulted; nothing here resolves a default config directory of
    its own, so a caller cannot accidentally read the owner's real answers.
    """
    raw = _read(config_dir / ANSWERS_FILENAME)
    identity = _section(raw.get("identity"), "identity")
    work_auth = {**_section(raw.get("work_auth"), "work_auth"), **_profile_work_auth(conn)}
    questions = _questions(raw.get("questions"))
    education = _education(config_dir)

    missing = [f"identity.{name}" for name in IDENTITY_FIELDS if name not in identity]
    missing += [f"work_auth.{name}" for name in WORK_AUTH_FIELDS if name not in work_auth]
    if not education:
        missing.append(EDUCATION_FIELD)

    return AnswersPanel(
        identity=identity,
        work_auth=work_auth,
        education=education,
        questions=questions,
        missing=missing,
    )


def _refuse(issue: AnswersIssue, message: str, *, where: str) -> NoReturn:
    """The one construction site, so a caller cannot invent an untyped refusal."""
    raise AnswersError(AnswersViolation(issue=issue, message=message, where=where))


def _read(path: Path) -> dict[object, object]:
    """The parsed top level of `answers.yaml`, or `{}` when there is no such file.

    An absent file is the first-run state and returns empty. A file that exists and cannot be
    read is a refusal — silently treating an unreadable file as absent would present a first-run
    page to an owner whose answers are right there on disk.
    """
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _refuse(AnswersIssue.UNREADABLE, f"cannot be read: {exc}", where=path.name)
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _refuse(AnswersIssue.MALFORMED_YAML, f"is not valid YAML: {exc}", where=path.name)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        _refuse(
            AnswersIssue.NOT_A_MAPPING,
            f"must be a mapping of {sorted(_TOP_LEVEL_FIELDS)}, not a {type(parsed).__name__}",
            where=path.name,
        )
    top: dict[object, object] = parsed
    for key in top:
        if key not in _TOP_LEVEL_FIELDS:
            _refuse(
                AnswersIssue.UNKNOWN_FIELD,
                f"unknown top-level key {key!r}; expected one of {sorted(_TOP_LEVEL_FIELDS)}. "
                "Education is read from resume.yaml and is not declared here",
                where=f"{path.name}.{key}",
            )
    return top


def _scalar(value: object, *, where: str) -> str | None:
    """One copyable string, or `None` for "not answered".

    A blank string is an absence, not a value: an empty column reads as an answer (design §6.4),
    and a whitespace-only cell on an employer's form is worse than a named gap. `bool` is checked
    before `int` because `True` is an `int` in Python and "1" is not an answer to "do you need
    sponsorship".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    _refuse(
        AnswersIssue.UNEXPECTED_VALUE_KIND,
        f"must be a single value, not a {type(value).__name__}",
        where=where,
    )


def _section(raw: object, name: str) -> dict[str, str]:
    """One closed-catalog section of the file. Absent, empty and all-blank are the same thing."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _refuse(
            AnswersIssue.SECTION_NOT_A_MAPPING,
            f"must be a mapping of {sorted(_SECTIONS[name])}, not a {type(raw).__name__}",
            where=name,
        )
    resolved: dict[str, str] = {}
    for key, value in raw.items():
        if key not in _SECTIONS[name]:
            _refuse(
                AnswersIssue.UNKNOWN_FIELD,
                f"unknown field {key!r}; expected one of {sorted(_SECTIONS[name])}",
                where=f"{name}.{key}",
            )
        answer = _scalar(value, where=f"{name}.{key}")
        if answer is not None:
            resolved[str(key)] = answer
    return resolved


def _questions(raw: object) -> list[Question]:
    """The `questions` list. A malformed entry refuses the whole file rather than shrinking it."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        _refuse(
            AnswersIssue.QUESTIONS_NOT_A_SEQUENCE,
            f"must be a list of {{q, a, note}} mappings, not a {type(raw).__name__}",
            where="questions",
        )
    entries: list[Question] = []
    for index, item in enumerate(raw):
        where = f"questions[{index}]"
        if not isinstance(item, dict):
            _refuse(
                AnswersIssue.QUESTION_NOT_A_MAPPING,
                f"must be a mapping of {{q, a, note}}, not a {type(item).__name__}",
                where=where,
            )
        for key in item:
            if key not in _QUESTION_FIELDS:
                _refuse(
                    AnswersIssue.UNKNOWN_FIELD,
                    f"unknown field {key!r}; expected one of {sorted(_QUESTION_FIELDS)}",
                    where=f"{where}.{key}",
                )
        question = _scalar(item.get("q"), where=f"{where}.q")
        if question is None:
            _refuse(AnswersIssue.QUESTION_MISSING_FIELD, _MISSING_Q, where=f"{where}.q")
        answer = _scalar(item.get("a"), where=f"{where}.a")
        if answer is None:
            _refuse(AnswersIssue.QUESTION_MISSING_FIELD, _MISSING_A, where=f"{where}.a")
        entries.append(
            Question(q=question, a=answer, note=_scalar(item.get("note"), where=f"{where}.note"))
        )
    return entries


def _profile_work_auth(conn: Connection | None) -> dict[str, str]:
    """The stored eligibility facts, restated. Empty when there is no connection, no profile row,
    no facts, or no work-authorisation fact — each of which means "the file decides".

    Nothing is derived: every key here is one stored fact under its own name.
    """
    if conn is None:
        return {}
    row = get_profile(conn)
    if row is None:
        return {}
    fact = parse_facts(row.eligibility_facts_json).work_authorization
    if fact is None:
        return {}
    resolved: dict[str, str] = {}
    for name, value in (
        ("status", fact.status),
        ("jurisdiction", fact.jurisdiction),
        ("needs_sponsorship", fact.needs_sponsorship),
    ):
        answer = _scalar(value, where=f"profile.work_authorization.{name}")
        if answer is None:
            continue
        # `needs_sponsorship` is already "yes"/"no" out of `_scalar`; only `status` is a catalog
        # token, and only it is restated.
        resolved[name] = _status_words(answer) if name == "status" else answer
    return resolved


def _status_words(status: str) -> str:
    """One declared `work_auth.status` in the words a form expects. Closed over the catalog."""
    words = WORK_AUTH_STATUS_WORDS.get(status)
    if words is None:
        _refuse(
            AnswersIssue.UNKNOWN_WORK_AUTH_STATUS,
            "is not a work-authorisation status this catalog declares",
            where="profile.work_authorization.status",
        )
    return words


def _education(config_dir: Path) -> list[str]:
    """`education` from the authored résumé, through the projection's own reader.

    `load_shell` is the route rather than `load_resume`, because it is the existing function for
    "header and education out of an authored résumé" and it does not additionally require
    `skill_groups` and `entries`. Its refusal is swallowed on purpose: a missing, malformed or
    education-less résumé leaves the panel usable with `education` named in `missing`, which is
    what the API's tolerate-and-say-so rule asks for (design §6.2).
    """
    try:
        _header, education = load_shell(config_dir / RESUME_FILENAME)
    except ProjectionError:
        return []
    return [line.strip() for line in education if line.strip()]
