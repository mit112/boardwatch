import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { Companion } from "../api/types";

vi.mock("../api/client", () => ({ getCompanions: vi.fn() }));

import { getCompanions } from "../api/client";
import { CompanionHistory } from "../components/CompanionHistory";

function reviewer(history?: NonNullable<Companion["history"]>): Companion {
  const doc: Companion = {
    schema: "boardwatch.companion/1",
    name: "reviewer",
    updated_at: "2026-11-17T10:14:00+00:00",
    state: "failed",
    summary: "store write failed: scan lock held",
    counts: {},
    items: [],
  };
  return history === undefined ? doc : { ...doc, history };
}

it("draws one row per night and a dash for a count that night did not report", async () => {
  vi.mocked(getCompanions).mockResolvedValue({
    companions: [
      reviewer([
        { label: "2026-11-17", counts: { asked: 80, closed: 18 } },
        { label: "2026-11-16", counts: { asked: 74, agreed: 9 } },
      ]),
    ],
  });
  render(<CompanionHistory />);
  const table = await screen.findByRole("region", { name: "reviewer history" });
  expect(within(table).getByText(/store write failed/)).toBeDefined();
  const rows = within(table).getAllByRole("row");
  expect(rows.map((r) => r.textContent)).toEqual([
    "Nightaskedclosedagreed",
    "2026-11-178018—",
    "2026-11-1674—9",
  ]);
});

it("draws nothing for a companion with no history", async () => {
  vi.mocked(getCompanions).mockResolvedValue({ companions: [reviewer()] });
  const { container } = render(<CompanionHistory />);
  await Promise.resolve();
  expect(container.textContent).toBe("");
});
