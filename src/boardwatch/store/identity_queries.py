"""Read/write posting identities at the current algorithm version (design §1.2, §2.2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, distinct, func, insert, select, update
from sqlalchemy.engine import Connection, Row

from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION, kind_spec
from boardwatch.core.near_duplicate import PostingEvidence
from boardwatch.core.posting_identity import IdentityInputs, PostingIdentity
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import companies, job_dispositions, posting_identities, postings


def load_identity_inputs(
    conn: Connection, posting_ids: Sequence[int] | None = None, *, open_only: bool = True
) -> tuple[IdentityInputs, ...]:
    """Identity inputs for every open posting, or just the named ones.

    `posting_ids=None` means "all of them" and is what `backfill`, `verify` and the funnel
    want. The ranker passes an explicit list because it only deduplicates the postings that
    survived every earlier filter, and `body_text` is the largest column in the schema —
    there is no reason to pull 32,771 bodies to deduplicate a few thousand leads.
    An empty list means an empty result, not "all".

    The explicit-list branch CHUNKS (D-288). `top_cmd`'s dedup block passes `eligible_ids`,
    which is ~3,683 on the scheduled path but **30,419** with the audit/drain flags open
    (`--include-hard-filter` and friends) — inside the same cap that took the daily driver
    down on 2026-08-23, with about two days of corpus growth to spare. Chunks CONCATENATE
    here — the result is a flat tuple with nothing to key on — so the id list is DEDUPED
    first, because `IN` collapses a repeated id and chunk-then-concatenate would not.
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
    if posting_ids is None:
        rows = list(conn.execute(stmt).all())
    else:
        # `dict.fromkeys` DEDUPES while preserving order, and that is load-bearing rather than
        # tidiness: `IN (7, 7)` returns posting 7 once, but two 7s in DIFFERENT chunks return
        # it once per chunk, and a concatenating merge keeps both. The four `dict.update`
        # sites are duplicate-safe by construction; this one and `load_identities` are not.
        rows = []
        for chunk in id_chunks(list(dict.fromkeys(posting_ids))):
            rows.extend(conn.execute(stmt.where(postings.c.id.in_(chunk))).all())
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
        for r in rows
    )


def load_identities(
    conn: Connection, posting_ids: Sequence[int] | None = None
) -> dict[int, tuple[PostingIdentity, ...]]:
    """Current-version identities for the named postings, or for all of them.

    `posting_ids=None` means "all" and issues NO `IN` list, mirroring
    `load_identity_inputs`. That is not symmetry for its own sake: SQLite caps bound
    parameters at `SQLITE_LIMIT_VARIABLE_NUMBER` — measured 32766 on the bundled 3.50.4, and
    only 999 before SQLite 3.32. Both the funnel's `unique` sweep and `identities verify` pass
    every open posting id, and the corpus is **32,771** — already past that cap, so an `IN`
    list here is not a future failure but a present one. Returning identities for closed
    postings too is harmless: every caller looks rows up by id from its own row set.

    An empty list still means an empty result, not "all". When one IS passed it is chunked
    (D-288) — `top_cmd`'s dedup read reaches this with the drain flags' 30,419 ids, and the
    `None` branch's exemption does nothing for a caller that needs a specific set.
    """
    if posting_ids is not None and not posting_ids:
        return {}
    stmt = select(
        posting_identities.c.posting_id,
        posting_identities.c.kind,
        posting_identities.c.identity_key,
    ).where(posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION)
    if posting_ids is None:
        rows = list(conn.execute(stmt).all())
    else:
        # Rows accumulate and the dict is built ONCE below, rather than merging a dict per
        # chunk. Per-chunk merging would be sound — a posting's identity rows all carry the
        # posting_id being chunked on, so no group straddles a chunk — but accumulating
        # removes the need to depend on that. Deduped for the same reason as
        # `load_identity_inputs`: a repeated id in two chunks would append its identity twice.
        rows = []
        for chunk in id_chunks(list(dict.fromkeys(posting_ids))):
            rows.extend(
                conn.execute(
                    stmt.where(posting_identities.c.posting_id.in_(chunk))
                ).all()
            )
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


@dataclass(frozen=True)
class SurfacedJob:
    """One job that reached `job_dispositions` — `seen`, `skipped`, or `built` all mean the
    job was surfaced to the operator (`pipeline/runner.py`, `cli/top_cmd.py`) — paired with
    the identity of the requested kind that its currently-anchored posting(s) carry.

    `identity_key` is `None` when none of the job's current postings carry a current-version
    identity of that kind: a body-less posting withholds `exact_quad` by design (D-132), and
    an un-backfilled one simply has no row yet. This report cannot and does not try to tell
    those two apart — both are "unjudgeable" for leakage and land in the same bucket
    (`reports/leakage.compute_leakage`'s `unidentified`), never folded into "unique".
    """

    job_id: int
    first_decided_at: datetime
    identity_key: str | None


def load_surfaced_exact_quad(conn: Connection) -> tuple[SurfacedJob, ...]:
    """Gate P6's leakage clause: the `exact_quad` half, one row per job.

    Kept as a named function rather than inlined at the call site because the `func.max`
    caveat below is specific to this kind — the wider `company_title_location` reader
    deliberately does NOT collapse a job's keys, and the two must not be confused.
    """
    return load_surfaced_identities(conn, kind="exact_quad")


def load_surfaced_identities(conn: Connection, *, kind: str) -> tuple[SurfacedJob, ...]:
    """Every job ever recorded in `job_dispositions`, paired with the identity key of `kind`
    that its currently-anchored posting(s) carry (design §2, Gate P6's leakage clause).

    **`kind` is a parameter, not a literal, and that is the point.** This read hardcoded
    `exact_quad`, so a job whose only identity was `company_title_location` landed in the
    `unidentified` bucket and could never be counted redundant — Gate P6's duplicate-leakage
    clause therefore reported 0.00% for a STRUCTURAL reason rather than because dedup works.
    A rule that cannot fire is a monitoring failure (CLAUDE.md), so the metric now reads the
    wider kind too, as a separate never-folded bound. Suppression is untouched:
    `SUPPRESSING_KINDS` still holds `exact_quad` alone.

    `kind` is validated against the closed catalog, so an out-of-catalog name raises
    `UnknownIdentityKind` here instead of quietly returning zero rows — which would read as
    "no leakage", the direction that makes the gate easier to pass.

    Joined through the CURRENT `postings.job_id` projection, not through
    `job_grouping_events` history. A job `identities regroup` has already merged away — zero
    postings anchored to it now, per `regroup.apply_merges` moving them onto the survivor —
    is therefore invisible here, deliberately: once a genuine duplicate is consolidated onto
    one canonical job, re-running this report should show it gone, which is the point of
    running `regroup` at all. This is a report on the corpus's CURRENT job structure, not a
    permanent historical tally of every surfacing that ever happened.

    Filtered to `IDENTITY_ALGORITHM_VERSION`, same as `load_identities` and for the same
    reason: an identity computed under a retired algorithm is not comparable to a current
    one, so a posting whose only identity predates a bump reads as unidentified here rather
    than as a stale key that happens to still be on disk.

    A job can anchor more than one posting only when `regroup` verified they share one
    `exact_quad` key (`core/dedup._verify_quad`), so `func.max` over the group either
    resolves to that one shared key or, when nothing under the job is identified, to `NULL` —
    it is not doing anything a plain "pick one" couldn't, given that invariant.

    That invariant holds only at merge time, under the algorithm version then in force. Merges
    are one-way (`store/regroup.py` only moves `postings.job_id` onto the survivor; nothing
    un-merges), and `core/identity_kinds.py` documents a version bump that already happened and
    SPLITS keys — p6.2 folded "+"/"#" to words, so `C++`/`C#`/`C` stopped sharing a title
    component. Two postings merged under p6.1 can therefore carry two different p6.2 keys while
    still anchored to one job, and `func.max` silently keeps the lexicographically larger,
    discarding the other. If the discarded key matches another surfaced job's key, that
    redundancy becomes invisible here — leakage reads lower than it is, the direction that makes
    the <=5% gate easier to pass. `load_surfaced_keys` is the reader that does NOT accept that
    trade; the gate clause still does, and `tests/unit/test_leakage_kinds.py` pins the contrast so
    the two readers cannot silently converge.

    No window filter here on purpose: `reports/leakage.compute_leakage` applies the 7-day cut
    over `first_decided_at`, mirroring the split `reports/stats.summarize` already draws
    between a dumb store read and the one place window logic lives.

    Not filtered on `postings.status` — a posting that reached leads while open and has since
    closed still really reached leads, and excluding it would understate leakage on exactly
    the postings old enough to have closed since.
    """
    kind_spec(kind)  # typed refusal at the call site; never a silent empty result
    stmt = (
        select(
            job_dispositions.c.job_id,
            job_dispositions.c.first_decided_at,
            func.max(posting_identities.c.identity_key).label("identity_key"),
        )
        .select_from(job_dispositions)
        .join(postings, postings.c.job_id == job_dispositions.c.job_id)
        .join(
            posting_identities,
            (posting_identities.c.posting_id == postings.c.id)
            & (posting_identities.c.kind == kind)
            & (posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION),
            isouter=True,
        )
        .group_by(job_dispositions.c.job_id, job_dispositions.c.first_decided_at)
    )
    return tuple(
        SurfacedJob(
            job_id=int(row.job_id),
            first_decided_at=row.first_decided_at,
            identity_key=None if row.identity_key is None else str(row.identity_key),
        )
        for row in conn.execute(stmt).all()
    )


def load_surfaced_keys(conn: Connection, *, kind: str) -> tuple[SurfacedJob, ...]:
    """The same read, but WITHOUT collapsing a job's keys — one row per (job, key).

    `load_surfaced_identities` aggregates with `func.max`, which is sound only under the
    one-key-per-job invariant `regroup` establishes at merge time under the algorithm version
    then in force. An `IDENTITY_ALGORITHM_VERSION` bump can break it (p6.2 already split
    `C++`/`C#`/`C` title components), and when it does, `func.max` keeps the lexicographically
    larger key and DISCARDS the other — hiding a redundancy and making leakage read lower than
    it is.

    For the candidate bound that direction is unacceptable, because the bound's whole claim is
    that the real figure is no higher. So this returns every key: a job holding two keys
    appears under both and inflates the bound rather than shrinking it.

    Jobs with no identity of this kind still come back exactly once, with `identity_key=None`,
    so the `unidentified` bucket is unchanged.
    """
    kind_spec(kind)
    stmt = (
        select(
            job_dispositions.c.job_id,
            job_dispositions.c.first_decided_at,
            posting_identities.c.identity_key,
        )
        .select_from(job_dispositions)
        .join(postings, postings.c.job_id == job_dispositions.c.job_id)
        .join(
            posting_identities,
            (posting_identities.c.posting_id == postings.c.id)
            & (posting_identities.c.kind == kind)
            & (posting_identities.c.algorithm_version == IDENTITY_ALGORITHM_VERSION),
            isouter=True,
        )
        .distinct()
        .order_by(job_dispositions.c.job_id, posting_identities.c.identity_key)
    )
    return tuple(
        SurfacedJob(
            job_id=int(row.job_id),
            first_decided_at=row.first_decided_at,
            identity_key=None if row.identity_key is None else str(row.identity_key),
        )
        for row in conn.execute(stmt).all()
    )


def load_near_duplicate_evidence(
    conn: Connection, posting_ids: Sequence[int]
) -> tuple[PostingEvidence, ...]:
    """The columns `core/near_duplicate` reads, for the named postings.

    A separate read from `load_identity_inputs` on purpose: that one feeds the SUPPRESSION
    path, and the two must not converge into one type that a later refactor could hand to
    `resolve_duplicates`. It also selects far less — no `content_hash`, no locations — because
    the candidate bound only ever runs over the few hundred jobs that reached leads.
    """
    if not posting_ids:
        return ()
    stmt = select(
        postings.c.id,
        postings.c.url,
        postings.c.body_text,
        postings.c.salary_min,
        postings.c.salary_max,
        postings.c.salary_currency,
        postings.c.salary_period,
    )
    rows: list[Row[Any]] = []
    for chunk in id_chunks(list(dict.fromkeys(posting_ids))):
        rows.extend(conn.execute(stmt.where(postings.c.id.in_(chunk))).all())
    return tuple(
        PostingEvidence(
            posting_id=int(r[0]),
            url=None if r[1] is None else str(r[1]),
            body_text=str(r[2]),
            salary_min=r[3],
            salary_max=r[4],
            salary_currency=None if r[5] is None else str(r[5]),
            salary_period=None if r[6] is None else str(r[6]),
        )
        for r in rows
    )


def load_surfaced_posting_ids(conn: Connection) -> dict[int, tuple[int, ...]]:
    """job_id -> the postings currently anchored to it, for every surfaced job."""
    stmt = (
        select(job_dispositions.c.job_id, postings.c.id)
        .select_from(job_dispositions)
        .join(postings, postings.c.job_id == job_dispositions.c.job_id)
        .order_by(job_dispositions.c.job_id, postings.c.id)
    )
    out: dict[int, list[int]] = {}
    for job_id, posting_id in conn.execute(stmt).all():
        out.setdefault(int(job_id), []).append(int(posting_id))
    return {job_id: tuple(ids) for job_id, ids in out.items()}
