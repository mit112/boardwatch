"""Read/write posting identities at the current algorithm version (design §1.2, §2.2)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, distinct, func, insert, select, update
from sqlalchemy.engine import Connection

from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.core.posting_identity import IdentityInputs, PostingIdentity
from boardwatch.store.tables import companies, posting_identities, postings


def load_identity_inputs(
    conn: Connection, posting_ids: Sequence[int] | None = None, *, open_only: bool = True
) -> tuple[IdentityInputs, ...]:
    """Identity inputs for every open posting, or just the named ones.

    `posting_ids=None` means "all of them" and is what `backfill`, `verify` and the funnel
    want. The ranker passes an explicit list because it only deduplicates the postings that
    survived every earlier filter, and `body_text` is the largest column in the schema —
    there is no reason to pull 23,455 bodies to deduplicate a few thousand leads.
    An empty list means an empty result, not "all".
    """
    if posting_ids is not None and not posting_ids:
        return ()
    stmt = select(
        postings.c.id,
        postings.c.company_id,
        companies.c.name,
        postings.c.provider_posting_id,
        postings.c.title,
        postings.c.locations_json,
        postings.c.content_hash,
        postings.c.body_text,
        postings.c.url,
        postings.c.first_seen_at,
    ).join(companies, postings.c.company_id == companies.c.id)
    if open_only:
        stmt = stmt.where(postings.c.status == "open")
    if posting_ids is not None:
        stmt = stmt.where(postings.c.id.in_(list(posting_ids)))
    return tuple(
        IdentityInputs(
            posting_id=int(r[0]),
            company_id=int(r[1]),
            company_name=str(r[2]),
            provider_posting_id=str(r[3]),
            title=str(r[4] or ""),
            # `locations_json` is a JSON column, so this is already a deserialized list.
            # Anything else a provider managed to store (a dict, a bare string) is not
            # location evidence, and coercing it here keeps that judgement in one place —
            # `normalized_locations` then has no parsing to get wrong.
            #
            # Non-string ELEMENTS are dropped rather than stringified. `str(x)` turned a
            # JSON `[null]` into `["None"]`, which normalizes to `["none"]` — a truthy
            # location component invented out of an explicit absence, so two postings with
            # `[null]` could suppress on "evidence" neither one has. Dropping them leaves an
            # empty list, which `normalized_locations` correctly reads as no evidence.
            locations=[x for x in r[5] if isinstance(x, str)] if isinstance(r[5], list) else None,
            content_hash=str(r[6]),  # NOT NULL in the schema; str() is for mypy, not safety
            body_text=str(r[7]),  # ditto
            url=None if r[8] is None else str(r[8]),
            first_seen_at=r[9],
        )
        for r in conn.execute(stmt).all()
    )


def load_identities(
    conn: Connection, posting_ids: Sequence[int] | None = None
) -> dict[int, tuple[PostingIdentity, ...]]:
    """Current-version identities for the named postings, or for all of them.

    `posting_ids=None` means "all" and issues NO `IN` list, mirroring
    `load_identity_inputs`. That is not symmetry for its own sake: SQLite caps bound
    parameters at `SQLITE_LIMIT_VARIABLE_NUMBER` — measured 32766 on the bundled 3.45.1
    (23,455 parameters succeed, 32,767 raises `OperationalError`), and only 999 before
    SQLite 3.32. Both the funnel's `unique` sweep and `identities verify` pass every open
    posting id, and the corpus is already 23,455, so an `IN` list made the *verification*
    path a scheduled failure as the program adds breadth. Returning identities for closed
    postings too is harmless: every caller looks rows up by id from its own row set.

    An empty list still means an empty result, not "all".
    """
    if posting_ids is not None and not posting_ids:
        return {}
    stmt = select(
        posting_identities.c.posting_id,
        posting_identities.c.kind,
        posting_identities.c.identity_key,
    ).where(posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION)
    if posting_ids is not None:
        stmt = stmt.where(posting_identities.c.posting_id.in_(list(posting_ids)))
    rows = conn.execute(stmt).all()
    out: dict[int, list[PostingIdentity]] = {}
    for posting_id, kind, key in rows:
        out.setdefault(int(posting_id), []).append(PostingIdentity(str(kind), str(key)))
    return {pid: tuple(items) for pid, items in out.items()}


def write_identities(
    conn: Connection,
    posting_id: int,
    identities: Sequence[PostingIdentity],
    *,
    now: datetime,
) -> int:
    """Make one posting's current-version rows match `identities` exactly.

    Returns rows inserted + updated + deleted. Idempotent: unchanged inputs return 0.

    Rows are rewritten rather than left alone because `scan/apply.py` refreshes title and
    locations on every observation while gating a *revision* on content_hash alone — so a
    retitle with an unchanged body moves an identity key without producing a revision.
    Leaving the superseded row would make `identities verify` permanently red on a
    legitimate update, and a permanently-red check is a discarded check (design §2.3).

    Deletion is part of the same contract: losing location evidence drops three kinds
    (§2.1), and an orphaned `exact_quad` row would keep suppressing on behalf of a posting
    that no longer earns one.

    Rows at other `algorithm_version`s are never read, updated, or deleted here — the
    UNIQUE key includes the version, so an algorithm change writes beside history.
    """
    existing = {
        i.kind: i.identity_key for i in load_identities(conn, [posting_id]).get(posting_id, ())
    }
    wanted = {i.kind: i.identity_key for i in identities}

    inserts = [
        {
            "posting_id": posting_id,
            "kind": kind,
            "identity_key": key,
            "algorithm_version": IDENTITY_ALGORITHM_VERSION,
            "created_at": now,
        }
        for kind, key in wanted.items()
        if kind not in existing
    ]
    changed = [(k, v) for k, v in wanted.items() if k in existing and existing[k] != v]
    dropped = [k for k in existing if k not in wanted]

    if inserts:
        conn.execute(insert(posting_identities), inserts)
    for kind, key in changed:
        conn.execute(
            update(posting_identities)
            .where(
                posting_identities.c.posting_id == posting_id,
                posting_identities.c.kind == kind,
                posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION,
            )
            .values(identity_key=key, created_at=now)
        )
    if dropped:
        conn.execute(
            delete(posting_identities).where(
                posting_identities.c.posting_id == posting_id,
                posting_identities.c.kind.in_(dropped),
                posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION,
            )
        )
    return len(inserts) + len(changed) + len(dropped)


def identities_complete(conn: Connection) -> bool:
    """True when every open posting carries a current-version identity.

    The gate for `unique` and for suppression itself. Never `if identities:` — a single
    backfilled posting in a 23,455-posting corpus is indistinguishable from a complete one
    under a truthiness check, and the number that falls out is not a measurement of
    anything (design §2.2).

    An empty corpus returns True: zero of zero really is complete, and the `unique` it
    yields — 0 — is a measured zero, not a structural one.
    """
    open_count = conn.execute(
        select(func.count()).select_from(postings).where(postings.c.status == "open")
    ).scalar_one()
    covered = conn.execute(
        select(func.count(distinct(posting_identities.c.posting_id)))
        .select_from(
            posting_identities.join(postings, posting_identities.c.posting_id == postings.c.id)
        )
        .where(
            postings.c.status == "open",
            posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION,
        )
    ).scalar_one()
    return int(open_count) == int(covered)
