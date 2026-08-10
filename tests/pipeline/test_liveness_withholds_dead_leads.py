"""P6 item 6 end to end — Gate P6's "0 dead postings reaching the lead list" clause.

Measured on the live store 2026-08-10, which is why this slice is shaped the way it is:

- **0** open postings are stale beyond 30 days — beyond 7, in fact. `CLOSE_AFTER_MISSES = 2` in
  `scan/apply.py` already closes anything absent from two complete board fetches, so staleness
  is not the leak and nothing here re-implements it.
- **216** open postings sit at `consecutive_missing = 1`: seen on a board, then absent once. That
  is the population this check exists for — the window between a requisition closing and the
  scanner noticing.
- A 12-URL probe on 2026-08-10 found the 404 signal has low RECALL (7 of 8 already-closed
  Workday/Ashby postings still answered 200) and did find a genuinely dead OPEN posting
  (`jobs.lever.co/palantir/…`, `consecutive_missing = 1`). Low recall is acceptable; a false
  positive is not, which is why fail-open is asserted here in more cases than `dead` is.

These tests never touch the network: the prober is injected, exactly as production injects the
real one from `run_cmd`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import Liveness
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.liveness import check_leads
from boardwatch.pipeline.runner import _zero_output_guard, run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.ledger_queries import load_dispositions

runner_input = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed_posting(data_dir: Path, n: int, *, url: str | None = None) -> int:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name=f"Acme{n}", provider="greenhouse", slug=f"acme{n}",
                    source="user", watched=False,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        )
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=f"p-{n}", job_id=job_id,
                    title="Backend Engineer", normalized_title="backend engineer",
                    url=f"https://example.test/j/{n}" if url is None else url,
                    locations_json=["Remote"], remote_policy="remote",
                    first_seen_at=now, last_seen_at=now, status="open",
                    consecutive_missing=0, content_hash=f"h-{n}", body_text=BODY,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{n}", body_text=BODY,
                captured_at=now, capture_reason="new",
            )
        )
    return posting_id


def _ready(data_dir: Path, count: int, *, urls: dict[int, str | None] | None = None) -> list[int]:
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    cli = CliRunner()
    urls = urls or {}
    ids = [_seed_posting(data_dir, n, url=urls.get(n)) for n in range(count)]
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=runner_input).exit_code == 0
    assert cli.invoke(app, ["--data-dir", str(data_dir), "tailor", "init"]).exit_code == 0
    return ids


def _prober(dead: set[int] = frozenset(), unknown: set[int] = frozenset()):  # type: ignore[assignment]
    def probe(posting_id: int, url: str) -> Liveness:
        if posting_id in dead:
            return Liveness(posting_id, "dead", "refetch_gone", "HTTP 404")
        if posting_id in unknown:
            return Liveness(posting_id, "unknown", "refetch_error", "ConnectTimeout")
        return Liveness(posting_id, "alive", "refetch_ok", "HTTP 200")
    return probe


def _pipeline(data_dir: Path, out_root: Path, top_n: int, prober=None):  # type: ignore[no-untyped-def]
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=top_n,
        liveness_prober=prober,
    )


def test_a_dead_posting_never_reaches_the_lead_list(env: Path, tmp_path: Path) -> None:
    """Gate P6's remaining clause, stated as a test. Without the filter this posting is a
    perfectly ordinary lead and gets a résumé built for it."""
    ids = _ready(env, 2)
    summary = _pipeline(env, tmp_path / "apps", top_n=2, prober=_prober(dead={ids[0]}))

    assert summary.fatal is None, summary.errors
    assert [lead.posting_id for lead in summary.tailored] == [ids[1]]
    assert summary.dead_lead_ids == [ids[0]]
    assert summary.liveness_checked == 2
    assert summary.liveness_dead == 1


def test_an_unknown_outcome_still_reaches_the_lead_list(env: Path, tmp_path: Path) -> None:
    """Fail-open, at the level that matters. A timeout must cost a wasted résumé, never a
    missed job."""
    ids = _ready(env, 2)
    summary = _pipeline(env, tmp_path / "apps", top_n=2, prober=_prober(unknown={ids[0]}))

    assert summary.fatal is None, summary.errors
    assert {lead.posting_id for lead in summary.tailored} == set(ids)
    assert summary.dead_lead_ids == []
    assert summary.liveness_unknown == 1


def test_a_dead_posting_is_not_closed_in_the_store(env: Path, tmp_path: Path) -> None:
    """Liveness is NEVER cached. `postings.status` belongs to the scanner's board-absence rule;
    a probe that wrote to it would let one 404 from a flaky CDN retire a live requisition
    permanently, and no later scan would ever reopen it because it would stop being ranked."""
    ids = _ready(env, 1)
    _pipeline(env, tmp_path / "apps", top_n=1, prober=_prober(dead={ids[0]}))

    engine = get_engine(env)
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.postings.c.status, tables.postings.c.closed_at)
            .where(tables.postings.c.id == ids[0])
        ).one()
    assert row.status == "open"
    assert row.closed_at is None


def test_a_withheld_lead_is_not_recorded_seen(env: Path, tmp_path: Path) -> None:
    """The D-110 seam, applied to this filter: only a caller that DELIVERS a lead may consume
    the queue. A posting withheld as gone was delivered to nobody, so suppressing it for the
    seen TTL would hide it for a week on the strength of one failed fetch."""
    ids = _ready(env, 2)
    _pipeline(env, tmp_path / "apps", top_n=2, prober=_prober(dead={ids[0]}))

    engine = get_engine(env)
    with engine.connect() as conn:
        anchors = {
            int(row.id): int(row.job_id)
            for row in conn.execute(
                select(tables.postings.c.id, tables.postings.c.job_id)
                .where(tables.postings.c.id.in_(ids))
            ).all()
        }
        dispositions = load_dispositions(conn)

    assert anchors[ids[0]] not in dispositions
    assert dispositions[anchors[ids[1]]].disposition == "built"


def test_a_shortlist_that_is_entirely_dead_is_an_HONEST_empty_day(  # noqa: N802
    env: Path, tmp_path: Path
) -> None:
    """Liveness working perfectly must not read as the failure mode it exists to prevent.

    Both guards would otherwise fire: `every lead failed to tailor` counts a withheld posting as
    a render failure, and the zero-output guard cannot explain a run that judged new eligible
    postings and produced nothing.
    """
    ids = _ready(env, 2)
    summary = _pipeline(env, tmp_path / "apps", top_n=2, prober=_prober(dead=set(ids)))

    assert summary.fatal is None, summary.errors
    assert summary.tailored == []
    assert sorted(summary.dead_lead_ids) == sorted(ids)
    # And it is not silent: the reason is in `errors`, one line per withheld posting.
    assert sum("withheld as gone" in message for message in summary.errors) == 2


def test_the_zero_output_guard_still_fires_with_nothing_dead_and_nothing_handled() -> None:
    """The widening stays narrow. A run that can explain nothing must still fail."""
    assert _zero_output_guard(5, 0, 0) is not None
    assert _zero_output_guard(5, 0, 1) is None  # explained by liveness
    assert _zero_output_guard(5, 1, 0) is None  # explained by the ledger
    assert _zero_output_guard(0, 0, 0) is None  # no new eligible work at all


def test_an_unprobed_run_reports_liveness_as_UNMEASURED_not_as_zero_dead(  # noqa: N802
    env: Path, tmp_path: Path
) -> None:
    """D-022/D-023: reporting the structurally-true 0 would assert a check nobody ran."""
    _ready(env, 1)
    summary = _pipeline(env, tmp_path / "apps", top_n=1, prober=None)

    assert summary.liveness_checked is None
    assert summary.liveness_dead is None
    assert summary.dead_lead_ids == []


def test_a_posting_with_no_url_is_served_without_being_probed(env: Path) -> None:
    """`postings.url` is nullable, so `check_leads` must not hand an empty string to the
    prober and must not treat the absence as evidence."""
    ids = _ready(env, 1, urls={0: ""})
    asked: list[int] = []

    def probe(posting_id: int, url: str) -> Liveness:
        asked.append(posting_id)
        return Liveness(posting_id, "dead", "refetch_gone", "HTTP 404")

    results = check_leads(get_engine(env), ids, prober=probe)

    assert asked == []
    assert results[ids[0]].verdict == "unknown"
    assert results[ids[0]].signal == "no_url"


def test_check_leads_writes_nothing(env: Path) -> None:
    """Stated as its own test because it is the invariant the whole module rests on."""
    ids = _ready(env, 2)
    engine = get_engine(env)

    def snapshot() -> list[tuple[int, str, object]]:
        with engine.connect() as conn:
            return [
                (int(r.id), str(r.status), r.closed_at)
                for r in conn.execute(
                    select(
                        tables.postings.c.id,
                        tables.postings.c.status,
                        tables.postings.c.closed_at,
                    )
                ).all()
            ]

    before = snapshot()
    check_leads(engine, ids, prober=_prober(dead=set(ids)))
    assert snapshot() == before
