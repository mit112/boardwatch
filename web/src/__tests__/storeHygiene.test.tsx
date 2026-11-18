import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getStoreHygiene: vi.fn() }));

import { getStoreHygiene } from "../api/client";
import type { StoreHygiene as StoreHygieneData } from "../api/types";
import { StoreHygiene } from "../components/StoreHygiene";

function data(
  over: Partial<StoreHygieneData["quarantine"]> = {},
  store: Partial<StoreHygieneData["store"]> = {},
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
      series: [],
      ...store,
    },
    tables: {
      rows: [
        { name: "eligibility_requirements", rows: 8882657, exact: false },
        { name: "quarantined_bodies", rows: 1172, exact: true },
      ],
    },
  };
}

it("shows the drain, the grouping rate, the size and says no growth is recorded", async () => {
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
    within(section).getByText(/No run shown has a recorded size yet/),
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

it("shows growth per run and a dash, never 0, where a run recorded no size", async () => {
  vi.mocked(getStoreHygiene).mockResolvedValue(
    data(
      {},
      {
        growth_recorded: true,
        series: [
          {
            run_id: 7,
            finished: null,
            db_bytes: 1000000000,
            wal_bytes: 0,
            growth_bytes: null,
          },
          {
            run_id: 8,
            finished: null,
            db_bytes: 1500000000,
            wal_bytes: 4000000,
            growth_bytes: 500000000,
          },
          {
            run_id: 9,
            finished: null,
            db_bytes: null,
            wal_bytes: null,
            growth_bytes: null,
          },
          {
            run_id: 10,
            finished: null,
            db_bytes: 1400000000,
            wal_bytes: 0,
            growth_bytes: -100000000,
          },
        ],
      },
    ),
  );
  render(<StoreHygiene />);
  const section = await screen.findByRole("region", { name: "Store hygiene" });
  expect(
    within(section).queryByText(/No run shown has a recorded size/),
  ).toBeNull();
  const table = within(section).getByRole("table", {
    name: "Store size by run",
  });
  const body = table.querySelectorAll("tbody tr");
  const cells = (i: number) =>
    Array.from(body[i]?.children ?? []).map((c) => c.textContent);
  // One row per run; the Finished cell is a dash because the fixture has no time.
  expect(cells(0)).toEqual(["7", "\u2014", "1.0 GB", "0.0 MB", "\u2014"]);
  expect(cells(1)).toEqual(["8", "\u2014", "1.5 GB", "4.0 MB", "+500.0 MB"]);
  expect(cells(2)).toEqual(["9", "\u2014", "\u2014", "\u2014", "\u2014"]);
  expect(cells(3)).toEqual([
    "10",
    "\u2014",
    "1.4 GB",
    "0.0 MB",
    "\u2212100.0 MB",
  ]);
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
