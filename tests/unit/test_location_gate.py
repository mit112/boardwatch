"""US-only location classifier for the hard location gate (Mit's visa requirement).

`classify_location` reads a posting's location strings + remote_policy and returns one of
`us` / `non_us` / `unknown`. The hard gate keeps `us` and (fail-open, Mit's ruling)
`unknown`, and drops `non_us`. Positive-allowlist shape, per job-apps' `_radancy_location_is_us`
lesson: a hard gate must confirm US, never merely fail to recognise non-US.

Cases below encode the collisions job-apps paid for: "Bangalore, IN" is India not Indiana;
"Paris, TX" is US not France; one US location among several non-US keeps the posting (Mit can
take the US one).
"""

import pytest

from boardwatch.rank.location_gate import classify_location


def _c(*locations: str) -> str:
    return classify_location(list(locations))


class TestUnambiguousUS:
    @pytest.mark.parametrize(
        "loc",
        [
            "San Francisco, CA",
            "New York, NY",
            "Austin, TX, United States",
            "San Mateo, CA, United States",
            "Seattle, Washington",
            "US",
            "USA",
            "Boston, MA 02110",
        ],
    )
    def test_explicit_us_signals(self, loc: str) -> None:
        assert _c(loc) == "us"

    @pytest.mark.parametrize("loc", ["San Francisco", "Seattle", "Austin", "Houston", "Palo Alto"])
    def test_bare_us_cities(self, loc: str) -> None:
        assert _c(loc) == "us"


class TestUnambiguousNonUS:
    @pytest.mark.parametrize(
        "loc",
        [
            "London, United Kingdom",
            "Toronto, Canada",
            "Bangalore, India",
            "Tel Aviv, Israel",
            "Copenhagen, Denmark",
            "Munich, Germany",
        ],
    )
    def test_explicit_non_us_countries(self, loc: str) -> None:
        assert _c(loc) == "non_us"

    @pytest.mark.parametrize("loc", ["London", "Bengaluru", "Toronto", "Seoul", "Tokyo"])
    def test_bare_non_us_cities(self, loc: str) -> None:
        assert _c(loc) == "non_us"


class TestCollisions:
    def test_in_is_india_not_indiana_when_the_city_is_indian(self) -> None:
        # job-apps regression: `is_non_us_location` read "IN" as Indiana and kept it.
        assert _c("Bangalore, IN") == "non_us"

    def test_a_us_state_abbrev_wins_over_a_city_name_shared_with_a_foreign_one(self) -> None:
        # "Paris, TX" is Texas, not France — the state suffix disambiguates.
        assert _c("Paris, TX") == "us"

    def test_the_same_city_name_with_a_foreign_country_is_non_us(self) -> None:
        assert _c("Paris, France") == "non_us"


class TestMultiLocation:
    def test_any_us_location_keeps_the_posting(self) -> None:
        # Mit can take the US role, so a posting offered in the US AND abroad is US-eligible.
        assert _c("Sunnyvale, CA; Toronto, Canada") == "us"

    def test_all_non_us_locations_drop(self) -> None:
        assert _c("Toronto, Canada; Vancouver, Canada") == "non_us"

    def test_a_non_us_signal_with_an_unknown_segment_and_no_us_is_non_us(self) -> None:
        assert _c("EMEA", "Bordeaux", "Remote - France") == "non_us"


class TestRemote:
    def test_us_scoped_remote_is_us(self) -> None:
        assert _c("Remote - US") == "us"
        assert _c("Remote (United States)") == "us"

    def test_non_us_scoped_remote_is_non_us(self) -> None:
        assert _c("Remote - EMEA") == "non_us"
        assert _c("Remote - India") == "non_us"

    def test_bare_remote_scope_is_unknown(self) -> None:
        # No country in the string and the policy flag carries no geography.
        assert _c("Remote") == "unknown"


class TestUnknown:
    @pytest.mark.parametrize("loc", ["Americas", "North America", "Worldwide", "Anywhere"])
    def test_ambiguous_multiregion_is_unknown(self, loc: str) -> None:
        assert _c(loc) == "unknown"

    def test_empty_is_unknown(self) -> None:
        assert classify_location([]) == "unknown"

    def test_policy_only_segments_do_not_decide(self) -> None:
        # "Hybrid"/"Remote" carry no geography, so a real non-US city still decides.
        assert _c("Hybrid", "Mexico City, MX") == "non_us"
        assert _c("Hybrid") == "unknown"
