import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The band's `role="status"` readout and its `closed` cell.
 *
 * The readout counted ONE lane, so the day the apply lane emptied and every delivered lead landed
 * in review the page said "Showing 0 of 0" directly above 149 listed leads — the single most
 * load-bearing sentence on the page contradicting the list under it. It must count what is
 * VISIBLE, which is both lanes whenever both are on screen.
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
  unapply: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

import { getQueue } from "../api/client";
import { App } from "../App";

/** The measured shape of the 2026-09-05 audit day: nothing appliable, everything in review. */
function emptyApplyLane() {
  return queueResponse(
    [],
    [
      queueRow({ title: "REVIEW-ALPHA", review_reason: "unevaluated" }),
      queueRow({ title: "REVIEW-BETA", review_reason: "unevaluated" }),
      queueRow({ title: "REVIEW-GAMMA", review_reason: "role_unconfirmed" }),
    ],
  );
}

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the status readout", () => {
  it("counts BOTH lanes when the apply lane is empty", async () => {
    vi.mocked(getQueue).mockResolvedValue(emptyApplyLane());
    render(<App />);

    // Three leads are on the page and every one of them is visible.
    expect(await screen.findByText(/Showing 3 of 3/)).toBeTruthy();
  });

  it("narrows with the text filter", async () => {
    vi.mocked(getQueue).mockResolvedValue(emptyApplyLane());
    render(<App />);
    await screen.findByText(/Showing 3 of 3/);

    fireEvent.change(screen.getByLabelText(/filter/i), { target: { value: "ALPHA" } });

    // The denominator is the page's whole population, so the reader can see how much was hidden.
    expect(screen.getByText(/Showing 1 of 3/)).toBeTruthy();
  });

  it("counts both lanes when both are populated", async () => {
    vi.mocked(getQueue).mockResolvedValue(
      queueResponse(
        [queueRow({ title: "APPLY-ONE" }), queueRow({ title: "APPLY-TWO" })],
        [queueRow({ title: "REVIEW-ONE", review_reason: "unevaluated" })],
      ),
    );
    render(<App />);

    expect(await screen.findByText(/Showing 3 of 3/)).toBeTruthy();
  });
});

describe("the closed cell", () => {
  it("reports postings the employer took down, beside ineligible", async () => {
    const response = emptyApplyLane();
    vi.mocked(getQueue).mockResolvedValue({
      ...response,
      counts: { ...response.counts, closed: 12 },
    });
    render(<App />);
    await screen.findByText(/Showing 3 of 3/);

    const cell = screen.getByTitle(/took the posting down/i);
    expect(cell.textContent).toBe("12");
  });
});
