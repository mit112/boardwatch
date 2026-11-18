import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import type { FunnelAbstain, FunnelAbstainRule } from "../api/types";
import {
  RuleDispositions,
  flagFor,
  topBlockers,
} from "../components/RuleDispositions";

function rule(
  rule_id: string,
  over: Partial<FunnelAbstainRule> = {},
): FunnelAbstainRule {
  return {
    rule_id,
    family: rule_id.split(":")[0] ?? rule_id,
    observed: 0,
    met: 0,
    unmet: 0,
    abstained: 0,
    abstain_rate: null,
    never_fired: false,
    fully_abstaining: false,
    not_applicable: false,
    ...over,
  };
}

function report(rules: FunnelAbstainRule[]): FunnelAbstain {
  return {
    rules,
    rule_count: rules.length,
    never_fired: rules.filter((r) => r.never_fired).length,
    not_applicable: 0,
    fully_abstaining: rules.filter((r) => r.fully_abstaining).length,
    out_of_catalog: [],
    out_of_catalog_rows: 0,
    unattributed_rows: 0,
    total_rows: 1000,
  };
}

const RULES = [
  rule("work_auth:no_sponsorship_offered", {
    observed: 100,
    met: 20,
    unmet: 74,
    abstained: 6,
    abstain_rate: 0.06,
  }),
  rule("experience_years:scoped_years_minimum", {
    observed: 500,
    met: 50,
    unmet: 400,
    abstained: 50,
    abstain_rate: 0.1,
  }),
  rule("work_auth:uk_authorization_required", {
    observed: 9,
    abstained: 9,
    abstain_rate: 1,
    fully_abstaining: true,
  }),
  rule("degree:field_required", { never_fired: true }),
];

it("orders the blocking rules by unmet rows and leaves out rules with none", () => {
  expect(topBlockers(RULES).map((r) => r.rule_id)).toEqual([
    "experience_years:scoped_years_minimum",
    "work_auth:no_sponsorship_offered",
  ]);
});

it("keeps met, unmet and abstained in their own columns, never summed", () => {
  render(<RuleDispositions abstain={report(RULES)} />);
  const table = screen.getByRole("region", { name: "Abstain rate per rule" });
  const row = within(table).getByRole("row", {
    name: /no_sponsorship_offered/,
  });
  expect([...row.querySelectorAll("td")].map((c) => c.textContent)).toEqual([
    "20",
    "74",
    "6",
    "6.0%",
    "",
  ]);
});

it("calls a rule that abstains on every row a monitoring failure, and a dead one never fired", () => {
  expect(flagFor(RULES[2]!)).toMatch(/monitoring failure/);
  expect(flagFor(RULES[3]!)).toBe("never fired");
  render(<RuleDispositions abstain={report(RULES)} />);
  const list = screen.getByRole("list", { name: "Rules that cannot decide" });
  expect(
    within(list)
      .getAllByRole("listitem")
      .map((li) => li.textContent),
  ).toEqual([
    "work_auth:uk_authorization_required: abstains on every row: a monitoring failure, it can never decide",
    "degree:field_required: never fired",
  ]);
});

it("prints a dash, not 0%, for a rule with no rows", () => {
  render(<RuleDispositions abstain={report(RULES)} />);
  const row = screen.getByRole("row", { name: /degree:field_required/ });
  expect(row.querySelectorAll("td")[3]?.textContent).toBe("—");
});

it("says so when the funnel predates the report", () => {
  render(<RuleDispositions abstain={undefined} />);
  expect(screen.getByText(/predates the per-rule report/)).toBeDefined();
});
