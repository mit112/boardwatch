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
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.core.clock import utcnow
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
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import companies, jobs, posting_versions, postings

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


@pytest.fixture(autouse=True)
def _cap_is_worth_testing() -> None:
    if VAR_LIMIT > 200_000:
        pytest.skip(f"SQLite here allows {VAR_LIMIT} parameters; the list would be absurd")


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
    offenders = sorted(
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if path.name not in {"engine.py", "read.py"}
        and bare.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == []


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
