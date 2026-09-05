import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GRID_TEMPLATE, QueueRowItem } from "../components/QueueRowItem";
import { formatScore } from "../lib/format";
import { queueRow } from "../test/rows";

/*
 * jsdom has NO layout: it computes no track widths, so a tier change cannot be measured here and
 * asserting on a rendered pixel would be asserting on zero. What IS checkable is the CLASS
 * CONTRACT — which templates exist and at which container widths they take over — and the cell
 * content that each tier moves between a column and the meta line.
 *
 * The container widths themselves are recorded in `QueueRowItem`'s own comment and were measured
 * in a browser; this file pins that the tiers exist and are ordered, not that a browser lays them
 * out a particular way.
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
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

import { getQueue } from "../api/client";
import { App } from "../App";

function renderRow(overrides = {}) {
  return render(
    <QueueRowItem
      row={queueRow(overrides)}
      rank={1}
      selected={false}
      active
      collapsing={false}
      onSelect={() => undefined}
      onApplied={() => undefined}
      onSkip={() => undefined}
      onReport={() => undefined}
    />,
  );
}

describe("the row's layout tiers", () => {
  it("carries a phone, a narrow, a middle and a wide template", () => {
    // The middle tier is the one the audit found unreachable: with the detail pane open the list
    // container is 864px at 1440 and 1184px at 2560, both under the 78rem wide-tier threshold, so
    // before this there was no tier between "title, score, verdict" and all eight columns.
    expect(GRID_TEMPLATE).toContain("@min-[40rem]:grid-cols-[");
    expect(GRID_TEMPLATE).toContain("@min-[52rem]:grid-cols-[");
    expect(GRID_TEMPLATE).toContain("@min-[78rem]:grid-cols-[");
  });

  it("gives the middle tier five fixed-or-fr tracks and no content-based one", () => {
    const middle = /@min-\[52rem\]:grid-cols-\[([^\]]+)\]/.exec(GRID_TEMPLATE)?.[1];
    expect(middle).toBeDefined();
    const tracks = (middle ?? "").split("_");
    // title · location · score · verdict · actions
    expect(tracks).toHaveLength(5);
    // The fixed-track rule from the comment block: an `auto` or a `min-content` track resolves to
    // a different width on every row, which is the one thing a row layout must never do.
    expect(middle).not.toContain("auto");
    expect(middle).not.toContain("min-content");
    expect(middle).not.toContain("max-content");
  });

  it("stops capping the page at 110rem, so the wide tier is reachable on a 27-inch display", () => {
    vi.mocked(getQueue).mockReturnValue(new Promise(() => undefined));
    render(<App />);
    const main = document.getElementById("view");
    expect(main).not.toBeNull();
    // 110rem = 1760px left 400px of dead margin each side at 2560 AND put the list container
    // under the wide tier's threshold whenever the pane was open.
    expect(main?.className).not.toContain("max-w-[110rem]");
    expect(main?.className).toContain("max-w-[160rem]");
  });
});

describe("the location cell", () => {
  it("shows the primary location and how many more the posting carries", () => {
    renderRow({ location: "Austin, TX", locations: ["Austin, TX", "Remote"] });
    screen.getAllByText("Austin, TX");
    screen.getAllByText("+1");
  });

  it("puts the whole list in the title attribute, so nothing is destroyed by truncation", () => {
    const { container } = renderRow({
      location: "Austin, TX",
      locations: ["Austin, TX", "Remote"],
    });
    const titled = Array.from(container.querySelectorAll("[title]")).map((element) =>
      element.getAttribute("title"),
    );
    expect(titled).toContain("Austin, TX, Remote");
  });

  it("renders an em dash when the posting carries no location at all", () => {
    renderRow({ location: null, locations: [] });
    screen.getAllByText("—");
    expect(screen.queryByText(/^\+\d+$/)).toBeNull();
  });
});

describe("the score cell", () => {
  it("prints two decimals, because every live row read 0.9 or 1.0 at one", () => {
    expect(formatScore(0.9)).toBe("0.90");
    expect(formatScore(1)).toBe("1.00");
  });

  it("explains itself with the server's own `why`, never with an inferred reason", () => {
    const why = "target company (+0.30), title match (+0.25)";
    const { container } = renderRow({ score: 0.9, why });
    const cell = Array.from(container.querySelectorAll("[title]")).find(
      (element) => element.textContent === "0.90",
    );
    expect(cell?.getAttribute("title")).toBe(why);
  });

  it("falls back to the plain caption when the server sent no `why`", () => {
    const { container } = renderRow({ score: 0.9, why: null });
    const cell = Array.from(container.querySelectorAll("[title]")).find(
      (element) => element.textContent === "0.90",
    );
    expect(cell?.getAttribute("title")).toBe("Score, as of now.");
  });
});
