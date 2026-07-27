"""Group 1: PII and path shape rules (R1-R4 here, R5-R6 added in Task 3).

These cover the leakage class gitleaks structurally cannot catch. gitleaks finds
credentials in history; it does not care about a home-directory path or a profile URL,
and those are the concrete vectors when code is harvested from a private tool.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from tools.generalization import allowlists as al
from tools.generalization.discovery import Repo, RepoFile
from tools.generalization.model import Violation

SELF_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "tools/generalization/",
    "tests/generalization/",
)

HOME_PATH_RE = re.compile(
    r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])[A-Za-z0-9._-]+", re.IGNORECASE
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RESERVED_EMAIL_RE = re.compile(r"@example\.(?:com|org|net)$", re.IGNORECASE)
# R3 matches NANP (3-3-4, hyphen/dot separated, optional +1 country code), international
# numbers (a "+" country code followed by digit groups), and bare two-group numbers such
# as UK mobiles or 5-5 splits. The leading/trailing lookaround stops a match from being a
# fragment of a larger dotted or hyphenated run, which is what a version string or a
# chained date range looks like.
PHONE_RE = re.compile(
    r"(?<![\d.-])(?:"
    r"(?:\+1[ .-])?(?:\(\d{3}\)[ .-]|\d{3}[.-])\d{3}[.-]\d{4}"
    r"|\+\d{1,3}[ .-]?\d{2,6}(?:[ .-]?\d{2,6}){0,3}"
    r"|\d{5}[ .-]\d{5,6}"
    r")(?![\d.-])"
)
PROFILE_URL_RE = re.compile(r"linkedin\.com/in/|mailto:", re.IGNORECASE)

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
                if hit in al.HOME_PATH_EXCEPTIONS:
                    used_paths.add(hit)
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
                if hit in al.EMAIL_EXCEPTIONS:
                    used_emails.add(hit)
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
                if hit in al.PHONE_EXCEPTIONS:
                    used_phones.add(hit)
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
                if hit in al.PROFILE_URL_EXCEPTIONS:
                    used_profile_urls.add(hit)
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
