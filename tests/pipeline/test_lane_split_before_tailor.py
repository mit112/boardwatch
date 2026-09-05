"""T43 — the apply/review lane split moves BEFORE the tailor loop.

Before this ticket, `run_pipeline` tailored every shortlisted lead and the lane split ran
later, at delivery-queue sync time (`delivery/queue.py:sync_queue`), which only ever picked a
folder for a résumé the pipeline had already rendered. That wasted the expensive render (4.35s
to 64.05s per lead, measured) on review-lane leads the owner has to read before applying to
anyway. The fix computes `review_gate.lane` — the ONE lane definition, the same one
`delivery/queue.py` and `delivery_queries.py` already call — once, before the loop, and tailors
apply-lane leads only; a review-lane lead is still DELIVERED (a real folder, a `resume_tailored`
artifact row, the JD and apply link), just with no PDF and `pending_tailor=True`.

Every posting here shares one seeded JD body (`test_pipeline_run.BODY`) that trips no
eligibility rule at all — the real catalog finds no requirement in it, so the engine's own
zero-row branch returns `uncertain`, which `review_gate.classify` routes to review under
`no_requirements_found`. That is what makes a PLAIN `_seed_posting` posting a review-lane lead
with no extra setup. An apply-lane lead needs a genuinely `eligible` verdict, which this module
fabricates directly in `eligibility_evaluations`/`eligibility_requirements` under the run's own
(profile_hash, rules_hash) identity — the real catalog has nothing in `BODY` to hang an
`eligible` verdict on, and authoring a catalog-satisfying JD is not what this ticket is about.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import insert, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.eligibility.engine import ENGINE_KIND, engine_version
from boardwatch.eligibility.preflight import current_identity
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.reports.tailor import run_tailor
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.delivery_queries import delivered_unapplied
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.conftest import write_test_resume_template
from tests.pipeline.test_pipeline_run import INIT_INPUT, _cli, _seed_posting


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Defined here, not imported: importing a same-named fixture shadows it at every test
    signature and ruff flags the redefinition (F811)."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _ready(data_dir: Path) -> None:
    assert _cli(data_dir, ["init"], INIT_INPUT).exit_code == 0
    assert _cli(data_dir, ["tailor", "init"]).exit_code == 0
    write_test_resume_template(load_settings(data_dir=data_dir).config_dir)


def _force_eligible(data_dir: Path, posting_id: int) -> None:
    """Fabricate a CURRENT `eligible` evaluation for `posting_id`, under the profile's real
    (profile_hash, rules_hash) identity, so `run_eligibility`'s anti-join skips re-evaluating
    it and `current_verdicts` reads this verdict back as-is. One `eligibility_requirements`
    row (preferred, met) keeps `no_requirement_rows` False without setting either unconfirmed
    flag, so `review_gate.classify` reaches its `eligible` short-circuit — an apply-lane lead.
    """
    settings = load_settings(data_dir=data_dir)
    engine = get_engine(data_dir)
    with engine.connect() as conn:
        identity = current_identity(conn, settings)
    assert identity is not None, "the profile must be seeded before forcing a verdict"
    profile_hash, rules_hash = identity
    now = utcnow()
    with engine.begin() as conn:
        version_id = (
            conn.execute(
                select(tables.posting_versions.c.id)
                .where(tables.posting_versions.c.posting_id == posting_id)
                .order_by(tables.posting_versions.c.id.desc())
            )
            .scalars()
            .first()
        )
        input_id = conn.execute(
            insert(tables.eligibility_inputs).values(
                posting_version_id=version_id,
                profile_hash=profile_hash,
                profile_snapshot_json={},
                rules_hash=rules_hash,
                rules_snapshot_json={},
                input_fingerprint=f"t43-fp-{posting_id}",
                created_at=now,
            )
        ).inserted_primary_key[0]
        eval_id = conn.execute(
            insert(tables.eligibility_evaluations).values(
                input_id=input_id,
                engine_kind=ENGINE_KIND,
                engine_version=engine_version(),
                verdict="eligible",
                created_at=now,
            )
        ).inserted_primary_key[0]
        conn.execute(
            insert(tables.eligibility_requirements).values(
                evaluation_id=eval_id,
                ordinal=0,
                rule_id="skill_pref:python",
                requiredness="preferred",
                requirement_text="Python",
                jd_locator_json={},
                disposition="met",
            )
        )


def _seed_slate(data_dir: Path) -> tuple[list[int], list[int]]:
    """3 apply-lane postings (forced `eligible`) + 2 review-lane postings (plain — the shared
    seeded body trips no eligibility rule, so the real engine abstains to `uncertain` with zero
    requirement rows, which routes to review under `no_requirements_found`). Returns
    (apply_ids, review_ids)."""
    apply_ids = [_seed_posting(data_dir, slug=f"apply{i}") for i in range(3)]
    for posting_id in apply_ids:
        _force_eligible(data_dir, posting_id)
    review_ids = [_seed_posting(data_dir, slug=f"review{i}") for i in range(2)]
    return apply_ids, review_ids


def _pipeline(data_dir: Path, out_root: Path, **kw: object):
    settings = load_settings(data_dir=data_dir)
    return run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
        **kw,
    )


def _fake_ok(tex: Path, pdf: Path) -> CompileOutcome:
    pdf.write_bytes(b"%PDF-1.7\n%stub\n")
    return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


def test_only_apply_lane_leads_are_tailored_review_lane_leads_are_pending(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3 apply + 2 review: exactly 3 leads render a PDF and exactly 2 carry `pending_tailor`,
    against a slate unchanged code renders all 5 of."""
    _ready(env)
    apply_ids, review_ids = _seed_slate(env)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_ok)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.fatal is None, summary.fatal
    assert len(summary.tailored) == 5, "both lanes must still be delivered, not dropped"

    # Asserted BEFORE `pending_tailor` is ever read: unchanged code has no such attribute at
    # all, and the point of this test is a behavioural failure (rendered a wrong SET of leads),
    # never a structural one (AttributeError) — this line alone is already false pre-T43,
    # since unchanged code renders every one of the 5, not just the 3 apply-lane leads.
    rendered_ids = {lead.posting_id for lead in summary.tailored if lead.pdf_built}
    assert rendered_ids == set(apply_ids), (
        f"expected exactly the 3 apply-lane leads rendered, got {rendered_ids}"
    )
    assert len(rendered_ids) == 3

    pending_ids = {lead.posting_id for lead in summary.tailored if lead.pending_tailor}
    assert pending_ids == set(review_ids), (
        f"expected exactly the 2 review-lane leads pending, got {pending_ids}"
    )
    assert len(pending_ids) == 2
    # A pending lead is never both: pdf_built and pending_tailor are mutually exclusive.
    assert rendered_ids.isdisjoint(pending_ids)


def test_review_lane_lead_reaches_the_delivery_queue_with_no_pdf(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A review-lane lead must still reach `delivered_unapplied` — the delivery queue's own
    read is rooted at `artifacts` (`delivery_queries._delivered_select` JOINs FROM it), so a
    lead with no artifact row at all would never appear in the queue, silently. This is the
    concrete shape of `queue._sync_locked`/`_reconcile_locked`'s PDF-less-lead question."""
    _ready(env)
    _apply_ids, review_ids = _seed_slate(env)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_ok)

    _pipeline(env, tmp_path / "apps")

    engine = get_engine(env)
    with engine.connect() as conn:
        rows = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    for posting_id in review_ids:
        assert posting_id in rows, f"review-lane lead {posting_id} never reached the queue"
        assert rows[posting_id].pdf_uri is None


def test_promoting_a_review_lead_renders_it_and_supersedes_the_pending_row(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`boardwatch tailor run <posting_id>` — the existing on-demand render command — writes a
    fresh `resume_tailored` artifact row with a real PDF and no `pending_tailor` marker.
    `delivered_unapplied`'s recency ordering (`_supersedes`) already prefers the newer row, so
    the lead reads as rendered with no explicit "clear the marker" step."""
    _ready(env)
    _apply_ids, review_ids = _seed_slate(env)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_ok)
    _pipeline(env, tmp_path / "apps")

    promoted_id = review_ids[0]
    settings = load_settings(data_dir=env)
    engine = get_engine(env)
    result = run_tailor(
        engine,
        settings,
        promoted_id,
        resume_path=settings.config_dir / "resume.yaml",
        out_dir=tmp_path / "promoted",
    )
    assert result.pdf_path is not None, "the promotion render itself must produce a real PDF"

    with engine.connect() as conn:
        rows = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
    assert rows[promoted_id].pdf_uri is not None, "promotion must supersede the pending row"


def test_b2_instrument_counts_the_apply_lane_not_every_delivered_lead(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2 (D-477) is apply-lane leads with a compiled PDF — 100%. The funnel's `pdf` stage must
    read 3/3 against this slate, never 3/5: a pending-tailor review lead never entered a
    render, so it must not count against the stage the way a real tailor failure would."""
    _ready(env)
    _seed_slate(env)
    monkeypatch.setattr("boardwatch.reports.tailor._default_runner", _fake_ok)

    summary = _pipeline(env, tmp_path / "apps")

    assert summary.funnel is not None, "no funnel artifact was written"
    data = json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))
    pdf_stage = next(stage for stage in data["stages"] if stage["name"] == "pdf")
    assert pdf_stage["entered"] == 3, pdf_stage
    assert pdf_stage["advanced"] == 3, pdf_stage
