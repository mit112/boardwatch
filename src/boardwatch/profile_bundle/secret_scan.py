"""Versioned, fail-closed secret detection over evidence captures (design §12.2).

A revision's manifest records the exact ruleset version it was scanned and passed with, so the
same bytes always get the same structural verdict regardless of what a later build additionally
knows how to detect. `BUILTIN_RULESETS` is the closed set of catalogs this build retains; an
unavailable recorded version raises `UnsupportedSecretRulesetError` rather than silently reporting
a clean scan, because "we cannot check" and "we checked and found nothing" must never look alike.

V1 deliberately ships no entropy heuristic: low-confidence token guessing would make structural
validation noisy and non-reproducible (design §12.2), so a bare high-entropy string that matches
no named rule is not a hit.

`SecretHit` carries only `rule_id` and a UTF-8 byte range. Nothing in this module logs, returns,
or embeds matched secret text anywhere — not in an exception message, not in a diagnostic detail —
because a scanner whose own findings leak the credential it found has not contained anything.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from boardwatch.profile_bundle.errors import ProfileBundleError, UnsupportedSecretRulesetError

# `CaptureMediaType` and the rule row shapes are owned by the models package, which is where they
# constrain authored fields, and are re-exported here so a caller that only needs the scanner needs
# only this module. The direction matters: this module depends on the record shapes, never the
# reverse, so the models package stays importable without the scanner.
from boardwatch.profile_bundle.models.evidence import CaptureMediaType
from boardwatch.profile_bundle.models.policy import SecretRule, SecretRuleset, SecretScanFlag

__all__ = [
    "BUILTIN_RULESETS",
    "CURRENT_RULESET_VERSION",
    "SUPPORTED_RULESET_VERSIONS",
    "CaptureMediaType",
    "InvalidUtf8CaptureError",
    "SecretHit",
    "SecretRule",
    "SecretRuleset",
    "SecretScanFlag",
    "builtin_ruleset",
    "ruleset_matches_builtin",
    "scan_capture",
]


_FLAG_TO_RE: Final[Mapping[SecretScanFlag, re.RegexFlag]] = {
    SecretScanFlag.IGNORE_CASE: re.IGNORECASE,
    SecretScanFlag.MULTILINE: re.MULTILINE,
}


@dataclass(frozen=True)
class SecretHit:
    """One match. Byte range only — never the matched text (see module docstring)."""

    rule_id: str
    start: int
    end: int


class InvalidUtf8CaptureError(ProfileBundleError):
    """A capture's raw bytes are not valid UTF-8, so no rule could be evaluated against it.

    Rules are authored against decoded text (design §12.2: "applied to the decoded UTF-8 text of
    every allowed inline or blob capture"), so a capture that cannot decode cannot be scanned at
    all. Reporting a clean scan in that case would be indistinguishable from an actual clean scan,
    which is exactly the ambiguity `UnsupportedSecretRulesetError` also exists to avoid.
    """


#: The exact eight v1 rows, transcribed verbatim from design §12.2 in the design's own order.
#: Patterns use `|-` chomping in the design's YAML, i.e. no trailing newline; the Python string
#: literals below already have none, so no further stripping is needed.
_V1_RULES: Final[tuple[SecretRule, ...]] = (
    SecretRule(
        rule_id="private-key-block",
        pattern=(
            r"-----BEGIN[ \t]+(?:OPENSSH[ \t]+|RSA[ \t]+|EC[ \t]+|DSA[ \t]+|PGP[ \t]+)?"
            r"PRIVATE[ \t]+KEY(?:[ \t]+BLOCK)?-----"
        ),
        flags=(),
    ),
    SecretRule(
        rule_id="authorization-header",
        pattern=(
            r"^[ \t]*authorization[ \t]*:[ \t]*(?:bearer|basic)[ \t]+"
            r"[A-Za-z0-9._~+/=-]{8,}[ \t]*$"
        ),
        flags=(SecretScanFlag.IGNORE_CASE, SecretScanFlag.MULTILINE),
    ),
    SecretRule(
        rule_id="cookie-header",
        pattern=r"^[ \t]*(?:cookie|set-cookie)[ \t]*:[^\r\n]{8,}$",
        flags=(SecretScanFlag.IGNORE_CASE, SecretScanFlag.MULTILINE),
    ),
    SecretRule(
        rule_id="credential-url",
        pattern=r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{4,}@",
        flags=(SecretScanFlag.IGNORE_CASE,),
    ),
    SecretRule(
        rule_id="generic-secret-assignment",
        # Split around the `["']?` literal: a raw string cannot hold both quote characters
        # under one delimiter without an escaping backslash that raw strings do not strip, so
        # the bracket group is built from two adjacent literals, each safe under its own quote.
        pattern=(
            r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|"
            r"private[_-]?key)\b[ \t]{0,8}(?::|=)[ \t]{0,8}"
            r'["'
            r"']?"
            r"[A-Za-z0-9._~+/=-]{8,}"
        ),
        flags=(SecretScanFlag.IGNORE_CASE,),
    ),
    SecretRule(
        rule_id="aws-access-key-id",
        pattern=r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        flags=(),
    ),
    SecretRule(
        rule_id="github-token",
        pattern=r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{82,255})\b",
        flags=(),
    ),
    SecretRule(
        rule_id="slack-token",
        pattern=r"\bxox[baprs]-[A-Za-z0-9-]{10,255}\b",
        flags=(),
    ),
)

CURRENT_RULESET_VERSION: Final = 1

#: The closed set of catalogs this build retains. A caller records the version it scanned with
#: and this must be findable forever the revision claims it: adding a rule requires a new version,
#: never editing this one (design §12.2's "cannot remove, add, reorder, rename, or weaken").
BUILTIN_RULESETS: Final[Mapping[int, SecretRuleset]] = {
    1: SecretRuleset(ruleset_version=CURRENT_RULESET_VERSION, rules=_V1_RULES),
}

SUPPORTED_RULESET_VERSIONS: Final[frozenset[int]] = frozenset(BUILTIN_RULESETS)


def _compiled_flags(flags: tuple[SecretScanFlag, ...]) -> int:
    value = 0
    for flag in flags:
        value |= _FLAG_TO_RE[flag]
    return value


def _compile_ruleset(ruleset: SecretRuleset) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Compile once per catalog. Called only at import time, over `BUILTIN_RULESETS`."""
    return tuple(
        (rule.rule_id, re.compile(rule.pattern, _compiled_flags(rule.flags)))
        for rule in ruleset.rules
    )


#: Cached per ruleset version so `scan_capture` never recompiles a pattern per call.
_COMPILED_BUILTIN: Final[Mapping[int, tuple[tuple[str, re.Pattern[str]], ...]]] = {
    version: _compile_ruleset(ruleset) for version, ruleset in BUILTIN_RULESETS.items()
}


def builtin_ruleset(version: int) -> SecretRuleset:
    """The retained catalog for `version`.

    Raises `UnsupportedSecretRulesetError` for anything not in `SUPPORTED_RULESET_VERSIONS`, so a
    caller can turn an unavailable recorded version into exit 3 rather than reporting a clean scan
    it never actually performed.
    """
    try:
        return BUILTIN_RULESETS[version]
    except KeyError:
        raise UnsupportedSecretRulesetError(version, sorted(SUPPORTED_RULESET_VERSIONS)) from None


def scan_capture(
    raw: bytes,
    *,
    media_type: CaptureMediaType,
    ruleset_version: int,
) -> tuple[SecretHit, ...]:
    """Scan one capture's decoded UTF-8 text against the named ruleset version.

    `media_type` is accepted because every caller has one to pass and a future capture format
    might one day need binary-aware handling, but all four allowed media types are UTF-8 text, so
    today it plays no part in rule selection — the parameter exists for the call-site contract,
    not because this function branches on it.
    """
    del media_type  # not used for rule selection; see docstring
    builtin_ruleset(ruleset_version)  # raises UnsupportedSecretRulesetError before any decoding
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidUtf8CaptureError(f"capture is not valid UTF-8 ({exc.reason})") from exc

    hits: list[SecretHit] = []
    for rule_id, pattern in _COMPILED_BUILTIN[ruleset_version]:
        for match in pattern.finditer(text):
            # Offsets are UTF-8 BYTE offsets, not character offsets: a diagnostic's byte range
            # must address the same bytes the manifest hashes, and those are never the same as
            # Python string indices once any non-ASCII text precedes the match.
            start = len(text[: match.start()].encode("utf-8"))
            end = len(text[: match.end()].encode("utf-8"))
            hits.append(SecretHit(rule_id=rule_id, start=start, end=end))

    hits.sort(key=lambda hit: (hit.start, hit.rule_id))
    return tuple(hits)


def _canonical_row(rule: SecretRule) -> tuple[str, str, frozenset[SecretScanFlag]]:
    """`flags` as a set for comparison: authoring order within one row carries no meaning, only
    which flags are present. Row identity and position in the sequence still matter — see
    `ruleset_matches_builtin`, which zips by index rather than comparing as sets of rows.
    """
    return (rule.rule_id, rule.pattern, frozenset(rule.flags))


def ruleset_matches_builtin(recorded: SecretRuleset) -> bool:
    """True only when `recorded` is canonically identical to the retained builtin catalog.

    Equal length and index-wise row equality together reject every kind of divergence design
    §12.2 names: a removed or added rule changes the length; a reordered, renamed, or weakened
    rule changes the row at some index even though the length matches.
    """
    builtin = BUILTIN_RULESETS.get(recorded.ruleset_version)
    if builtin is None:
        return False
    if len(recorded.rules) != len(builtin.rules):
        return False
    return all(
        _canonical_row(r) == _canonical_row(b)
        for r, b in zip(recorded.rules, builtin.rules, strict=True)
    )
