"""Lane-death classification, latching, and factory wiring (P3 slice 5, D-146)."""

import httpx
import pytest

from boardwatch.llm.client import (
    LaneDeathReason,
    LLMError,
    LLMLaneDeadError,
    lane_death_reason,
)
from boardwatch.llm.retry import safe_json

_TABLE = {
    "billing_error": LaneDeathReason.CREDIT_EXHAUSTED,
    "authentication_error": LaneDeathReason.CREDENTIAL_INVALID,
}


def test_lane_dead_error_carries_a_typed_reason():
    exc = LLMLaneDeadError("HTTP 403", reason=LaneDeathReason.CREDIT_EXHAUSTED)
    assert exc.reason is LaneDeathReason.CREDIT_EXHAUSTED
    # It must remain catchable as the existing base class, so every current
    # `except LLMError` site keeps working unchanged.
    assert isinstance(exc, LLMError)


def test_classifier_maps_a_catalogued_type():
    body = {"error": {"type": "billing_error", "message": "credit balance too low"}}
    assert lane_death_reason(body, table=_TABLE) is LaneDeathReason.CREDIT_EXHAUSTED


def test_classifier_reads_the_code_field_too():
    # OpenAI-compatible providers put the token in `code`, not `type`.
    body = {"error": {"code": "authentication_error"}}
    assert lane_death_reason(body, table=_TABLE) is LaneDeathReason.CREDENTIAL_INVALID


@pytest.mark.parametrize(
    "body",
    [
        None,                                  # unparseable body
        [],                                     # non-object root
        "forbidden",                            # string root
        {},                                     # empty object
        {"error": "forbidden"},                 # error is a string, not an object
        {"error": {}},                          # no type/code at all
        {"error": {"type": 7}},                 # non-string type
        {"error": {"type": "unknown_error"}},   # out of catalog
        {"error": {"code": None}},              # null code
    ],
)
def test_classifier_never_raises_and_returns_none_for_unclassifiable(body):
    # A classifier that raises would land in extract_llm.py's blanket `except`
    # and reproduce the exact silent success this slice removes.
    assert lane_death_reason(body, table=_TABLE) is None


def test_safe_json_returns_none_instead_of_raising():
    assert safe_json(httpx.Response(403, text="not json")) is None
    assert safe_json(httpx.Response(403, json={"error": {"type": "x"}})) == {
        "error": {"type": "x"}
    }
