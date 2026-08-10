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
