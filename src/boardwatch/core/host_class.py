"""Three host classes, not two (P6 design §3).

A binary ATS-vs-aggregator split classifies a company's own careers site as "not ATS" and
drops the company's own page in favour of a job board. `unknown` is the default and is
never suppressed and never elected, so an unclassified host fails to annotate-only.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

HostClass = Literal["ats", "aggregator", "unknown"]

# Versioned data. Field-neutral: these are applicant-tracking systems and job boards,
# nothing about a role, industry or country. Bump IDENTITY_ALGORITHM_VERSION when edited.
ATS_HOSTS: frozenset[str] = frozenset(
    {
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "myworkdayjobs.com",
        "workday.com",
        "smartrecruiters.com",
        "icims.com",
        "taleo.net",
        "successfactors.com",
        "bamboohr.com",
        "breezy.hr",
        "workable.com",
        "jobvite.com",
        "recruitee.com",
        "teamtailor.com",
        "rippling.com",
        "paylocity.com",
    }
)

AGGREGATOR_HOSTS: frozenset[str] = frozenset(
    {
        "linkedin.com",
        "indeed.com",
        "ziprecruiter.com",
        "glassdoor.com",
        "dice.com",
        "wellfound.com",
        "angel.co",
        "builtin.com",
        "simplyhired.com",
        "monster.com",
        "careerbuilder.com",
        "otta.com",
        "jobright.ai",
    }
)


def _host_of(url: str) -> str:
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return ""
    return host.lower()


def _matches(host: str, table: frozenset[str]) -> bool:
    # Suffix match on a dot boundary, never substring: "greenhouse.io.evil.example" and
    # "notgreenhouse.io" must not win survivor election.
    return any(host == known or host.endswith("." + known) for known in table)


def classify_host(url: str) -> HostClass:
    host = _host_of(url)
    if not host:
        return "unknown"
    if _matches(host, ATS_HOSTS):
        return "ats"
    if _matches(host, AGGREGATOR_HOSTS):
        return "aggregator"
    return "unknown"
