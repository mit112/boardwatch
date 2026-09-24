"""P0 item 4: the new manifest hashes (`config_hash`, `profile_row_hash`), and T111's sixth.

These pin the claims the manifest makes and could get wrong: that the config hash tracks exactly
the decision-relevant settings and nothing else, that it FAILS closed on an unclassified field
rather than silently covering the wrong set, and — since T111 — that `routing_hash` sees the
routing knobs those hashes deliberately do not, with the same closure and without moving a single
one of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.core.settings import GateTier, LLMTier, Settings
from boardwatch.eligibility.engine import engine_version
from boardwatch.reports import manifest
from boardwatch.reports.manifest import (
    UnclassifiedRoutingFieldError,
    UnclassifiedSettingError,
    config_hash,
    policy_version,
    profile_row_hash,
    routing_hash,
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {"data_dir": tmp_path / "data", "config_dir": tmp_path / "cfg"}
    base.update(overrides)
    return Settings(**base)


def test_config_hash_is_stable_for_the_same_settings(tmp_path: Path) -> None:
    assert config_hash(_settings(tmp_path)) == config_hash(_settings(tmp_path))


def test_a_decision_relevant_change_changes_the_hash(tmp_path: Path) -> None:
    base = config_hash(_settings(tmp_path))
    assert config_hash(_settings(tmp_path, location_filter_mode="hard")) != base
    assert config_hash(_settings(tmp_path, recency_half_life_days=30.0)) != base
    assert config_hash(_settings(tmp_path, llm=LLMTier(enabled=True, provider="anthropic"))) != base


def test_a_machine_local_or_throughput_change_does_not_change_the_hash(tmp_path: Path) -> None:
    """scan_workers, notify and max_calls_per_run are OUT — they must not move the hash, or a
    reproducibility check would fire on a change that cannot alter which postings become leads."""
    base = config_hash(_settings(tmp_path))
    assert config_hash(_settings(tmp_path, scan_workers=8)) == base
    assert config_hash(_settings(tmp_path, detail_fetch_budget=999)) == base
    assert config_hash(_settings(tmp_path, reap_stale_after_hours=1)) == base
    assert config_hash(_settings(tmp_path, fetch_deadline_seconds=5.0)) == base
    assert config_hash(_settings(tmp_path, llm=LLMTier(max_calls_per_run=7))) == base


def test_a_data_dir_change_does_not_change_the_hash(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("elsewhere")
    assert config_hash(_settings(tmp_path)) == config_hash(
        Settings(data_dir=other, config_dir=other)
    )


def test_config_hash_fails_closed_on_an_unclassified_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a newly-added Settings field by dropping one from the classification: the hash
    must refuse rather than quietly cover a different set of fields."""
    monkeypatch.setattr(
        manifest, "_CONFIG_RELEVANT", manifest._CONFIG_RELEVANT - {"location_filter_mode"}
    )
    with pytest.raises(UnclassifiedSettingError):
        config_hash(_settings(tmp_path))


def test_profile_row_hash_distinguishes_missing_from_empty() -> None:
    """A null column and an empty list are different inputs; folding them would let a profile
    that dropped every exclude-title hash the same as one that never had any."""
    missing = profile_row_hash(
        skills=["python"], target_titles=None, exclude_titles=None,
        locations=None, remote_only=False,
    )
    empty = profile_row_hash(
        skills=["python"], target_titles=[], exclude_titles=[],
        locations=[], remote_only=False,
    )
    assert missing != empty


def test_profile_row_hash_tracks_exclude_titles() -> None:
    base = profile_row_hash(
        skills=["python"], target_titles=["swe"], exclude_titles=["manager"],
        locations=["remote"], remote_only=True,
    )
    changed = profile_row_hash(
        skills=["python"], target_titles=["swe"], exclude_titles=["manager", "sales"],
        locations=["remote"], remote_only=True,
    )
    assert base != changed


def test_profile_row_hash_tracks_the_skill_taxonomy() -> None:
    """The taxonomy is user-overridable and, since the zero-signal veto, decides a drop bucket.

    Without it in the identity an operator could edit {config_dir}/taxonomy.yaml, change which
    postings are dropped as having no recognised requirement term, and the manifest would still
    report two runs as identical — the same failure the leveling catalog's digest closes.
    """
    base = dict(
        skills=["python"], target_titles=[], exclude_titles=[], locations=[], remote_only=False,
        target_seniority_band="entry", leveling_digest="lev",
    )
    assert profile_row_hash(**base, taxonomy_version="aaa") != profile_row_hash(
        **base, taxonomy_version="bbb"
    )


_TAXONOMY_ONE = """
patterns:
  - name: Python
    category: language
    pattern: "\\\\bPython\\\\b"
"""
# One pattern MORE, and none of it appears in the profile text below. That is the case the
# manifest docstring names: `skills` is the taxonomy applied to the operator's own text, so it
# sits still here while the set of postings the zero-signal veto drops changes. If the identity
# were covered "indirectly through `skills`", this fixture would not move either hash.
_TAXONOMY_TWO = _TAXONOMY_ONE + """  - name: Kubernetes
    category: platform
    pattern: "\\\\bKubernetes\\\\b"
"""


def test_taxonomy_drift_moves_both_identities(tmp_path: Path) -> None:
    """The manifest hash AND the permanent-disposition stamp, over the two production callers.

    Two identities, both derived from `profile_row_hash`, reached through the two call sites
    that actually build them — `pipeline.funnel_writer.collect_run_funnel` and
    `pipeline.policy.run_policy_version`. Asserting the pure function alone would not catch a
    call site that never passed the argument, which is the failure mode a defaulted parameter
    invites. `run_preflight` is deliberately NOT run, so `profile.skills_json` is identical
    across both halves and the taxonomy version is the only input that moved.
    """
    from boardwatch.pipeline.funnel_writer import collect_run_funnel
    from boardwatch.pipeline.policy import run_policy_version
    from boardwatch.reports.run_funnel import ScanContext
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import insert_run, save_profile

    settings = _settings(tmp_path)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer who writes Python.", target_titles=[],
            exclude_titles=[], locations=[], remote_only=False, skills=["Python"],
            taxonomy_version="pinned", resume_max_pages=1,
        )
    run_id = insert_run(engine)

    def _identities() -> tuple[str | None, str]:
        funnel = collect_run_funnel(
            engine, settings, run_id=run_id, scan=ScanContext(ran=False), shortlist=None,
            tailored=[], tailor_failed=0, projection_ran=False, rewrite_rows=[],
            # This synthetic funnel times no run, and `None` is the honest report for that —
            # never `()`, which would claim a timed run that reached no stage boundary.
            lanes=[], stage_durations=None, errors=[], fatal=None,
        )
        with engine.connect() as conn:
            return funnel.manifest.profile_row_hash, run_policy_version(conn, settings)

    (settings.config_dir / "taxonomy.yaml").write_text(_TAXONOMY_ONE, encoding="utf-8")
    first_manifest, first_stamp = _identities()
    (settings.config_dir / "taxonomy.yaml").write_text(_TAXONOMY_TWO, encoding="utf-8")
    second_manifest, second_stamp = _identities()

    assert first_manifest is not None and second_manifest is not None
    assert first_manifest != second_manifest, "the manifest called two runs identical"
    assert first_stamp != second_stamp, "a permanent disposition would carry the wrong policy"


def test_role_taxonomy_drift_moves_both_identities(tmp_path: Path) -> None:
    """The user's role taxonomy decides the role gate's drop, over the same two callers.

    No file, then a bundled one, then a gathered one: each is a different ranker policy, so the
    manifest hash and the permanent-disposition stamp must move at every step.
    """
    from boardwatch.pipeline.funnel_writer import collect_run_funnel
    from boardwatch.pipeline.policy import run_policy_version
    from boardwatch.rank.role_taxonomy import write_role_taxonomy
    from boardwatch.reports.run_funnel import ScanContext
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.queries import insert_run, save_profile

    settings = _settings(tmp_path)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="A profile.", target_titles=[], exclude_titles=[], locations=[],
            remote_only=False, skills=[], taxonomy_version="pinned", resume_max_pages=1,
        )
    run_id = insert_run(engine)

    def _identities() -> tuple[str | None, str]:
        funnel = collect_run_funnel(
            engine, settings, run_id=run_id, scan=ScanContext(ran=False), shortlist=None,
            tailored=[], tailor_failed=0, projection_ran=False, rewrite_rows=[],
            lanes=[], stage_durations=None, errors=[], fatal=None,
        )
        with engine.connect() as conn:
            return funnel.manifest.profile_row_hash, run_policy_version(conn, settings)

    absent = _identities()
    write_role_taxonomy(settings.config_dir, {"version": 1, "field": "software", "bundled": True})
    bundled = _identities()
    write_role_taxonomy(
        settings.config_dir,
        {"version": 1, "field": "widgetry",
         "role_families": [{"id": "inspection", "title_words": ["widget inspector"]}]},
    )
    gathered = _identities()
    for index in (0, 1):
        assert len({absent[index], bundled[index], gathered[index]}) == 3, index


# ------------------------------------------------------- T111: the sixth value, and its closure

#: The five values `routing_hash` must not move. Named as a list so each assertion below is
#: explicit rather than a loop over whatever the manifest happens to expose — this is the
#: assertion that keeps a routing change from reopening a permanent disposition, and a test that
#: silently checked four of five would not say so.
def _five(settings: Settings) -> dict[str, str | None]:
    return {
        "code_fingerprint": engine_version(),
        "config_hash": config_hash(settings),
        # The three profile-derived values are pure functions of the PROFILE, not of `Settings`,
        # so they are computed over a fixed profile here: a routing knob cannot reach them at all,
        # and pinning them makes that structural fact an assertion rather than an assumption.
        "profile_row_hash": profile_row_hash(
            skills=["python"], target_titles=["swe"], exclude_titles=[], locations=["Boston"],
            remote_only=False, target_seniority_band="entry", leveling_digest="lev",
            taxonomy_version="tax",
        ),
        "profile_facts_hash": "facts-abc",
        "rules_hash": "rules-abc",
    }


def test_flipping_the_seniority_hold_moves_the_sixth_value_and_only_the_sixth(
    tmp_path: Path,
) -> None:
    """**The T111 defect and its guard in one test.**

    The first block is the CHARACTERIZATION and it passed before this shipped: astra's probe
    measured that flipping `seniority_hold` leaves `config_hash` byte-identical, so two runs can
    carry identical five-hash manifests and route every lead differently — and B8's 14-day
    evidence is read against those manifests.

    The second block is what T111 adds. The third is the one that keeps dispositions from
    reopening: all five existing values are asserted EXPLICITLY, because `policy_version` is
    composed from them and any one of them moving would re-stamp every permanent decision.
    """
    off = _settings(tmp_path, gate=GateTier(seniority_hold=False))
    on = _settings(tmp_path, gate=GateTier(seniority_hold=True))

    assert config_hash(off) == config_hash(on)
    assert routing_hash(off) != routing_hash(on)

    before, after = _five(off), _five(on)
    assert before["code_fingerprint"] == after["code_fingerprint"]
    assert before["config_hash"] == after["config_hash"]
    assert before["profile_row_hash"] == after["profile_row_hash"]
    assert before["profile_facts_hash"] == after["profile_facts_hash"]
    assert before["rules_hash"] == after["rules_hash"]
    assert policy_version(**before) == policy_version(**after)  # type: ignore[arg-type]


def test_the_gate_effort_moves_config_hash_like_the_model(tmp_path: Path) -> None:
    """`effort` is classified beside `model`: the same judge reasoning harder or less can
    return a different verdict for the same JD, so it re-stamps `policy_version` exactly as a
    model switch does. The model pair is the control that the comparison can discriminate."""
    unset = config_hash(_settings(tmp_path))

    assert config_hash(_settings(tmp_path, gate=GateTier(effort="medium"))) != unset
    assert config_hash(_settings(tmp_path, gate=GateTier(effort="low"))) != config_hash(
        _settings(tmp_path, gate=GateTier(effort="medium"))
    )
    assert config_hash(_settings(tmp_path, gate=GateTier(model="haiku"))) != unset


def test_the_other_routing_knobs_move_the_sixth_value_too(tmp_path: Path) -> None:
    """`seniority_hold` is the knob F6 was raised on, not the only one it named. Each of these is
    excluded from `config_hash` for a reason that is correct about VERDICTS and silent about
    lanes: the three gate knobs decide which delivered leads carry a judge verdict when the lane
    split runs, and the form budget decides which leads have a form to be hard-stopped by."""
    base = routing_hash(_settings(tmp_path))

    assert routing_hash(_settings(tmp_path, gate=GateTier(batch_size=7))) != base
    assert routing_hash(_settings(tmp_path, gate=GateTier(call_timeout_s=30))) != base
    assert routing_hash(_settings(tmp_path, gate=GateTier(depth=60))) != base
    assert routing_hash(_settings(tmp_path, form_question_fetch_budget=0)) != base


def test_an_acquisition_or_machine_local_change_does_not_move_the_sixth_value(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The control the test above needs. A fingerprint that moved on everything would satisfy it
    for the wrong reason and would make every pair of runs incomparable — which is the same as
    having no segmentation at all. Acquisition changes how much corpus ARRIVES and machine-local
    paths change nothing; neither can put a delivered lead in a different lane."""
    base = routing_hash(_settings(tmp_path))
    other = tmp_path_factory.mktemp("elsewhere")

    assert routing_hash(_settings(tmp_path, scan_workers=8)) == base
    assert routing_hash(_settings(tmp_path, lanes_enabled=["linkedin"])) == base
    assert routing_hash(_settings(tmp_path, death_probe_budget=999)) == base
    assert routing_hash(_settings(tmp_path, fetch_deadline_seconds=5.0)) == base
    assert routing_hash(_settings(tmp_path, llm=LLMTier(max_calls_per_run=7))) == base
    assert routing_hash(Settings(data_dir=other, config_dir=other)) == base


def test_routing_hash_fails_closed_on_an_unclassified_knob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same closure `config_hash` has, extended to the new set — without it the next routing
    knob is silently uncovered again, which is exactly how `seniority_hold` got here.

    Dropping a member from the OUT set simulates a knob that `config_hash` classified irrelevant
    and nobody then decided about for routing. Its own error type, so a caller cannot catch this
    and "fix" it by editing the config classification.
    """
    monkeypatch.setattr(
        manifest, "_ROUTING_IRRELEVANT", manifest._ROUTING_IRRELEVANT - {"scan_workers"}
    )
    with pytest.raises(UnclassifiedRoutingFieldError):
        routing_hash(_settings(tmp_path))


def test_routing_hash_covers_the_modules_that_decide_the_lane(tmp_path: Path) -> None:
    """The second half: a routing change arrives through the CODE as often as through a knob, and
    none of these five modules is inside `engine_version`'s four.

    Checked rather than asserted — `digested_modules()` is read here, so this fails if that list
    ever grows to cover a lane module and the two fingerprints start double-counting it.
    """
    from boardwatch.eligibility.engine import digested_modules

    assert set(digested_modules()).isdisjoint(
        {Path(name).name for name in manifest._ROUTING_MODULES}
    )
    assert all(
        (Path(manifest.__file__).parent.parent / name).is_file()
        for name in manifest._ROUTING_MODULES
    )
    # The source really is an input: a module whose text changes moves the value.
    original = manifest._routing_source

    def _mutated(relative: str) -> str:
        text = original(relative)
        return text + "\nZZZ_ROUTING_PROBE = 1\n" if relative.endswith("review_gate.py") else text

    base = routing_hash(_settings(tmp_path))
    manifest._routing_source = _mutated  # type: ignore[assignment]
    try:
        assert routing_hash(_settings(tmp_path)) != base
    finally:
        manifest._routing_source = original  # type: ignore[assignment]


def test_a_permanent_disposition_survives_a_hold_flip(tmp_path: Path) -> None:
    """**The ruling's hard constraint, asserted through the ledger rather than through the hash.**

    "Permanent dispositions keep their current identity. Changing a hold must reopen NOTHING."
    `policy_version` is composed from the five values above and `routing_hash` is not one of
    them, so a `built` job stamped before the flip is still live AND not stale afterwards.
    `stale_dispositions` is what the drain reads; an empty answer is the whole claim.
    """
    from datetime import datetime

    from sqlalchemy import insert

    from boardwatch.store import tables
    from boardwatch.store.db import ensure_schema, get_engine
    from boardwatch.store.ledger_queries import (
        live_dispositions,
        record_disposition,
        stale_dispositions,
    )

    now = datetime(2026, 9, 19, 12, 0, 0)
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    before = policy_version(**_five(_settings(tmp_path, gate=GateTier(seniority_hold=False))))  # type: ignore[arg-type]
    after = policy_version(**_five(_settings(tmp_path, gate=GateTier(seniority_hold=True))))  # type: ignore[arg-type]

    with engine.begin() as conn:
        job_id = int(
            conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
        )
        record_disposition(
            conn, job_id, disposition="built", reason="lead_built",
            policy_version=before, now=now,
        )

    with engine.connect() as conn:
        assert job_id in live_dispositions(conn, now=now)
        assert stale_dispositions(conn, policy_version=after, now=now) == {}
    assert before == after
