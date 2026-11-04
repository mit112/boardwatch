"""Which employers have been seen filing H-1B labor condition applications for computing jobs.

A lookup over a local data file (`<config_dir>/sponsors.json`, written by `boardwatch sponsors
build` from the US Department of Labor's public LCA disclosure files). The repository ships no data.

A record is EVIDENCE THAT AN EMPLOYER FILED. No record is not evidence that it does not: a new
company, a renamed one, a name that normalizes differently, and an employer outside the source
files all look the same. Nothing here may therefore be spelled "does not sponsor". The positive
flag a caller derives from a record is `sponsor_seen`; the absence of a record carries no flag.

This signal never touches eligibility. Nothing under `boardwatch/eligibility/` imports it.

Matching is EXACT on the normalized name. No prefix, no fuzzy, no substring: a loose match turns a
different company into a false green flag, and that is the only failure that matters here.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from boardwatch.eligibility.facts import Facts

SPONSORS_FILENAME = "sponsors.json"
EXCLUSIONS_FILENAME = "sponsor-exclusions.txt"
FORMAT_VERSION = 1

# A normalized name shorter than this is never matched: it is a common word, not an employer.
MIN_KEY_LENGTH = 4

# Legal-form words, dropped from the END of a name. `usa`, `us`, `america`, `holdings` and `group`
# are deliberately absent: removing them merges different companies.
_LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "llc",
        "llp",
        "lp",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "company",
        "plc",
        "pllc",
        "gmbh",
        "na",
    }
)
_DBA = re.compile(r"\s(?:dba|d/b/a)\s")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_employer(name: str) -> str:
    """The exact-match key for an employer name. Empty when nothing usable survives."""
    # NFKD splits an accented letter into base letter and combining mark; the ASCII encode drops
    # the mark (so `Décor` is `decor`, not `de cor`), emoji and a curly apostrophe. The straight
    # apostrophe is dropped to match, so `Kohl's` and `Kohl’s` are one name, `kohls`.
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("'", "")
    text = _DBA.split(f" {text} ", maxsplit=1)[0]
    tokens = _NOT_ALNUM.sub(" ", text.replace("&", " and ")).split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


class SponsorRecord(BaseModel):
    """What the source files say about one employer, over the rows that were counted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    feins: tuple[str, ...]
    certified_rows: int
    computing_rows: int
    computing_new_employment_rows: int
    computing_low_wage_rows: int
    secondary_entity_rows: int
    naics2: str
    state: str
    latest_decision: str | None


class SponsorsFile(BaseModel):
    """The file's shape. `extra="forbid"` so a stray key is reported, never silently unused."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: int
    built: str
    sources: tuple[dict[str, object], ...]
    employers: dict[str, SponsorRecord]


@dataclass(frozen=True)
class SponsorIndex:
    records: dict[str, SponsorRecord]
    exclusions: frozenset[str]
    problem: str | None

    def lookup(self, company_name: str) -> SponsorRecord | None:
        """The record for exactly this employer, or None. None means no record, nothing more."""
        key = normalize_employer(company_name)
        if len(key) < MIN_KEY_LENGTH or key in self.exclusions:
            return None
        return self.records.get(key)


def facts_need_sponsorship(facts: Facts) -> bool:
    """True only when the stored fact says so. Absent (None) and False are both inactive.

    A read of the declared bit and nothing else: no inference from `status`, so a profile that
    never answered the question never turns this signal on.
    """
    work_auth = facts.work_authorization
    return work_auth is not None and work_auth.needs_sponsorship is True


def load_sponsor_index(config_dir: Path) -> SponsorIndex:
    """Read the data file and the exclusions. Never raises; a failure lands in `problem`.

    A missing data file is an empty index with a problem, so a caller can say the signal is absent
    rather than render every company as unknown without a reason. An exclusions file that exists
    but cannot be read also yields an empty index: a name someone reviewed as wrong must not come
    back as a match because its file was unreadable.
    """
    path = config_dir / SPONSORS_FILENAME
    try:
        loaded = SponsorsFile.model_validate(json.loads(path.read_bytes()))
        if loaded.format != FORMAT_VERSION:
            return _empty(f"{path}: format {loaded.format}, expected {FORMAT_VERSION}")
    except FileNotFoundError:
        return _empty(f"{path}: not found; run `boardwatch sponsors build`")
    except (OSError, ValueError, ValidationError) as exc:
        return _empty(f"{path}: {exc}")

    exclusions_path = config_dir / EXCLUSIONS_FILENAME
    try:
        exclusions = _parse_exclusions(exclusions_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        exclusions = frozenset()
    except (OSError, UnicodeDecodeError) as exc:
        return _empty(f"{exclusions_path}: {exc}")
    return SponsorIndex(records=dict(loaded.employers), exclusions=exclusions, problem=None)


def _parse_exclusions(text: str) -> frozenset[str]:
    names = (line.split("#", 1)[0].strip() for line in text.splitlines())
    return frozenset(normalize_employer(name) for name in names if name)


def _empty(problem: str) -> SponsorIndex:
    return SponsorIndex(records={}, exclusions=frozenset(), problem=problem)
