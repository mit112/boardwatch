import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { FunnelSource } from "../api/types";
import { sourceYield } from "../lib/sourceYield";

vi.mock("../api/client", () => ({ getSourceYield: vi.fn() }));

import { getSourceYield } from "../api/client";
import { SourceYield } from "../components/SourceYield";

function board(provider: string, open: number, eligible: number): FunnelSource {
  return {
    provider,
    board_slug: `${provider}-${String(open)}`,
    company_source: "user",
    open_postings: open,
    unique: null,
    assisted: null,
    eligible,
    leads: 0,
    applied: 0,
  };
}

const BOARDS = [
  board("ashby", 10, 2),
  board("ashby", 5, 1),
  board("lever", 3, 0),
];

it("sums the snapshot per source and keeps the all-time counts beside it", () => {
  const rows = sourceYield(BOARDS, {
    ashby: { built: 4, applied: 1 },
    linkedin: { built: 9, applied: 3 },
  });
  expect(rows).toEqual([
    {
      source: "linkedin",
      open: 0,
      eligible: 0,
      built: 9,
      applied: 3,
      applyRate: 1 / 3,
    },
    {
      source: "ashby",
      open: 15,
      eligible: 3,
      built: 4,
      applied: 1,
      applyRate: 0.25,
    },
    {
      source: "lever",
      open: 3,
      eligible: 0,
      built: 0,
      applied: 0,
      applyRate: null,
    },
  ]);
});

it("reads unknown all-time counts as dashes, never zeros", async () => {
  vi.mocked(getSourceYield).mockRejectedValue(new Error("503"));
  render(<SourceYield boards={BOARDS} />);
  const row = screen.getByRole("row", { name: /^ashby/ });
  await Promise.resolve();
  expect([...row.querySelectorAll("td")].map((c) => c.textContent)).toEqual([
    "15",
    "3",
    "—",
    "—",
    "—",
  ]);
});

it("draws the applied ÷ built rate from the server's counts", async () => {
  vi.mocked(getSourceYield).mockResolvedValue({
    sources: { ashby: { built: 4, applied: 1 } },
  });
  render(<SourceYield boards={BOARDS} />);
  const table = screen.getByRole("region", {
    name: "Discovery yield per source",
  });
  expect(await within(table).findByText("25%")).toBeDefined();
});
