"""Evidence that two same-company/title/location postings are DIFFERENT openings.

This module can only ever make the reported near-duplicate bound SMALLER, so every test
below is written from the direction that matters: a discriminator may fire only on proof.
Absence of evidence, one-sided evidence, and overlapping evidence must all abstain.

The cases are the ones adjudicated by hand against the live store on 2026-08-27 (FINDINGS.md
section 2b): Affirm, Verkada and Broadcom on the distinct side; Citi, Philips, Disney and
Intel on the duplicate side.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from boardwatch.core.near_duplicate import (
    DISCRIMINATORS,
    PostingEvidence,
    UnknownDiscriminator,
    discriminator_evidence,
    distinguishing_evidence,
)


def _e(pid: int = 1, **over: object) -> PostingEvidence:
    base: dict[str, object] = {
        "posting_id": pid,
        "url": "https://boards.greenhouse.io/acme/jobs/1234",
        "body_text": "we are hiring a backend engineer.",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_period": None,
    }
    base.update(over)
    return PostingEvidence(**base)  # type: ignore[arg-type]


# --- the closed catalog ---------------------------------------------------------------


def test_the_discriminator_catalog_is_closed_and_typed_at_the_call_site():
    with pytest.raises(UnknownDiscriminator) as excinfo:
        discriminator_evidence("body_city", _e())
    assert excinfo.value.name == "body_city"


def test_every_catalog_member_is_answerable():
    """A name in the catalog with no extractor is the mirror of
    `MissingSuppressionResolver`: it would abstain forever and nobody would notice."""
    for name in DISCRIMINATORS:
        assert isinstance(discriminator_evidence(name, _e()), frozenset)


def test_distinguishing_evidence_never_names_something_outside_the_catalog():
    a = _e(1, url="https://acme.wd5.myworkdayjobs.com/x/job/NY/Data-Engineer_R1")
    b = _e(2, url="https://acme.wd5.myworkdayjobs.com/x/job/NY/Sales-Manager_R2")
    assert set(distinguishing_evidence(a, b)) <= set(DISCRIMINATORS)


# --- requisition_slug -----------------------------------------------------------------


def test_a_differing_url_title_slug_is_proof_of_a_different_opening():
    """D-295's Capital One case: one posting's own URL says `--Front-End`, the other's does
    not, while `postings.title` is identical for both."""
    a = _e(
        1,
        url="https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/McLean-VA/"
        "Lead-Software-Engineer_R244724",
    )
    b = _e(
        2,
        url="https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/McLean-VA/"
        "Lead-Software-Engineer--Front-End_R245666",
    )
    assert distinguishing_evidence(a, b) == ("requisition_slug",)


def test_the_requisition_id_is_stripped_so_two_spellings_of_one_role_agree():
    """Every posting in a group has a different provider_posting_id by construction
    (`UNIQUE(company_id, provider_posting_id)`). If the req id leaked into the slug, the
    discriminator would fire on EVERY pair and silently empty the candidate bound."""
    a = _e(1, url="https://x.wd5.myworkdayjobs.com/s/job/Austin/CPU-Performance-Architect_JR0285980")
    b = _e(2, url="https://x.wd5.myworkdayjobs.com/s/job/Austin/CPU-Performance-Architect_JR0281596")
    assert distinguishing_evidence(a, b) == ()


def test_a_trailing_republish_counter_is_stripped_too():
    a = _e(1, url="https://x.wd5.myworkdayjobs.com/s/job/NY/Team-Leader_587733-1")
    b = _e(2, url="https://x.wd5.myworkdayjobs.com/s/job/NY/Team-Leader_585139")
    assert distinguishing_evidence(a, b) == ()


def test_a_numeric_greenhouse_path_yields_no_slug_and_cannot_distinguish():
    a = _e(1, url="https://job-boards.greenhouse.io/affirm/jobs/7793244003")
    b = _e(2, url="https://job-boards.greenhouse.io/affirm/jobs/7793242003")
    assert discriminator_evidence("requisition_slug", a) == frozenset()
    assert distinguishing_evidence(a, b) == ()


def test_a_lever_uuid_is_not_read_as_a_title_slug():
    """A UUID splits into hex words; without an explicit guard two different UUIDs would
    read as two different titles and veto a real duplicate out of the bound.

    The two UUIDs are CONSTRUCTED so that several of their chunks are digit-free — that is
    what the guard is for. Two randomly drawn UUIDs are almost always killed by the
    digit-word strip alone, so a test built from real ones passes with the guard deleted and
    proves nothing. Each length-4 chunk is digit-free about 2% of the time, so over a corpus
    this arises on its own eventually.
    """
    a = _e(1, url="https://jobs.lever.co/veeva/deadbeef-cafe-4fed-bead-facecafebeef")
    b = _e(2, url="https://jobs.lever.co/veeva/decafbad-face-4bed-cafe-deadbeefcafe")
    assert discriminator_evidence("requisition_slug", a) == frozenset()
    assert distinguishing_evidence(a, b) == ()


def test_a_real_lever_uuid_is_also_not_a_slug():
    a = _e(1, url="https://jobs.lever.co/veeva/74d90b13-7637-4487-985e-1f1a3373a79d")
    b = _e(2, url="https://jobs.lever.co/veeva/7e9486f7-510c-4a5a-8c62-7b2c4976c7c5")
    assert discriminator_evidence("requisition_slug", a) == frozenset()
    assert distinguishing_evidence(a, b) == ()


def test_a_generic_last_segment_is_not_a_slug():
    """`.../open-positions/job?gh_jid=...` is the same segment for every Databricks posting."""
    a = _e(1, url="https://databricks.com/company/careers/open-positions/job?gh_jid=8675639002")
    assert discriminator_evidence("requisition_slug", a) == frozenset()


def test_a_missing_url_abstains_rather_than_matching_another_missing_url():
    """Two absent URLs must not compare equal-and-therefore-same, and must not compare
    different-and-therefore-distinct. Absence is not evidence in either direction."""
    assert discriminator_evidence("requisition_slug", _e(1, url=None)) == frozenset()
    assert distinguishing_evidence(_e(1, url=None), _e(2, url=None)) == ()
    assert (
        distinguishing_evidence(
            _e(1, url=None),
            _e(2, url="https://x.wd5.myworkdayjobs.com/s/job/NY/Data-Engineer_R1"),
        )
        == ()
    )


# --- salary_band ----------------------------------------------------------------------


def test_a_differing_structured_salary_band_is_proof():
    a = _e(1, salary_min=Decimal("125000"), salary_max=Decimal("160000"), salary_currency="USD")
    b = _e(2, salary_min=Decimal("150000"), salary_max=Decimal("300000"), salary_currency="USD")
    assert distinguishing_evidence(a, b) == ("salary_band",)


def test_an_identical_structured_salary_band_is_not_proof():
    a = _e(1, salary_min=Decimal("125000"), salary_max=Decimal("160000"), salary_currency="USD")
    b = _e(2, salary_min=Decimal("125000"), salary_max=Decimal("160000"), salary_currency="USD")
    assert distinguishing_evidence(a, b) == ()


def test_body_stated_pay_is_used_when_neither_side_has_a_structured_band():
    """The live Affirm pair: both bodies state a range, and the two ranges share nothing."""
    a = _e(1, body_text="usa base pay range per year: $145,000 - $205,000")
    b = _e(2, body_text="usa base pay range per year: $185,000 - $245,000")
    assert distinguishing_evidence(a, b) == ("salary_band",)


def test_overlapping_body_pay_figures_are_not_proof():
    """A JD that merely lists one EXTRA figure is not a different opening. Requiring
    disjointness rather than inequality is what keeps the bound an upper bound."""
    a = _e(1, body_text="base pay range: $145,000 - $205,000")
    b = _e(2, body_text="base pay range: $145,000 - $205,000, plus up to $30,000 in bonus")
    assert distinguishing_evidence(a, b) == ()


def test_the_top_of_a_range_counts_even_without_its_own_dollar_sign():
    """Intel writes `$122,440.00-172,860.00 USD`: one currency symbol for two figures.

    Dropping the upper bound only ever makes the extracted set SMALLER, which makes two sets
    MORE likely to look disjoint — the direction that shrinks the bound on no evidence. Two
    postings sharing a top-of-band and differing only in the bottom must still intersect.
    """
    a = _e(1, body_text="annual salary range: $122,440.00-172,860.00 usd")
    b = _e(2, body_text="annual salary range: $141,910.00-172,860.00 usd")
    assert discriminator_evidence("salary_band", a) == frozenset({122440, 172860})
    assert distinguishing_evidence(a, b) == ()


def test_an_em_dash_range_with_two_dollar_signs_is_read_as_two_figures():
    """Verkada writes `$125,000—$160,000`. Both spellings must yield both ends."""
    a = _e(1, body_text="pay range $125,000—$160,000")
    assert discriminator_evidence("salary_band", a) == frozenset({125000, 160000})


def test_a_structured_band_on_one_side_only_abstains_rather_than_comparing_apples():
    a = _e(1, salary_min=Decimal("125000"), salary_max=Decimal("160000"), salary_currency="USD")
    b = _e(2, body_text="base pay range: $185,000 - $245,000")
    assert distinguishing_evidence(a, b) == ()


def test_a_currency_difference_alone_is_not_read_as_the_same_band():
    a = _e(1, salary_min=Decimal("120000"), salary_max=Decimal("160000"), salary_currency="USD")
    b = _e(2, salary_min=Decimal("120000"), salary_max=Decimal("160000"), salary_currency="CAD")
    assert distinguishing_evidence(a, b) == ("salary_band",)


# --- experience_years -----------------------------------------------------------------


def test_a_disjoint_years_floor_is_proof_of_a_different_opening():
    """The live Verkada pair, and D-295's Philips 5+/2+ pair: one title, one city, two
    levels. The junior opening is the one a merge would hide."""
    a = _e(1, body_text="bs in computer science and 1-3 years of experience")
    b = _e(2, body_text="bs in computer science and 3+ years of experience")
    assert distinguishing_evidence(a, b) == ("experience_years",)


def test_a_shared_years_floor_is_not_proof_even_when_one_side_states_more():
    a = _e(1, body_text="5+ years of experience")
    b = _e(2, body_text="5+ years of experience, including 3 years of experience with go")
    assert distinguishing_evidence(a, b) == ()


def test_a_years_figure_with_no_experience_nearby_is_not_a_floor():
    """"Our team has 25 years of history" is not a requirement. Reading it as one would
    veto a real duplicate out of the bound."""
    assert discriminator_evidence("experience_years", _e(1, body_text="25 years of history")) == (
        frozenset()
    )


def test_years_stated_on_one_side_only_abstains():
    a = _e(1, body_text="5+ years of experience")
    b = _e(2, body_text="we are hiring a backend engineer.")
    assert distinguishing_evidence(a, b) == ()


# --- the four adjudicated true duplicates must NOT be distinguished --------------------


def test_the_citi_pair_is_not_distinguished():
    """Live jobs 53296/53297: `Regulatory Risk Officer - C13 - JACKSONVILLE`, bodies differ
    by ONE deleted word and by nothing a discriminator can see."""
    base = "the regulatory risk officer is responsible for oversight."
    a = _e(
        1,
        url="https://citi.wd5.myworkdayjobs.com/2/job/Jacksonville-Florida-United-States/"
        "Regulatory-Risk-Officer---C13---JACKSONVILLE_26988739",
        body_text=base + " prior audit experience is recommended.",
    )
    b = _e(
        2,
        url="https://citi.wd5.myworkdayjobs.com/2/job/Jacksonville-Florida-United-States/"
        "Regulatory-Risk-Officer---C13---JACKSONVILLE_26988744",
        body_text=base + " prior audit experience.",
    )
    assert distinguishing_evidence(a, b) == ()


def test_the_philips_pair_is_not_distinguished():
    """Live jobs 23188/23199: the second body merely echoes its own req number and appends
    `#eos`."""
    base = "lead the field service team. 5 years of experience required."
    a = _e(
        1,
        url="https://philips.wd3.myworkdayjobs.com/jobs-and-careers/job/"
        "Latham-New-York-United-States/Team-Leader_585139",
        body_text=base,
    )
    b = _e(
        2,
        url="https://philips.wd3.myworkdayjobs.com/jobs-and-careers/job/"
        "Latham-New-York-United-States/Team-Leader_587733-1",
        body_text="587733 team leader " + base + " #eos",
    )
    assert distinguishing_evidence(a, b) == ()


# --- multiple discriminators ----------------------------------------------------------


def test_several_discriminators_are_all_named_in_catalog_order():
    """The Affirm pair fires on two at once. Naming both, in a stable order, is what makes
    the veto auditable after the fact."""
    a = _e(
        1,
        url="https://x.wd5.myworkdayjobs.com/s/job/NY/Analytics-Lead_R1",
        body_text="5+ years of experience. base pay range: $145,000 - $205,000",
    )
    b = _e(
        2,
        url="https://x.wd5.myworkdayjobs.com/s/job/NY/Analytics-Lead-Full-Stack_R2",
        body_text="8+ years of experience. base pay range: $185,000 - $245,000",
    )
    assert distinguishing_evidence(a, b) == (
        "requisition_slug",
        "salary_band",
        "experience_years",
    )


def test_distinguishing_evidence_is_symmetric():
    a = _e(1, body_text="5+ years of experience")
    b = _e(2, body_text="9+ years of experience")
    assert distinguishing_evidence(a, b) == distinguishing_evidence(b, a)
