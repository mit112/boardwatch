"""A lane returns BoardSnapshots and is not a Provider (JD-acquisition spec §4.1, §4.2)."""

from boardwatch.core.models import RawPosting
from boardwatch.lanes.base import lane_snapshot
from boardwatch.providers.registry import build_providers


def _raw(pid: str = "in-1") -> RawPosting:
    return RawPosting(
        provider_posting_id=pid,
        title="Software Engineer, New Grad",
        url=f"https://example.test/jobs/{pid}",
        locations=["Seattle, WA"],
        body_text="we are hiring a new grad engineer",
        raw_json={},
    )


def test_a_lane_snapshot_is_always_partial():
    """`complete` is unexpressible. An empty `complete` closes a company's whole board."""
    assert lane_snapshot([_raw()], "https://example.test/search").status == "partial"
    assert lane_snapshot([], "https://example.test/search").status == "partial"


def test_a_lane_snapshot_never_claims_a_board_enumeration():
    snapshot = lane_snapshot([_raw()], "https://example.test/search")
    assert snapshot.listed_ids == frozenset()
    assert snapshot.board_reported_total is None
    assert snapshot.board_enumerated is None
    assert snapshot.detail_deferred is None
    assert snapshot.board_total_censored is None


def test_the_provider_registry_still_holds_exactly_the_six_ats_families():
    """A lane must never be registered: fixture rule R13 fires on a provider with no fixtures."""
    assert set(build_providers()) == {
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "workable",
        "workday",
    }
