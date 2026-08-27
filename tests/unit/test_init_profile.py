from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.eligibility.facts import parse_facts, parse_policy
from boardwatch.store import tables
from boardwatch.store.db import get_engine
from boardwatch.store.queries import get_profile

runner = CliRunner()

INIT_INPUT = (
    "3\n"  # path choice → paste
    "acme, globex\n"  # slugs
    "Backend engineer: Python, Go, PostgreSQL, Kubernetes.\n"  # profile text
    "Backend Engineer, Software Engineer\n"  # target titles
    "Staff, Principal\n"  # exclude titles
    "New York, Remote\n"  # locations
    "n\n"  # remote only?
    "n\n"  # set up eligibility now?
)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "data"


def _invoke(data_dir: Path, args: list[str], input_text: str | None = None) -> object:
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=input_text)


def test_init_creates_watches_and_profile(env: Path) -> None:
    result = _invoke(env, ["init"], INIT_INPUT)
    assert result.exit_code == 0
    engine = get_engine(env)
    with engine.connect() as conn:
        companies = conn.execute(select(tables.companies).order_by(tables.companies.c.slug)).all()
        profile = conn.execute(select(tables.profile)).one()
    assert [(c.slug, c.provider, c.source, c.watched) for c in companies] == [
        ("acme", "greenhouse", "user", True),
        ("globex", "greenhouse", "user", True),
    ]
    assert {"Python", "Go", "PostgreSQL", "Kubernetes"} <= set(profile.skills_json)
    assert profile.taxonomy_version
    assert profile.target_titles_json == ["Backend Engineer", "Software Engineer"]
    assert profile.exclude_titles_json == ["Staff", "Principal"]
    assert profile.locations_json == ["New York", "Remote"]
    assert profile.remote_only is False


def test_init_is_idempotent(env: Path) -> None:
    assert _invoke(env, ["init"], INIT_INPUT).exit_code == 0
    rerun_input = INIT_INPUT.replace("Kubernetes", "Terraform")
    assert _invoke(env, ["init"], rerun_input).exit_code == 0
    engine = get_engine(env)
    with engine.connect() as conn:
        companies = conn.execute(select(tables.companies)).all()
        profiles = conn.execute(select(tables.profile)).all()
    assert len(companies) == 2  # updated, never duplicated
    assert len(profiles) == 1
    assert "Terraform" in profiles[0].skills_json  # re-derived on save


def test_zero_skill_warning(env: Path) -> None:
    no_skill_input = INIT_INPUT.replace(
        "Backend engineer: Python, Go, PostgreSQL, Kubernetes.",
        "I enjoy hiking and reading.",
    )
    result = _invoke(env, ["init"], no_skill_input)
    assert result.exit_code == 0
    assert "ranking will use" in result.output
    assert "title/recency/location only" in result.output


def test_profile_show(env: Path) -> None:
    _invoke(env, ["init"], INIT_INPUT)
    result = _invoke(env, ["profile", "show"])
    assert result.exit_code == 0
    assert "Python" in result.output
    assert "Taxonomy version" in result.output


def test_profile_show_without_profile_fails_cleanly(env: Path) -> None:
    result = _invoke(env, ["profile", "show"])
    assert result.exit_code == 1
    assert "boardwatch init" in result.output


def test_profile_edit_rederives_skills(env: Path) -> None:
    _invoke(env, ["init"], INIT_INPUT)
    edit_input = (
        "Now focused on Rust and Kafka stream processing.\n"  # new text
        "\n"  # keep target titles
        "\n"  # keep exclude titles
        "\n"  # keep locations
        "n\n"  # remote only
        "\n"  # keep resume max pages
        "\n"  # keep target seniority band
        "n\n"  # update eligibility checks? no
    )
    result = _invoke(env, ["profile", "edit"], edit_input)
    assert result.exit_code == 0
    engine = get_engine(env)
    with engine.connect() as conn:
        profile = conn.execute(select(tables.profile)).one()
    assert "Rust" in profile.skills_json and "Kafka" in profile.skills_json
    assert "Python" not in profile.skills_json


def test_profile_input_validated_at_the_boundary() -> None:
    from pydantic import ValidationError

    from boardwatch.cli.profile_cmd import ProfileInput

    with pytest.raises(ValidationError):  # empty/whitespace-only text never persists
        ProfileInput(
            text="", target_titles=[], exclude_titles=[], locations=[], remote_only=False
        )


def test_help_smoke(env: Path) -> None:
    assert runner.invoke(app, ["init", "--help"]).exit_code == 0
    assert runner.invoke(app, ["profile", "--help"]).exit_code == 0


# --- Task 11: catalog-driven eligibility during init and profile edit ---

# Eligibility prompts, in catalog family order:
# work_auth(status,jurisdiction,needs_sponsorship,policy),
# experience_years(total,policy), clearance(scheme,level,state,accesses,obtainable,policy),
# degree(highest_degree,policy), contract_not_fte(preference,policy),
# internship(preference,policy). A blank field is skipped; a blank policy takes the default.
# This script is POSITIONAL, so a new family (or field) shifts every later answer. That is
# why P9 and P2a had to edit it, and why
# test_init_reprompts_on_a_bad_eligibility_answer_instead_of_aborting in
# tests/pipeline/test_eligibility_flow.py builds its stdin from catalog.families instead.
_ELIG_INIT = (
    "3\nacme\nBackend engineer: Python, Go.\n\n\n\nn\n"  # companies, profile, filters, remote
    "y\n"                          # set up eligibility now?
    "\n"                           # career field: skip
    "citizen\nus\n\nblocker\n"     # work_auth: skip needs_sponsorship
    "\n\n"                      # experience_years: skip field, default policy
    "\n\n\n\n\n\n"              # clearance: skip five fields, default policy
    "none\nblocker\n"           # degree
    "fte_only\nblocker\n"       # contract_not_fte
    "exclude\n\n"               # internship: default policy
)


def test_init_eligibility_path_persists_facts_and_policy(env: Path) -> None:
    assert _invoke(env, ["init"], _ELIG_INIT).exit_code == 0
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    facts = parse_facts(row.eligibility_facts_json)
    policy = parse_policy(row.eligibility_policy_json)
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "citizen"
    assert facts.work_authorization.jurisdiction == "us"
    assert facts.highest_degree == "none"
    assert facts.total_years_experience is None  # blank field stayed absent
    assert policy.families["work_auth"] == "blocker"
    assert policy.families["degree"] == "blocker"
    # P9's two families are prompted by the same catalog-driven loop, with no new call site.
    assert facts.employment_type_preference == "fte_only"
    assert facts.internship_preference == "exclude"
    assert policy.families["contract_not_fte"] == "blocker"
    # A blank policy answer takes the catalog default, which is `preference` for both.
    assert policy.families["internship"] == "preference"


def test_init_career_field_prompt_persists_the_answer(env: Path) -> None:
    elig_input = _ELIG_INIT.replace(
        "y\n"          # set up eligibility now?
        "\n",          # career field: skip
        "y\n"          # set up eligibility now?
        "software\n",  # career field: set
        1,
    )
    assert _invoke(env, ["init"], elig_input).exit_code == 0
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    facts = parse_facts(row.eligibility_facts_json)
    assert facts.career_field == "software"


def test_init_reprompts_on_a_bad_career_field_instead_of_aborting(env: Path) -> None:
    """An out-of-vocabulary career field must be re-asked, not accepted and not fatal.

    Accepting it would store `nursing` and shift every later answer by one line; aborting
    would discard the profile answers already entered. Both are visible from here.
    """
    elig_input = _ELIG_INIT.replace(
        "y\n"          # set up eligibility now?
        "\n",          # career field: skip
        "y\n"          # set up eligibility now?
        "nursing\n"    # career field: not in the catalog vocabulary → re-prompt
        "software\n",  # career field: the retry
        1,
    )
    result = _invoke(env, ["init"], elig_input)
    assert result.exit_code == 0
    assert "unknown career_field 'nursing'" in result.output
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    facts = parse_facts(row.eligibility_facts_json)
    assert facts.career_field == "software"
    # The retry consumed the career-field prompt, so the later answers did not slide up.
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "citizen"


def test_init_skipping_eligibility_leaves_columns_null(env: Path) -> None:
    skip = "3\nacme\nBackend engineer: Python, Go.\n\n\n\nn\nn\n"  # trailing n: skip eligibility
    assert _invoke(env, ["init"], skip).exit_code == 0
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    assert row.eligibility_facts_json is None
    assert row.eligibility_policy_json is None


# The edit-side counterpart of _ELIG_INIT, and just as POSITIONAL: `profile edit` re-asks the
# profile and filter prompts first, then the same eligibility prompts as init.
_ELIG_EDIT = (
    "\n\n\n\n\n"                        # keep profile text and all filters
    "\n"                               # keep resume max pages
    "\n"                               # keep target seniority band
    "y\n"                              # update eligibility checks?
    "\n"                               # career field: skip (keeps stored value)
    "permanent_resident\nus\n\n\n"     # work_auth: change status, skip bit, default policy
    "\n\n"                             # experience_years
    "\n\n\n\n\n\n"                     # clearance (five fields plus policy)
    "master\n\n"                       # degree: change to master, default policy
    "open_to_contract\n\n"             # contract_not_fte: change, default policy
    "\n\n"                             # internship: keep `exclude` from init
)


def test_profile_edit_updates_eligibility(env: Path) -> None:
    assert _invoke(env, ["init"], _ELIG_INIT).exit_code == 0
    assert _invoke(env, ["profile", "edit"], _ELIG_EDIT).exit_code == 0
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    facts = parse_facts(row.eligibility_facts_json)
    assert facts.work_authorization is not None
    assert facts.work_authorization.status == "permanent_resident"
    assert facts.work_authorization.jurisdiction == "us"  # preserved from init
    assert facts.highest_degree == "master"
    assert facts.employment_type_preference == "open_to_contract"  # changed
    assert facts.internship_preference == "exclude"  # blank kept the init value


def test_profile_edit_sets_the_career_field(env: Path) -> None:
    """`profile edit` must be able to SET a career field, not merely skip past the prompt —
    otherwise the only thing an existing install can do with the field is leave it unset."""
    assert _invoke(env, ["init"], _ELIG_INIT).exit_code == 0
    edit = _ELIG_EDIT.replace(
        "y\n"          # update eligibility checks?
        "\n",          # career field: skip
        "y\n"          # update eligibility checks?
        "software\n",  # career field: set
        1,
    )
    assert _invoke(env, ["profile", "edit"], edit).exit_code == 0
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    facts = parse_facts(row.eligibility_facts_json)
    assert facts.career_field == "software"
    # The set answer consumed only the career-field prompt; the rest of the script still lands.
    assert facts.highest_degree == "master"


def test_profile_edit_reprompts_on_a_bad_career_field(env: Path) -> None:
    """Same re-prompt contract as init: a bogus value is re-asked, never stored, and never
    aborts the edit — the profile row has already been saved by this point."""
    assert _invoke(env, ["init"], _ELIG_INIT).exit_code == 0
    edit = _ELIG_EDIT.replace(
        "y\n"          # update eligibility checks?
        "\n",          # career field: skip
        "y\n"          # update eligibility checks?
        "nursing\n"    # career field: not in the catalog vocabulary → re-prompt
        "software\n",  # career field: the retry
        1,
    )
    result = _invoke(env, ["profile", "edit"], edit)
    assert result.exit_code == 0
    assert "unknown career_field 'nursing'" in result.output
    with get_engine(env).connect() as conn:
        row = get_profile(conn)
    assert row is not None
    facts = parse_facts(row.eligibility_facts_json)
    assert facts.career_field == "software"
    assert facts.highest_degree == "master"  # later answers did not slide up


def test_a_bad_seniority_band_reprompts_instead_of_discarding_the_edit(env: Path) -> None:
    """A typo must not abort the edit and throw away every answer already typed.

    The eligibility prompts loop for exactly this reason. A bare `typer.prompt` would let
    "Entry" raise a pydantic literal_error inside persist_profile, after the operator had
    already retyped their profile text, titles and locations.
    """
    _invoke(env, ["init"], INIT_INPUT)
    edit_input = (
        "\n"  # keep text
        "\n"  # keep target titles
        "\n"  # keep exclude titles
        "\n"  # keep locations
        "n\n"  # remote only
        "\n"  # keep resume max pages
        "Entry\n"  # BAD band — wrong case
        "entry\n"  # corrected
        "n\n"  # update eligibility checks? no
    )
    result = _invoke(env, ["profile", "edit"], edit_input)
    assert result.exit_code == 0
    assert "is not a seniority band" in result.output
    engine = get_engine(env)
    with engine.connect() as conn:
        assert get_profile(conn).target_seniority_band == "entry"
