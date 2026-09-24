"""DESIGN-T183 B3: the location gates read the tenant's `target_countries`, not a built-in US.

Three gates: the ranker's hard location veto (L5), its foreign-ad veto (L4) and the review
gate's location hold (L6). Undeclared targets make all three INERT and report the abstain (owner
ruling Q2). A target country with no positive pack also abstains: without the target's own pack
the resolver cannot apply the target-first order, so "London, ON" would read GBR. The `usa` pack
is the only one that ships (Q6), so a second tenant's pack is a fixture here.
"""

import pytest

from boardwatch.delivery.review_gate import REVIEW_DIR, LaneDecision
from boardwatch.delivery.review_gate import classify as _classify
from boardwatch.rank.heuristic import ProfileView, hard_filter_verdict
from boardwatch.rank.location_data import USA_PACK, CountryPack
from boardwatch.rank.location_gate import location_target
from boardwatch.rank.tenant_assumptions import ungrounded_reasons

CAN_PACK = CountryPack(
    iso3="CAN",
    markers=frozenset({"canada"}),
    bare_tokens=frozenset(),
    subdivision_names=frozenset({"ontario", "quebec", "british columbia", "alberta"}),
    subdivision_codes=frozenset({"ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE"}),
    postal_pattern=r"(?<![A-Za-z0-9])[A-Z]\d[A-Z] ?\d[A-Z]\d(?![A-Za-z0-9])",
    cities=frozenset({"toronto", "montreal", "ottawa", "vancouver"}),
)
WITH_CAN = (CAN_PACK, USA_PACK)


def _profile(*countries: str) -> ProfileView:
    return ProfileView(
        skills=frozenset(), target_titles=(), exclude_titles=(), locations=(),
        remote_only=False, target_countries=countries,
    )


def _veto(title: str, locations: list[str], profile: ProfileView, **kw: object) -> str | None:
    got = hard_filter_verdict(title, locations, "unknown", profile, "hard", **kw)  # type: ignore[arg-type]
    return None if got is None else got.clause


class TestTheTargetAndItsAbstain:
    def test_undeclared_abstains_on_the_missing_field(self) -> None:
        target = location_target(())
        assert target.abstain == "missing_profile_field:target_countries"
        assert target.classify(["London, United Kingdom"]) is None

    def test_a_target_with_no_pack_abstains_on_the_missing_pack(self) -> None:
        target = location_target(("CAN", "USA"))
        assert target.abstain == "missing_country_pack:CAN"
        assert target.classify(["Boston, MA"]) is None

    def test_a_us_target_reads_exactly_as_the_us_classifier(self) -> None:
        target = location_target(("USA",))
        assert target.abstain is None
        assert target.classify(["Boston, MA"]) == "in_target"
        assert target.classify(["London, United Kingdom"]) == "out_of_target"
        assert target.classify(["Remote"]) == "unknown"

    def test_the_targets_pack_goes_first(self) -> None:
        """"London, ON" is Ontario for a CAN tenant, although the token map says GBR."""
        target = location_target(("CAN",), (USA_PACK, CAN_PACK))
        assert target.classify(["London, ON"]) == "in_target"
        # Both packs claim this segment (the US state `CA`, the CAN subdivision "ontario"), so
        # only the ORDER decides it: the target's reading wins, the fail-open direction.
        assert target.classify(["Ontario, CA"]) == "in_target"
        assert location_target(("USA",), (CAN_PACK, USA_PACK)).classify(["Ontario, CA"]) == (
            "in_target"
        )


class TestTheRankerHardGate:
    def test_a_us_target_drops_a_foreign_posting(self) -> None:
        assert _veto("Engineer", ["London, United Kingdom"], _profile("USA")) == "non_us_location"

    def test_undeclared_targets_drop_nothing(self) -> None:
        assert _veto("Engineer", ["London, United Kingdom"], _profile()) is None
        assert _veto("Ingénieur (H/F)", ["Remote"], _profile()) is None

    def test_a_target_without_its_pack_drops_nothing(self) -> None:
        assert _veto("Registered Nurse", ["Toronto, ON"], _profile("CAN")) is None
        assert _veto("Registered Nurse", ["Boston, MA"], _profile("CAN")) is None

    def test_a_can_target_keeps_toronto_and_drops_boston(self) -> None:
        profile = _profile("CAN")
        assert _veto("Registered Nurse", ["Toronto, ON"], profile, location_packs=WITH_CAN) is None
        assert (
            _veto("Registered Nurse", ["Boston, MA"], profile, location_packs=WITH_CAN)
            == "non_us_location"
        )
        assert _veto("Physiotherapist", ["Remote"], profile, location_packs=WITH_CAN) is None

    def test_an_ad_marker_of_a_target_country_is_a_home_signal(self) -> None:
        assert _veto("Infirmière (H/F)", ["Remote"], _profile("USA")) == "foreign_ad_marker"
        assert _veto("Infirmière (H/F)", ["Remote"], _profile("CAN"), location_packs=WITH_CAN) is None

    def test_soft_mode_keeps_the_knob_and_vetoes_nothing(self) -> None:
        """Q7: `location_filter_mode` stays, with the target-set meaning."""
        got = hard_filter_verdict(
            "Engineer", ["London, United Kingdom"], "unknown", _profile("USA"), "soft"
        )
        assert got is None


def _review(locations: list[str], target: tuple[str, ...], **kw: object) -> LaneDecision:
    return _classify(  # type: ignore[arg-type]
        verdict="uncertain", locations=locations, role="swe",
        experience_unconfirmed=False, eligibility_unconfirmed=False, no_requirement_rows=False,
        posting_closed=False, seniority_above_band=False, judge_verdict=None,
        judge_seniority_above_band=False, revised_since_build=False,
        target_countries=target, **kw,
    )


class TestTheReviewHold:
    def test_a_us_target_holds_a_foreign_lead(self) -> None:
        assert _review(["Kaunas, Lithuania"], ("USA",)) == LaneDecision(
            REVIEW_DIR, "non_us_location"
        )

    def test_undeclared_targets_hold_nothing_on_location(self) -> None:
        assert _review(["Kaunas, Lithuania"], ()).reason != "non_us_location"

    def test_a_can_target_holds_boston_and_not_toronto(self) -> None:
        assert _review(["Toronto, ON"], ("CAN",), location_packs=WITH_CAN).reason is None
        assert _review(["Boston, MA"], ("CAN",), location_packs=WITH_CAN).reason == (
            "non_us_location"
        )
        assert _review(["Boston, MA"], ("CAN",)).reason is None  # no pack: abstain


@pytest.mark.parametrize(
    ("countries", "expected"),
    [
        ((), "missing_profile_field:target_countries"),
        (("CAN",), "missing_country_pack:CAN"),
        (("USA",), None),
    ],
)
def test_the_report_grounds_both_location_gates_on_the_target(
    countries: tuple[str, ...], expected: str | None
) -> None:
    got = ungrounded_reasons(
        field="software", taxonomy_field="software", target_seniority_band="entry",
        seniority_hold=True, target_countries=countries,
    )
    assert got["location"] == got["foreign_ad"] == expected
