"""R13-R15: the ATS fixture set is derived from live config, the provenance that R7 cannot
see is pinned, and every capture carries a declared review deadline.

R7 already pins the BYTES of all 31 fixture .json files, so content drift in those is a solved
problem. Three things it cannot see, because each is a different KIND of drift:

R13  The fixture set versus the provider registry. R7 pins what is there; nothing asks whether
     what is there is what the registry says should be. A seventh provider whose fixtures were
     never captured is invisible to a byte pin, because the missing directory has no bytes.

R14  The six README.md files. `.md` is outside DATA_SUFFIXES, so they are outside R7's scope
     entirely. They carry the capture date and the recorded field contract -- Workday's records
     three pagination traps and the jobReqId/jobPostingId split -- so an unreviewed edit there
     rewrites what the fixture is CLAIMED to prove while every byte pin stays green. The
     eligibility corpus is pinned here for the same reason: it is a .py, so R7 never sees it,
     and one edited expected-verdict turns a red test green.

R15  Review deadlines. A capture that still matches its pin perfectly can have been overtaken
     by the live API months ago. This is the one drift that no hash can detect offline.

WHAT R15 DOES AND DOES NOT MEAN. It enforces that somebody looked on schedule; it does NOT
prove a fixture matches production. `--extend` restores green with a reason and no network, by
design (see the drain, below). Calling it a freshness gate would be a lie -- it is a
review-deadline gate, and an overdue review is the thing it reports.

WHY IT FAILS RATHER THAN WARNS. A warning loses to the noise of a 6,439-test run, and the
failure it would be describing is the exact disease CLAUDE.md names: a fixture sitting still
while production churns. A single global max-age constant was rejected because bumping one
number silences all six providers at once -- one edit erasing six independent signals.

THE DRAIN (CLAUDE.md: every quarantine needs one, designed in the same change). Red here is
actionable WITHOUT network: `python -m tools.fixture_refresh --extend <provider> --days N
--reason "..."` appends a dated, reasoned rollover. So the gate never blocks someone who cannot
reach the live API, and a fixture rolled over three times shows three lines of history instead
of sliding quietly.

Provenance lives in this module as a typed dict rather than a data file for one reason: this is
tools CODE, not repo DATA, so it stays outside R7's inventory scope and needs no pin of its own,
and `mypy --strict` checks it.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath

from boardwatch.providers.registry import PROVIDER_NAMES
from tools.generalization.discovery import Repo
from tools.generalization.model import Violation

FIXTURE_ROOT = "tests/fixtures"
CORPUS_PATH = "tests/pipeline/test_eligibility_corpus.py"

# The literal whose rows are the oracle. Named here so R15 reads the same symbol the test
# parametrizes over, rather than re-deriving a grammar for "the big list in that file".
CORPUS_SYMBOL = "CASES"

REFRESH_HINT = "Run `python -m tools.fixture_refresh --check` to see what changed."

@dataclass(frozen=True)
class Extension:
    """One dated, reasoned rollover of a review deadline. The drain's audit trail."""

    on: date
    reason: str


@dataclass(frozen=True)
class FixtureProvenance:
    """What a human recorded about one provider's captured fixtures.

    `captured` is when the shape was recorded from the live API during an attended session.
    `review_by` is the date the next review is DUE, not a claim about freshness.
    """

    captured: date
    review_by: date
    readme_pin: str
    extensions: tuple[Extension, ...] = field(default_factory=tuple)


# Capture dates are the ones each README states in prose, cross-read against the last commit
# to touch that directory. Deadlines are captured + 90 days: an ATS response shape is not
# stable enough for a longer window, and a shorter one would have landed this gate already red.
FIXTURE_PROVENANCE: dict[str, FixtureProvenance] = {
    "ashby": FixtureProvenance(
        captured=date(2026, 6, 13),
        review_by=date(2026, 9, 11),
        readme_pin="sha256:68a4536b3d10f9fb6eafe18aa1a0396ecbe77352a0693daee1770374bc120dd2",
    ),
    "greenhouse": FixtureProvenance(
        captured=date(2026, 6, 12),
        review_by=date(2026, 9, 10),
        readme_pin="sha256:dca8ddf164d773e3f8a75842071cf53e26b15653f9405357f261602b689341d5",
    ),
    "lever": FixtureProvenance(
        captured=date(2026, 6, 13),
        review_by=date(2026, 9, 11),
        readme_pin="sha256:622d35d9b72fd239bd1f143ee18bb043df8d6b5f332a85ec61d008b1f129dc97",
    ),
    "smartrecruiters": FixtureProvenance(
        captured=date(2026, 8, 1),
        review_by=date(2026, 10, 30),
        readme_pin="sha256:ce749351be812b2358411a618226397c6971ec003a3ccfc8b162fea7c2eda3b8",
    ),
    "workable": FixtureProvenance(
        captured=date(2026, 8, 1),
        review_by=date(2026, 10, 30),
        readme_pin="sha256:7da2fa0bc2c002798ce0eee0843f3699bab3cef964b8d2fed727bd87cab6e008",
    ),
    "workday": FixtureProvenance(
        captured=date(2026, 8, 4),
        review_by=date(2026, 11, 2),
        readme_pin="sha256:1526656082a998a36b05e11a80dfa02d85f36e0484ca3cdca523116e2519b48c",
    ),
}

# Whole-file byte pin, not a digest over the parsed rows. CASES is a mutable list consumed by
# @pytest.mark.parametrize further down the file, so a digest over the literal alone stays green
# while a `CASES[0] = (...)` line appended below rewrites the oracle. Byte-stable across
# platforms because .gitattributes pins eol=lf repo-wide for exactly this reason.
CORPUS_PIN = "sha256:fbaf07ca83af85d755b6a14292b211d0afdc633e676d9a0c4c105dc9e1aed021"

# A HUMAN-REVIEWED constant, and that is the whole of its value. It is counted by ast rather than
# by bytes, but that alone would not make it a second path: an earlier version let
# `fixture_refresh --record` rewrite this number from the same read that produced CORPUS_PIN, and
# a 500-row truncated corpus then went green on both. So `--record` REFUSES to write this line --
# it prints the measured count and stops, and a human edits it. The independence is the human,
# not the ast. The corpus asserts this number itself at its own tail; that assert lives INSIDE
# the file being tampered with, which is why it is restated out here.
CORPUS_ROWS = 1038


def readme_path(provider: str) -> str:
    return f"{FIXTURE_ROOT}/{provider}/README.md"


def _sha256(repo: Repo, path: str) -> str | None:
    """Hex digest of a tracked file's bytes, or None when it is not in the tree."""
    entry = repo.by_path(path)
    if entry is None:
        return None
    return hashlib.sha256(entry.abspath.read_bytes()).hexdigest()


def _tracked_under_fixtures(repo: Repo) -> tuple[dict[str, set[str]], set[str]]:
    """Provider directory -> the paths inside it RELATIVE to that directory, plus any file
    loose at the fixture root.

    Enumerated from `repo.files` (git-tracked) rather than by walking the filesystem: an
    untracked scratch file under tests/fixtures/ would fail this gate locally and then vanish
    in CI, which is a worse gate than none.

    Relative paths, NOT basenames. Bucketing by basename let `ashby/docs/README.md` satisfy
    R13's "has a README" check while `ashby/README.md` was deleted, and R14 then skipped the
    absent file -- so the one document R14 exists to pin could be replaced wholesale with all
    fifteen rules green. A nested path must stay distinguishable from a top-level one.
    """
    dirs: dict[str, set[str]] = {}
    loose: set[str] = set()
    for entry in repo.files:
        parts = PurePosixPath(entry.path).parts
        if len(parts) < 3 or parts[0] != "tests" or parts[1] != "fixtures":
            continue
        if len(parts) == 3:
            loose.add(parts[2])
            continue
        dirs.setdefault(parts[2], set()).add("/".join(parts[3:]))
    return dirs, loose


def check_fixture_coverage(repo: Repo) -> list[Violation]:
    """R13: the fixture set matches the provider registry, in both directions."""
    violations: list[Violation] = []
    dirs, loose = _tracked_under_fixtures(repo)

    for provider in sorted(PROVIDER_NAMES - set(dirs)):
        violations.append(
            Violation(
                "R13",
                f"{FIXTURE_ROOT}/{provider}",
                None,
                f"provider {provider!r} is in the registry but has no fixture directory. "
                "Capture its fixtures in an attended session, or do not register it",
            )
        )
    for provider in sorted(set(dirs) - PROVIDER_NAMES):
        violations.append(
            Violation(
                "R13",
                f"{FIXTURE_ROOT}/{provider}",
                None,
                f"fixture directory {provider!r} maps to no registered provider. Delete it, "
                "or restore the provider it belongs to",
            )
        )
    for name in sorted(loose):
        violations.append(
            Violation(
                "R13",
                f"{FIXTURE_ROOT}/{name}",
                None,
                "file at the fixture root belongs to no provider. Move it under the provider "
                "directory it documents, or widen this rule deliberately if the fixture root "
                "ever needs a file of its own",
            )
        )

    for provider in sorted(PROVIDER_NAMES & set(dirs)):
        names = dirs[provider]
        for nested in sorted(name for name in names if "/" in name):
            violations.append(
                Violation(
                    "R13",
                    f"{FIXTURE_ROOT}/{provider}/{nested}",
                    None,
                    "a provider directory holds files, never subdirectories. Nesting hides a "
                    "file from the rule that pins it: a nested README.md once satisfied the "
                    "presence check below while the pinned top-level one was deleted",
                )
            )
        for stray in sorted(
            name for name in names if name.endswith(".md") and name != "README.md"
        ):
            violations.append(
                Violation(
                    "R13",
                    f"{FIXTURE_ROOT}/{provider}/{stray}",
                    None,
                    "only README.md may be Markdown here. R7 cannot see .md at all and R14 "
                    "pins README.md by name, so a second .md file is pinned by nothing and "
                    "can state anything",
                )
            )
        if "README.md" not in names:
            violations.append(
                Violation(
                    "R13",
                    readme_path(provider),
                    None,
                    "no README.md. The README is where the capture date and the recorded "
                    "field contract live, so a directory without one records no provenance",
                )
            )
        if not any(name.endswith(".json") for name in names):
            violations.append(
                Violation(
                    "R13",
                    f"{FIXTURE_ROOT}/{provider}",
                    None,
                    "no .json fixture. A provider directory holding no capture proves nothing",
                )
            )
    return violations


def count_corpus_rows(text: str) -> int | None:
    """Rows in the corpus literal, by ast so the module is never imported. None if unreadable.

    The ONE implementation. `fixture_refresh` measures through this same function rather than
    keeping its own walk: a second copy drifted on two points at once (which duplicate
    `CASES` wins, and whether an unreadable literal counts as 0), which would have let the
    tool record a number the gate disagreed with.
    """
    for node in ast.parse(text).body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not (isinstance(node.target, ast.Name) and node.target.id == CORPUS_SYMBOL):
            continue
        return len(node.value.elts) if isinstance(node.value, ast.List) else None
    return None


def _corpus_rows(repo: Repo) -> int | None:
    entry = repo.by_path(CORPUS_PATH)
    return None if entry is None else count_corpus_rows(entry.text)


def check_fixture_pins(repo: Repo) -> list[Violation]:
    """R14: the provenance and oracle files that DATA_SUFFIXES does not reach are pinned."""
    violations: list[Violation] = []

    for provider in sorted(PROVIDER_NAMES & set(FIXTURE_PROVENANCE)):
        path = readme_path(provider)
        actual = _sha256(repo, path)
        if actual is None:
            # Deliberately NOT deferred to R13. An earlier version skipped here on the grounds
            # that R13 owns the missing-file report, and that made the two rules jointly
            # bypassable: nest a README one level down and R13's presence check was satisfied
            # while this pin was never compared. A rule that owns a pin reports its own
            # absence.
            violations.append(
                Violation(
                    "R14",
                    path,
                    None,
                    "the pinned README is not in the tree. It carries the capture date and "
                    "the recorded field contract, so losing it discards the provenance this "
                    "pin exists to protect",
                )
            )
            continue
        expected = FIXTURE_PROVENANCE[provider].readme_pin.removeprefix("sha256:")
        if actual != expected:
            violations.append(
                Violation(
                    "R14",
                    path,
                    None,
                    f"provenance changed: pin says {expected[:12]}, file is {actual[:12]}. "
                    f"Re-review what the README now claims, then re-record. {REFRESH_HINT}",
                )
            )

    actual_corpus = _sha256(repo, CORPUS_PATH)
    if actual_corpus is None:
        violations.append(
            Violation(
                "R14",
                CORPUS_PATH,
                None,
                "the pinned eligibility corpus is not in the tree. It is the oracle for 987 "
                "labelled cases; losing it silently would retire that gate",
            )
        )
        return violations

    expected_corpus = CORPUS_PIN.removeprefix("sha256:")
    if actual_corpus != expected_corpus:
        violations.append(
            Violation(
                "R14",
                CORPUS_PATH,
                None,
                f"content changed: pin says {expected_corpus[:12]}, file is "
                f"{actual_corpus[:12]}. An edited expected-verdict turns a red test green, so "
                f"this change needs review before the pin moves. {REFRESH_HINT}",
            )
        )

    rows = _corpus_rows(repo)
    if rows is None:
        violations.append(
            Violation(
                "R14",
                CORPUS_PATH,
                None,
                f"no `{CORPUS_SYMBOL}: ... = [...]` literal found. The row count cannot be "
                "counted through a second path, so the pin is verifying itself",
            )
        )
    elif rows != CORPUS_ROWS:
        violations.append(
            Violation(
                "R14",
                CORPUS_PATH,
                None,
                f"{CORPUS_SYMBOL} holds {rows} rows, pinned at {CORPUS_ROWS}. "
                f"{REFRESH_HINT}",
            )
        )
    return violations


def check_fixture_review_due(repo: Repo, today: date | None = None) -> list[Violation]:
    """R15: every registered provider declares a review deadline, and none is overdue."""
    violations: list[Violation] = []
    now = today or date.today()

    for provider in sorted(PROVIDER_NAMES - set(FIXTURE_PROVENANCE)):
        violations.append(
            Violation(
                "R15",
                "tools/generalization/fixtures.py",
                None,
                f"provider {provider!r} has no FIXTURE_PROVENANCE entry. Record when its "
                "fixtures were captured and when they are next due for review",
            )
        )
    for provider in sorted(set(FIXTURE_PROVENANCE) - PROVIDER_NAMES):
        violations.append(
            Violation(
                "R15",
                "tools/generalization/fixtures.py",
                None,
                f"stale FIXTURE_PROVENANCE entry {provider!r}: no such registered provider",
            )
        )

    for provider in sorted(PROVIDER_NAMES & set(FIXTURE_PROVENANCE)):
        record = FIXTURE_PROVENANCE[provider]
        if record.review_by < record.captured:
            violations.append(
                Violation(
                    "R15",
                    "tools/generalization/fixtures.py",
                    None,
                    f"{provider}: review_by {record.review_by} precedes captured "
                    f"{record.captured}, so the deadline was already past when it was set",
                )
            )
        previous = record.captured
        for extension in record.extensions:
            if not extension.reason.strip():
                violations.append(
                    Violation(
                        "R15",
                        "tools/generalization/fixtures.py",
                        None,
                        f"{provider}: an extension dated {extension.on} has a blank reason. "
                        "The reason IS the acceptance, so a blank one is a rubber stamp",
                    )
                )
            if extension.on < previous:
                violations.append(
                    Violation(
                        "R15",
                        "tools/generalization/fixtures.py",
                        None,
                        f"{provider}: extension dated {extension.on} is out of order (the "
                        f"one before it is {previous}). An unordered trail hides how many "
                        "times this capture has been rolled over",
                    )
                )
            previous = extension.on
        if now > record.review_by:
            overdue = (now - record.review_by).days
            violations.append(
                Violation(
                    "R15",
                    readme_path(provider),
                    None,
                    f"review overdue by {overdue} day(s): captured {record.captured}, due "
                    f"{record.review_by}. Re-check the live API and re-record, or accept the "
                    f"delay explicitly with `python -m tools.fixture_refresh --extend "
                    f"{provider} --days N --reason \"...\"`",
                )
            )
    return violations
