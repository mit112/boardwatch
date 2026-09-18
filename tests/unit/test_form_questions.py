"""The Greenhouse application form's hard stops (`delivery/form_questions`).

**Every question string, option label and EEO block in this module was copied VERBATIM from a
live `boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}?questions=true` payload on 2026-09-17**
— tenet3/8810809002, relativity/8726261002 and giftogram/4392576009, the three apply-lane leads a
hand pre-flight withdrew for a requirement that appears nowhere in the JD boardwatch evaluates.
The curly quotes, the `U. S.` with a space after the period, the `&ldquo;` entities and the double
space in the giftogram label are all real, and they are the whole reason the catalog's patterns
look the way they do. Do not tidy them.

GREENHOUSE-ONLY BY CONSTRUCTION: Ashby's posting API and Lever's do not expose the application
form at all, so no other provider can be reached this way.
"""

from __future__ import annotations

import json

import pytest

from boardwatch.core.politeness import FetchFailure
from boardwatch.delivery.form_questions import (
    CATALOG,
    FormQuestion,
    QuestionsUnreadable,
    fetch_questions,
    match_questions,
    parse_questions,
    questions_url,
)

# --- the three verified hard stops -----------------------------------------------------------

#: tenet3 / 8810809002. Note `U. S.` — a space after each period — which is why the catalog's
#: citizenship surface needs `U\.?\s?S\.?` in its "requires ... citizenship" alternative.
TENET3 = FormQuestion(
    label=(
        "This position requires current U. S. citizenship in order to achieve and maintain a "
        "security clearance. Are you currently a U. S. citizen?"
    ),
    description=(
        "<p>The National Industrial Security Program Operating Manual, section 2-209, indicates "
        "that Non-U.S. citizens are not eligible for security clearances in nearly all "
        "situations and are not eligible for access to Top Secret information under any "
        "circumstances.</p>"
    ),
    options=("Yes", "No"),
)

#: relativity / 8726261002. The hard stop is in the DESCRIPTION, not the label — the label is the
#: two words "EXPORT COMPLIANCE" — which is why the matched text has to include the description.
RELATIVITY = FormQuestion(
    label="EXPORT COMPLIANCE",
    description=(
        "<p><!--StartFragment-->As defined in the ITAR, &ldquo;U.S. Persons&rdquo; include U.S. "
        "citizens, lawful permanent residents (i.e., Green Card holders), and certain protected "
        "individuals (e.g., refugees/asylees, American Samoans). Please consult with a "
        "knowledgeable advisor if you are unsure whether you are a &ldquo;U.S. "
        "Person.&rdquo;<br><br>The person hired will have access to information and items "
        "controlled by the International Traffic in Arms Regulation (ITAR), and, therefore, must "
        "either be a &ldquo;U.S. person&rdquo; as defined by those regulations or otherwise "
        "eligible for a federally issued export control license. To assist Relativity in "
        "assessing its export compliance obligations in relation to your application, please "
        "identify which statement best applies to you:<!--EndFragment--></p>"
    ),
    options=("I am currently a “U.S. Person”", 'I am not a “U.S. Person"'),
)

#: giftogram / 4392576009. Two spaces before `~3`, verbatim.
GIFTOGRAM = FormQuestion(
    label=(
        "Are you a US Citizen or Green Card Holder that can work onsite in Whippany NJ  ~3 days "
        "per week"
    ),
    description=None,
    options=("Yes", "No"),
)

#: Greenhouse's own `compliance[].type == "eeoc"` blocks, verbatim from the tenet3 payload. They
#: arrive HTML-ESCAPED (`&lt;p&gt;`), one more reason `compliance[]` is not the same input as
#: `questions[]`. The VEVRAA one is the adversarial case for the export surface: it says
#: "a veteran of the U.S. military ... or a person who was discharged" five times over.
EEO_VEVRAA = (
    "&lt;p&gt;\n  If you believe you belong to any of the categories of protected veterans "
    "listed below, please indicate by making the appropriate selection.\n  As a government "
    "contractor subject to the Vietnam Era Veterans&#39; Readjustment Assistance Act (VEVRAA), "
    "we request this information in order to measure\n  the effectiveness of the outreach and "
    "positive recruitment efforts we undertake pursuant to VEVRAA. Classification of protected "
    "categories\n  is as follows:\n&lt;/p&gt;\n&lt;p&gt;A &quot;disabled veteran&quot; is one of "
    "the following: a veteran of the U.S. military, ground, naval or air service who is entitled "
    "to compensation (or who but for the receipt of military retired pay would be entitled to "
    "compensation) under laws administered by the Secretary of Veterans Affairs; or a person who "
    "was discharged or released from active duty because of a service-connected "
    "disability.&lt;/p&gt;\n"
)

#: The EEO clause that NAMES citizenship. Not from any of the three payloads — Greenhouse's four
#: `eeoc` blocks are a fixed boilerplate set (CC-305, VEVRAA, two self-identification blocks) and
#: none of them mentions citizenship; verified on all three payloads plus stripe and databricks
#: on 2026-09-17. This is the standard equal-opportunity clause wording, which DOES, and it is
#: the string a catalog that keyed on the bare word "citizenship" would hold every lead on.
EEO_CITIZENSHIP_CLAUSE = (
    "We are an equal opportunity employer and all qualified applicants will receive "
    "consideration for employment without regard to race, color, religion, sex, national "
    "origin, citizenship status, age, disability, genetic information, protected veteran "
    "status, gender identity or sexual orientation."
)


def _payload(*questions: FormQuestion, compliance: tuple[str, ...] = ()) -> bytes:
    """The payload shape Greenhouse returns, built from these fixtures.

    Assembled here rather than checked in whole so the fixtures above stay readable as the
    strings they are; every field this module reads is present, and `compliance[]` is populated
    so the exclusion has something to exclude.
    """
    return json.dumps(
        {
            "id": 8810809002,
            "title": "Junior Frontend Software Engineer- Hybrid",
            "questions": [
                {
                    "label": q.label,
                    "description": q.description,
                    "required": True,
                    "fields": [
                        {
                            "name": "question_1",
                            "type": "multi_value_single_select",
                            "values": [
                                {"label": option, "value": index}
                                for index, option in enumerate(q.options)
                            ],
                        }
                    ],
                }
                for q in questions
            ],
            "compliance": [
                {"type": "eeoc", "description": text, "questions": []} for text in compliance
            ],
        }
    ).encode()


# --- the catalog ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "surface"),
    [
        (TENET3, "citizenship_required"),
        (RELATIVITY, "us_person_export_control"),
        (GIFTOGRAM, "citizen_or_green_card"),
    ],
    ids=["tenet3", "relativity", "giftogram"],
)
def test_each_verified_question_matches_exactly_one_catalog_surface(
    question: FormQuestion, surface: str
) -> None:
    """One question, one named surface. The catalog is CLOSED and its members do not overlap, so
    the surface that fired is a fact the lane-composition report can count rather than whichever
    pattern happened to be tried first.

    The giftogram string is what forces that: "Are you a US Citizen or Green Card Holder" satisfies
    the citizenship surface's "are you a US citizen" reading as well as its own, and a catalog that
    let both fire could not say which class the lead is in.
    """
    matched = [member.surface_id for member in CATALOG if member.pattern.search(question.text)]
    assert matched == [surface]

    hit = match_questions((question,))
    assert hit is not None
    assert hit.surface_id == surface
    assert hit.question == question.label


def test_the_citizenship_question_matches_without_the_requirement_restated() -> None:
    """The recall hole the tenet3 label HIDES, and the reason the "are you" alternative carries
    the optional space after each period too.

    tenet3 states the requirement and then asks the question, so its label matches through the
    "requires ... citizenship" alternative whatever the other one does. A form that asked only the
    question — and spelled the initials the way this employer spells them everywhere else — would
    be missed with no test failing. Found by the web-server test, which used exactly this string.
    """
    for spelling in (
        "Are you currently a U. S. citizen?",
        "Are you currently a U.S. citizen?",
        "Are you a US citizen?",
        "Are you a United States citizen?",
    ):
        hit = match_questions((FormQuestion(label=spelling, description=None, options=()),))
        assert hit is not None, spelling
        assert hit.surface_id == "citizenship_required"


def test_the_eeo_boilerplate_matches_no_surface() -> None:
    """The failure this guards is total, not partial: every Greenhouse board carries these blocks,
    so a catalog they match holds EVERY Greenhouse lead for review and the gate is worse than
    absent. `compliance[]` is excluded structurally by `parse_questions` as well — this is the
    second of the two independent defences, on the patterns themselves."""
    for text in (EEO_VEVRAA, EEO_CITIZENSHIP_CLAUSE):
        assert [member.surface_id for member in CATALOG if member.pattern.search(text)] == []


def test_us_person_alone_is_not_a_hard_stop_without_the_export_half() -> None:
    """Why the export surface is ONE member with TWO lookaheads rather than a pattern for each.

    "U.S. person" is a defined term in tax law as well as in the ITAR, and the tax form of the
    question is not a hard stop at all — it asks how to classify a payment, and anyone can answer
    it. Only the PAIR, in one question, states a requirement. Splitting the two conditions into
    separate members, or dropping either lookahead, turns every form carrying the phrase into a
    hold.

    Unlike the three hard stops above, these two strings are CONSTRUCTED rather than copied from a
    payload — the point is the phrase in a non-export context, and none of the three verified
    forms has one. They are the arm that fails when the ITAR half is removed.
    """
    for label in (
        "Are you a U.S. person for tax-withholding purposes (see Form W-9)?",
        "Payments to a non-U.S. person may be subject to withholding. Are you a U.S. person?",
    ):
        question = FormQuestion(label=label, description=None, options=("Yes", "No"))
        assert match_questions((question,)) is None, label

    # ...and the same phrase WITH the export half is the hit, so the arm above is not passing
    # because the phrase itself stopped matching.
    paired = FormQuestion(
        label="Are you a U.S. person as defined by the export control regulations?",
        description=None,
        options=("Yes", "No"),
    )
    hit = match_questions((paired,))
    assert hit is not None and hit.surface_id == "us_person_export_control"


def test_the_ordinary_form_questions_match_no_surface() -> None:
    """A control that must stay GREEN. Every one of these is on the relativity form beside the
    export block, and holding a lead for "LinkedIn Profile" would be the gate firing on the whole
    Greenhouse population by another route. The sponsorship question is the sharp one: it is about
    work authorization and it is deliberately NOT a surface here, because the eligibility engine
    already reads sponsorship from the JD and answering it is not a hard stop."""
    ordinary = (
        FormQuestion(label="First Name", description=None, options=()),
        FormQuestion(label="Resume/CV", description=None, options=()),
        FormQuestion(label="LinkedIn Profile", description=None, options=()),
        FormQuestion(
            label=(
                "Will you now or in the future require employment visa sponsorship "
                "(e.g., H-1B, TN, etc.)?"
            ),
            description=None,
            options=("Yes", "No"),
        ),
        FormQuestion(
            label="Are you willing to work onsite 5 days a week in Long Beach CA for this role? ",
            description=None,
            options=("Yes", "No"),
        ),
    )
    for question in ordinary:
        assert match_questions((question,)) is None


def test_the_matched_question_is_quoted_and_bounded() -> None:
    """The quote is EVIDENCE, and it is what the reader acts on — but it lands in `details.json`
    and on a page chip, so it is bounded. Truncated at 300 characters rather than dropped: a
    truncated question still names the requirement, and no question this module has seen is
    anywhere near the bound (the tenet3 label, the longest of the three, is 122)."""
    assert len(TENET3.label) < 300
    long = FormQuestion(label="Are you a U.S. citizen? " + "x" * 400, description=None, options=())
    hit = match_questions((long,))
    assert hit is not None
    assert len(hit.question) == 300
    assert hit.question == long.label[:300]


# --- parsing ----------------------------------------------------------------------------------


def test_the_matched_text_spans_the_label_the_description_and_the_option_labels() -> None:
    """All three, because each of the three verified hard stops lives in a DIFFERENT one of them:
    tenet3's is in the label, relativity's is in the description (its label is the two words
    "EXPORT COMPLIANCE"), and the option labels are what make the export block unambiguous. The
    description arrives as HTML and is stripped, so `&ldquo;` becomes a real quote and a tag never
    lands between two words the pattern has to match across."""
    questions = parse_questions(_payload(RELATIVITY))
    assert len(questions) == 1
    text = questions[0].text
    assert "EXPORT COMPLIANCE" in text
    assert "“U.S. person”" in text
    assert "I am currently a “U.S. Person”" in text
    assert "<p>" not in text and "&ldquo;" not in text


def test_compliance_blocks_are_never_part_of_the_matched_text() -> None:
    """The structural half of the EEO defence. `questions[]` ONLY — never `compliance[]`,
    `demographic_questions` or `location_questions`, which are the same boilerplate on every
    board and belong to no requisition's requirements."""
    questions = parse_questions(_payload(GIFTOGRAM, compliance=(EEO_VEVRAA,)))
    assert [q.label for q in questions] == [GIFTOGRAM.label]
    assert all("VEVRAA" not in q.text for q in questions)


def test_a_null_questions_array_reads_as_no_questions_rather_than_an_error() -> None:
    """Greenhouse returns `"questions": null` for some boards. That is "this board publishes no
    form", which is a fact about the board and not a fault: it must produce no hit and no
    error, so the lead rides on unheld."""
    questions = parse_questions(json.dumps({"id": 1, "questions": None}).encode())
    assert questions == ()
    assert match_questions(questions) is None


def test_an_unparseable_payload_is_a_typed_violation_at_the_raise_site() -> None:
    """Never classified by string-matching a message downstream: the sweep's fail-open arm has to
    tell "no questions known" from a bug in this module, and a bare `ValueError` from `json` is
    indistinguishable from either."""
    for content in (b"", b"not json", b'{"questions": 7}', b'{"questions": [3]}'):
        with pytest.raises(QuestionsUnreadable):
            parse_questions(content)


# --- fetching ---------------------------------------------------------------------------------


def test_the_questions_url_is_the_public_job_endpoint_with_questions_on() -> None:
    assert questions_url("tenet3", "8810809002") == (
        "https://boards-api.greenhouse.io/v1/boards/tenet3/jobs/8810809002?questions=true"
    )


class _StubFetcher:
    """One GET, recorded. Not the real `Fetcher`: these tests pin what this module ASKS FOR and
    what it does with the answer, and a real client would put the suite on the network."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.urls: list[str] = []

    def get(self, url: str) -> object:
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Result:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.not_modified = False


def test_a_fetch_reads_the_form_through_the_fetcher_exactly_once() -> None:
    """Through `Fetcher`, so `boards-api.greenhouse.io` — a host the board scan already hits —
    is paced under the SAME per-host lock rather than by a second client of our own."""
    fetcher = _StubFetcher(_Result(_payload(TENET3)))
    questions = fetch_questions(fetcher, slug="tenet3", posting_ref="8810809002")  # type: ignore[arg-type]
    assert fetcher.urls == [questions_url("tenet3", "8810809002")]
    assert [q.label for q in questions] == [TENET3.label]


@pytest.mark.parametrize(
    "failure",
    [FetchFailure("500 from boards-api.greenhouse.io"), TimeoutError("read timeout")],
    ids=["http-500", "timeout"],
)
def test_any_fetch_failure_reads_as_no_questions_known(failure: Exception) -> None:
    """FAIL-OPEN, and it is the whole safety argument for putting a network read on the delivery
    path: an error is "no questions known", never a hold. The alternative direction would cost the
    owner a real application every time a board 500s, which is the one outcome worse than missing
    a hard stop (D-380)."""
    fetcher = _StubFetcher(failure)
    assert fetch_questions(fetcher, slug="tenet3", posting_ref="1") is None  # type: ignore[arg-type]


def test_an_unreadable_body_reads_as_no_questions_known_too() -> None:
    """A 200 that will not parse is the same claim as a 500 for this gate's purposes, and it
    must not raise into `sync_queue`: the queue holds COPIES of delivered work, and a board that
    changed its payload shape must not cost the owner the folder tree."""
    fetcher = _StubFetcher(_Result(b"<html>we moved</html>"))
    assert fetch_questions(fetcher, slug="tenet3", posting_ref="1") is None  # type: ignore[arg-type]
