import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BAND_WIDE, StatusBand } from "../components/StatusBand";
import { queueResponse, queueRow } from "../test/rows";

/*
 * The band below 40rem. Ten cells at 44px-plus each stacked to 496px on a phone, so the whole
 * first screen was counters and the first lead was below the fold.
 *
 * The setup file's `matchMedia` stub answers `true` to everything, which pins every other spec at
 * the wide tier; this one swaps in a stub that answers `false` for the band's query alone, so the
 * narrow arrangement is exercised without moving any other breakpoint.
 */

const COUNTS = queueResponse([queueRow()], [queueRow({ review_reason: "unevaluated" })]).counts;

function renderBand() {
  return render(
    <StatusBand
      counts={COUNTS}
      showing={2}
      total={2}
      reviewNote="Held for a look, not blindly appliable."
      activeFacet={null}
      onToggleFacet={() => undefined}
    />,
  );
}

/* Bound so restoring it in `afterEach` cannot hand `matchMedia` a different `this`. */
const wideStub = window.matchMedia.bind(window);

beforeEach(() => {
  window.matchMedia = (query: string) =>
    ({
      matches: query !== BAND_WIDE,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
});

afterEach(() => {
  window.matchMedia = wideStub;
  vi.clearAllMocks();
});

describe("the status band below 40rem", () => {
  it("keeps in queue, eligible, review and the readout out, and folds the rest", () => {
    const { container } = renderBand();

    // The three that answer "is there work here", plus the one sentence that answers "did my
    // filter match anything".
    expect(screen.getByText("in queue")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^eligible /i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^review /i })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Showing 2 of 2");

    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(within(details as HTMLElement).getByText("more")).toBeTruthy();
    // Folded, not dropped: every remaining cell is inside the disclosure.
    const folded = [
      "uncertain",
      "ineligible",
      "closed",
      "applied ever",
      "skipped",
      "reported",
      "last run",
    ];
    for (const label of folded) {
      expect(within(details as HTMLElement).getByText(label)).toBeTruthy();
    }
  });

  it("renders each control exactly once, so no accessible name is ambiguous", () => {
    renderBand();

    // The failure a pure-CSS fold would have: the same cell in the DOM twice, one copy hidden.
    expect(screen.getAllByRole("button", { name: /^uncertain /i })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /^review /i })).toHaveLength(1);
  });

  it("draws one flat row at 40rem and above", () => {
    window.matchMedia = wideStub;
    const { container } = renderBand();

    expect(container.querySelector("details")).toBeNull();
    expect(screen.getByText("last run")).toBeTruthy();
  });
});
