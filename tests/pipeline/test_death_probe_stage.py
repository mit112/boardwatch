"""D-325 through `run_pipeline` — the wiring, not the rule.

`tests/unit/test_death_probe.py` pins what the sweep decides. What it cannot see is whether the
sweep is REACHED: a stage that is never called, or whose report never reaches the funnel
artifact, passes every unit test in this repo while the class it exists for keeps growing behind
it. That is the failure D-314 already had once — a closing path that was structurally
unreachable, with nothing red.

So these run the real pipeline and read the artifact off disk.

Never the network: the prober is injected, exactly as `cli/run_cmd.py` injects the real one.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert, select, update

from boardwatch.core.clock import utcnow
from boardwatch.core.liveness import Liveness
from boardwatch.core.normalize import content_hash
from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from tests.conftest import write_test_resume_template

runner_input = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
BODY = "We are hiring a backend engineer to work on Python and PostgreSQL services."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed_posting(data_dir: Path, n: int, *, watched: bool = False) -> int:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name=f"Acme{n}", provider="greenhouse", slug=f"acme{n}",
                    source="user", watched=watched,
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
                    url=f"https://example.test/j/{n}",
                    locations_json=["Remote"], remote_policy="remote",
                    first_seen_at=now, last_seen_at=now, status="open",
                    consecutive_missing=0, content_hash=content_hash(BODY), body_text=BODY,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=content_hash(BODY), body_text=BODY,
                captured_at=now, capture_reason="new",
            )
        )
    return posting_id


def _ready(data_dir: Path, count: int, *, watched: bool = False) -> list[int]:
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    cli = CliRunner()
    ids = [_seed_posting(data_dir, n, watched=watched) for n in range(count)]
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=runner_input).exit_code == 0
    assert cli.invoke(app, ["--data-dir", str(data_dir), "tailor", "init"]).exit_code == 0
    # T2: `tailor init` does not scaffold `resume_template.tex`, and `resolve_template` no longer
    # falls back to the bundled default for a real config dir missing it — so a pipeline run that
    # reaches tailoring/rendering needs one on disk, as a properly set-up user's config dir would.
    write_test_resume_template(load_settings(data_dir=data_dir).config_dir)
    return ids


def _gone_for(gone: set[int]):  # type: ignore[no-untyped-def]
    def probe(posting_id: int, url: str) -> Liveness:
        if posting_id in gone:
            return Liveness(posting_id, "dead", "refetch_gone", "HTTP 404")
        return Liveness(posting_id, "alive", "refetch_ok", "HTTP 200")

    return probe


def _pipeline(data_dir: Path, out_root: Path, *, prober=None) -> PipelineSummary:  # type: ignore[no-untyped-def]
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=5,
        liveness_prober=prober,
    )


def _age_the_probe(data_dir: Path) -> None:
    """Move every recorded probe 25 h into the past so the 24 h TTL admits the rows again.

    Rewinding the stored timestamp rather than injecting a clock into the pipeline: the TTL
    under test is the one production evaluates, and a `now` seam would exist only for tests.
    Rows never probed keep their NULL, which is what puts them first in the sweep order.
    """
    with get_engine(data_dir).begin() as conn:
        conn.execute(
            update(tables.postings)
            .where(tables.postings.c.last_death_probe_at.is_not(None))
            .values(last_death_probe_at=utcnow() - timedelta(hours=25))
        )


def _status(data_dir: Path, posting_id: int) -> tuple[str, int]:
    with get_engine(data_dir).connect() as conn:
        row = conn.execute(
            select(tables.postings.c.status, tables.postings.c.death_strikes).where(
                tables.postings.c.id == posting_id
            )
        ).one()
    return str(row.status), int(row.death_strikes)


def test_one_pipeline_run_records_a_strike_and_closes_nothing(env: Path, tmp_path: Path) -> None:
    """The narrowing that matters most in a real run: one 404 is one observation. Before this
    change `postings.status` was untouchable from a probe; after it, it takes two."""
    ids = _ready(env, 2)

    summary = _pipeline(env, tmp_path / "apps", prober=_gone_for({ids[0]}))

    assert summary.fatal is None, summary.errors
    assert _status(env, ids[0]) == ("open", 1)
    assert _status(env, ids[1]) == ("open", 0)


def test_two_pipeline_runs_close_the_posting_and_the_funnel_says_so(
    env: Path, tmp_path: Path
) -> None:
    """The whole change, end to end, read back through the artifact rather than the summary.

    A counter that lives only on `PipelineSummary` is a number nobody sees — the funnel is where
    a run is actually read, and where a detector that has stopped firing has to become visible.
    """
    ids = _ready(env, 2)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root, prober=_gone_for({ids[0]}))
    _age_the_probe(env)
    summary = _pipeline(env, out_root, prober=_gone_for({ids[0]}))

    assert summary.fatal is None, summary.errors
    assert _status(env, ids[0]) == ("closed", 2)
    assert _status(env, ids[1]) == ("open", 0)

    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    probe = payload["death_probe"]
    assert probe["instrumented"] is True
    assert probe["closed"] == 1
    assert probe["gone"] == 1
    assert probe["alive"] == 1
    assert probe["attempted"] == probe["due"] == 2
    assert probe["budget_refused"] == 0


def test_a_closed_posting_leaves_the_ranked_corpus_on_the_run_that_proved_it(
    env: Path, tmp_path: Path
) -> None:
    """The point of closing it, asserted through the funnel's corpus head rather than through
    `tailored` — by run 2 the ledger has already suppressed the surviving lead as `built`, so an
    empty `tailored` would pass this vacuously whether or not anything closed.

    The corpus stage counts every OPEN posting in the store. Two before, one after, and it is
    THIS run's funnel: the sweep runs before the ranker, so a posting proved dead leaves the
    pool on the run that proved it rather than on the next one.
    """
    ids = _ready(env, 2)
    out_root = tmp_path / "apps"

    first = _pipeline(env, out_root, prober=_gone_for({ids[0]}))
    assert first.funnel is not None
    before = json.loads(first.funnel.json_path.read_text(encoding="utf-8"))
    _age_the_probe(env)
    summary = _pipeline(env, out_root, prober=_gone_for({ids[0]}))

    def _corpus(payload: dict[str, object]) -> int:
        stages = payload["stages"]
        assert isinstance(stages, list)
        return int(next(s for s in stages if s["name"] == "corpus")["entered"])

    assert _corpus(before) == 2
    assert summary.funnel is not None
    assert _corpus(json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))) == 1
    assert ids[0] not in [lead.posting_id for lead in summary.tailored]
    # And it was never offered to the shortlist liveness check: the sweep closed it first.
    assert summary.dead_lead_ids == []


def test_a_watched_companys_posting_is_never_swept_by_the_pipeline(
    env: Path, tmp_path: Path
) -> None:
    """`watched = 1` boards already have a correct closing path (`_process_missing`). Sweeping
    them would put a 6.7%-sensitivity probe in front of a mechanism that enumerates the whole
    board — strictly worse evidence, and a second writer of the same column."""
    ids = _ready(env, 2, watched=True)
    out_root = tmp_path / "apps"

    _pipeline(env, out_root, prober=_gone_for(set(ids)))
    _age_the_probe(env)
    summary = _pipeline(env, out_root, prober=_gone_for(set(ids)))

    assert _status(env, ids[0]) == ("open", 0)
    assert _status(env, ids[1]) == ("open", 0)
    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["death_probe"]["due"] == 0
    assert payload["death_probe"]["attempted"] == 0


def test_a_run_with_no_prober_reports_the_sweep_as_UNMEASURED(  # noqa: N802
    env: Path, tmp_path: Path
) -> None:
    """`--no-check-liveness` asks for no network liveness at all, and the sweep honours that.
    What it must NOT do is report zero closed, which asserts a measurement nobody took."""
    _ready(env, 2)

    summary = _pipeline(env, tmp_path / "apps", prober=None)

    assert summary.death_probe is None
    assert summary.funnel is not None
    payload = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert payload["death_probe"] == {
        "instrumented": False,
        "due": None,
        "unprobeable": None,
        "attempted": None,
        "budget_refused": None,
        "gone": None,
        "unknown": None,
        "alive": None,
        "closed": None,
        "strikes_cleared": None,
    }
