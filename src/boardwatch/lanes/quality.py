"""Body quality controls for JD acquisition (design §4.5).

A lane pays one request per posting for a body, so the thing it must not do is bank a
response that arrived. The prior art's failure is the specification here inverted: job-apps'
browser tier stored whatever came back, so a login interstitial and a real JD were the same
row, and eleven scheduled runs "recovered" bodies that were sign-in pages.

Every verdict here maps onto an outcome ALREADY in `lanes.outcomes.AcquisitionOutcome`. That
catalog is closed and `AcquisitionTally.record` raises off it, so a control that wanted a name
of its own would be a control that cannot be counted.

BOTH markers catalogs are matched WORD-BOUNDED, not by substring, and that is not tidiness:
"design intent" contains "sign in", so a substring test flags the login wall on a JD that
happens to describe design work. The alternation is `(?:...)`-grouped for the same reason
`rank/location_gate` groups its own — `|` binds looser than concatenation, so an ungrouped
body applies the leading `\\b` to the first token only and every token between the ends
matches unbounded.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from boardwatch.core.html_text import html_to_text
from boardwatch.extract.role_family import classify_role_family
from boardwatch.lanes.outcomes import AcquisitionOutcome

# The floor a body must clear to be worth storing. Three independent measures rather than one:
# a login page is short, a cookie banner is long but structureless, and a one-paragraph teaser
# is long and structured but is not a JD. Any single threshold passes two of those three.
MIN_BODY_CHARS = 500
MIN_SECTION_MARKERS = 1
MIN_BODY_LINES = 8

# Two distinct wall markers are required, and this is the whole reason the test is two-sided:
# nearly every real posting page carries a "Sign in" in its chrome, so a one-sided test rejects
# the corpus.
MIN_WALL_MARKERS = 2

# Headings a real job description carries. Closed catalog: a body that matches none of these is
# reported as below the floor, never as a new kind of body.
_SECTION_MARKERS: tuple[str, ...] = (
    "responsibilities",
    "qualifications",
    "requirements",
    "what you'll do",
    "what you will do",
    "who you are",
    "about the role",
    "about this role",
    "about the job",
    "job description",
    "essential functions",
    "duties",
    "required skills",
    "preferred skills",
    "what we offer",
    "benefits",
    "compensation",
)

_WALL_MARKERS: tuple[str, ...] = (
    "sign in",
    "log in",
    "login",
    "sign up",
    "create an account",
    "create your account",
    "you must be logged in",
    "session expired",
    "access denied",
    "enable javascript",
    "enable cookies",
    "captcha",
    "verify you are human",
    "unusual traffic",
    "forgot your password",
)

# A body heading longer than this is a sentence, not a title. Used only by
# `role_body_mismatch`, which needs the body's own declared role and reads it off the heading
# the JD endpoint returns first (the contract records the body is shaped `"<H1>..."`).
_MAX_DECLARED_TITLE_CHARS = 120

# The classifier's fallback, returned for any title it recognizes nothing in. Named rather than
# spelled inline at the one comparison that matters — see `role_body_mismatch`.
_UNSPECIFIC_ROLE_FAMILY = "general_swe"


def _alternation(markers: tuple[str, ...]) -> re.Pattern[str]:
    body = "|".join(re.escape(marker) for marker in sorted(markers, key=len, reverse=True))
    return re.compile(rf"\b(?:{body})\b", re.IGNORECASE)


_SECTION_RE = _alternation(_SECTION_MARKERS)
_WALL_RE = _alternation(_WALL_MARKERS)

# selectolax decodes entities, so a JD written with a typographic apostrophe reaches us as
# "what you’ll do" and matches no catalog entry — which reads as "no section markers", the
# exact input that turns a real JD into a login wall. Folded before matching, not spelled as a
# second entry per marker.
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "´": "'"})


def _normalized(text: str) -> str:
    return text.translate(_APOSTROPHES)


@dataclass(frozen=True)
class BodyRejection:
    """Why a body was refused, in the vocabulary the tally already counts."""

    outcome: AcquisitionOutcome
    reason: str


def count_section_markers(text: str) -> int:
    """DISTINCT section markers present. Occurrences would let one repeated heading pass."""
    return len({match.group(0).casefold() for match in _SECTION_RE.finditer(_normalized(text))})


def count_wall_markers(text: str) -> int:
    return len({match.group(0).casefold() for match in _WALL_RE.finditer(_normalized(text))})


def is_login_wall(text: str) -> bool:
    """The two-sided test: several wall markers AND no sign of a real JD.

    Deliberately not "any wall marker": a footer "Sign in" sits on the real body of most
    postings, so the one-sided form rejects almost the whole corpus.
    """
    return count_wall_markers(text) >= MIN_WALL_MARKERS and count_section_markers(text) == 0


def meets_body_floor(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    return (
        len(text) >= MIN_BODY_CHARS
        and count_section_markers(text) >= MIN_SECTION_MARKERS
        and len(lines) >= MIN_BODY_LINES
    )


def declared_role_line(text: str) -> str | None:
    """The body's own heading, when it has one that could be a title.

    None when the first non-blank line is too long to be a heading. A JD that opens with a
    paragraph declares no role, and reading a role family out of prose would classify on
    whichever family's vocabulary the sentence happened to use first.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return stripped if len(stripped) <= _MAX_DECLARED_TITLE_CHARS else None
    return None


def declared_role_family(text: str) -> str | None:
    """The role family the body itself declares, or None when it declares nothing usable."""
    declared = declared_role_line(text)
    if declared is None:
        return None
    family = classify_role_family(declared)
    return None if family == _UNSPECIFIC_ROLE_FAMILY else family


def role_body_mismatch(title: str, text: str) -> bool:
    """The body declares a role family, and it is not the listed title's.

    Two-sided, in the same spirit as the login-wall test, and the second side is what keeps
    this control from eating the corpus: `classify_role_family` returns `general_swe` for
    anything it recognizes nothing in, so a heading that is really the employer's name would
    otherwise "disagree" with every specific title. A mismatch is only asserted when BOTH
    sides resolve to a SPECIFIC family and those families differ.

    What this actually guards is body/listing misattribution — an aggregator serving the wrong
    JD for a listing. That is the failure the `objectID` tail would cause if the id were ever
    decomposed instead of used opaquely, so the check is worth its cost even at this precision.
    """
    body_family = declared_role_family(text)
    title_family = classify_role_family(title)
    if body_family is None or title_family == _UNSPECIFIC_ROLE_FAMILY:
        return False
    return title_family != body_family


def assess_body(html: str, *, title: str) -> tuple[str, BodyRejection | None]:
    """Extract `html` and judge it. Returns the extracted text and a rejection, or None.

    The order is the diagnostic: the login-wall test runs BEFORE the floor because a wall is
    also short and structureless, so the floor would absorb it and report the interstitial as
    a thin JD — losing exactly the distinction §4.5 exists to make.
    """
    text = html_to_text(html)
    if not text.strip():
        return text, BodyRejection("extracted_empty", "extraction produced no text")
    if is_login_wall(text):
        return text, BodyRejection(
            "rejected_login_wall",
            f"{count_wall_markers(text)} wall markers and no JD section marker",
        )
    if not meets_body_floor(text):
        lines = len([line for line in text.splitlines() if line.strip()])
        return text, BodyRejection(
            "rejected_quality_gate",
            f"below the floor: {len(text)} chars, "
            f"{count_section_markers(text)} section markers, {lines} lines",
        )
    if role_body_mismatch(title, text):
        return text, BodyRejection(
            "rejected_quality_gate",
            f"body declares role family {declared_role_family(text)!r}, "
            f"listing title declares {classify_role_family(title)!r}",
        )
    return text, None


# ---------------------------------------------------------------------------
# The lane-body ingest precondition (D-406): a body must be the EMPLOYER's own text.
# ---------------------------------------------------------------------------
#
# The controls above ask whether a body is a usable job description. This one asks a
# different question that none of them can answer: WHOSE text is it. job-apps' jobright
# records store jobright's rendered PAGE, not the employer's JD — the page title, the site
# nav, and jobright's own derived label `H1B Sponsor Likely` all sit inside what boardwatch
# then freezes as the JD. Every control above passes such a body: it is long, it is
# structured, it carries `Responsibilities` and `Qualification`, and its declared role family
# matches the listing. It is simply not the employer speaking.
#
# Why that matters is specific and is the whole reason this exists. `work_auth` is a BLOCKER
# family, and `INELIGIBLE` must carry a quoted span from the frozen JD. An
# `ineligible(work_auth)` quoting `H1B Sponsor Likely` would present a third party's GUESS as
# the employer's stated requirement — a keystone-invariant violation with a real span behind
# it, which is the one failure mode the evidence chain cannot detect after the fact.
#
# CLOSED and VERSIONED. A body carrying an aggregator phrase this catalog does not know is
# reported as passing, never as a new kind of foreignness; widening the catalog is an edit here.
# The version below is audit metadata a human may bump. What actually re-reaches every stored
# body is the fingerprint (`catalog_fingerprint`, which moves on any marker edit) keying the
# corpus re-sweep, and the drain re-running this current detector against each held body.

FOREIGN_BODY_CATALOG_VERSION = 1

# Page furniture and derived labels that only an aggregator's own UI emits. Every member is
# measured against the live corpus (2026-09-01), not imagined: the first five are jobright's
# chrome and CTAs, the sixth is its own sponsorship verdict, and the last two are LinkedIn's
# signed-out interstitial. An employer writing its own JD emits none of them.
_FOREIGN_BODY_MARKERS: tuple[str, ...] = (
    "apply on employer site",
    "sign in join now",
    "apply with autofill",
    "improve resume match score",
    "boost your interview chances",
    "h1b sponsor likely",
    "join or sign in to find your next job",
    "agree & join linkedin",
)

# A CONSERVATIVE POLICY, and — stated plainly because the first version of this comment got it
# wrong — NOT a measured discriminator. Over the live corpus on 2026-09-01 the distribution is
# bimodal with nothing in between: 139,713 bodies match ZERO markers, nine match five or six,
# and **not one body anywhere in the corpus matches exactly one**. So no live posting is
# currently decided by this threshold, and lowering it to 1 would change no verdict today.
#
# What the earlier comment claimed as justification was a different fact about a different
# question. The bare token `Jobright` appears in 50 bodies, 41 of them postings for the
# employer *Jobright.ai itself*, and `| LinkedIn` in 13 BlackRock Workday bodies that link
# their own social accounts — which is why NEITHER token is in the catalog above. It argues for
# EXCLUDING those two strings, not for requiring two of the eight that ARE catalogued.
#
# The threshold is kept anyway, as headroom rather than as evidence: every catalogued phrase is
# an aggregator's UI string today, but a future marker could plausibly appear once inside a long
# employer JD, and a second independent marker is cheap insurance against that. Because no real
# body sits at exactly one marker, the guard for this threshold necessarily uses a SYNTHETIC
# fixture (a real employer body with one marker appended) — recorded so nobody later mistakes
# that fixture for a measured case.
MIN_FOREIGN_MARKERS = 2


class ForeignBodyText(ValueError):
    """A body that is not the employer's own text, raised at the site that detects it.

    Typed, and carrying the markers as DATA. Nothing downstream may re-derive what happened by
    string-matching this message — the detector is necessarily textual, the classification is
    not.
    """

    def __init__(self, markers: tuple[str, ...]) -> None:
        super().__init__(f"body is an aggregator's page text, not the employer's: {markers}")
        self.markers = markers
        self.catalog_version = FOREIGN_BODY_CATALOG_VERSION


def foreign_body_markers(text: str) -> tuple[str, ...]:
    """The DISTINCT aggregator markers this body carries, sorted. Empty for employer text.

    Substring rather than word-bounded, unlike the two catalogs above, and the reason is the
    inverse of theirs: every member here is a multi-word phrase from a specific site's chrome,
    so there is no short token for a longer word to swallow. Case- and whitespace-folded,
    because the same phrase reaches us across a line break from one lane and inline from
    another.
    """
    folded = " ".join(_normalized(text).casefold().split())
    return tuple(marker for marker in _FOREIGN_BODY_MARKERS if marker in folded)


def catalog_fingerprint() -> str:
    """A digest of the catalog AND the threshold — the EXECUTABLE identity of this detector.

    `FOREIGN_BODY_CATALOG_VERSION` is a human-facing label and a human can forget to bump it.
    This cannot be forgotten: it is computed from the markers themselves, so adding, removing or
    editing one changes it whether or not anybody touched the version. `body_precondition_checks`
    stores THIS, which is what makes a catalog edit re-check every stored body instead of leaving
    them governed by the semantics of whatever catalog happened to run first.
    """
    material = "\u0000".join((str(MIN_FOREIGN_MARKERS), *sorted(_FOREIGN_BODY_MARKERS)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def is_employer_body(text: str) -> bool:
    """Does this body satisfy the precondition — is it the employer's own text?"""
    return len(foreign_body_markers(text)) < MIN_FOREIGN_MARKERS


def require_employer_body(text: str) -> None:
    """Raise `ForeignBodyText` unless the body is the employer's own text."""
    markers = foreign_body_markers(text)
    if len(markers) >= MIN_FOREIGN_MARKERS:
        raise ForeignBodyText(markers)
