from __future__ import annotations

from boardwatch.tailor.tokens import has_whole_token, toks, whole_token_sub


def test_toks_splits_words_and_punctuation() -> None:
    assert toks("Shipped JS, at scale!") == ["Shipped", "JS", ",", "at", "scale", "!"]


def test_has_whole_token_true_and_false() -> None:
    assert has_whole_token("Shipped JS at scale", "JS") is True
    assert has_whole_token("Parsed JSON quickly", "JS") is False


def test_whole_token_sub_replaces_case_insensitively() -> None:
    assert whole_token_sub("Shipped js at scale", "JS", "JavaScript") == "Shipped JavaScript at scale"
    assert whole_token_sub("Parsed JSON quickly", "JS", "JavaScript") is None
