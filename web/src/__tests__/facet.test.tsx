import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The status-band verdict facet. Two properties carry it, and each test below is written so it
 * fails against the way this feature is easy to get wrong:
 *
 *  1. A facet reaches BOTH lanes. A review-lane lead can be `eligible` — held only for its
 *     location — so "show only eligible" that skipped the review list would hide real appliable
 *     work. This is the documented "make the review list look empty for a matching filter" failure.
 *     Turning a facet on therefore shows BOTH lists (All jobs), so what is on screen is what the
 *     number that was clicked counted.
 *  2. The band's own counts are computed BEFORE the facet, so switching from one facet straight to
 *     another works: clicking `eligible` must not drop the `uncertain` cell to zero, which is the
 *     cell the reader clicks next.
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

/** A queue whose two lanes each hold eligible and uncertain leads, with named, exact titles. */
function twoLaneQueue() {
  return queueResponse(
    [
      queueRow({ verdict: "eligible", title: "APPLY-ELIGIBLE" }),
      queueRow({ verdict: "eligible", title: "APPLY-ELIGIBLE-2" }),
      queueRow({ verdict: "uncertain", title: "APPLY-UNCERTAIN" }),
      queueRow({ verdict: "uncertain", title: "APPLY-UNCERTAIN-2" }),
      queueRow({ verdict: "uncertain", title: "APPLY-UNCERTAIN-3" }),
    ],
    [
      // The load-bearing row: eligible AND in the review lane — the appliable-abroad case.
      queueRow({
        verdict: "eligible",
        title: "REVIEW-ELIGIBLE",
        location: "Toronto, Ontario, Canada",
        review_reason: "non_us_location",
      }),
      queueRow({ verdict: "uncertain", title: "REVIEW-UNCERTAIN", review_reason: "role_vetoed" }),
    ],
  );
}

/** Whether a grid currently renders a row with this exact title. */
function hasRow(grid: HTMLElement, title: string): boolean {
  return within(grid).queryByText(title) !== null;
}

beforeEach(() => {
  vi.useRealTimers();
  vi.mocked(getQueue).mockResolvedValue(twoLaneQueue());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("verdict facet", () => {
  it("filters BOTH lanes to eligible, keeping the eligible review lead", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    // Both lists on one page, so the eligible review job is visible BEFORE the facet narrows it.
    fireEvent.click(screen.getByRole("button", { name: /^All jobs/ }));
    const review = screen.getByRole("grid", { name: "Needs review" });
    expect(hasRow(review, "REVIEW-ELIGIBLE")).toBe(true);
    expect(hasRow(review, "REVIEW-UNCERTAIN")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /^eligible 2 —/i }));

    // Apply lane: only eligible remains.
    const queue = screen.getByRole("grid", { name: "Jobs to explore" });
    expect(hasRow(queue, "APPLY-ELIGIBLE")).toBe(true);
    expect(hasRow(queue, "APPLY-UNCERTAIN")).toBe(false);
    // Review lane: the eligible lead is STILL shown; the uncertain one is gone. This is the
    // assertion that fails if the facet skips the review lane.
    const reviewAfter = screen.getByRole("grid", { name: "Needs review" });
    expect(hasRow(reviewAfter, "REVIEW-ELIGIBLE")).toBe(true);
    expect(hasRow(reviewAfter, "REVIEW-UNCERTAIN")).toBe(false);
  });

  it("leaves the uncertain band count intact after clicking eligible", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    // The uncertain cell reads 3 up front, and the accessible name carries the number.
    expect(screen.getByRole("button", { name: /^uncertain 3 —/i })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^eligible 2 —/i }));

    // Still 3 — the facet is applied after the counts, so the cell the reader clicks next has not
    // dropped to zero. If the facet were folded into `filtered`, this would read "uncertain 0".
    expect(screen.getByRole("button", { name: /^uncertain 3 —/i })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^eligible 2 —/i }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("clears the facet from the Reset filters control", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    fireEvent.click(screen.getByRole("button", { name: /^eligible 2 —/i }));
    expect(hasRow(screen.getByRole("grid", { name: "Jobs to explore" }), "APPLY-UNCERTAIN")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));

    expect(hasRow(screen.getByRole("grid", { name: "Jobs to explore" }), "APPLY-UNCERTAIN")).toBe(true);
    expect(
      screen.getByRole("button", { name: /^eligible 2 —/i }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("REVIEW shows the review list alone and hides the apply list", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });

    fireEvent.click(screen.getByRole("button", { name: /^review 2 —/i }));

    // Apply queue gone entirely; this fails if REVIEW is treated as a verdict filter.
    expect(screen.queryByRole("grid", { name: "Jobs to explore" })).toBeNull();
    expect(screen.queryByText("APPLY-ELIGIBLE")).toBeNull();
    // Whole review lane shown — both verdicts, since REVIEW selects the lane, not a verdict.
    const review = screen.getByRole("grid", { name: "Needs review" });
    expect(hasRow(review, "REVIEW-ELIGIBLE")).toBe(true);
    expect(hasRow(review, "REVIEW-UNCERTAIN")).toBe(true);
    // "Showing X of Y" re-scoped to the review list (2 of 2) and says so, not the apply list (5).
    expect(screen.getByText("Showing 2 of 2 in Needs review")).toBeTruthy();
  });

  it("choosing Jobs to explore restores the apply list after REVIEW", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    fireEvent.click(screen.getByRole("button", { name: /^review 2 —/i }));
    expect(
      screen.getByRole("button", { name: /^review 2 —/i }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(screen.queryByRole("grid", { name: "Jobs to explore" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /^Jobs to explore/ }));

    expect(screen.getByRole("grid", { name: "Jobs to explore" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^review 2 —/i }).getAttribute("aria-pressed"),
    ).toBe("false");
  });
});
