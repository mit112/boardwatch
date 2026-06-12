from boardwatch.core.normalize import (
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

    def test_caveat_cpp_collapses_to_c(self) -> None:
        # Pinned ACCEPTED caveat: '+' is stripped, so C++ titles collide with C titles.
        assert normalize_title("C++ Developer") == "c developer"

    def test_whitespace_collapsed(self) -> None:
        assert normalize_title("Software   Engineer\t II") == "software engineer ii"


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
