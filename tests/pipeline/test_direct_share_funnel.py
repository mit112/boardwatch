"""D-683 end to end: the real runner, ranker and funnel writer on a synthetic store, with the share
armed. What is pinned is what a reader of `funnel-<id>.json` and `.md` gets: where the direct and
other leads went at every step, that the section reconciles against the counters the funnel already
keeps and against the store, and that arming the count changed nothing that was delivered.

The fixture is six postings under one tier, links alternating direct (Ashby) and other, all with the
same score, so the ranker's order is the id order and the share's reorder is the identity. Posting
`ids[0]` (direct) is dead when probed; `top_n` is 4, so `ids[4]` (direct) and `ids[5]` (other) fall
below the cut. The expected numbers follow from those three facts:

    interleave order   ids[0] D  ids[1] N  ids[2] D  ids[3] N  | ids[4] D  ids[5] N  (cut)
    withheld as gone   ids[0]
    delivered          ids[1] N  ids[2] D  ids[3] N
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from boardwatch.core.settings import load_settings
from boardwatch.pipeline.runner import PipelineSummary, run_pipeline
from boardwatch.rank.direct_share import DirectShareTally
from boardwatch.store.db import get_engine
from tests.pipeline.test_liveness_withholds_dead_leads import _prober, _ready

_ROUTES = 'auto_hosts = ["ashbyhq.com"]\n'


def _direct(n: int) -> str:
    return f"https://jobs.ashbyhq.com/acme/00000000-0000-0000-0000-{n:012d}"


def _other(n: int) -> str:
    return f"https://example.test/j/{n}"


URLS = {0: _direct(0), 1: _other(1), 2: _direct(2), 3: _other(3), 4: _direct(4), 5: _other(5)}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, out_root: Path, share: float) -> tuple[PipelineSummary, list[int]]:
    ids = _ready(data_dir, 6, urls=URLS)
    settings = load_settings(data_dir=data_dir)
    settings.config_dir.mkdir(exist_ok=True)
    (settings.config_dir / "apply-routes.toml").write_text(_ROUTES, encoding="utf-8")
    settings = settings.model_copy(update={"slate_direct_share": share})
    summary = run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        top_n=4,
        liveness_prober=_prober(dead={ids[0]}),
    )
    assert summary.fatal is None, summary.errors
    return summary, ids


def _payload(summary: PipelineSummary) -> dict[str, object]:
    assert summary.funnel is not None
    loaded = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_artifact_says_where_each_direct_and_other_lead_went(env: Path, tmp_path: Path) -> None:
    summary, ids = _run(env, tmp_path / "apps", 0.5)
    payload = _payload(summary)

    assert [lead.posting_id for lead in summary.tailored] == [ids[1], ids[2], ids[3]]
    section = payload["direct_share"]
    assert isinstance(section, dict)
    assert section["state"] == "measured" and section["share"] == 0.5
    assert section["reconciles"] is True and payload["reconciles"] is True
    # No gate and no projection ran, so those steps are ABSENT rather than zero.
    assert section["steps"] == [
        "hidden_duplicate", "hidden_handled", "hidden_applied", "hidden_lane_copy",
        "hidden_requisition_twin", "hidden_slate_cap", "hidden_cluster_cap", "capped_by_top_n",
        "withheld_not_live", "beyond_slate", "execution_deferred", "tailor_failed",
    ]
    zero = {step: 0 for step in section["steps"]}  # type: ignore[attr-defined]
    totals = section["totals"]
    assert isinstance(totals, dict)
    assert totals["direct"] == {
        "entered": 3, "removed": {**zero, "capped_by_top_n": 1, "withheld_not_live": 1},
        "delivered": 1, "delivered_review_lane": 1, "unaccounted": 0,
    }
    assert totals["non_direct"] == {
        "entered": 3, "removed": {**zero, "capped_by_top_n": 1},
        "delivered": 2, "delivered_review_lane": 2, "unaccounted": 0,
    }
    # The review-lane share is read off the leads the run itself flagged.
    assert sum(lead.pending_tailor for lead in summary.tailored) == 3
    tiers = section["tiers"]
    assert isinstance(tiers, dict) and len(tiers) == 1
    (tier,) = tiers.values()
    # The direct leads lost, by id, are the evidence the history never kept.
    assert tier["direct"]["dropped_ids"] == {
        "capped_by_top_n": [ids[4]], "withheld_not_live": [ids[0]],
    }
    assert "dropped_ids" not in tier["non_direct"]

    # Every step total agrees with the counter the funnel already had, the delivered count with
    # the artifact rows, and the delivered direct count with a fresh routing of the stored links.
    checks = {c["name"]: (c["in_memory"], c["from_store"], c["agrees"])
              for c in payload["cross_checks"]  # type: ignore[attr-defined]
              if c["name"].startswith("direct_share:")}
    assert checks["direct_share:entered"] == (6, 6, True)
    assert checks["direct_share:capped_by_top_n"] == (2, 2, True)
    assert checks["direct_share:withheld_not_live"] == (1, 1, True)
    assert checks["direct_share:delivered"] == (3, 3, True)
    assert checks["direct_share:delivered_direct"] == (1, 1, True)
    assert checks["direct_share:unaccounted"] == (0, 0, True)
    assert all(agrees for _, _, agrees in checks.values())
    assert "direct_share:gate_rejected" not in checks
    assert "direct_share:projection_failed" not in checks

    assert summary.funnel is not None
    text = summary.funnel.markdown_path.read_text(encoding="utf-8")
    block = text[text.index("## Direct share"):]
    block = block[:block.index("\n## ", 5)]
    assert "| entered the interleave | 3 | 3 |" in block
    assert "| capped_by_top_n | 1 | 1 |" in block
    assert "| withheld_not_live | 1 | 0 |" in block
    assert "| delivered | 1 | 2 |" in block
    assert f"- `capped_by_top_n`: {ids[4]}" in block
    assert f"- `withheld_not_live`: {ids[0]}" in block


def test_counting_changes_nothing_that_is_delivered(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same run twice on separate stores, once with the tally's recording and the attribution
    switched off. The delivered leads, the withheld ones and the dispositions written match."""
    from sqlalchemy import select

    from boardwatch.store import tables

    def dispositions(data_dir: Path) -> list[tuple[int, str]]:
        with get_engine(data_dir).connect() as conn:
            return sorted(
                (int(r.job_id), str(r.disposition))
                for r in conn.execute(select(
                    tables.job_dispositions.c.job_id, tables.job_dispositions.c.disposition
                ))
            )

    on, ids_on = _run(env, tmp_path / "apps-on", 0.5)

    other_root = tmp_path / "second"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(other_root / "cfg"))
    monkeypatch.setattr(DirectShareTally, "drop", lambda *a, **k: None)
    monkeypatch.setattr(DirectShareTally, "finish", lambda *a, **k: None)
    off, ids_off = _run(other_root / "data", other_root / "apps", 0.5)

    assert ids_on == ids_off
    assert [lead.posting_id for lead in on.tailored] == [lead.posting_id for lead in off.tailored]
    assert on.dead_lead_ids == off.dead_lead_ids == [ids_on[0]]
    assert dispositions(env) == dispositions(other_root / "data")
    # With the recording off the section cannot reconcile, and says so rather than guessing: every
    # lead the ranker would have counted is unaccounted. The slate it describes is unchanged.
    assert _payload(off)["direct_share"]["reconciles"] is False  # type: ignore[index]
    assert _payload(on)["direct_share"]["reconciles"] is True  # type: ignore[index]


def test_with_the_share_off_the_artifact_says_off_and_carries_no_counts(
    env: Path, tmp_path: Path
) -> None:
    summary, ids = _run(env, tmp_path / "apps", 0.0)
    payload = _payload(summary)
    assert payload["direct_share"] == {
        "instrumented": False, "state": "off", "share": 0.0,
        "detail": "slate_direct_share is 0",
    }
    assert not [c for c in payload["cross_checks"] if c["name"].startswith("direct_share:")]  # type: ignore[attr-defined]
    assert payload["reconciles"] is True
    assert summary.funnel is not None
    text = summary.funnel.markdown_path.read_text(encoding="utf-8")
    assert "## Direct share\n\n*OFF." in text
    assert [lead.posting_id for lead in summary.tailored] == [ids[1], ids[2], ids[3]]


def _relink_after_ranking(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, *, report: bool
) -> None:
    """Stand in for D-689's step: write a DIRECT employer link for `ids[1]` (non-direct, delivered)
    after the ranker has classified it, the way the real step does, and say so only when `report`.
    The slate is ids[0..3] in id order (module docstring), so `ids[1]` is its second id."""
    from datetime import datetime

    from boardwatch.pipeline import runner
    from boardwatch.store.application_destinations import record_application_destination

    def fake(
        engine: object, shortlist_ids: list[int], console: object
    ) -> tuple[list[str], dict[int, str]]:
        posting = sorted(shortlist_ids)[1]
        url = _direct(100)
        with get_engine(data_dir).begin() as conn:
            record_application_destination(
                conn, posting_id=posting, url=url, source_url=URLS[1],
                evidence_ref="local-twin:v1:test", verified_at=datetime(2026, 11, 11),
            )
        return [], ({posting: url} if report else {})

    monkeypatch.setattr(runner, "_link_local_twins", fake)


def _direct_checks(payload: dict[str, object]) -> tuple[int, int, bool]:
    (check,) = [c for c in payload["cross_checks"]  # type: ignore[attr-defined]
                if c["name"] == "direct_share:delivered_direct"]
    return check["in_memory"], check["from_store"], check["agrees"]


def test_a_link_written_after_ranking_is_counted_and_reconciles(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Run 1022: two lane leads got an employer link from the local-twin step after the ranker
    # had counted them non-direct, so the store recount found 48 direct where the ranker had 46.
    _relink_after_ranking(monkeypatch, env, report=True)
    summary, ids = _run(env, tmp_path / "apps", 0.5)
    assert ids[1] in [lead.posting_id for lead in summary.tailored]
    payload = _payload(summary)
    section = payload["direct_share"]
    assert isinstance(section, dict)
    assert section["relinked"] == {"to_direct": 1, "off_direct": 0}
    # The route totals stay the ranker's: re-routing is reported beside them, not folded in.
    assert section["totals"]["direct"]["delivered"] == 1  # type: ignore[index]
    assert _direct_checks(payload) == (2, 2, True)
    assert payload["reconciles"] is True
    assert summary.funnel is not None
    assert "Re-linked after ranking: 1 delivered lead(s)" in (
        summary.funnel.markdown_path.read_text(encoding="utf-8")
    )


def test_an_unreported_link_change_still_fails_the_recount(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same store write with nothing reported: the check must still catch it.
    _relink_after_ranking(monkeypatch, env, report=False)
    summary, _ = _run(env, tmp_path / "apps", 0.5)
    payload = _payload(summary)
    relinked = payload["direct_share"]["relinked"]  # type: ignore[index]
    assert relinked == {"to_direct": 0, "off_direct": 0}
    assert _direct_checks(payload) == (1, 2, False)
    assert payload["reconciles"] is False


def test_relinked_routes_classify_nothing_without_a_routes_file(env: Path) -> None:
    from boardwatch.pipeline.runner import _relinked_routes

    settings = load_settings(data_dir=env)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    links = {1: _direct(1), 2: _other(2)}
    assert _relinked_routes(settings, links) == {}
    (settings.config_dir / "apply-routes.toml").write_text(_ROUTES, encoding="utf-8")
    assert _relinked_routes(settings, links) == {1: True, 2: False}
