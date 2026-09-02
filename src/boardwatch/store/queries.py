"""Run bookkeeping and small read queries.

insert_run commits immediately at scan start so the running scan's started_at
is queryable while it runs (§0.3 — the scan lock carries no holder metadata).
Run counts are derived conveniences; posting_events is the source of truth (§4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Connection,
    Engine,
    Row,
    Select,
    func,
    insert,
    literal_column,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import ResponseValidators
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.tables import (
    board_scans,
    companies,
    http_cache,
    posting_versions,
    postings,
    profile,
    runs,
)

# An alias so the "no newer version exists" correlated EXISTS can compare a row against
# its own table. The pattern mirrors extract/preflight.py:63-81, which finds every
# missing row with ONE set-oriented correlated EXISTS rather than a per-row lookup.
_pv = posting_versions.alias("pv_current")


def body_is_empty() -> ColumnElement[bool]:
    """SQL predicate: this open posting's JD body is empty once trimmed (a stub).

    ONE expression with four readers: `run_funnel_queries.count_stub_postings`, which is the
    stub-rate instrument, and the three corpus-wide ranking surfaces (`top`, `notify`, `stats`)
    whose zero-signal rule must ABSTAIN rather than veto on a body it never had. If the
    ranker's notion of "empty" drifted from the instrument's, the alarm and the fail-open would
    stop describing the same postings — and the fail-open exists precisely so that a lane
    landing empty bodies raises the alarm instead of reading as clean noise removal.

    Evaluated in SQLite, never in Python: `body_text` is the largest column in the schema and
    the ranker reads every open posting, so the flag is computed where the row already is.
    `show <id>` is the one caller that does not use this predicate — it reads a single posting
    and already has the body in hand — and it repeats the strip set below verbatim for the same
    agreement reason.

    The two-arg `trim` names the strip set explicitly — SQLite's one-arg `trim` removes spaces
    ONLY, so a body of tabs or newlines would otherwise read as non-empty.
    """
    return func.trim(postings.c.body_text, " \t\n\r\f\v") == ""

# The closed catalog of run outcomes (P0 item 4). Out-of-catalog is a failure, never a new
# bucket, so the setter raises rather than writing an unknown string.
RUN_RUNNING = "running"
RUN_OK = "ok"
RUN_FAILED = "failed"
RUN_STATUSES = frozenset({RUN_RUNNING, RUN_OK, RUN_FAILED})


class UnknownRunStatusError(ValueError):
    """A run status outside the closed catalog. Typed at the raise site, never a string match."""


def _checked_status(status: str) -> str:
    if status not in RUN_STATUSES:
        raise UnknownRunStatusError(
            f"{status!r} is not a run status; expected one of {sorted(RUN_STATUSES)}"
        )
    return status


def insert_run(engine: Engine) -> int:
    with engine.begin() as conn:
        result = conn.execute(insert(runs).values(started_at=utcnow(), boards_attempted=0))
        return int(result.inserted_primary_key[0])  # type: ignore[index]


def finalize_run(
    engine: Engine,
    run_id: int,
    *,
    boards_attempted: int,
    boards_complete: int,
    boards_partial: int | None = None,
    boards_unchanged: int | None = None,
    boards_failed: int | None = None,
    postings_seen: int,
    new_count: int,
    closed_count: int,
    reopened_count: int,
    errors: list[str],
    finished: bool = True,
    status: str = RUN_OK,
) -> None:
    """Write the scan stage's counts onto a run row.

    `finished=False` when the caller does not own the run — under `boardwatch run` the scan
    is stage one of three, so stamping finished_at here would record the pipeline as complete
    the moment scan returned. The owner calls finish_run instead.
    """
    values: dict[str, object] = {
        "boards_attempted": boards_attempted,
        "boards_complete": boards_complete,
        "boards_partial": boards_partial,
        "boards_unchanged": boards_unchanged,
        "boards_failed": boards_failed,
        "postings_seen": postings_seen,
        "new_count": new_count,
        "closed_count": closed_count,
        "reopened_count": reopened_count,
        "errors_json": errors,
    }
    if finished:
        values["finished_at"] = utcnow()
        # Only when this caller owns the run. `errors` is NOT the discriminator: per-board
        # failures are the scan's normal partial outcome (Workday returns `partial`
        # routinely), so the caller decides, and it is the only one that can tell a few dead
        # boards from a systemic outage.
        values["status"] = _checked_status(status)
    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.id == run_id).values(**values))


def finish_run(
    engine: Engine, run_id: int, *, errors: list[str] | None = None, status: str = RUN_OK
) -> None:
    """Stamp finished_at and the terminal status on a run the caller owns.

    `status` is the run's exit status for P0 item 4's manifest. It is a parameter rather than
    something inferred from `errors` because the two are not the same question: a run can
    finish with per-lead tailor errors and still be a successful run, while a run killed
    before this call has no errors recorded at all and is not successful.

    What an un-updated row means is fixed by the column default, and the honest statement is
    narrower than "it was killed": `running` with `finished_at` NULL means only *nothing ever
    closed this row*. Three conditions share that signature — a run still in flight, a run
    killed by SIGKILL, and a standalone lane that raised between `ensure_run` and its own
    `finish_run` (`reports/tailor.py`, `eligibility/preflight.py` and `cli/eligibility_cmd.py`
    each call this on the success path only, with no `try/finally`). Separating those three
    needs the reaper that P3 owns; this column does not claim to do it.

    Errors are appended, not replaced: the scan stage has already written its own into
    errors_json by the time the pipeline finishes, and overwriting would lose them.

    Known narrow race: the `errors` branch is a SELECT-then-UPDATE read-modify-write on
    errors_json, not a single atomic statement (unlike `reap_stale_runs`'s `json_insert`). In
    WAL mode, `SQLITE_BUSY_SNAPSHOT` — which `busy_timeout` does not retry — is possible if
    `reap_stale_runs` commits a write to this same row between this function's SELECT and
    UPDATE. It requires a run finishing WITH errors while concurrently crossing the reaper's
    >24h threshold in this exact microsecond gap — extraordinarily narrow, and not worth
    restructuring this function's read-modify-write for.
    """
    with engine.begin() as conn:
        values: dict[str, object] = {
            "finished_at": utcnow(),
            "status": _checked_status(status),
        }
        if errors:
            existing = conn.execute(
                select(runs.c.errors_json).where(runs.c.id == run_id)
            ).scalar_one_or_none()
            values["errors_json"] = list(existing or []) + errors
        conn.execute(update(runs).where(runs.c.id == run_id).values(**values))


def reap_stale_runs(engine: Engine, *, older_than: timedelta) -> list[int]:
    """Drain phantom `running` rows a crashed/killed run left behind (P3 slice 2, D-046).

    Age-based, not liveness-based: `runs` carries no pid/heartbeat column, and adding one
    would only work same-host anyway. A single atomic UPDATE re-checks
    `status='running' AND finished_at IS NULL AND started_at < cutoff` INSIDE the statement, so
    a row `finish_run` closes concurrently is skipped by the UPDATE's own predicate, and
    calling this twice reaps nothing the second time — no read-modify-write, no lost update, no
    duplicate note. `errors_json` is appended to via `json_insert`, atomically, rather than
    read back and rewritten.

    The returned/logged ids come from the UPDATE's own `RETURNING`, never from a separate
    pre-UPDATE `SELECT`: under a race between two reapers (two `run` starts, or `doctor`
    racing a `run`, against the same cutoff), a pre-UPDATE `SELECT` can still see a row as
    `running` a moment before the winner's UPDATE closes it — the loser's data is correct
    (its own UPDATE mutates zero rows of that id) but a SELECT-derived list would still claim
    it as reaped. `RETURNING` reports exactly what THIS call mutated, never what it merely saw.

    A false reap self-corrects `status`, not `errors_json`: `finish_run` has no
    `status='running'` precondition, so a run that breaches the threshold and then finishes
    normally overwrites `failed` with its real terminal status. The `reaped: ...` note this
    function appended, though, is never removed — `finish_run` only ever appends to
    `errors_json` (see its docstring), it does not strip prior entries. That persistence is
    intentional, not a bug to fix: a run that took over the threshold and then completed is
    genuinely anomalous, and the note is a truthful breadcrumb of that, worth keeping even on
    an otherwise-successful run. Do not read this as "fully self-corrects" — only the status
    column does.
    """
    now = utcnow()
    cutoff = now - older_than
    stale = (
        (runs.c.status == RUN_RUNNING)
        & runs.c.finished_at.is_(None)
        & (runs.c.started_at < cutoff)
    )
    hours = older_than.total_seconds() / 3600
    note = f"reaped: running with no terminal status for > {hours:g}h"
    with engine.begin() as conn:
        result = conn.execute(
            update(runs)
            .where(stale)
            .values(
                status=RUN_FAILED,
                finished_at=now,
                errors_json=func.json_insert(
                    func.coalesce(runs.c.errors_json, literal_column("'[]'")), "$[#]", note
                ),
            )
            .returning(runs.c.id)
        )
        return [int(row.id) for row in result.all()]


def append_run_error(engine: Engine, run_id: int, note: str) -> None:
    """Add one error to a run row that has already been finished, and nothing else.

    Exists because `runner.py` emits the funnel and morning artifacts AFTER `finish_run` — it
    has to, or the artifact would record every run as still in progress — so a reporting
    failure there had no way to reach the store at all. It was printed to the console and
    nothing else, which meant **a run whose funnel never wrote still exited 0 and looked
    identical to a clean one** to anything reading the database. That matters because Gate P3
    counts clean unattended runs while B1 and B5 are read out of the funnel (D-287, and
    STATE's open question 1).

    Deliberately NOT `finish_run(errors=[note])`: that would re-stamp `finished_at` and
    `status`, so a reporting failure would move the run's own completion time. A reporting
    failure is not a run outcome, and this function cannot change one — it only appends.

    Atomic `json_insert` rather than a read-modify-write, matching `reap_stale_runs`: this is
    called from a `finally` block that may already be unwinding an exception, and it can race
    the reaper on the same row.
    """
    with engine.begin() as conn:
        conn.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                errors_json=func.json_insert(
                    func.coalesce(runs.c.errors_json, literal_column("'[]'")), "$[#]", note
                )
            )
        )


def record_corpus_counts(
    engine: Engine,
    run_id: int,
    *,
    open_postings: int,
    evaluated: int,
    candidates: int,
) -> None:
    """Stamp the standing eligible corpus onto a run row that has already been finished.

    The same shape as `append_run_error` above, and for the same reason: this is called from
    the funnel writer, which runs AFTER `finish_run`, so it must be able to add a fact to a
    finished row without touching `status` or `finished_at`. Deliberately NOT
    `finalize_run(...)`: that re-stamps both, so recording an observation about the corpus
    would move the run's own completion time, and a corpus count is not a run outcome.

    All three are required keyword arguments rather than defaulting to `None`. There is one
    caller, and a forgotten count should be a type error rather than a silently NULL column
    that the corpus-regression detector then skips forever without saying why (the same
    direction `collect_run_funnel` takes for `lanes`).

    NULL therefore means exactly one thing: this function was never called for the run — a row
    that predates the columns, or a run whose funnel never reached the corpus count. The
    detector treats such a run as unmeasured and skips it; it never reads absent as zero,
    because zero here is the alarm.
    """
    with engine.begin() as conn:
        conn.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                corpus_open=open_postings,
                corpus_evaluated=evaluated,
                corpus_candidates=candidates,
            )
        )


def ensure_run(engine: Engine, run_id: int | None) -> int:
    """Return the caller's run id, minting a fresh run row when there is none.

    This is what keeps `run_id IS NULL` meaning exactly one thing — *the row predates run
    attribution* — instead of also meaning "written outside a pipeline". Every stage that
    writes an attributable row calls this, so a stage invoked standalone is recorded as a
    degenerate pipeline run rather than as an unattributed write.
    """
    return insert_run(engine) if run_id is None else run_id


def get_validators(
    conn: Connection,
    url: str,
    *,
    max_age: timedelta | None = None,
    now: datetime | None = None,
) -> ResponseValidators | None:
    """Cached conditional-request validators for ``url``, or None when none are usable.

    ``max_age`` forces periodic revalidation: a validator whose ``fetched_at`` is older than it
    is dropped, so the next scan refetches unconditionally instead of trusting a possibly-stale
    upstream ETag forever. ``max_age=None`` (the default) never expires a validator.
    """
    row = conn.execute(
        select(http_cache.c.etag, http_cache.c.last_modified, http_cache.c.fetched_at).where(
            http_cache.c.url == url
        )
    ).one_or_none()
    if row is None:
        return None
    if max_age is not None and (utcnow() if now is None else now) - row.fetched_at > max_age:
        return None
    return ResponseValidators(etag=row.etag, last_modified=row.last_modified)


def get_watched_companies(
    conn: Connection, *, slug: str | None = None, provider: str | None = None
) -> list[Row[Any]]:
    stmt = select(companies).where(companies.c.watched.is_(True))
    if slug is not None:
        # Case-folded in SQL, the way `stored_slug` compares (D-339): `--company KAYAK` must
        # reach the board stored as `kayak`. A Python `.lower()` disagrees above ASCII.
        stmt = stmt.where(func.lower(companies.c.slug) == func.lower(slug))
    if provider is not None:
        stmt = stmt.where(companies.c.provider == provider)
    return list(conn.execute(stmt).all())


def stored_slug(conn: Connection, *, provider: str, slug: str) -> str | None:
    """The slug this provider already stores for `slug`, compared WITHOUT REGARD TO CASE.

    `UNIQUE(provider, slug)` is a case-SENSITIVE index, so it does not stop one board being
    stored twice under two spellings. It happened: `ashby:Lightfield` (user) and
    `ashby:lightfield` (lane) were one board with one set of 19 postings and one set of Ashby
    posting UUIDs, both watched, fetched twice a run — and the duplicate postings were
    unsuppressible, because every identity kind that suppresses a duplicate is scoped by
    `company_id` and there were two. `ashby:KAYAK` was the same thing caught by hand.

    Returned rather than a bool so a caller can INSERT UNDER THE STORED SPELLING instead of its
    own. That is what keeps the guard from rewriting a live URL: nothing normalizes an existing
    slug, so the stored spelling is the one every existing URL and cache key already uses.

    **Correction 2026-09-01:** this paragraph used to justify that by saying a Workday career
    site is case-sensitive live. It is not — measured across three boards and three casing
    styles, the CXS endpoint returns identical results either way (see `workday.split_slug`).
    The justification is preservation-is-free, not preservation-is-required. Nothing about this
    function changes: it is the guard that makes Workday case differences converge instead of
    duplicating, which is precisely why lowering the case would buy nothing.

    A provider that wants its slugs folded says so with `normalize_slug` (smartrecruiters does);
    this function only refuses the SECOND ROW.

    Case folding happens on both sides in SQL, so both use SQLite's ASCII-only `lower()` and
    agree. Python's Unicode-aware `str.lower()` on one side would disagree with it above
    ASCII and miss a match — failing toward two rows, which is the bug this exists to stop.

    Oldest row wins (`ORDER BY id`), so a store that already holds a collided pair resolves to
    the same row every time instead of alternating.
    """
    return conn.execute(
        select(companies.c.slug)
        .where(companies.c.provider == provider, func.lower(companies.c.slug) == func.lower(slug))
        .order_by(companies.c.id)
        .limit(1)
    ).scalar_one_or_none()


def upsert_watch(conn: Connection, *, provider: str, slug: str, name: str, source: str) -> str:
    """Watch `(provider, slug)`, and return the slug ACTUALLY watched.

    The returned slug differs from the argument when the store already holds this board under
    another case: the watch lands on that row rather than adding a second one. Callers report
    the difference — a user who typed `ashby:KAYAK` must not be left believing a new board was
    added when `ashby:kayak` was already watched.
    """
    target = stored_slug(conn, provider=provider, slug=slug) or slug
    stmt = sqlite_insert(companies).values(
        name=name, provider=provider, slug=target, source=source, watched=True
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[companies.c.provider, companies.c.slug], set_={"watched": True}
        )
    )
    return target


def upsert_lane_company(
    conn: Connection, *, provider: str, slug: str, name: str, watch: bool = False
) -> int:
    """Record a company an aggregator lane discovered: `source='lane'`. Returns its `companies.id`.

    Stored `watched=False` (D-285) UNLESS the caller passes `watch=True`. Unwatched is
    load-bearing, not caution: `scan/coordinator.py` looks every watched company's provider up in
    the registry and appends `unknown provider` to `summary.errors` on a miss, so a watched
    `hiringcafe` row would add an error line to every run forever. Nothing downstream of the scan
    filters on `watched`, so the lane's postings still reach the shortlist either way.

    `watch=True` is for exactly the case the default forbids: a company on a provider the scanner
    CAN parse. An Indeed tier-1 convergence sits on a supported board (`hit_identity` assigns a
    real provider only when `parse_posting_target` recovered one), so watching it adds no `unknown
    provider` line AND is the DRAIN for the secondhand body that hit wrote (D-414(a)): with the
    board watched, a later scan fetches the employer's own JD, `remote_policy` and location and
    replaces JD v1, which otherwise decides forever because a lane-first company is scanned by
    nothing. (A fresh ETag/Last-Modified can make that scan read `unchanged` and defer the fetch, so
    the drain is bounded by the validator TTL rather than guaranteed on the very next scan.)
    It stays a defaulted parameter rather than a second function because the default
    (`False`) preserves every existing caller's behaviour exactly and the flag is MONOTONIC —
    `False`->`True` only, never the reverse — so it is safe from any lane at any frequency.

    With `watch=False` this touches NOTHING AT ALL on conflict, name included; with `watch=True`
    it upgrades ONLY `watched` (`False`->`True`) and still leaves name and source alone. A lane
    must never unwatch a board the user watches and must never relabel a `registry` company as
    lane-discovered — either would make the store's own account of where a company came from a lie.

    `name` looked inert and is not: `scan/apply.py` reads `companies.name` and feeds it into
    `IdentityInputs.company_name`, a component of the `cross_host` posting identity. So letting
    an aggregator's rendering of an employer ("Acme Technologies") overwrite a curated registry
    name ("Acme") would silently re-key that company's stored identities, and `identities
    verify` would report every posting written under the old name as stale until a full board
    scan rewrote it. The display name is also unrecoverable once overwritten — nothing records
    the prior value.

    The cost is that a lane company's name is frozen at first discovery. That is the right
    trade: it is cosmetic, it is stable, and it makes this function safe no matter how often or
    from where a caller invokes it.

    The insert's conflict clause is case-SENSITIVE, so on its own it would happily add a second
    row for a board already stored under another case. `stored_slug` is what stops it, and the id
    it resolves to is returned so the caller does not have to re-select by a slug the store may
    not hold. When `stored_slug` already found the row, a `watch=True` upgrade is an UPDATE keyed
    on the stored slug, not a re-insert, for the same reason.

    `stored_slug` closes the SEQUENTIAL case-variant duplicate only, NOT a CONCURRENT one: the
    case-insensitive read and the case-SENSITIVE insert here are not atomic, so a manual
    `upsert_watch` of a case-variant slug that commits BETWEEN this function's `stored_slug` read
    and its insert still leaves two rows (`ashby:Lightfield` + `ashby:lightfield`), splitting
    postings across two `company_id`s. That race is a KNOWN, PRE-EXISTING gap that `watch=True`
    only makes worse by making the duplicate watched; its proper fix is a `(provider, lower(slug))`
    unique index plus reconciling existing collisions -- a live-store migration, deliberately
    deferred (owner-gated).
    """
    target = stored_slug(conn, provider=provider, slug=slug)
    if target is None:
        stmt = sqlite_insert(companies).values(
            name=name, provider=provider, slug=slug, source="lane", watched=watch
        )
        # `watch=True` must survive a race that inserted this row first (upgrade its `watched`);
        # `watch=False` must still touch nothing on conflict. Only `watched` is ever set on
        # conflict, so a raced row's name and source are never relabelled.
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[companies.c.provider, companies.c.slug],
                set_={"watched": True},
            )
            if watch
            else stmt.on_conflict_do_nothing(
                index_elements=[companies.c.provider, companies.c.slug]
            )
        )
        target = slug
    elif watch:
        # The row already exists, possibly under another slug CASE (`target`). Upgrade THAT row
        # rather than inserting the lane's spelling as a second one. `watched.is_(False)` keeps
        # the upgrade monotonic and leaves an already-watched board — and its name and source —
        # untouched.
        conn.execute(
            update(companies)
            .where(
                companies.c.provider == provider,
                companies.c.slug == target,
                companies.c.watched.is_(False),
            )
            .values(watched=True)
        )
    return int(
        conn.execute(
            select(companies.c.id).where(
                companies.c.provider == provider, companies.c.slug == target
            )
        ).scalar_one()
    )


def company_exists(conn: Connection, *, provider: str, slug: str) -> bool:
    """Is this `(provider, slug)` already stored, watched or not — under ANY slug case?

    The lane budget's is-new check. `get_watched_companies` cannot answer it: a lane-discovered
    company is unwatched, so asking that would charge a cap slot to a company already stored,
    every run, and reach would never widen.

    Case-insensitive for the same reason the upserts are (see `stored_slug`), and it has to be:
    a case-variant that read as NEW here spent a cap slot AND got past `upsert_lane_company`,
    which is exactly how `ashby:lightfield` became a second row for `ashby:Lightfield`.
    """
    return stored_slug(conn, provider=provider, slug=slug) is not None


# keep the P0 signature working — it is now a thin wrapper (no caller churn)
def upsert_watched_company(conn: Connection, *, provider: str, slug: str, name: str) -> None:
    upsert_watch(conn, provider=provider, slug=slug, name=name, source="user")


def unwatch(conn: Connection, *, provider: str, slug: str) -> int:
    """Unwatch a board, resolving the slug the way `upsert_watch` does.

    Case-insensitive because `upsert_watch` is: without it, `companies add ashby:KAYAK` (which
    now lands on the stored `ashby:kayak`) could not be undone by `companies remove ashby:KAYAK`.
    """
    target = stored_slug(conn, provider=provider, slug=slug)
    if target is None:
        return 0
    result = conn.execute(
        update(companies)
        .where(companies.c.provider == provider, companies.c.slug == target)
        .values(watched=False)
    )
    return int(result.rowcount)


def list_watches(conn: Connection) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(
                companies.c.provider, companies.c.slug, companies.c.source,
                companies.c.watched, companies.c.last_health, companies.c.last_ok_at,
            ).where(companies.c.watched.is_(True)).order_by(companies.c.provider, companies.c.slug)
        ).all()
    )


def get_profile(conn: Connection) -> Row[Any] | None:
    return conn.execute(select(profile).where(profile.c.id == 1)).one_or_none()


def save_profile(
    conn: Connection,
    *,
    text: str,
    target_titles: list[str],
    exclude_titles: list[str],
    locations: list[str],
    remote_only: bool,
    skills: list[str],
    taxonomy_version: str,
    resume_max_pages: int,
    target_seniority_band: str = "any",
) -> None:
    stmt = sqlite_insert(profile).values(
        id=1,
        text=text,
        skills_json=skills,
        taxonomy_version=taxonomy_version,
        target_titles_json=target_titles,
        exclude_titles_json=exclude_titles,
        locations_json=locations,
        remote_only=remote_only,
        resume_max_pages=resume_max_pages,
        target_seniority_band=target_seniority_band,
        updated_at=utcnow(),
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[profile.c.id],
            set_={
                "text": stmt.excluded.text,
                "skills_json": stmt.excluded.skills_json,
                "taxonomy_version": stmt.excluded.taxonomy_version,
                "target_titles_json": stmt.excluded.target_titles_json,
                "exclude_titles_json": stmt.excluded.exclude_titles_json,
                "locations_json": stmt.excluded.locations_json,
                "remote_only": stmt.excluded.remote_only,
                "resume_max_pages": stmt.excluded.resume_max_pages,
                "target_seniority_band": stmt.excluded.target_seniority_band,
                "updated_at": stmt.excluded.updated_at,
            },
        )
    )


def save_eligibility(
    conn: Connection, *, facts_json: dict[str, object], policy_json: dict[str, object]
) -> None:
    """Write the eligibility facts and severity policy onto the existing profile row.

    Takes JSON-ready dicts rather than the typed models, so this layer never imports from
    boardwatch.eligibility. The eligibility layer reads and writes the store; the reverse
    dependency would invert the layering.

    A separate UPDATE, never part of save_profile's upsert. Two reasons, both verified:
    profile.text is NOT NULL with no default, so an insert carrying only facts raises
    IntegrityError; and save_profile's set_ map must never list these columns or
    `profile edit` silently wipes declared facts (spec §4.6).
    """
    conn.execute(
        update(profile)
        .where(profile.c.id == 1)
        .values(
            eligibility_facts_json=facts_json,
            eligibility_policy_json=policy_json,
            updated_at=utcnow(),
        )
    )


def last_complete_scan_ages(conn: Connection) -> dict[int, datetime]:
    """company_id → finished_at of its most recent complete-or-unchanged board_scan."""
    stmt = (
        select(board_scans.c.company_id, func.max(board_scans.c.finished_at))
        .where(board_scans.c.status.in_(("complete", "unchanged")))
        .group_by(board_scans.c.company_id)
    )
    return {row[0]: row[1] for row in conn.execute(stmt).all()}


@dataclass(frozen=True)
class CurrentVersion:
    """The newest immutable content version of one posting.

    body_text comes from posting_versions, NEVER from postings.body_text, which
    scan/apply.py:119-120 rewrites in place on every revision. Spans stored against a
    version stay valid forever; spans against the posting garble on the next revision.
    """

    posting_version_id: int
    posting_id: int
    body_text: str
    captured_at: datetime


def canonical_job_ids(conn: Connection, posting_ids: Sequence[int]) -> dict[int, int]:
    """`{posting_id: postings.job_id}` for the postings asked about, read fresh.

    Exists because a delivery-queue folder records the `job_id` it was written under, and that
    answer GOES STALE: identity resolution can converge a lane copy onto a native find, at which
    point the posting's canonical job moves and the folder's stored value no longer names it.
    Measured case, run 139: posting 131367 (a lane copy, `pst_2a1f2c22...`) now carries
    `job_id = 69007`, the native Workday find (`JR-202618529`), while its folder still recorded
    131367 — so the folder identified neither the offered posting nor the job it belonged to.

    **Lives here rather than in `delivery_queries` because it binds an id list.** That module
    forbids `.in_()` outright, and its own test enforces it: collecting posting ids and binding
    them is the shape that hit SQLite's 32,766 bound-parameter cap at six call sites on
    2026-08-23 and killed every scheduled run from that day on. Chunked through `id_chunks`
    (D-288) like every other id-list read here, and `dict.update` is the EXACT merge because the
    result is keyed on `posting_id`, the very column being chunked.

    A posting the store no longer holds is simply absent rather than raising: a queue folder for
    a deleted posting is the caller's problem to classify, not this query's.
    """
    if not posting_ids:
        return {}
    resolved: dict[int, int] = {}
    for chunk in id_chunks(posting_ids):
        resolved.update(
            {
                int(row.id): int(row.job_id)
                for row in conn.execute(
                    select(postings.c.id, postings.c.job_id).where(postings.c.id.in_(chunk))
                ).all()
            }
        )
    return resolved


def current_posting_versions(
    conn: Connection, posting_ids: Sequence[int] | None = None
) -> dict[int, CurrentVersion]:
    """posting_id -> its newest posting_versions row.

    With posting_ids=None this sweeps every OPEN posting in ONE statement, which is the
    preflight path. With an explicit list it ignores status, which is how `show` renders a
    closed posting's historical verdict (D-P2-9), and it issues one statement per 500 ids
    because `export` passes the whole open corpus (D-287) — NOT one statement, and do not
    read this docstring as evidence that it is. No per-posting SQL on either path (D-P2-16).

    The tie-break on (captured_at, id) is load-bearing: two versions captured in the same
    transaction share captured_at, and ordering by captured_at alone would make "the
    current version" nondeterministic.
    """
    if posting_ids is not None and not posting_ids:
        return {}
    newer = (
        select(posting_versions.c.id)
        .where(
            posting_versions.c.posting_id == _pv.c.posting_id,
            tuple_(posting_versions.c.captured_at, posting_versions.c.id)
            > tuple_(_pv.c.captured_at, _pv.c.id),
        )
        .exists()
    )
    stmt = (
        select(
            _pv.c.id.label("posting_version_id"),
            _pv.c.posting_id,
            _pv.c.body_text,
            _pv.c.captured_at,
        )
        .join(postings, _pv.c.posting_id == postings.c.id)
        .where(~newer)
    )
    def rows_of(selectable: Select[Any]) -> dict[int, CurrentVersion]:
        return {
            int(row.posting_id): CurrentVersion(
                posting_version_id=int(row.posting_version_id),
                posting_id=int(row.posting_id),
                body_text=str(row.body_text),
                captured_at=row.captured_at,
            )
            for row in conn.execute(selectable).all()
        }

    if posting_ids is None:
        return rows_of(stmt.where(postings.c.status == "open"))
    # Chunked past SQLite's bound-parameter cap. `export` passes every open posting id UNION
    # every tracked one, which crossed the cap at 32,771 open postings — the `None` branch
    # above never had the problem, this one has been failing since. Chunk-and-merge is exact:
    # `~newer` is correlated per posting and considers all of that posting's versions
    # whatever the filter, so a posting's current version does not depend on its chunk.
    out: dict[int, CurrentVersion] = {}
    for chunk in id_chunks(list(posting_ids)):
        out.update(rows_of(stmt.where(postings.c.id.in_(chunk))))
    return out
