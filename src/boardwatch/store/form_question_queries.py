"""The cached Greenhouse application forms (`posting_form_questions`).

Its own module rather than a pair of functions in `store/delivery_queries.py`, for one reason
that file states in its first line: **that module never writes.** No INSERT, UPDATE or DELETE and
no call that performs one — a web request must not mutate the store on a page load. The read half
belongs beside the write half, so both live here and `delivery_queries` imports the read.

What is stored is the FETCHED form, keyed on `posting_version_id`, never the match. The catalog in
`delivery/form_questions` is applied fresh on every read, so it can gain a surface and take effect
on the next reconcile without re-asking a single board.
"""

from __future__ import annotations

from sqlalchemy import Connection, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import posting_form_questions


def record_form_questions(
    conn: Connection, posting_version_id: int, questions_json: list[dict[str, object]]
) -> None:
    """Store one posting version's form, replacing any row already there.

    Upsert rather than plain insert, and not because a re-ask is expected: a version's form is
    asked about once, so the conflict arm is only reachable when a sweep is re-run over a row a
    previous one already stored (a crash between the write and the commit, or a hand re-run). The
    later answer is the better one, and raising on the conflict would make the recovery path fail
    on work that had already succeeded.
    """
    stmt = sqlite_insert(posting_form_questions).values(
        posting_version_id=posting_version_id,
        questions_json=questions_json,
        fetched_at=utcnow(),
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["posting_version_id"],
            set_={
                "questions_json": stmt.excluded.questions_json,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
    )


def cached_form_questions(
    conn: Connection, posting_version_ids: list[int]
) -> dict[int, list[dict[str, object]]]:
    """`posting_version_id` -> the stored form, for every version that has one.

    A version ABSENT from the result is "no questions known" — never asked, or asked and not
    answered — and a version present with an EMPTY list is "this board publishes no form". The two
    are different facts and the caller must not fold them: only the second means the form has been
    read, and only the first is worth another GET.

    Chunked through `id_chunks` like every other id list in this store, and keyed on the very
    column it chunks on, so `dict.update` is the exact merge.
    """
    stored: dict[int, list[dict[str, object]]] = {}
    for chunk in id_chunks(posting_version_ids):
        stored.update(
            {
                int(row.posting_version_id): list(row.questions_json)
                for row in conn.execute(
                    select(
                        posting_form_questions.c.posting_version_id,
                        posting_form_questions.c.questions_json,
                    ).where(posting_form_questions.c.posting_version_id.in_(chunk))
                ).all()
            }
        )
    return stored
