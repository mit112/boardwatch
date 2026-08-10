"""Versioned secret detection over evidence captures (design §12.2).

The catalog is pinned verbatim rather than trusted to whatever the module currently ships: every
one of the eight v1 rules gets a positive fixture (must match) and a near-miss negative fixture
(structurally close but must not match), so a future edit that quietly widens or narrows a rule
is caught here rather than only in production. No fixture below is a real-looking credential —
every token is either a repeated filler character or an obviously synthetic literal.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardwatch.profile_bundle.errors import UnsupportedSecretRulesetError
from boardwatch.profile_bundle.secret_scan import (
    BUILTIN_RULESETS,
    CURRENT_RULESET_VERSION,
    SUPPORTED_RULESET_VERSIONS,
    CaptureMediaType,
    InvalidUtf8CaptureError,
    SecretHit,
    SecretRule,
    SecretRuleset,
    SecretScanFlag,
    builtin_ruleset,
    ruleset_matches_builtin,
    scan_capture,
)

_MEDIA = CaptureMediaType.TEXT_PLAIN

# (rule_id, positive fixture that must match, near-miss fixture that must not match)
_RULE_FIXTURES: tuple[tuple[str, str, str], ...] = (
    (
        "private-key-block",
        "-----BEGIN RSA PRIVATE KEY-----\nfiller\n-----END RSA PRIVATE KEY-----\n",
        # No `ignore_case` flag: lowercase must not match, only the exact literal casing.
        "-----begin rsa private key-----\n",
    ),
    (
        "authorization-header",
        "context line\nAuthorization: Bearer AAAAAAAA\nmore context\n",
        # Token is 4 chars; the rule requires 8+.
        "context line\nAuthorization: Bearer AAAA\nmore context\n",
    ),
    (
        "cookie-header",
        "context line\nCookie: AAAAAAAA\nmore context\n",
        # Only 3 chars after the colon; the rule requires 8+.
        "context line\nCookie: AAA\nmore context\n",
    ),
    (
        "credential-url",
        "see https://user:AAAAAAAA@example.com/path for details",
        # Password segment is 3 chars; the rule requires 4+.
        "see https://user:AAA@example.com/path for details",
    ),
    (
        "generic-secret-assignment",
        "config: api_key: AAAAAAAA is set",
        # Token is 5 chars; the rule requires 8+.
        "config: api_key: AAAAA is set",
    ),
    (
        "aws-access-key-id",
        "found AKIA" + "A" * 16 + " in the log",
        # Only 15 chars after AKIA; the rule requires exactly 16.
        "found AKIA" + "A" * 15 + " in the log",
    ),
    (
        "github-token",
        "found ghp_" + "A" * 36 + " in the log",
        # Only 35 chars after ghp_; the rule requires 36+.
        "found ghp_" + "A" * 35 + " in the log",
    ),
    (
        "slack-token",
        "found xoxb-" + "A" * 10 + " in the log",
        # Only 9 chars after xoxb-; the rule requires 10+.
        "found xoxb-" + "A" * 9 + " in the log",
    ),
)

_ALL_V1_RULE_IDS = tuple(rule_id for rule_id, _, _ in _RULE_FIXTURES)


def _hit_rule_ids(raw: bytes) -> set[str]:
    hits = scan_capture(raw, media_type=_MEDIA, ruleset_version=CURRENT_RULESET_VERSION)
    return {hit.rule_id for hit in hits}


@pytest.mark.parametrize("rule_id,positive,negative", _RULE_FIXTURES)
def test_each_v1_rule_matches_its_positive_fixture(
    rule_id: str, positive: str, negative: str
) -> None:
    assert rule_id in _hit_rule_ids(positive.encode("utf-8"))


@pytest.mark.parametrize("rule_id,positive,negative", _RULE_FIXTURES)
def test_each_v1_rule_rejects_its_near_miss_fixture(
    rule_id: str, positive: str, negative: str
) -> None:
    assert rule_id not in _hit_rule_ids(negative.encode("utf-8"))


def test_v1_catalog_is_exactly_the_eight_named_rules_in_order() -> None:
    builtin = builtin_ruleset(1)
    assert tuple(rule.rule_id for rule in builtin.rules) == (
        "private-key-block",
        "authorization-header",
        "cookie-header",
        "credential-url",
        "generic-secret-assignment",
        "aws-access-key-id",
        "github-token",
        "slack-token",
    )
    assert set(_ALL_V1_RULE_IDS) == set(rule.rule_id for rule in builtin.rules)


def test_v1_flags_match_the_design_exactly() -> None:
    expected_flags = {
        "private-key-block": (),
        "authorization-header": (SecretScanFlag.IGNORE_CASE, SecretScanFlag.MULTILINE),
        "cookie-header": (SecretScanFlag.IGNORE_CASE, SecretScanFlag.MULTILINE),
        "credential-url": (SecretScanFlag.IGNORE_CASE,),
        "generic-secret-assignment": (SecretScanFlag.IGNORE_CASE,),
        "aws-access-key-id": (),
        "github-token": (),
        "slack-token": (),
    }
    for rule in builtin_ruleset(1).rules:
        assert rule.flags == expected_flags[rule.rule_id]


def test_capture_media_type_has_exactly_the_four_allowed_members() -> None:
    assert {member.value for member in CaptureMediaType} == {
        "text/plain",
        "text/markdown",
        "application/json",
        "text/csv",
    }


def test_secret_scan_flag_closure_rejects_anything_else() -> None:
    SecretScanFlag("ignore_case")
    SecretScanFlag("multiline")
    with pytest.raises(ValueError):
        SecretScanFlag("case_insensitive")
    with pytest.raises(ValidationError):
        SecretRule(rule_id="x", pattern="abc", flags=("case_insensitive",))  # type: ignore[arg-type]


def test_secret_rule_and_ruleset_forbid_extra_fields_and_are_frozen() -> None:
    rule = SecretRule(rule_id="x", pattern="abc", flags=())
    with pytest.raises(ValidationError):
        SecretRule(rule_id="x", pattern="abc", flags=(), unexpected="nope")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        rule.rule_id = "y"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        SecretRuleset(ruleset_version=1, rules=(), unexpected="nope")  # type: ignore[call-arg]


def test_secret_rule_rejects_duplicate_flags() -> None:
    with pytest.raises(ValidationError):
        SecretRule(
            rule_id="x",
            pattern="abc",
            flags=(SecretScanFlag.IGNORE_CASE, SecretScanFlag.IGNORE_CASE),
        )


def test_secret_rule_rejects_non_kebab_rule_id() -> None:
    with pytest.raises(ValidationError):
        SecretRule(rule_id="Not_Kebab", pattern="abc", flags=())


def test_secret_rule_rejects_uncompilable_pattern() -> None:
    with pytest.raises(ValidationError):
        SecretRule(rule_id="x", pattern="(unterminated", flags=())


def test_ruleset_matches_builtin_true_for_the_real_v1_catalog() -> None:
    assert ruleset_matches_builtin(BUILTIN_RULESETS[1]) is True


def test_ruleset_matches_builtin_false_when_a_rule_is_removed() -> None:
    builtin = BUILTIN_RULESETS[1]
    shortened = SecretRuleset(ruleset_version=1, rules=builtin.rules[:-1])
    assert ruleset_matches_builtin(shortened) is False


def test_ruleset_matches_builtin_false_when_a_rule_is_added() -> None:
    builtin = BUILTIN_RULESETS[1]
    extra_rule = SecretRule(rule_id="extra-rule", pattern="abc", flags=())
    lengthened = SecretRuleset(ruleset_version=1, rules=(*builtin.rules, extra_rule))
    assert ruleset_matches_builtin(lengthened) is False


def test_ruleset_matches_builtin_false_when_two_rows_are_reordered() -> None:
    builtin = BUILTIN_RULESETS[1]
    rows = list(builtin.rules)
    rows[0], rows[1] = rows[1], rows[0]
    reordered = SecretRuleset(ruleset_version=1, rules=tuple(rows))
    assert ruleset_matches_builtin(reordered) is False


def test_ruleset_matches_builtin_false_when_a_rule_is_renamed() -> None:
    builtin = BUILTIN_RULESETS[1]
    rows = list(builtin.rules)
    renamed = rows[0].model_copy(update={"rule_id": "renamed-rule"})
    renamed_rows = SecretRuleset(ruleset_version=1, rules=(renamed, *rows[1:]))
    assert ruleset_matches_builtin(renamed_rows) is False


def test_ruleset_matches_builtin_false_when_a_pattern_is_weakened() -> None:
    builtin = BUILTIN_RULESETS[1]
    rows = list(builtin.rules)
    aws_rule = next(r for r in rows if r.rule_id == "aws-access-key-id")
    weakened = aws_rule.model_copy(update={"pattern": r"\b(?:AKIA|ASIA)[A-Z0-9]{4}\b"})
    weakened_rows = tuple(weakened if r.rule_id == "aws-access-key-id" else r for r in rows)
    weakened_ruleset = SecretRuleset(ruleset_version=1, rules=weakened_rows)
    assert ruleset_matches_builtin(weakened_ruleset) is False


def test_ruleset_matches_builtin_false_when_a_flag_is_dropped() -> None:
    builtin = BUILTIN_RULESETS[1]
    rows = list(builtin.rules)
    auth_rule = next(r for r in rows if r.rule_id == "authorization-header")
    weakened = auth_rule.model_copy(update={"flags": (SecretScanFlag.MULTILINE,)})
    weakened_rows = tuple(
        weakened if r.rule_id == "authorization-header" else r for r in rows
    )
    weakened_ruleset = SecretRuleset(ruleset_version=1, rules=weakened_rows)
    assert ruleset_matches_builtin(weakened_ruleset) is False


def test_ruleset_matches_builtin_false_for_unsupported_version() -> None:
    unknown = SecretRuleset(ruleset_version=999, rules=())
    assert ruleset_matches_builtin(unknown) is False


def test_unknown_ruleset_version_raises_with_found_and_supported() -> None:
    with pytest.raises(UnsupportedSecretRulesetError) as excinfo:
        builtin_ruleset(999)
    assert excinfo.value.found == 999
    assert excinfo.value.supported == tuple(sorted(SUPPORTED_RULESET_VERSIONS))


def test_scan_capture_raises_unsupported_ruleset_version_not_a_clean_scan() -> None:
    with pytest.raises(UnsupportedSecretRulesetError) as excinfo:
        scan_capture(b"nothing secret here", media_type=_MEDIA, ruleset_version=999)
    assert excinfo.value.found == 999
    assert excinfo.value.supported == tuple(sorted(SUPPORTED_RULESET_VERSIONS))


def test_scan_capture_matches_across_non_ascii_surrounding_text() -> None:
    raw = ("café notes: AKIA" + "A" * 16 + " café notes").encode("utf-8")
    hits = scan_capture(raw, media_type=_MEDIA, ruleset_version=CURRENT_RULESET_VERSION)
    assert any(hit.rule_id == "aws-access-key-id" for hit in hits)


def test_scan_capture_rejects_invalid_utf8_rather_than_reporting_no_hits() -> None:
    with pytest.raises(InvalidUtf8CaptureError):
        scan_capture(b"\xff\xfe not valid utf-8", media_type=_MEDIA, ruleset_version=1)


def test_v1_has_no_entropy_heuristic() -> None:
    # A high-entropy bare token that matches none of the eight named rules must produce zero
    # hits: v1 deliberately does not try to guess at "this looks random enough to be a secret".
    high_entropy_token = "Qx7ZmP3vN9kLdRt2WsYb8Jf4Hc6Vu1EoIaGnMq5T"
    assert len(high_entropy_token) == 40
    hits = scan_capture(
        high_entropy_token.encode("utf-8"),
        media_type=_MEDIA,
        ruleset_version=CURRENT_RULESET_VERSION,
    )
    assert hits == ()


def test_byte_offsets_are_utf8_byte_offsets_not_character_indices() -> None:
    prefix = "é "  # 1 char '\xe9' (2 UTF-8 bytes) + 1 ASCII space (1 byte) = 3 bytes, 2 chars.
    match_text = "AKIA" + "A" * 16
    raw = (prefix + match_text).encode("utf-8")
    hits = scan_capture(raw, media_type=_MEDIA, ruleset_version=CURRENT_RULESET_VERSION)
    aws_hits = [hit for hit in hits if hit.rule_id == "aws-access-key-id"]
    assert len(aws_hits) == 1
    expected_start = len(prefix.encode("utf-8"))
    assert expected_start == 3
    assert len(prefix) == 2  # sanity: the character index would have been wrong here
    assert aws_hits[0].start == expected_start
    assert aws_hits[0].end == expected_start + len(match_text.encode("utf-8"))


def test_scan_capture_returns_stable_sorted_order_for_overlapping_inputs() -> None:
    # Two different rule families both fire, and repeated calls must agree on the same order.
    text = (
        "Authorization: Bearer AAAAAAAA\n"
        "found ghp_" + "A" * 36 + " here\n"
        "Cookie: AAAAAAAA\n"
    )
    raw = text.encode("utf-8")
    first = scan_capture(raw, media_type=_MEDIA, ruleset_version=CURRENT_RULESET_VERSION)
    second = scan_capture(raw, media_type=_MEDIA, ruleset_version=CURRENT_RULESET_VERSION)
    assert first == second
    assert len(first) >= 3
    starts = [hit.start for hit in first]
    assert starts == sorted(starts)


def test_scan_capture_hits_are_secret_hit_instances_with_no_matched_text_field() -> None:
    raw = ("found AKIA" + "A" * 16).encode("utf-8")
    hits = scan_capture(raw, media_type=_MEDIA, ruleset_version=CURRENT_RULESET_VERSION)
    assert len(hits) == 1
    hit = hits[0]
    assert isinstance(hit, SecretHit)
    assert set(hit.__dataclass_fields__) == {"rule_id", "start", "end"}
