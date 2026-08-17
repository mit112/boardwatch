"""The write side of R13-R15: re-recording pins, and draining an overdue deadline.

The hazard these tests exist for is a rewrite that silently changes NOTHING: it would report
success, leave a stale pin behind, and the gate would keep passing against a fixture nobody
re-reviewed. So every anchor that goes missing must raise, never fall through.
"""

from __future__ import annotations

from datetime import date

import pytest

from tools.fixture_refresh.__main__ import main
from tools.fixture_refresh.rewrite import RewriteError, extend_deadline, record_pins

SOURCE = '''FIXTURE_PROVENANCE: dict[str, FixtureProvenance] = {
    "greenhouse": FixtureProvenance(
        captured=date(2026, 6, 12),
        review_by=date(2026, 9, 10),
        readme_pin="sha256:aaaa",
    ),
    "lever": FixtureProvenance(
        captured=date(2026, 6, 13),
        review_by=date(2026, 9, 11),
        readme_pin="sha256:bbbb",
    ),
}

CORPUS_PIN = "sha256:cccc"

CORPUS_ROWS = 987
'''


def test_record_pins_rewrites_every_measured_value() -> None:
    out = record_pins(
        SOURCE, readmes={"greenhouse": "1111", "lever": "2222"}, corpus_pin="3333", rows=990
    )
    assert 'readme_pin="sha256:1111"' in out
    assert 'readme_pin="sha256:2222"' in out
    assert 'CORPUS_PIN = "sha256:3333"' in out
    assert "CORPUS_ROWS = 990" in out
    assert "aaaa" not in out and "bbbb" not in out and "cccc" not in out


def test_record_pins_leaves_untouched_source_byte_identical() -> None:
    """Re-recording values that already match must be a true no-op, not a reformat."""
    same = record_pins(
        SOURCE, readmes={"greenhouse": "aaaa", "lever": "bbbb"}, corpus_pin="cccc", rows=987
    )
    assert same == SOURCE


def test_record_pins_raises_rather_than_no_opping_on_a_missing_provider() -> None:
    with pytest.raises(RewriteError, match="no FIXTURE_PROVENANCE entry for 'ashby'"):
        record_pins(SOURCE, readmes={"ashby": "1111"}, corpus_pin="3333", rows=987)


def test_record_pins_raises_when_the_corpus_anchor_is_gone() -> None:
    stripped = SOURCE.replace('CORPUS_PIN = "sha256:cccc"', "")
    with pytest.raises(RewriteError, match="CORPUS_PIN"):
        record_pins(stripped, readmes={}, corpus_pin="3333", rows=987)


def test_extend_appends_the_first_rollover_and_moves_the_deadline() -> None:
    out = extend_deadline(
        SOURCE,
        provider="greenhouse",
        on=date(2026, 9, 11),
        reason="no network this week",
        new_review_by=date(2026, 12, 10),
    )
    assert "review_by=date(2026, 12, 10)," in out
    assert 'Extension(on=date(2026, 9, 11), reason="no network this week"),' in out
    # Only greenhouse moved.
    assert "review_by=date(2026, 9, 11)," in out


def test_a_second_rollover_is_appended_not_overwritten() -> None:
    """The COUNT of rollovers is the signal: a fourth extension is a different fact."""
    once = extend_deadline(
        SOURCE,
        provider="greenhouse",
        on=date(2026, 9, 11),
        reason="first",
        new_review_by=date(2026, 10, 11),
    )
    twice = extend_deadline(
        once,
        provider="greenhouse",
        on=date(2026, 10, 12),
        reason="second",
        new_review_by=date(2026, 11, 11),
    )
    assert twice.count("Extension(on=date(") == 2
    assert 'reason="first"' in twice and 'reason="second"' in twice


def test_a_blank_reason_is_refused() -> None:
    with pytest.raises(RewriteError, match="non-empty reason"):
        extend_deadline(
            SOURCE,
            provider="greenhouse",
            on=date(2026, 9, 11),
            reason="   ",
            new_review_by=date(2026, 12, 10),
        )


@pytest.mark.parametrize("reason", ['broke", captured=date(1999, 1, 1), x="', "back\\slash"])
def test_a_reason_that_would_escape_its_string_literal_is_refused(reason: str) -> None:
    """The reason is interpolated into generated source, so a quote is a code-injection hole."""
    with pytest.raises(RewriteError, match="quote or a backslash"):
        extend_deadline(
            SOURCE,
            provider="greenhouse",
            on=date(2026, 9, 11),
            reason=reason,
            new_review_by=date(2026, 12, 10),
        )


def test_extend_raises_on_an_unknown_provider() -> None:
    with pytest.raises(RewriteError, match="no FIXTURE_PROVENANCE entry for 'nope'"):
        extend_deadline(
            SOURCE,
            provider="nope",
            on=date(2026, 9, 11),
            reason="x",
            new_review_by=date(2026, 12, 10),
        )


# ------------------------------------------------------------------------------ the CLI


def test_check_mode_passes_against_the_real_tree() -> None:
    assert main(["--check"]) == 0


def test_extend_without_a_reason_is_refused_before_anything_is_written() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--extend", "greenhouse"])
    assert exc.value.code == 2


def test_extend_and_record_together_are_refused() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--record", "--extend", "greenhouse", "--reason", "x"])
    assert exc.value.code == 2


def test_a_non_positive_extension_is_refused() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--extend", "greenhouse", "--days", "0", "--reason", "x"])
    assert exc.value.code == 2


def test_an_unknown_provider_is_refused_by_the_cli() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--extend", "nope", "--reason", "x"])
    assert exc.value.code == 2
