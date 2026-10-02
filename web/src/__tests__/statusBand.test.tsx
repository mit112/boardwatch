import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The page's `role="status"` readout and the pipeline band's `closed` and lane-copy cells.
 *
 * The readout counted ONE lane, so the day the apply lane emptied and every delivered lead landed
 * in review the page said "Showing 0 of 0" directly above 149 listed leads — the single most
 * load-bearing sentence on the page contradicting the list under it. It now names the list it
 * counts ("… in Needs review"), and counts exactly the rows that list shows: a count that does not
 * say which population it is over invites adding it to another one.
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

    // The apply list is empty, so the page opens on the list that has the work — and says so.
    expect(await screen.findByText("Showing 3 of 3 in Needs review")).toBeTruthy();
  });

  it("narrows with the text filter", async () => {
    vi.mocked(getQueue).mockResolvedValue(emptyApplyLane());
    render(<App />);
    await screen.findByText("Showing 3 of 3 in Needs review");

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "ALPHA" },
    });

    // The denominator is the page's whole population, so the reader can see how much was hidden.
    expect(screen.getByText("Showing 1 of 3 in Needs review")).toBeTruthy();
  });

  it("counts each list on its own, and both together only under All jobs", async () => {
    vi.mocked(getQueue).mockResolvedValue(
      queueResponse(
        [queueRow({ title: "APPLY-ONE" }), queueRow({ title: "APPLY-TWO" })],
        [queueRow({ title: "REVIEW-ONE", review_reason: "unevaluated" })],
      ),
    );
    render(<App />);

    // Jobs to explore holds two; the review job is NOT folded into that number.
    expect(await screen.findByText("Showing 2 of 2 in Jobs to explore")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^Needs review/ }));
    expect(screen.getByText("Showing 1 of 1 in Needs review")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^All jobs/ }));
    expect(screen.getByText("Showing 3 of 3 in All jobs")).toBeTruthy();
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
    await screen.findByText("Showing 3 of 3 in Needs review");

    const cell = screen.getByTitle(/took the posting down/i);
    expect(cell.textContent).toBe("12");
  });
});

describe("the lane-copy cell", () => {
  it("reports leads held as lane copies, passed through from the server", async () => {
    const response = emptyApplyLane();
    vi.mocked(getQueue).mockResolvedValue({
      ...response,
      counts: { ...response.counts, lane_copy: 3 },
    });
    render(<App />);
    await screen.findByText("Showing 3 of 3 in Needs review");

    const cell = screen.getByTitle(/employer-board twin/i);
    expect(cell.textContent).toBe("3");
  });
});
