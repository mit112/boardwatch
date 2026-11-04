"""Sponsorship history as a near-tie-break on rank, never a verdict.

Active only when the profile row declares `needs_sponsorship` true AND the tenant's
`sponsors.json` has records. Scores are floats on [0, 1] and an exact tie almost never fires, so
the tie is the 0.01 band `round(total, 2)`. Every expected order below is written out by hand
from the scores in `SCORES`; none is produced by calling the sort.

Fixture (score, flagged by a record):  B 0.804 no · A 0.800 YES · D 0.720 no · C 0.700 YES ·
X 0.900 YES but the posting says it does not sponsor, so its verdict is `ineligible` (tier 3).
A sits 0.004 under B, inside the band, so the flag lifts it above B. C sits 0.02 under D, outside
the band, so the flag does nothing. X has the highest score and a flag and must still rank last.
"""

from __future__ import annotations

import json
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from sqlalchemy import CursorResult, insert, update

from boardwatch.cli import top_cmd
from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.eligibility.facts import Facts, WorkAuthFact, facts_payload
from boardwatch.rank.heuristic import score_posting
from boardwatch.rank.sponsors import SPONSORS_FILENAME
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

_REAL_SCORE = score_posting
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."
REFUSAL = BODY + " We do not offer visa sponsorship for this position."
_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\nsoftware\n"

# name -> (company, title, body, forced score)
SPEC: dict[str, tuple[str, str, str, float]] = {
    "B": ("Bravo Works", "Backend Engineer", BODY, 0.804),
    "A": ("Alpha Works", "Backend Engineer", BODY, 0.800),
    "D": ("Delta Works", "Backend Engineer", BODY, 0.720),
    "C": ("Charlie Works", "Backend Engineer", BODY, 0.700),
    "X": ("Xray Works", "Backend Engineer", REFUSAL, 0.900),
}
FLAGGED = ("Alpha Works", "Charlie Works", "Xray Works")
NEEDS = Facts(work_authorization=WorkAuthFact(
    status="ead_or_similar", jurisdiction="us", needs_sponsorship=True))
NOT_NEEDED = Facts(work_authorization=WorkAuthFact(
    status="citizen", jurisdiction="us", needs_sponsorship=False))
UNDECLARED = Facts(work_authorization=WorkAuthFact(status="ead_or_similar", jurisdiction="us"))


def _record(name: str) -> dict[str, Any]:
    return {
        "name": name, "feins": ["11-1111111"], "certified_rows": 9, "computing_rows": 7,
        "computing_new_employment_rows": 3, "computing_low_wage_rows": 2,
        "secondary_entity_rows": 0, "naics2": "54", "state": "CA", "latest_decision": "2026-03-01",
    }


def _write_index(config_dir: Path, names: tuple[str, ...] = FLAGGED) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    employers = {name.lower().removesuffix(" works") + " works": _record(name) for name in names}
    (config_dir / SPONSORS_FILENAME).write_text(json.dumps(
        {"format": 1, "built": "2026-11-04", "sources": [], "employers": employers}))


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _pk(result: CursorResult[Any]) -> int:
    key = result.inserted_primary_key
    assert key is not None
    return int(key[0])


def _seed(data_dir: Path, facts: Facts | None) -> dict[str, int]:
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    ids: dict[str, int] = {}
    with engine.begin() as conn:
        for n, (name, (company, title, body, _)) in enumerate(SPEC.items()):
            company_id = _pk(conn.execute(insert(tables.companies).values(
                name=company, provider="greenhouse", slug=f"co{n}", source="user", watched=False,
            )))
            job_id = _pk(conn.execute(insert(tables.jobs).values(created_at=now)))
            posting_id = _pk(conn.execute(insert(tables.postings).values(
                company_id=company_id, provider_posting_id=f"p-{n}", job_id=job_id,
                title=title, normalized_title=f"backend engineer {n}",
                url=f"https://jobs.example/{n}", locations_json=["Remote"],
                remote_policy="remote", first_seen_at=now, last_seen_at=now, status="open",
                consecutive_missing=0, content_hash=f"h-{n}", body_text=body,
            )))
            conn.execute(insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{n}", body_text=body,
                captured_at=now, capture_reason="new",
            ))
            ids[name] = posting_id
    cli = CliRunner()
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=_INPUT).exit_code == 0
    if facts is not None:
        with engine.begin() as conn:
            conn.execute(update(tables.profile).where(tables.profile.c.id == 1).values(
                eligibility_facts_json=facts_payload(facts)))
    return ids


def _force_scores(monkeypatch: pytest.MonkeyPatch, ids: dict[str, int]) -> None:
    """Replace each posting's total with the fixture's, keyed by the company it is read beside.

    `score_posting` is not told the company, so the posting's title is made unique through the
    call order instead: the ranker scores rows in `postings.id` order, which is `SPEC` order.
    """
    real = _REAL_SCORE
    totals = iter(spec[3] for spec in SPEC.values())

    def forced(*args: Any, **kwargs: Any) -> Any:
        return replace(real(*args, **kwargs), total=next(totals))

    monkeypatch.setattr(top_cmd, "score_posting", forced)
    assert list(ids) == list(SPEC)


def _rank(
    data_dir: Path, limit: int = 5
) -> tuple[RankedResults, str]:
    settings = load_settings(data_dir=data_dir)
    buffer = StringIO()
    ranked = rank_open_postings(
        get_engine(data_dir), settings, limit=limit, record_surfaced=False,
        include_ineligible=True, output_console=Console(file=buffer, width=200),
    )
    return ranked, buffer.getvalue()


def _order(ranked: RankedResults, ids: dict[str, int]) -> str:
    by_id = {v: k for k, v in ids.items()}
    return "".join(by_id[p.posting_id] for p in ranked.visible)


def _reconciles(r: RankedResults) -> bool:
    return r.considered == (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_zero_signal + r.hidden_over_seniority + r.hidden_ineligible
        + r.hidden_duplicate + r.hidden_applied + r.hidden_handled + r.hidden_slate_cap
        + r.hidden_cluster_cap + r.hidden_lane_copy + r.hidden_requisition_twin
        + r.hidden_below_cutoff
    )


def _setup(env: Path, monkeypatch: pytest.MonkeyPatch, facts: Facts | None) -> dict[str, int]:
    ids = _seed(env, facts)
    _force_scores(monkeypatch, ids)
    return ids


def test_the_precondition_that_gives_the_tests_meaning(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the signal: score order, and X (highest score) is the one the rules reject, in
    the lowest tier, so it comes last even though it scores 0.9."""
    ids = _setup(env, monkeypatch, NEEDS)
    ranked, _ = _rank(env)
    assert _order(ranked, ids) == "BADCX"
    verdicts = {p.posting_id: p.verdict for p in ranked.visible}
    assert verdicts[ids["X"]] == "ineligible"


@pytest.mark.parametrize("facts", [NOT_NEEDED, UNDECLARED, Facts(), None])
def test_inactive_when_the_fact_is_false_or_none_and_no_file_is_read(
    env: Path, monkeypatch: pytest.MonkeyPatch, facts: Facts | None
) -> None:
    # Here X is not rejected (this profile never needed sponsorship, or never said so), so its
    # 0.9 puts it first: the order is plain score order inside one tier.
    ids = _setup(env, monkeypatch, facts)
    _write_index(env.parent / "cfg")

    def boom(_dir: Path) -> None:
        raise AssertionError("the sponsor index must not be read for a profile that does not need it")

    monkeypatch.setattr(top_cmd, "load_sponsor_index", boom)
    ranked, out = _rank(env)
    assert _order(ranked, ids) == "XBADC"
    assert "sponsor history" not in out


def test_inactive_and_silent_when_the_file_is_missing(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(env, monkeypatch, NEEDS)
    ranked, out = _rank(env)
    assert _order(ranked, ids) == "BADCX"
    assert "sponsor" not in out.lower()


def test_a_valid_file_with_no_employers_is_inert_and_silent(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(env, monkeypatch, NEEDS)
    _write_index(env.parent / "cfg", names=())
    ranked, out = _rank(env)
    assert _order(ranked, ids) == "BADCX"
    assert "sponsor" not in out.lower()


def test_active_a_flag_wins_inside_the_band_and_only_inside_it(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(env, monkeypatch, NEEDS)
    _write_index(env.parent / "cfg")
    ranked, out = _rank(env)
    # A (0.800, flagged) passes B (0.804): 0.004 apart, one band. C (0.700, flagged) does not pass
    # D (0.720): 0.02 apart. X, flagged with the top score, stays in the lowest tier.
    assert _order(ranked, ids) == "ABDCX"
    assert "3 of the first 5 positions carry an H-1B filer flag" in out


def test_a_lookup_miss_ranks_like_no_flag(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _setup(env, monkeypatch, NEEDS)
    _write_index(env.parent / "cfg", names=("Someone Else Works",))
    ranked, out = _rank(env)
    assert _order(ranked, ids) == "BADCX"
    assert "0 of the first 5 positions" in out


def test_no_verdict_and_no_count_changes_with_the_signal(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(env, monkeypatch, NEEDS)
    off, _ = _rank(env)
    _force_scores(monkeypatch, ids)
    _write_index(env.parent / "cfg")
    on, _ = _rank(env)
    assert _order(on, ids) != _order(off, ids)
    assert {p.posting_id: p.verdict for p in on.visible} == {
        p.posting_id: p.verdict for p in off.visible}
    assert {p.posting_id: p.tier for p in on.visible} == {p.posting_id: p.tier for p in off.visible}
    for ranked in (off, on):
        assert ranked.considered == 5
        assert _reconciles(ranked)
    # A posting that says it does not sponsor stays hidden when ineligibles are not asked for.
    settings = load_settings(data_dir=env)
    _force_scores(monkeypatch, ids)
    hidden = rank_open_postings(
        get_engine(env), settings, limit=5, record_surfaced=False,
        output_console=Console(file=StringIO()),
    )
    assert ids["X"] not in {p.posting_id for p in hidden.visible}
    assert hidden.hidden_ineligible == 1


def test_an_unusable_index_is_said_once_and_a_missing_one_is_not(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(env, monkeypatch, NEEDS)
    cfg = env.parent / "cfg"
    cfg.mkdir(exist_ok=True)
    (cfg / SPONSORS_FILENAME).write_text("{broken")
    ranked, out = _rank(env)
    assert _order(ranked, ids) == "BADCX"
    assert out.count("sponsor history tie-break is inert") == 1
    assert SPONSORS_FILENAME in out


def test_the_signal_does_not_move_config_hash(env: Path) -> None:
    from boardwatch.reports.manifest import config_hash

    before = config_hash(load_settings(data_dir=env))
    _write_index(env.parent / "cfg")
    assert config_hash(load_settings(data_dir=env)) == before
