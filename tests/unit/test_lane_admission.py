"""The per-run new-company cap (JD-acquisition spec §4.6, owner ruling in D-278)."""

import pytest

from boardwatch.lanes.admission import DEFAULT_NEW_COMPANIES_PER_RUN, CompanyBudget


def test_the_default_cap_is_ten_per_run():
    assert DEFAULT_NEW_COMPANIES_PER_RUN == 10


def test_the_cap_admits_up_to_its_limit_and_refuses_the_rest():
    budget = CompanyBudget(limit=2)
    admitted = [budget.admit("greenhouse", slug) for slug in ("a", "b", "c", "d")]
    assert admitted == [True, True, False, False]


def test_every_refusal_is_identified_not_merely_counted():
    """A silently dropped company is indistinguishable from one never seen."""
    budget = CompanyBudget(limit=1)
    for slug in ("kept", "dropped_1", "dropped_2"):
        budget.admit("greenhouse", slug)
    assert budget.admitted == (("greenhouse", "kept"),)
    assert budget.refused == (("greenhouse", "dropped_1"), ("greenhouse", "dropped_2"))


def test_readmitting_the_same_company_does_not_consume_budget_twice():
    """Two postings from one new employer are one company, not two."""
    budget = CompanyBudget(limit=1)
    assert budget.admit("greenhouse", "acme") is True
    assert budget.admit("greenhouse", "acme") is True
    assert budget.admitted == (("greenhouse", "acme"),)


def test_a_zero_cap_admits_nothing_and_is_not_an_error():
    """The off switch. A lane with a zero budget still reports what it would have added."""
    budget = CompanyBudget(limit=0)
    assert budget.admit("greenhouse", "acme") is False
    assert budget.refused == (("greenhouse", "acme"),)


def test_a_negative_cap_is_rejected_at_construction():
    with pytest.raises(ValueError):
        CompanyBudget(limit=-1)


def test_a_none_limit_is_uncapped_and_never_refuses():
    """The per-lane "unlimited" override resolves to `limit=None`, not `limit=0` — 0 already
    means the opposite (the off switch above). `None` must admit every distinct company."""
    budget = CompanyBudget(limit=None)
    for slug in ("a", "b", "c", "d", "e"):
        assert budget.admit("greenhouse", slug) is True
    assert budget.refused == ()


def test_the_same_slug_on_two_providers_is_two_companies():
    """`companies` is UNIQUE(provider, slug), so greenhouse:acme and lever:acme are two
    rows. A budget keyed on a shared display name would charge one slot for both and take
    the run silently over the cap."""
    budget = CompanyBudget(limit=1)
    assert budget.admit("greenhouse", "acme") is True
    assert budget.admit("lever", "acme") is False
    assert budget.refused == (("lever", "acme"),)


def test_two_display_names_for_one_slug_are_one_company():
    """The other direction: an aggregator naming one employer "Acme" and "Acme Inc." is
    still the single row UNIQUE(provider, slug) holds, so it costs one slot, not two.
    Keyed on a name, this would have burned the whole budget on one company."""
    budget = CompanyBudget(limit=2)
    assert budget.admit("greenhouse", "acme") is True
    assert budget.admit("greenhouse", "acme") is True
    assert budget.admitted == (("greenhouse", "acme"),)
    assert budget.admit("greenhouse", "beta") is True
    assert budget.admit("greenhouse", "gamma") is False


def test_refusing_the_same_company_twice_records_it_once():
    """A refusal COUNT that lists one employer three times overstates what the cap cost, and
    that number is the whole reason the refusal list exists. `admitted` already dedupes; an
    aggregator returning many postings per employer makes the two sides disagree otherwise."""
    budget = CompanyBudget(limit=1)
    budget.admit("greenhouse", "kept")
    for _ in range(3):
        assert budget.admit("greenhouse", "dropped") is False
    assert budget.refused == (("greenhouse", "dropped"),)


# --- The tier-aware bound (D-452, D-459) -----------------------------------------------------


def test_without_a_tier1_budget_a_tier1_admission_charges_the_lane_cap():
    """UPGRADE NEUTRALITY. No `.tier1` override ships, so the nested budget is None for every
    lane, and a tier-1 admission must then be indistinguishable from any other — same slot, same
    refusal list. A default that separated the two bounds silently would move every existing
    tenant's admissions on upgrade."""
    budget = CompanyBudget(limit=1)
    assert budget.admit("indeed", "acme", tier1=False) is True
    assert budget.admit("greenhouse", "vertex", tier1=True) is False
    assert budget.admitted == (("indeed", "acme"),)
    assert budget.refused == (("greenhouse", "vertex"),)


def test_a_tier1_admission_is_charged_to_the_tier1_budget_and_not_to_the_lane_cap():
    """The whole point: at the lane cap, tier 1 is still admitted under its OWN bound. On Indeed
    that slot buys a supported employer board that joins the scan fleet and pays off on every
    later run, where a tier-2 slot buys a permanently-secondhand row (D-452)."""
    budget = CompanyBudget(limit=1, tier1=CompanyBudget(limit=2))
    assert budget.admit("indeed", "acme") is True
    assert budget.admit("indeed", "beta") is False, "the lane cap must still bite on tier 2"
    assert budget.admit("greenhouse", "vertex", tier1=True) is True
    assert budget.admit("lever", "beacon", tier1=True) is True
    assert budget.admitted == (
        ("indeed", "acme"),
        ("greenhouse", "vertex"),
        ("lever", "beacon"),
    )
    assert budget.refused == (("indeed", "beta"),)


def test_the_tier1_budget_is_a_bound_not_an_uncap():
    """D-459 refused leaving Indeed at `"unlimited"` because it is a STREAM, not a pool: ~58 new
    boards a run at 9.33 s of scan time each, compounding. So the tier-1 bound must refuse too,
    and its refusals must be identified like any other."""
    budget = CompanyBudget(limit=10, tier1=CompanyBudget(limit=1))
    assert budget.admit("greenhouse", "vertex", tier1=True) is True
    assert budget.admit("lever", "beacon", tier1=True) is False
    assert budget.admitted == (("greenhouse", "vertex"),)
    assert budget.refused == (("lever", "beacon"),)


def test_an_uncapped_tier1_budget_never_refuses_while_the_lane_cap_still_does():
    """`"indeed.tier1" = "unlimited"` resolves to `CompanyBudget(None)`, the same uncapped
    sentinel `_lane_company_cap` produces — and it must not leak across to tier 2, which is the
    half D-452 said to refuse freely."""
    budget = CompanyBudget(limit=0, tier1=CompanyBudget(limit=None))
    for slug in ("a", "b", "c"):
        assert budget.admit("greenhouse", slug, tier1=True) is True
    assert budget.admit("indeed", "acme") is False
    assert budget.refused == (("indeed", "acme"),)
