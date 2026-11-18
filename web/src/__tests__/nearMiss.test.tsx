import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getNearMisses: vi.fn() }));

import { getNearMisses } from "../api/client";
import type { NearMisses } from "../api/types";
import { NearMissPanel } from "../components/NearMissPanel";

const DATA: NearMisses = {
  profile: true,
  blocked: 1000,
  one_unmet: 300,
  near_misses: 120,
  with_abstain: 15,
  gated_out: [
    { clause: "excluded_title", count: 150 },
    { clause: "out_of_field", count: 15 },
  ],
  rules: [
    {
      rule_id: "experience_years:scoped_years_minimum",
      count: 90,
      with_abstain: 12,
      requirements: [
        { text: "2 years of experience required", count: 70 },
        { text: "3 years of experience required", count: 20 },
      ],
      samples: [
        {
          posting_id: 7,
          title: "Software Engineer",
          company: "Acme",
          requirement: "2 years of experience required",
          quote: "Requires 2 years of professional experience <b>not markup</b>",
        },
      ],
    },
    {
      rule_id: "work_auth:no_sponsorship_offered",
      count: 30,
      with_abstain: 0,
      requirements: [],
      samples: [],
    },
  ],
};

it("states the cohort, what the gates left out and the abstains apart, then each rule", async () => {
  vi.mocked(getNearMisses).mockResolvedValue(DATA);
  render(<NearMissPanel />);
  const panel = await screen.findByRole("region", { name: "Near-miss list" });
  const summary = within(panel).getByText(/open postings that pass the title/);
  expect(summary.textContent).toContain("120 open postings");
  expect(summary.textContent).toContain("Of 1,000 blocked postings, 300 hold");
  expect(summary.textContent).toContain(
    "The gates left out 165: 150 an excluded title, 15 outside the role taxonomy.",
  );
  // The abstains stay a separate sentence and are never added to the 120.
  expect(summary.textContent).toContain(
    "15 more also abstain on a blocking rule and are not counted.",
  );

  const list = within(panel).getByRole("list", { name: "Near-misses by rule" });
  expect(
    Array.from(list.querySelectorAll("[title]")).map((e) => e.textContent),
  ).toEqual([
    "experience_years:scoped_years_minimum",
    "work_auth:no_sponsorship_offered",
  ]);
  expect(within(panel).getByText("90 near-misses")).toBeDefined();
  expect(within(panel).getByText("30 near-misses")).toBeDefined();
  expect(
    within(panel).getByText(
      "Asked: 2 years of experience required (70) · 3 years of experience required (20)",
    ),
  ).toBeDefined();
  expect(
    within(panel).getByText(/12 more have this one unmet requirement/),
  ).toBeDefined();
});

it("shows a sample's quoted span as text, never as markup", async () => {
  vi.mocked(getNearMisses).mockResolvedValue(DATA);
  render(<NearMissPanel />);
  const panel = await screen.findByRole("region", { name: "Near-miss list" });
  expect(within(panel).getByText("Software Engineer")).toBeDefined();
  const quote = within(panel).getByText(/Requires 2 years of professional/);
  expect(quote.textContent).toBe(
    "Requires 2 years of professional experience <b>not markup</b>",
  );
  expect(quote.querySelector("b")).toBeNull();
});

it("draws nothing without a profile", async () => {
  vi.mocked(getNearMisses).mockResolvedValue({
    profile: false,
    blocked: 0,
    one_unmet: 0,
    near_misses: 0,
    with_abstain: 0,
    gated_out: [],
    rules: [],
  });
  const { container } = render(<NearMissPanel />);
  await Promise.resolve();
  expect(container.textContent).toBe("");
});
