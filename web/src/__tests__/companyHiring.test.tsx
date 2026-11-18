import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getCompanyHiring: vi.fn() }));

import { getCompanyHiring } from "../api/client";
import { CompanyHiring } from "../components/CompanyHiring";
import type { CompanyHiring as CompanyHiringData, CompanyHiringRow } from "../api/types";

const row = (over: Partial<CompanyHiringRow>): CompanyHiringRow => ({
  company_id: 1,
  company: "Acme",
  provider: "ashby",
  watched: false,
  new: 10,
  new_per_week: 1.25,
  eligible: 4,
  eligible_per_week: 0.5,
  applied: 2,
  withdrawn: 1,
  newest_open_eligible: { posting_id: 9, title: "Role a6", age_days: 3.4 },
  ...over,
});

const ACME = row({});
const BIRCH = row({
  company_id: 2,
  company: "Birch",
  provider: "greenhouse",
  watched: true,
  new: 3,
  new_per_week: 0.375,
  eligible: 1,
  eligible_per_week: 0.125,
  applied: 0,
  withdrawn: 0,
  newest_open_eligible: null,
});

const DATA: CompanyHiringData = {
  window_days: 56,
  eligible_known: true,
  new: 13,
  eligible: 5,
  companies: 2,
  rows: [ACME, BIRCH],
  watched_rows: [BIRCH],
};

it("prints the window, the counts per company and the newest open eligible role", async () => {
  vi.mocked(getCompanyHiring).mockResolvedValue(DATA);
  render(<CompanyHiring />);
  const section = await screen.findByRole("region", { name: "Company hiring" });
  expect(section.textContent).toContain("Postings first seen in the last 56 days (8 weeks)");
  expect(section.textContent).toContain("13 new across 2 companies, 5 eligible now");
  expect(within(section).getByRole("row", { name: /^Acme/ }).textContent).toBe(
    "Acmeashby1.250.5010421Role a63d",
  );
  // No open eligible role: a dash, not an empty cell.
  expect(within(section).getByRole("row", { name: /^Birch/ }).textContent).toBe(
    "Birchgreenhouse0.380.133100—",
  );
});

it("filters to watched companies, which can include one the overall list left out", async () => {
  vi.mocked(getCompanyHiring).mockResolvedValue({ ...DATA, rows: [ACME], watched_rows: [BIRCH] });
  render(<CompanyHiring />);
  const section = await screen.findByRole("region", { name: "Company hiring" });
  expect(within(section).queryByRole("row", { name: /^Birch/ })).toBeNull();
  fireEvent.click(within(section).getByRole("checkbox", { name: "Watched companies only" }));
  expect(within(section).getByRole("row", { name: /^Birch/ })).toBeDefined();
  expect(within(section).queryByRole("row", { name: /^Acme/ })).toBeNull();
});

it("says so when no watched company has a new posting", async () => {
  vi.mocked(getCompanyHiring).mockResolvedValue({ ...DATA, watched_rows: [] });
  render(<CompanyHiring />);
  const section = await screen.findByRole("region", { name: "Company hiring" });
  fireEvent.click(within(section).getByRole("checkbox", { name: "Watched companies only" }));
  expect(section.textContent).toContain("No watched company has a new posting in this window.");
});

it("shows dashes, not zero, for eligible when there is no profile", async () => {
  vi.mocked(getCompanyHiring).mockResolvedValue({
    ...DATA,
    eligible_known: false,
    eligible: null,
    rows: [
      row({ eligible: null, eligible_per_week: null, newest_open_eligible: null }),
    ],
    watched_rows: [],
  });
  render(<CompanyHiring />);
  const section = await screen.findByRole("region", { name: "Company hiring" });
  expect(section.textContent).toContain("eligible is not measured");
  expect(section.textContent).not.toContain("eligible now");
  expect(within(section).getByRole("row", { name: /^Acme/ }).textContent).toBe(
    "Acmeashby1.25—10—21—",
  );
});

it("says so when the figures could not be loaded", async () => {
  vi.mocked(getCompanyHiring).mockRejectedValue(new Error("down"));
  render(<CompanyHiring />);
  expect(await screen.findByText("Company hiring could not be loaded.")).toBeDefined();
});
