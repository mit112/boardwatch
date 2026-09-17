import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * "New since last visit": the per-viewer watermark, and the facet it drives.
 *
 * The queue grows by 20-30 leads a night and the only way to find them was the run filter, which
 * needs the run number first. This answers it in one click, with no API change and no server-side
 * per-viewer state — the watermark is the highest `delivered_run_id` this browser saw the last
 * time the page loaded.
 *
 * Three properties carry it, and each test below is written against the way it is easy to get
 * wrong:
 *
 *  1. A FIRST visit marks nothing. An absent watermark read as `0` marks the whole queue new,
 *     permanently, on the one load where the reader cannot tell that is wrong.
 *  2. The watermark advances on load, and only AFTER the set is computed — otherwise the
 *     comparison is against its own answer and nothing is ever new.
 *  3. Storage that THROWS still renders the page. `localStorage` throws outright when it is
 *     disabled, and a viewer that cannot remember a visit must still be a viewer.
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

// Mirrors QueuePage's own poll interval, the way `queueLoad` does: advanced past, never asserted
// on, so this is not the vacuous "assert a shared constant" trap.
const POLL_MS = 30_000;

// The key `api/token.ts` writes. Spelled out here on purpose: a test that imported the private
// constant would pass against a rename that broke every already-stored watermark on disk.
const WATERMARK_KEY = "boardwatch.queue.watermark";

/** Three nights of deliveries: run 430 is what the reader has already seen, 431 and 432 are not. */
function threeRunQueue() {
  return queueResponse(
    [
      queueRow({ delivered_run_id: 430, title: "SEEN-430" }),
      queueRow({ delivered_run_id: 431, title: "FRESH-431" }),
      queueRow({ delivered_run_id: 432, title: "FRESH-432" }),
      // No run recorded at all. Not new, and — the discriminating half — it must not throw or be
      // swept in by a comparison that treats `null` as less than every watermark.
      queueRow({ delivered_run_id: null, title: "NO-RUN" }),
    ],
    [queueRow({ delivered_run_id: 432, title: "REVIEW-432", review_reason: "non_us_location" })],
  );
}

function hasRow(grid: HTMLElement, title: string): boolean {
  return within(grid).queryByText(title) !== null;
}

/* `localStorage` is NOT cleared by the shared setup — only `sessionStorage` is — because the token
   lives there and its own specs manage it. This watermark does too, so this file clears it. */
beforeEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
  vi.mocked(getQueue).mockResolvedValue(threeRunQueue());
});

afterEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe("new since last visit", () => {
  it("is the leads delivered after the stored watermark, in both lanes", async () => {
    window.localStorage.setItem(WATERMARK_KEY, "430");

    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(screen.getByRole("button", { name: "show" }));

    // Two apply-lane leads on runs 431 and 432; the count is the apply lane, like `eligible`.
    fireEvent.click(screen.getByRole("button", { name: /^new since last visit 2 —/i }));

    const queue = screen.getByRole("grid", { name: "Queue" });
    expect(hasRow(queue, "FRESH-431")).toBe(true);
    expect(hasRow(queue, "FRESH-432")).toBe(true);
    // The two that must NOT be in the set: one delivered at the watermark (strictly greater, not
    // greater-or-equal) and one with no run at all.
    expect(hasRow(queue, "SEEN-430")).toBe(false);
    expect(hasRow(queue, "NO-RUN")).toBe(false);
    // The review lane is reached too, exactly as every other row-level facet reaches it.
    expect(hasRow(screen.getByRole("grid", { name: "Review" }), "REVIEW-432")).toBe(true);
  });

  it("marks NOTHING new on a first visit, with no watermark stored", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    // Zero, not five. An absent watermark read as `0` reports every lead in the payload.
    expect(screen.getByRole("button", { name: /^new since last visit 0 —/i })).toBeTruthy();
  });

  it("advances the stored watermark to the highest run on the page, after computing the set", async () => {
    window.localStorage.setItem(WATERMARK_KEY, "430");

    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    // 432 — the highest `delivered_run_id` in either lane. And the set was computed first: the
    // cell still reads 2, which it could not if the watermark had advanced before the comparison.
    expect(window.localStorage.getItem(WATERMARK_KEY)).toBe("432");
    expect(screen.getByRole("button", { name: /^new since last visit 2 —/i })).toBeTruthy();
  });

  /*
   * The set is FROZEN for the life of the page: the reader is working down it, so it must not move
   * under them. `refresh` adopts a newer response through the same path the first load used, and
   * the latch in `adopt` is what makes that a no-op for this set.
   */
  it("does not move the set when a later response is adopted", async () => {
    vi.useFakeTimers();
    window.localStorage.setItem(WATERMARK_KEY, "430");
    /*
     * A poll lands a run-433 lead and the reader presses refresh. The watermark ON DISK is already
     * 432 by then, so a set recomputed at that point reports exactly ONE lead and loses the two
     * the reader is part-way through — the defect the latch in `adopt` exists to prevent.
     */
    // The SAME row objects in both responses, so the only difference between them is the extra
    // run-433 lead. A fresh `queueRow()` per response mints new posting ids, and this test would
    // then pass because the set no longer matches anything rather than because it did not move.
    const standing = [
      queueRow({ delivered_run_id: 430, title: "SEEN-430" }),
      queueRow({ delivered_run_id: 431, title: "FRESH-431" }),
      queueRow({ delivered_run_id: 432, title: "FRESH-432" }),
    ];
    const newest = queueRow({ delivered_run_id: 433, title: "NEWEST-433" });
    vi.mocked(getQueue)
      .mockResolvedValueOnce(queueResponse([...standing]))
      .mockResolvedValue(queueResponse([...standing, newest]));

    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("button", { name: /^new since last visit 2 —/i })).toBeTruthy();
    expect(window.localStorage.getItem(WATERMARK_KEY)).toBe("432");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    fireEvent.click(screen.getByText("refresh"));

    // Still 2, and still the SAME two: the set did not recompute against the advanced watermark.
    expect(screen.getByRole("button", { name: /^new since last visit 2 —/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^new since last visit 2 —/i }));
    const queue = screen.getByRole("grid", { name: "Queue" });
    expect(hasRow(queue, "FRESH-431")).toBe(true);
    expect(hasRow(queue, "FRESH-432")).toBe(true);
    expect(hasRow(queue, "NEWEST-433")).toBe(false);
  });

  /*
   * Storage that throws on READ. `localStorage` throws outright when it is disabled or the quota
   * is gone, and the throw is on the property access itself — so an unguarded read takes the page
   * down before the first row is drawn.
   */
  it("still renders the page when storage throws on read", async () => {
    const real = window.localStorage;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("storage is disabled");
      },
    });
    try {
      render(<App />);
      await screen.findByRole("grid", { name: "Queue" });

      // The page drew, and nothing is new — the honest answer when there is no way to know.
      expect(hasRow(screen.getByRole("grid", { name: "Queue" }), "FRESH-432")).toBe(true);
      expect(screen.getByRole("button", { name: /^new since last visit 0 —/i })).toBeTruthy();
    } finally {
      Object.defineProperty(window, "localStorage", { configurable: true, value: real });
    }
  });
});
