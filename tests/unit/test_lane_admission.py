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
