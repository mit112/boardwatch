"""An AUTHORED LinkedIn guest search payload, built to the structure D-290 recorded.

NOT A CAPTURE, and that is a ruling rather than a convenience (D-285/D-290). No employer name, no
job-description text, and no card HTML below is copied from LinkedIn: the SHAPES are the recorded
ones, every string arranged in them is invented. Committing a capture would oblige a `provenance`
whose only honest value (`public`) obliges a `license`, and there is no license for a third party's
posting text in a public repository. `synthetic` would be a lie.

THE OPPOSITE TRAP, AND HOW THIS FILE AVOIDS IT. An authored fixture proves only what our own code
constructs -- that is how a round-trip test passed against an invented shape, and how five of six
providers passed a dereference rule that was wrong. Two independent traps guard against it, and
neither can pass a fixture of merely well-formed cards:

  * `URN_URL_MISMATCH_CARD` gives a card whose job-view URL ends in a DIFFERENT number than its
    `data-entity-urn`. A client that read the id off the URL tail would key the posting wrong; the
    test asserts the id is the URN's. D-290: 0 opaque URNs -- the id is the URN, not the link.
  * `NAME_COLLISION_CARDS` gives two cards sharing one display NAME under two different company
    slugs. A client that grouped by name would collapse two employers into one; the test asserts
    two groups. D-290: company is a plain string PLUS a stable slug, and the slug is the key.

DRIFT. `REVIEW_BY` is the date somebody must re-confirm the §2 field list and §2 selectors against
the live guest search (contract §2's reconstructed-selectors caveat). It is a review deadline, not a
freshness claim; the drain is a dated edit to `REVIEW_BY` with the reason recorded beside it. R13's
pinned-fixture-dir rule does not apply -- a lane is not a registered provider.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

# The probe session (D-290). PROBED + 90, matching the window the six ATS captures use.
PROBED = date(2026, 8, 23)
REVIEW_BY = date(2026, 11, 21)

# Contract §1: the only two request shapes, and the one filter parameter that is evidenced.
SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?f_TPR=r86400"
)
JOB_POSTING_PREFIX = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"


@dataclass(frozen=True)
class Card:
    """One search-result card, in the fields D-290 recorded as 100/100 complete."""

    job_id: str
    title: str
    company_name: str
    company_slug: str
    location: str
    posted_date: str  # ISO YYYY-MM-DD, the `time[datetime]` attribute
    # The numeric tail of the job-view URL. Defaults to `job_id`, as it does on a real card; a test
    # sets it different to prove the id is read from the URN, never the URL.
    url_tail: str | None = None
    # Query/trailing-slash noise on the `/company/{slug}` href, present on a real card. The client
    # must recover the bare slug regardless.
    company_href_suffix: str = "/?trk=public_jobs_topcard-org-name"


def _title_slug(title: str) -> str:
    return "-".join(title.lower().split())


def view_url(card: Card) -> str:
    """The job-view URL -- the ONLY URL a card exposes (contract §2: `externalApply` = 0)."""
    tail = card.url_tail if card.url_tail is not None else card.job_id
    return (
        f"https://www.linkedin.com/jobs/view/"
        f"{_title_slug(card.title)}-at-{card.company_slug}-{tail}"
        "?refId=aB3&trackingId=xY9"
    )


def company_href(card: Card) -> str:
    return f"https://www.linkedin.com/company/{card.company_slug}{card.company_href_suffix}"


def card_html(card: Card) -> str:
    """One card in the recorded shape: a `<li>` wrapping a `div.base-card[data-entity-urn]`."""
    return (
        "<li>"
        '<div class="base-card relative w-full" '
        f'data-entity-urn="urn:li:jobPosting:{card.job_id}">'
        f'<a class="base-card__full-link" href="{view_url(card)}"></a>'
        f'<h3 class="base-search-card__title">{card.title}</h3>'
        '<h4 class="base-search-card__subtitle">'
        f'<a class="hidden-nested-link" href="{company_href(card)}">{card.company_name}</a>'
        "</h4>"
        f'<span class="job-search-card__location">{card.location}</span>'
        f'<time class="job-search-card__listdate" datetime="{card.posted_date}">'
        f"{card.posted_date}</time>"
        "</div></li>"
    )


def search_page_html(cards: list[Card] | None = None, *, extra_li: str = "") -> str:
    """The guest `seeMore` fragment: a sequence of `<li>` cards, no envelope."""
    rows = "".join(card_html(card) for card in (search_cards() if cards is None else cards))
    return f"<ul class='jobs-search__results-list'>{rows}{extra_li}</ul>"


def job_description_body(title: str, employer: str) -> str:
    """A JD body in the recorded shape: a heading, real section headings, a footer sign-in.

    The footer `Sign in` is load-bearing, not decoration: nearly every real posting page carries
    one, so a one-sided login-wall test would reject the whole corpus. This fixture makes that
    regression fail rather than pass.
    """
    return (
        f"<h1>{title}</h1>"
        f"<p>{employer} is hiring a {title.lower()} to join a small team that ships weekly. "
        "This role is open to applicants already able to work in the United States, and the team "
        "is on site four days a week.</p>"
        "<h2>Responsibilities</h2>"
        "<ul>"
        "<li>Own a service end to end, from design through operation.</li>"
        "<li>Review your teammates' changes and keep the build green.</li>"
        "<li>Write down what you learned so the next person does not relearn it.</li>"
        "<li>Answer the on-call pager one week in six.</li>"
        "</ul>"
        "<h2>Qualifications</h2>"
        "<ul>"
        "<li>Comfortable reading code you did not write.</li>"
        "<li>Some experience with a relational database.</li>"
        "<li>Able to explain a tradeoff in writing.</li>"
        "</ul>"
        "<h2>Benefits</h2>"
        "<p>Health cover from day one, a training budget, and paid time off.</p>"
    )


def job_posting_html(card: Card, *, body: str | None = None) -> str:
    """`jobPosting/{id}` -> an HTML fragment; the description in `.show-more-less-html__markup`."""
    markup = body if body is not None else job_description_body(card.title, card.company_name)
    return (
        '<section class="show-more-less-html">'
        '<div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">'
        f"{markup}"
        "</div></section>"
        '<div class="description__job-criteria-list">'
        '<h3 class="description__job-criteria-subheader">Seniority level</h3></div>'
    )


_TITLES = ("Software Engineer, New Grad", "Backend Engineer", "Data Engineer", "Platform Engineer")
_LOCATIONS = ("Seattle, WA", "Austin, TX", "New York, NY", "Remote (United States)")


def search_cards() -> list[Card]:
    """The canonical well-formed set: 4 companies, 2 postings each -- 8 cards on 4 slugs.

    Distinct ids, slugs and names throughout, so grouping, the company cap and per-posting budget
    are all exercised on a clean payload. The traps live in the dedicated fixtures below.
    """
    cards: list[Card] = []
    job_id = 4_010_000_000
    for company in range(4):
        for posting in range(2):
            job_id += 1
            cards.append(
                Card(
                    job_id=str(job_id),
                    title=_TITLES[posting % len(_TITLES)],
                    company_name=f"Acme {company:02d}",
                    company_slug=f"acme-{company:02d}",
                    location=_LOCATIONS[(company + posting) % len(_LOCATIONS)],
                    posted_date="2026-08-23",
                )
            )
    return cards


# A card whose job-view URL ends in a DIFFERENT number than its URN. The id must be the URN's.
URN_URL_MISMATCH_CARD = Card(
    job_id="4010000900",
    title="Software Engineer, New Grad",
    company_name="Beacon Labs",
    company_slug="beacon-labs",
    location="Boston, MA",
    posted_date="2026-08-23",
    url_tail="1234567",
)

# Two cards sharing one display NAME under two different slugs. They must form two groups.
NAME_COLLISION_CARDS = [
    Card("4010000910", "Backend Engineer", "Vertex", "vertex-analytics", "Denver, CO", "2026-08-23"),
    Card("4010000911", "Backend Engineer", "Vertex", "vertex-robotics", "Denver, CO", "2026-08-23"),
]


def dup_id_cards() -> list[Card]:
    """Two cards resolving to ONE (slug, job_id). The second must be dropped, not fetched.

    Without the drop the run aborts: `apply.py` snapshots `existing` once and both rows take the
    INSERT branch, so the second violates UNIQUE(company_id, provider_posting_id) inside
    `apply_board`'s single transaction and rolls the whole board back. An aggregator MAY serve one
    posting twice; every ATS provider enumerates a board once and may assume distinct ids.
    """
    first = replace(search_cards()[0])
    return [first, replace(first, title="Backend Engineer")]  # same slug + job_id, different title


def card_html_missing_urn(card: Card) -> str:
    """A card with no `data-entity-urn`. Seen, uncountable to an id -> not_attemptable."""
    return card_html(card).replace(f' data-entity-urn="urn:li:jobPosting:{card.job_id}"', "")


def card_html_missing_title(card: Card) -> str:
    return card_html(card).replace(
        f'<h3 class="base-search-card__title">{card.title}</h3>', ""
    )


def card_html_missing_company(card: Card) -> str:
    """A card with no company anchor: no slug, so no company to key on -> not_attemptable."""
    start = card_html(card).index('<h4 class="base-search-card__subtitle">')
    end = card_html(card).index("</h4>") + len("</h4>")
    html = card_html(card)
    return html[:start] + html[end:]
