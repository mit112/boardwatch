"""Facts and policy are user-owned, so the CLI is the only writer. Values are validated
against the CATALOG's declared choices, never against a source literal."""

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.eligibility_cmd import set_ceiling
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import Policy, parse_facts, parse_policy
from boardwatch.rank.role_taxonomy import write_role_taxonomy
from boardwatch.store.db import get_engine
from boardwatch.store.queries import get_profile

runner = CliRunner()

INIT_INPUT = (
    "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\nsoftware\n"
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


def test_setting_the_field_of_study(env: Path) -> None:
    """`field_of_study` is a non-family scalar, so the dotted setter cannot reach it and it
    needs its own branch. Without one the fact is unwritable and the rule never fires."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "facts", "set", "field_of_study",
                      "software_engineering"]).exit_code == 0
    facts, _ = _facts(env)
    assert facts.field_of_study == "software_engineering"


def test_setting_a_field_of_study_outside_the_catalog_is_refused(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "field_of_study", "wizardry"])
    assert result.exit_code == 1
    assert "unknown field_of_study" in result.output
    facts, _ = _facts(env)
    assert facts.field_of_study is None


def test_facts_set_refuses_career_field_and_names_the_taxonomy(env: Path) -> None:
    """T208: the engine reads `career_field` from the role taxonomy, so a stored value would be a
    second write path nothing reads. `facts set` refuses it, says where the field comes from, and
    stores nothing — even for a value the catalog declares."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "facts", "set", "career_field", "software"])
    assert result.exit_code == 1
    assert "role-taxonomy.yaml" in result.output
    facts, _ = _facts(env)
    assert facts.career_field is None


def test_facts_renders_the_career_field_the_taxonomy_declares(env: Path, tmp_path: Path) -> None:
    """career_field belongs to no family, so the family loop cannot render it and it needs its
    own line — showing what the ENGINE reads, the taxonomy's field (T208). Scoped to the whole
    line: `software` alone also occurs in other output."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0  # answers the taxonomy `software`
    with_taxonomy = _run(env, ["eligibility", "facts"])
    assert with_taxonomy.exit_code == 0
    assert "Career field: software (from role-taxonomy.yaml)" in with_taxonomy.output

    (tmp_path / "cfg" / "role-taxonomy.yaml").unlink()
    without = _run(env, ["eligibility", "facts"])
    assert without.exit_code == 0
    assert "Career field: not set (from role-taxonomy.yaml)" in without.output


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
    write_role_taxonomy(  # the profile's field is `data`, so `internship` does not apply
        tmp_path / "cfg",
        {"version": 1, "field": "data", "role_families": [{"id": "analyst", "title_words": ["analyst"]}]},
    )
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


def _corrupt_policy(data_dir: Path) -> None:
    """The bare FAMILIES map stored where a Policy document belongs — the shape a hand edit
    or an older writer produces, and the one the 2026-09-04 review's own probe hit."""
    from boardwatch.store import tables

    with get_engine(data_dir).begin() as conn:
        conn.execute(
            tables.profile.update()
            .where(tables.profile.c.id == 1)
            .values(eligibility_policy_json={"experience_years": "blocker"})
        )


def test_a_read_command_refuses_an_unusable_profile_row_by_name(env: Path) -> None:
    """It exits 1 and NAMES the column, because the operator has to know which of the two
    JSON columns to edit. Previously `summary` printed counts computed under the catalog
    defaults, which is a different policy than the user set."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    _corrupt_policy(env)

    result = _run(env, ["eligibility", "summary"])

    assert result.exit_code == 1, result.output
    assert "eligibility_policy_json" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["top"],
        ["export", "--format", "jsonl"],
        ["eligibility", "run"],
        ["stats"],
    ],
    ids=["top", "export", "eligibility-run", "stats"],
)
def test_every_command_that_reads_the_profile_refuses_an_unusable_row_cleanly(
    env: Path, args: list[str]
) -> None:
    """T7 follow-up, found by review. `_profile_row.py`'s own docstring says the CLI's job is to
    name the column and exit 1, because "a traceback names a line in pydantic, which is not the
    thing the operator has to edit" — but four commands reached `run_eligibility` / `compute_stats`
    with no handler at all, so they crashed with exactly that traceback. They are also the four an
    operator runs most.

    The run still REFUSED in every case, so the keystone was never at risk; what was wrong was
    that the refusal was unreadable.
    """
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    _corrupt_policy(env)

    result = _run(env, args)

    assert result.exit_code == 1, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert "eligibility_policy_json" in result.output
    assert "Traceback" not in result.output


# ---- the near-miss ceiling is per-user policy data (T47, D-480)

def test_setting_a_near_miss_ceiling(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "policy", "ceiling", "experience_years", "1"])
    assert result.exit_code == 0, result.output
    _, policy = _facts(env)
    assert policy.near_miss_years_ceilings == {"experience_years": 1}


def test_setting_a_ceiling_preserves_the_severity_map(env: Path) -> None:
    """The two live on ONE stored document, so a writer that rebuilt the model from the new
    value alone would silently clear the severities the user set first."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "policy", "set", "experience_years", "blocker"]).exit_code == 0
    assert _run(env, ["eligibility", "policy", "ceiling", "experience_years", "1"]).exit_code == 0
    _, policy = _facts(env)
    assert policy.families["experience_years"] == "blocker"
    assert policy.near_miss_years_ceilings == {"experience_years": 1}


def test_setting_a_severity_preserves_the_ceiling(env: Path) -> None:
    """The REVERSE order, and the one that actually regressed: both values live on one stored
    document, so a writer that rebuilds `Policy` from its own field alone silently discards
    the other. Harmless while `families` was the only field; a wiped floor once it is not."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "policy", "ceiling", "experience_years", "1"]).exit_code == 0
    assert _run(env, ["eligibility", "policy", "set", "experience_years", "blocker"]).exit_code == 0
    _, policy = _facts(env)
    assert policy.near_miss_years_ceilings == {"experience_years": 1}
    assert policy.families["experience_years"] == "blocker"


def test_a_family_declaring_no_ceiling_is_refused(env: Path) -> None:
    """`work_auth` is a real catalog family, so this cannot be caught by the family check
    `policy set` already does -- it is refused because no ceiling applies to it, and the
    message has to name the families where one does."""
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "policy", "ceiling", "work_auth", "1"])
    assert result.exit_code != 0
    assert "experience_years" in result.output
    _, policy = _facts(env)
    assert policy.near_miss_years_ceilings == {}


def test_a_negative_ceiling_is_refused_by_the_pure_writer() -> None:
    """Asserted on the pure writer, not through the CLI. A negative literal on the command
    line is refused by the option parser before the writer is ever reached, so a CLI-only
    test would pass with no validation in this function at all -- it would be green against
    a writer that stored -1 happily."""
    catalog = load_rules(Path("/nonexistent-override"))
    with pytest.raises(typer.BadParameter, match="0 or more"):
        set_ceiling(Policy(), catalog, "experience_years", -1)


def test_a_negative_ceiling_never_reaches_the_store(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    assert _run(env, ["eligibility", "policy", "ceiling", "experience_years", "-1"]).exit_code != 0
    _, policy = _facts(env)
    assert policy.near_miss_years_ceilings == {}


def test_a_non_integer_ceiling_is_refused(env: Path) -> None:
    assert _run(env, ["init"], INIT_INPUT).exit_code == 0
    result = _run(env, ["eligibility", "policy", "ceiling", "experience_years", "1.5"])
    assert result.exit_code != 0
    assert "1.5" in result.output
    _, policy = _facts(env)
    assert policy.near_miss_years_ceilings == {}
