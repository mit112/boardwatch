"""Facts and policy are user-owned, so the CLI is the only writer. Values are validated
against the CATALOG's declared choices, never against a source literal."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.eligibility.facts import parse_facts, parse_policy
from boardwatch.store.db import get_engine
from boardwatch.store.queries import get_profile

runner = CliRunner()

INIT_INPUT = (
    "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"
)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def _facts(data_dir: Path):
    with get_engine(data_dir).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    return parse_facts(row.eligibility_facts_json), parse_policy(row.eligibility_policy_json)


def test_setting_a_scalar_fact(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "bachelor"]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.highest_degree == "bachelor"


def test_setting_an_int_fact(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set", "total_years_experience", "8"]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.total_years_experience == 8


def test_setting_a_structured_field(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    for dotted, value in (
        ("work_authorization.status", "citizen"),
        ("work_authorization.jurisdiction", "us"),
    ):
        assert _run(env, ["eligibility", "facts", "set", dotted, value]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "citizen"
    assert facts.work_authorization.jurisdiction == "us"


def test_setting_one_structured_field_preserves_the_other(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    _run(env, ["eligibility", "facts", "set", "work_authorization.status", "citizen"])
    _run(env, ["eligibility", "facts", "set", "work_authorization.jurisdiction", "us"])
    _run(env, ["eligibility", "facts", "set", "work_authorization.status", "permanent_resident"])
    facts, _ = _facts(env)
    assert facts.work_authorization is not None
    assert facts.work_authorization.jurisdiction == "us"


def test_setting_the_needs_sponsorship_bit(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set",
                      "work_authorization.needs_sponsorship", "no"]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.work_authorization is not None
    assert facts.work_authorization.needs_sponsorship is False


def test_setting_a_choice_set_field(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set", "security_clearance.accesses",
                      "sci,poly"]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.security_clearance is not None
    assert set(facts.security_clearance.accesses) == {"sci", "poly"}


def test_setting_the_clearance_obtainability_bit(env: Path) -> None:
    """A resolver input nobody can write is a rule that can never fire. The catalog declares
    `obtainable` as an ordinary bool field, so the existing dotted setter reaches it."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set",
                      "security_clearance.obtainable", "no"]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.security_clearance is not None
    assert facts.security_clearance.obtainable is False


def test_set_career_field_accepts_a_catalog_value(tmp_path: Path) -> None:
    from boardwatch.cli.eligibility_cmd import set_career_field
    from boardwatch.eligibility.catalog import load_rules
    from boardwatch.eligibility.facts import Facts
    catalog = load_rules(tmp_path / "no-override")  # bundled: career_fields == {software}
    out = set_career_field(Facts(), catalog, "software")
    assert out.career_field == "software"


def test_set_career_field_rejects_out_of_vocab(tmp_path: Path) -> None:
    import typer

    from boardwatch.cli.eligibility_cmd import set_career_field
    from boardwatch.eligibility.catalog import load_rules
    from boardwatch.eligibility.facts import Facts
    catalog = load_rules(tmp_path / "no-override")
    with pytest.raises(typer.BadParameter):
        set_career_field(Facts(), catalog, "nursing")


def test_facts_set_routes_career_field_to_its_own_setter(env: Path) -> None:
    """The dispatch in `facts set`, exercised through the CLI rather than around it.

    `set_fact` resolves a `family.fact`, and career_field is a non-family scalar, so without
    the interception this command fails with `unknown fact 'career_field'` and stores nothing.
    """
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "career_field", "software"])
    assert result.exit_code == 0
    facts, _ = _facts(env)
    assert facts.career_field == "software"


def test_facts_set_rejects_a_career_field_outside_the_catalog_vocabulary(env: Path) -> None:
    """Rejection has to come from the career-field vocabulary, not the fact list: routed to
    `set_fact` instead, this would also exit 1, but saying `unknown fact` about a fact that
    exists."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "career_field", "nursing"])
    assert result.exit_code == 1
    assert "unknown career_field 'nursing'" in result.output
    facts, _ = _facts(env)
    assert facts.career_field is None


def test_facts_renders_the_career_field_line(env: Path) -> None:
    """career_field belongs to no family, so the family loop cannot render it and it needs its
    own line. Scoped to the whole line: `software` alone also occurs in other output."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    before = _run(env, ["eligibility", "facts"])
    assert before.exit_code == 0
    assert "Career field: not set" in before.output

    assert _run(env, ["eligibility", "facts", "set", "career_field", "software"]).exit_code == 0
    after = _run(env, ["eligibility", "facts"])
    assert after.exit_code == 0
    assert "Career field: software" in after.output


def test_an_unknown_fact_is_rejected_and_lists_the_valid_ones(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "favourite_colour", "blue"])
    assert result.exit_code == 1
    assert "highest_degree" in result.output


def test_a_value_outside_the_catalog_choices_is_rejected(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "highest_degree", "phd"])
    assert result.exit_code == 1
    assert "doctorate" in result.output  # the message lists the declared choices


def test_a_non_integer_years_value_is_rejected(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "total_years_experience", "loads"])
    assert result.exit_code == 1


def test_a_structured_fact_needs_a_field(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "work_authorization", "citizen"])
    assert result.exit_code == 1
    assert "status" in result.output


def test_setting_a_policy(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "policy", "set", "degree", "blocker"]).exit_code == 0
    _, policy = _facts(env)
    assert policy.families["degree"] == "blocker"


def test_an_unknown_policy_family_is_rejected(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "policy", "set", "salary", "blocker"])
    assert result.exit_code == 1
    assert "work_auth" in result.output


def test_an_unknown_severity_is_rejected(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "policy", "set", "degree", "maybe"]).exit_code == 1


def test_facts_renders_declared_and_undeclared_values(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    _run(env, ["eligibility", "facts", "set", "highest_degree", "bachelor"])
    result = _run(env, ["eligibility", "facts"])
    assert result.exit_code == 0
    assert "bachelor" in result.output
    assert "not set" in result.output  # the other three are visibly absent


def test_policy_renders_the_materialised_map(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "policy"])
    assert result.exit_code == 0
    for family in ("work_auth", "experience_years", "clearance", "degree"):
        assert family in result.output
    assert "preference" in result.output  # the catalog default


def test_the_commands_fail_cleanly_with_no_profile(env: Path) -> None:
    result = _run(env, ["eligibility", "facts"])
    assert result.exit_code == 1
    assert "boardwatch init" in result.output


def test_summary_with_no_evaluations_reports_zero(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "summary"])
    assert result.exit_code == 0
    assert "evaluated: 0" in result.output
    assert "no current-engine evaluation: 0" in result.output


def test_abstain_lists_every_catalog_rule_on_an_empty_database(env: Path) -> None:
    """The distinguishing behaviour vs `summary`: with zero rows, `summary` shows nothing and
    `abstain` still shows all 45 rules, every one of them flagged `never fired`."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "abstain"])

    assert result.exit_code == 0
    assert "45 rules · 45 never fired" in result.output
    assert "0 fire but never decide" in result.output
    # A rule with no rows is never reported as 0% — that would read as "never abstains".
    assert "0%" not in result.output


def test_setting_COLUMNS_reaches_the_module_level_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """The premise the three width-controlling tests below rest on, pinned on its own.

    Since rich 15.0.0 `Console.__init__` reads `COLUMNS` eagerly into `self._width`, and
    `Console.size` returns `self._width` verbatim when it is set. `cli/eligibility_cmd.py`
    builds its `Console` at import, so an ambient `COLUMNS` freezes that console's width for
    the whole process and every later `monkeypatch.setenv("COLUMNS", ...)` silently does
    nothing — the tests below then assert against whatever width the RUNNER happened to
    supply. `tests/conftest.py` pops `COLUMNS`/`LINES` at import to keep `_width` None, which
    is the only state in which `Console.size`'s live lookup is reachable. Without that pop
    this fails under `COLUMNS=80`, which is exactly how ubuntu/3.12 went red in CI.
    """
    from boardwatch.cli.eligibility_cmd import console

    monkeypatch.setenv("COLUMNS", "137")
    # `Console.size` returns `width - self.legacy_windows`, so a legacy Windows console reports one
    # column fewer than `COLUMNS` names — it reserves the last cell that would otherwise auto-wrap.
    # Read the flag off the console rather than restating the platform test here: what this pins is
    # that the env var ARRIVES, not what rich subsequently subtracts from it. Asserting the bare
    # 137 made this the one deterministic failure in all nine nightly Windows jobs (D-212).
    assert console.width == 137 - console.legacy_windows


def test_typer_does_not_force_a_terminal_for_help_rendering() -> None:
    """The same premise one layer up, for typer's own help console rather than rich's.

    `typer/rich_utils.py` bakes `FORCE_TERMINAL = True if getenv("GITHUB_ACTIONS") or
    getenv("FORCE_COLOR") or getenv("PY_COLORS") else None` at IMPORT time and passes it to the
    console it builds for every `--help` render. Baked at import means the pop in
    `tests/conftest.py` only works because it runs BEFORE anything imports typer — an ordering
    nothing else pins, and rich's own vars did not need because it reads those live.

    So this asserts the outcome, not the environment: a styled help render splits an option name
    across escape codes, and `assert "--new" in result.stdout` then fails on a flag that rendered
    perfectly. That is exactly how all three ubuntu jobs went red at `64cf63c` while all three
    macOS jobs passed.
    """
    import typer.rich_utils

    assert typer.rich_utils.FORCE_TERMINAL is not True


def test_abstain_names_rules_that_have_never_been_detected(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """These seven are exactly why enumeration cannot come from a GROUP BY.

    Widened because rule_ids must render in full: at 80 columns rich abbreviates them to a
    common prefix and two distinct rules become indistinguishable.
    """
    monkeypatch.setenv("COLUMNS", "160")
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "abstain"])

    for rule_id in (
        "clearance:doe_q_required",
        "work_auth:eu_authorization_required",
        "experience_years:total_years_minimum",
    ):
        assert rule_id in result.output


def test_abstain_never_abbreviates_a_rule_id_on_a_narrow_terminal(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 80 columns rich's default overflow truncates rule_ids to a shared prefix, so
    `experience_years:total_years_minimum` and `..._preferred` both render as
    `experience_years:total_y…` — two different rules, one string. The rule_id is this
    report's key, so it may wrap but must never be abbreviated. Pins `overflow="fold"`.
    """
    monkeypatch.setenv("COLUMNS", "80")
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "abstain"])

    assert "…" not in result.output


def _write_field_tier_catalog(config_dir: Path):
    """Make `internship` a field-tier family that applies only to `software`.

    Derived from the SHIPPED rules.yaml rather than hand-written, so catalog drift reaches
    this test instead of being frozen out of it.
    """
    import yaml

    from boardwatch.eligibility.catalog import bundled_rules_text, load_rules

    document = yaml.safe_load(bundled_rules_text())
    document["career_fields"] = ["software", "data"]
    for family in document["families"]:
        if family["id"] == "internship":
            family["tier"] = "field"
            family["applies_to"] = ["software"]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "rules.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    return load_rules(config_dir)


def test_abstain_footer_counts_the_not_applicable_bucket(
    env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A field-tier family that does not apply to this profile is in NEITHER `never fired`
    nor `fire but never decide`, so a footer naming only those two stops partitioning the
    catalog the moment such a family exists — the table row is right and the summary lies.

    Width is pinned so the footer is one unwrapped line and the assertion can be scoped to it.
    """
    monkeypatch.setenv("COLUMNS", "200")
    catalog = _write_field_tier_catalog(tmp_path / "cfg")
    skipped = sum(len(f.patterns) for f in catalog.families if f.id == "internship")
    total = sum(len(f.patterns) for f in catalog.families)
    assert skipped > 0

    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set", "career_field", "data"]).exit_code == 0
    result = _run(env, ["eligibility", "abstain"])

    assert result.exit_code == 0
    assert (
        f"{total} rules · {total - skipped} never fired · {skipped} not applicable · "
        f"0 fire but never decide"
    ) in result.output


def test_extract_skips_cleanly_when_extraction_disabled(env: Path) -> None:
    """Both the extraction feature and the LLM tier are off by default: `extract` must
    degrade to a one-line message and exit 0, never an error, with no profile or
    postings needed. The extraction gate is checked first, so its message is the one
    that surfaces here."""
    result = _run(env, ["eligibility", "extract"])
    assert result.exit_code == 0
    assert "llm eligibility extraction is off" in result.output.lower()


def test_help_smoke(env: Path) -> None:
    assert runner.invoke(app, ["eligibility", "--help"]).exit_code == 0
    assert runner.invoke(app, ["eligibility", "facts", "--help"]).exit_code == 0
    assert runner.invoke(app, ["eligibility", "policy", "--help"]).exit_code == 0
    assert runner.invoke(app, ["eligibility", "run", "--help"]).exit_code == 0
    assert runner.invoke(app, ["eligibility", "summary", "--help"]).exit_code == 0
    assert runner.invoke(app, ["eligibility", "abstain", "--help"]).exit_code == 0
    assert runner.invoke(app, ["eligibility", "extract", "--help"]).exit_code == 0
