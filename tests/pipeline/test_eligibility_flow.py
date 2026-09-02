"""The eligibility LANDING POINT: user controls, one set-oriented preflight, and the
`show` audit render, exercised end to end without hand-writing any eligibility row."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy import event, insert, select, update
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.eligibility.audit import VerdictPresentation, load_audit
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import engine_version
from boardwatch.eligibility.facts import parse_facts, parse_policy
from boardwatch.eligibility.preflight import current_identity, run_eligibility
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import get_profile, save_profile

runner = CliRunner()

INIT_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
DEGREE_BODY = "We are hiring a backend engineer. A Bachelor's degree is required."
DEGREE_QUOTE = "Bachelor's degree is required"  # DEGREE_BODY[36:65], the stored span
PLAIN_BODY = "A backend engineering position on our team."
REVISED_BODY = "This role was updated and now covers only frontend interface polish work."


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def _seed_posting(
    data_dir: Path, body: str, *, slug: str = "acme2", status: str = "open"
) -> int:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug=slug, source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id=f"p-{slug}", title="Backend Engineer",
                    normalized_title="backend engineer", url="https://example.test/j",
                    locations_json=["Remote"], remote_policy="remote", first_seen_at=now,
                    last_seen_at=now, status=status, consecutive_missing=0,
                    content_hash=f"h-{slug}", body_text=body, job_id=job_id,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", body_text=body,
                captured_at=now, capture_reason="new",
            )
        )
    return posting_id


def _profile(data_dir: Path):
    with get_engine(data_dir).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    return parse_facts(row.eligibility_facts_json), parse_policy(row.eligibility_policy_json)


def _set_facts_and_policy(data_dir: Path) -> None:
    for dotted, value in (
        ("work_authorization.status", "citizen"),
        ("work_authorization.jurisdiction", "us"),
        ("highest_degree", "none"),
    ):
        assert _run(data_dir, ["eligibility", "facts", "set", dotted, value]).exit_code == 0
    assert _run(data_dir, ["eligibility", "policy", "set", "degree", "blocker"]).exit_code == 0


def test_named_cli_transcript_on_a_fresh_install(env: Path) -> None:
    posting_id = _seed_posting(env, DEGREE_BODY)
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    _set_facts_and_policy(env)

    assert _run(env, ["eligibility", "run"]).exit_code == 0
    assert _run(env, ["top"]).exit_code == 0
    show = _run(env, ["show", str(posting_id)])
    assert show.exit_code == 0
    assert "ineligible" in show.output
    assert "degree" in show.output.lower()

    facts, policy = _profile(env)
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "citizen"
    assert facts.work_authorization.jurisdiction == "us"
    assert facts.highest_degree == "none"
    assert policy.families["degree"] == "blocker"


def test_the_transcript_on_an_upgraded_install_with_null_columns(env: Path) -> None:
    posting_id = _seed_posting(env, DEGREE_BODY)
    # an install that predates eligibility: a profile row whose two columns are NULL, no init.
    engine = get_engine(env)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        assert conn.execute(select(tables.profile.c.eligibility_facts_json)).scalar_one() is None
    _set_facts_and_policy(env)
    assert _run(env, ["eligibility", "run"]).exit_code == 0
    show = _run(env, ["show", str(posting_id)])
    assert show.exit_code == 0
    assert "ineligible" in show.output


def test_preflight_no_ops_with_no_profile_and_top_still_raises(env: Path) -> None:
    _seed_posting(env, DEGREE_BODY)
    app_ctx = build_context(env)
    stats = run_eligibility(app_ctx.engine, app_ctx.settings, Console())
    assert stats.skipped_no_profile is True
    assert stats.evaluated == 0
    top = _run(env, ["top"])
    assert top.exit_code == 1
    assert "no profile" in top.output


def _evaluate_open(
    env: Path, body: str, *, degree: str = "none", degree_policy: str = "blocker"
) -> int:
    posting_id = _seed_posting(env, body)
    engine = get_engine(env)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", degree]).exit_code == 0
    assert _run(env, ["eligibility", "policy", "set", "degree", degree_policy]).exit_code == 0
    assert _run(env, ["eligibility", "run"]).exit_code == 0
    return posting_id


def test_revise_then_render_slices_the_original_version(env: Path) -> None:
    posting_id = _evaluate_open(env, DEGREE_BODY)
    engine = get_engine(env)
    now = utcnow()
    with engine.begin() as conn:  # a scan revision: new version row + postings rewritten in place
        conn.execute(
            insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash="h-rev", body_text=REVISED_BODY,
                captured_at=now + timedelta(minutes=1), capture_reason="revised",
            )
        )
        conn.execute(
            update(tables.postings).where(tables.postings.c.id == posting_id).values(
                content_hash="h-rev", body_text=REVISED_BODY
            )
        )
    catalog = load_rules(env.parent / "cfg")
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
    assert view is not None
    assert view.is_historical is True
    quote = view.requirements[0].quote
    assert DEGREE_QUOTE in quote  # the ORIGINAL version's span, not the rewritten posting body
    assert quote not in REVISED_BODY


def test_closed_posting_renders_its_newest_historical_evaluation(env: Path) -> None:
    posting_id = _evaluate_open(env, DEGREE_BODY)
    engine = get_engine(env)
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings).where(tables.postings.c.id == posting_id).values(
                status="closed", closed_at=utcnow()
            )
        )
        before = len(conn.execute(select(tables.eligibility_evaluations)).all())
    catalog = load_rules(env.parent / "cfg")
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
        after = len(conn.execute(select(tables.eligibility_evaluations)).all())
    assert view is not None
    assert view.is_historical is True
    assert view.verdict == "ineligible"
    assert after == before  # never freshly evaluated (D-P2-9)


def test_version_gated_labels_fall_back_to_the_raw_rule_id(env: Path) -> None:
    posting_id = _evaluate_open(env, DEGREE_BODY)
    engine = get_engine(env)
    catalog = load_rules(env.parent / "cfg")
    stale = replace(catalog, version=catalog.version + "-stale")
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, stale)
    assert view is not None
    assert view.catalog_version_matches is False
    label = view.requirements[0].label
    assert "degree:bachelor_required" in label  # the raw composite rule_id
    assert "catalog version no longer present" in label
    assert "A bachelor's degree is required" not in label  # no current-catalog label


def test_support_resolves_from_the_frozen_snapshot(env: Path) -> None:
    posting_id = _evaluate_open(env, DEGREE_BODY, degree="bachelor")
    # the live profile changes AFTER the evaluation was recorded
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "master"]).exit_code == 0
    engine = get_engine(env)
    catalog = load_rules(env.parent / "cfg")
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
    assert view is not None
    supports = view.requirements[0].support
    assert supports and supports[0].evidence_quote == "bachelor"  # not the live "master"


def _seed_many(data_dir: Path, count: int) -> None:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="bulk", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        for i in range(count):
            job_id = int(
                conn.execute(insert(tables.jobs).values(created_at=now)).inserted_primary_key[0]
            )
            posting_id = int(
                conn.execute(
                    insert(tables.postings).values(
                        company_id=company_id, provider_posting_id=f"p{i}", title="Backend Engineer",
                        normalized_title="backend engineer", url="https://example.test/j",
                        locations_json=["Remote"], remote_policy="remote", first_seen_at=now,
                        last_seen_at=now, status="open", consecutive_missing=0,
                        content_hash=f"h{i}", body_text=PLAIN_BODY, job_id=job_id,
                    )
                ).inserted_primary_key[0]
            )
            conn.execute(
                insert(tables.posting_versions).values(
                    posting_id=posting_id, content_hash=f"h{i}", body_text=PLAIN_BODY,
                    captured_at=now, capture_reason="new",
                )
            )


def _run_and_count_scans(data_dir: Path, count: int) -> tuple[int, int]:
    _seed_many(data_dir, count)
    app_ctx = build_context(data_dir)
    statements: list[str] = []

    @event.listens_for(app_ctx.engine, "before_cursor_execute")
    def _record(conn, cursor, statement, params, context, executemany):  # noqa: ANN001, ANN202
        statements.append(statement)

    stats = run_eligibility(app_ctx.engine, app_ctx.settings, Console())
    scans = [
        s for s in statements
        if s.lstrip().upper().startswith("SELECT") and "posting_versions" in s
    ]
    return stats.evaluated, len(scans)


def test_selection_is_one_query_and_does_not_scale_with_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    small_evaluated, small_scans = _run_and_count_scans(tmp_path / "small", 20)
    large_evaluated, large_scans = _run_and_count_scans(tmp_path / "large", 200)
    assert small_evaluated == 20
    assert large_evaluated == 200
    # An N+1 selection would scan posting_versions once per posting; the set-oriented
    # anti-join scans it exactly once regardless of corpus size. Counting is the only
    # check that discriminates, because an N+1 also "runs eligibility".
    #
    # THREE such reads since the lane-body precondition shipped (D-406), and the count is the
    # point: the selection anti-join, the quarantine drain (bounded by the BUCKET), and the
    # body sweep (bounded by the versions the current detector has not judged yet, which is the
    # whole corpus once and nothing thereafter). None is per-posting, which is exactly what the
    # equality asserts — an N+1 in any of the three shows up as 20 against 200, never 3 against 3.
    assert small_scans == large_scans == 3


def test_a_fact_change_re_evaluates_and_updates_the_verdict(env: Path) -> None:
    # The reported F-STALE bug: the anti-join keyed only on engine_version, so a corrected
    # fact was never re-evaluated and top/show served the old verdict forever.
    posting_id = _evaluate_open(env, DEGREE_BODY, degree="none")
    assert "hidden as ineligible" in _run(env, ["top"]).output  # ineligible, hidden
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "bachelor"]).exit_code == 0
    result = _run(env, ["eligibility", "run"])
    assert result.exit_code == 0
    assert "evaluated 1" in result.output  # re-evaluated against the new profile, not skipped
    top = _run(env, ["top"])
    assert "hidden as ineligible" not in top.output  # no longer ineligible
    assert str(posting_id) in top.output  # and now visible


def test_toggling_a_fact_back_restores_the_prior_verdict(env: Path) -> None:
    # A run after a change writes a NEW input+evaluation; toggling back reaches an input the
    # ledger already holds, so the read must match the current identity, not the newest row.
    posting_id = _evaluate_open(env, DEGREE_BODY, degree="none")  # ineligible, identity A
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "bachelor"]).exit_code == 0
    assert _run(env, ["eligibility", "run"]).exit_code == 0  # eligible, identity B (newer row)
    assert "hidden as ineligible" not in _run(env, ["top"]).output
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "none"]).exit_code == 0
    result = _run(env, ["eligibility", "run"])
    assert "evaluated 0" in result.output  # identity A already has a row: nothing to write
    top = _run(env, ["top"])
    assert "hidden as ineligible" in top.output  # identity A's ineligible, not identity B's
    assert str(posting_id) not in _postings_shown(top.output)


def _postings_shown(top_output: str) -> str:
    # the rendered table rows, excluding the trailing hidden-count sentence (which itself
    # contains a bare count that must not be mistaken for a posting id)
    return "\n".join(
        line for line in top_output.splitlines() if "hidden as ineligible" not in line
    )


def test_show_agrees_with_top_after_toggling_a_fact_back(env: Path) -> None:
    posting_id = _evaluate_open(env, DEGREE_BODY, degree="none")
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "bachelor"]).exit_code == 0
    assert _run(env, ["eligibility", "run"]).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "none"]).exit_code == 0
    assert _run(env, ["eligibility", "run"]).exit_code == 0
    show = _run(env, ["show", str(posting_id)])
    assert show.exit_code == 0
    # show reads the audit for the CURRENT profile (identity A), matching what top hides,
    # not the newer identity-B evaluation that also exists on this version.
    assert "Eligibility: ineligible" in show.output


def test_eligible_with_zero_requirements_renders_as_no_rule_applied(env: Path) -> None:
    # "No flags" != cleared (CLAUDE.md, P2 item 6): an `eligible` that fired NO rule must not
    # read the same as an `eligible` that actually cleared a requirement. The remaining
    # eligible-with-zero-rows case is an IGNORED family (D-250): a body that fires nothing at
    # all now abstains to `uncertain`, so this fixture states a degree requirement and ignores
    # the degree family, which stays `eligible` because the user opted out of the only gate.
    posting_id = _evaluate_open(env, DEGREE_BODY, degree="none", degree_policy="ignore")
    catalog = load_rules(env.parent / "cfg")
    engine = get_engine(env)
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
    assert view is not None
    assert view.verdict == "eligible"  # the stored verdict is unchanged
    assert view.requirements == ()
    assert view.presentation is VerdictPresentation.ELIGIBLE_NO_RULES_APPLIED

    show = _run(env, ["show", str(posting_id)])
    assert show.exit_code == 0
    assert "no eligibility rule applied" in show.output


def test_eligible_with_cleared_requirements_renders_as_cleared(env: Path) -> None:
    posting_id = _evaluate_open(env, DEGREE_BODY, degree="bachelor")
    catalog = load_rules(env.parent / "cfg")
    engine = get_engine(env)
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
    assert view is not None
    assert view.verdict == "eligible"  # the stored verdict is unchanged
    assert len(view.requirements) >= 1
    assert view.presentation is VerdictPresentation.ELIGIBLE_CLEARED

    show = _run(env, ["show", str(posting_id)])
    assert show.exit_code == 0
    assert "requirement" in show.output and "cleared" in show.output


def test_eligible_with_a_non_met_row_renders_mixed_not_cleared(env: Path) -> None:
    # Fix round 1's live case: an eligible verdict can carry a met BLOCKER row (e.g. work_auth)
    # alongside a non-blocking PREFERENCE-family unmet row (e.g. degree, D-035's five families
    # that stay preference). Rendering "2 requirements cleared" would claim the unmet row is
    # cleared -- the exact overclaim item 6 exists to kill. The header must go neutral, and the
    # true per-row disposition must still render below, unchanged.
    from boardwatch.store.eligibility import RequirementItem, record_evaluation

    posting_id = _seed_posting(env, DEGREE_BODY)
    engine = get_engine(env)
    catalog = load_rules(env.parent / "cfg")
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )
        pv_id = conn.execute(
            select(tables.posting_versions.c.id).where(
                tables.posting_versions.c.posting_id == posting_id
            )
        ).scalar_one()
        record_evaluation(
            conn,
            posting_version_id=int(pv_id),
            profile_hash="ph", profile_snapshot={},
            rules_hash="rh", rules_snapshot={"catalog_version": catalog.version},
            input_fingerprint="fp", engine_kind="deterministic",
            engine_version="1+deadbeefcafe", verdict="eligible", score=None,
            requirements=[
                RequirementItem(
                    requiredness="required", requirement_text="US work authorization",
                    jd_locator={"span": [0, 10]},
                    disposition="met", rule_id="work_auth:citizen_or_lpr",
                ),
                RequirementItem(
                    requiredness="required", requirement_text="Bachelor's degree preferred",
                    jd_locator={"span": [36, 65]},
                    disposition="unmet", rule_id="degree:bachelor_required",
                ),
            ],
        )
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
    assert view is not None
    assert view.verdict == "eligible"  # the stored verdict is unchanged, presentation-only fix
    assert view.presentation is VerdictPresentation.ELIGIBLE_MIXED
    assert view.met_count == 1  # only the met row counts, never both

    show = _run(env, ["show", str(posting_id)])
    assert show.exit_code == 0
    assert "2 requirements cleared" not in show.output  # the overclaim this test guards against
    assert "1 cleared" in show.output  # the honest count, in neutral wording
    assert "unmet" in show.output  # the true disposition of the second row still renders below


def test_load_audit_tolerates_a_malformed_span(env: Path) -> None:
    # The eval tables are append-only and trigger-guarded, so a poison locator row (e.g. from a
    # future or hand write) could never be corrected. load_audit must render an empty quote for
    # it rather than raise IndexError and take down `show`.
    from boardwatch.store.eligibility import RequirementItem, record_evaluation

    posting_id = _seed_posting(env, DEGREE_BODY)
    engine = get_engine(env)
    catalog = load_rules(env.parent / "cfg")
    with engine.begin() as conn:
        pv_id = conn.execute(
            select(tables.posting_versions.c.id).where(
                tables.posting_versions.c.posting_id == posting_id
            )
        ).scalar_one()
        record_evaluation(
            conn,
            posting_version_id=int(pv_id),
            profile_hash="ph", profile_snapshot={},
            rules_hash="rh", rules_snapshot={"catalog_version": catalog.version},
            input_fingerprint="fp", engine_kind="deterministic",
            engine_version="1+deadbeefcafe", verdict="uncertain", score=None,
            requirements=[
                RequirementItem(
                    requiredness="required", requirement_text="x",
                    jd_locator={"span": [1]},  # malformed: a one-element span
                    disposition="unknown", rule_id="degree:x",
                )
            ],
        )
    with engine.connect() as conn:
        view = load_audit(conn, posting_id, catalog)
    assert view is not None
    assert view.requirements[0].quote == ""


def test_facts_set_rejects_a_non_ascii_digit_cleanly(env: Path) -> None:
    _seed_posting(env, DEGREE_BODY)
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    # "²".isdigit() is True but int("²") raises; the coercion must reject it as a clean
    # BadParameter (exit 1), never let a raw ValueError escape the command.
    result = _run(env, ["eligibility", "facts", "set", "total_years_experience", "²"])
    assert result.exit_code == 1
    assert not isinstance(result.exception, ValueError)
    assert "whole number" in result.output


def test_init_reprompts_on_a_bad_eligibility_answer_instead_of_aborting(env: Path) -> None:
    # A single typo used to abort the whole wizard (exit 2) after the profile was already
    # saved, discarding every eligibility answer. It must re-prompt and accept the correction.
    catalog = load_rules(env.parent / "cfg")
    elig: list[str] = []
    for family_index, family in enumerate(catalog.families):
        for field_index, _field in enumerate(family.fields):
            if family_index == 0 and field_index == 0:
                elig += ["notachoice", "citizen"]  # first field: rejected, then corrected
            else:
                elig.append("")  # skip
        elig.append("")  # policy: accept the neutral default
    # The two trailing blanks skip the career-field and field-of-study prompts, which are
    # single catalog-scalars rather than family fields, so the loop above cannot reach them.
    preamble = ["3", "acme", "Backend engineer.", "", "", "", "n", "y", "", ""]
    result = _run(env, ["init"], "\n".join(preamble + elig) + "\n")
    assert result.exit_code == 0, result.output
    facts, _ = _profile(env)
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "citizen"  # the correction landed


# ------------------------------------------------------- the parallel evaluation path

PARALLEL_BODIES = (
    DEGREE_BODY,
    PLAIN_BODY,
    "We require an active Secret clearance and 8+ years of experience.",
    "This team does not sponsor work visas; applicants must already be authorized to "
    "work in the United States.",
    "A Master's degree in Computer Science is required, and 5+ years of experience "
    "with distributed systems is required.",
    "Interns welcome. No degree requirement of any kind.",
)


def _ledger(data_dir: Path) -> list[tuple[object, ...]]:
    """Every persisted eligibility row, keyed on posting version rather than row id.

    Row ids, timestamps and run ids are deliberately excluded: they differ between two
    independently seeded stores for reasons that have nothing to do with the evaluation.
    Everything the engine DECIDED is included, requirement rows and all.
    """
    joined = tables.eligibility_inputs.join(
        tables.eligibility_evaluations,
        tables.eligibility_evaluations.c.input_id == tables.eligibility_inputs.c.id,
    ).outerjoin(
        tables.eligibility_requirements,
        tables.eligibility_requirements.c.evaluation_id == tables.eligibility_evaluations.c.id,
    )
    with get_engine(data_dir).connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                select(
                    tables.eligibility_inputs.c.posting_version_id,
                    tables.eligibility_inputs.c.profile_hash,
                    tables.eligibility_inputs.c.rules_hash,
                    tables.eligibility_inputs.c.input_fingerprint,
                    tables.eligibility_evaluations.c.engine_kind,
                    tables.eligibility_evaluations.c.engine_version,
                    tables.eligibility_evaluations.c.verdict,
                    tables.eligibility_requirements.c.ordinal,
                    tables.eligibility_requirements.c.rule_id,
                    tables.eligibility_requirements.c.requiredness,
                    tables.eligibility_requirements.c.requirement_text,
                    tables.eligibility_requirements.c.jd_locator_json,
                    tables.eligibility_requirements.c.disposition,
                    tables.eligibility_requirements.c.rationale,
                )
                .select_from(joined)
                .order_by(
                    tables.eligibility_inputs.c.posting_version_id,
                    tables.eligibility_requirements.c.ordinal,
                )
            ).all()
        ]


def _install(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(root / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    data_dir = root / "data"
    for index, body in enumerate(PARALLEL_BODIES):
        _seed_posting(data_dir, body, slug=f"acme-{index}")
    assert _run(data_dir, ["init"], INIT_INPUT).exit_code == 0
    _set_facts_and_policy(data_dir)
    return data_dir


def test_the_parallel_path_writes_exactly_what_the_serial_path_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two identically seeded stores, one judged serially and one through a process pool.

    A green test that only ever took the serial branch verifies nothing, so the pool
    constructor is spied on: the serial run must build none, and the parallel run must build
    exactly ONE for the whole stage. BATCH_SIZE is dropped to 2 so the six postings span
    three commit batches — that is what makes "one pool" a real assertion rather than an
    artefact of there being a single chunk, and it also holds the per-batch commit boundary
    the resumability guarantee rests on.
    """
    from boardwatch.eligibility import preflight as preflight_module

    built: list[object] = []
    real_pool = preflight_module.ProcessPoolExecutor

    def spy(*args: object, **kwargs: object) -> object:
        built.append(kwargs.get("max_workers"))
        return real_pool(*args, **kwargs)  # type: ignore[arg-type]

    serial_dir = _install(tmp_path / "serial", monkeypatch)
    monkeypatch.setattr(preflight_module, "ProcessPoolExecutor", spy)
    serial_ctx = build_context(serial_dir)
    serial_stats = run_eligibility(serial_ctx.engine, serial_ctx.settings, Console(quiet=True))
    assert serial_stats.evaluated == len(PARALLEL_BODIES)
    assert built == [], "the default threshold must keep a small backlog on the serial path"

    parallel_dir = _install(tmp_path / "parallel", monkeypatch)
    monkeypatch.setattr(preflight_module, "BATCH_SIZE", 2)
    parallel_ctx = build_context(parallel_dir)
    parallel_stats = run_eligibility(
        parallel_ctx.engine,
        parallel_ctx.settings,
        Console(quiet=True),
        workers=2,
        parallel_threshold=1,
    )
    assert built == [2], built  # ONE pool for three batches, not one per batch
    assert parallel_stats.evaluated == len(PARALLEL_BODIES)
    assert parallel_stats.profile_hash == serial_stats.profile_hash
    assert parallel_stats.rules_hash == serial_stats.rules_hash

    serial_rows, parallel_rows = _ledger(serial_dir), _ledger(parallel_dir)
    assert serial_rows == parallel_rows
    verdicts = {row[0]: row[6] for row in serial_rows}
    assert len(verdicts) == len(PARALLEL_BODIES)
    assert len(set(verdicts.values())) >= 2, verdicts  # not one uniform verdict
    assert any(row[8] is not None for row in serial_rows), "no requirement row was written"


def test_a_worker_that_loads_a_different_identity_refuses_to_evaluate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pool initializer is the only thing between a child that rebuilt a DIFFERENT
    catalog or engine and a ledger row attributed to an identity nothing evaluated under.
    Those rows carry BEFORE UPDATE/DELETE RAISE(ABORT) triggers, so they can only be
    superseded, never corrected — the guard has to actually fire.

    Each of the three slots is wrongly supplied in turn, because a comparison mis-wired to
    read the same hash twice would still refuse a wrong profile_hash and admit a wrong
    rules_hash. Driven in-process rather than through a pool; the ACCEPTING path is what
    `test_the_parallel_path_writes_exactly_what_the_serial_path_writes` proves, since a
    raising initializer breaks the pool outright.
    """
    from boardwatch.eligibility import preflight as preflight_module

    data_dir = _install(tmp_path / "guard", monkeypatch)
    ctx = build_context(data_dir)
    with ctx.engine.connect() as conn:
        row = get_profile(conn)
        pair = current_identity(conn, ctx.settings)
    assert row is not None and pair is not None
    profile_hash, rules_hash = pair
    inputs = (ctx.settings.config_dir, row.eligibility_facts_json, row.eligibility_policy_json)

    for wrong in (
        ("not-the-profile-hash", rules_hash, engine_version()),
        (profile_hash, "not-the-rules-hash", engine_version()),
        (profile_hash, rules_hash, "9+ffffffffffff"),
    ):
        with pytest.raises(RuntimeError, match="different input identity"):
            preflight_module._init_worker(*inputs, *wrong)

    # The refusal precedes the assignment, so a rejected child holds no inputs at all.
    assert preflight_module._WORKER_INPUTS is None
