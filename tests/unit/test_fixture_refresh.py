"""The write side of R13-R15: re-recording pins, and draining an overdue deadline.

The hazard these tests exist for is a rewrite that silently changes NOTHING: it would report
success, leave a stale pin behind, and the gate would keep passing against a fixture nobody
re-reviewed. So every anchor that goes missing must raise, never fall through.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from tools.fixture_refresh.__main__ import main
from tools.fixture_refresh.rewrite import (
    PROVENANCE_MODULE,
    RewriteError,
    extend_deadline,
    record_pins,
)
from tools.generalization.fixtures import CORPUS_PIN, FIXTURE_PROVENANCE

REPO_ROOT = Path(__file__).resolve().parents[2]

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
    out = record_pins(SOURCE, readmes={"greenhouse": "1111", "lever": "2222"}, corpus_pin="3333")
    assert 'readme_pin="sha256:1111"' in out
    assert 'readme_pin="sha256:2222"' in out
    assert 'CORPUS_PIN = "sha256:3333"' in out
    assert "aaaa" not in out and "bbbb" not in out and "cccc" not in out


def test_record_pins_never_touches_the_corpus_row_count() -> None:
    """CORPUS_ROWS is the corpus's second path, and a second path this tool can rewrite from
    the same read that produced the pin is not a second path at all.

    An earlier version wrote both, and a corpus truncated to 500 rows then satisfied the pin
    AND the count in one `--record`. The row count stays a human-reviewed constant.
    """
    out = record_pins(SOURCE, readmes={"greenhouse": "1111", "lever": "2222"}, corpus_pin="3333")
    assert "CORPUS_ROWS = 987" in out


def test_record_pins_leaves_untouched_source_byte_identical() -> None:
    """Re-recording values that already match must be a true no-op, not a reformat."""
    same = record_pins(SOURCE, readmes={"greenhouse": "aaaa", "lever": "bbbb"}, corpus_pin="cccc")
    assert same == SOURCE


def test_the_anchors_match_the_REAL_provenance_module_not_just_the_synthetic_one() -> None:
    """Binds the rewriter's five anchors to the file it actually edits.

    Every other test here runs against `SOURCE`, a constant shaped by the same author to match
    the anchors -- so it agrees with itself. If `fixtures.py` is ever reflowed, `record_pins`
    silently stops matching and the rest of this suite stays green, which is exactly the
    "changes nothing and reports success" failure the module docstring says it prevents.
    """
    path = REPO_ROOT / PROVENANCE_MODULE
    text = path.read_text(encoding="utf-8")
    current = {
        provider: record.readme_pin.removeprefix("sha256:")
        for provider, record in FIXTURE_PROVENANCE.items()
    }
    rewritten = record_pins(text, readmes=current, corpus_pin=CORPUS_PIN.removeprefix("sha256:"))
    assert rewritten == text, "record_pins no longer round-trips the real module unchanged"


def test_record_pins_raises_rather_than_no_opping_on_a_missing_provider() -> None:
    with pytest.raises(RewriteError, match="no FIXTURE_PROVENANCE entry for 'ashby'"):
        record_pins(SOURCE, readmes={"ashby": "1111"}, corpus_pin="3333")


def test_record_pins_raises_when_the_corpus_anchor_is_gone() -> None:
    stripped = SOURCE.replace('CORPUS_PIN = "sha256:cccc"', "")
    with pytest.raises(RewriteError, match="CORPUS_PIN"):
        record_pins(stripped, readmes={}, corpus_pin="3333")


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


@pytest.mark.parametrize(
    "reason",
    [
        'broke", captured=date(1999, 1, 1), x="',
        "back\\slash",
        "line one\nline two",
        "tab\there",
    ],
)
def test_a_reason_that_would_escape_its_string_literal_is_refused(reason: str) -> None:
    """The reason is interpolated into generated source, so a quote is a code-injection hole.

    A newline is the subtle one: it survives `.strip()`, lands mid-literal, and produces source
    that does not parse. `_write` catches that before touching the file, but as a traceback
    rather than a diagnosis, so it is refused here instead.
    """
    with pytest.raises(RewriteError, match="quote, a backslash, or a non-printable"):
        extend_deadline(
            SOURCE,
            provider="greenhouse",
            on=date(2026, 9, 11),
            reason=reason,
            new_review_by=date(2026, 12, 10),
        )


def test_an_over_long_reason_is_refused_because_it_would_break_the_lint_gate() -> None:
    """The drain must be able to restore green, and ruff enforces line-length 100 over tools/.

    A perfectly reasonable 55-character reason emitted a 111-character line, so running the
    documented remedy turned `make check` red on E501 inside the module the gate imports.
    """
    reason = "no network access while travelling in Europe for the whole of this month"
    with pytest.raises(RewriteError, match="fit on one line"):
        extend_deadline(
            SOURCE,
            provider="greenhouse",
            on=date(2026, 9, 11),
            reason=reason,
            new_review_by=date(2026, 12, 10),
        )


def test_an_accepted_reason_emits_a_line_within_the_lint_limit() -> None:
    """The guard's own boundary: whatever it accepts must actually pass ruff."""
    out = extend_deadline(
        SOURCE,
        provider="greenhouse",
        on=date(2026, 12, 11),
        reason="x" * 44,
        new_review_by=date(2027, 3, 11),
    )
    ast.parse(out)
    assert max(len(line) for line in out.splitlines()) <= 100


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


def test_check_mode_passes_against_the_real_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    assert main(["--check"]) == 0


def test_check_mode_does_not_measure_so_a_missing_readme_reports_drift_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deleted README is drift (exit 1), never "the tool could not run" (exit 2).

    `_measure` used to run before the mode branch and read all six READMEs, so the drain
    crashed with an errno on exactly the R13 drift it exists to report.
    """
    monkeypatch.chdir(REPO_ROOT)

    def explode(_root: Path) -> None:
        raise AssertionError("--check must not measure content pins")

    monkeypatch.setattr("tools.fixture_refresh.__main__._measure", explode)
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
