"""The form-question bank (T312): the questions employers ask most, and whether an answer stands.

Reads the cached Greenhouse application forms (`posting_form_questions`, one row per posting
VERSION) and counts, for each question, the open postings whose CURRENT form asks it. A posting
counts once per question however often its form repeats it. Only postings that are open, whose
form belongs to the posting's newest version, and whose current verdict is `eligible` are counted.
`uncertain` (the abstain verdict) is counted apart as a number of forms and never enters a
question's count, and neither does `ineligible` or a posting with no current evaluation: the
keystone keeps the three apart.

**Whether an answer exists comes from the owner's `answers.yaml`, and only the question text
crosses into this module.** The caller passes the questions the owner has answered, never their
answers or notes, so the payload cannot carry answer text: there is none here to carry. A question
is answered when its normalised text equals a normalised answered question. The normalisation is
`normalise_question` (whitespace collapsed, case folded) and nothing fuzzier: a near-match is
reported unanswered, which is the safe direction (the owner is asked to answer it once more, not
told it is done).

Greenhouse prints six built-in fields on every form (`STANDARD_FIELDS`). They are asked of every
applicant and answered by the identity block, so counting them would put six rows at the top that
never differ; they are left out of the bank and named in the payload.

Read-only. Reads narrow columns only: `postings` rows carry the body text, so postings are read
by primary key for `status` alone and only for the ids that have a cached form.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection
from typing import Any

from sqlalchemy import Connection, func, select

from boardwatch.eligibility.read import current_verdicts
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import posting_form_questions, posting_versions, postings

#: How many questions the bank returns.
TOP_QUESTIONS = 30

#: Greenhouse's built-in fields, in normalised form. Closed: a question outside it is a question.
STANDARD_FIELDS: tuple[str, ...] = (
    "first name",
    "last name",
    "email",
    "phone",
    "resume/cv",
    "cover letter",
)


def normalise_question(text: str) -> str:
    """The grouping key: whitespace collapsed, case folded. Deliberately nothing more."""
    return " ".join(text.split()).casefold()


def _spelling(seen: Counter[str]) -> str:
    """The most common spelling of a question, ties to the smallest text, so the label is stable."""
    return min(seen, key=lambda text: (-seen[text], text))


def form_question_bank(
    conn: Connection,
    *,
    identity: tuple[str, str] | None,
    answered: Collection[str] | None,
) -> dict[str, Any]:
    """The bank. `identity` is the live (profile_hash, rules_hash), or None with no profile (every
    form is then unevaluated). `answered` is the owner's answered QUESTION texts, or None when the
    answers file could not be read, in which case no row claims either state."""
    forms = {
        int(row.posting_version_id): list(row.questions_json)
        for row in conn.execute(
            select(
                posting_form_questions.c.posting_version_id,
                posting_form_questions.c.questions_json,
            )
        ).all()
    }
    version_ids = sorted(forms)

    posting_of: dict[int, int] = {}
    for chunk in id_chunks(version_ids):
        posting_of.update(
            {
                int(r.id): int(r.posting_id)
                for r in conn.execute(
                    select(posting_versions.c.id, posting_versions.c.posting_id).where(
                        posting_versions.c.id.in_(chunk)
                    )
                ).all()
            }
        )
    posting_ids = sorted(set(posting_of.values()))

    # The newest version of each posting, picked in Python on `julianday`: `captured_at` mixes
    # naive-UTC and offset-carrying text, which SQL would order as text and SQLAlchemy's DateTime
    # would read back with the offset dropped. `julianday` reads both as UTC.
    newest: dict[int, tuple[float, int]] = {}
    for chunk in id_chunks(posting_ids):
        for r in conn.execute(
            select(
                posting_versions.c.id,
                posting_versions.c.posting_id,
                func.julianday(posting_versions.c.captured_at).label("captured"),
            ).where(posting_versions.c.posting_id.in_(chunk))
        ).all():
            stamp = (float(r.captured), int(r.id))
            if int(r.posting_id) not in newest or stamp > newest[int(r.posting_id)]:
                newest[int(r.posting_id)] = stamp
    status: dict[int, str] = {}
    for chunk in id_chunks(posting_ids):
        status.update(
            {
                int(r.id): str(r.status)
                for r in conn.execute(
                    select(postings.c.id, postings.c.status).where(postings.c.id.in_(chunk))
                ).all()
            }
        )

    scope = {
        "stored": len(forms),
        "eligible": 0,
        "abstain": 0,
        "ineligible": 0,
        "unevaluated": 0,
        "closed": 0,
        "superseded": 0,
        # A cached `questions: null` (the board has no application form) is stored as `[]`: not
        # a form, so it is in no count below.
        "no_questions": 0,
    }
    live: list[int] = []  # open postings whose form is their newest version's
    for vid in version_ids:
        pid = posting_of.get(vid)
        if not forms[vid]:
            scope["no_questions"] += 1
        elif pid is None or newest[pid][1] != vid:
            scope["superseded"] += 1
        elif status.get(pid) != "open":
            scope["closed"] += 1
        else:
            live.append(vid)
    verdicts = (
        current_verdicts(conn, live, *identity) if identity is not None and live else {}
    )

    asked: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for vid in live:
        verdict = verdicts.get(posting_of[vid])
        if verdict == "eligible":
            scope["eligible"] += 1
        elif verdict == "uncertain":
            scope["abstain"] += 1
            continue
        elif verdict == "ineligible":
            scope["ineligible"] += 1
            continue
        else:
            scope["unevaluated"] += 1
            continue
        keys: set[str] = set()
        for entry in forms[vid]:
            label = " ".join(str(entry["label"]).split())
            key = label.casefold()
            if label and key not in STANDARD_FIELDS:
                keys.add(key)
                spellings[key][label] += 1
        asked.update(keys)

    done = None if answered is None else {normalise_question(q) for q in answered}
    # Unanswered first, then most common, then text for a stable order. With the answers file
    # unreadable nothing is either, so the order is by count alone.
    ranked = sorted(
        asked.items(),
        key=lambda item: (done is not None and item[0] in done, -item[1], item[0]),
    )
    rows = [
        {
            "question": _spelling(spellings[key]),
            "count": count,
            "answered": None if done is None else key in done,
        }
        for key, count in ranked[:TOP_QUESTIONS]
    ]
    return {
        "forms": scope,
        "answers_readable": done is not None,
        "distinct": len(asked),
        "unanswered": None if done is None else sum(1 for k in asked if k not in done),
        "standard_fields": list(STANDARD_FIELDS),
        "questions": rows,
    }
