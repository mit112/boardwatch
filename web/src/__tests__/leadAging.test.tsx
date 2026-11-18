import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getLeadAging: vi.fn() }));

import { getLeadAging } from "../api/client";
import { LeadAging } from "../components/LeadAging";

it("prints each outcome's wait and the closed-first count by source", async () => {
  vi.mocked(getLeadAging).mockResolvedValue({
    leads: 5,
    still_waiting: 1,
    outcomes: {
      applied: { count: 2, median_days: 2, p90_days: 2.8 },
      closed: { count: 1, median_days: 2, p90_days: 2 },
      skipped: { count: 1, median_days: 0.25, p90_days: 0.25 },
    },
    closed_before_applied_by_board: { greenhouse: 1 },
  });
  render(<LeadAging />);
  const section = await screen.findByRole("region", { name: "Lead aging" });
  const applied = within(section).getByRole("row", { name: /Applied/ });
  expect(applied.textContent).toBe("Applied22.0 d2.8 d");
  expect(within(section).getByText(/1 have no outcome yet/)).toBeDefined();
  expect(within(section).getByText("greenhouse").textContent).toBe("greenhouse 1");
});

it("shows a dash, not zero days, for an outcome nobody reached", async () => {
  vi.mocked(getLeadAging).mockResolvedValue({
    leads: 0,
    still_waiting: 0,
    outcomes: {
      applied: { count: 0, median_days: null, p90_days: null },
      closed: { count: 0, median_days: null, p90_days: null },
      skipped: { count: 0, median_days: null, p90_days: null },
    },
    closed_before_applied_by_board: {},
  });
  render(<LeadAging />);
  const row = await screen.findByRole("row", { name: /Skipped/ });
  expect(row.textContent).toBe("Skipped0——");
});
