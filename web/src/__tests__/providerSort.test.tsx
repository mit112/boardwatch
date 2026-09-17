import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The ATS header, through the page rather than through `lib/sort`.
 *
 * `sort.test.tsx` covers the comparator; what is only reachable from here is the WIRING — that
 * the affordance is on screen at all, that clicking it re-orders the real grid, and that the
 * columnheader it lives in reports the sort to a screen reader. The control was added to the
 * title | company cell because that is the column the ATS is rendered in, and a sort control
 * over a cell the reader is not looking at is exactly the hidden affordance the data-table
 * card refuses (`ux-table-sort-filter`).
 *
 * Nothing here touches the hash: sort lives in `sessionStorage` (`QUEUE_KEYS.sort`), not in
 * `useHashRoute`, so `provider` has no hash round-trip to honour.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
  markApplied: vi.fn(),
  markSkipped: vi.fn(),
  unskip: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

import { getQueue } from "../api/client";
import { App } from "../App";

/** The data rows of one grid: `role="row"` also matches the sticky header row. */
function dataRows(grid: HTMLElement): HTMLElement[] {
  return within(grid)
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"));
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.location.hash = "";
});

describe("the ATS column", () => {
  // Interleaved, so neither the delivered order nor a plain reversal of it can pass for a sort.
  const rows = [
    queueRow({ title: "Alpha Engineer", provider: "workday" }),
    queueRow({ title: "Bravo Engineer", provider: "greenhouse" }),
    queueRow({ title: "Charlie Engineer", provider: "workday" }),
  ];

  it("offers a visible sort control that groups the grid into ATS blocks", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse(rows));
    render(<App />);

    const grid = await screen.findByRole("grid", { name: "Queue" });
    // Delivered order: the ranker's, which interleaves the two providers.
    expect(dataRows(grid).map((row) => row.textContent)).toEqual([
      expect.stringContaining("Alpha Engineer"),
      expect.stringContaining("Bravo Engineer"),
      expect.stringContaining("Charlie Engineer"),
    ]);

    // Found by its accessible name, not by a test id: if it is not nameable it is not usable.
    fireEvent.click(screen.getByRole("button", { name: "ats" }));

    // Descending first, which is what `nextSort` gives every non-rank, non-age column — so the
    // `workday` block leads. Rank order inside a block is untouched: Alpha before Charlie.
    expect(dataRows(grid).map((row) => row.textContent)).toEqual([
      expect.stringContaining("Alpha Engineer"),
      expect.stringContaining("Charlie Engineer"),
      expect.stringContaining("Bravo Engineer"),
    ]);

    // The header cell the control sits in must SAY the table is sorted. Keyed on `title` alone,
    // this read `none` while the grid was in fact re-ordered — a screen reader told the table
    // was unsorted by the same markup that had just sorted it.
    const header = within(grid)
      .getAllByRole("columnheader")
      .find((cell) => within(cell).queryByRole("button", { name: "ats" }) !== null);
    expect(header?.getAttribute("aria-sort")).toBe("descending");
  });
});
