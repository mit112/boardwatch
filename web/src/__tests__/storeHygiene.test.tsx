import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getStoreHygiene: vi.fn() }));

import { getStoreHygiene } from "../api/client";
import type { StoreHygiene as StoreHygieneData } from "../api/types";
import { StoreHygiene } from "../components/StoreHygiene";

function data(
  over: Partial<StoreHygieneData["quarantine"]> = {},
): StoreHygieneData {
  return {
    quarantine: {
      held: 1117,
      drained: 55,
      oldest_held_days: 73.1,
      last_drained_at: "2026-11-09T10:55:00",
      days_since_drain: 8.7,
      stall_days: 14,
      stalled: false,
      weekly: [{ week_start: "2026-11-16", quarantined: 52, drained: 0 }],
      ...over,
    },
    grouping: {
      merges: 4329,
      merged_jobs: 4329,
      without_source_job: 0,
      postings_approx: 1350431,
      per_1000_postings: 3.21,
      methods: [{ method: "exact_quad", algorithm_version: "p6.3", count: 4329 }],
      weekly: [{ week_start: "2026-11-16", merges: 112 }],
    },
    store: {
      db_bytes: 49982316544,
      wal_bytes: 0,
      total_bytes: 49982316544,
      growth_recorded: false,
    },
    tables: {
      rows: [
        { name: "eligibility_requirements", rows: 8882657, exact: false },
        { name: "quarantined_bodies", rows: 1172, exact: true },
      ],
    },
  };
}

it("shows the drain, the grouping rate, the size and says growth is not recorded", async () => {
  vi.mocked(getStoreHygiene).mockResolvedValue(data());
  render(<StoreHygiene />);
  const section = await screen.findByRole("region", { name: "Store hygiene" });
  expect(
    within(section).getByText(
      /1,117 bodies held, 55 drained\. Oldest held 73\.1 d/,
    ),
  ).toBeDefined();
  expect(within(section).queryByRole("alert")).toBeNull();
  expect(
    within(section).getByText(/3\.21 per 1,000 of about 1,350,431/),
  ).toBeDefined();
  expect(within(section).getByText(/50\.0 GB on disk/)).toBeDefined();
  expect(
    within(section).getByText(/Growth per run is not recorded/),
  ).toBeDefined();
  expect(within(section).getByText("eligibility_requirements")).toBeDefined();
});

it("marks only the estimated table sizes with an approximate sign", async () => {
  vi.mocked(getStoreHygiene).mockResolvedValue(data());
  render(<StoreHygiene />);
  const section = await screen.findByRole("region", { name: "Store hygiene" });
  expect(
    within(section).getByRole("columnheader", { name: "Rows" }),
  ).toBeDefined();
  const cell = (name: string) =>
    within(section).getByText(name).closest("tr")?.querySelector("td")
      ?.textContent;
  expect(cell("eligibility_requirements")).toBe("≈ 8,882,657");
  expect(cell("quarantined_bodies")).toBe("1,172");
});

it("raises an alert when held bodies have stopped draining", async () => {
  vi.mocked(getStoreHygiene).mockResolvedValue(data({ stalled: true }));
  render(<StoreHygiene />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toMatch(/none has drained in the last 14 days/);
});

it("says so when the numbers cannot be loaded", async () => {
  vi.mocked(getStoreHygiene).mockRejectedValue(new Error("503"));
  render(<StoreHygiene />);
  expect(
    await screen.findByText("Store hygiene could not be loaded."),
  ).toBeDefined();
});
