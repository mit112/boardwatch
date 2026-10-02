import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Mark-applied's undo. The other two write paths (skip, report) each call an inverse route and
 * only then put the row back; applied did neither — it restored the row locally and said so in
 * copy, because the client had no `unapplied` call even though the server routes one.
 *
 * The property under test is therefore the SAME one `queueMutations.test.tsx` pins for skip and
 * report, and the second test is the half that is easy to leave out: an undo whose write FAILS
 * must not put the row back, or the page shows a lead the store still has an application record
 * for.
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

import { getQueue, markApplied, unapply } from "../api/client";
import { App } from "../App";

const COLLAPSE_MS = 200;

function dataRows(): HTMLElement[] {
  return within(screen.getByRole("grid", { name: "Jobs to explore" }))
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"));
}

function titles(): string[] {
  return dataRows().map((row) => within(row).getByText(/Engineer|Analyst/).textContent ?? "");
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

async function applyFirstRow() {
  const a = queueRow({ company: "Globex", title: "Backend Engineer" });
  const b = queueRow({ company: "Initech", title: "Analyst" });
  vi.mocked(getQueue).mockResolvedValue(queueResponse([a, b]));
  vi.mocked(markApplied).mockResolvedValue({ outcome: "created", job_id: a.job_id });
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  const row = within(screen.getByRole("grid", { name: "Jobs to explore" }))
    .getByText("Backend Engineer")
    .closest('[role="row"]');
  if (row === null) throw new Error("no row for the first job");
  fireEvent.keyDown(row, { key: "a" });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(COLLAPSE_MS);
  });
  expect(titles()).toEqual(["Analyst"]);
  return a;
}

describe("mark-applied undo", () => {
  it("calls unapply and restores the row", async () => {
    const a = await applyFirstRow();
    vi.mocked(unapply).mockResolvedValue({ outcome: "unchanged", job_id: a.job_id });

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // The write, not just a local restore: this is what makes the toast's promise true.
    expect(vi.mocked(unapply)).toHaveBeenCalledWith(a.posting_id);
    expect(titles()).toEqual(["Backend Engineer", "Analyst"]);
  });

  it("says what happened, in the past tense, with an Undo beside it", async () => {
    await applyFirstRow();
    // Past tense, and the company: it says what actually happened, once the server said so.
    const toast = screen.getByText("Application recorded for Globex.");
    expect(toast).toBeTruthy();
    // And the control it offers is the undo, by name.
    expect(screen.getByRole("button", { name: "Undo" })).toBeTruthy();
  });

  it("leaves the row out and shows an error toast when unapply fails", async () => {
    await applyFirstRow();
    vi.mocked(unapply).mockRejectedValue(new Error("500 from /api/queue/1/unapplied"));

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Restoring here would put a row back in a queue whose store still records the application.
    expect(titles()).toEqual(["Analyst"]);
    expect(screen.getByText("500 from /api/queue/1/unapplied")).toBeTruthy();
  });
});
