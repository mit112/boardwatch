"""The delivery queue: a second root holding copies of what a run produced (design §4).

The dated output tree under the applications root is a machine record and is untouched by
everything in this package.
"""

from boardwatch.delivery.names import LeadNames, NameBudgetError, plan_lead_names, slug

__all__ = ["LeadNames", "NameBudgetError", "plan_lead_names", "slug"]
