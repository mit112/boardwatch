import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ReviewReason } from "../api/types";
import { ReviewReasonBadge } from "../components/ReviewReasonBadge";
import {
  REVIEW_REASON_LABELS,
  reviewBreakdown,
  reviewLaneSentence,
} from "../lib/reviewReasons";
import { queueResponse, queueRow } from "../test/rows";

/*
 * The review lane's copy. It hand-wrote two of the nine reasons — "outside the US, or … not
 * positively call software" — so on the audit day it described 0 of the 149 leads under it: the
 * lane held 108 `unevaluated` and 41 `role_unconfirmed`, neither of them named.
 *
 * `REVIEW_REASON_LABELS` is the single source for those words, and the first test is what makes
 * that claim true rather than aspirational: `ReviewReasonBadge` still carries its own private map,
 * so the two are compared through the badge's RENDER — the only channel available while the badge
 * belongs to another ticket.
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

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("REVIEW_REASON_LABELS", () => {
  it("agrees with ReviewReasonBadge's own catalog, key for key", () => {
    const keys = Object.keys(REVIEW_REASON_LABELS) as ReviewReason[];
    // Nine, not eight: a member dropped from the labels map would otherwise pass this vacuously.
    expect(keys).toHaveLength(9);
    for (const reason of keys) {
      const view = render(<ReviewReasonBadge reason={reason} />);
      // The badge renders exactly one element carrying its label text.
      expect(screen.getByText(REVIEW_REASON_LABELS[reason])).toBeTruthy();
      view.unmount();
    }
  });
});

describe("the generated review sentence", () => {
  const rows = [
    queueRow({ review_reason: "unevaluated" }),
    queueRow({ review_reason: "unevaluated" }),
    queueRow({ review_reason: "unevaluated" }),
    queueRow({ review_reason: "role_unconfirmed" }),
    queueRow({ review_reason: "role_unconfirmed" }),
    queueRow({ review_reason: "non_us_location" }),
  ];

  it("names every reason present, in count order, with its count", () => {
    expect(reviewBreakdown(rows)).toBe("3 not evaluated, 2 role unconfirmed, 1 outside the US");
  });

  it("states the lane total alongside the breakdown", () => {
    expect(reviewLaneSentence(rows)).toBe(
      "6 held for a look: 3 not evaluated, 2 role unconfirmed, 1 outside the US.",
    );
  });

  it("states the total alone when no row carries a reason the catalog knows", () => {
    // An older server omits `review_reason` entirely; the count is still true, so it is still said.
    expect(reviewLaneSentence([queueRow({ review_reason: null })])).toBe("1 held for a look.");
  });

  it("reaches the page, replacing the two hand-written reasons", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], rows));
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    expect(
      screen.getByText(/6 held for a look: 3 not evaluated, 2 role unconfirmed, 1 outside the US/),
    ).toBeTruthy();
    // The old copy named two reasons and described none of these leads.
    expect(screen.queryByText(/will not positively call software — so it is not/)).toBeNull();
    // The folder cross-reference stays: if the page and the tree disagree, the tree wins.
    expect(screen.getByText(/Same split as the/)).toBeTruthy();
  });

  it("generates the band's review tooltip from the same counts", async () => {
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow()], rows));
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    const note = screen.getByTitle(/Held for a look/);
    expect(note.getAttribute("title") ?? "").toContain(
      "3 not evaluated, 2 role unconfirmed, 1 outside the US",
    );
  });
});
