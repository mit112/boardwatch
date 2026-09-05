import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The REASON facet. Every review row already carried a reason chip and nothing could filter by
 * one, so on a 149-lead lane the chips were nine repeating labels the reader had to scan past
 * rather than a control.
 *
 * It composes with the verdict facet exactly as the verdict facet composes with the text box —
 * applied AFTER the band's counts, so the cell the reader clicks next has not dropped to zero —
 * and it takes the apply lane off the page the way the `review` facet does, because no apply-lane
 * row has a reason and an empty grid with a hint would be answering a question nobody asked.
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

function laneQueue() {
  return queueResponse(
    [queueRow({ title: "APPLY-ONE" }), queueRow({ title: "APPLY-TWO" })],
    [
      queueRow({ title: "UNEVAL-A", review_reason: "unevaluated", verdict: "eligible" }),
      queueRow({ title: "UNEVAL-B", review_reason: "unevaluated", verdict: "eligible" }),
      queueRow({ title: "UNEVAL-C", review_reason: "unevaluated", verdict: "uncertain" }),
      queueRow({ title: "ROLE-A", review_reason: "role_unconfirmed", verdict: "eligible" }),
      queueRow({ title: "ROLE-B", review_reason: "role_unconfirmed", verdict: "eligible" }),
    ],
  );
}

function reviewTitles(): string[] {
  return within(screen.getByRole("grid", { name: "Review" }))
    .getAllByRole("row")
    .filter((row) => row.hasAttribute("data-row-id"))
    .map((row) => within(row).getByText(/UNEVAL|ROLE/).textContent ?? "");
}

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
  vi.mocked(getQueue).mockResolvedValue(laneQueue());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the reason facet", () => {
  it("offers one chip per reason present, in count order, with its count", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    const chips = within(screen.getByRole("group", { name: /review reason/i })).getAllByRole(
      "button",
    );
    expect(chips.map((chip) => chip.getAttribute("aria-label"))).toEqual([
      "not evaluated 3 — show only these",
      "role unconfirmed 2 — show only these",
    ]);
  });

  it("filters the review list to that reason and takes the apply lane off the page", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByRole("button", { name: /^not evaluated 3 —/ }));

    // No "show" click: selecting a reason must open the lane it filters, or the page is a header.
    expect(reviewTitles()).toEqual(["UNEVAL-A", "UNEVAL-B", "UNEVAL-C"]);
    expect(screen.queryByRole("grid", { name: "Queue" })).toBeNull();
    expect(screen.queryByText("APPLY-ONE")).toBeNull();
  });

  it("composes with the verdict facet", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByRole("button", { name: /^not evaluated 3 —/ }));
    fireEvent.click(screen.getByRole("button", { name: /^eligible 2 —/i }));

    // Both filters, intersected: the uncertain unevaluated lead is gone, the role ones never were.
    expect(reviewTitles()).toEqual(["UNEVAL-A", "UNEVAL-B"]);
  });

  it("leaves the band's counts alone, so the next chip is still clickable", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByRole("button", { name: /^not evaluated 3 —/ }));

    // Computed before the facet, exactly like the verdict cells: `role unconfirmed` must not have
    // dropped to zero just because the list it counts is currently filtered away.
    expect(screen.getByRole("button", { name: /^role unconfirmed 2 —/ })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^not evaluated 3 —/ }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("clears on a second click, restoring the apply lane", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(screen.getByRole("button", { name: /^not evaluated 3 —/ }));
    expect(screen.queryByRole("grid", { name: "Queue" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /^not evaluated 3 — showing only these/ }));

    expect(screen.getByRole("grid", { name: "Queue" })).toBeTruthy();
    expect(reviewTitles()).toHaveLength(5);
  });

  it("offers no chips when the review lane is empty", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], []));
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    expect(screen.queryByRole("group", { name: /review reason/i })).toBeNull();
  });
});
