import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The status band's FINAL-GATE facet, built on the mechanism the verdict facet (D-377) and the
 * lane facet (D-378) already use. Each test below is written so it fails against the way this
 * feature is easy to get wrong:
 *
 *  1. It filters on `judge_verdict`, NOT on `verdict`. Every row in the fixture below carries the
 *     rules verdict `eligible`, so an implementation that read the wrong field shows all of them
 *     for every cell.
 *  2. `not judged` is `judge_verdict == null` exactly. An implementation that treated it as "not
 *     gate-eligible" pulls the uncertain lead in too.
 *  3. The counts stay facet-blind, so clicking one cell does not drop the cell the reader clicks
 *     next to zero.
 *  4. A gate facet reaches BOTH lanes, exactly as a verdict facet does.
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

/**
 * Every row reads `eligible` to the RULES engine; only the gate distinguishes them. That is what
 * makes each assertion below discriminating rather than a restatement of the verdict facet.
 */
function gateQueue() {
  return queueResponse(
    [
      queueRow({ verdict: "eligible", judge_verdict: "eligible", title: "GATE-CLEAR" }),
      queueRow({ verdict: "eligible", judge_verdict: "eligible", title: "GATE-CLEAR-2" }),
      queueRow({ verdict: "eligible", judge_verdict: "uncertain", title: "GATE-UNSURE" }),
      queueRow({ verdict: "eligible", judge_verdict: null, title: "GATE-SILENT" }),
    ],
    [
      // A review-lane lead the gate also read as uncertain. A gate facet must reach it, for the
      // reason a verdict facet must: dropping it is the documented "make the review list look
      // empty for a matching filter" failure.
      queueRow({
        verdict: "eligible",
        judge_verdict: "uncertain",
        title: "REVIEW-UNSURE",
        review_reason: "non_us_location",
      }),
    ],
  );
}

function hasRow(grid: HTMLElement, title: string): boolean {
  return within(grid).queryByText(title) !== null;
}

beforeEach(() => {
  vi.useRealTimers();
  vi.mocked(getQueue).mockResolvedValue(gateQueue());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the final-gate facet", () => {
  it("counts the gate's three buckets over the apply lane, apart from the rules verdict", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    // All four apply rows are rules-`eligible`; the gate splits them 2 / 1 / 1. An
    // implementation reading `verdict` reports "gate eligible 4".
    expect(screen.getByRole("button", { name: /^eligible 4 —/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^gate eligible 2 —/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^gate uncertain 1 —/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^not judged 1 —/i })).toBeTruthy();
  });

  it("filters BOTH lanes to the gate's uncertain, keeping the uncertain review lead", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(screen.getByRole("button", { name: "show" }));

    fireEvent.click(screen.getByRole("button", { name: /^gate uncertain 1 —/i }));

    const queue = screen.getByRole("grid", { name: "Queue" });
    expect(hasRow(queue, "GATE-UNSURE")).toBe(true);
    expect(hasRow(queue, "GATE-CLEAR")).toBe(false);
    expect(hasRow(queue, "GATE-SILENT")).toBe(false);
    // The review lane is reached too. This is the assertion that fails if the gate facet skips it.
    expect(hasRow(screen.getByRole("grid", { name: "Review" }), "REVIEW-UNSURE")).toBe(true);
  });

  it("shows the unjudged lead alone for not judged, never the gate-uncertain one", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByRole("button", { name: /^not judged 1 —/i }));

    const queue = screen.getByRole("grid", { name: "Queue" });
    expect(hasRow(queue, "GATE-SILENT")).toBe(true);
    // The discriminating pair: "not judged" is `judge_verdict == null`, not "not gate-eligible".
    // An implementation that inverted `judge_eligible` shows GATE-UNSURE here as well.
    expect(hasRow(queue, "GATE-UNSURE")).toBe(false);
    expect(hasRow(queue, "GATE-CLEAR")).toBe(false);
  });

  it("leaves the other gate counts intact after clicking one, and names the filter in words", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByRole("button", { name: /^gate eligible 2 —/i }));

    // Still 1 and 1 — the facet is applied AFTER the counts, so the cell the reader clicks next
    // has not dropped to zero. Folded into `filtered` these would both read 0.
    expect(screen.getByRole("button", { name: /^gate uncertain 1 —/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^not judged 1 —/i })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^gate eligible 2 —/i }).getAttribute("aria-pressed"),
    ).toBe("true");
    // The words the reader clicked, not the wire member: "judge_eligible only" is a field name.
    expect(screen.getByText("Showing gate eligible only.")).toBeTruthy();
  });

  it("clears the gate facet from the Show all control", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(screen.getByRole("button", { name: /^gate uncertain 1 —/i }));
    expect(hasRow(screen.getByRole("grid", { name: "Queue" }), "GATE-CLEAR")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Show all" }));

    expect(hasRow(screen.getByRole("grid", { name: "Queue" }), "GATE-CLEAR")).toBe(true);
    expect(
      screen.getByRole("button", { name: /^gate uncertain 1 —/i }).getAttribute("aria-pressed"),
    ).toBe("false");
  });
});
