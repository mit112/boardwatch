"""The per-run new-company cap (JD-acquisition spec §4.6, owner ruling in D-278)."""

import pytest

from boardwatch.lanes.admission import DEFAULT_NEW_COMPANIES_PER_RUN, CompanyBudget


def test_the_default_cap_is_ten_per_run():
    assert DEFAULT_NEW_COMPANIES_PER_RUN == 10


def test_the_cap_admits_up_to_its_limit_and_refuses_the_rest():
    budget = CompanyBudget(limit=2)
    assert [budget.admit(name) for name in ("a", "b", "c", "d")] == [True, True, False, False]


def test_every_refusal_is_named_not_merely_counted():
    """A silently dropped company is indistinguishable from one never seen."""
    budget = CompanyBudget(limit=1)
    for name in ("kept", "dropped_1", "dropped_2"):
        budget.admit(name)
    assert budget.admitted == ("kept",)
    assert budget.refused == ("dropped_1", "dropped_2")


def test_readmitting_the_same_company_does_not_consume_budget_twice():
    """Two postings from one new employer are one company, not two."""
    budget = CompanyBudget(limit=1)
    assert budget.admit("acme") is True
    assert budget.admit("acme") is True
    assert budget.admitted == ("acme",)


def test_a_zero_cap_admits_nothing_and_is_not_an_error():
    """The off switch. A lane with a zero budget still reports what it would have added."""
    budget = CompanyBudget(limit=0)
    assert budget.admit("acme") is False
    assert budget.refused == ("acme",)


def test_a_negative_cap_is_rejected_at_construction():
    with pytest.raises(ValueError):
        CompanyBudget(limit=-1)
