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
from boardwatch.eligibility.facts import parse_facts, parse_policy
from boardwatch.eligibility.preflight import run_eligibility
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
    assert small_scans == 1
    assert large_scans == 1


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
    preamble = ["3", "acme", "Backend engineer.", "", "", "", "n", "y", ""]  # skip career field
    result = _run(env, ["init"], "\n".join(preamble + elig) + "\n")
    assert result.exit_code == 0, result.output
    facts, _ = _profile(env)
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "citizen"  # the correction landed
