import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Sorting by job board, through the page rather than through `lib/sort`.
 *
 * `sort.test.tsx` covers the comparator; what is only reachable from here is the WIRING — that
 * the control is on screen with a name, and that choosing it re-orders the real list. The owner
 * applies in batches by board, so what the sort has to produce is blocks.
 *
 * Nothing here touches the hash: sort lives in `sessionStorage` (`QUEUE_KEYS.sort`).
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getApplied: vi.fn(),
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

describe("sorting by job board", () => {
  // Interleaved, so neither the delivered order nor a plain reversal of it can pass for a sort.
  const rows = [
    queueRow({ title: "Alpha Engineer", provider: "workday" }),
    queueRow({ title: "Bravo Engineer", provider: "greenhouse" }),
    queueRow({ title: "Charlie Engineer", provider: "workday" }),
  ];

  it("groups the list into job-board blocks, each still in the delivered order", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse(rows));
    render(<App />);

    const grid = await screen.findByRole("grid", { name: "Jobs to explore" });
    // Delivered order: the ranker's, which interleaves the two boards.
    expect(dataRows(grid).map((row) => row.textContent)).toEqual([
      expect.stringContaining("Alpha Engineer"),
      expect.stringContaining("Bravo Engineer"),
      expect.stringContaining("Charlie Engineer"),
    ]);

    // Found by its label, not by a test id: if the control cannot be named it cannot be used.
    fireEvent.change(screen.getByRole("combobox", { name: "Sort by" }), {
      target: { value: "provider:asc" },
    });

    // Ascending by board name: `greenhouse` leads, then the `workday` block with Alpha before
    // Charlie — the order INSIDE a block is the delivered one and is never reversed.
    expect(dataRows(grid).map((row) => row.textContent)).toEqual([
      expect.stringContaining("Bravo Engineer"),
      expect.stringContaining("Alpha Engineer"),
      expect.stringContaining("Charlie Engineer"),
    ]);
  });
});
