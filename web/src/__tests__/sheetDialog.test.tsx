import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueDetail, QueueRow } from "../api/types";
import { queueResponse, queueRow } from "../test/rows";

/*
 * The narrow tier's detail pane is a `fixed inset-0` sheet over a page `QueuePage` inerts — a
 * modal in everything but its semantics. Two claims are asserted here, and only at that tier:
 *
 *   - it announces itself as one (`role="dialog"`, `aria-modal`, a name taken from its heading),
 *     while the side-by-side column at `lg` does NOT, because a column beside the list blocks
 *     nothing and a dialog role there would be a lie to a screen reader;
 *   - Escape puts the cursor back on the row that opened it, not on `<body>`.
 *
 * `<App />` and not `DetailPane` alone: the trigger row lives in the grid and the close that has to
 * put the cursor back on it is wired in `QueuePage`.
 *
 * WHY THE FOCUS TEST OPENS WITH A CLICK. The pane captured `document.activeElement` when it mounted
 * and refocused that element on close, which works only while the cursor is still on the trigger
 * row at mount time. In Chromium it is not: opening a lead assigns `window.location.hash`, which is
 * a fragment navigation resolving to no element, and the browser answers by moving focus to the
 * body — so the pane captured `<body>` and faithfully restored `<body>` on Escape (D-348; not
 * `inert`, which D-348 ruled out by stripping the attributes and reproducing anyway). jsdom
 * implements neither fragment navigation nor `inert`, so neither route strips focus here; a click
 * reaches the same state, because jsdom does not focus what it clicks. The fix does not care which
 * route emptied it — the row is found by `data-row-id` at CLOSE time rather than remembered.
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

import { getAnswers, getDetail, getQueue, getRuns } from "../api/client";
import { App } from "../App";

const LEAD = queueRow({ posting_id: 4242, title: "Compiler Engineer", company: "Acme Corp" });
const OTHER = queueRow({ posting_id: 4243, title: "Platform Engineer", company: "Acme Corp" });

function detailFor(row: QueueRow): QueueDetail {
  return { row, jd_body: "About the team.", requirements: [], board_target: null };
}

/* The shared setup pins `matchMedia` at `true` (the `lg` column tier). This file needs both
   tiers, so it installs its own and restores the shared stub afterwards. */
const SHARED_MATCH_MEDIA: typeof window.matchMedia = window.matchMedia.bind(window);

function installMatchMedia(matches: boolean): void {
  window.matchMedia = vi.fn((media: string) => ({
    matches,
    media,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }));
}

/** The grid row for a posting: the element a keyboard reader was on when they pressed Enter. */
function rowElement(postingId: number): HTMLElement {
  const row = document.querySelector<HTMLElement>(`[data-row-id="${String(postingId)}"]`);
  if (row === null) throw new Error(`no row for ${String(postingId)}`);
  return row;
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/#/queue");
  vi.mocked(getQueue).mockResolvedValue(queueResponse([LEAD, OTHER]));
  vi.mocked(getDetail).mockImplementation((id: number) =>
    Promise.resolve(detailFor([LEAD, OTHER].find((row) => row.posting_id === id) ?? LEAD)),
  );
  vi.mocked(getRuns).mockResolvedValue({ runs: [] });
  vi.mocked(getAnswers).mockResolvedValue({
    identity: {},
    work_auth: {},
    education: [],
    questions: [],
  });
});

afterEach(() => {
  window.matchMedia = SHARED_MATCH_MEDIA;
  vi.clearAllMocks();
});

/** Open `LEAD` from its grid row and wait for the pane to have drawn the lead. */
async function openFromRow(): Promise<void> {
  render(<App />);
  await screen.findByRole("grid", { name: "Queue" });
  fireEvent.click(rowElement(LEAD.posting_id));
  await screen.findByRole("heading", { name: "Compiler Engineer" });
}

describe("the narrow-tier detail sheet", () => {
  it("returns focus to the row for the same lead when Escape closes it", async () => {
    installMatchMedia(false);
    await openFromRow();
    // The premise, asserted rather than assumed: the cursor is NOT on the trigger row while the
    // sheet is up, which is the state Chromium is in and the one a remembered element cannot
    // recover from.
    expect(document.activeElement).not.toBe(rowElement(LEAD.posting_id));

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Compiler Engineer" })).toBeNull();
    });

    // Looked up NOW, by posting id: the row that is on the page after the close is the one the
    // cursor has to be on, whatever happened to the element that was there at open time.
    await waitFor(() => {
      expect(document.activeElement).toBe(rowElement(LEAD.posting_id));
    });
    expect(document.activeElement).not.toBe(document.body);
  });

  it("announces itself as a modal dialog named by its heading", async () => {
    installMatchMedia(false);
    await openFromRow();

    // Named by the heading it actually shows, not by a label invented beside it: the query is by
    // ROLE AND NAME, so both halves have to hold.
    const dialog = screen.getByRole("dialog", { name: "Compiler Engineer" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe(
      screen.getByRole("heading", { name: "Compiler Engineer" }).id,
    );
  });

  it("is a plain complementary column at the side-by-side tier, never a dialog", async () => {
    installMatchMedia(true);
    await openFromRow();

    expect(screen.queryByRole("dialog")).toBeNull();
    screen.getByRole("complementary", { name: "Lead detail" });
  });
});
