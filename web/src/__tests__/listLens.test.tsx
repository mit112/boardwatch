import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Which list the page opens on: Jobs to explore (the apply lane), Needs review (the review lane),
 * or All jobs.
 *
 * Jobs to explore is right while there is an apply list to work down. It is wrong when that list
 * is EMPTY: the page would open on "nothing here" with the work one click away, every day the
 * engine version moves. So the default follows the work, and a stored choice outranks it — the
 * reader who picked a list did so on purpose, and it survives a tab round trip and a reload.
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

describe("which list the page opens on", () => {
  it("opens on Needs review when the apply list is empty", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([], REVIEW));
    render(<App />);

    // No click: the rows must be on screen as the page settles.
    expect(await screen.findByRole("grid", { name: "Needs review" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^Needs review/ }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("opens on Jobs to explore when it has rows, leaving the review list one click away", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });

    expect(screen.queryByRole("grid", { name: "Needs review" })).toBeNull();
    // Not hidden: the list's button carries its count, scoped by its own name.
    expect(screen.getByRole("button", { name: /^Needs review 2$/ })).toBeTruthy();
  });

  it("lets a stored choice beat the empty-list default", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "explore");
    vi.mocked(getQueue).mockResolvedValue(queueResponse([], REVIEW));
    render(<App />);
    await screen.findByText("No jobs to explore right now.", { exact: false });

    // The reader chose it on purpose; the default must not move them under their own hands.
    expect(screen.queryByRole("grid", { name: "Needs review" })).toBeNull();
  });

  it("shows both lists under a stored All jobs", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "all");
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    render(<App />);

    expect(await screen.findByRole("grid", { name: "Needs review" })).toBeTruthy();
    expect(screen.getByRole("grid", { name: "Jobs to explore" })).toBeTruthy();
  });

  it("ignores a stored list this bundle does not know, instead of showing nothing", async () => {
    window.sessionStorage.setItem("boardwatch.queue.lens", "a_list_from_a_newer_bundle");
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    render(<App />);

    expect(await screen.findByRole("grid", { name: "Jobs to explore" })).toBeTruthy();
  });

  it("records the choice, so the next mount honours it", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], REVIEW));
    const view = render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });

    fireEvent.click(screen.getByRole("button", { name: /^Needs review/ }));
    expect(window.sessionStorage.getItem("boardwatch.queue.lens")).toBe("review");
    view.unmount();

    render(<App />);
    expect(await screen.findByRole("grid", { name: "Needs review" })).toBeTruthy();
  });
});
