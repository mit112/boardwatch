import pytest

from boardwatch.core.normalize import (
    canonical_location,
    canonical_locations,
    content_hash,
    normalize_body,
    normalize_company,
    normalize_title,
)


class TestNormalizeCompany:
    def test_strips_corporate_suffixes(self) -> None:
        assert normalize_company("Stripe, Inc.") == "stripe"
        assert normalize_company("Datadog, Inc.") == "datadog"
        assert normalize_company("Anduril Industries") == "anduril industries"
        assert normalize_company("Palantir Technologies") == "palantir"

    def test_suffix_requires_word_boundary(self) -> None:
        # 'co' is a suffix token, but 'Coinbase' must survive intact.
        assert normalize_company("Coinbase") == "coinbase"
        assert normalize_company("Tata & Co.") == "tata"

    def test_case_and_punctuation_folded(self) -> None:
        assert normalize_company("  EPIC Systems Corp ") == "epic systems"

    def test_caveat_us_centric_suffix_list(self) -> None:
        # Pinned ACCEPTED caveat: only US-style suffixes are stripped; GmbH survives.
        assert normalize_company("Celonis GmbH") == "celonis gmbh"

    def test_caveat_non_ascii_letters_are_dropped(self) -> None:
        # Pinned ACCEPTED caveat: normalization is ASCII-only.
        assert normalize_company("Café Münster Labs") == "caf mnster"


class TestNormalizeTitle:
    def test_punctuation_becomes_space(self) -> None:
        assert (
            normalize_title("Sr. Software Engineer (Backend) - Remote")
            == "sr software engineer backend remote"
        )

    def test_language_punctuation_no_longer_collapses(self) -> None:
        # This RETIRES a previously pinned ACCEPTED caveat ("'+' is stripped, so C++ titles
        # collide with C titles"), which asserted `normalize_title("C++ Developer") ==
        # "c developer"`. The caveat was accepted when a title collision was cosmetic. P6
        # slice 1 made normalize_title a component of `exact_quad` — the ONLY suppressing
        # identity kind — so the same collision now HIDES a real, different posting, and
        # `_verify_quad` re-runs this very function and agrees with the wrong answer. See
        # D-096, including the measurement showing the fix costs no recall on the live corpus.
        assert normalize_title("C++ Developer") == "c plus plus developer"
        assert normalize_title("C# Developer") == "c sharp developer"
        assert normalize_title("C Developer") == "c developer"

    def test_other_punctuation_is_still_stripped(self) -> None:
        # Only '+' and '#' are folded to words; everything else keeps collapsing, which is
        # what lets real duplicates that differ only in punctuation noise still match.
        assert normalize_title("Store-in-Store, Retail") == normalize_title("Store in Store Retail")

    def test_whitespace_collapsed(self) -> None:
        assert normalize_title("Software   Engineer\t II") == "software engineer ii"

    def test_non_ascii_title_survives(self) -> None:
        # Regression: an all-Korean title must not collapse to "" (which collided 64
        # Coupang postings into one empty-string bucket). Title normalization keeps
        # Unicode letters, unlike the ASCII-only company normalizer.
        assert normalize_title("소프트웨어 엔지니어") == "소프트웨어 엔지니어"

    def test_distinct_non_ascii_titles_do_not_collide(self) -> None:
        assert normalize_title("소프트웨어 엔지니어") != normalize_title("백엔드 개발자")

    def test_underscore_still_folds_to_space(self) -> None:
        # \W keeps underscore as a word char, so it is excluded explicitly to match
        # the previous ASCII behavior (underscores became spaces).
        assert normalize_title("Software_Engineer") == "software engineer"


class TestContentHash:
    def test_stable_across_whitespace_only_changes(self) -> None:
        a = "We build  systems.\nJoin us."
        b = "We build systems. Join us."
        assert content_hash(a) == content_hash(b)

    def test_stable_across_case_only_changes(self) -> None:
        assert content_hash("Build Systems") == content_hash("build systems")

    def test_changes_on_real_body_change(self) -> None:
        assert content_hash("5+ years of Go") != content_hash("2+ years of Go")

    def test_is_sha256_hex(self) -> None:
        digest = content_hash("anything")
        assert len(digest) == 64
        int(digest, 16)  # parses as hex

    def test_normalize_body_is_the_documented_input(self) -> None:
        assert normalize_body("  A\t B\nC  ") == "a b c"


class TestCanonicalLocation:
    """One place written two ways is one place — and nothing more than that.

    Both fold cases below are the two pairs measured in the live queue tree on 2026-08-28,
    where 46 of 70 redundant folders differed only in the location string. Every other test
    in this class is an over-merge guard: it asserts a pair that must NOT fold, because
    merging two different places would delete a real job from the owner's view.
    """

    def test_folds_a_state_name_onto_its_usps_abbreviation(self) -> None:
        # Ontic, "Associate Software Engineer - Full Stack": one req, two spellings.
        assert canonical_location("Austin, Texas, United States") == canonical_location("Austin, TX")
        assert canonical_location("Costa Mesa, California, United States") == "costa mesa, ca"
        assert canonical_location("Washington, District of Columbia") == "washington, dc"

    def test_folds_a_county_and_a_site_suffix_onto_the_city(self) -> None:
        # Lyft, "Software Engineer": "San Francisco County, CA" is San Francisco.
        assert canonical_location("San Francisco County, CA") == canonical_location(
            "San Francisco, CA, San Francisco Office"
        )
        # Anduril writes the building code after the state; two buildings in one city are
        # one city.
        assert canonical_location("Costa Mesa, CA (OC-00)") == "costa mesa, ca"
        assert canonical_location("Washington, DC (999)") == canonical_location(
            "Washington, DC (DC-01)"
        )

    def test_a_state_name_in_the_first_segment_is_left_alone(self) -> None:
        """"New York" and "Washington" are cities as often as they are states.

        Mapping every segment turns "New York, NY" into "ny, ny" and "Washington, DC" into
        "wa, dc" — which then collide with genuinely different places.
        """
        assert canonical_location("New York, NY") == "new york, ny"
        assert canonical_location("New York, New York") == "new york, ny"
        assert canonical_location("Washington, DC") == "washington, dc"
        assert canonical_location("Indiana, PA") == "indiana, pa"

    def test_a_trailing_country_is_dropped_only_beside_a_us_state(self) -> None:
        """Without the guard, "Remote, US" folds to "remote" and loses its only country."""
        assert canonical_location("Remote, US") == "remote, us"
        assert canonical_location("United States") == "united states"
        assert canonical_location("Santa Clara, CA, US") == "santa clara, ca"

    def test_a_parenthetical_is_dropped_only_from_a_state_segment(self) -> None:
        """"Remote (IND)" is the ISO alpha-3 signal the location gate reads (D-264)."""
        assert canonical_location("Remote (IND)") == "remote (ind)"
        assert canonical_location("San Jose (Costa Rica)") == "san jose (costa rica)"

    def test_county_is_stripped_only_when_a_us_state_follows(self) -> None:
        assert canonical_location("Orange County") == "orange county"
        assert canonical_location("County Cork, Ireland") == "county cork, ireland"

    @pytest.mark.parametrize(
        "raw",
        [
            "London, United Kingdom",
            "Toronto, ON, Canada",
            "Bengaluru, Karnataka, India",
            "Tokyo, Japan",
            "Paris, France",
            "Munich (DE)",
            "Remote Canada",
        ],
    )
    def test_a_non_us_location_passes_through_unchanged(self, raw: str) -> None:
        """Multi-tenancy: a user outside the US must not have their locations mangled.

        Out-of-catalog segments are left alone, never guessed. The one catalog ambiguity is
        "georgia", which is both a US state and a country — it is asserted separately.
        """
        assert canonical_location(raw) == normalize_body(raw)

    def test_georgia_the_country_folds_to_the_state_abbreviation(self) -> None:
        """The one known catalog ambiguity, asserted rather than left to be discovered.

        It cannot produce a wrong MERGE — nothing spells the country "GA" — and the two
        spellings already collided under the previous normalizer whenever the string was the
        bare word "Georgia". Fixing it would cost the real fold of "Atlanta, Georgia".
        """
        assert canonical_location("Tbilisi, Georgia") == "tbilisi, ga"
        assert canonical_location("Atlanta, Georgia") == "atlanta, ga"

    def test_is_idempotent(self) -> None:
        for raw in ["San Francisco County, CA", "Austin, Texas, United States", "London"]:
            once = canonical_location(raw)
            assert canonical_location(once) == once


class TestCanonicalLocations:
    def test_a_place_named_twice_in_one_list_is_one_place(self) -> None:
        # Brex publishes the primary city in long form beside the same city in short form.
        assert canonical_locations(["San Francisco, California, United States", "San Francisco, CA"]) == [
            "san francisco, ca"
        ]

    def test_an_office_alias_is_dropped_when_its_city_is_already_listed(self) -> None:
        assert canonical_locations(["San Francisco, CA", "San Francisco Office"]) == [
            "san francisco, ca"
        ]

    def test_an_office_alias_naming_another_city_is_kept(self) -> None:
        assert canonical_locations(["Seattle, WA", "San Francisco Office"]) == [
            "san francisco office",
            "seattle, wa",
        ]

    def test_an_office_alias_alone_is_never_dropped(self) -> None:
        """Dropping it would invent an empty location out of the only evidence there is."""
        assert canonical_locations(["San Francisco Office"]) == ["san francisco office"]

    def test_a_strict_superset_is_not_merged(self) -> None:
        """Twitch posts one req as Seattle+SF and another as SF only (out of scope).

        Merging a superset onto its subset is a policy call, not normalization: it hides a
        posting that names a city the other one does not.
        """
        assert canonical_locations(["Seattle, WA", "San Francisco, CA"]) != canonical_locations(
            ["San Francisco, CA"]
        )

    def test_two_different_cities_are_not_merged(self) -> None:
        """PayPal posts "Software Engineer" in San Jose, Austin, Scottsdale and New York."""
        assert canonical_locations(["San Jose, CA"]) != canonical_locations(["Austin, TX"])

    def test_us_and_canada_are_not_merged(self) -> None:
        """Affirm posts "Remote US" beside "Remote Canada" — merging is actively wrong."""
        assert canonical_locations(["Remote US"]) != canonical_locations(["Remote Canada"])
