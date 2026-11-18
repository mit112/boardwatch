import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getPostingLifetime: vi.fn() }));

import { getPostingLifetime } from "../api/client";
import { PostingLifetime } from "../components/PostingLifetime";

const NONE = { count: 0, median_days: null, p90_days: null };

it("prints lifetimes by provider and company, the never-closed count and the reopen rate", async () => {
  vi.mocked(getPostingLifetime).mockResolvedValue({
    closed: { count: 4, median_days: 2.5, p90_days: 7.9 },
    never_closed: 1,
    reopen: { events: 1, postings: 1, rate: 0.25 },
    to_apply: { count: 2, median_days: 3, p90_days: 4.6, excluded_imports: 61 },
    urgent: true,
    providers: [
      {
        provider: "ashby",
        count: 2,
        median_days: 2,
        p90_days: 2.8,
        never_closed: 1,
        reopen_rate: 0,
        to_apply: { count: 1, median_days: 5, p90_days: 5 },
        urgent: true,
      },
      {
        provider: "greenhouse",
        count: 2,
        median_days: 6,
        p90_days: 9.2,
        never_closed: 0,
        reopen_rate: 0.5,
        to_apply: NONE,
        urgent: null,
      },
    ],
    companies: [{ company: "Acme", provider: "ashby", count: 6, median_days: 2, p90_days: 3, never_closed: 1 }],
  });
  render(<PostingLifetime />);
  const section = await screen.findByRole("region", { name: "Posting lifetime" });
  expect(
    within(section).getByText(/1 postings have never closed and are not in the medians/),
  ).toBeDefined();
  expect(within(section).getByText(/61 imported jobs are left out of time to apply/)).toBeDefined();
  expect(within(section).getByText(/Postings close faster than we apply/)).toBeDefined();
  expect(within(section).getByRole("row", { name: /^ashby/ }).textContent).toBe(
    "ashby212.0 d2.8 d5.0 d0%Yes",
  );
  // No applications for this provider: a dash for the wait and for urgency, never 0 d.
  expect(within(section).getByRole("row", { name: /^greenhouse/ }).textContent).toBe(
    "greenhouse206.0 d9.2 d—50%—",
  );
  expect(within(section).getByRole("row", { name: /^Acme/ }).textContent).toBe(
    "Acmeashby612.0 d3.0 d",
  );
});

it("shows dashes, not zero days, when nothing has closed", async () => {
  vi.mocked(getPostingLifetime).mockResolvedValue({
    closed: NONE,
    never_closed: 2,
    reopen: { events: 0, postings: 0, rate: null },
    to_apply: { ...NONE, excluded_imports: 0 },
    urgent: null,
    providers: [],
    companies: [],
  });
  render(<PostingLifetime />);
  const section = await screen.findByRole("region", { name: "Posting lifetime" });
  expect(section.textContent).toContain("median life —, 90th percentile —");
  expect(section.textContent).toContain("Urgency is not measured.");
  expect(section.textContent).not.toContain("0.0 d");
});

it("says so when the figures could not be loaded", async () => {
  vi.mocked(getPostingLifetime).mockRejectedValue(new Error("down"));
  render(<PostingLifetime />);
  expect(await screen.findByText("Posting lifetime could not be loaded.")).toBeDefined();
});
