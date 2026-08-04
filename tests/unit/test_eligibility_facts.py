"""Facts and policy are frozen boundary models and every missing or malformed value
fails closed to absent, so no resolver can read a semantically undefined value
(D-P2-15)."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from boardwatch.core.clock import utcnow
from boardwatch.eligibility.facts import (
    ClearanceFact,
    Facts,
    Policy,
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
    assert payload["work_authorization"] == {"status": "citizen", "jurisdiction": "us"}
    assert payload["security_clearance"] == {
        "scheme": "us_dod", "level": "top_secret", "state": "active", "accesses": ["sci"],
    }
    assert parse_facts(payload) == facts


def test_absent_facts_render_as_null_not_missing_keys() -> None:
    """A key that vanishes changes the hashed payload; an explicit null does not."""
    payload = facts_payload(Facts())
    assert set(payload) == {
        "work_authorization", "total_years_experience", "security_clearance", "highest_degree",
        "employment_type_preference", "internship_preference",
    }
    assert all(value is None for value in payload.values())


@pytest.mark.parametrize(
    "raw",
    [
        None,
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
def test_malformed_stored_facts_fail_closed_to_absent(raw: object) -> None:
    assert parse_facts(raw) == Facts()


def test_policy_defaults_to_no_overrides() -> None:
    assert parse_policy(None).families == {}
    assert parse_policy({"families": {"degree": "blocker"}}).families == {"degree": "blocker"}


@pytest.mark.parametrize(
    "raw",
    [{"families": {"degree": "sometimes"}}, {"families": "degree"}, {"families": ["degree"]}, 7],
)
def test_malformed_stored_policy_fails_closed_to_no_overrides(raw: object) -> None:
    assert parse_policy(raw) == Policy()


def _engine(tmp_path: Path):
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _base_profile(engine) -> None:
    with engine.begin() as conn:
        save_profile(
            conn, text="a profile", target_titles=[], exclude_titles=[], locations=[],
            remote_only=False, skills=[], taxonomy_version="v1",
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
            taxonomy_version="v2",
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
