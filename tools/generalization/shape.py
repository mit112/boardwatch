"""Group 1: PII and path shape rules, R1 to R6.

These cover the leakage class gitleaks structurally cannot catch. gitleaks finds
credentials in history; it does not care about a home-directory path or a profile URL,
and those are the concrete vectors when code is harvested from a private tool.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from tools.generalization import allowlists as al
from tools.generalization.discovery import Repo, RepoFile
from tools.generalization.model import Violation

SELF_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "tools/generalization/",
    "tests/generalization/",
)

# Case matters, and only the Windows drive form is case-insensitive. Real macOS output is
# always "/Users/" and real Linux output always "/home/", while a blanket IGNORECASE also
# matched ordinary REST routes: "GET /users/me" and "/api/v1/users/123" both fired, and this
# project integrates an API documented as /v1/users/{id}. A rule that fires on legitimate
# content is the failure this phase exists to correct, so the case-variant prefixes
# ("/users/", "/HOME/") are an accepted bypass instead.
HOME_PATH_RE = re.compile(r"(?:/Users/|/home/|(?i:[A-Za-z]:[\\/]Users[\\/]))[A-Za-z0-9._-]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RESERVED_EMAIL_RE = re.compile(r"@example\.(?:com|org|net)$", re.IGNORECASE)
# R3 matches NANP (3-3-4, hyphen/dot separated, optional +1 country code), international
# numbers written with an explicit "+" country code (either separated groups or the
# compact E.164 run), and the trunk-zero form (a leading zero, 5 digits, a space, 6
# digits). The leading/trailing lookaround stops a match from being a fragment of a larger
# dotted or hyphenated run, which is what a version string or a chained date range looks
# like. There is deliberately NO bare local-format alternative: a digit pair with no
# country code has the same shape as a numeric range (a salary band, a port range) or a
# space-grouped identifier, so no shape-only rule can tell them apart. Local-format
# numbers are an accepted bypass.
PHONE_RE = re.compile(
    r"(?<![\d.-])(?:"
    r"(?:\+1[ .-])?(?:\(\d{3}\)[ .-]|\d{3}[.-])\d{3}[.-]\d{4}"
    r"|\+\d{1,3}[ .-]\d{2,6}(?:[ .-]?\d{2,6}){1,3}"
    r"|\+\d{10,15}"
    r"|0\d{4} \d{6}"
    r")(?![\d.-])"
)
# Numbers whose digits including the country code total fewer than ten are not matched. Ten is
# the threshold that separates a real number from space-grouped or dot-grouped thousands
# notation, which is how a changelog delta ("+12 345 678 bytes") is written. The cost is real
# in both directions and stated rather than hidden: a handful of national plans reach only
# eight or nine digits with the country code and are therefore missed, while grouped values at
# or above ten digits still match.
MIN_INTL_PHONE_DIGITS = 10
# The identifying tail is part of the match on purpose: the exception table keys on matched
# text, so a bare "mailto:" pattern would mean the only possible entry is "mailto:" itself,
# which disables half of R4 repo-wide. Same match-level discipline R2 uses. The last character
# of the tail may not be trailing punctuation, so a SECURITY.md contact line ending a sentence
# with a period does not fold that period into the match: an exception keyed on the clean
# address then actually matches, instead of producing two confusing violations (the punctuated
# hit unexcused, the clean entry unused).
PROFILE_URL_RE = re.compile(
    r"linkedin\.com/in/[A-Za-z0-9_%-]+|mailto:[^\s\"'>)\]]*[^\s\"'>)\].,;:!?]", re.IGNORECASE
)

ALLOWLIST_PATH = "tools/generalization/allowlists.py"


def scannable(repo: Repo) -> Iterator[RepoFile]:
    """Files the rules may inspect, minus the checker's own sources."""
    for entry in repo.files:
        if entry.path.startswith(SELF_EXCLUDED_PREFIXES):
            continue
        yield entry


def stale(table: dict[str, str], used: set[str], rule: str) -> list[Violation]:
    """An exception that never matched is dead weight and hides drift.

    A match found only inside a self-excluded file (allowlists.py itself, or this
    module) never marks its entry used, on purpose: without that, every exception
    would mark itself used against its own literal in allowlists.py, and staleness
    detection would never fire.
    """
    return [
        Violation(
            rule,
            ALLOWLIST_PATH,
            None,
            f"stale exception {key!r} never matched anything; remove it",
        )
        for key in sorted(set(table) - used)
    ]


def excused(
    table: dict[str, str],
    hit: str,
    used: set[str],
    rule: str,
    problems: list[Violation],
) -> bool:
    """Whether `hit` carries an exception entry, and whether that entry is worth anything.

    Returns True for any entry, so the hit is not reported twice, but records a violation when
    the reason is blank. The entry IS the justification, so membership alone would make these
    tables the rubber stamps this discipline exists to prevent. Same rule check_inventory
    applies to a blank SHIPPED_DATA reason. The key is marked used either way, so a blank entry
    is reported once as a blank reason rather than also as stale.
    """
    if hit not in table:
        return False
    used.add(hit)
    if not table[hit].strip():
        problems.append(
            Violation(
                rule,
                ALLOWLIST_PATH,
                None,
                f"exception {hit!r} has a blank reason. The entry is the justification, so a "
                "blank one is a rubber stamp",
            )
        )
    return True


def check_shapes(repo: Repo) -> list[Violation]:
    """R1 home paths, R2 emails, R3 phone numbers, R4 personal profile URLs."""
    violations: list[Violation] = []
    used_paths: set[str] = set()
    used_emails: set[str] = set()
    used_phones: set[str] = set()
    used_profile_urls: set[str] = set()
    for entry in scannable(repo):
        if not entry.is_text:
            continue
        for lineno, line in enumerate(entry.text.splitlines(), 1):
            for match in HOME_PATH_RE.finditer(line):
                hit = match.group(0)
                if excused(al.HOME_PATH_EXCEPTIONS, hit, used_paths, "R1", violations):
                    continue
                violations.append(
                    Violation(
                        "R1",
                        entry.path,
                        lineno,
                        f"home-directory absolute path {hit!r}. "
                        "Use '~/...' or '<home>/...' in docs and a tmp_path in tests",
                    )
                )
            for match in EMAIL_RE.finditer(line):
                hit = match.group(0)
                if RESERVED_EMAIL_RE.search(hit):
                    continue
                if excused(al.EMAIL_EXCEPTIONS, hit, used_emails, "R2", violations):
                    continue
                violations.append(
                    Violation(
                        "R2",
                        entry.path,
                        lineno,
                        f"email address {hit!r}. Use an example.com address, "
                        "or add a reviewed entry to EMAIL_EXCEPTIONS",
                    )
                )
            for match in PHONE_RE.finditer(line):
                hit = match.group(0)
                if excused(al.PHONE_EXCEPTIONS, hit, used_phones, "R3", violations):
                    continue
                if hit.startswith("+") and sum(c.isdigit() for c in hit) < MIN_INTL_PHONE_DIGITS:
                    continue
                violations.append(
                    Violation(
                        "R3",
                        entry.path,
                        lineno,
                        f"phone-number-shaped text {hit!r}. "
                        "Use a fictional number, or add a reviewed entry to PHONE_EXCEPTIONS",
                    )
                )
            for match in PROFILE_URL_RE.finditer(line):
                hit = match.group(0)
                if excused(al.PROFILE_URL_EXCEPTIONS, hit, used_profile_urls, "R4", violations):
                    continue
                violations.append(
                    Violation(
                        "R4",
                        entry.path,
                        lineno,
                        f"personal profile URL {hit!r}. "
                        "Add a reviewed entry to PROFILE_URL_EXCEPTIONS",
                    )
                )
    violations.extend(stale(al.HOME_PATH_EXCEPTIONS, used_paths, "R1"))
    violations.extend(stale(al.EMAIL_EXCEPTIONS, used_emails, "R2"))
    violations.extend(stale(al.PHONE_EXCEPTIONS, used_phones, "R3"))
    violations.extend(stale(al.PROFILE_URL_EXCEPTIONS, used_profile_urls, "R4"))
    return violations


ARTIFACT_STEMS: frozenset[str] = frozenset(
    {
        "resume",
        "résumé",
        "cv",
        "cover_letter",
        "cover-letter",
        "coverletter",
        "eeo",
        "work_auth",
        "work-authorization",
        "transcript",
    }
)

# Stems are matched on data and artifact files only, never on .py modules. A
# legitimate resume.py, work_auth.py, eeo.py or cv.py (computer vision) must pass:
# this phase bans personal VALUES, not work-authorization CONCEPTS. The eligibility
# feature will reason about work authorization as a requirement, by design.
STEM_CHECKED_SUFFIXES: frozenset[str] = frozenset(
    {
        "",
        ".yaml",
        ".yml",
        ".json",
        ".jsonl",
        ".csv",
        ".tsv",
        ".toml",
        ".tex",
        ".typ",
        ".txt",
        ".md",
        ".mako",
    }
)

BINARY_DOC_SUFFIXES: frozenset[str] = frozenset({".pdf", ".docx", ".doc", ".rtf", ".pages"})


def _artifact_stem(path: str) -> str | None:
    # Leading dots are stripped so a hidden file like .resume.yaml cannot bypass
    # the stem check.
    for segment in PurePosixPath(path).parts:
        stem = PurePosixPath(segment).stem.lstrip(".").casefold()
        if stem in ARTIFACT_STEMS:
            return stem
    return None


def check_artifact_files(repo: Repo) -> list[Violation]:
    """R5 personal-artifact filenames, R6 binary documents."""
    violations: list[Violation] = []
    used_names: set[str] = set()
    used_binaries: set[str] = set()
    for entry in scannable(repo):
        if entry.suffix in BINARY_DOC_SUFFIXES:
            if not excused(al.BINARY_DOC_EXCEPTIONS, entry.path, used_binaries, "R6", violations):
                violations.append(
                    Violation(
                        "R6",
                        entry.path,
                        None,
                        f"binary document ({entry.suffix}). This repo ships no documents, "
                        "and a document is a common carrier for personal data",
                    )
                )
        if entry.suffix in STEM_CHECKED_SUFFIXES:
            hit = _artifact_stem(entry.path)
            if hit is None:
                continue
            if not excused(al.ARTIFACT_NAME_EXCEPTIONS, entry.path, used_names, "R5", violations):
                violations.append(
                    Violation(
                        "R5",
                        entry.path,
                        None,
                        f"personal-artifact name segment {hit!r}. Personal career data "
                        "belongs in the user's own data directory, never in this repo",
                    )
                )
    violations.extend(stale(al.ARTIFACT_NAME_EXCEPTIONS, used_names, "R5"))
    violations.extend(stale(al.BINARY_DOC_EXCEPTIONS, used_binaries, "R6"))
    return violations
