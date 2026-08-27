"""Proof that two same-company/title/location postings are DIFFERENT openings.

This is the design D-295 deferred: "the requisition slug in the posting's own URL, the city
named in the body, the salary band, the YOE line ... every discriminator lies OUTSIDE the
similarity number, so it is a new design and not a threshold change."

**It does not suppress anything, and it must never be wired into `core/dedup`.** D-295
falsified suppression on `company_title_location` and re-measuring on 2026-08-27 confirmed
it: on a hand-adjudicated random sample of 30 residual pairs, 20 of 30 (66.7%) were
genuinely different jobs, and on the delivered population 14 of 17 groups (82.4%) were. A
suppression built on this key deletes four real leads for every duplicate it collapses, and
the fail-safe direction for suppression is "never silently delete a real job". So this module
feeds a REPORT: `reports/leakage.py`'s candidate near-duplicate bound.

**Direction of failure.** The candidate bound is an UPPER bound on duplicate leakage, and
this module is the only thing that can make it smaller. A false positive here therefore makes
a gate easier to pass, which is the one way a gate metric must not fail. Two consequences run
through every extractor below:

1. **Absence abstains.** A discriminator with nothing stated on one side returns nothing, and
   two absent values never compare equal. Absence of evidence is not evidence of difference,
   the mirror of `posting_identity.normalized_locations`' reasoning.
2. **The test is DISJOINTNESS, not inequality.** Two postings differ only when both state
   something and the two stated sets share NOTHING. A job description that merely lists one
   extra salary figure or one extra years floor is the same opening described at more length,
   and inequality would veto it out of the bound on no evidence.

The catalog is closed. An out-of-catalog name is a typed refusal at the call site, never a
new bucket.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# Closed catalog, in report order. Adding a member means adding an extractor to `_EXTRACTORS`
# below — `test_every_catalog_member_is_answerable` fails otherwise, which is the same shape
# as `core/dedup.MissingSuppressionResolver`: a catalog entry with no implementation would
# abstain forever and nobody would notice.
DISCRIMINATORS: tuple[str, ...] = ("requisition_slug", "salary_band", "experience_years")


class UnknownDiscriminator(ValueError):
    """Raised at the call site for a discriminator outside the closed catalog."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown near-duplicate discriminator: {name!r}")
        self.name = name


@dataclass(frozen=True)
class PostingEvidence:
    """The columns a discriminator reads.

    Deliberately NOT `core.posting_identity.IdentityInputs`: that type feeds the suppression
    path, and keeping the two apart is what stops this module from being wired into
    `resolve_duplicates` by a later convenience refactor.
    """

    posting_id: int
    url: str | None
    body_text: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: str | None


# --- requisition_slug -----------------------------------------------------------------

# Ported from job-apps' `autoapply/job_identity.py`, which keys on the board's own posting id
# and falls back to a light URL normalization. What transfers here is the opposite half: the
# HUMAN-READABLE part of the last path segment, which is the posting's own description of
# itself and is frequently more specific than `postings.title`. D-295's Capital One case is
# the canonical one — two postings share the title `Lead Software Engineer` in McLean while
# one URL says `Lead-Software-Engineer--Front-End`.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_SLUG_SPLIT = re.compile(r"[\W_]+")


def _requisition_slug(evidence: PostingEvidence) -> frozenset[str]:
    """At most one slug, or nothing when the URL carries no title.

    Words containing a digit are dropped, and that is load-bearing rather than tidiness:
    `postings` enforces `UNIQUE(company_id, provider_posting_id)`, so every posting in a
    candidate group carries a different requisition id BY CONSTRUCTION. If the req id leaked
    into the slug, this discriminator would fire on every pair and silently empty the bound.

    A UUID is rejected explicitly. Its hex chunks split into words, and a chunk that happens
    to hold no digit would otherwise read as a title word — two Lever postings would look
    like two different roles. Fewer than two surviving words is not a title either: it is
    `job`, `search`, or a bare numeric Greenhouse id.
    """
    url = (evidence.url or "").strip()
    if not url:
        return frozenset()
    segment = re.sub(r"[?#].*$", "", url).rstrip("/").rsplit("/", 1)[-1]
    if not segment or _UUID.match(segment):
        return frozenset()
    words = [w.lower() for w in _SLUG_SPLIT.split(segment) if w and not any(c.isdigit() for c in w)]
    if len(words) < 2:
        return frozenset()
    return frozenset({" ".join(words)})


# --- salary_band ----------------------------------------------------------------------

# `$120,000`, `$120,000.00`, `$120K`, `$120.5k`. Bare numbers are not read as pay: a body is
# full of years, counts and version numbers, and a currency symbol is what makes a figure a
# claim about compensation.
#
# The optional second half is the top of a range, and its `$` is optional because plenty of
# postings write one symbol for two figures — Intel's `$122,440.00-172,860.00 USD` is the
# measured case. Dropping the top of a band only ever makes the extracted set SMALLER, which
# makes two sets MORE likely to look disjoint, which shrinks the bound on no evidence.
#
# A leading `$` is still required, and that leaves a known gap: Affirm writes `CAN base pay
# range per year: 181,000 - 241,000` with no symbol anywhere, so both sides extract nothing
# and the pair stays in the bound even though its two bands are disjoint. That gap is left
# open deliberately. Closing it needs a context cue ("pay range", "salary"), which is new
# precision risk, and the gap fails in the safe direction: it can only leave a distinct pair
# INSIDE the bound, never take a duplicate out of it.
_FIGURE = r"\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{2,4}(?:\.\d+)?\s?[kK]\b"
_MONEY = re.compile(rf"\$\s?({_FIGURE})(?:\s*(?:[-–—]|to)\s*\$?\s?({_FIGURE}))?")
_PAY_FLOOR = 20_000
_PAY_CEILING = 2_000_000


def _body_pay_figures(body_text: str) -> frozenset[int]:
    out: set[int] = set()
    for match in _MONEY.finditer(body_text):
        for group in match.groups():
            if group is None:
                continue
            raw = group.replace(",", "").strip().lower()
            value = int(float(raw[:-1].strip()) * 1000) if raw.endswith("k") else int(float(raw))
            if _PAY_FLOOR <= value <= _PAY_CEILING:
                out.add(value)
    return frozenset(out)


def _salary_band(evidence: PostingEvidence) -> frozenset[object]:
    """The structured band when the provider gave one, else the figures stated in the body.

    The two sources are never mixed. A structured `(min, max)` and a set of body figures are
    different kinds of claim, and comparing them would make "structured on one side only"
    look like a disagreement. When only one side has a structured band, both sides fall back
    to the body — and if that leaves one side empty, the discriminator abstains.

    Currency and period are part of the band because 120,000 CAD is not 120,000 USD, and an
    annual band is not an hourly one.
    """
    if evidence.salary_min is None and evidence.salary_max is None:
        return frozenset(_body_pay_figures(evidence.body_text))
    return frozenset(
        {
            (
                None if evidence.salary_min is None else str(evidence.salary_min),
                None if evidence.salary_max is None else str(evidence.salary_max),
                (evidence.salary_currency or "").lower(),
                (evidence.salary_period or "").lower(),
            )
        }
    )


def _has_structured_band(evidence: PostingEvidence) -> bool:
    return evidence.salary_min is not None or evidence.salary_max is not None


# --- experience_years -----------------------------------------------------------------

# A years figure counts only when `experience` follows it closely. `eligibility/rules.yaml`
# solves a harder problem — whether a floor is REQUIRED, with hedge and idiom suppression —
# and is not reused here: this asks only what the posting states, the eligibility engine is
# not on `core`'s import path, and a requirement-grade extractor would abstain on hedged
# text, which for a bound is the wrong direction.
_YEARS = re.compile(
    r"(?<![\d.\-])(\d{1,2})\s*\+?\s*(?:[-–—]|to)?\s*\d{0,2}\s*\+?\s*years?\b[^.;:\n]{0,40}?"
    r"\bexperience\b",
    re.IGNORECASE,
)
_YEARS_CEILING = 40


def _experience_years(evidence: PostingEvidence) -> frozenset[int]:
    return frozenset(
        value
        for value in (int(m.group(1)) for m in _YEARS.finditer(evidence.body_text))
        if 0 < value <= _YEARS_CEILING
    )


# --- the catalog ----------------------------------------------------------------------

_EXTRACTORS = {
    "requisition_slug": _requisition_slug,
    "salary_band": _salary_band,
    "experience_years": _experience_years,
}


def discriminator_evidence(name: str, evidence: PostingEvidence) -> frozenset[object]:
    """Everything one posting states under one discriminator. Empty means "says nothing"."""
    try:
        extractor = _EXTRACTORS[name]
    except KeyError:
        raise UnknownDiscriminator(name) from None
    return frozenset(extractor(evidence))


def distinguishing_evidence(a: PostingEvidence, b: PostingEvidence) -> tuple[str, ...]:
    """The discriminators that PROVE `a` and `b` are different openings, in catalog order.

    Empty means "no proof", which is not the same as "duplicate" — it is the abstain that
    keeps the pair inside the candidate bound.
    """
    proven: list[str] = []
    for name in DISCRIMINATORS:
        left: frozenset[object]
        right: frozenset[object]
        if name == "salary_band" and _has_structured_band(a) != _has_structured_band(b):
            # One provider published a band and the other did not. Falling back to body
            # figures on both sides keeps the comparison like-for-like.
            left = frozenset(_body_pay_figures(a.body_text))
            right = frozenset(_body_pay_figures(b.body_text))
        else:
            left = discriminator_evidence(name, a)
            right = discriminator_evidence(name, b)
        if left and right and not (left & right):
            proven.append(name)
    return tuple(proven)
