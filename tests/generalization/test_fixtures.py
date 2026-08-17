"""R13-R15: fixture coverage against the registry, provenance pins, and review deadlines.

Every test here is a mutation proof: it makes one thing wrong in a copy of the real tree and
names the rule that must notice. A check that cannot fire is a check to delete, so the control
tests (the real tree is clean) are only meaningful next to these.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from boardwatch.providers.registry import PROVIDER_NAMES
from tools.generalization import fixtures as fx
from tools.generalization.discovery import Repo, RepoFile, discover
from tools.generalization.fixtures import (
    CORPUS_PATH,
    FIXTURE_PROVENANCE,
    Extension,
    FixtureProvenance,
    check_fixture_coverage,
    check_fixture_pins,
    check_fixture_review_due,
    readme_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _real() -> Repo:
    return discover(REPO_ROOT)


def _substitute(path: str, data: bytes, tmp_path: Path) -> Repo:
    """The real tree with one file's BYTES replaced by a file that really exists on disk.

    The bytes must land on disk because the pin rules hash `abspath.read_bytes()`, not the
    decoded `text` field -- hashing the lossy `errors="replace"` decode would make the pin
    disagree with git for any non-UTF-8 byte.
    """
    target = tmp_path / hashlib.sha256(path.encode()).hexdigest()[:16]
    target.write_bytes(data)
    kept = tuple(f for f in _real().files if f.path != path)
    replaced = RepoFile(
        path=path,
        abspath=target,
        is_text=True,
        text=data.decode("utf-8", errors="replace"),
    )
    return Repo(root=REPO_ROOT, files=kept + (replaced,))


def _without(prefix: str) -> Repo:
    """The real tree with every file at or under `prefix` absent."""
    kept = tuple(
        f for f in _real().files if f.path != prefix and not f.path.startswith(prefix + "/")
    )
    return Repo(root=REPO_ROOT, files=kept)


def _plus(path: str, tmp_path: Path) -> Repo:
    """The real tree with one extra tracked file."""
    target = tmp_path / "extra"
    target.write_text("{}\n", encoding="utf-8")
    extra = RepoFile(path=path, abspath=target, is_text=True, text="{}\n")
    return Repo(root=REPO_ROOT, files=_real().files + (extra,))


def _rules(violations: list[fx.Violation]) -> set[str]:
    return {v.rule for v in violations}


# --------------------------------------------------------------------------- controls


def test_the_real_tree_passes_all_three_rules() -> None:
    repo = _real()
    assert check_fixture_coverage(repo) == []
    assert check_fixture_pins(repo) == []
    assert check_fixture_review_due(repo, today=date(2026, 8, 17)) == []


def test_every_registered_provider_has_provenance_and_a_future_deadline() -> None:
    """Pins the gate's own premise: it lands green, and each deadline is a real future date."""
    assert set(FIXTURE_PROVENANCE) == set(PROVIDER_NAMES)
    for name, record in FIXTURE_PROVENANCE.items():
        assert record.captured <= record.review_by, name
        assert record.readme_pin.startswith("sha256:"), name


# --------------------------------------------------------------------------- R13 coverage


def test_registering_a_seventh_provider_without_fixtures_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headline case driven from the registry side, not by deleting a directory.

    Removing an existing directory exercises the same set difference, but only this direction
    proves the gate is derived from LIVE CONFIG -- that adding to the registry is what makes it
    fire, which is the property CLAUDE.md asks for.
    """
    monkeypatch.setattr(fx, "PROVIDER_NAMES", PROVIDER_NAMES | {"jobvite"})
    violations = check_fixture_coverage(_real())
    assert _rules(violations) == {"R13"}
    assert [v.path for v in violations] == ["tests/fixtures/jobvite"]
    assert "is in the registry but has no fixture directory" in violations[0].detail


def test_a_registered_provider_with_no_fixture_directory_fails() -> None:
    """The headline case: register a seventh provider, capture nothing, and be caught."""
    violations = check_fixture_coverage(_without("tests/fixtures/lever"))
    assert _rules(violations) == {"R13"}
    assert any("is in the registry but has no fixture directory" in v.detail for v in violations)
    assert any("lever" in v.path for v in violations)


def test_a_fixture_directory_matching_no_provider_fails(tmp_path: Path) -> None:
    """The other direction: deleting a provider must not leave an orphan directory."""
    violations = check_fixture_coverage(_plus("tests/fixtures/retired/normal.json", tmp_path))
    assert _rules(violations) == {"R13"}
    assert any("maps to no registered provider" in v.detail for v in violations)


def test_a_file_loose_at_the_fixture_root_fails(tmp_path: Path) -> None:
    violations = check_fixture_coverage(_plus("tests/fixtures/stray.json", tmp_path))
    assert _rules(violations) == {"R13"}
    assert any("belongs to no provider" in v.detail for v in violations)


def test_a_provider_directory_without_a_readme_fails() -> None:
    violations = check_fixture_coverage(_without("tests/fixtures/ashby/README.md"))
    assert _rules(violations) == {"R13"}
    assert any("no README.md" in v.detail for v in violations)


def test_a_provider_directory_without_any_json_fails() -> None:
    """Strip every capture but keep the README: the directory records provenance for nothing."""
    kept = tuple(
        f
        for f in _real().files
        if not (f.path.startswith("tests/fixtures/workable/") and f.path.endswith(".json"))
    )
    violations = check_fixture_coverage(Repo(root=REPO_ROOT, files=kept))
    assert _rules(violations) == {"R13"}
    assert any("no .json fixture" in v.detail for v in violations)


def test_enumeration_is_git_tracked_so_untracked_debris_cannot_fail_the_gate(
    tmp_path: Path,
) -> None:
    """A scratch file under tests/fixtures/ must not red the gate locally and vanish in CI.

    Discovery is what decides tracked-ness, so this pins the coupling: the rule reads
    `repo.files` and nothing else, and a real file on disk that discovery did not report is
    invisible to it.
    """
    debris = REPO_ROOT / "tests" / "fixtures" / "scratch-debris.json"
    debris.write_text("{}\n", encoding="utf-8")
    try:
        assert debris.exists()
        repo = _real()
        # Without this the test proves nothing: the walk fallback WOULD see the debris, so a
        # pass in walk mode would be a false negative rather than evidence about tracking.
        assert repo.mode == "git"
        assert not any(f.path.endswith("scratch-debris.json") for f in repo.files)
        assert check_fixture_coverage(repo) == []
    finally:
        debris.unlink()


# --------------------------------------------------------------------------- R14 pins


def test_an_edited_readme_fails(tmp_path: Path) -> None:
    """The provenance half: R7 cannot see .md at all, so this is the only thing watching."""
    path = readme_path("workday")
    original = (REPO_ROOT / path).read_bytes()
    repo = _substitute(path, original + b"\nCaptured 2026-08-17.\n", tmp_path)
    violations = check_fixture_pins(repo)
    assert _rules(violations) == {"R14"}
    assert any("provenance changed" in v.detail for v in violations)


def test_an_edited_corpus_row_fails(tmp_path: Path) -> None:
    """The tamper case this rule exists for: flip one expected verdict to green a red test."""
    original = (REPO_ROOT / CORPUS_PATH).read_text(encoding="utf-8")
    tampered = original.replace(
        "'ineligible', [['work_auth:no_sponsorship_offered', 'required', 'unmet']]",
        "'eligible', [['work_auth:no_sponsorship_offered', 'required', 'met']]",
        1,
    )
    assert tampered != original, "the tamper did not apply, so this test proves nothing"
    violations = check_fixture_pins(_substitute(CORPUS_PATH, tampered.encode(), tmp_path))
    assert _rules(violations) == {"R14"}
    assert any("content changed" in v.detail for v in violations)


def test_appending_a_mutation_line_to_the_corpus_fails(tmp_path: Path) -> None:
    """Why the pin is over the whole file, not over the parsed CASES literal.

    CASES is a mutable list consumed by parametrize further down, so `CASES[0] = ...` appended
    below the literal rewrites the oracle while leaving the literal itself untouched. A digest
    over the parsed rows would stay green here.
    """
    original = (REPO_ROOT / CORPUS_PATH).read_text(encoding="utf-8")
    tampered = original + "\nCASES[0] = ('m0000:tampered', '', {}, {}, 'eligible', [])\n"
    repo = _substitute(CORPUS_PATH, tampered.encode(), tmp_path)
    # The literal is byte-identical, so the row count still agrees...
    assert fx._corpus_rows(repo) == fx.CORPUS_ROWS
    # ...and only the whole-file pin catches it.
    violations = check_fixture_pins(repo)
    assert _rules(violations) == {"R14"}
    assert any("content changed" in v.detail for v in violations)


def test_a_truncated_corpus_fails_the_row_count_even_when_the_pin_agrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row count is a genuinely independent second path, not a restatement of the pin.

    Pinning the truncated file's own hash makes the byte check pass, which is exactly what a
    refresh tool that blessed a corrupted corpus would do. The ast-derived count still fires.
    """
    original = (REPO_ROOT / CORPUS_PATH).read_text(encoding="utf-8")
    head, sep, tail = original.partition("    ('m0500")
    assert sep, "the truncation anchor is gone; re-pick a row label"
    truncated = (head + "]\n" + tail.split("\n", 1)[1].split("]\n", 1)[1]).encode()
    monkeypatch.setattr(fx, "CORPUS_PIN", "sha256:" + hashlib.sha256(truncated).hexdigest())
    violations = check_fixture_pins(_substitute(CORPUS_PATH, truncated, tmp_path))
    assert _rules(violations) == {"R14"}
    assert any("rows, pinned at" in v.detail for v in violations)
    assert not any("content changed" in v.detail for v in violations)


def test_a_corpus_with_no_cases_literal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"CASES = []\n"
    monkeypatch.setattr(fx, "CORPUS_PIN", "sha256:" + hashlib.sha256(body).hexdigest())
    violations = check_fixture_pins(_substitute(CORPUS_PATH, body, tmp_path))
    assert any("cannot be counted through a second path" in v.detail for v in violations)


def test_a_missing_corpus_fails() -> None:
    violations = check_fixture_pins(_without(CORPUS_PATH))
    assert _rules(violations) == {"R14"}
    assert any("is not in the tree" in v.detail for v in violations)


# --------------------------------------------------------------------------- R15 deadlines


def test_an_overdue_review_fails() -> None:
    violations = check_fixture_review_due(_real(), today=date(2027, 1, 1))
    assert _rules(violations) == {"R15"}
    assert len(violations) == len(PROVIDER_NAMES)
    assert all("review overdue by" in v.detail for v in violations)


def test_the_deadline_is_still_green_on_the_due_date_itself() -> None:
    """`today > review_by`, not `>=`: the due date is the last green day, as documented."""
    due = FIXTURE_PROVENANCE["greenhouse"].review_by
    assert check_fixture_review_due(_real(), today=due) == []
    overdue = check_fixture_review_due(_real(), today=date.fromordinal(due.toordinal() + 1))
    assert [v.path for v in overdue] == [readme_path("greenhouse")]


def test_a_registered_provider_with_no_provenance_entry_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trimmed = {k: v for k, v in FIXTURE_PROVENANCE.items() if k != "ashby"}
    monkeypatch.setattr(fx, "FIXTURE_PROVENANCE", trimmed)
    violations = check_fixture_review_due(_real(), today=date(2026, 8, 17))
    assert _rules(violations) == {"R15"}
    assert any("has no FIXTURE_PROVENANCE entry" in v.detail for v in violations)


def test_a_provenance_entry_for_no_registered_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The closed catalog runs both ways: a retired provider must not keep its entry."""
    extra = dict(FIXTURE_PROVENANCE)
    extra["retired"] = FixtureProvenance(
        captured=date(2026, 1, 1), review_by=date(2027, 1, 1), readme_pin="sha256:00"
    )
    monkeypatch.setattr(fx, "FIXTURE_PROVENANCE", extra)
    violations = check_fixture_review_due(_real(), today=date(2026, 8, 17))
    assert _rules(violations) == {"R15"}
    assert any("stale FIXTURE_PROVENANCE entry" in v.detail for v in violations)


def test_a_deadline_that_precedes_its_capture_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = dict(FIXTURE_PROVENANCE)
    broken["lever"] = FixtureProvenance(
        captured=date(2026, 6, 13), review_by=date(2026, 6, 1), readme_pin="sha256:00"
    )
    monkeypatch.setattr(fx, "FIXTURE_PROVENANCE", broken)
    violations = check_fixture_review_due(_real(), today=date(2026, 8, 17))
    assert any("precedes captured" in v.detail for v in violations)


def test_a_blank_extension_reason_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drain's reason is the acceptance, so an empty one is a rubber stamp."""
    rubber = dict(FIXTURE_PROVENANCE)
    rubber["workday"] = FixtureProvenance(
        captured=date(2026, 8, 4),
        review_by=date(2026, 11, 2),
        readme_pin=FIXTURE_PROVENANCE["workday"].readme_pin,
        extensions=(Extension(on=date(2026, 9, 1), reason="   "),),
    )
    monkeypatch.setattr(fx, "FIXTURE_PROVENANCE", rubber)
    violations = check_fixture_review_due(_real(), today=date(2026, 8, 17))
    assert _rules(violations) == {"R15"}
    assert any("blank reason" in v.detail for v in violations)


def test_out_of_order_extensions_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    jumbled = dict(FIXTURE_PROVENANCE)
    jumbled["workday"] = FixtureProvenance(
        captured=date(2026, 8, 4),
        review_by=date(2026, 11, 2),
        readme_pin=FIXTURE_PROVENANCE["workday"].readme_pin,
        extensions=(
            Extension(on=date(2026, 10, 1), reason="no network on the road"),
            Extension(on=date(2026, 9, 1), reason="backdated"),
        ),
    )
    monkeypatch.setattr(fx, "FIXTURE_PROVENANCE", jumbled)
    violations = check_fixture_review_due(_real(), today=date(2026, 8, 17))
    assert any("out of order" in v.detail for v in violations)


def test_an_extension_with_a_real_reason_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drain must actually drain, or the gate is a wall."""
    rolled = dict(FIXTURE_PROVENANCE)
    rolled["greenhouse"] = FixtureProvenance(
        captured=date(2026, 6, 12),
        review_by=date(2026, 12, 9),
        readme_pin=FIXTURE_PROVENANCE["greenhouse"].readme_pin,
        extensions=(Extension(on=date(2026, 9, 10), reason="no network access this week"),),
    )
    monkeypatch.setattr(fx, "FIXTURE_PROVENANCE", rolled)
    assert check_fixture_review_due(_real(), today=date(2026, 9, 11)) == []
