import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The lists a job is sorted into by how it gets applied to, and what each leaves out.
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

/* The owner's rulings, spelled out as rows: expected membership is written by hand per row. */
const ROWS = [
  queueRow({ title: "AUTO-UNGATED", apply_route: "auto" }),
  queueRow({ title: "AUTO-GATED", apply_route: "auto" }),
  queueRow({ title: "HAND-UNGATED", apply_route: "hand" }),
  queueRow({ title: "LINK-GATED", apply_route: "unresolved" }),
];
const REVIEW = [
  queueRow({
    title: "REVIEW-AUTO",
    apply_route: "auto",
    review_reason: "unevaluated",
  }),
];
const MOVED = [queueRow({ title: "MOVED", apply_route: "hand" })];

function response(routes: { configured: boolean; problem: string | null }) {
  const base = queueResponse(ROWS, REVIEW);
  return { ...base, manual: MOVED, apply_routes: routes };
}

const ON = { configured: true, problem: null };

function listed(): string[] {
  const titles = ["AUTO-UNGATED", "AUTO-GATED", "HAND-UNGATED", "LINK-GATED", "REVIEW-AUTO", "MOVED"];
  return titles.filter((title) => screen.queryByText(title) !== null);
}

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the route lists", () => {
  it.each([
    ["Auto-apply", 3, ["AUTO-UNGATED", "AUTO-GATED", "REVIEW-AUTO"]],
    ["Apply by hand", 2, ["HAND-UNGATED", "MOVED"]],
    ["Link not resolved", 1, ["LINK-GATED"]],
    ["All jobs", 6, ["AUTO-UNGATED", "AUTO-GATED", "HAND-UNGATED", "LINK-GATED", "REVIEW-AUTO", "MOVED"]],
  ])("%s holds its %i jobs", async (label, count, titles) => {
    vi.mocked(getQueue).mockResolvedValue(response(ON));
    render(<App />);
    await screen.findByText("MOVED");

    const tab = screen.getByRole("button", { name: new RegExp(`^${label}`) });
    expect(tab.getAttribute("aria-label")).toBe(`${label} ${String(count)}`);
    fireEvent.click(tab);
    expect(listed()).toEqual(titles);
    expect(screen.getByText(`Showing ${String(count)} of ${String(count)} in ${label}`)).toBeTruthy();
  });

  it("keeps Needs review as a filter that works inside a route list", async () => {
    vi.mocked(getQueue).mockResolvedValue(response(ON));
    render(<App />);
    await screen.findByText("MOVED");

    fireEvent.click(screen.getByRole("button", { name: /^Auto-apply/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Needs review 1/ }));
    expect(listed()).toEqual(["REVIEW-AUTO"]);
    fireEvent.click(screen.getByRole("button", { name: /^Needs review 1/ }));
    expect(listed()).toEqual(["AUTO-UNGATED", "AUTO-GATED", "REVIEW-AUTO"]);
  });

  it("keeps the review filter visible and resettable when no review job is left", async () => {
    window.sessionStorage.setItem("boardwatch.queue.reviewOnly", "1");
    vi.mocked(getQueue).mockResolvedValue({ ...queueResponse(ROWS), apply_routes: ON });
    render(<App />);

    const chip = await screen.findByRole("button", { name: /^Needs review 0/ });
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    expect(listed()).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(listed()).toEqual(["AUTO-UNGATED", "AUTO-GATED", "HAND-UNGATED", "LINK-GATED"]);
  });

  it("does not fold a job under a similar one in another list", async () => {
    const twins = [
      queueRow({ title: "SAME-ROLE", company: "Twin Co", apply_route: "auto" }),
      queueRow({ title: "SAME-ROLE", company: "Twin Co", apply_route: "hand" }),
    ];
    vi.mocked(getQueue).mockResolvedValue({ ...queueResponse(twins), apply_routes: ON });
    window.sessionStorage.setItem("boardwatch.queue.hideSimilar", "1");
    render(<App />);
    await screen.findAllByText("SAME-ROLE");

    fireEvent.click(screen.getByRole("button", { name: /^Apply by hand/ }));
    expect(screen.getAllByText("SAME-ROLE")).toHaveLength(1);
  });

  it("offers only the plain lists on a machine with no routing, the fresh-machine path", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse(ROWS, REVIEW));
    render(<App />);
    await screen.findByText("AUTO-GATED");

    expect(screen.queryByRole("button", { name: /^Auto-apply/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Link not resolved/ })).toBeNull();
    expect(screen.getByRole("button", { name: /^Apply by hand/ })).toBeTruthy();
  });

  it("says so out loud when a routing file could not be read", async () => {
    vi.mocked(getQueue).mockResolvedValue(
      response({ configured: true, problem: "links.json: broken" }),
    );
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toContain("links.json: broken");
  });
});
