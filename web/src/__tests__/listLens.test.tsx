import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Which list the page opens on: All jobs, unless a stored choice names a list this machine offers.
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

const REVIEW = [
  queueRow({ title: "REVIEW-ALPHA", review_reason: "unevaluated" }),
  queueRow({ title: "REVIEW-BETA", review_reason: "role_unconfirmed" }),
];

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.clearAllMocks();
});

const ROUTED = { configured: true, gate_tracked: true, problem: null };

function routed(rows = [queueRow({ title: "AUTO-ROW", apply_route: "auto" })]) {
  return { ...queueResponse(rows, REVIEW), apply_routes: ROUTED };
}

describe("which list the page opens on", () => {
  it("opens on All jobs, with both lanes as sections", async () => {
    vi.mocked(getQueue).mockResolvedValue(routed());
    render(<App />);

    expect(await screen.findByRole("grid", { name: "Needs review" })).toBeTruthy();
    expect(screen.getByRole("grid", { name: "No check held these back" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^All jobs/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("honours a stored list", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "auto");
    vi.mocked(getQueue).mockResolvedValue(routed());
    render(<App />);

    expect(await screen.findByRole("grid", { name: "No check held these back" })).toBeTruthy();
    expect(screen.queryByRole("grid", { name: "Needs review" })).toBeNull();
  });

  it("carries a stored Apply by hand from before the route lists", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "manual");
    vi.mocked(getQueue).mockResolvedValue(routed());
    render(<App />);

    await screen.findByRole("grid", { name: "Needs review" });
    expect(
      screen.getByRole("button", { name: /^Apply by hand/ }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("ignores a stored list this bundle does not know, instead of showing nothing", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "a_list_from_a_newer_bundle");
    vi.mocked(getQueue).mockResolvedValue(routed());
    render(<App />);

    expect(await screen.findByRole("grid", { name: "No check held these back" })).toBeTruthy();
  });

  it("falls back to All jobs when a stored list is not offered on this machine", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "auto");
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow({ title: "PLAIN" })]));
    render(<App />);

    expect(await screen.findByRole("grid", { name: "No check held these back" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^All jobs/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("records the choice, so the next mount honours it", async () => {
    vi.mocked(getQueue).mockResolvedValue(routed());
    const view = render(<App />);
    await screen.findByRole("grid", { name: "No check held these back" });

    fireEvent.click(screen.getByRole("button", { name: /^Auto-apply/ }));
    expect(window.sessionStorage.getItem("boardwatch.queue.lens")).toBe("auto");
    view.unmount();

    render(<App />);
    await screen.findByRole("grid", { name: "No check held these back" });
    expect(
      screen.getByRole("button", { name: /^Auto-apply/ }).getAttribute("aria-pressed"),
    ).toBe("true");
  });
});
