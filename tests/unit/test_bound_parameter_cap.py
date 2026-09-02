"""The eligibility ledger reads must survive an id list longer than SQLite's parameter cap.

SQLite refuses any statement binding more than `SQLITE_LIMIT_VARIABLE_NUMBER` parameters —
32766 on the bundled 3.50, and only 999 before 3.32. On 2026-08-23 the live store crossed it
at 32,771 open postings and every scheduled run died. Two symptoms, one cause: the funnel
reached `current_evaluations` first and swallowed the failure into a printed
`! funnel artifact not written` warning, then the ranker reached `current_verdicts` and took
the run down with `OperationalError: too many SQL variables`. The corpus only grows, so from
that day the failure was permanent rather than intermittent.

**Every test here binds MORE ids than the cap, deliberately.** A test using a comfortable
batch size passes against the unchunked code and merely moves the wall to a later date, which
is exactly how this shipped. The cap is read off the running interpreter rather than
hard-coded, so the list crosses the real limit on whatever SQLite is bundled here.

The one real id is placed LAST in the list: an implementation that chunks but returns only the
first chunk's rows raises nothing and still loses the verdict, so "did not raise" alone is not
the assertion.
"""

import re
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.posting_identity import PostingIdentity
from boardwatch.core.regroup import JobMerge
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.eligibility.read import (
    current_evaluations_chunked,
    current_gate_verdicts,
    current_verdicts,
)
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.abstain_queries import count_requirement_dispositions
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.identity_queries import (
    load_identities,
    load_identity_inputs,
    write_identities,
)
from boardwatch.store.ledger_queries import load_dispositions, record_disposition, reopen_jobs
from boardwatch.store.param_chunks import ID_CHUNK_SIZE
from boardwatch.store.quarantine_queries import drain_quarantine, live_quarantine
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.regroup import apply_merges, job_anchors
from boardwatch.store.tables import (
    companies,
    jobs,
    posting_versions,
    postings,
    quarantined_bodies,
)

BLOCK_ALL = Policy(families={
    "work_auth": "blocker", "experience_years": "blocker",
    "clearance": "blocker", "degree": "blocker",
})

# The live cap on this interpreter's SQLite, not a literal: a hard-coded 32766 would stop
# crossing the real limit the moment the bundled SQLite changed it, and the test would go
# green while the bug came back.
VAR_LIMIT = sqlite3.connect(":memory:").getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)

# A JD the bundled catalog has something to say about, so the verdict read back is a real
# deterministic verdict rather than None.
JD = "Bachelor's degree required."


def _oversized(real_id: int) -> list[int]:
    """`VAR_LIMIT + 1` ids: non-existent padding, then the one id that exists.

    One over the cap before the query's own scalars (profile_hash, rules_hash, engine_kind,
    engine_version) are bound, so the list alone is already too long. Ids that match no row
    cost one bound parameter each exactly like real ones — the cap is on parameters, not on
    rows — so this needs no 32k-row fixture and stays fast.
    """
    padding = list(range(real_id + 1, real_id + 1 + VAR_LIMIT))
    return [*padding, real_id]


# Applied ONLY to the tests that must bind over the cap — never to the static import-pin
# below, which has no dependence on the parameter limit and must not be skipped with them.
#
# The threshold is deliberately far above both real-world values. `uv`'s interpreter reports
# 32,766, but some distro builds (and this machine's system python3) patch
# SQLITE_MAX_VARIABLE_NUMBER to 250,000 — at which point these tests must bind 250,001 ids and
# run slowly, NOT skip. A skip here would be green for the wrong reason, which is precisely the
# failure mode this whole file exists to prevent, and `pytest.skip` announces nothing.
needs_a_real_cap = pytest.mark.skipif(
    VAR_LIMIT > 1_000_000,
    reason=f"SQLite here allows {VAR_LIMIT} bound parameters; the id list would be absurd",
)


def test_the_chunk_size_is_small_enough_for_the_spanning_tests_to_span() -> None:
    """Every `_oversized_spanning` test's discriminating power rests on this inequality.

    Those tests catch a dropped chunk only because their two real ids land in DIFFERENT
    chunks, which holds only while `ID_CHUNK_SIZE` is under the parameter cap. `needs_a_real_cap`
    bounds `VAR_LIMIT` from ABOVE only, so nothing else here notices a build that patches
    `SQLITE_MAX_VARIABLE_NUMBER` *down* below 500, or a future session raising `ID_CHUNK_SIZE`
    toward the cap for fewer round-trips. Either collapses every list into one chunk, and an
    implementation that keeps only the last chunk would then pass all six.

    A test rather than a module-level assert, deliberately: an import-time assert aborts
    COLLECTION of this file, which is exactly how the whole set is verified — forcing
    `ID_CHUNK_SIZE` to 10**9 and requiring every test here to go red. An assert would make that
    check impossible to run instead of merely failing it.
    """
    assert ID_CHUNK_SIZE < VAR_LIMIT, (
        f"chunk size {ID_CHUNK_SIZE} >= parameter cap {VAR_LIMIT}: the spanning tests would "
        "fit in a single chunk and could no longer catch a dropped one"
    )


@pytest.fixture()
def catalog(tmp_path):
    return load_rules(tmp_path / "no-override")


@pytest.fixture()
def db(tmp_path) -> Engine:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    return engine


@pytest.fixture()
def seeded(db: Engine) -> tuple[int, int]:
    """(posting_id, posting_version_id) for one open posting whose body the catalog reads."""
    now = utcnow()
    with db.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
        jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        pid = int(conn.execute(insert(postings).values(
            company_id=cid, job_id=jid, provider_posting_id="p-1", title="Eng",
            normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
            consecutive_missing=0, content_hash="h1", body_text=JD,
        )).inserted_primary_key[0])
        vid = int(conn.execute(insert(posting_versions).values(
            posting_id=pid, content_hash="h1", body_text=JD,
            captured_at=now, run_id=None, capture_reason="new",
        )).inserted_primary_key[0])
    return pid, vid


def _identity(catalog, version_id: int, facts: Facts):
    return build_identity(
        posting_version_id=version_id, facts=facts, policy=BLOCK_ALL, catalog=catalog,
        declared_fields=declared_fields(),
    )


def _write_deterministic(db: Engine, catalog, version_id: int, facts: Facts) -> int:
    result = evaluate(JD, facts, BLOCK_ALL, catalog)
    with db.begin() as conn:
        return write_evaluation(
            conn, posting_version_id=version_id, identity=_identity(catalog, version_id, facts),
            result=result,
        )


@needs_a_real_cap
def test_current_evaluations_chunked_reads_more_ids_than_the_bound_parameter_cap(
    db: Engine, catalog, seeded: tuple[int, int]
) -> None:
    """The ledger read the FUNNEL uses, whose failure is swallowed into a printed warning.

    Fails against the engine's un-wrapped read with `OperationalError: too many SQL
    variables`, and against a wrapper that keeps only one chunk's rows with a missing verdict.
    """
    _, version_id = seeded
    facts = Facts(highest_degree="none")
    eval_id = _write_deterministic(db, catalog, version_id, facts)
    ident = _identity(catalog, version_id, facts)
    with db.connect() as conn:
        got = current_evaluations_chunked(
            conn, _oversized(version_id), ident.profile_hash, ident.rules_hash
        )
    assert got == {version_id: (eval_id, "ineligible")}


def test_nothing_outside_read_py_calls_the_engines_unchunked_evaluation_read() -> None:
    """`current_evaluations_chunked` is the only safe door, and this pins it shut.

    The engine's `current_evaluations` binds its whole id list in one statement and CANNOT be
    fixed in place: `engine.py` is digested (`engine.digested_modules`), so batching there
    would move `engine_version` and re-key every verdict in the corpus plus every permanent
    ledger stamp — for a change that alters no verdict. So the unsafe function stays, and a
    fifth caller reaching for it directly would restore the 2026-08-23 outage silently, not
    at once but whenever the corpus next grew. `\b` after the name excludes the `_chunked`
    wrapper, which is the point of the check.
    """
    src = Path(__file__).resolve().parents[2] / "src" / "boardwatch"
    bare = re.compile(r"\bcurrent_evaluations\b")
    # Keyed on the RELATIVE PATH, not the bare filename: excluding `"engine.py"` by name would
    # silently exempt a future `providers/engine.py` or `store/read.py` from the whole check.
    allowed = {"eligibility/engine.py", "eligibility/read.py"}
    offenders = sorted(
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if path.relative_to(src).as_posix() not in allowed
        and bare.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == []


@needs_a_real_cap
def test_current_verdicts_reads_more_ids_than_the_bound_parameter_cap(
    db: Engine, catalog, seeded: tuple[int, int]
) -> None:
    """read.py's deterministic read — the site the RANKER hits, whose failure kills the run.

    Reached from `top_cmd` via `rank_open_postings`; it binds the list TWICE (its own
    posting_versions lookup and the `current_evaluations` call inside it), so both have to
    chunk for this to pass.
    """
    posting_id, version_id = seeded
    facts = Facts(highest_degree="none")
    _write_deterministic(db, catalog, version_id, facts)
    ident = _identity(catalog, version_id, facts)
    with db.connect() as conn:
        got = current_verdicts(
            conn, _oversized(version_id), ident.profile_hash, ident.rules_hash
        )
    assert got == {posting_id: "ineligible"}


@needs_a_real_cap
def test_current_gate_verdicts_reads_more_ids_than_the_bound_parameter_cap(
    db: Engine, catalog, seeded: tuple[int, int]
) -> None:
    """read.py's final-gate read — the ranker's second corpus-scale bind, on the same list.

    The chunked statement groups by the very column it filters on, so every group lives
    inside one chunk and `max(id) per posting_version` is unchanged by chunking. A verdict
    that went missing here would silently un-hide an `ineligible` posting.
    """
    posting_id, version_id = seeded
    jd = "This position requires an active Top Secret security clearance."
    verdict = OracleVerdict(
        label="1", decision="ineligible", reason="clearance",
        evidence="requires an active Top Secret security clearance", confidence="high",
    )
    with db.begin() as conn:
        final_gate.record_gate_verdict(
            conn, posting_version_id=version_id, jd_text=jd, facts=Facts(),
            policy=Policy(families={}), catalog=catalog, verdict=verdict,
        )
    ident = build_identity(
        posting_version_id=0, facts=Facts(), policy=Policy(families={}), catalog=catalog,
        declared_fields=declared_fields(),
    )
    with db.connect() as conn:
        got = current_gate_verdicts(
            conn, _oversized(version_id), ident.profile_hash, ident.rules_hash
        )
    assert got == {posting_id: "ineligible"}


def _oversized_spanning(first_id: int, last_id: int) -> list[int]:
    """`first_id`, then non-existent padding past the cap, then `last_id`.

    The two real ids land in DIFFERENT chunks on purpose. For a GROUP BY whose key is not the
    chunked column, an implementation that dict-merges per-chunk counts instead of ADDING them
    raises nothing and simply returns the last chunk's count. Placement is the only thing that
    catches that, so this builder exists separately from `_oversized`.
    """
    start = max(first_id, last_id) + 1
    padding = list(range(start, start + VAR_LIMIT))
    return [first_id, *padding, last_id]


@pytest.fixture()
def two_evaluations(db: Engine, catalog) -> tuple[int, int]:
    """Two evaluation ids over two postings that share a (rule_id, disposition)."""
    now = utcnow()
    eval_ids: list[int] = []
    with db.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-two", source="user", watched=True,
        )).inserted_primary_key[0])
        for n in (1, 2):
            jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
            pid = int(conn.execute(insert(postings).values(
                company_id=cid, job_id=jid, provider_posting_id=f"pp-{n}", title="Eng",
                normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
                consecutive_missing=0, content_hash=f"hh{n}", body_text=JD,
            )).inserted_primary_key[0])
            vid = int(conn.execute(insert(posting_versions).values(
                posting_id=pid, content_hash=f"hh{n}", body_text=JD,
                captured_at=now, run_id=None, capture_reason="new",
            )).inserted_primary_key[0])
            eval_ids.append(vid)
    facts = Facts(highest_degree="none")
    return (
        _write_deterministic(db, catalog, eval_ids[0], facts),
        _write_deterministic(db, catalog, eval_ids[1], facts),
    )


@needs_a_real_cap
def test_count_requirement_dispositions_sums_across_more_ids_than_the_cap(
    db: Engine, two_evaluations: tuple[int, int]
) -> None:
    """The funnel's abstain report, reached at `funnel_writer.py:165` on EVERY run.

    It runs immediately after the chunked evaluation read and binds one id per open posting —
    33,429 of them today — so chunking `current_evaluations` alone leaves the funnel dying
    here instead, one query later. Unlike the reads above this is an AGGREGATE whose GROUP BY
    key is not the chunked column, so the per-chunk counts must be ADDED.
    """
    first, last = two_evaluations
    with db.connect() as conn:
        got = count_requirement_dispositions(conn, _oversized_spanning(first, last))
    # 2, not 1: both evaluations produce the same (rule_id, disposition) and sit in different
    # chunks, so a dict-merge silently drops one while raising nothing.
    assert sum(got.values()) == 2, got
    assert got, "no requirement rows at all — the fixture stopped exercising the aggregate"


@needs_a_real_cap
def test_current_posting_versions_reads_more_posting_ids_than_the_cap(
    db: Engine, seeded: tuple[int, int]
) -> None:
    """`export` feeds this every open posting id UNION every tracked one — 32,771+ today.

    The `posting_ids=None` branch already issues no `IN` list; the explicit-list branch is the
    one `cli/export_cmd.py:89` takes, so `boardwatch export` has been failing since the corpus
    crossed the cap, independently of the run. Chunk-and-merge is exact here: the `~newer`
    EXISTS is correlated per posting and looks at all of that posting's versions regardless of
    the filter, so which chunk a posting falls in cannot change its current version.
    """
    posting_id, version_id = seeded
    with db.connect() as conn:
        got = current_posting_versions(conn, _oversized(posting_id))
    assert set(got) == {posting_id}
    assert got[posting_id].posting_version_id == version_id


# --------------------------------------------------------------------------------------
# The DRAIN path (D-288 review finding b). Everything above is reached on every scheduled
# run; everything below is reached only with `top`'s audit flags open —
# `--include-hard-filter` / `--include-non-swe` / `--include-over-seniority`, which are
# D-277's only drain for a `hidden_hard_filter` holding 59% of the corpus. With them open
# `eligible_ids` was MEASURED at 30,419 against a cap of 32,766: not broken yet, ~2 days of
# headroom at the corpus's ~1,264/day net growth. Same bug class as D-287, one call path
# over, and the only reason it had not fired is that nobody had run the audit that week.
#
# The merge semantics differ per site and getting one wrong RAISES NOTHING — it silently
# returns a short answer. THREE shapes, matching `param_chunks.id_chunks`' contract:
# `dict.update` at the FOUR sites whose result is keyed on the chunked column itself
# (`load_identities`, `job_anchors`, `apply_merges`' re-read, `load_dispositions`);
# CONCATENATE at `load_identity_inputs`, which returns a flat tuple keyed on nothing; and a
# SUMMED `rowcount` at `reopen_jobs`, which returns a scalar rather than a mapping.
# Every test below places two real ids in DIFFERENT chunks, so an implementation that keeps
# only one chunk fails on the missing row rather than passing on the survivor.
# --------------------------------------------------------------------------------------


@pytest.fixture()
def two_postings(db: Engine) -> tuple[int, int, int, int, int]:
    """(survivor_job, job_a, posting_a, job_b, posting_b), created in that id order.

    The survivor job is created FIRST so its id is below both real job ids, and therefore
    outside the padding range `_oversized_spanning` builds above `max(first, last)`. A
    padding id that collided with a real row would make the test agree with itself.
    """
    now = utcnow()
    with db.begin() as conn:
        cid = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-drain", source="user", watched=True,
        )).inserted_primary_key[0])
        survivor = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
        made: list[int] = []
        for n in (1, 2):
            jid = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
            pid = int(conn.execute(insert(postings).values(
                company_id=cid, job_id=jid, provider_posting_id=f"drain-{n}", title="Eng",
                normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
                consecutive_missing=0, content_hash=f"dh{n}", body_text=JD,
            )).inserted_primary_key[0])
            made += [jid, pid]
    return (survivor, made[0], made[1], made[2], made[3])


@needs_a_real_cap
def test_load_identity_inputs_reads_more_posting_ids_than_the_cap(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """`top_cmd.py:421` passes `eligible_ids` straight in — 30,419 with the drain flags open.

    The `posting_ids=None` branch issues no `IN` list and was never broken; this is the
    explicit-list branch. The result is a flat tuple, so the chunks CONCATENATE — a merge
    that overwrote instead of extending would return only the last chunk's rows.
    """
    _, _, posting_a, _, posting_b = two_postings
    with db.connect() as conn:
        got = load_identity_inputs(conn, _oversized_spanning(posting_a, posting_b))
    # A LIST, not a set: cardinality is exactly the property this site's merge rule owns, and
    # a set comparison passes for a merge that returns each row twice as readily as once.
    assert [row.posting_id for row in got] == [posting_a, posting_b]


@needs_a_real_cap
def test_load_identities_reads_more_posting_ids_than_the_cap(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """`top_cmd.py:416`, the dedup read, on the same `eligible_ids` list.

    Rows accumulate across chunks and the dict is built once at the end, rather than merging
    per-chunk dicts: a posting's identities all share its `posting_id`, so a per-chunk
    `dict.update` would be sound here too — but only because chunking splits on that same
    column, and building the dict once removes the need to rely on it.
    """
    _, _, posting_a, _, posting_b = two_postings
    now = utcnow()
    with db.begin() as conn:
        for pid in (posting_a, posting_b):
            write_identities(conn, pid, [PostingIdentity("exact_quad", f"q-{pid}")], now=now)
    with db.connect() as conn:
        got = load_identities(conn, _oversized_spanning(posting_a, posting_b))
    assert set(got) == {posting_a, posting_b}
    assert got[posting_a] == (PostingIdentity("exact_quad", f"q-{posting_a}"),)


@needs_a_real_cap
def test_job_anchors_reads_more_posting_ids_than_the_cap(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """`top_cmd.py:432` — and its answer feeds the ledger read below, so a short result here
    would quietly narrow that one too.

    D-288 finding (a) is why this is on the list at all: D-287's table attributed this site a
    <=950 bound, but that bound belongs to `runner._regroup`'s `member_ids`, not to the
    function. The SECOND caller passes corpus-scaled `eligible_ids`. A bound belongs to a
    caller, never to a site.
    """
    _, job_a, posting_a, job_b, posting_b = two_postings
    with db.connect() as conn:
        got = job_anchors(conn, _oversized_spanning(posting_a, posting_b))
    assert got == {posting_a: job_a, posting_b: job_b}


@needs_a_real_cap
def test_apply_merges_re_reads_more_posting_ids_than_the_cap(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """`apply_merges` re-reads every merge's anchor inside the writing transaction.

    That re-read is the guard which keeps an event out of the append-only trail for an UPDATE
    that would match no rows, so losing a chunk of it does not merely under-merge — it drops
    real merges while reporting success. The padding merges name postings that do not exist,
    which is exactly what a stale plan looks like: they are correctly filtered out, and only
    the two real ones move.
    """
    survivor, job_a, posting_a, job_b, posting_b = two_postings
    stale = [
        JobMerge(posting_id=pid, from_job_id=survivor, to_job_id=survivor)
        for pid in range(max(posting_a, posting_b) + 1, max(posting_a, posting_b) + 1 + VAR_LIMIT)
    ]
    merges = [
        JobMerge(posting_id=posting_a, from_job_id=job_a, to_job_id=survivor),
        *stale,
        JobMerge(posting_id=posting_b, from_job_id=job_b, to_job_id=survivor),
    ]
    with db.begin() as conn:
        moved = apply_merges(conn, merges, identity_kind="exact_quad", now=utcnow())
    assert moved == 2, "a dropped chunk loses a real merge and still reports success"
    with db.connect() as conn:
        assert job_anchors(conn, [posting_a, posting_b]) == {
            posting_a: survivor, posting_b: survivor
        }


@needs_a_real_cap
def test_load_dispositions_reads_more_job_ids_than_the_cap(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """`top_cmd.py:433` reaches this through `live_dispositions`, keyed on `job_anchors`'
    values — so with the drain flags open it binds one job id per eligible posting.

    A short answer here does not raise: it reports a `built` job as un-handled, and the
    ranker re-serves a lead the program already built. That is the exact defect the ledger
    exists to prevent, reintroduced through the read that enforces it.
    """
    _, job_a, _, job_b, _ = two_postings
    now = utcnow()
    with db.begin() as conn:
        for jid in (job_a, job_b):
            record_disposition(
                conn, jid, disposition="built", reason="lead_built",
                policy_version="pv-1", now=now,
            )
    with db.connect() as conn:
        got = load_dispositions(conn, _oversized_spanning(job_a, job_b))
    assert set(got) == {job_a, job_b}


@needs_a_real_cap
def test_reopen_jobs_sums_rowcount_across_more_job_ids_than_the_cap(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """The drain's WRITE side — `ledger reopen`, and `regroup._carry_dispositions`.

    The one site here that is NOT a mapping: it returns a scalar `rowcount`, so the chunks
    must be ADDED. The two rows sit in different chunks on purpose — an implementation that
    returns the last chunk's `rowcount` reports 1 while having correctly reopened 2, and the
    operator reads a drain that under-counts what it drained. Same shape as D-287's
    `abstain_queries` finding, which a `dict.update` would have silently understated.
    """
    _, job_a, _, job_b, _ = two_postings
    now = utcnow()
    with db.begin() as conn:
        for jid in (job_a, job_b):
            record_disposition(
                conn, jid, disposition="built", reason="lead_built",
                policy_version="pv-1", now=now,
            )
    with db.begin() as conn:
        released = reopen_jobs(conn, _oversized_spanning(job_a, job_b), now=now)
    assert released == 2, "per-chunk rowcounts must be summed, not overwritten"
    with db.connect() as conn:
        rows = load_dispositions(conn, [job_a, job_b])
    assert all(row.reopened_at is not None for row in rows.values())


@needs_a_real_cap
def test_a_repeated_id_spanning_two_chunks_is_not_returned_twice(
    db: Engine, two_postings: tuple[int, int, int, int, int]
) -> None:
    """`IN (7, 7)` yields posting 7 once; chunk-then-concatenate would yield it once PER CHUNK.

    The one semantic difference chunking introduces that is not a dropped row but an INVENTED
    one, and it is invisible to every other test here because they all pass distinct ids. It
    reaches the two sites that concatenate or accumulate; the four `dict.update` sites collapse
    duplicates for free, and `reopen_jobs` is protected by its own `reopened_at IS NULL` guard.

    No caller passes a duplicate today — `top_cmd`'s `eligible_ids` comes from a query with at
    most one row per posting — so this pins a precondition rather than fixing a live bug. It is
    worth pinning because the failure is silent: a duplicated `IdentityInputs` row would make
    one posting look like a two-member duplicate group to `resolve_duplicates`.
    """
    _, _, posting_a, _, posting_b = two_postings
    spanning = _oversized_spanning(posting_a, posting_b)
    with db.connect() as conn:
        inputs = load_identity_inputs(conn, [*spanning, posting_a])
        identities = load_identities(conn, [*spanning, posting_a])
    assert [row.posting_id for row in inputs] == [posting_a, posting_b]
    assert set(identities) <= {posting_a, posting_b}


@needs_a_real_cap
def test_the_body_quarantine_drain_sums_rowcount_across_more_held_bodies_than_the_cap(
    db: Engine, seeded: tuple[int, int]
) -> None:
    """The lane-body quarantine's ONLY exit (D-406), and the second scalar-`rowcount` site.

    Unlike `reopen_jobs`, this list is not passed in by a caller — it is built inside the drain
    from the rows it holds — so the id count is bounded by the BUCKET, and the bucket is bounded
    by the corpus. A lane that started serving an aggregator's page text at scale is precisely
    the failure the precondition exists to catch, and at that scale this drain is the only way
    any of those postings is ever judged again. An unchunked `IN` raises `too many SQL
    variables` there; a last-chunk-only sum reports a drain that under-counts what it drained.

    Every held body here carries the EMPLOYER's own text, which is the corrected-catalog
    re-entry condition: the rows were held under a catalog that has since had the marker that
    misjudged them withdrawn, so all of them are releasable in one pass.
    """
    posting_id, _ = seeded
    held = VAR_LIMIT + 1
    now = utcnow()
    with db.begin() as conn:
        conn.execute(
            insert(posting_versions),
            [
                {
                    "posting_id": posting_id, "content_hash": f"qh-{n}",
                    "body_text": "About the role\nWe are hiring a backend engineer.",
                    # DISTINCT and ascending, so the `newer` EXISTS each held row runs is an
                    # index seek on (posting_id, captured_at, id) rather than a scan of every
                    # sibling version. Identical timestamps make this fixture quadratic.
                    "captured_at": now + timedelta(seconds=n), "capture_reason": "revised",
                }
                for n in range(held)
            ],
        )
        version_ids = list(
            conn.execute(
                select(posting_versions.c.id).where(
                    posting_versions.c.content_hash.like("qh-%")
                )
            ).scalars()
        )
        assert len(version_ids) == held
        conn.execute(
            insert(quarantined_bodies),
            [
                {
                    "posting_version_id": vid, "posting_id": posting_id,
                    "markers_json": ["apply on employer site", "sign in join now"],
                    "catalog_version": 1, "quarantined_at": now, "reopened_at": None,
                }
                for vid in version_ids
            ],
        )

    with db.begin() as conn:
        released = drain_quarantine(conn, now=now)

    assert released == held, "per-chunk rowcounts must be summed, not overwritten"
    with db.connect() as conn:
        assert live_quarantine(conn) == {}
