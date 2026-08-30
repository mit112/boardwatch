import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueResponse } from "../api/types";
import { queueResponse, queueRow } from "../test/rows";

/*
 * QueuePage's async load and background poll, where the bug class is different from the render
 * boundaries next door: a throw INSIDE a promise is invisible to a React error boundary, so these
 * paths are guarded by `?? []` normalisation and by `.catch`, never by containment (see the
 * `adopt` comment in `QueuePage.tsx`). Each test drives a real load or a real poll and checks the
 * guard held — an unnormalised `review` would land in the load `.catch` and paint a transport
 * failure that is not true, and a swallowed poll must not wipe state the reader is looking at.
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
import { getQueue } from "../api/client";
import { App } from "../App";

// Mirrors QueuePage's own poll interval. Advanced past, never asserted on — so this is not the
// vacuous "assert a shared constant" trap; the test needs a duration long enough to fire the tick.
const POLL_MS = 30_000;

/** The data rows of one grid: `role="row"` also matches the sticky header row. */
function dataRows(grid: HTMLElement): HTMLElement[] {
  return within(grid)
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"));
}

/** The shape a viewer older than the lane split actually sends: no `review` key at all. */
function withoutReview(response: QueueResponse): QueueResponse {
  const copy = { ...response };
  delete (copy as { review?: unknown }).review;
  return copy;
}

beforeEach(() => {
  // 1a/1b use real timers and RTL's `findBy`; only the poll test opts into fake timers.
  vi.useRealTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("QueuePage load", () => {
  it("renders the apply lane and no error card when the server omits `review`", async () => {
    const apply = [queueRow(), queueRow(), queueRow()];
    // No `review` key — exactly the older-server payload the `?? []` in `adopt` exists for. If that
    // guard is removed, spreading `undefined` throws inside the load promise, the `.catch` paints
    // the load-failure card, and BOTH assertions below flip.
    vi.mocked(getQueue).mockResolvedValue(withoutReview(queueResponse(apply)));

    render(<App />);

    const grid = await screen.findByRole("grid", { name: "Queue" });
    expect(dataRows(grid)).toHaveLength(apply.length);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the transport message in an alert card when the load rejects", async () => {
    vi.mocked(getQueue).mockRejectedValue(new Error("503 from /api/queue"));

    render(<App />);

    // `role="alert"`, carrying what the transport said verbatim. Remove the load `.catch` and this
    // card never appears.
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("503 from /api/queue")).toBeTruthy();
    expect(screen.queryByRole("grid", { name: "Queue" })).toBeNull();
  });
});

describe("QueuePage background poll", () => {
  it("keeps the pending 'N new' count when a later poll rejects", async () => {
    vi.useFakeTimers();
    const a = queueRow();
    const b = queueRow();
    const c = queueRow();
    vi.mocked(getQueue)
      .mockResolvedValueOnce(queueResponse([a, b])) // initial load
      .mockResolvedValueOnce(queueResponse([a, b, c])) // first poll: c is new
      .mockRejectedValueOnce(new Error("poll transport blew up")); // second poll: fails

    render(<App />);
    // Flush the initial load promise so the grid is populated and `knownIds` holds a and b.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(dataRows(screen.getByRole("grid", { name: "Queue" }))).toHaveLength(2);

    // First poll: one unseen posting surfaces the quiet "1 new" indicator.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    expect(screen.getByText(/\b1 new\b/)).toBeTruthy();

    // Second poll REJECTS. The poll `.catch` swallows it deliberately; the indicator the reader is
    // looking at must survive. If that catch cleared `newCount`/`stashed`, this assertion fails.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    expect(screen.getByText(/\b1 new\b/)).toBeTruthy();
  });
});
