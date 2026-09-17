import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AppliedHistoryResponse } from "../api/types";
import { appliedResponse, appliedRow, withoutFields } from "../test/rows";

/*
 * The applied history page (`#/applied`), which is the third route and the only read-only one.
 *
 * A lead leaves the queue the instant it is marked applied, so what this page is for is the state
 * that had no surface at all: what was applied to, when, whether the requisition is still up, and
 * which résumé went out. Each test below names one of those and asserts a reader can see it.
 *
 * The client is mocked rather than the fixture server driven, for the reason `runsPage.test.tsx`
 * gives: `src/fixtures/` may only be reached through the dynamic import in `api/client.ts`, and no
 * test may import it.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
  getApplied: vi.fn(),
  markApplied: vi.fn(),
  markSkipped: vi.fn(),
  unskip: vi.fn(),
  unapply: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getApplied, getQueue, markApplied, unapply } from "../api/client";
import { App } from "../App";

/** The application rows of the applied table: `role="row"` also matches its header row. */
function dataRows(): HTMLElement[] {
  return within(screen.getByRole("table"))
    .getAllByRole("row")
    .filter((row) => within(row).queryAllByRole("columnheader").length === 0);
}

/** The value beside a `<dt>` in the counts band, which is how every cell on it is built. */
function bandValue(label: string): string {
  const band = screen.getByRole("region", { name: "Applied history status" });
  return within(band).getByText(label).nextElementSibling?.textContent ?? "";
}

async function renderApplied(response: AppliedHistoryResponse): Promise<void> {
  vi.mocked(getApplied).mockResolvedValue(response);
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  window.sessionStorage.clear();
  // The route is the URL, so the page under test is reached the way a bookmark reaches it.
  window.history.replaceState(null, "", "/#/applied");
  vi.mocked(getQueue).mockResolvedValue({
    rows: [],
    review: [],
    counts: {
      in_queue: 0,
      eligible: 0,
      uncertain: 0,
      judge_eligible: 0,
      judge_uncertain: 0,
      judge_unjudged: 0,
      ineligible: 0,
      review: 0,
      closed: 0,
      applied_ever: 0,
      skipped: 0,
      reported: 0,
      delivered_last_run: 0,
      last_run_finished: null,
    },
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("the applied route", () => {
  it("draws the page at #/applied, beside the two tabs it did not replace", async () => {
    await renderApplied(appliedResponse([appliedRow({ company: "Acme Corp" })]));

    // The page, reached from the hash alone: no click, so this is the bookmark/reload path.
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("Acme Corp")).toBeTruthy();
    // The third tab is pressed and the other two are still there — the route was ADDED.
    expect(screen.getByRole("button", { name: "Applied" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(screen.getByRole("button", { name: "Queue" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Runs" })).toBeTruthy();
  });

  it("contains a throw from the page in the route's own boundary, keeping the tabs", async () => {
    /*
     * D-363's containment at the route scope, for the new view. The throw is produced by real
     * component code meeting real data, never by a rigged component: a server NEWER than this
     * bundle is structural (`boardwatch web` serves the bundle from DISK and answers from the
     * Python it imported at STARTUP), and a field whose TYPE moved is the half no `== null` guard
     * can reach — `rows` arriving as an object makes `.filter` throw during render.
     */
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await renderApplied({
      rows: {} as unknown as AppliedHistoryResponse["rows"],
      counts: { total: 0, by_status: {}, posting_closed: 0 },
    });

    expect(screen.getByText("This view could not be drawn.")).toBeTruthy();
    // The nav sits OUTSIDE the boundary, so the other two views are one click away — which is the
    // only way out this card offers. Asserted as a pair: a test that looked for the card alone
    // would pass just as happily against a blank document with one card in it.
    expect(screen.getByRole("button", { name: "Queue" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Runs" })).toBeTruthy();
  });
});

describe("the counts band", () => {
  it("shows the total, the closed-posting count and every status bucket", async () => {
    await renderApplied(
      appliedResponse([
        appliedRow(),
        appliedRow({ posting_status: "closed", closed_at: "2026-09-12T09:00:00+00:00" }),
        appliedRow({ status: "withdrawn" }),
      ]),
    );

    expect(bandValue("applications")).toBe("3");
    // Applied AND since closed. The withdrawn row is on an open posting, so it is not in here
    // either way; the point is that the cell is its own figure and not folded into the total.
    expect(bandValue("posting closed")).toBe("1");
    expect(bandValue("applied")).toBe("2");
    expect(bandValue("withdrawn")).toBe("1");
    // A measured zero, printed. The catalog arrives whole, so "0 offers" is a reading rather
    // than a bucket the reader has to guess was absent.
    expect(bandValue("offer")).toBe("0");
  });

  it("carries the year on the applied date, and no time of day on the close", async () => {
    /*
     * This is the one page built to hold a MULTI-YEAR history, and it is sorted by this column by
     * default — so `Sep 10` alone printed the same label for 2025-09-10 and 2026-09-10 and the
     * list read as mis-sorted. `closed_at` is a DATE (the day the requisition went down), so a
     * time of day on it is precision the column does not have.
     */
    await renderApplied(
      appliedResponse([
        appliedRow({
          submitted_at: "2025-09-10T15:30:00+00:00",
          created_at: "2025-09-10T15:30:00+00:00",
          posting_status: "closed",
          closed_at: "2026-09-12T09:00:00+00:00",
        }),
      ]),
    );

    const cells = within(dataRows()[0] as HTMLElement).getAllByRole("cell");
    expect((cells[0] as HTMLElement).textContent ?? "").toMatch(/2025/);
    const closed = screen.getByText(/^closed /).textContent ?? "";
    expect(closed).toMatch(/2026/);
    // No clock on a date. Written as "not a time" rather than as an exact string so the
    // assertion holds under whatever locale the reader's machine prints.
    expect(closed).not.toMatch(/\d:\d\d/);
  });

  it("says in words, and with a date, that a posting has closed", async () => {
    await renderApplied(
      appliedResponse([
        appliedRow({ posting_status: "closed", closed_at: "2026-09-12T09:00:00+00:00" }),
      ]),
    );

    // SC 1.4.1: the reader has to be able to tell a dead requisition from a live one in a
    // screenshot and read aloud, so the marker is TEXT carrying the date, never a colour.
    expect(screen.getByText(/^closed /)).toBeTruthy();
  });
});

describe("the row's controls", () => {
  it("calls unapply and offers an undo that marks it applied again", async () => {
    const row = appliedRow({ company: "Acme Corp", title: "Backend Engineer" });
    await renderApplied(appliedResponse([row]));
    vi.mocked(unapply).mockResolvedValue({ outcome: "transitioned", job_id: row.job_id });
    vi.mocked(markApplied).mockResolvedValue({ outcome: "created", job_id: row.job_id });

    fireEvent.click(screen.getByRole("button", { name: "Unmark applied" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // The EXISTING inverse route, keyed on the posting the queue delivered — not a new write path.
    expect(vi.mocked(unapply)).toHaveBeenCalledWith(row.posting_id);
    const toast = screen.getByText(/^Withdrawn: Acme Corp — Backend Engineer/);
    expect(toast.textContent ?? "").toMatch(/Undo marks it applied again/);

    // And the undo is real: it calls the forward route rather than restoring the row on screen.
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(markApplied)).toHaveBeenCalledWith(row.posting_id);
  });

  it("does not claim a withdrawal the server says it did not make", async () => {
    // `mark_job_unapplied` answers `unchanged` for an attempt that does not read as applied.
    const row = appliedRow({ company: "Acme Corp", status: "interested" });
    await renderApplied(appliedResponse([row]));
    vi.mocked(unapply).mockResolvedValue({ outcome: "unchanged", job_id: row.job_id });

    fireEvent.click(screen.getByRole("button", { name: "Unmark applied" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText(/Nothing to withdraw for Acme Corp/)).toBeTruthy();
    // No undo is offered, because nothing was done to undo.
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("offers neither control on a row whose job never reached the queue", async () => {
    // The imported-history shape: no delivered posting, so there is no id to open a PDF with and
    // none to unmark. Said in words rather than left as two buttons that are simply missing.
    await renderApplied(
      appliedResponse([appliedRow({ posting_id: null, pdf_available: false })]),
    );

    expect(screen.queryByRole("button", { name: "Unmark applied" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open PDF" })).toBeNull();
    expect(screen.getByText(/never delivered/)).toBeTruthy();
  });
});

  it("offers the unmark only on the attempt the write would act on", async () => {
    /*
     * `mark_job_unapplied` resolves posting -> job -> latest attempt, so the control is offered
     * exactly where the server says that attempt is (`can_unmark`). A row that does not get it
     * SAYS SO: two rows for one job, one with a button and one with nothing, is a difference the
     * reader cannot otherwise account for.
     */
    const job = 4242;
    await renderApplied(
      appliedResponse([
        appliedRow({ job_id: job, company: "Acme Corp", status: "applied", can_unmark: false }),
        appliedRow({ job_id: job, company: "Acme Corp", status: "interviewing", can_unmark: true }),
      ]),
    );

    expect(screen.getAllByRole("button", { name: "Unmark applied" })).toHaveLength(1);
    expect(screen.getByText(/only a job's latest attempt/)).toBeTruthy();
  });

describe("a server older than this bundle", () => {
  it("still draws the row, and still offers the PDF, with no pdf_uri on the wire", async () => {
    /*
     * `pdf_uri` is the PATH, and the control is keyed on `pdf_available` — the server's own answer
     * to "would `/api/pdf/<id>` serve this". Keying it on the uri instead would drop the button
     * for a server that never learned to send the path, which is a lost résumé rather than a lost
     * tooltip. `undefined` is the only input here: `null` passes either way.
     */
    const row = withoutFields(appliedRow({ company: "Acme Corp" }), ["pdf_uri"]);
    await renderApplied(appliedResponse([row]));

    expect(dataRows()).toHaveLength(1);
    expect(screen.getByText("Acme Corp")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open PDF" })).toBeTruthy();
  });

  it("offers no unmark at all when the server never learned to say which attempt", async () => {
    // `can_unmark` absent arrives as `undefined`. The control is withheld rather than offered on
    // every row: an older server's unapply still acts on the job's latest attempt, so a button
    // here would make the same wrong promise this field exists to stop.
    const row = withoutFields(appliedRow({ company: "Acme Corp" }), ["can_unmark"]);
    await renderApplied(appliedResponse([row]));

    expect(dataRows()).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Unmark applied" })).toBeNull();
    expect(screen.getByText(/only a job's latest attempt/)).toBeTruthy();
  });

  it("draws every other cell when the dates and the posting status are absent", async () => {
    const row = withoutFields(appliedRow({ company: "Acme Corp" }), [
      "submitted_at",
      "created_at",
      "posting_status",
      "closed_at",
      "source",
    ]);
    await renderApplied(appliedResponse([row]));

    expect(dataRows()).toHaveLength(1);
    expect(screen.getByText("Acme Corp")).toBeTruthy();
    // What it could not be told reads as absent, never as a zero and never as "open".
    expect(within(dataRows()[0] as HTMLElement).getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("search and sort", () => {
  it("filters on company, title and location, and reports how many are showing", async () => {
    await renderApplied(
      appliedResponse([
        appliedRow({ company: "Acme Corp", title: "Backend Engineer" }),
        appliedRow({ company: "Globex", title: "Data Analyst" }),
      ]),
    );
    expect(dataRows()).toHaveLength(2);

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "globex" } });

    expect(dataRows()).toHaveLength(1);
    expect(screen.getByText("Globex")).toBeTruthy();
    // Scoped to the band: the toaster is a `role="status"` region too, and asserting on "the"
    // status region would be a query that breaks the first time a toast is up.
    const band = screen.getByRole("region", { name: "Applied history status" });
    expect(within(band).getByRole("status").textContent).toContain("Showing 1 of 2");
  });

  it("sorts by company when its header is taken, without touching the date order first", async () => {
    await renderApplied(
      appliedResponse([
        appliedRow({ company: "Zenith", submitted_at: "2026-09-12T09:00:00+00:00" }),
        appliedRow({ company: "Acme Corp", submitted_at: "2026-09-01T09:00:00+00:00" }),
      ]),
    );
    // Newest first, which is the order the payload arrives in and the default sort.
    expect(dataRows().map((row) => row.textContent?.includes("Zenith"))).toEqual([true, false]);

    fireEvent.click(screen.getByRole("button", { name: "company" }));

    expect(dataRows().map((row) => row.textContent?.includes("Acme Corp"))).toEqual([true, false]);
    const header = screen.getByRole("columnheader", { name: /company/ });
    expect(header.getAttribute("aria-sort")).toBe("ascending");
  });
});

describe("the empty state", () => {
  it("names both ways to record an application when nothing has been applied to", async () => {
    await renderApplied(appliedResponse([]));

    expect(
      screen.getByText(
        "Nothing applied yet — mark a lead applied from the queue, or `boardwatch track add <posting_id>`.",
      ),
    ).toBeTruthy();
  });

  it("points at the search box, not at the queue, when a filter hid every row", async () => {
    await renderApplied(appliedResponse([appliedRow({ company: "Acme Corp" })]));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "nothing-matches" } });

    // The lever that would bring rows back is the text box. The other sentence would point the
    // reader at the queue for a list that is not in fact empty.
    expect(screen.getByText(/No application matches that search/)).toBeTruthy();
    expect(screen.queryByText(/Nothing applied yet/)).toBeNull();
  });
});
