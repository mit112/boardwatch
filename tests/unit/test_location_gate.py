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

from boardwatch.rank.location_data import (
    AMBIGUOUS_REGIONS,
    NON_US_CITIES,
    NON_US_COUNTRIES,
    NON_US_REGIONS,
    US_CITIES,
    US_MARKERS,
    US_STATE_NAMES,
)
from boardwatch.rank.location_gate import _alternation, classify_location


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
    @pytest.mark.parametrize(
        "loc",
        [
            # US towns that share a foreign city/country name — a US STATE suffix must keep
            # them (the reviewed regression: the reverse order silently DROPPED these real US
            # postings in hard mode, the worst error for a visa gate).
            "Vienna, VA",
            "Vienna, Virginia",
            "Lebanon, NH",
            "Panama City, FL",
            "Athens, GA",
            "Manchester, NH",
            "Rome, NY",
            "Mexico, MO",
            "Peru, IN",
            "London, KY",
            "Berlin, NH",
            "Lima, OH",
            "China, TX",
            "Paris, TX",
        ],
    )
    def test_a_us_state_suffix_keeps_a_town_that_shares_a_foreign_name(self, loc: str) -> None:
        assert _c(loc) == "us"

    @pytest.mark.parametrize(
        "loc",
        [
            "Vienna, Austria",
            "Athens, Greece",
            "London, United Kingdom",
            "Paris, France",
            "Rome, Italy",
        ],
    )
    def test_the_same_names_with_a_foreign_country_are_non_us(self, loc: str) -> None:
        assert _c(loc) == "non_us"

    def test_a_bare_state_code_that_is_also_a_country_code_leaks_to_us_not_dropped(self) -> None:
        # "Bangalore, IN" is India, but ", IN" is also Indiana's code. It resolves `us` (kept)
        # rather than `non_us` (dropped) — a deliberate FAIL-OPEN leak, never a false drop. The
        # spelled-out country form is still read correctly as non-US.
        assert _c("Bangalore, IN") == "us"
        assert _c("Bangalore, India") == "non_us"


class TestMultiLocation:
    def test_any_us_location_keeps_the_posting(self) -> None:
        # Mit can take the US role, so a posting offered in the US AND abroad is US-eligible.
        assert _c("Sunnyvale, CA; Toronto, Canada") == "us"

    def test_all_non_us_locations_drop(self) -> None:
        assert _c("Toronto, Canada; Vancouver, Canada") == "non_us"

    def test_a_non_us_signal_with_an_unknown_segment_and_no_us_is_non_us(self) -> None:
        assert _c("EMEA", "Bordeaux", "Remote - France") == "non_us"


class TestUSAndForeignInOneSegment:
    """A single location string naming the US AND a foreign place is US-eligible — the posting
    is offered in the US. Regression: the gate dropped these as non_us because bare "US" was
    resolved AFTER the foreign country token, and only ';|/•| or ' split segments so a comma /
    "and" / "&" never separated them."""

    @pytest.mark.parametrize(
        "loc",
        [
            "US, Canada",
            "US and Canada",
            "US & Canada",
            "Remote - US, Canada",
            "US, EMEA",
            "U.S., Canada",
        ],
    )
    def test_bare_us_beside_a_foreign_place_is_us(self, loc: str) -> None:
        assert _c(loc) == "us"

    @pytest.mark.parametrize(
        "loc",
        [
            # Controls that must NOT flip: a foreign place with no US signal stays non_us. In
            # particular a US CITY that merely shares a foreign name is still resolved AFTER the
            # non-US tokens, so "Manchester, UK" is not rescued to US by the fix.
            "London, UK",
            "Manchester, UK",
            "Toronto, Canada",
            "Berlin, Germany",
            "Bangalore, India",
            "Remote - EMEA",
        ],
    )
    def test_a_foreign_place_without_a_us_signal_stays_non_us(self, loc: str) -> None:
        assert _c(loc) == "non_us"


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


class TestForeignCityCatalogAdditions:
    """Cities that reached run 65's shortlist through the `unknown` fail-open.

    Every token was checked against the corpus before being added: it names no US town a
    posting could plausibly carry, so promoting it to `non_us` cannot delete a real US role.
    """

    @pytest.mark.parametrize(
        "loc",
        [
            "Buc",
            "Basel",
            "Penzberg",
            "Kleinmachnow",
            "Suresnes",
            "Kaiseraugst",
            "Grenzach",
            "Böblingen",
            "Mannheim",
            "Lodz",
            "Petaling Jaya",
            "Sao Jose dos Campos",
            "Uppsala",
            "Seongnam",
            "Klagenfurt",
            "Barueri",
            "Ciudad Juarez",
            "Drachten",
            "Diegem",
            "Rio de Janeiro",
            "Islamabad",
            "Rehovot",
            "Saskatoon",
            "Warszawa",
            "Abidjan",
            "Wuhan",
            "Hino",
            "Danderyd",
        ],
    )
    def test_unambiguous_foreign_cities_are_non_us(self, loc: str) -> None:
        assert _c(loc) == "non_us"

    @pytest.mark.parametrize("loc", ["Saxony", "Thuringia"])
    def test_foreign_subnational_regions_are_non_us(self, loc: str) -> None:
        assert _c(loc) == "non_us"

    def test_a_new_city_token_still_loses_to_an_explicit_us_signal(self) -> None:
        # The additions go in BELOW the US checks, so the ordering that protects US towns is
        # untouched: a US state suffix or a bare "US" beside the city still wins.
        assert _c("Sunnyvale, CA; Basel") == "us"
        assert _c("US, Basel") == "us"


class TestUSNamesakesStayFailOpen:
    """The curation rule's other half. A name shared with a real US town is deliberately left
    OUT of the catalog, so it stays `unknown` (kept) rather than `non_us` (dropped): a future
    Dublin OH / Limerick PA / Birmingham AL posting must never be silently deleted. Mit's
    ruling, and the same standard that already keeps Paris and Cambridge out.
    """

    @pytest.mark.parametrize(
        "loc",
        [
            "Dublin",
            "Cambridge",
            "Limerick",
            "Uxbridge",
            "Abingdon",
            "Birmingham",
            "Warren",
            "Ontario",
            "Valencia",
            "Best",
            "Moscow",
        ],
    )
    def test_a_name_with_a_us_namesake_is_never_dropped(self, loc: str) -> None:
        assert _c(loc) != "non_us"

    @pytest.mark.parametrize(
        "loc",
        ["Princeton University", "Armonk", "NY office", "UT MAIN CAMPUS", "Waukesha", "Lehi"],
    )
    def test_us_places_outside_the_city_allowlist_stay_unknown(self, loc: str) -> None:
        # These are real US locations the allowlist does not name. Fail-open keeps them; the
        # new tokens must not have widened far enough to catch them.
        assert _c(loc) == "unknown"


class TestStructuralCountryCode:
    """Some providers emit an ISO-3166 alpha-3 country code where no city token exists —
    a site code ("VNM06-01-Ho Chi Minh"), a dash prefix ("BGR-Varna"), or a parenthesised
    suffix ("Remote (IND)"). Three letters, so unlike a 2-letter code it collides with no US
    state abbreviation, which is why only the alpha-3 form is read.
    """

    @pytest.mark.parametrize(
        "loc",
        [
            "BGR-Varna",
            "SGP-Robinson Road SO",
            "VNM06-01-Ho Chi Minh- Crescent Plaza",
            "HUN04-01-Paty-Csonka Janos 1-3",
            "IDN05-01-Jakarta- Jl.R. A Kartini Kav. 8",
            "MYS03-01-Kuala Lumpur-Plaza Sentral",
            "RUS06-01-Moscow-Naberezhnaya Tower",
            "VNM.Ho Chi Minh",
            "Remote (IND)",
            "Dublin (IRL)",
        ],
    )
    def test_a_structural_non_us_country_code_is_non_us(self, loc: str) -> None:
        assert _c(loc) == "non_us"

    def test_the_code_decides_where_the_city_token_deliberately_does_not(self) -> None:
        # "Dublin" alone stays fail-open (US namesake), but "Dublin (IRL)" names its country.
        assert _c("Dublin") == "unknown"
        assert _c("Dublin (IRL)") == "non_us"

    @pytest.mark.parametrize(
        "loc",
        [
            "USA-GA-Remote Location",
            "USA-NJ-Remote Location",
            "USA-California-San Jose-1320 Ridder Park",
        ],
    )
    def test_the_us_alpha_3_in_the_same_shape_is_us(self, loc: str) -> None:
        assert _c(loc) == "us"

    @pytest.mark.parametrize("loc", ["IN - Indianapolis", "CA - San Francisco", "OR - Portland"])
    def test_a_two_letter_prefix_is_not_read_as_a_country(self, loc: str) -> None:
        # Deliberately unread: "IN"/"CA"/"OR" are Indiana/California/Oregon as often as
        # India/Canada/nothing, and "IT -"/"SE -" are department and compass prefixes.
        assert _c(loc) != "non_us"


class TestAlternationWordBoundary:
    """The `(?:...)` grouping inside `_alternation`.

    Without it, `|` binds looser than concatenation, so only the FIRST token keeps the
    lookbehind and only the LAST keeps the lookahead — every token between them matched as a
    bare substring. Region token "uk" therefore fired inside "Waukesha" and "West Milwaukee",
    and a US-only gate dropped 41 real GE HealthCare Wisconsin postings as non-US. It was
    intermittent: which token lands last follows `frozenset` iteration order, which varies with
    per-process hash randomisation, so the same store classified the same city differently from
    one run to the next.
    """

    @pytest.mark.parametrize(
        "catalog",
        [
            NON_US_REGIONS,
            NON_US_CITIES,
            NON_US_COUNTRIES,
            US_CITIES,
            US_STATE_NAMES,
            AMBIGUOUS_REGIONS,
            frozenset(US_MARKERS),
        ],
        ids=["regions", "non_us_cities", "countries", "us_cities", "states", "ambiguous",
             "markers"],
    )
    def test_no_token_matches_inside_a_longer_word(self, catalog: frozenset[str]) -> None:
        # Seed-independent: the ungrouped form leaves EVERY token but two unbounded, so whichever
        # ordering a process picks, some token in each catalog fails this.
        pattern = _alternation(catalog)
        for token in catalog:
            embedded = f"zz{token}zz"
            assert pattern.search(embedded) is None, (
                f"{token!r} matched inside {embedded!r} — the alternation is not grouped"
            )

    @pytest.mark.parametrize(
        "loc",
        [
            "Waukesha",          # GE HealthCare, Wisconsin — "uk" fired inside it
            "West Milwaukee",    # GE HealthCare, Wisconsin
            "Milwaukee",
            "Waukegan",
            "Keuka Park",
            "Dukes County",
            "Europa Center",     # "europe" must not fire on a partial
            "Asiatown",
        ],
    )
    def test_us_places_containing_a_foreign_token_are_never_dropped(self, loc: str) -> None:
        assert _c(loc) != "non_us"

    @pytest.mark.parametrize(
        "loc",
        [
            # The other direction: drops that the substring accident made correct BY LUCK now
            # need a real token, so fixing the boundary does not lose precision.
            "Milano",
            "Remote (Deutschland)",
            "Moscow Oblast, Russian Federation",
        ],
    )
    def test_spelled_out_foreign_forms_are_still_non_us(self, loc: str) -> None:
        assert _c(loc) == "non_us"
