"""T303: the near-miss list. Expected values are worked out by hand from the fixture below.

Blocking families here: `experience_years` (E) and `work_auth` (W). `degree` is NOT a blocker.
The gate vetoes a title containing "Senior" (`excluded_title`) and the location "London"
(`non_us_location`). Every posting is Acme's, `Software Engineer` unless said, and the body is
`BODY`, so a quoted span is `BODY[start:end]`.

  id  what                                                           in the list?
  p1  verdict ineligible; E unmet "2 years" (required)               near-miss E
  p2  ineligible; E unmet "3 years"                                   near-miss E
  p3  ineligible; W unmet                                             near-miss W
  p4  ineligible; E unmet AND W unmet (two blocking rows)             no: not ONE unmet
  p5  ineligible; E unmet + W UNKNOWN (a blocking abstain)            with_abstain, E; never a near-miss
  p6  ineligible; E unmet but PREFERRED, W unmet required             near-miss W (preferred blocks nothing)
  p7  ineligible; degree unmet (not a blocker) + E unmet              near-miss E (a non-blocker is not a 2nd)
  p8  "Senior ..." ineligible; E unmet                                gated out: excluded_title
  p9  ["London"] ineligible; W unmet                                  gated out: non_us_location
  p10 uncertain; W unknown only                                       not blocked
  p11 CLOSED posting; E unmet                                         not open
  p12 two versions: the OLD one is ineligible with E unmet; the NEW   not current
      one is eligible
  p13 ineligible; E unmet, but under ANOTHER profile hash             not the current identity
  p14 "Senior ..." ineligible; E unmet + W unknown                    gated out: excluded_title (the
                                                                      gate precedes the abstain split)
  p15 ineligible; E unmet "2 years" written TWICE (two unmet rows)    no: not ONE unmet
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext, compute_near_miss_report
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.near_miss_queries import near_misses
from boardwatch.store.tables import (
    companies,
    eligibility_evaluations,
    eligibility_inputs,
    eligibility_requirements,
    jobs,
    posting_versions,
    postings,
)
from tests.conftest import write_bundled_role_taxonomy
from tests.unit.test_web_server import (
    BLOCKING_FACTS,
    BLOCKING_POLICY,
    JD_ELIGIBLE,
    JD_INELIGIBLE,
    _deliver,
    call,
    serving,
)

NOW = datetime(2026, 11, 17, 12, 0, 0)
PROFILE, RULES, ENGINE = "profile-now", "rules-now", "det:test"
BLOCKING = frozenset({"experience_years", "work_auth"})
E_MIN = "experience_years:scoped_years_minimum"
W_NO = "work_auth:no_sponsorship_offered"
BODY = "We need 2 years of experience. We need 3 years of experience. No sponsorship offered."
TWO_YEARS = "We need 2 years of experience."
THREE_YEARS = "We need 3 years of experience."
NO_SPONSOR = "No sponsorship offered."


def _span(quote: str) -> list[int]:
    start = BODY.index(quote)
    return [start, start + len(quote)]


@pytest.fixture(autouse=True)
def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


Row = tuple[str, str, str, str, str]  # rule_id, requiredness, disposition, text, quoted span


def _req(
    rule: str, disposition: str, quote: str, *, requiredness: str = "required", text: str = ""
) -> Row:
    return (rule, requiredness, disposition, text or quote, quote)


def _evaluate(
    conn: Connection,
    version_id: int,
    verdict: str,
    rows: list[Row],
    *,
    profile: str = PROFILE,
) -> None:
    input_id = int(
        conn.execute(
            insert(eligibility_inputs).values(
                posting_version_id=version_id,
                profile_hash=profile,
                rules_hash=RULES,
                input_fingerprint=f"fp-{version_id}-{profile}",
                created_at=NOW,
            )
        ).inserted_primary_key[0]
    )
    evaluation = int(
        conn.execute(
            insert(eligibility_evaluations).values(
                input_id=input_id,
                engine_kind="deterministic",
                engine_version=ENGINE,
                verdict=verdict,
                created_at=NOW,
            )
        ).inserted_primary_key[0]
    )
    for ordinal, (rule, requiredness, disposition, text, quote) in enumerate(rows):
        conn.execute(
            insert(eligibility_requirements).values(
                evaluation_id=evaluation,
                ordinal=ordinal,
                rule_id=rule,
                requiredness=requiredness,
                requirement_text=text,
                jd_locator_json={"field": "body_text", "span": _span(quote)},
                disposition=disposition,
            )
        )


def _posting(
    conn: Connection,
    company: int,
    key: str,
    verdict: str,
    rows: list[Row],
    *,
    title: str = "Software Engineer",
    locations: list[str] | None = None,
    status: str = "open",
    profile: str = PROFILE,
) -> int:
    job = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting = int(
        conn.execute(
            insert(postings).values(
                company_id=company,
                job_id=job,
                provider_posting_id=key,
                title=title,
                normalized_title=title.casefold(),
                locations_json=locations if locations is not None else ["Boston, MA"],
                remote_policy="remote",
                first_seen_at=NOW,
                last_seen_at=NOW,
                status=status,
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text=BODY,
            )
        ).inserted_primary_key[0]
    )
    version = _version(conn, posting, NOW)
    _evaluate(conn, version, verdict, rows, profile=profile)
    return posting


def _version(conn: Connection, posting: int, at: datetime) -> int:
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting,
                content_hash=f"v-{posting}-{at.isoformat()}",
                body_text=BODY,
                captured_at=at,
                capture_reason="new",
            )
        ).inserted_primary_key[0]
    )


def _gate(title: str, locations: list[str] | tuple[str, ...], remote: str) -> str | None:
    if "Senior" in title:
        return "excluded_title"
    if list(locations) == ["London"]:
        return "non_us_location"
    return None


def _build(conn: Connection) -> dict[str, int]:
    acme = int(
        conn.execute(
            insert(companies).values(
                name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
            )
        ).inserted_primary_key[0]
    )
    p: dict[str, int] = {}
    p["p1"] = _posting(
        conn, acme, "p1", "ineligible", [_req(E_MIN, "unmet", TWO_YEARS, text="2 years asked")]
    )
    p["p2"] = _posting(
        conn, acme, "p2", "ineligible", [_req(E_MIN, "unmet", THREE_YEARS, text="3 years asked")]
    )
    p["p3"] = _posting(conn, acme, "p3", "ineligible", [_req(W_NO, "unmet", NO_SPONSOR)])
    p["p4"] = _posting(
        conn,
        acme,
        "p4",
        "ineligible",
        [_req(E_MIN, "unmet", TWO_YEARS), _req(W_NO, "unmet", NO_SPONSOR)],
    )
    p["p5"] = _posting(
        conn,
        acme,
        "p5",
        "ineligible",
        [_req(E_MIN, "unmet", TWO_YEARS), _req(W_NO, "unknown", NO_SPONSOR)],
    )
    p["p6"] = _posting(
        conn,
        acme,
        "p6",
        "ineligible",
        [_req(E_MIN, "unmet", TWO_YEARS, requiredness="preferred"), _req(W_NO, "unmet", NO_SPONSOR)],
    )
    p["p7"] = _posting(
        conn,
        acme,
        "p7",
        "ineligible",
        [_req("degree:masters", "unmet", NO_SPONSOR), _req(E_MIN, "unmet", TWO_YEARS, text="2 years asked")],
    )
    p["p8"] = _posting(
        conn, acme, "p8", "ineligible", [_req(E_MIN, "unmet", TWO_YEARS)], title="Senior Engineer"
    )
    p["p9"] = _posting(
        conn, acme, "p9", "ineligible", [_req(W_NO, "unmet", NO_SPONSOR)], locations=["London"]
    )
    p["p10"] = _posting(conn, acme, "p10", "uncertain", [_req(W_NO, "unknown", NO_SPONSOR)])
    p["p11"] = _posting(
        conn, acme, "p11", "ineligible", [_req(E_MIN, "unmet", TWO_YEARS)], status="closed"
    )
    p["p12"] = _posting(conn, acme, "p12", "ineligible", [_req(E_MIN, "unmet", TWO_YEARS)])
    newer = _version(conn, p["p12"], datetime(2026, 11, 18))
    _evaluate(conn, newer, "eligible", [])
    p["p13"] = _posting(
        conn, acme, "p13", "ineligible", [_req(E_MIN, "unmet", TWO_YEARS)], profile="profile-old"
    )
    p["p14"] = _posting(
        conn,
        acme,
        "p14",
        "ineligible",
        [_req(E_MIN, "unmet", TWO_YEARS), _req(W_NO, "unknown", NO_SPONSOR)],
        title="Senior Engineer",
    )
    p["p15"] = _posting(
        conn,
        acme,
        "p15",
        "ineligible",
        [_req(E_MIN, "unmet", TWO_YEARS), _req(E_MIN, "unmet", TWO_YEARS)],
    )
    return p


def _call(conn: Connection, **over: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "profile_hash": PROFILE,
        "rules_hash": RULES,
        "engine_kind": "deterministic",
        "engine_version": ENGINE,
        "blocking": BLOCKING,
        "gate": _gate,
    }
    args.update(over)
    return near_misses(conn, **args)


def test_counts_each_stage_apart_and_never_folds_the_abstain_in(engine: Engine) -> None:
    with engine.begin() as conn:
        _build(conn)
        got = _call(conn)

    # Blocked: ineligible, open, current version, current identity: p1-p9, p14, p15.
    assert got["blocked"] == 11
    # Exactly one blocking unmet row, before the gates: p1 p2 p3 p5 p6 p7 p8 p9 p14.
    assert got["one_unmet"] == 9
    # Through the gates, no blocking abstain: p1 p2 p3 p6 p7.
    assert got["near_misses"] == 5
    # One blocking unmet plus a blocking abstain, through the gates: p5. Not in near_misses.
    assert got["with_abstain"] == 1
    assert got["gated_out"] == [
        {"clause": "excluded_title", "count": 2},  # p8, p14
        {"clause": "non_us_location", "count": 1},  # p9
    ]


def test_groups_by_rule_with_the_requirement_texts_and_the_abstains_beside(engine: Engine) -> None:
    with engine.begin() as conn:
        _build(conn)
        got = _call(conn)

    by_rule = {r["rule_id"]: r for r in got["rules"]}
    assert [r["rule_id"] for r in got["rules"]] == [E_MIN, W_NO]  # largest first
    e, w = by_rule[E_MIN], by_rule[W_NO]
    assert (e["count"], e["with_abstain"]) == (3, 1)  # p1 p2 p7; p5 apart
    assert (w["count"], w["with_abstain"]) == (2, 0)  # p3 p6
    assert e["requirements"] == [
        {"text": "2 years asked", "count": 2},  # p1, p7
        {"text": "3 years asked", "count": 1},  # p2
    ]


def test_samples_are_the_newest_postings_with_the_quoted_span(engine: Engine) -> None:
    with engine.begin() as conn:
        p = _build(conn)
        got = _call(conn)

    e = next(r for r in got["rules"] if r["rule_id"] == E_MIN)
    assert [s["posting_id"] for s in e["samples"]] == [p["p7"], p["p2"], p["p1"]]
    assert [s["quote"] for s in e["samples"]] == [TWO_YEARS, THREE_YEARS, TWO_YEARS]
    assert {s["company"] for s in e["samples"]} == {"Acme"}
    w = next(r for r in got["rules"] if r["rule_id"] == W_NO)
    assert [(s["posting_id"], s["quote"]) for s in w["samples"]] == [
        (p["p6"], NO_SPONSOR),
        (p["p3"], NO_SPONSOR),
    ]


def test_a_rule_with_only_abstaining_postings_is_listed_with_a_zero_count(engine: Engine) -> None:
    with engine.begin() as conn:
        acme = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        _posting(
            conn,
            acme,
            "a1",
            "ineligible",
            [_req(E_MIN, "unmet", TWO_YEARS), _req(W_NO, "unknown", NO_SPONSOR)],
        )
        got = _call(conn)
    assert (got["near_misses"], got["with_abstain"]) == (0, 1)
    (rule,) = got["rules"]
    assert (rule["rule_id"], rule["count"], rule["with_abstain"], rule["samples"]) == (
        E_MIN,
        0,
        1,
        [],
    )


def test_a_policy_that_demotes_a_family_stops_it_blocking(engine: Engine) -> None:
    """With `work_auth` not a blocker, p4 (E and W unmet) has ONE blocking unmet row, and p5's
    W abstain stops being a blocking abstain: it becomes a clean E near-miss."""
    with engine.begin() as conn:
        p = _build(conn)
        got = _call(conn, blocking=frozenset({"experience_years"}))
    # p3 and p6 hold no blocking unmet row now, so work_auth drops out of the list altogether.
    (e,) = got["rules"]
    assert e["rule_id"] == E_MIN
    # p1 p2 p4 p5 p7. p15 states E twice: still two unmet rows. p8 p14 are gated.
    assert (e["count"], e["with_abstain"]) == (5, 0)
    assert [s["posting_id"] for s in e["samples"]] == [p["p7"], p["p5"], p["p4"]]


def test_a_company_rename_shows_in_the_next_report(engine: Engine) -> None:
    with engine.begin() as conn:
        _build(conn)
    with engine.connect() as conn:
        assert _call(conn)["rules"][0]["samples"][0]["company"] == "Acme"
    with engine.begin() as conn:
        conn.execute(companies.update().values(name="Acme Renamed"))
    with engine.connect() as conn:
        assert _call(conn)["rules"][0]["samples"][0]["company"] == "Acme Renamed"


def _ctx(tmp_path: Path) -> ApiContext:
    (tmp_path / "out").mkdir()
    (tmp_path / "queue").mkdir()
    return ApiContext(
        settings=load_settings(),
        out_root=(tmp_path / "out").resolve(),
        queue_root=(tmp_path / "queue").resolve(),
        owner_name="Example Owner",
        platform="darwin",
    )


def test_the_route_runs_the_pipelines_own_gates_over_a_real_evaluation(
    tmp_path: Path, engine: Engine
) -> None:
    """End to end through `/api/near-misses`: real evaluations from the real engine, the real
    profile identity, `hard_filter_verdict` and the role gate. The location veto holds even though
    `location_filter_mode` is its default (`soft`), because the lane holds a lead outside the
    target countries either way."""
    write_bundled_role_taxonomy(tmp_path / "config")
    ctx = _ctx(tmp_path)
    blocked: dict[str, Any] = {
        "body": JD_INELIGIBLE,
        "facts": BLOCKING_FACTS,
        "policy": BLOCKING_POLICY,
    }
    with engine.begin() as conn:
        fine, _ = _deliver(conn, "fine", **blocked)
        _deliver(conn, "abroad", locations=["London, United Kingdom"], **blocked)
        _deliver(conn, "nurse", title="Registered Nurse Practitioner", **blocked)
        _deliver(conn, "open", body=JD_ELIGIBLE, facts=BLOCKING_FACTS, policy=BLOCKING_POLICY)
    with engine.connect() as conn:
        report = compute_near_miss_report(conn, ctx.settings)
    # The run stores it beside its funnel; the route only reads the newest stored report.
    day = ctx.out_root / "2026-11-18"
    day.mkdir()
    (day / "near-miss-41.json").write_text(json.dumps(report), encoding="utf-8")
    with serving(ctx) as live:
        assert call(live, "/api/near-misses").status == 401
        got = call(live, "/api/near-misses", bearer=live.token).json()

    assert (got["available"], got["run_id"]) == (True, 41)
    assert got["profile"] is True
    # Three ineligible postings, each holding the one work_auth row; the eligible one is not blocked.
    assert (got["blocked"], got["one_unmet"]) == (3, 3)
    assert (got["near_misses"], got["with_abstain"]) == (1, 0)
    assert got["gated_out"] == [
        {"clause": "non_us_location", "count": 1},
        {"clause": "out_of_field", "count": 1},
    ]
    (rule,) = got["rules"]
    assert rule["rule_id"].startswith("work_auth:")
    assert rule["count"] == 1
    (sample,) = rule["samples"]
    assert sample["posting_id"] == fine
    assert sample["quote"] and sample["quote"] in JD_INELIGIBLE
    assert sample["company"] == "Acme fine"


def test_the_route_serves_the_newest_runs_report_and_says_when_there_is_none(
    tmp_path: Path,
) -> None:
    """Run 9's report is in an older day folder, run 12's in a newer one and run 10's at the top
    level: run 12 is served, by run id, never by file order. A malformed name is ignored."""
    ctx = _ctx(tmp_path)
    with serving(ctx) as live:
        assert call(live, "/api/near-misses", bearer=live.token).json() == {"available": False}
    (ctx.out_root / "2026-11-01").mkdir()
    (ctx.out_root / "2026-11-02").mkdir()
    (ctx.out_root / "2026-11-01" / "near-miss-9.json").write_text('{"near_misses": 9}')
    (ctx.out_root / "2026-11-02" / "near-miss-12.json").write_text('{"near_misses": 12}')
    (ctx.out_root / "near-miss-10.json").write_text('{"near_misses": 10}')
    (ctx.out_root / "near-miss-x.json").write_text('{"near_misses": 99}')
    with serving(ctx) as live:
        got = call(live, "/api/near-misses", bearer=live.token).json()
    assert got == {"available": True, "run_id": 12, "near_misses": 12}


def test_the_route_says_there_is_no_profile_rather_than_inventing_zeros(
    tmp_path: Path, engine: Engine
) -> None:
    ctx = _ctx(tmp_path)
    with engine.connect() as conn:
        got = compute_near_miss_report(conn, ctx.settings)
    assert got["profile"] is False
    assert (got["near_misses"], got["rules"]) == (0, [])
