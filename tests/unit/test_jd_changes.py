"""T309: postings whose JD changed after a résumé was built or after an application was sent.

Expected values are worked out by hand from the fixture below, not from the query. Instants are
written as TEXT so some carry a UTC offset; in each trap the text order and the instant order of
the two stamps DISAGREE, so a text comparison gets the row wrong.

Versions (v = posting_versions row, `R` = capture_reason 'revised'). Times are UTC unless shown.
  P1  v1 new 11-01 12:00 | v2 R 11-05 14:00+02:00 (= 12:00Z) | v3 R 11-07 12:00
      built from v1.                                  -> stale, 2 revisions, latest v3
  P2  v1 new 11-01 12:00 | v2 R 11-01 13:30+02:00 (= 11:30Z, BEFORE the build; text says after)
      built from v1.                                  -> not stale
  P3  v1 new 11-01 12:00 | v2 R 11-01 11:30-02:00 (= 13:30Z, AFTER the build; text says before)
      built from v1.                                  -> stale, 1 revision, latest v2
  P4  v1 new 11-01 | v2 R 11-03; built from v1 AND from v2 -> rebuilt after the change, not stale
  P5  v1 new 11-01 | v2 R 11-03, no résumé built          -> in neither built count
  P6  v1 new 11-01 | v2 backfill_original 11-09; built from v1 -> a backfill is not a change
Applications (all against the posting's version v1):
  A1  P1, sent 11-06 12:00          -> v3 only (v2 was already live): 1 revision, sent v2, latest v3
  A2  P2, sent 11-01 13:00          -> the 11:30Z revision is before it (text says after): not changed
  A3  P3, sent 11-01 12:45          -> the 13:30Z revision is after it (text says before): changed
  A4  P1, import, submitted == created (unknown date)       -> excluded_imports, never compared
  A5  P1, no posting version                                -> no_posting_version
  A6  P1, import with a real date 11-02 12:00               -> kept: 2 revisions, sent v1
  A7  P1, no submitted_at                                   -> not checked
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text

from boardwatch.store import jd_change_queries
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.jd_change_queries import jd_changes
from boardwatch.store.run_funnel_queries import TAILORED_KIND
from boardwatch.store.tables import (
    application_events,
    artifacts,
    companies,
    jobs,
    postings,
)

D0 = datetime(2026, 11, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _posting(conn: Connection, company: int, key: str) -> int:
    job = int(conn.execute(insert(jobs).values(created_at=D0)).inserted_primary_key[0])
    return int(
        conn.execute(
            insert(postings).values(
                company_id=company,
                job_id=job,
                provider_posting_id=key,
                title=f"Engineer {key}",
                normalized_title="engineer",
                url=f"https://boards.test/{key}",
                remote_policy="remote",
                first_seen_at=D0,
                last_seen_at=D0,
                status="open",
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )


def _version(conn: Connection, posting: int, at: str, reason: str) -> int:
    """A posting version whose capture time is written as text (so it may carry an offset)."""
    return int(
        conn.execute(
            text(
                "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at,"
                " capture_reason) VALUES (:p, :h, 'body', :at, :r)"
            ),
            {"p": posting, "h": f"h-{posting}-{at}", "at": at, "r": reason},
        ).lastrowid
    )


def _build(conn: Connection, version: int, built_at: datetime = D0) -> None:
    conn.execute(
        insert(artifacts).values(
            posting_version_id=version, kind=TAILORED_KIND, uri="file:///r.pdf", created_at=built_at
        )
    )


def _app(
    conn: Connection,
    job: int,
    version: int | None,
    submitted: str | None,
    *,
    attempt: int,
    created: str = "2026-11-01 00:00:00",
    imported: bool = False,
) -> int:
    app = int(
        conn.execute(
            text(
                "INSERT INTO applications (job_id, posting_version_id, attempt_no, status,"
                " created_at, updated_at, submitted_at)"
                " VALUES (:j, :v, :n, 'applied', :c, :c, :s)"
            ),
            {"j": job, "v": version, "n": attempt, "c": created, "s": submitted},
        ).lastrowid
    )
    conn.execute(
        insert(application_events).values(
            application_id=app,
            event_type="created",
            to_status="applied",
            occurred_at=D0,
            recorded_at=D0,
            source="import" if imported else "user",
        )
    )
    return app


def _job_of(conn: Connection, posting: int) -> int:
    return int(
        conn.execute(text("SELECT job_id FROM postings WHERE id = :p"), {"p": posting}).scalar_one()
    )


def _seed(conn: Connection) -> dict[str, int]:
    acme = int(
        conn.execute(
            insert(companies).values(
                name="Acme", provider="ashby", slug="acme", source="user", watched=True
            )
        ).inserted_primary_key[0]
    )
    ids: dict[str, int] = {}
    p1, p2, p3, p4, p5, p6 = (_posting(conn, acme, f"p{n}") for n in range(1, 7))

    v1 = _version(conn, p1, "2026-11-01 12:00:00", "new")
    v2 = _version(conn, p1, "2026-11-05 14:00:00+02:00", "revised")
    v3 = _version(conn, p1, "2026-11-07 12:00:00", "revised")
    _build(conn, v1)
    ids.update(p1=p1, v1=v1, v2=v2, v3=v3)

    q1 = _version(conn, p2, "2026-11-01 12:00:00", "new")
    _version(conn, p2, "2026-11-01 13:30:00+02:00", "revised")
    _build(conn, q1)
    ids.update(p2=p2, q1=q1)

    r1 = _version(conn, p3, "2026-11-01 12:00:00", "new")
    r2 = _version(conn, p3, "2026-11-01 11:30:00-02:00", "revised")
    _build(conn, r1)
    ids.update(p3=p3, r1=r1, r2=r2)

    s1 = _version(conn, p4, "2026-11-01 12:00:00", "new")
    s2 = _version(conn, p4, "2026-11-03 12:00:00", "revised")
    _build(conn, s1)
    _build(conn, s2)

    _version(conn, p5, "2026-11-01 12:00:00", "new")
    _version(conn, p5, "2026-11-03 12:00:00", "revised")

    t1 = _version(conn, p6, "2026-11-01 12:00:00", "new")
    _version(conn, p6, "2026-11-09 12:00:00", "backfill_original")
    _build(conn, t1)

    ids["a1"] = _app(conn, _job_of(conn, p1), v1, "2026-11-06 12:00:00", attempt=1)
    ids["a2"] = _app(conn, _job_of(conn, p2), q1, "2026-11-01 13:00:00", attempt=1)
    ids["a3"] = _app(conn, _job_of(conn, p3), r1, "2026-11-01 12:45:00", attempt=1)
    same = "2026-11-08 09:00:00"
    ids["a4"] = _app(
        conn, _job_of(conn, p1), v1, same, attempt=2, created=same, imported=True
    )
    ids["a5"] = _app(conn, _job_of(conn, p1), None, "2026-11-02 12:00:00", attempt=3)
    ids["a6"] = _app(
        conn, _job_of(conn, p1), v1, "2026-11-02 12:00:00", attempt=4, imported=True
    )
    ids["a7"] = _app(conn, _job_of(conn, p1), v1, None, attempt=5)
    return ids


def test_built_lists_only_postings_revised_after_their_newest_build(engine: Engine) -> None:
    with engine.begin() as conn:
        ids = _seed(conn)
        built = jd_changes(conn)["built"]
    # Postings with a build: P1, P2, P3, P4, P6. Stale: P1 and P3 only.
    assert built["checked"] == 5
    assert built["stale"] == 2
    # Newest change first: P1's latest revision is 11-07 12:00Z, P3's is 11-01 13:30Z.
    assert [r["posting_id"] for r in built["rows"]] == [ids["p1"], ids["p3"]]
    p1, p3 = built["rows"]
    assert (p1["built_version_id"], p1["revisions"], p1["latest_version_id"]) == (
        ids["v1"],
        2,
        ids["v3"],
    )
    assert p1["latest_revised_at"] == "2026-11-07T12:00:00+00:00"
    assert p1["built_at"] == "2026-11-01T12:00:00+00:00"
    assert (p1["company"], p1["title"], p1["url"]) == (
        "Acme",
        "Engineer p1",
        "https://boards.test/p1",
    )
    # P3's revision (11:30 at -02:00) is 13:30Z, after the 12:00Z build though its text sorts before.
    assert (p3["built_version_id"], p3["revisions"], p3["latest_version_id"]) == (
        ids["r1"],
        1,
        ids["r2"],
    )
    assert p3["latest_revised_at"] == "2026-11-01T13:30:00+00:00"


def test_applied_compares_instants_counts_imports_apart_and_names_the_live_version(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        ids = _seed(conn)
        applied = jd_changes(conn)["applied"]
    # Checked: A1, A2, A3, A6 (dated, with a version). A4 is an undated import, A5 has no version,
    # A7 has no submission. Changed: A1, A3, A6.
    assert applied["checked"] == 4
    assert applied["changed"] == 3
    assert applied["excluded_imports"] == 1
    assert applied["no_posting_version"] == 1
    # A6 and A1 share the latest revision (v3), so the later application id comes first; A3's
    # revision is 11-01 and sorts last.
    assert [r["application_id"] for r in applied["rows"]] == [ids["a6"], ids["a1"], ids["a3"]]
    a6, a1, a3 = applied["rows"]
    # A6 was sent 11-02: v1 was live, and both revisions came after.
    assert (a6["sent_version_id"], a6["revisions"], a6["latest_version_id"]) == (
        ids["v1"],
        2,
        ids["v3"],
    )
    # A1 was sent 11-06 12:00: v2 (11-05) was already live, so only v3 is a change since.
    assert (a1["sent_version_id"], a1["revisions"], a1["latest_version_id"]) == (
        ids["v2"],
        1,
        ids["v3"],
    )
    assert a1["submitted_at"] == "2026-11-06T12:00:00+00:00"
    assert a1["status"] == "applied"
    assert (a3["sent_version_id"], a3["revisions"]) == (ids["r1"], 1)


def test_the_row_list_is_capped_but_the_totals_are_not(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jd_change_queries, "ROW_LIMIT", 1)
    with engine.begin() as conn:
        ids = _seed(conn)
        out = jd_changes(conn)
    assert out["limit"] == 1
    assert out["built"]["stale"] == 2
    assert [r["posting_id"] for r in out["built"]["rows"]] == [ids["p1"]]
    assert out["applied"]["changed"] == 3
    assert len(out["applied"]["rows"]) == 1


def test_an_empty_store_reports_zeros(engine: Engine) -> None:
    with engine.begin() as conn:
        out = jd_changes(conn)
    assert out["built"] == {"checked": 0, "stale": 0, "rows": []}
    assert out["applied"] == {
        "checked": 0,
        "changed": 0,
        "excluded_imports": 0,
        "no_posting_version": 0,
        "rows": [],
    }
