import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * The queue's only write path: `act()` in `QueuePage.tsx`. Both flows here are promise-guarded, so
 * — like the load and poll — no error boundary is in play; the correctness lives in a `.then`, a
 * `.catch`, and an optimistic removal that a failure must undo.
 *
 * Fake timers throughout, because the removal is scheduled behind a `COLLAPSE_MS` animation and
 * the write resolves asynchronously; advancing them inside `act` keeps every state update wrapped
 * and lets the reject in 2b land AFTER the optimistic removal, exactly as a real slow network does.
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

// Imported AFTER the mock factory, which vitest hoists above both.
import { getQueue, markApplied, markSkipped, unskip } from "../api/client";
import { App } from "../App";

// Mirrors QueuePage's collapse animation length. Advanced past, never asserted on.
const COLLAPSE_MS = 200;

function dataRows(): HTMLElement[] {
  return within(screen.getByRole("grid", { name: "Queue" }))
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

async function renderWithTwoRows() {
  const a = queueRow({ company: "Globex", title: "Backend Engineer" });
  const b = queueRow({ company: "Initech", title: "Analyst" });
  vi.mocked(getQueue).mockResolvedValue(queueResponse([a, b]));
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(dataRows()).toHaveLength(2);
  return { a, b };
}

describe("QueuePage write flows", () => {
  it("skip resolves: the row leaves, and its undo toast calls unskip and restores it", async () => {
    const { a } = await renderWithTwoRows();
    vi.mocked(markSkipped).mockResolvedValue({ outcome: "skipped" });
    vi.mocked(unskip).mockResolvedValue({ outcome: "unskipped" });

    fireEvent.click(screen.getByRole("button", { name: "Skip: Backend Engineer at Globex" }));

    // The write resolves and the row collapses out of the list.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(COLLAPSE_MS);
    });
    expect(vi.mocked(markSkipped)).toHaveBeenCalledWith(a.posting_id);
    expect(titles()).toEqual(["Analyst"]);

    // The toast IS the undo window. Its undo action calls `unskip` and puts the row back.
    expect(screen.getByText("Skipped Globex — Backend Engineer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(unskip)).toHaveBeenCalledWith(a.posting_id);
    expect(titles()).toEqual(["Backend Engineer", "Analyst"]);
  });

  it("mark-applied rejects: the row is restored and an error toast is pushed", async () => {
    const { a } = await renderWithTwoRows();
    // A deferred write, rejected only AFTER the optimistic removal — the real order of a slow
    // network, and the order the restore-on-failure `.catch` must handle.
    let failApplied: (reason: unknown) => void = () => undefined;
    const pending = new Promise<never>((_resolve, reject) => {
      failApplied = reject;
    });
    pending.catch(() => undefined); // no unhandled rejection before the component consumes it
    vi.mocked(markApplied).mockReturnValue(pending);

    fireEvent.click(
      screen.getByRole("button", { name: "Mark applied: Backend Engineer at Globex" }),
    );

    // Optimistic removal first: the row is gone while the write is still in flight.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(COLLAPSE_MS);
    });
    expect(vi.mocked(markApplied)).toHaveBeenCalledWith(a.posting_id);
    expect(titles()).toEqual(["Analyst"]);

    // Now the write fails. Removing the `restore(row.posting_id)` in the `.catch` leaves the row
    // gone forever, so this is where that guard is proven.
    await act(async () => {
      failApplied(new Error("409 from /api/applied"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(titles()).toEqual(["Backend Engineer", "Analyst"]);
    expect(screen.getByText("409 from /api/applied")).toBeTruthy();
  });
});
