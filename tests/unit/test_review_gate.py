"""Delivery-time apply/review lane classifier (`delivery/review_gate.lane`).

Fixture strings are calibrated against the live `classify_location` / `role_verdict`
classifiers (2026-08-27): US cities classify `us`; "Kaunas Office" is `unknown`
(city without a country); "Kaunas, Lithuania"/"Zhubei, Taiwan" are `non_us`;
"Front Office Agent"/"Field Auto Appraiser" have no role signal → `uncertain`.
"""

from __future__ import annotations

from boardwatch.delivery.review_gate import REVIEW_DIR, lane


def test_eligible_always_applies_regardless_of_location_or_role() -> None:
    assert lane(verdict="eligible", locations=["Kaunas, Lithuania"], title="Janitor") == ""


def test_verified_uncertain_us_swe_is_promoted_to_apply() -> None:
    assert (
        lane(
            verdict="uncertain",
            locations=["San Jose, CA, United States"],
            title="Software Engineer",
        )
        == ""
    )


def test_uncertain_unknown_location_routes_to_review() -> None:
    # "Kaunas Office" classifies as unknown (city, no country) -> not positively US.
    assert (
        lane(
            verdict="uncertain",
            locations=["Kaunas Office"],
            title="Associate JAVA Software Engineer",
        )
        == REVIEW_DIR
    )


def test_uncertain_foreign_location_routes_to_review() -> None:
    assert (
        lane(verdict="uncertain", locations=["Kaunas, Lithuania"], title="Software Engineer")
        == REVIEW_DIR
    )


def test_uncertain_non_swe_role_routes_to_review() -> None:
    assert (
        lane(
            verdict="uncertain",
            locations=["Chicago, Illinois, United States"],
            title="Front Office Agent",
        )
        == REVIEW_DIR
    )
    assert (
        lane(
            verdict="uncertain",
            locations=["USA - NY (Remote)"],
            title="Field Auto Appraiser",
        )
        == REVIEW_DIR
    )


def test_unevaluated_none_verdict_routes_to_review() -> None:
    # None means never eligibility-checked for the current identity — not verified-appliable.
    assert lane(verdict=None, locations=["Austin, TX"], title="Software Engineer") == REVIEW_DIR


def test_empty_locations_routes_to_review() -> None:
    assert lane(verdict="uncertain", locations=[], title="Software Engineer") == REVIEW_DIR
