import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Whether the review lane starts open.
 *
 * Collapsed-by-default is right while there is an apply queue to work down — the lane is folded,
 * not hidden, and the count is always visible. It is wrong when the apply lane is EMPTY: the page
 * then opens on a placeholder above a closed section, and the reader clicks "show" every single
 * day the engine version moves. The stored preference outranks both, so the choice survives a
 * Runs→Queue round trip and a reload.
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

describe("the review lane's open state", () => {
  it("starts EXPANDED when the apply lane is empty", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([], REVIEW));
    render(<App />);

    // No "show" click: the rows must be on screen as the page settles.
    expect(await screen.findByRole("grid", { name: "Review" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "hide" })).toBeTruthy();
  });

  it("stays COLLAPSED when the apply lane has rows", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    expect(screen.queryByRole("grid", { name: "Review" })).toBeNull();
    expect(screen.getByRole("button", { name: "show" })).toBeTruthy();
  });

  it("lets a stored `false` beat the empty-lane default", async () => {
    window.sessionStorage.setItem("boardwatch.review-open", "false");
    vi.mocked(getQueue).mockResolvedValue(queueResponse([], REVIEW));
    render(<App />);
    await screen.findByRole("button", { name: "show" });

    // The reader closed it on purpose; the default must not reopen it under them.
    expect(screen.queryByRole("grid", { name: "Review" })).toBeNull();
  });

  it("lets a stored `true` open it while the apply lane has rows", async () => {
    window.sessionStorage.setItem("boardwatch.review-open", "true");
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    render(<App />);

    expect(await screen.findByRole("grid", { name: "Review" })).toBeTruthy();
  });

  it("records the toggle, so the next mount honours it", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    const view = render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByRole("button", { name: "show" }));
    expect(window.sessionStorage.getItem("boardwatch.review-open")).toBe("true");
    view.unmount();

    render(<App />);
    expect(await screen.findByRole("grid", { name: "Review" })).toBeTruthy();
  });
});
