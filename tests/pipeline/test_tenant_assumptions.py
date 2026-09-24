"""T185 (DESIGN-T183 A2) — the funnel reports whether each ranker/review gate decided on the
TENANT's data.

These gates hard-code a US, software, entry-level tenant and cannot abstain. The report changes
no decision; it makes a second tenant's silent fall-through visible as an abstain instead of a
gate that looks like it fired. Driven through `run_pipeline` on a seeded store and read back off
the published JSON, the only place a reader sees it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from sqlalchemy import insert, update

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import load_settings
from boardwatch.delivery.review_gate import REVIEW_DIR, LaneDecision
from boardwatch.pipeline import runner as runner_mod
from boardwatch.pipeline.runner import run_pipeline
from boardwatch.rank import tenant_assumptions as tenant_mod
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from tests.pipeline.test_pipeline_run import _ready

_NO_COUNTRIES = "missing_profile_field:target_countries"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(runner_mod, "send_heartbeat", lambda: None)
    return tmp_path / "data"


def _set_facts(data_dir: Path, facts: dict[str, Any]) -> None:
    with get_engine(data_dir).begin() as conn:
        conn.execute(update(tables.profile).values(eligibility_facts_json=facts))


def _add_posting(data_dir: Path, slug: str, title: str, locations: list[str]) -> None:
    body = f"{title}. Bachelor's degree preferred."
    now = utcnow()
    with get_engine(data_dir).begin() as conn:
        company_id = conn.execute(
            insert(tables.companies).values(
                name=slug.title(), provider="greenhouse", slug=slug, source="user", watched=True
            )
        ).inserted_primary_key[0]
        job_id = conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        posting_id = conn.execute(
            insert(tables.postings).values(
                company_id=company_id, provider_posting_id=f"p-{slug}", title=title,
                normalized_title=title.lower(), url=f"https://example.test/{slug}",
                locations_json=locations, remote_policy="onsite", first_seen_at=now,
                last_seen_at=now, status="open", consecutive_missing=0,
                content_hash=f"h-{slug}", body_text=body, job_id=job_id,
            )
        ).inserted_primary_key[0]
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", body_text=body,
                captured_at=now, capture_reason="new",
            )
        )


def _run(data_dir: Path, out_root: Path, *, mode: str) -> dict[str, Any]:
    settings = load_settings(data_dir=data_dir).model_copy(update={"location_filter_mode": mode})
    summary = run_pipeline(
        get_engine(data_dir),
        settings,
        console=Console(quiet=True),
        out_root=out_root,
        resume_path=settings.config_dir / "resume.yaml",
        skip_scan=True,
    )
    assert summary.funnel is not None, "guard: the funnel must have been written"
    return json.loads(summary.funnel.json_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _seed_tenant2(data_dir: Path) -> None:
    """DESIGN-T183 §3's second tenant, DATA ONLY: a Canadian nurse whose field is not in the
    bundled catalog, with P1/P2/P3/P5 from the smoke spec beside `_ready`'s software posting."""
    _ready(data_dir)
    _set_facts(
        data_dir,
        {
            "career_field": "clinical_care",
            "work_authorization": {"status": "citizen", "jurisdiction": "ca"},
            "total_years_experience": 8,
            "highest_degree": "bachelor",
            "employment_type_preference": "open_to_contract",
        },
    )
    _add_posting(data_dir, "p1", "Registered Nurse", ["Toronto, ON"])
    _add_posting(data_dir, "p2", "Registered Nurse", ["Boston, MA"])
    _add_posting(data_dir, "p3", "Physiotherapist", ["Remote"])
    _add_posting(data_dir, "p5", "Infirmière (H/F)", ["Montréal"])


def test_the_funnel_reports_each_gate_for_a_software_tenant(env: Path, tmp_path: Path) -> None:
    """Mit-shaped facts: `career_field: software` grounds the role, zero-signal and seniority
    field gates, so they report what they did, with no missing-field abstain. No profile field
    names target countries yet, so both location gates abstain on every posting they saw."""
    _ready(env)
    _set_facts(env, {"career_field": "software"})
    _add_posting(env, "nurse", "Registered Nurse", ["Remote"])
    _add_posting(env, "toronto", "Software Engineer", ["Toronto, ON"])

    payload = _run(env, tmp_path / "apps", mode="hard")

    report = payload["tenant_assumptions"]
    ranker = report["ranker"]
    assert set(ranker) == {"location", "foreign_ad", "role", "zero_signal", "seniority_field"}
    assert ranker["role"]["fired"] == 1, ranker["role"]  # the nurse title, vetoed on its merits
    assert ranker["role"]["fired_on_default"] == 0
    for gate in ("role", "zero_signal", "seniority_field"):
        assert not any(
            reason.startswith("missing_profile_field") for reason in ranker[gate]["abstained"]
        ), (gate, ranker[gate])
    location = ranker["location"]
    assert location["fired"] == 0
    assert location["abstained"] == {_NO_COUNTRIES: location["considered"]}, location
    assert location["considered"] == 3, location
    assert location["fired_on_default"] == 1, location  # Toronto, dropped on the US default
    assert report["review"]["location"]["abstained"] == {
        _NO_COUNTRIES: report["review"]["location"]["considered"]
    }
    assert payload["reconciles"] is True


@pytest.mark.parametrize("mode", ["soft", "hard"])
def test_a_second_tenant_sees_the_role_and_location_gates_abstain_not_fire(
    env: Path, tmp_path: Path, mode: str
) -> None:
    """The falsifier: a gate that reports `fired` while reading a field tenant 2 lacks. Every
    decision the role and location gates made for this tenant rests on nothing it declared, so
    each one is an abstain naming the field, and the drops it still makes are `fired_on_default`.
    """
    _seed_tenant2(env)

    payload = _run(env, tmp_path / "apps", mode=mode)

    report = payload["tenant_assumptions"]
    ranker, review = report["ranker"], report["review"]
    role = ranker["role"]
    assert role["considered"] == 5 if mode == "soft" else role["considered"] >= 1
    assert role["fired"] == 0, role
    assert role["abstained"] == {"no_role_pack:clinical_care": role["considered"]}, role
    assert role["fired_on_default"] >= 1, role  # the nurse titles, vetoed as `not_swe`
    for gate in ("zero_signal", "seniority_field"):
        assert ranker[gate]["fired"] == 0, (gate, ranker[gate])
        assert sum(ranker[gate]["abstained"].values()) == ranker[gate]["considered"]
    if mode == "hard":
        location = ranker["location"]
        assert location["considered"] == 5, location
        assert location["fired"] == 0, location
        assert location["abstained"] == {_NO_COUNTRIES: 5}, location
        assert location["fired_on_default"] >= 1, location  # Toronto reads `non_us`
    else:
        assert "location" not in ranker, "soft mode never runs the ranker's location clause"
    for gate in ("location", "role"):
        assert review[gate]["fired"] == 0, (gate, review[gate])
        assert sum(review[gate]["abstained"].values()) == review[gate]["considered"] >= 1
    assert review["location"]["abstained"] == {_NO_COUNTRIES: review["location"]["considered"]}
    assert payload["reconciles"] is True


def test_a_profile_with_no_career_field_names_the_missing_field(
    env: Path, tmp_path: Path
) -> None:
    _ready(env)
    _set_facts(env, {})

    payload = _run(env, tmp_path / "apps", mode="soft")

    ranker = payload["tenant_assumptions"]["ranker"]
    for gate in ("role", "zero_signal", "seniority_field"):
        assert ranker[gate]["fired"] == 0, (gate, ranker[gate])
        assert ranker[gate]["abstained"] == {
            "missing_profile_field:career_field": ranker[gate]["considered"]
        }, (gate, ranker[gate])


def test_the_report_changes_no_other_funnel_key(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL: the same seeded run with the report produced and with it suppressed. Only the
    `tenant_assumptions` key may differ; every other key is byte-identical once the per-run
    clocks and the two runs' own temp roots are set aside."""
    volatile = {"started_at", "finished_at", "stage_durations", "tenant_assumptions"}

    def run_once(root: Path) -> tuple[str, Any]:
        monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(root / "cfg"))
        _seed_tenant2(root / "data")
        payload = _run(root / "data", root / "apps", mode="hard")
        rest = {key: value for key, value in payload.items() if key not in volatile}
        text = json.dumps(rest, sort_keys=True, default=str).replace(str(root), "<root>")
        return text, payload["tenant_assumptions"]

    with_report, report = run_once(tmp_path / "a")
    monkeypatch.setattr(tenant_mod.TenantAssumptionTally, "observe", lambda self, gate, **kw: None)
    without_report, suppressed = run_once(tmp_path / "b")

    assert report["ranker"] and suppressed["ranker"] == {}, "guard: suppression must have bitten"
    assert with_report == without_report


def test_a_lead_held_above_the_tenant_gates_is_not_counted_as_considered(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T185 review. `classify` returns at the form-question hold, above every tenant gate, so
    that lead was never put to the location, role or judge gates and must not appear in their
    `considered` — the old tally reported a `missing_profile_field:target_countries` abstain for
    a location gate that never ran."""
    _ready(env)
    _set_facts(env, {"career_field": "software"})
    _add_posting(env, "stopped", "Software Engineer, Stopped", ["Remote"])
    real_classify = runner_mod.classify
    seen: list[str] = []

    def stopped_first(**kwargs: Any) -> LaneDecision:
        # The RUN's pre-tailor split (`runner._lead_lanes`) is the call the tally observes;
        # the queue's own later `lane_decision` is a different call site and is left alone.
        seen.append(kwargs["title"])
        if kwargs["title"] == "Software Engineer, Stopped":
            return LaneDecision(REVIEW_DIR, "form_question_hard_stop")
        return real_classify(**kwargs)

    monkeypatch.setattr(runner_mod, "classify", stopped_first)

    payload = _run(env, tmp_path / "apps", mode="soft")

    assert seen.count("Software Engineer, Stopped") == 1, seen  # guard: the hold was applied
    split = len(seen)
    assert split >= 2, seen
    review = payload["tenant_assumptions"]["review"]
    for gate in ("location", "role", "judge_seniority"):
        assert review[gate]["considered"] == split - 1, (gate, review[gate])
    assert payload["reconciles"] is True


def test_a_confirmed_us_posting_never_reached_the_foreign_ad_gate(env: Path, tmp_path: Path) -> None:
    """T185 review. In hard mode `hard_filter_verdict` puts the ad-marker check only to a posting
    whose location is not a confirmed US one, so a cleared "Austin, TX" posting is considered by
    the location gate and NOT by the foreign-ad gate; a "Remote" posting reaches both."""
    _ready(env)
    _set_facts(env, {"career_field": "software"})
    _add_posting(env, "austin", "Software Engineer", ["Austin, TX"])
    _add_posting(env, "remote", "Software Engineer", ["Remote"])

    payload = _run(env, tmp_path / "apps", mode="hard")

    ranker = payload["tenant_assumptions"]["ranker"]
    assert ranker["location"]["considered"] >= 2, ranker["location"]
    assert ranker["foreign_ad"]["considered"] == ranker["location"]["considered"] - 1, ranker
    assert payload["reconciles"] is True
