import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueDetail, ReviewReason, Verdict } from "../api/types";
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
 * rigged to throw. `ReviewReasonBadge` and `VerdictChip` both index a CLOSED catalog with a value
 * off the wire; a member this bundle has never heard of yields `undefined`, and reading `.label`
 * or `.className` off that throws. That is not hypothetical — `boardwatch web` serves this bundle
 * from disk while answering from the Python it imported at startup, so a server NEWER than the
 * bundle is structural, and no `== null` guard reaches it.
 *
 * Boundaries catch render, lifecycle and constructor throws and nothing else. Nothing here throws
 * from an event handler or a promise, because React never sees those and a test that pretended
 * otherwise would be asserting against React rather than against this application.
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
import { getAnswers, getDetail, getQueue } from "../api/client";
import { App } from "../App";

const UNKNOWN_REASON = fromANewerServer<ReviewReason>("held_for_a_reason_this_bundle_lacks");
const UNKNOWN_VERDICT = fromANewerServer<Verdict>("a_verdict_this_bundle_lacks");

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

  it("keeps the apply lane when the review lane throws", async () => {
    const apply = [queueRow(), queueRow(), queueRow()];
    const review = [queueRow({ review_reason: UNKNOWN_REASON })];
    vi.mocked(getQueue).mockResolvedValue(queueResponse(apply, review));

    render(<App />);
    const grid = await screen.findByRole("grid", { name: "Queue" });
    expect(dataRows(grid)).toHaveLength(apply.length);

    // The lane is collapsed by default, so nothing in it has rendered yet. Opening it is what
    // makes the row render and throw — a state update, still a RENDER, still caught.
    fireEvent.click(screen.getByRole("button", { name: "show" }));

    // FIRST, because this is the claim the reproduction is about: removing this one boundary took
    // the apply lane from 408 rows to 0. The COUNT is the assertion, not the grid's presence.
    expect(dataRows(screen.getByRole("grid", { name: "Queue" }))).toHaveLength(apply.length);
    expect(screen.getByText("The review lane could not be drawn.")).toBeTruthy();
    // And the failure was contained BELOW the route, so the view's own card never appeared.
    expect(screen.queryByText("This view could not be drawn.")).toBeNull();
  });

  it("keeps the navigation when the whole queue view throws", async () => {
    // The throw is in the APPLY lane this time, which no boundary inside the page contains, so it
    // reaches the one wrapping the route switch.
    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow({ verdict: UNKNOWN_VERDICT })]));

    render(<App />);

    expect(await screen.findByText("This view could not be drawn.")).toBeTruthy();
    // The header sits outside the boundary, so the other view stays one click away — which is the
    // only way out this card offers the reader.
    expect(screen.getByRole("button", { name: "Queue" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Runs" })).toBeTruthy();
  });

  it("keeps the queue when the detail pane throws", async () => {
    const apply = [queueRow(), queueRow()];
    vi.mocked(getQueue).mockResolvedValue(queueResponse(apply));
    vi.mocked(getAnswers).mockRejectedValue(new Error("no answers file"));
    // The row in the LIST is intact; only the detail response carries the unknown verdict, so the
    // throw is confined to the pane rather than to the row that opened it.
    const opened = first(apply);
    const detail: QueueDetail = {
      row: { ...opened, verdict: UNKNOWN_VERDICT },
      jd_body: "A job description.",
      requirements: [],
      board_target: null,
    };
    vi.mocked(getDetail).mockResolvedValue(detail);

    render(<App />);
    const grid = await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(first(dataRows(grid)));

    expect(await screen.findByText("This lead could not be drawn.")).toBeTruthy();
    expect(dataRows(screen.getByRole("grid", { name: "Queue" }))).toHaveLength(apply.length);
    expect(screen.queryByText("This view could not be drawn.")).toBeNull();
  });
});
