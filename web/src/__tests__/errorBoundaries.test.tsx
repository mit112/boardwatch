import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueDetail, RequirementView, ReviewReason, Verdict } from "../api/types";
import { fromANewerServer, queueResponse, queueRow } from "../test/rows";

/*
 * D-363's containment, at three of its four scopes — the fourth, the root boundary in `main.tsx`,
 * is `rootBoundary.test.tsx` because it has to import that module for real.
 *
 * The claim under test is one sentence: a component that throws while RENDERING costs a CARD, not
 * the page. So every assertion here is paired — the fallback appeared AND the part that was
 * supposed to survive is still on the page. A test that only looked for the fallback would pass
 * just as happily against a blank document with one card in it, which is the failure.
 *
 * Every throw is produced by real component code meeting real data, never by a mocked component
 * rigged to throw. The data is a value of the WRONG SHAPE off the wire — a list that is not a
 * list, a missing list — which is what a server newer or older than the bundle can send, and
 * which no `== null` guard reaches. (A member this bundle has never heard of in a CLOSED catalog
 * used to be the trigger; the status model now degrades those to plain text and does not throw,
 * which the last test pins as its own property.)
 *
 * Boundaries catch render, lifecycle and constructor throws and nothing else. Nothing here throws
 * from an event handler or a promise, because React never sees those and a test that pretended
 * otherwise would be asserting against React rather than against this application.
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
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getAnswers, getDetail, getQueue } from "../api/client";
import { App } from "../App";

const UNKNOWN_REASON = fromANewerServer<ReviewReason>("held_for_a_reason_this_bundle_lacks");
const UNKNOWN_VERDICT = fromANewerServer<Verdict>("a_verdict_this_bundle_lacks");
/** Something that claims to be a list of two places and is not one, so reading the row's
 *  locations throws. It is read in the ROW alone — no filter, sort or count touches it — so the
 *  throw is confined to the list that drew the row. */
const MALFORMED_LOCATIONS = { length: 2 } as unknown as string[];

/** The data rows of one grid: `role="row"` also matches the sticky header row. */
function dataRows(grid: HTMLElement): HTMLElement[] {
  return within(grid)
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"));
}

function first<T>(items: T[]): T {
  const [item] = items;
  if (item === undefined) throw new Error("expected at least one item");
  return item;
}

describe("render containment", () => {
  beforeEach(() => {
    // React reports every caught error through `console.error`, and `ErrorBoundary` logs the
    // component stack on top of that. Silenced so a passing run reads as a passing run.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("keeps the apply list when the review list throws", async () => {
    const apply = [queueRow(), queueRow(), queueRow()];
    const review = [queueRow({ review_reason: "unevaluated", locations: MALFORMED_LOCATIONS })];
    vi.mocked(getQueue).mockResolvedValue(queueResponse(apply, review));
    // Both lists on one page, so the survivor and the casualty are side by side.
    window.sessionStorage.setItem("boardwatch.queue.lens", "all");

    render(<App />);

    // FIRST, because this is the claim the reproduction is about: removing this one boundary took
    // the apply list from 408 rows to 0. The COUNT is the assertion, not the grid's presence.
    const grid = await screen.findByRole("grid", { name: "Jobs to explore" });
    expect(dataRows(grid)).toHaveLength(apply.length);
    expect(screen.getByText("The review list could not be drawn.")).toBeTruthy();
    // And the failure was contained BELOW the route, so the view's own card never appeared.
    expect(screen.queryByText("This view could not be drawn.")).toBeNull();
  });

  it("keeps the navigation when the whole queue view throws", async () => {
    // The throw is in the APPLY list this time, which no boundary inside the page contains, so it
    // reaches the one wrapping the route switch.
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow({ locations: MALFORMED_LOCATIONS })]));

    render(<App />);

    expect(await screen.findByText("This view could not be drawn.")).toBeTruthy();
    // The header sits outside the boundary, so the other view stays one click away — which is the
    // only way out this card offers the reader.
    expect(screen.getByRole("button", { name: "Jobs" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Runs" })).toBeTruthy();
  });

  it("keeps the queue when the detail pane throws", async () => {
    const apply = [queueRow(), queueRow()];
    vi.mocked(getQueue).mockResolvedValue(queueResponse(apply));
    vi.mocked(getAnswers).mockRejectedValue(new Error("no answers file"));
    // The row in the LIST is intact; only the detail response is malformed (no requirement list
    // at all), so the throw is confined to the workspace rather than to the row that opened it.
    const opened = first(apply);
    const detail: QueueDetail = {
      row: opened,
      jd_body: "A job description.",
      requirements: undefined as unknown as RequirementView[],
      board_target: null,
    };
    vi.mocked(getDetail).mockResolvedValue(detail);

    render(<App />);
    const grid = await screen.findByRole("grid", { name: "Jobs to explore" });
    fireEvent.click(first(dataRows(grid)));

    expect(await screen.findByText("This job could not be drawn.")).toBeTruthy();
    expect(dataRows(screen.getByRole("grid", { name: "Jobs to explore" }))).toHaveLength(apply.length);
    expect(screen.queryByText("This view could not be drawn.")).toBeNull();
  });

  it("draws a job whose verdict and reason this bundle has never heard of, as plain text", async () => {
    // The OTHER half of the story: a catalog member from a newer server is not an error. It must
    // degrade to a row that says nothing it cannot back up, with no card and no boundary involved.
    const apply = [queueRow({ verdict: UNKNOWN_VERDICT, title: "Unfamiliar Verdict Engineer" })];
    const review = [
      queueRow({ review_reason: UNKNOWN_REASON, title: "Unfamiliar Reason Engineer" }),
    ];
    vi.mocked(getQueue).mockResolvedValue(queueResponse(apply, review));
    window.sessionStorage.setItem("boardwatch.queue.lens", "all");

    render(<App />);

    expect(await screen.findByText("Unfamiliar Verdict Engineer")).toBeTruthy();
    expect(screen.getByText("Unfamiliar Reason Engineer")).toBeTruthy();
    expect(screen.queryByText(/could not be drawn/)).toBeNull();
  });
});
