"""The employer's JD cut out of a job-apps LinkedIn page capture (`jobapps.slice_linkedin_page`).

The three page fixtures are live captures from job-apps' tree (2026-09-26), trimmed: the site
nav, the forms and the footer keep their exact lines, the JD is cut to a few lines, and the job
poster's name is replaced. They are the three shapes the 16 LinkedIn captures take: a pay range
and a poster card between the header and the JD, the AI upsell with its three sign-in forms, and
neither. Each fixture is asserted HELD by the real detector before slicing, so a fixture that
drifted clean would fail here rather than make the slice tests vacuous.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.jobapps import JobAppsLane, slice_linkedin_page
from boardwatch.lanes.quality import is_employer_body

_CONSENT = (
    "By clicking Continue to join or sign in, you agree to LinkedIn’s\n"
    "User Agreement\n,\nPrivacy Policy\n, and\nCookie Policy\n.\n"
)


def _nav(company: str, title: str, place: str) -> str:
    return (
        f"{company} hiring {title} in {place} | LinkedIn\n"
        "Skip to main content\nLinkedIn\n"
        f"{title} in Houston, TX\nExpand search\n"
        "Jobs\nPeople\nLearning\nClear text\nClear text\nSign in\nJoin now\n"
        f"{title}\n{company}\n{place}\nApply\n"
    )


def _footer(company: str) -> str:
    return (
        "Show more\nShow less\nSeniority level\nEntry level\nEmployment type\nFull-time\n"
        "Job function\nInformation Technology\nIndustries\nSoftware Development\n"
        f"Referrals increase your chances of interviewing at {company} by 2x\n"
        "See who you know\nGet notified when a new job is posted.\nSet alert\n"
        "Sign in to set job alerts for “Software Engineer” roles.\n"
        "Email or phone\nPassword\nShow\nForgot password?\nSign in\nSign in with Email\nor\n"
        f"New to LinkedIn?\nJoin now\n{_CONSENT}"
        "Similar jobs\nSoftware Engineer - Java\nPayPal\nSan Jose, CA\n2 weeks ago\n"
        "People also viewed\nLinkedIn\n© 2026\nAbout\nLanguage\n"
        f"Agree & Join LinkedIn\n{_CONSENT}"
    )


# BeaconFire's shape: a pay range and the poster's card between the header and the JD.
PAY_AND_POSTER_JD = (
    "BeaconFire is based in Central NJ, specializing in Software Development.\n"
    "Jr. Java Developer\n"
    "Location: California/NJ\n"
    "Job Responsibilities:\n"
    "● Develop applications using Java 8/JEE (and higher), Angular 2+, React.js, SQL.\n"
    "Requirement:\n"
    "● Experience in a programming language Java and JavaScript\n"
    "Preferred Qualifications:\n"
    "● 0-1 year of practical experience in Java coding\n"
)
PAY_AND_POSTER_PAGE = (
    _nav("BeaconFire Inc.", "Junior Java Developer", "California, United States")
    + "Junior Java Developer\nBeaconFire Inc.\nCalifornia, United States\n1 day ago\n"
    "Over 200 applicants\nSee who BeaconFire Inc. has hired for this role\nApply\nSave\n"
    "Report this job\n"
    "BeaconFire Inc. provided pay range\n"
    "This range is provided by BeaconFire Inc.. Your actual pay will be based on your skills and "
    "experience — talk with your recruiter to learn more.\n"
    "Base pay range\n"
    "$60,000.00/yr - $80,000.00/yr\n"
    "Direct message the job poster from BeaconFire Inc.\n"
    "Jane D.\nJane D.\nTechnical Sourcer\n"
    + PAY_AND_POSTER_JD
    + _footer("BeaconFire Inc.")
)


def _form(purpose: str) -> str:
    return (
        f"Sign in to {purpose}\nEmail or phone\nPassword\nShow\nForgot password?\nSign in\n"
        f"Join with email\nor\nAlready on LinkedIn?\nSign in\n{_CONSENT}"
    )


# Emonics' shape: the AI upsell and its three sign-in forms between the header and the JD.
AI_UPSELL_JD = (
    "Job Overview:\n"
    "We are looking for an Entry Level Software Engineer to design, develop, and maintain "
    "scalable applications.\n"
    "Responsibilities:\n"
    "Write clean and efficient code\n"
    "Requirements:\n"
    "Degree in Computer Science or related field\n"
)
AI_UPSELL_PAGE = (
    _nav("Emonics LLC", "Software Engineer", "Austin, TX")
    + "Software Engineer\nEmonics LLC\nAustin, TX\n1 hour ago\n80 applicants\n"
    "See who Emonics LLC has hired for this role\nApply\nSave\nReport this job\n"
    "Use AI to assess how you fit\n"
    "Get AI-powered advice on this job and more exclusive features.\n"
    "Am I a good fit for this job?\n"
    "Tailor my resume\n"
    + _form("access AI-powered advices")
    + _form("evaluate your skills")
    + _form("tailor your resume")
    + AI_UPSELL_JD
    + _footer("Emonics LLC")
)

# Virtusa's shape: the join form sits ABOVE "Report this job", and the JD follows it directly.
PLAIN_JD = (
    "Role\nIOS Developer\nResponsibilities\n"
    "Design and build application iOS platform.\n"
    "Required Skills\n"
    "Well versed in Swift UI, Swift and Cocoa touch\n"
)
PLAIN_PAGE = (
    _nav("Virtusa", "iOS Developer", "Pittsburgh, PA")
    + "Join or sign in to find your next job\nJoin to apply for the\niOS Developer\nrole at\n"
    "Virtusa\nEmail or phone\nPassword\nShow\nForgot password?\nSign in\nSign in with Email\n"
    f"or\nNew to LinkedIn?\nJoin now\n{_CONSENT}"
    "iOS Developer\nVirtusa\nPittsburgh, PA\n15 hours ago\n50 applicants\nSave\n"
    "Report this job\n" + PLAIN_JD + _footer("Virtusa")
)

PAGES = [
    pytest.param(PAY_AND_POSTER_PAGE, PAY_AND_POSTER_JD, id="pay-range-and-poster"),
    pytest.param(AI_UPSELL_PAGE, AI_UPSELL_JD, id="ai-upsell-three-forms"),
    pytest.param(PLAIN_PAGE, PLAIN_JD, id="plain"),
]


@pytest.mark.parametrize(("page", "jd"), PAGES)
def test_every_fixture_page_is_held_by_the_real_detector(page: str, jd: str) -> None:
    """The precondition the slice exists for: the capture as job-apps stores it is held, and
    the JD inside it is not."""
    assert not is_employer_body(page)
    assert is_employer_body(jd)


@pytest.mark.parametrize(("page", "jd"), PAGES)
def test_the_slice_is_exactly_the_employers_jd(page: str, jd: str) -> None:
    """Exact equality, so each preamble block and the end anchor are pinned. Catches: the start
    one line off, a pay range, poster card or AI upsell left in (or only its FIRST form
    skipped), and the cut made at "Seniority level" instead of before "Show more"."""
    assert slice_linkedin_page(page) == jd


@pytest.mark.parametrize(
    ("broken", "why"),
    [
        (PLAIN_PAGE.replace("Report this job\n", ""), "no start anchor"),
        (PLAIN_PAGE.replace("Report this job\n", "Report this job\nReport this job\n"), "two"),
        (PLAIN_PAGE.replace("Show less\nSeniority level\n", "Seniority level\n"), "no end anchor"),
        (PLAIN_PAGE.replace(" | LinkedIn\n", "\n", 1), "not a LinkedIn page title"),
        (PAY_AND_POSTER_PAGE.replace("Base pay range\n", ""), "pay block out of shape"),
        (PAY_AND_POSTER_PAGE.replace("Jane D.\nJane D.\n", "Jane D.\n"), "poster card out of shape"),
        (AI_UPSELL_PAGE.replace("Cookie Policy\n", "Cookies\n"), "a form with no consent"),
        (PLAIN_PAGE.replace(PLAIN_JD, ""), "nothing between the anchors"),
    ],
    ids=lambda value: value if len(value) < 40 else "",
)
def test_a_page_out_of_the_measured_shape_is_not_sliced(broken: str, why: str) -> None:
    """Never a guess: every way the page can leave the measured shape returns None, and the lane
    then stores the capture as it is for the quarantine to hold. Catches a slice that falls
    back to a partial cut, or to the text after a start anchor with no end."""
    assert slice_linkedin_page(broken) is None, why


# ---------------------------------------------------------------------------------------
# The lane: which records are sliced.
# ---------------------------------------------------------------------------------------

_RULE = "=" * 80


def _record(root: Path, name: str, *, acquisition: str, url: str, jd: str) -> None:
    folder = root / "LinkedIn" / name
    folder.mkdir(parents=True)
    (folder / "discovery_record.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "posting_id": f"pst_{name}",
                "primary_acquisition": acquisition,
                "cohort_date": "2026-09-26",
                "canonical": {
                    "company": "Virtusa",
                    "title": "iOS Developer",
                    "direct_url": url,
                    "location": "Pittsburgh, PA",
                },
            }
        ),
        encoding="utf-8",
    )
    (folder / "job_description.txt").write_text(
        f"Company: Virtusa\nFit: 60/100\n\n{_RULE}\nJOB DESCRIPTION\n{_RULE}\n\n{jd}",
        encoding="utf-8",
    )


def _bodies(root: Path, tmp_path: Path) -> dict[str, str]:
    fetcher = Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1))
    result = JobAppsLane(source_dir=root).collect(fetcher, lambda provider, slug: True)
    return {
        posting.provider_posting_id: posting.body_text
        for snapshot in result.snapshots
        for posting in snapshot.snapshot.postings
    }


def test_a_linkedin_records_capture_is_stored_as_the_employers_jd(tmp_path: Path) -> None:
    """Catches the slice not being wired into the lane's body read."""
    root = tmp_path / "queue"
    _record(
        root, "li", acquisition="linkedin",
        url="https://www.linkedin.com/jobs/view/4458214586", jd=PLAIN_PAGE,
    )
    assert _bodies(root, tmp_path) == {"4458214586": PLAIN_JD}


def test_a_linkedin_capture_out_of_shape_is_stored_as_it_is(tmp_path: Path) -> None:
    """The fallback at the lane: today's behaviour exactly, the whole capture, for the
    quarantine to hold. Catches a lane that drops the record or stores an empty body."""
    root = tmp_path / "queue"
    broken = PLAIN_PAGE.replace("Report this job\n", "")
    _record(
        root, "li", acquisition="linkedin",
        url="https://www.linkedin.com/jobs/view/4458214586", jd=broken,
    )
    assert _bodies(root, tmp_path) == {"4458214586": broken}


@pytest.mark.parametrize("acquisition", ["jobright", "indeed", "simplify"])
def test_a_capture_is_sliced_whatever_the_records_acquisition(
    tmp_path: Path, acquisition: str
) -> None:
    """The page's shape decides, not the acquisition: job-apps captures a LinkedIn page for
    jobright- and simplify-acquired records too (measured 2026-09-27: 8 and 2, IXL's new-grad
    role among them). Catches the slice gated back onto `linkedin` records only."""
    root = tmp_path / "queue"
    _record(
        root, "other", acquisition=acquisition,
        url="https://jobright.ai/jobs/info/6a95ed6fcabc9f6703e1b085", jd=PLAIN_PAGE,
    )
    assert list(_bodies(root, tmp_path).values()) == [PLAIN_JD]
