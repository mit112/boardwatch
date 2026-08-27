"""The read-only queue queries (design §6.1-§6.4).

A real schema on `tmp_path` with rows inserted directly — never the live store. Every test that
asserts an ABSENCE carries a control that asserts the presence it is the absence of: `[]` from a
function that returned `[]` for an unrelated reason is green for the wrong reason, and the
exclusion tests (applied, skipped) are exactly the shape where that happens.

Three of these defend a distinction the type system alone cannot:

- `posted_days is None` and `!= 0`. `0` is a measurement ("posted today"); the board publishing
  no date is not.
- `pdf_uri is None` with no exception when `meta_json` carries no `pdf_uri` key.
- `jd_body is None`, not `""`, when there is no current version.

`BOARDWATCH_CONFIG_DIR` is forced onto `tmp_path` because `delivered_unapplied` resolves the
eligibility identity through `load_settings()`. Without it the verdict assertions would be
computed against whatever `rules.yaml` override sits in the developer's own config directory.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text

from boardwatch.core.settings import load_settings
from boardwatch.eligibility.audit import AuditRequirement
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store import delivery_queries
from boardwatch.store.applications import create_application
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.delivery_queries import RequirementView, delivered_unapplied, queue_detail
from boardwatch.store.param_chunks import ID_CHUNK_SIZE
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import artifacts, companies, jobs, posting_versions, postings, runs

NOW = datetime(2026, 8, 26, 12, 0, 0)

# A JD the bundled catalog has several families to say something about, so a written evaluation
# produces real requirement rows rather than an empty tuple.
JD = (
    "Bachelor's degree in Computer Science required. Must be a US citizen and hold an active "
    "security clearance. 8+ years of professional experience required."
)

# What `scan/apply.py` does to `postings.body_text` on a revision: it rewrites it in place. Any
# read that took the JD from there would return this instead of the frozen version body.
REWRITTEN = "this posting body was rewritten in place by a later scan"


@pytest.fixture(autouse=True)
def _scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


# --------------------------------------------------------------------------------------- seeding


def _run(conn: Connection, started_at: datetime = NOW) -> int:
    return int(
        conn.execute(
            insert(runs).values(started_at=started_at, boards_attempted=0)
        ).inserted_primary_key[0]
    )


def _company(
    conn: Connection,
    slug: str,
    *,
    name: str = "Acme",
    tags: list[str] | None = None,
    source: str = "user",
    watched: bool = True,
) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name, provider="greenhouse", slug=slug, source=source,
                watched=watched, tags_json=tags,
            )
        ).inserted_primary_key[0]
    )


def _job(conn: Connection) -> int:
    return int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])


def _posting(
    conn: Connection,
    *,
    company_id: int,
    job_id: int,
    key: str,
    status: str = "open",
    posted_at: datetime | None = NOW - timedelta(days=4),
    locations: list[str] | None = None,
    remote_policy: str = "remote",
    url: str | None = "https://boards.test/apply",
    body: str = JD,
) -> int:
    return int(
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=key,
                title="Software Engineer", normalized_title="software engineer", url=url,
                locations_json=["Boston, MA"] if locations is None else locations,
                remote_policy=remote_policy, posted_at=posted_at, first_seen_at=NOW,
                last_seen_at=NOW, status=status,
                closed_at=NOW if status == "closed" else None,
                consecutive_missing=0, content_hash=f"hash-{key}", body_text=body,
            )
        ).inserted_primary_key[0]
    )


def _version(
    conn: Connection, *, posting_id: int, body: str = JD, captured_at: datetime = NOW
) -> int:
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"v-{posting_id}", body_text=body,
                captured_at=captured_at, run_id=None, capture_reason="new",
            )
        ).inserted_primary_key[0]
    )


def _artifact(
    conn: Connection,
    *,
    version_id: int,
    run_id: int | None = None,
    created_at: datetime = NOW,
    meta: dict[str, object] | None = None,
    uri: str = "/out/2026-08-26/acme/tailored-1.typ",
) -> int:
    return int(
        conn.execute(
            insert(artifacts).values(
                posting_version_id=version_id, kind="resume_tailored", uri=uri,
                generator="boardwatch.tailor", media_type="text/x-tex",
                meta_json={"pdf_uri": "/out/2026-08-26/acme/tailored-1.pdf"}
                if meta is None
                else meta,
                created_at=created_at, run_id=run_id,
            )
        ).inserted_primary_key[0]
    )


def _deliver(
    conn: Connection,
    key: str,
    *,
    job_id: int | None = None,
    status: str = "open",
    posted_at: datetime | None = NOW - timedelta(days=4),
    locations: list[str] | None = None,
    remote_policy: str = "remote",
    tags: list[str] | None = None,
    meta: dict[str, object] | None = None,
    delivered_at: datetime = NOW,
    run_id: int | None = None,
    posting_body: str = JD,
    version_body: str = JD,
    source: str = "user",
    watched: bool = True,
) -> tuple[int, int]:
    """One delivered lead — company, job, posting, frozen version, tailored artifact.

    Returns `(posting_id, job_id)`. Pass an existing `job_id` to make two postings siblings of
    one canonical job, which is the population deduplication has to collapse.
    """
    company_id = _company(conn, f"acme-{key}", tags=tags, source=source, watched=watched)
    job = _job(conn) if job_id is None else job_id
    posting_id = _posting(
        conn, company_id=company_id, job_id=job, key=key, status=status,
        posted_at=posted_at, locations=locations, remote_policy=remote_policy,
        body=posting_body,
    )
    version_id = _version(conn, posting_id=posting_id, body=version_body)
    _artifact(
        conn, version_id=version_id, run_id=run_id, created_at=delivered_at,
        meta=meta, uri=f"/out/2026-08-26/{key}/tailored-{posting_id}.typ",
    )
    return posting_id, job


def _write_evaluation(conn: Connection, posting_id: int, version_id: int, body: str) -> str:
    """A real deterministic evaluation under the live profile's identity. Returns its verdict.

    Goes through `evaluate` + `write_evaluation` rather than hand-inserting the ledger rows so
    the identity really is the one `current_identity` recomputes from the stored profile — a
    hand-written `profile_hash` would make the read pass against any implementation that also
    hand-wrote the same constant.
    """
    catalog = load_rules(load_settings().config_dir)
    result = evaluate(body, Facts(), Policy(), catalog)
    identity = build_identity(
        posting_version_id=version_id, facts=Facts(), policy=Policy(), catalog=catalog,
        declared_fields=declared_fields(),
    )
    write_evaluation(
        conn, posting_version_id=version_id, identity=identity, result=result
    )
    return result.verdict


def _save_profile(conn: Connection) -> None:
    save_profile(
        conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
        locations=["Boston, MA"], remote_only=False, skills=["python"],
        taxonomy_version="v1", resume_max_pages=1,
    )


# ------------------------------------------------------------------------------- deduplication


def test_two_postings_of_one_job_collapse_to_the_most_recent_delivery(engine: Engine) -> None:
    """Dedup keys on the canonical job, not the posting (design §6.1: 227 postings in 100
    multi-posting groups live). An implementation deduping by posting returns two rows."""
    with engine.begin() as conn:
        older, job = _deliver(conn, "older", delivered_at=NOW - timedelta(days=2))
        newer, _ = _deliver(conn, "newer", job_id=job, delivered_at=NOW)
    with engine.connect() as conn:
        rows = delivered_unapplied(conn, skipped=set())
    assert [(row.posting_id, row.job_id) for row in rows] == [(newer, job)]
    assert older not in {row.posting_id for row in rows}


def test_an_applied_job_removes_every_sibling_posting(engine: Engine) -> None:
    """`applications` keys on the job, so applying to one posting must retire its siblings.

    The control run (before the application) is what makes the empty result mean something.
    """
    with engine.begin() as conn:
        _, job = _deliver(conn, "one", delivered_at=NOW - timedelta(days=1))
        second, _ = _deliver(conn, "two", job_id=job, delivered_at=NOW)
        _deliver(conn, "other", delivered_at=NOW)
    with engine.connect() as conn:
        before = delivered_unapplied(conn, skipped=set())
    assert second in {row.posting_id for row in before}

    with engine.begin() as conn:
        create_application(conn, job_id=job, status="applied", source="test")
    with engine.connect() as conn:
        after = delivered_unapplied(conn, skipped=set())
    assert job not in {row.job_id for row in after}
    assert len(after) == len(before) - 1


def test_a_skipped_job_is_absent(engine: Engine) -> None:
    with engine.begin() as conn:
        _, job = _deliver(conn, "skipme")
        _deliver(conn, "keepme")
    with engine.connect() as conn:
        assert len(delivered_unapplied(conn, skipped=set())) == 2
        rows = delivered_unapplied(conn, skipped={job})
    assert [row.job_id for row in rows] != []
    assert job not in {row.job_id for row in rows}


def test_two_runs_delivering_the_same_posting_yield_one_row_with_the_later_run(
    engine: Engine,
) -> None:
    """One posting, two tailored artifacts from two runs. The later delivery wins.

    Fails against an implementation that keeps the first row it sees, and against one that
    returns a row per artifact.
    """
    with engine.begin() as conn:
        company_id = _company(conn, "acme")
        job = _job(conn)
        posting_id = _posting(conn, company_id=company_id, job_id=job, key="p1")
        version_id = _version(conn, posting_id=posting_id)
        first_run = _run(conn, NOW - timedelta(days=1))
        later_run = _run(conn, NOW)
        _artifact(
            conn, version_id=version_id, run_id=first_run,
            created_at=NOW - timedelta(days=1), uri="/out/old/tailored-1.typ",
        )
        _artifact(conn, version_id=version_id, run_id=later_run, created_at=NOW)
    with engine.connect() as conn:
        rows = delivered_unapplied(conn, skipped=set())
        detail = queue_detail(conn, posting_id)
    assert len(rows) == 1
    assert rows[0].delivered_run_id == later_run
    assert rows[0].tex_uri == "/out/2026-08-26/acme/tailored-1.typ"
    # The detail resolves the same delivery, so the PDF the pane offers is the one the row
    # names. Fails against an implementation that takes the posting's FIRST tailored artifact.
    assert detail is not None
    assert detail.row.delivered_run_id == later_run


# ------------------------------------------------------------------------------------- the row


def test_a_posting_with_no_posted_at_has_no_age_and_not_zero(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`—`, never `0d`. A dated control sits beside it so the None is not simply "never set".

    The clock is FROZEN to `NOW`, because `posted_days` is the one field here derived from the
    wall clock rather than read back from the row. Seeding `NOW - 4 days` and asserting `4`
    against a live `utcnow()` was not a flake but a dated time bomb: it held only while real
    UTC stayed under five days from 2026-08-22 12:00, went permanently red at 2026-08-27 12:00
    UTC, and drifted a further day every day after. Patch the CONSUMER binding -- the module
    under test imported `utcnow` by value, so patching `core.clock` would not be seen.
    """
    monkeypatch.setattr(delivery_queries, "utcnow", lambda: NOW)
    with engine.begin() as conn:
        undated, _ = _deliver(conn, "undated", posted_at=None)
        dated, _ = _deliver(conn, "dated", posted_at=NOW - timedelta(days=4))
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[undated].posted_days is None
    assert by_posting[undated].posted_days != 0
    assert by_posting[dated].posted_days == 4
    # first_seen is a DIFFERENT quantity and is returned whether or not posted_at exists.
    assert by_posting[undated].first_seen == NOW
    assert by_posting[dated].first_seen == NOW


def test_a_closed_posting_with_a_tailored_resume_is_still_returned(engine: Engine) -> None:
    """35 such postings exist live. Labelling is the design; draining is deferred (§12.1)."""
    with engine.begin() as conn:
        closed, _ = _deliver(conn, "closed", status="closed")
        open_id, _ = _deliver(conn, "open")
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[closed].status == "closed"
    assert by_posting[open_id].status == "open"


def test_an_open_posting_nobody_enumerates_reads_as_unverifiable(engine: Engine) -> None:
    """`open` on an unwatched company is an assertion the store cannot make (D-314).

    Nothing enumerates that board, so the posting was never measured as still listed; it was
    merely never contradicted. The watched control sits beside it so `unverifiable` cannot be
    green for an implementation that relabels every row.
    """
    with engine.begin() as conn:
        unwatched, _ = _deliver(conn, "lane", source="lane", watched=False)
        watched, _ = _deliver(conn, "watched", source="registry", watched=True)
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[unwatched].status == "unverifiable"
    assert by_posting[watched].status == "open"


def test_an_unwatched_company_that_is_no_lane_is_unverifiable_too(engine: Engine) -> None:
    """The discriminating case: 274 of the 722 affected rows live on `source='user'` companies,
    and 23 `source='lane'` postings sit on companies that ARE watched (measured 2026-08-27).

    A predicate keyed on `source='lane'` is therefore wrong in both directions, so both
    directions are asserted here: an unwatched non-lane company is unverifiable, and a lane
    posting on a watched company is a genuine `open`.
    """
    with engine.begin() as conn:
        user_unwatched, _ = _deliver(conn, "user-off", source="user", watched=False)
        lane_watched, _ = _deliver(conn, "lane-on", source="lane", watched=True)
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[user_unwatched].status == "unverifiable"
    assert by_posting[lane_watched].status == "open"


def test_a_closed_posting_is_never_relabelled_unverifiable(engine: Engine) -> None:
    """`closed` is only ever written by `_process_missing` off a `complete` snapshot, so it is
    always a real measurement — including on the 51 closed postings whose company has since
    been unwatched. Only the `open` claim is unsupported.
    """
    with engine.begin() as conn:
        closed_unwatched, _ = _deliver(
            conn, "closed-off", status="closed", source="user", watched=False
        )
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[closed_unwatched].status == "closed"


def test_queue_detail_reports_the_same_unverifiable_status_as_the_row(engine: Engine) -> None:
    """The pane and the list read one derivation. Two would eventually disagree."""
    with engine.begin() as conn:
        unwatched, _ = _deliver(conn, "lane", source="lane", watched=False)
        watched, _ = _deliver(conn, "watched", source="registry", watched=True)
    with engine.connect() as conn:
        unverifiable = queue_detail(conn, unwatched)
        verifiable = queue_detail(conn, watched)
    assert unverifiable is not None and unverifiable.row.status == "unverifiable"
    assert verifiable is not None and verifiable.row.status == "open"


def test_meta_without_a_pdf_uri_yields_none_and_does_not_raise(engine: Engine) -> None:
    """The `pdf_uri` key is legacy (D-058) and load-bearing; its ABSENCE is not an error."""
    with engine.begin() as conn:
        without, _ = _deliver(conn, "nopdf", meta={"typst_pdf_built": False})
        with_pdf, _ = _deliver(conn, "pdf", meta={"pdf_uri": "/out/x.pdf"})
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[without].pdf_uri is None
    assert by_posting[with_pdf].pdf_uri == "/out/x.pdf"


def test_an_unknown_remote_policy_reads_as_absent(engine: Engine) -> None:
    """`postings.remote_policy` is NOT NULL and defaults to 'unknown', which is the column
    saying nothing is known. No reader should have to know that sentinel."""
    with engine.begin() as conn:
        unknown, _ = _deliver(conn, "unknown", remote_policy="unknown")
        remote, _ = _deliver(conn, "remote", remote_policy="remote")
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[unknown].remote_policy is None
    assert by_posting[remote].remote_policy == "remote"


def test_target_flag_is_tri_state(engine: Engine) -> None:
    """No tags at all is None, never False: "we know nothing" and "we know it is not a target"
    are different claims, and the column has no writer in `src/` yet."""
    with engine.begin() as conn:
        untagged, _ = _deliver(conn, "untagged", tags=None)
        empty, _ = _deliver(conn, "empty", tags=[])
        tagged, _ = _deliver(conn, "tagged", tags=["target", "sponsor"])
        other, _ = _deliver(conn, "other", tags=["watchlist"])
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[untagged].target_flag is None
    # An empty list is the same claim as a NULL column, and neither is False.
    assert by_posting[empty].target_flag is None
    assert by_posting[tagged].target_flag is True
    assert by_posting[other].target_flag is False


def test_the_row_carries_the_apply_url_company_and_location(engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, "fields")
    with engine.connect() as conn:
        (row,) = delivered_unapplied(conn, skipped=set())
    assert row.posting_id == posting_id
    assert row.company == "Acme"
    assert row.title == "Software Engineer"
    assert row.location == "Boston, MA"
    assert row.apply_url == "https://boards.test/apply"


def test_a_posting_naming_no_place_has_no_location(engine: Engine) -> None:
    """`None`, not `""`. An empty string renders as a value; an empty column is a gap, and the
    design's own rule is that a field which reads as a value it does not have is worse than an
    absent one."""
    with engine.begin() as conn:
        nowhere, _ = _deliver(conn, "nowhere", locations=[])
        somewhere, _ = _deliver(conn, "somewhere")
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[nowhere].location is None
    assert by_posting[nowhere].location != ""
    assert by_posting[somewhere].location == "Boston, MA"


# -------------------------------------------------------------------------------- the verdict


def test_a_posting_with_no_eligibility_evaluation_has_no_verdict(engine: Engine) -> None:
    with engine.begin() as conn:
        _save_profile(conn)
        _deliver(conn, "unjudged")
    with engine.connect() as conn:
        (row,) = delivered_unapplied(conn, skipped=set())
    assert row.verdict is None


def test_the_current_identitys_verdict_is_returned(engine: Engine) -> None:
    """The discriminator for the whole verdict column: an implementation that never wires it
    reports None here as well, and cannot tell this test from the one above."""
    with engine.begin() as conn:
        _save_profile(conn)
        judged, _ = _deliver(conn, "judged")
        version_id = int(
            conn.execute(
                posting_versions.select().where(posting_versions.c.posting_id == judged)
            ).one().id
        )
        expected = _write_evaluation(conn, judged, version_id, JD)
        _deliver(conn, "unjudged")
    assert expected in {"eligible", "ineligible", "uncertain"}
    with engine.connect() as conn:
        by_posting = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert by_posting[judged].verdict == expected
    assert len([row for row in by_posting.values() if row.verdict is None]) == 1


# --------------------------------------------------------------------------------- the detail


def test_queue_detail_reads_the_frozen_version_body_never_the_posting_body(
    engine: Engine,
) -> None:
    """`scan/apply.py` rewrites `postings.body_text` in place, so a span stored against the
    frozen version garbles the instant it is sliced from the posting. Fails against an
    implementation reading `postings.body_text`."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, "frozen", posting_body=REWRITTEN, version_body=JD)
    with engine.connect() as conn:
        detail = queue_detail(conn, posting_id)
    assert detail is not None
    assert detail.jd_body == JD
    assert detail.jd_body != REWRITTEN


def test_queue_detail_without_a_current_version_reports_an_absent_body(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`jd_body is None`, not `""`, and no exception.

    Forced rather than seeded on purpose: a tailored artifact reaches its posting only THROUGH
    `posting_versions`, and `postings_job_required_*` plus `PRAGMA foreign_keys=ON` make a
    delivered posting with no version row unreachable through well-formed data. The branch is
    still real — the two existing readers disagree about it (`audit.py` tolerates,
    `projection/posting.py` raises) — so the dependency is stubbed to produce the state.
    Fails against `versions[posting_id]` (KeyError) and against `... or ""`.
    """
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, "noversion")
    monkeypatch.setattr(
        delivery_queries, "current_posting_versions", lambda _conn, _ids: {}
    )
    with engine.connect() as conn:
        detail = queue_detail(conn, posting_id)
    assert detail is not None
    assert detail.jd_body is None
    assert detail.jd_body != ""
    assert detail.row.posting_id == posting_id


def test_queue_detail_requirements_come_from_the_stored_audit(engine: Engine) -> None:
    """Reused from `load_audit`, spans and all — every quote is a slice of the frozen body."""
    with engine.begin() as conn:
        _save_profile(conn)
        posting_id, _ = _deliver(conn, "audited")
        version_id = int(
            conn.execute(
                posting_versions.select().where(posting_versions.c.posting_id == posting_id)
            ).one().id
        )
        expected = _write_evaluation(conn, posting_id, version_id, JD)
    with engine.connect() as conn:
        detail = queue_detail(conn, posting_id)
    assert detail is not None
    assert detail.row.verdict == expected
    assert detail.requirements
    assert all(isinstance(req, AuditRequirement) for req in detail.requirements)
    assert all(req.quote in JD for req in detail.requirements)
    # Not every rule quotes a span, but a JD naming a degree, a clearance and a year count
    # must produce at least one. Without this, all-empty quotes would satisfy `in JD`.
    assert any(req.quote for req in detail.requirements)


def test_queue_detail_names_the_board_that_produced_the_lead(engine: Engine) -> None:
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, "board")
    with engine.connect() as conn:
        detail = queue_detail(conn, posting_id)
    assert detail is not None
    assert detail.board_target == "greenhouse:acme-board"


def test_queue_detail_is_none_for_a_posting_that_was_never_delivered(engine: Engine) -> None:
    with engine.begin() as conn:
        company_id = _company(conn, "acme")
        job = _job(conn)
        posting_id = _posting(conn, company_id=company_id, job_id=job, key="p1")
        _version(conn, posting_id=posting_id)
    with engine.connect() as conn:
        assert queue_detail(conn, posting_id) is None
        assert queue_detail(conn, 999_999) is None


def test_queue_detail_still_answers_for_an_applied_lead(engine: Engine) -> None:
    """The queue offers an undo on "mark applied", so the detail of a lead that just left the
    list has to stay readable. `delivered_unapplied`'s exclusions are not `queue_detail`'s."""
    with engine.begin() as conn:
        posting_id, job = _deliver(conn, "applied")
        create_application(conn, job_id=job, status="applied", source="test")
    with engine.connect() as conn:
        assert delivered_unapplied(conn, skipped=set()) == []
        detail = queue_detail(conn, posting_id)
    assert detail is not None
    assert detail.row.posting_id == posting_id


# ------------------------------------------------------------------------------------ hygiene


def test_a_delivered_posting_with_no_canonical_job_is_dropped(engine: Engine) -> None:
    """`postings.job_id` NULL means the lead can be neither retired by an application nor
    marked applied, so it would sit in the queue forever. It is dropped, not shown.

    Reaching it needs the `postings_job_required_insert` trigger out of the way — which is
    exactly the population the guard is for: rows that predate `p0_jobs_anchor` installing it,
    or a hand-edited store. `PRAGMA foreign_keys` does not gate triggers, so the trigger is
    dropped for this one store and the control lead proves the query still returns anything.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER postings_job_required_insert"))
        company_id = _company(conn, "orphan")
        orphan = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=None, provider_posting_id="orphan",
                    title="Software Engineer", normalized_title="software engineer",
                    url=None, locations_json=["Boston, MA"], remote_policy="remote",
                    posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW, status="open",
                    consecutive_missing=0, content_hash="orphan", body_text=JD,
                )
            ).inserted_primary_key[0]
        )
        _artifact(conn, version_id=_version(conn, posting_id=orphan), uri="/out/orphan.typ")
        kept, _ = _deliver(conn, "kept")
    with engine.connect() as conn:
        rows = delivered_unapplied(conn, skipped=set())
        assert queue_detail(conn, orphan) is None
    assert [row.posting_id for row in rows] == [kept]


def test_the_seeded_rows_leave_no_dangling_foreign_key(engine: Engine) -> None:
    """`PRAGMA foreign_key_check` is empty. Alembic runs with FKs off, so a fixture can seed a
    dangling row and every later assertion would be about a state the scanner cannot produce."""
    with engine.begin() as conn:
        _save_profile(conn)
        _, job = _deliver(conn, "a", run_id=_run(conn))
        _deliver(conn, "b", job_id=job)
        _deliver(conn, "c", status="closed", posted_at=None)
        create_application(conn, job_id=job, status="applied", source="test")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_the_verdict_of_a_lead_beyond_the_first_chunk_still_arrives(engine: Engine) -> None:
    """More delivered leads than `ID_CHUNK_SIZE`, with the only evaluated one placed LAST.

    `current_posting_versions` and `current_verdicts` both split their id list into 500-id
    statements and merge the pieces, and a merge that keeps only one chunk raises nothing — it
    silently loses the verdict. Rows tie on `delivered_at` here, so the order is artifact id
    descending and the FIRST lead seeded is the last one in the list, i.e. in the final chunk.
    A row-count assertion alone would pass against a dropped chunk, so the assertion is the
    verdict of that specific lead.
    """
    with engine.begin() as conn:
        _save_profile(conn)
        judged, _ = _deliver(conn, "judged")
        version_id = int(
            conn.execute(
                posting_versions.select().where(posting_versions.c.posting_id == judged)
            ).one().id
        )
        expected = _write_evaluation(conn, judged, version_id, JD)
        for index in range(ID_CHUNK_SIZE + 50):
            _deliver(conn, f"bulk-{index}")
    with engine.connect() as conn:
        rows = delivered_unapplied(conn, skipped=set())
    assert len(rows) == ID_CHUNK_SIZE + 51
    assert rows[-1].posting_id == judged
    assert rows[-1].verdict == expected


def test_the_module_binds_no_id_list_of_its_own() -> None:
    """No `.in_()` anywhere in the module.

    The delivered set is reached by a JOIN outward from `artifacts`, never by collecting posting
    ids and binding them — the shape that hit SQLite's 32,766 bound-parameter cap at six call
    sites on 2026-08-23 and killed every scheduled run from that day on. The two id lists this
    module does pass go to `current_posting_versions` and `current_verdicts`, which chunk
    internally; an `.in_()` written here would have no such protection.
    """
    source = Path(delivery_queries.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "in_" not in calls


def test_requirement_view_is_the_audits_own_requirement_type() -> None:
    """Locked in the plan as `RequirementView`; reusing `AuditRequirement` is what keeps the
    span slicing in one place instead of copying half of it."""
    assert RequirementView is AuditRequirement


def test_the_module_contains_no_write() -> None:
    """Read-only is a property of the SOURCE, not of the tests that happen to be written.

    A `select`-only module cannot be proven read-only by exercising it: the write would be on
    a path no test took. So the source is parsed and the three mutating constructors are
    forbidden outright, by import and by call.
    """
    source = Path(delivery_queries.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"insert", "update", "delete", "text", "exec_driver_sql"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            offenders = {alias.name for alias in node.names} & forbidden
            assert not offenders, f"delivery_queries imports {sorted(offenders)}"
        if isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            assert name not in forbidden, f"delivery_queries calls {name}()"
