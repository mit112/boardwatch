"""T366: the value model's shadow — P(good) beside every gate candidate, ordering nothing.

The keystone test is `test_the_gate_decides_identically_with_the_model_on_and_off`: the score
may only be RECORDED. The rest pin what the shadow file says and which readings it learns from.
Expected values come from each fixture's construction (planted titles, a hand count, the file's
own recorded scores recounted by the metric's definition), never from the module's own path.
"""

from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings, load_settings
from boardwatch.eligibility import final_gate
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import parse_policy
from boardwatch.eligibility.final_gate import gate_effort_key, record_gate_verdict
from boardwatch.eligibility.oracle import OracleVerdict
from boardwatch.eligibility.preflight import engine_facts
from boardwatch.eligibility.read import gate_judge_identity
from boardwatch.llm.gate_judge import run_gate_backlog
from boardwatch.pipeline import value_shadow as vs
from boardwatch.pipeline.value_shadow import ValueShadow, load_readings
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import current_posting_versions, get_profile, insert_run
from tests.pipeline.test_gate_stage import (
    _candidates,
    _depth_pipeline,
    _gate_row_order,
    _needs_an_executable_fake,
    _ready,
    _set_first_seen,
    env,
    fake_claude,
)

__all__ = ["env", "fake_claude"]  # the fixtures, imported so pytest resolves them here

GOOD_TITLE = "Junior Software Engineer"
BAD_TITLE = "Senior Staff Principal Engineer"


def _configure(
    data_dir: Path, *, min_readings: int, backlog_budget: int = 0, refresh_budget: int = 0
) -> Settings:
    config_dir = load_settings(data_dir=data_dir).config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        "[gate]\nenabled = true\nmodel = \"sonnet\"\neffort = \"medium\"\nbatch_size = 13\n"
        f"call_timeout_s = 30\nvalue_model_min_readings = {min_readings}\n"
        f"refresh_budget = {refresh_budget}\nbacklog_budget = {backlog_budget}\n",
        encoding="utf-8",
    )
    with get_engine(data_dir).begin() as conn:
        conn.execute(tables.profile.update().values(target_seniority_band="entry"))
    return load_settings(data_dir=data_dir)


def _post(
    engine: Engine, *, title: str, company: str = "Acme", slug: str | None = None,
    status: str = "open", first_seen: object = None, body: str = "We build backend services.",
) -> int:
    """One posting with one version. A company per `slug` (default: one shared `company`)."""
    now = utcnow()
    slug = slug or company.lower()
    with engine.begin() as conn:
        found = conn.execute(
            select(tables.companies.c.id).where(
                tables.companies.c.provider == "greenhouse", tables.companies.c.slug == slug
            )
        ).scalar()
        company_id = int(found) if found else int(conn.execute(insert(tables.companies).values(
            name=company, provider="greenhouse", slug=slug, source="user", watched=True,
        )).inserted_primary_key[0])
        job_id = int(conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0])
        key = f"{slug}-{title}-{job_id}"
        posting_id = int(conn.execute(insert(tables.postings).values(
            company_id=company_id, provider_posting_id=key, title=title,
            normalized_title=title.lower(), url="https://example.test/j", locations_json=["Remote"],
            remote_policy="remote", first_seen_at=first_seen or now, last_seen_at=now,
            status=status, consecutive_missing=0, content_hash=key, body_text=body, job_id=job_id,
        )).inserted_primary_key[0])
        conn.execute(insert(tables.posting_versions).values(
            posting_id=posting_id, content_hash=key, body_text=body, captured_at=now,
            capture_reason="new",
        ))
    return posting_id


def _read(
    engine: Engine, settings: Settings, posting_id: int, *, good: bool, run_id: int | None = None,
    model: str = "sonnet", effort: str = "medium", band: str = "entry",
    seniority: str | None = None, decision: str | None = None,
) -> None:
    """Write one gate reading through the production writer, as the judge's stage does."""
    with engine.begin() as conn:
        profile = get_profile(conn)
        assert profile is not None
        facts = engine_facts(profile.eligibility_facts_json, settings.config_dir)
        version = current_posting_versions(conn, [posting_id])[posting_id]
        record_gate_verdict(
            conn, posting_version_id=version.posting_version_id, jd_text=version.body_text,
            facts=facts, policy=parse_policy(profile.eligibility_policy_json),
            catalog=load_rules(settings.config_dir),
            verdict=OracleVerdict(
                label=str(posting_id), decision=decision or ("eligible" if good else "uncertain"),
                reason=None, evidence="", confidence="high",
                seniority_fit=seniority or ("yes" if good else "no"),
            ),
            run_id=run_id, provider="claude-code-agent", model=model, effort=effort,
            target_band=band,
        )


def _history(engine: Engine, settings: Settings, n: int = 30) -> list[int]:
    """`n` good (junior titles) and `n` bad (senior titles) readings under the current identity,
    oldest first. Returns the postings read, in that order."""
    read: list[int] = []
    for i in range(n):
        for title, good in ((f"{GOOD_TITLE} {i}", True), (f"{BAD_TITLE} {i}", False)):
            posting_id = _post(engine, title=title, status="closed")
            _read(engine, settings, posting_id, good=good)
            read.append(posting_id)
    return read


def _shadow(settings: Settings, engine: Engine) -> tuple[ValueShadow, int]:
    time.sleep(0.01)  # the run starts strictly after the history it may learn from
    run_id = insert_run(engine)
    shadow = ValueShadow(settings, run_id)
    shadow.start(engine)
    return shadow, run_id


def _report(path: Path | None) -> dict[str, object]:
    assert path is not None
    report: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return report


def _stack(env: Path) -> tuple[Engine, Settings]:
    _ready(env)
    settings = _configure(env, min_readings=20, backlog_budget=3, refresh_budget=2)
    engine = get_engine(env)
    ensure_schema(engine)
    return engine, settings


# ---------------------------------------------------------------------------
# which readings the model learns from
# ---------------------------------------------------------------------------


def test_the_model_trains_on_the_current_judge_identity_only(env: Path) -> None:
    """Decoys under every other identity (another model, another level, another band) would each
    change the count: the model's training set is exactly the 60 current readings."""
    engine, settings = _stack(env)
    _history(engine, settings, n=30)
    for i, (model, effort, band) in enumerate(
        [("opus", "medium", "entry"), ("sonnet", "high", "entry"), ("sonnet", "medium", "any")]
    ):
        _read(engine, settings, _post(engine, title=f"decoy {i}", status="closed"),
              good=True, model=model, effort=effort, band=band)
    shadow, _ = _shadow(settings, engine)

    assert shadow._header["readings"] == 60
    assert shadow._header["good_readings"] == 30
    assert shadow._header["trained"] is True


def test_a_reading_under_another_engine_version_or_facts_key_is_not_learned_from(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, settings = _stack(env)
    _history(engine, settings, n=30)  # written under the facts as they were
    with get_engine(env).begin() as conn:  # the candidate's facts change: the judge is asked anew
        profile = get_profile(conn)
        assert profile is not None
        facts = dict(profile.eligibility_facts_json or {})
        facts["total_years_experience"] = 9
        conn.execute(tables.profile.update().values(eligibility_facts_json=facts))
    _read(engine, settings, _post(engine, title="new facts", status="closed"), good=True)
    with monkeypatch.context() as old:  # same facts, but from before the judge's policy moved
        old.setattr(final_gate, "gate_engine_version", lambda: "final_gate:p5-oracle-1:old")
        _read(engine, settings, _post(engine, title="old policy", status="closed"), good=True)

    shadow, _ = _shadow(settings, engine)

    assert shadow._header["readings"] == 1  # the one reading under the new facts and policy
    assert shadow._header["trained"] is False


def test_only_readings_made_before_the_run_are_learned_from(env: Path) -> None:
    """The run's own judge answers must stay out-of-sample."""
    engine, settings = _stack(env)
    _history(engine, settings, n=30)
    time.sleep(0.01)
    run_id = insert_run(engine)
    time.sleep(0.01)
    _read(engine, settings, _post(engine, title="judged this run", status="closed"), good=True,
          run_id=run_id)
    shadow = ValueShadow(settings, run_id)
    shadow.start(engine)
    assert shadow._header["readings"] == 60


def test_the_label_is_eligible_and_seniority_yes_and_the_newest_reading_per_posting_wins(
    env: Path,
) -> None:
    engine, settings = _stack(env)
    cleared = _post(engine, title="cleared", status="closed")
    above_band = _post(engine, title="above band", status="closed")
    flipped = _post(engine, title="flipped", status="closed")
    _read(engine, settings, cleared, good=True)  # eligible + yes
    _read(engine, settings, above_band, good=False, decision="eligible", seniority="no")
    _read(engine, settings, flipped, good=True)
    _read(engine, settings, flipped, good=False)  # the newer reading overrides
    with engine.connect() as conn:
        profile = get_profile(conn)
        assert profile is not None
        facts = engine_facts(profile.eligibility_facts_json, settings.config_dir)
        scope = gate_judge_identity(facts, model="sonnet", effort=gate_effort_key("medium"),
                                    target_band="entry")
        by_post = {r.posting_id: r.good for r in load_readings(conn, scope, "entry")}
    assert by_post == {cleared: True, above_band: False, flipped: False}


def test_under_target_band_any_the_label_is_eligible_alone(env: Path) -> None:
    """Under `any` the judge is not asked about seniority (it answers the inert `unclear`), so a
    clear is good without a seniority `yes`."""
    engine, settings = _stack(env)
    a = _post(engine, title="a", status="closed")
    b = _post(engine, title="b", status="closed")
    _read(engine, settings, a, good=True, band="any", seniority="unclear")
    _read(engine, settings, b, good=False, band="any", seniority="unclear", decision="uncertain")
    with engine.connect() as conn:
        profile = get_profile(conn)
        assert profile is not None
        facts = engine_facts(profile.eligibility_facts_json, settings.config_dir)
        scope = gate_judge_identity(facts, model="sonnet", effort=gate_effort_key("medium"),
                                    target_band="any")
        by_post = {r.posting_id: r.good for r in load_readings(conn, scope, "any")}
    assert by_post == {a: True, b: False}


# ---------------------------------------------------------------------------
# the shadow file
# ---------------------------------------------------------------------------


def test_too_few_readings_get_no_model_and_no_scores(env: Path, tmp_path: Path) -> None:
    engine, settings = _stack(env)
    settings = _configure(env, min_readings=1000, backlog_budget=3)
    _history(engine, settings, n=30)
    candidate = _post(engine, title=GOOD_TITLE)
    shadow, run_id = _shadow(settings, engine)
    shadow.observe_slate([candidate])
    shadow.observe_backlog([candidate])

    report = _report(shadow.finish(engine, tmp_path / "day"))

    assert report["trained"] is False
    assert report["readings"] == 60 and report["min_readings"] == 1000
    assert "candidates" not in report and "arrivals" not in report
    assert "p_good" not in json.dumps(report)  # no scores, not zeros
    assert str(report["summary_line"]).startswith("value model (shadow): not trained")
    assert (tmp_path / "day" / f"value-shadow-{run_id}.json").exists()


def test_every_candidate_is_recorded_with_its_position_its_p_and_its_rank_by_p(
    env: Path, tmp_path: Path
) -> None:
    engine, settings = _stack(env)  # backlog budget 3, refresh budget 2
    _history(engine, settings, n=30)
    # Existing order puts the senior-titled postings first in every pool.
    slate = [_post(engine, title=f"{BAD_TITLE} s{i}") for i in range(4)] + [
        _post(engine, title=f"{GOOD_TITLE} s{i}") for i in range(4)
    ]
    refresh = [_post(engine, title=f"{BAD_TITLE} r{i}") for i in range(3)]
    backlog = [_post(engine, title=f"{GOOD_TITLE} b{i}") for i in range(20)]
    shadow, _ = _shadow(settings, engine)
    shadow.observe_slate(slate)
    shadow.observe_refresh(refresh)
    shadow.observe_backlog(backlog)
    shadow.sent_slate(slate)
    shadow.sent_refresh(refresh[:2], 2)
    shadow.sent_backlog(backlog[:3], 3)

    report = _report(shadow.finish(engine, tmp_path / "day"))

    records = report["candidates"]
    assert isinstance(records, list)
    by_pool: dict[str, list[dict[str, object]]] = {}
    for record in records:
        by_pool.setdefault(str(record["pool"]), []).append(record)
    # Slate: all eight, in the order given. Refresh: its budget (2) of three. Backlog: the budget
    # (3) plus four budgets of lookahead (12) = 15 of the 20, the first 3 being what was sent.
    assert [r["posting_id"] for r in by_pool["slate"]] == slate
    assert [r["position"] for r in by_pool["slate"]] == list(range(8))
    assert [r["posting_id"] for r in by_pool["refresh"]] == refresh[:2]
    assert [r["posting_id"] for r in by_pool["backlog"]] == backlog[:15]
    assert [r["sent"] for r in by_pool["backlog"]] == [True] * 3 + [False] * 12
    assert all(r["sent"] for r in by_pool["slate"] + by_pool["refresh"])
    assert not any(r["passed_over"] for r in records)
    for pool_records in by_pool.values():
        assert all(0.0 < float(r["p_good"]) < 1.0 for r in pool_records)  # type: ignore[arg-type]
        # rank_by_p is 1..n and follows P (highest first, the existing order breaking ties)
        ordered = sorted(pool_records, key=lambda r: (-float(r["p_good"]), r["position"]))  # type: ignore[arg-type]
        assert [r["rank_by_p"] for r in ordered] == list(range(1, len(pool_records) + 1))
    # The planted rule is learned: every junior-titled slate posting outscores every senior one.
    slate_p = {r["posting_id"]: float(r["p_good"]) for r in by_pool["slate"]}  # type: ignore[arg-type]
    assert min(slate_p[p] for p in slate[4:]) > max(slate_p[p] for p in slate[:4])
    assert report["trained"] is True and report["readings"] == 60


def _pairs_auc(scored: list[tuple[float, bool]]) -> float:
    """AUC by its definition: the share of (good, not good) pairs the score orders correctly."""
    wins = sum(
        1.0 if p > q else 0.5 if p == q else 0.0
        for p, good in scored if good for q, other in scored if not other
    )
    return wins / (sum(g for _, g in scored) * sum(not g for _, g in scored))


def test_the_runs_own_judged_items_give_auc_top_half_precision_and_the_backlog_comparison(
    env: Path, tmp_path: Path
) -> None:
    engine, settings = _stack(env)  # backlog budget 3
    _history(engine, settings, n=30)
    # 24 slate items, 12 junior-titled (the model's top half) and 12 senior-titled. The existing
    # order puts five juniors and seven seniors first. The judge reads 10 of the 12 juniors good
    # and every senior bad: the model's top half is 10/12, the existing order's is 5/12.
    juniors = [_post(engine, title=f"{GOOD_TITLE} s{i}") for i in range(12)]
    seniors = [_post(engine, title=f"{BAD_TITLE} s{i}") for i in range(12)]
    slate = juniors[:5] + seniors[:7] + juniors[5:] + seniors[7:]
    backlog = [_post(engine, title=f"{BAD_TITLE} b{i}") for i in range(3)] + [
        _post(engine, title=f"{GOOD_TITLE} b{i}") for i in range(3)
    ]
    shadow, run_id = _shadow(settings, engine)
    shadow.observe_slate(slate)
    shadow.sent_slate(slate)
    shadow.observe_backlog(backlog)  # budget 3: the senior three are sent, the junior three not
    shadow.sent_backlog(backlog[:3], 3)
    labels = {p: p in juniors[:10] for p in slate}
    labels.update({backlog[0]: True, backlog[1]: True, backlog[2]: False})  # the three sent
    for posting_id, good in labels.items():
        _read(engine, settings, posting_id, good=good, run_id=run_id)

    report = _report(shadow.finish(engine, tmp_path / "day"))

    records = report["candidates"]
    assert isinstance(records, list)
    p = {(r["pool"], r["posting_id"]): float(r["p_good"]) for r in records}  # type: ignore[arg-type]
    slate_scored = [(p[("slate", i)], labels[i]) for i in slate]
    realized = report["realized"]
    assert isinstance(realized, dict)
    assert realized["judged"] == 24 + 3
    # AUC over every judged, scored item, recounted by pairs from the file's own scores.
    every = slate_scored + [(p[("backlog", i)], labels[i]) for i in backlog[:3]]
    assert realized["auc"] == pytest.approx(_pairs_auc(every))
    # Top half of the 24 slate items (12): the model's twelve highest vs the existing first twelve.
    half = realized["slate"]
    assert isinstance(half, dict) and half["judged"] == 24
    by_model = sorted(range(24), key=lambda i: -slate_scored[i][0])[:12]
    assert half["top_half_model"] == pytest.approx(sum(slate_scored[i][1] for i in by_model) / 12)
    assert half["top_half_model"] == pytest.approx(10 / 12)
    assert half["top_half_existing_order"] == pytest.approx(5 / 12)
    # Backlog: three requests sent, two of the three judged good; the model's own top three of
    # the six scored are compared with it.
    backlog_scores = sorted((p[("backlog", i)] for i in backlog), reverse=True)
    block = realized["backlog"]
    assert isinstance(block, dict)
    assert block["realized_good_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert block["top_n"] == 3 and block["sent"] == 3 and block["scored"] == 6
    assert block["predicted_for_model_top_n"] == pytest.approx(
        sum(backlog_scores[:3]) / 3, abs=1e-3
    )
    assert set(block["model_top_picks"]) == set(backlog[3:])  # the juniors it would have sent
    sent = [p[("backlog", i)] for i in backlog[:3]]
    assert block["predicted_for_batch"] == pytest.approx(sum(sent) / 3, abs=1e-3)
    assert block["predicted_for_model_top_n"] > block["predicted_for_batch"]
    # The morning line, in full. The two precision figures differ (83% and 42%), so a line that
    # printed the existing order's figure under "model" and the model's under "ranker" fails.
    predicted = sum(backlog_scores[:3]) / 3
    assert report["summary_line"] == (
        f"value model (shadow): trained on 60 readings, n=27 judged, "
        f"AUC {_pairs_auc(every):.3f}, top half model 83% vs ranker 42%, "
        f"backlog top-3 predicted {predicted:.0%} realized 67%"
    )


def test_a_run_that_judged_nothing_reports_no_metrics_rather_than_zeros(
    env: Path, tmp_path: Path
) -> None:
    engine, settings = _stack(env)
    _history(engine, settings, n=30)
    shadow, _ = _shadow(settings, engine)
    shadow.observe_slate([_post(engine, title=GOOD_TITLE), _post(engine, title=BAD_TITLE)])

    report = _report(shadow.finish(engine, tmp_path / "day"))

    # Nothing was sent, so nothing was passed over: an item is refused only if the gate walked
    # on past it.
    assert [(r["sent"], r["passed_over"]) for r in report["candidates"]] == [(False, False)] * 2  # type: ignore[attr-defined]
    realized = report["realized"]
    assert isinstance(realized, dict)
    assert realized["judged"] == 0 and realized["auc"] is None
    assert realized["slate"] == {"judged": 0, "top_half_model": None,
                                 "top_half_existing_order": None}
    assert report["summary_line"] == (
        "value model (shadow): trained on 60 readings, n=0 judged, AUC n/a, top half model n/a "
        "vs ranker n/a, backlog top-0 predicted n/a realized n/a"
    )


def _gate_world(env: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "ok") -> tuple[
    Engine, Settings
]:
    engine, settings = _stack(env)  # refresh budget 2, backlog budget 3, batch size 13
    _history(engine, settings, n=30)
    monkeypatch.setenv("GATE_FAKE_MODE", mode)
    monkeypatch.setenv("GATE_FAKE_SENIORITY", "yes")
    return engine, settings


@_needs_an_executable_fake
def test_the_refresh_records_what_the_judge_received_not_a_prefix_of_the_candidates(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Budget 2 over A, B, C where the send boundary withholds A's body (D-406): the gate sends B
    and C. The shadow must say so, not mark A and B as sent and C as unsent."""
    from types import SimpleNamespace

    from boardwatch.llm.gate_judge import run_gate_refresh
    from tests.unit.test_lane_body_precondition import JOBRIGHT_PAGE

    engine, settings = _gate_world(env, monkeypatch)
    foreign = _post(engine, title=f"{GOOD_TITLE} foreign", body=JOBRIGHT_PAGE)
    b = _post(engine, title=f"{GOOD_TITLE} b")
    c = _post(engine, title=f"{GOOD_TITLE} c")
    shadow, run_id = _shadow(settings, engine)

    result = run_gate_refresh(
        engine, settings, [SimpleNamespace(posting_id=p) for p in (foreign, b, c)],
        run_id=run_id, observe=shadow.observe_refresh, observe_sent=shadow.sent_refresh,
    )

    assert result.sent == 2
    records = {
        r["posting_id"]: r
        for r in _report(shadow.finish(engine, tmp_path / "day"))["candidates"]  # type: ignore[attr-defined]
    }
    assert {p: records[p]["sent"] for p in (foreign, b, c)} == {foreign: False, b: True, c: True}
    assert records[foreign]["passed_over"] is True
    assert not records[b]["passed_over"] and not records[c]["passed_over"]


@_needs_an_executable_fake
def test_the_backlog_comparison_counts_requests_sent_and_leaves_refused_items_out_of_the_top_picks(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from boardwatch.llm.gate_judge import run_gate_backlog
    from tests.unit.test_lane_body_precondition import JOBRIGHT_PAGE

    engine, settings = _gate_world(env, monkeypatch)
    # Newest first: the refused junior-titled posting leads, the model would love it.
    foreign = _post(engine, title=f"{GOOD_TITLE} foreign", body=JOBRIGHT_PAGE)
    j1 = _post(engine, title=f"{GOOD_TITLE} j1")
    others = [_post(engine, title=f"{BAD_TITLE} s{i}") for i in range(4)]
    order = [foreign, j1, *others]
    _set_first_seen(env, {p: i for i, p in enumerate(order)})
    shadow, run_id = _shadow(settings, engine)

    result = run_gate_backlog(
        engine, settings, _candidates(env, order), run_id=run_id,
        observe=shadow.observe_backlog, observe_sent=shadow.sent_backlog,
    )

    assert result.sent == 3  # j1 and two seniors: the budget skipped the refused body
    report = _report(shadow.finish(engine, tmp_path / "day"))
    block = report["realized"]["backlog"]  # type: ignore[index]
    records = {r["posting_id"]: r for r in report["candidates"]}  # type: ignore[attr-defined]
    assert [records[p]["sent"] for p in order] == [False, True, True, True, False, False]
    assert records[foreign]["passed_over"] is True
    # The last two were never reached (the budget ended the pass): not refused, just unsent.
    assert [records[p]["passed_over"] for p in order] == [True, False, False, False, False, False]
    assert block["top_n"] == 3 and block["sent"] == 3
    assert foreign not in block["model_top_picks"]  # the gate would never have sent it
    assert j1 in block["model_top_picks"] and len(block["model_top_picks"]) == 3


@_needs_an_executable_fake
def test_a_refused_item_at_the_end_of_the_pool_is_passed_over_too(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Budget 3 over [A, B, refused]: the pass ends because the POOL ran out, with two sends
    against a budget of three. The refused item has no later send to prove it was walked past,
    and it scores highest, so it must still be kept out of the model's top picks."""
    from boardwatch.llm.gate_judge import run_gate_backlog
    from tests.unit.test_lane_body_precondition import JOBRIGHT_PAGE

    engine, settings = _gate_world(env, monkeypatch)
    a = _post(engine, title=f"{BAD_TITLE} a")
    b = _post(engine, title=f"{BAD_TITLE} b")
    foreign = _post(engine, title=f"{GOOD_TITLE} foreign", body=JOBRIGHT_PAGE)
    order = [a, b, foreign]
    _set_first_seen(env, {p: i for i, p in enumerate(order)})
    shadow, run_id = _shadow(settings, engine)

    result = run_gate_backlog(
        engine, settings, _candidates(env, order), run_id=run_id,
        observe=shadow.observe_backlog, observe_sent=shadow.sent_backlog,
    )

    assert result.sent == 2
    report = _report(shadow.finish(engine, tmp_path / "day"))
    records = {r["posting_id"]: r for r in report["candidates"]}  # type: ignore[attr-defined]
    assert records[foreign]["passed_over"] is True and records[foreign]["sent"] is False
    block = report["realized"]["backlog"]  # type: ignore[index]
    assert block["top_n"] == 2
    assert set(block["model_top_picks"]) == {a, b}


@_needs_an_executable_fake
def test_fewer_readings_than_requests_still_compares_against_the_top_n_sent(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`wrongcount`: the judge answers one of the three items sent. The budget was spent on three
    requests, so the model's prediction is for its top three, not its top one."""
    from boardwatch.llm.gate_judge import run_gate_backlog

    engine, settings = _gate_world(env, monkeypatch, mode="wrongcount")
    order = [_post(engine, title=f"{GOOD_TITLE} q{i}") for i in range(5)]
    _set_first_seen(env, {p: i for i, p in enumerate(order)})
    shadow, run_id = _shadow(settings, engine)

    result = run_gate_backlog(
        engine, settings, _candidates(env, order), run_id=run_id,
        observe=shadow.observe_backlog, observe_sent=shadow.sent_backlog,
    )

    assert result.sent == 3 and result.judged == 1
    report = _report(shadow.finish(engine, tmp_path / "day"))
    block = report["realized"]["backlog"]  # type: ignore[index]
    assert (block["sent"], block["judged"], block["top_n"]) == (3, 1, 3)
    p = sorted((float(r["p_good"]) for r in report["candidates"]), reverse=True)  # type: ignore[attr-defined]
    assert block["predicted_for_model_top_n"] == pytest.approx(sum(p[:3]) / 3, abs=1e-3)
    assert block["realized_good_rate"] == 1.0  # the one answered item was good


def test_training_uses_only_the_newest_readings_up_to_the_cap(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, settings = _stack(env)
    history = _history(engine, settings, n=30)  # 60 readings, oldest first
    monkeypatch.setattr(vs, "TRAIN_READINGS_CAP", 40)
    with engine.connect() as conn:
        profile = get_profile(conn)
        assert profile is not None
        facts = engine_facts(profile.eligibility_facts_json, settings.config_dir)
        scope = gate_judge_identity(facts, model="sonnet", effort=gate_effort_key("medium"),
                                    target_band="entry")
        newest = load_readings(conn, scope, "entry", limit=40)
    assert [r.posting_id for r in newest] == history[-40:]  # the newest forty, oldest first

    shadow, _ = _shadow(settings, engine)

    assert shadow._header["readings"] == 40 and shadow._header["capped"] is True
    assert shadow._header["trained"] is True


def test_a_configured_floor_above_the_cap_raises_the_cap(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, settings = _stack(env)
    _history(engine, settings, n=30)
    monkeypatch.setattr(vs, "TRAIN_READINGS_CAP", 10)  # the floor, 20, is above it

    shadow, _ = _shadow(settings, engine)

    assert shadow._header["readings"] == 20 and shadow._header["trained"] is True


def test_arrivals_are_scored_and_summed_per_board_for_postings_first_seen_this_run(
    env: Path, tmp_path: Path
) -> None:
    engine, settings = _stack(env)
    _history(engine, settings, n=30)
    old = _post(engine, title=GOOD_TITLE, company="Oldco", first_seen=utcnow() - timedelta(days=3))
    shadow, _ = _shadow(settings, engine)
    time.sleep(0.01)
    # First seen after the run began: three at one board, two at another.
    a = [_post(engine, title=f"{GOOD_TITLE} a{i}", company="Boardone") for i in range(3)]
    b = [_post(engine, title=f"{BAD_TITLE} b{i}", company="Boardtwo") for i in range(2)]
    shadow.observe_slate([old, *a, *b])  # the same postings, scored through the candidate path

    report = _report(shadow.finish(engine, tmp_path / "day"))

    arrivals = report["arrivals"]
    assert isinstance(arrivals, dict) and arrivals["complete"] is True
    assert arrivals["scored"] == 5
    boards = {str(board["slug"]): board for board in arrivals["boards"]}  # type: ignore[attr-defined]
    assert set(boards) == {"boardone", "boardtwo"}  # the posting seen three days ago is not one
    assert (boards["boardone"]["n"], boards["boardtwo"]["n"]) == (3, 2)
    p = {r["posting_id"]: float(r["p_good"]) for r in report["candidates"]}  # type: ignore[attr-defined]
    # Counted a second way: each board's sum is its postings' recorded candidate scores.
    assert boards["boardone"]["p_sum"] == pytest.approx(sum(p[i] for i in a), abs=1e-3)
    assert boards["boardtwo"]["p_sum"] == pytest.approx(sum(p[i] for i in b), abs=1e-3)
    assert boards["boardone"]["p_sum"] > boards["boardtwo"]["p_sum"]


def test_arrival_scoring_past_its_budget_stops_and_says_so(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, settings = _stack(env)
    _history(engine, settings, n=30)
    shadow, _ = _shadow(settings, engine)
    time.sleep(0.01)
    _post(engine, title=GOOD_TITLE)
    monkeypatch.setattr(vs, "ARRIVAL_BUDGET_SECONDS", -1.0)

    arrivals = _report(shadow.finish(engine, tmp_path / "day"))["arrivals"]

    assert isinstance(arrivals, dict)
    assert arrivals["complete"] is False and arrivals["scored"] == 0


def test_a_run_with_no_shadow_work_writes_nothing(env: Path, tmp_path: Path) -> None:
    engine, settings = _stack(env)
    shadow = ValueShadow(settings, insert_run(engine))  # never started
    assert shadow.finish(engine, tmp_path / "day") is None
    assert not (tmp_path / "day").exists()


def test_a_training_failure_never_reaches_the_gate_and_is_raised_at_the_write(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, settings = _stack(env)
    _history(engine, settings, n=30)

    def broken(*_a: object, **_k: object) -> object:
        raise RuntimeError("fit probe")

    monkeypatch.setattr(vs, "train", broken)
    shadow, _ = _shadow(settings, engine)  # `start` does not raise
    shadow.observe_slate([1, 2, 3])  # nor does a pool
    with pytest.raises(RuntimeError, match="fit probe"):
        shadow.finish(engine, tmp_path / "day")
    assert not list((tmp_path / "day").glob("*"))


# ---------------------------------------------------------------------------
# the gate's taps
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_the_backlog_tap_sees_the_candidates_in_the_order_the_gate_sends_them(
    env: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    _configure(env, min_readings=20, backlog_budget=3)
    engine = get_engine(env)
    a, b, c = (_post(engine, title=f"t{n}", slug=f"s{n}") for n in "abc")
    _set_first_seen(env, {a: 0, c: 1, b: 2})  # newest first: a, c, b
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    seen: list[int] = []

    result = run_gate_backlog(
        engine, load_settings(data_dir=env), _candidates(env, [c, b, a]), run_id=None,
        observe=seen.extend,
    )

    assert result.sent == 3
    assert seen == [a, c, b] == _gate_row_order(env)


# ---------------------------------------------------------------------------
# the keystone: it orders nothing
# ---------------------------------------------------------------------------


def _run_world(
    data_dir: Path, apps: Path, *, min_readings: int, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, list[str], Path]:
    """The same store and the same judge, with the model trained (or not, by `min_readings`)."""
    _ready(data_dir)
    settings = _configure(data_dir, min_readings=min_readings, backlog_budget=2, refresh_budget=2)
    engine = get_engine(data_dir)
    _history(engine, settings, n=15)
    titles = [GOOD_TITLE, BAD_TITLE, GOOD_TITLE, BAD_TITLE, GOOD_TITLE, BAD_TITLE]
    for n, title in enumerate(titles):
        _post(engine, title=f"{title} {n}", slug=f"keystone-{n}")
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")
    monkeypatch.setenv("GATE_FAKE_SENIORITY", "yes")
    summary = _depth_pipeline(data_dir, apps, top_n=3)
    tree = sorted(
        str(path.relative_to(apps)) for path in apps.rglob("*")
        if path.is_file() and not path.name.startswith(("value-shadow", "funnel", "morning",
                                                        "near-miss", "digest"))
        and "queue" not in path.parts
    )
    return summary, tree, apps


def _verdict_rows(data_dir: Path) -> list[tuple[str, str, str]]:
    with get_engine(data_dir).connect() as conn:
        return [
            (str(r.title), str(r.verdict), json.dumps(r.raw_output_json["gate_verdict"], sort_keys=True))
            for r in conn.execute(
                select(tables.postings.c.title, tables.eligibility_evaluations.c.verdict,
                       tables.eligibility_evaluations.c.raw_output_json)
                .join(tables.posting_versions,
                      tables.posting_versions.c.posting_id == tables.postings.c.id)
                .join(tables.eligibility_inputs,
                      tables.eligibility_inputs.c.posting_version_id == tables.posting_versions.c.id)
                .join(tables.eligibility_evaluations,
                      tables.eligibility_evaluations.c.input_id == tables.eligibility_inputs.c.id)
                .where(tables.eligibility_evaluations.c.engine_kind == "llm",
                       tables.postings.c.status == "open")
                .order_by(tables.eligibility_evaluations.c.id)
            )
        ]


@_needs_an_executable_fake
def test_the_gate_decides_identically_with_the_model_on_and_off(
    tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant: the score may only be recorded. Two identical stores and judges, one with
    enough readings for the model to train and one without; the slate and its order, the gate's
    tally, every verdict written, and the folders the leads landed in are the same."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg-on"))
    on_summary, on_tree, on_apps = _run_world(
        tmp_path / "on", tmp_path / "apps-on", min_readings=20, monkeypatch=monkeypatch
    )
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg-off"))
    off_summary, off_tree, off_apps = _run_world(
        tmp_path / "off", tmp_path / "apps-off", min_readings=10**6, monkeypatch=monkeypatch
    )

    def facts(summary: object) -> object:
        return (
            [(lead.title, lead.tier) for lead in summary.tailored],  # type: ignore[attr-defined]
            summary.gate_judged, summary.gate_eligible, summary.gate_ineligible,  # type: ignore[attr-defined]
            summary.gate_backlog_sent, summary.gate_backlog_judged,  # type: ignore[attr-defined]
            summary.fatal,  # type: ignore[attr-defined]
        )

    assert facts(on_summary) == facts(off_summary)
    assert on_summary.tailored, "the run must deliver leads for this comparison to mean anything"  # type: ignore[attr-defined]
    assert on_tree == off_tree
    assert _verdict_rows(tmp_path / "on") == _verdict_rows(tmp_path / "off")
    # And the two really differ in what they recorded: the model exists in one run only.
    (on_file,) = on_apps.glob("*/value-shadow-*.json")
    (off_file,) = off_apps.glob("*/value-shadow-*.json")
    on_report, off_report = _report(on_file), _report(off_file)
    assert on_report["trained"] is True and off_report["trained"] is False
    slate = [r for r in on_report["candidates"] if r["pool"] == "slate"]  # type: ignore[attr-defined]
    assert slate, "the shadow recorded the slate it watched"
    # The slate positions are the order the gate wrote its rows in (the ranker's order): the
    # 30 history rows come first, then the three slate leads.
    by_position = sorted(slate, key=lambda r: r["position"])
    assert [r["posting_id"] for r in by_position] == _gate_row_order(tmp_path / "on")[30:33]
    # The fixture can tell a reordering from none: the model's order is not the ranker's.
    assert [r["rank_by_p"] for r in by_position] != [1, 2, 3]
    assert "candidates" not in off_report


# ---------------------------------------------------------------------------
# failure direction
# ---------------------------------------------------------------------------


@_needs_an_executable_fake
def test_a_shadow_failure_is_recorded_above_the_morning_digest_and_never_fails_the_run(
    env: Path, tmp_path: Path, fake_claude: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ready(env)
    _configure(env, min_readings=20)
    _post(get_engine(env), title=GOOD_TITLE)
    monkeypatch.setenv("GATE_FAKE_MODE", "ok")

    def broken(*_a: object, **_k: object) -> object:
        raise RuntimeError("shadow probe")

    monkeypatch.setattr(vs.ValueShadow, "finish", broken)

    summary = _depth_pipeline(env, tmp_path / "apps", top_n=2)

    assert summary.fatal is None, summary.fatal
    assert "value shadow not written: shadow probe" in summary.errors
    assert summary.tailored, "the run still delivered"
    assert summary.morning is not None
    # Above `_emit_morning`: the digest the owner reads carries the note.
    assert "value shadow not written: shadow probe" in summary.morning.markdown_path.read_text()


@_needs_an_executable_fake
def test_a_run_with_the_gate_off_makes_no_shadow(env: Path, tmp_path: Path) -> None:
    _ready(env)
    _post(get_engine(env), title=GOOD_TITLE)
    summary = _depth_pipeline(env, tmp_path / "apps", top_n=2)
    assert not list((tmp_path / "apps").glob("*/value-shadow-*"))
    assert "value_shadow" not in [stage.name for stage in summary.stage_durations]
