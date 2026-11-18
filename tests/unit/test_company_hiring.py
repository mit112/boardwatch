"""T308: company hiring view.

Expected values are worked out by hand from the fixture below, not from the query.

NOW is 2026-11-17 12:00 UTC and the window is 56 days, so it opens 2026-09-22 12:00 UTC (8 weeks).
Identity is ("PH", "RH"); "eligible" is a deterministic `eligible` evaluation of the posting's
NEWEST version under that identity and the current engine version.

  Acme (unwatched)  new in window: a1 (eligible), a2 (eligible), a3 (uncertain), a4 (ineligible),
                    a6 (eligible; event "2026-09-22 08:00:00-05:00" = 13:00 UTC, INSIDE the window
                    although its text sorts before the cutoff text), a7 (eligible only on a version
                    since replaced), a8 (eligible under another profile), a9 (eligible under another
                    engine version), a10 (uncertain, two `new` events), a11 (eligible, CLOSED).
                    a5 and a5b (uncertain) have events "2026-09-22 14:00:00+05:00" and "...15:00..."
                    = 09:00 and 10:00 UTC: OUTSIDE, though their text sorts after the cutoff text.
                    => new 10, eligible 4 (a1 a2 a6 a11).
                    Open eligible now: a1 a2 a6; the newest by id is a6 (a11 is newer but closed).
  Birch (watched)   b1 (eligible), b2, b3 (uncertain)            => new 3, eligible 1.
  Cedar (unwatched) twelve postings, c1 eligible and CLOSED      => new 12, eligible 1.
  Dune              one eligible posting first seen 60 days ago  => not in the window, not listed.

Order: eligible desc, then new desc, then company id: Acme (4), Cedar (1, new 12), Birch (1, new 3).
Applications: a1's job applied, then a second attempt withdrawn; a2's job rejected then applied
(one applied job); a3's job interested; a4's job withdrawn, but a NEWER Birch posting shares that
job, so Birch is credited with the withdrawal.
  => Acme applied 2 withdrawn 1; Birch applied 0 withdrawn 1; Cedar 0 and 0.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert, text

from boardwatch.eligibility.engine import engine_version
from boardwatch.eligibility.read import current_verdicts
from boardwatch.store import company_hiring_queries as chq
from boardwatch.store.company_hiring_queries import company_hiring
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import current_posting_version_ids
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    jobs,
    posting_versions,
    postings,
    runs,
)

NOW = datetime(2026, 11, 17, 12, 0, 0)
IDENTITY = ("PH", "RH")


@pytest.fixture(autouse=True)
def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    chq._memo = None


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(conn: Connection, name: str, *, watched: bool) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name, provider="ashby", slug=name.lower(), source="user", watched=watched
            )
        ).inserted_primary_key[0]
    )


def _run(conn: Connection) -> int:
    return int(conn.execute(insert(runs).values(started_at=NOW, finished_at=NOW)).inserted_primary_key[0])


def _event(conn: Connection, posting: int, stamp: str, run: int, kind: str = "new") -> None:
    conn.execute(
        text(
            "INSERT INTO posting_events (posting_id, kind, run_id, created_at)"
            " VALUES (:p, :k, :r, :s)"
        ),
        {"p": posting, "k": kind, "r": run, "s": stamp},
    )


def _version(conn: Connection, posting: int, captured: datetime, tag: str) -> int:
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting,
                content_hash=f"h-{posting}-{tag}",
                body_text="body",
                captured_at=captured,
                capture_reason="new",
            )
        ).inserted_primary_key[0]
    )


def _judge(
    conn: Connection,
    version: int,
    verdict: str,
    *,
    profile: str = IDENTITY[0],
    engine_ver: str | None = None,
) -> None:
    input_id = int(
        conn.execute(
            insert(eligibility_inputs).values(
                posting_version_id=version,
                profile_hash=profile,
                rules_hash=IDENTITY[1],
                profile_snapshot_json={},
                rules_snapshot_json={},
                input_fingerprint=f"fp-{version}-{profile}-{engine_ver}-{verdict}",
                created_at=NOW,
            )
        ).inserted_primary_key[0]
    )
    conn.execute(
        insert(eligibility_evaluations).values(
            input_id=input_id,
            engine_kind="deterministic",
            engine_version=engine_ver or engine_version(),
            verdict=verdict,
            created_at=NOW,
        )
    )


def _posting(
    conn: Connection,
    company: int,
    key: str,
    *,
    new: str | None,
    run: int,
    verdict: str | None = None,
    status: str = "open",
    job: int | None = None,
    seen: datetime = NOW,
    profile: str = IDENTITY[0],
    engine_ver: str | None = None,
) -> tuple[int, int]:
    if job is None:
        job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting = int(
        conn.execute(
            insert(postings).values(
                company_id=company,
                job_id=job,
                provider_posting_id=key,
                title=f"Role {key}",
                normalized_title=f"role {key}",
                remote_policy="remote",
                first_seen_at=seen,
                last_seen_at=NOW,
                status=status,
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text="body",
            )
        ).inserted_primary_key[0]
    )
    if new is not None:
        _event(conn, posting, new, run)
    version = _version(conn, posting, NOW - timedelta(days=30), "v1")
    if verdict is not None:
        _judge(conn, version, verdict, profile=profile, engine_ver=engine_ver)
    return posting, job


def _day(n: int) -> str:
    return (NOW - timedelta(days=n)).isoformat(sep=" ")


def _app(conn: Connection, job: int, attempt: int, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO applications (job_id, attempt_no, status, created_at, updated_at)"
            " VALUES (:j, :n, :s, :t, :t)"
        ),
        {"j": job, "n": attempt, "s": status, "t": NOW.isoformat(sep=" ")},
    )


@pytest.fixture()
def seeded(engine: Engine) -> dict[str, int]:
    ids: dict[str, int] = {}
    with engine.begin() as conn:
        run = _run(conn)
        acme = _company(conn, "Acme", watched=False)
        birch = _company(conn, "Birch", watched=True)
        cedar = _company(conn, "Cedar", watched=False)
        dune = _company(conn, "Dune", watched=False)
        ids.update(acme=acme, birch=birch, cedar=cedar, dune=dune)

        def add(key: str, company: int, **kw: object) -> tuple[int, int]:
            posting, job = _posting(conn, company, key, run=run, **kw)  # type: ignore[arg-type]
            ids[key] = posting
            ids[f"job-{key}"] = job
            return posting, job

        add("a1", acme, new=_day(1), verdict="eligible", seen=NOW - timedelta(days=1))
        add("a2", acme, new=_day(10), verdict="eligible")
        add("a3", acme, new=_day(20), verdict="uncertain")
        add("a4", acme, new=_day(30), verdict="ineligible")
        add("a5", acme, new="2026-09-22 14:00:00+05:00", verdict="uncertain")
        add("a5b", acme, new="2026-09-22 15:00:00+05:00", verdict="uncertain")
        add(
            "a6", acme, new="2026-09-22 08:00:00-05:00", verdict="eligible",
            seen=NOW - timedelta(days=3),
        )
        a7, _ = add("a7", acme, new=_day(5), verdict="eligible")
        # A newer version with no evaluation: a7's eligible verdict is about a body it no longer has.
        _version(conn, a7, NOW - timedelta(days=2), "v2")
        add("a8", acme, new=_day(6), verdict="eligible", profile="OTHER")
        add("a9", acme, new=_day(7), verdict="eligible", engine_ver="0+old")
        a10, _ = add("a10", acme, new=_day(8), verdict="uncertain")
        _event(conn, a10, _day(9), run)
        add("a11", acme, new=_day(4), verdict="eligible", status="closed")

        add("b1", birch, new=_day(2), verdict="eligible")
        add("b2", birch, new=_day(3), verdict="uncertain")
        add("b3", birch, new=_day(4), verdict="uncertain")

        for n in range(1, 13):
            add(
                f"c{n}", cedar, new=_day(n),
                verdict="eligible" if n == 1 else "ineligible",
                status="closed" if n == 1 else "open",
            )
        add("d1", dune, new=_day(60), verdict="eligible")

        # Birch's NEWER posting shares a4's job, so the job's withdrawal is credited to Birch.
        add("b-twin", birch, new=None, job=ids["job-a4"])
        _app(conn, ids["job-a1"], 1, "applied")
        _app(conn, ids["job-a1"], 2, "withdrawn")
        _app(conn, ids["job-a2"], 1, "rejected")
        _app(conn, ids["job-a2"], 2, "applied")
        _app(conn, ids["job-a3"], 1, "interested")
        _app(conn, ids["job-a4"], 1, "withdrawn")
    return ids


def _hiring(engine: Engine, identity: tuple[str, str] | None = IDENTITY) -> dict[str, object]:
    with engine.connect() as conn:
        return company_hiring(conn, identity, NOW)


def test_counts_are_worked_out_by_hand(engine: Engine, seeded: dict[str, int]) -> None:
    got = _hiring(engine)
    assert got["window_days"] == 56
    assert got["eligible_known"] is True
    assert (got["new"], got["eligible"], got["companies"]) == (25, 6, 3)
    rows = {r["company"]: r for r in got["rows"]}  # type: ignore[attr-defined]
    acme, birch, cedar = rows["Acme"], rows["Birch"], rows["Cedar"]
    assert (acme["new"], acme["eligible"]) == (10, 4)
    assert (birch["new"], birch["eligible"]) == (3, 1)
    assert (cedar["new"], cedar["eligible"]) == (12, 1)
    assert (acme["new_per_week"], acme["eligible_per_week"]) == (1.25, 0.5)
    assert (cedar["new_per_week"], cedar["eligible_per_week"]) == (1.5, 0.12)
    assert "Dune" not in rows


def test_sorted_by_eligible_then_new_then_id(engine: Engine, seeded: dict[str, int]) -> None:
    # Birch has the lower id and Cedar has more new postings: only the tie-break on `new` puts
    # Cedar before Birch, and only sorting on eligible puts Acme (10 new) before Cedar (12 new).
    assert [r["company"] for r in _hiring(engine)["rows"]] == ["Acme", "Cedar", "Birch"]  # type: ignore[attr-defined]


def test_window_edge_uses_the_instant_not_the_text(engine: Engine, seeded: dict[str, int]) -> None:
    got = _hiring(engine)
    acme = got["rows"][0]  # type: ignore[index]
    # a6 is inside (13:00 UTC) though its text sorts before the cutoff text; a5 and a5b are
    # outside though their text sorts after it. 10 new includes a6 and excludes both; a text
    # compare would read 11 new (a5, a5b in, a6 out) and 3 eligible.
    assert acme["new"] == 10
    assert acme["eligible"] == 4


def test_only_the_newest_version_under_the_live_identity_counts(
    engine: Engine, seeded: dict[str, int]
) -> None:
    # Acme's 4: a1 a2 a6 a11. Not a7 (replaced version), a8 (other profile), a9 (other engine).
    with engine.connect() as conn:
        expected = {seeded[k] for k in ("a1", "a2", "a6", "a11", "b1", "c1", "d1")}
        agg = chq._aggregate(conn, IDENTITY, NOW)
        assert agg.eligible == expected
        # The long way round, per posting version, must agree with the reverse pass.
        every = sorted(v for k, v in seeded.items() if re.fullmatch(r"[abcd]\d+b?|b-twin", k))
        newest = current_posting_version_ids(conn, every)
        verdicts = current_verdicts(conn, list(newest.values()), *IDENTITY)
        assert {p for p, v in verdicts.items() if v == "eligible"} == expected


def test_applied_and_withdrawn_count_jobs_once_for_the_newest_postings_company(
    engine: Engine, seeded: dict[str, int]
) -> None:
    rows = {r["company"]: r for r in _hiring(engine)["rows"]}  # type: ignore[attr-defined]
    assert (rows["Acme"]["applied"], rows["Acme"]["withdrawn"]) == (2, 1)
    assert (rows["Birch"]["applied"], rows["Birch"]["withdrawn"]) == (0, 1)
    assert (rows["Cedar"]["applied"], rows["Cedar"]["withdrawn"]) == (0, 0)


def test_newest_open_eligible_role(engine: Engine, seeded: dict[str, int]) -> None:
    rows = {r["company"]: r for r in _hiring(engine)["rows"]}  # type: ignore[attr-defined]
    # a11 is newer than a6 and eligible, but closed.
    assert rows["Acme"]["newest_open_eligible"] == {
        "posting_id": seeded["a6"],
        "title": "Role a6",
        "age_days": 3.0,
    }
    assert rows["Birch"]["newest_open_eligible"]["posting_id"] == seeded["b1"]
    # Cedar's one eligible posting is closed: eligible 1, no open eligible role.
    assert rows["Cedar"]["newest_open_eligible"] is None


def test_watched_rows_reach_past_the_cap(
    engine: Engine, seeded: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chq, "ROWS_SHOWN", 2)
    got = _hiring(engine)
    assert [r["company"] for r in got["rows"]] == ["Acme", "Cedar"]  # type: ignore[attr-defined]
    # Birch is watched and falls outside the top two overall: it is still in the watched list.
    watched = got["watched_rows"]  # type: ignore[assignment]
    assert [r["company"] for r in watched] == ["Birch"]
    assert watched[0]["watched"] is True
    assert watched[0]["eligible"] == 1


def test_no_profile_means_unknown_not_zero(engine: Engine, seeded: dict[str, int]) -> None:
    got = _hiring(engine, None)
    assert got["eligible_known"] is False
    assert got["eligible"] is None
    rows = got["rows"]  # type: ignore[assignment]
    # Ranked by new postings, since eligible is unknown.
    assert [r["company"] for r in rows] == ["Cedar", "Acme", "Birch"]
    assert all(r["eligible"] is None and r["eligible_per_week"] is None for r in rows)
    assert all(r["newest_open_eligible"] is None for r in rows)
    assert rows[0]["new"] == 12


def test_uncertain_is_not_folded_into_either_side(engine: Engine, seeded: dict[str, int]) -> None:
    # Birch: 3 new, 1 eligible, 2 uncertain. The payload carries no ineligible count to fold into.
    birch = next(r for r in _hiring(engine)["rows"] if r["company"] == "Birch")  # type: ignore[attr-defined]
    assert birch["eligible"] == 1
    assert "ineligible" not in birch


def test_a_company_with_nothing_new_in_the_window_is_not_listed(engine: Engine) -> None:
    with engine.begin() as conn:
        run = _run(conn)
        quiet = _company(conn, "Quiet", watched=True)
        _posting(conn, quiet, "q1", new=_day(100), run=run, verdict="eligible")
    got = _hiring(engine)
    assert (got["new"], got["companies"], got["rows"], got["watched_rows"]) == (0, 0, [], [])


def test_the_aggregate_is_memoised_until_a_new_event(
    engine: Engine, seeded: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    real = chq._aggregate

    def counted(*args: object) -> object:
        nonlocal calls
        calls += 1
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(chq, "_aggregate", counted)
    _hiring(engine)
    _hiring(engine)
    assert calls == 1
    _hiring(engine, ("PH2", "RH"))  # another profile is another answer
    assert calls == 2
    with engine.begin() as conn:
        _event(conn, seeded["b2"], _day(1), 1)
    _hiring(engine, ("PH2", "RH"))
    assert calls == 3
    # A later day moves the window, so it is not served from the old answer.
    with engine.connect() as conn:
        company_hiring(conn, ("PH2", "RH"), NOW + timedelta(days=1))
    assert calls == 4


def test_names_and_watched_are_read_fresh_not_memoised(engine: Engine, seeded: dict[str, int]) -> None:
    assert next(r for r in _hiring(engine)["rows"] if r["company_id"] == seeded["acme"])["watched"] is False  # type: ignore[attr-defined]
    with engine.begin() as conn:
        conn.execute(text("UPDATE companies SET name = 'Acme Corp', watched = 1 WHERE id = :i"), {"i": seeded["acme"]})
    acme = next(r for r in _hiring(engine)["rows"] if r["company_id"] == seeded["acme"])  # type: ignore[attr-defined]
    assert (acme["company"], acme["watched"]) == ("Acme Corp", True)


def test_payload_is_json_serialisable(engine: Engine, seeded: dict[str, int]) -> None:
    json.dumps(_hiring(engine))
