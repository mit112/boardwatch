"""Facts and policy are frozen boundary models. An ABSENT value is legitimate and reads
as absent, so no resolver can read a semantically undefined value (D-P2-15); a MALFORMED
value is refused with `ProfileRowInvalid`, because a policy that fails closed to the
catalog defaults drops five of six families to `preference` and clears postings the
user's own policy rejects."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from boardwatch.core.clock import utcnow
from boardwatch.eligibility.facts import (
    ClearanceFact,
    Facts,
    Policy,
    ProfileRowInvalid,
    WorkAuthFact,
    facts_payload,
    parse_facts,
    parse_policy,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import get_profile, save_eligibility, save_profile
from boardwatch.store.tables import profile as profile_table


def test_facts_default_to_absent() -> None:
    facts = Facts()
    assert facts.work_authorization is None
    assert facts.total_years_experience is None
    assert facts.security_clearance is None
    assert facts.highest_degree is None


def test_facts_are_frozen() -> None:
    facts = Facts(highest_degree="bachelor")
    with pytest.raises(ValidationError):
        facts.highest_degree = "master"  # type: ignore[misc]


def test_structured_facts_round_trip() -> None:
    facts = Facts(
        work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"),
        total_years_experience=8,
        security_clearance=ClearanceFact(
            scheme="us_dod", level="top_secret", state="active", accesses=("sci",)
        ),
        highest_degree="master",
    )
    payload = facts_payload(facts)
    assert payload["work_authorization"] == {
        "status": "citizen", "jurisdiction": "us", "needs_sponsorship": None,
    }
    assert payload["security_clearance"] == {
        "scheme": "us_dod", "level": "top_secret", "state": "active", "accesses": ["sci"],
        "obtainable": None,
    }
    assert parse_facts(payload) == facts


def test_absent_facts_render_as_null_not_missing_keys() -> None:
    """A key that vanishes changes the hashed payload; an explicit null does not."""
    payload = facts_payload(Facts())
    assert set(payload) == {
        "work_authorization", "total_years_experience", "security_clearance", "highest_degree",
        "field_of_study", "employment_type_preference", "internship_preference",
        "education_timing",
        "career_field",  # engine-gated (not resolver-declared) — hashed unconditionally, per B1
    }
    assert all(value is None for value in payload.values())


@pytest.mark.parametrize(
    "raw",
    [
        # `None` is deliberately NOT here: an unset column is absent, not malformed. It has
        # its own control, test_an_absent_column_still_reads_as_absent.
        "not a mapping",
        [],
        {"total_years_experience": "five"},
        # A boolean is not a year count. pydantic coerces True->1 / False->0 by default,
        # which is a GUESS (D-P2-15) that resolves `unmet` where the fact should be absent.
        {"total_years_experience": True},
        {"total_years_experience": False},
        {"work_authorization": "citizen"},
        {"work_authorization": {"status": "citizen", "unknown_key": 1}},
        {"security_clearance": {"accesses": "sci"}},
        {"highest_degree": ["bachelor"]},
    ],
)
def test_malformed_stored_facts_are_refused(raw: object) -> None:
    with pytest.raises(ProfileRowInvalid) as caught:
        parse_facts(raw)
    assert caught.value.column == "eligibility_facts_json"


def test_policy_defaults_to_no_overrides() -> None:
    assert parse_policy(None).families == {}
    assert parse_policy({"families": {"degree": "blocker"}}).families == {"degree": "blocker"}


@pytest.mark.parametrize(
    "raw",
    [{"families": {"degree": "sometimes"}}, {"families": "degree"}, {"families": ["degree"]}, 7],
)
def test_malformed_stored_policy_is_refused(raw: object) -> None:
    with pytest.raises(ProfileRowInvalid) as caught:
        parse_policy(raw)
    assert caught.value.column == "eligibility_policy_json"


def test_an_unknown_facts_key_names_itself_in_the_refusal() -> None:
    """The operator has to know WHICH key made the row unusable; a bare "invalid" leaves
    them editing JSON blind."""
    with pytest.raises(ProfileRowInvalid) as caught:
        parse_facts({"years_experience": 1, "stray": 1})
    assert caught.value.column == "eligibility_facts_json"
    assert "stray" in str(caught.value)


def test_a_bare_families_map_is_refused_not_read_as_no_overrides() -> None:
    """The exact shape that fooled the 2026-09-04 review's own probe: the FAMILIES dict
    stored where a Policy document belongs. Read as "no overrides" it materialises the
    catalog defaults, where only work_auth is a blocker and the other five families drop
    to `preference` — a severity that can never yield `ineligible`. That is a CLEARING
    failure, so it must be loud."""
    with pytest.raises(ProfileRowInvalid) as caught:
        parse_policy({"experience_years": "blocker"})
    assert caught.value.column == "eligibility_policy_json"
    assert "experience_years" in str(caught.value)


def test_a_non_json_object_payload_is_refused() -> None:
    with pytest.raises(ProfileRowInvalid):
        parse_policy("not json")
    with pytest.raises(ProfileRowInvalid):
        parse_facts("not json")


def test_an_absent_column_still_reads_as_absent() -> None:
    """The control, and the whole distinction this ticket draws: never SET is legitimate
    (a fresh install, an upgraded schema); set to nonsense is not."""
    assert parse_facts(None) == Facts()
    assert parse_policy(None) == Policy()


def _engine(tmp_path: Path):
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _base_profile(engine) -> None:
    with engine.begin() as conn:
        save_profile(
            conn, text="a profile", target_titles=[], exclude_titles=[], locations=[],
            remote_only=False, skills=[], taxonomy_version="v1", resume_max_pages=1,
        )


def test_save_eligibility_writes_after_the_profile_row_exists(tmp_path: Path) -> None:
    """profile.text is NOT NULL with no default, so facts are written by a separate
    UPDATE after persist_profile, never before (spec §4.6 ordering constraint 1)."""
    engine = _engine(tmp_path)
    _base_profile(engine)
    facts = Facts(highest_degree="bachelor", total_years_experience=8)
    policy = Policy(families={"degree": "blocker"})
    with engine.begin() as conn:
        save_eligibility(
            conn,
            facts_json=facts_payload(facts),
            policy_json=policy.model_dump(mode="json"),
        )
    with engine.connect() as conn:
        row = get_profile(conn)
    assert row is not None
    assert parse_facts(row.eligibility_facts_json) == facts
    assert parse_policy(row.eligibility_policy_json) == policy


def test_save_profile_never_wipes_declared_facts(tmp_path: Path) -> None:
    """REGRESSION LOCK: if save_profile's set_ map ever lists the two eligibility
    columns, `profile edit` silently destroys the user's declared facts."""
    engine = _engine(tmp_path)
    _base_profile(engine)
    facts = Facts(highest_degree="master")
    with engine.begin() as conn:
        save_eligibility(
            conn,
            facts_json=facts_payload(facts),
            policy_json=Policy(families={"degree": "blocker"}).model_dump(mode="json"),
        )
    with engine.begin() as conn:  # a later profile edit
        save_profile(
            conn, text="edited profile", target_titles=["Backend Engineer"],
            exclude_titles=[], locations=[], remote_only=True, skills=["Python"],
            taxonomy_version="v2", resume_max_pages=1,
        )
    with engine.connect() as conn:
        row = get_profile(conn)
    assert row is not None
    assert row.text == "edited profile"
    assert parse_facts(row.eligibility_facts_json) == facts
    assert parse_policy(row.eligibility_policy_json).families == {"degree": "blocker"}


def test_save_profile_set_map_does_not_mention_the_eligibility_columns() -> None:
    """A structural lock alongside the behavioural one: the behavioural test would also
    pass if someone added the columns to the map with the same values by accident."""
    import inspect

    source = inspect.getsource(save_profile)
    assert "eligibility_facts_json" not in source
    assert "eligibility_policy_json" not in source


def test_save_eligibility_leaves_other_profile_columns_alone(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _base_profile(engine)
    with engine.begin() as conn:
        save_eligibility(
            conn,
            facts_json=facts_payload(Facts(highest_degree="none")),
            policy_json=Policy().model_dump(mode="json"),
        )
    with engine.connect() as conn:
        row = conn.execute(select(profile_table).where(profile_table.c.id == 1)).one()
    assert row.text == "a profile"
    assert row.taxonomy_version == "v1"


def test_reading_a_profile_with_null_columns_yields_absent_values(tmp_path: Path) -> None:
    """The upgraded-install path: NULL columns mean no facts and no policy overrides."""
    engine = _engine(tmp_path)
    _base_profile(engine)
    with engine.connect() as conn:
        row = get_profile(conn)
    assert row is not None
    assert parse_facts(row.eligibility_facts_json) == Facts()
    assert parse_policy(row.eligibility_policy_json) == Policy()
    assert utcnow() is not None  # clock convention smoke
