"""Per-rule abstain rate (PROGRAM.md §3.P0.2).

The keystone invariant says a rule that cannot fire is a MONITORING failure, not a
conservatism feature. This module is the monitoring. It exists because the obvious query is
wrong: `GROUP BY rule_id` over eligibility_requirements can only ever emit groups for rules
that have been detected at least once, so the rules most worth knowing about — the ones that
have never fired at all — produce no row and read as absent rather than as broken.

So enumeration comes from the CATALOG and the observed counts are LEFT JOINed onto it. Three
outcomes are kept apart on purpose, because collapsing any pair of them destroys the signal:

  * `abstain_rate is None` — the rule has never fired. Not 0%. A rule with no rows would
    otherwise be reported as the healthiest rule in the catalog.
  * `abstain_rate == 1.0` — the rule fires and never decides anything.
  * `0.0 <= abstain_rate < 1.0` — the rule works.

`out_of_catalog` and `unattributed` are surfaced rather than bucketed, per the closed-catalog
rule: a rule_id the catalog does not declare is a failure, and a NULL rule_id belongs to no
rule at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from boardwatch.eligibility.catalog import RulesCatalog

# (rule_id, disposition) -> row count. rule_id is None for rows the schema allows to carry no
# rule attribution at all.
DispositionCounts = Mapping[tuple[str | None, str], int]


@dataclass(frozen=True)
class RuleAbstain:
    """One catalog rule, with whatever the data had to say about it — possibly nothing."""

    rule_id: str
    family: str
    met: int
    unmet: int
    unknown: int

    @property
    def observed(self) -> int:
        return self.met + self.unmet + self.unknown

    @property
    def abstain_rate(self) -> float | None:
        """None when the rule has never fired — a rate over zero rows is not 0%, it is undefined.

        This is the single most load-bearing line in the module. Returning 0.0 here would make
        `experience_years:scoped_years_minimum` (11,670 rows, 11,670 abstains) and a rule that
        has never once been detected report as equally healthy in opposite directions.
        """
        if self.observed == 0:
            return None
        return self.unknown / self.observed

    @property
    def never_fired(self) -> bool:
        return self.observed == 0

    @property
    def fully_abstaining(self) -> bool:
        """Fires, and has never once decided. Deliberately excludes never-fired."""
        return self.observed > 0 and self.unknown == self.observed


@dataclass(frozen=True)
class AbstainReport:
    """Every rule in the catalog, in catalog order, plus what did not belong to any of them."""

    rules: tuple[RuleAbstain, ...]
    out_of_catalog: tuple[str, ...]
    out_of_catalog_rows: int
    unattributed: int

    @property
    def never_fired(self) -> tuple[RuleAbstain, ...]:
        return tuple(rule for rule in self.rules if rule.never_fired)

    @property
    def fully_abstaining(self) -> tuple[RuleAbstain, ...]:
        return tuple(rule for rule in self.rules if rule.fully_abstaining)

    @property
    def observed_rows(self) -> int:
        return sum(rule.observed for rule in self.rules)

    @property
    def total_rows(self) -> int:
        """Every row handed in, wherever it ended up. B6 reconciles against this."""
        return self.observed_rows + self.out_of_catalog_rows + self.unattributed


def build_abstain_report(catalog: RulesCatalog, counts: DispositionCounts) -> AbstainReport:
    """LEFT JOIN observed dispositions onto the catalog enumeration.

    `counts` is keyed by (rule_id, disposition) so the caller can hand over a raw GROUP BY
    without having to know which rules the catalog declares — that reconciliation is this
    function's whole job.
    """
    declared = {
        pattern.rule_id: family.id
        for family in catalog.families
        for pattern in family.patterns
    }

    tallies: dict[str, dict[str, int]] = {rule_id: {} for rule_id in declared}
    out_of_catalog: dict[str, int] = {}
    unattributed = 0

    for (rule_id, disposition), count in counts.items():
        if rule_id is None:
            unattributed += count
        elif rule_id in tallies:
            tallies[rule_id][disposition] = tallies[rule_id].get(disposition, 0) + count
        else:
            out_of_catalog[rule_id] = out_of_catalog.get(rule_id, 0) + count

    rules = tuple(
        RuleAbstain(
            rule_id=rule_id,
            family=family_id,
            met=tallies[rule_id].get("met", 0),
            unmet=tallies[rule_id].get("unmet", 0),
            unknown=tallies[rule_id].get("unknown", 0),
        )
        for rule_id, family_id in declared.items()
    )
    return AbstainReport(
        rules=rules,
        out_of_catalog=tuple(sorted(out_of_catalog)),
        out_of_catalog_rows=sum(out_of_catalog.values()),
        unattributed=unattributed,
    )
