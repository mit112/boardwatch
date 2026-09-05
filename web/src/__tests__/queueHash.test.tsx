import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueDetail, QueueRow } from "../api/types";
import { queueResponse, queueRow } from "../test/rows";

/*
 * The queue's addressable state, and the state that survives a tab switch.
 *
 * Two failures, one change. Taking the Runs tab and coming back threw away the filter text, the
 * score floor, both facets and both sort orders — every one of them re-entered by hand. And the
 * open lead was in no URL at all, so "look at this one" could not be sent, bookmarked, or even
 * reloaded onto.
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

const LEAD = queueRow({ posting_id: 61310, title: "RUN-5-LEAD", delivered_run_id: 5 });
const SAME_RUN = queueRow({ posting_id: 61311, title: "RUN-5-OTHER", delivered_run_id: 5 });
const OTHER_RUN = queueRow({ posting_id: 61312, title: "RUN-4-LEAD", delivered_run_id: 4 });
const REVIEW_OTHER_RUN = queueRow({
  posting_id: 61313,
  title: "RUN-4-REVIEW",
  delivered_run_id: 4,
  review_reason: "unevaluated",
});

function detailFor(row: QueueRow): QueueDetail {
  return { row, jd_body: "A job description.", requirements: [], board_target: null };
}

function queueTitles(): string[] {
  return within(screen.getByRole("grid", { name: "Queue" }))
    .getAllByRole("row")
    .filter((row) => row.hasAttribute("data-row-id"))
    .map((row) => within(row).getByText(/RUN-/).textContent ?? "");
}

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/#/queue");
  vi.mocked(getQueue).mockResolvedValue(
    queueResponse([LEAD, SAME_RUN, OTHER_RUN], [REVIEW_OTHER_RUN]),
  );
  vi.mocked(getDetail).mockImplementation((id: number) =>
    Promise.resolve(
      detailFor(
        [LEAD, SAME_RUN, OTHER_RUN, REVIEW_OTHER_RUN].find((row) => row.posting_id === id) ?? LEAD,
      ),
    ),
  );
  // A lead can now be open on the FIRST render, so the answers panel's fetch happens on mount too.
  vi.mocked(getRuns).mockResolvedValue({ runs: [] });
  vi.mocked(getAnswers).mockResolvedValue({
    identity: {},
    work_auth: {},
    education: [],
    questions: [],
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("#/queue?run=&lead=", () => {
  it("opens the named lead and filters both lanes to the named run", async () => {
    window.history.replaceState(null, "", "/#/queue?run=5&lead=61310");
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    // The lead the URL names is open, fetched by id — not merely highlighted.
    expect(vi.mocked(getDetail)).toHaveBeenCalledWith(61310);
    // Both lanes are narrowed: the review lead belongs to run 4 and is gone with the apply one.
    expect(queueTitles()).toEqual(["RUN-5-LEAD", "RUN-5-OTHER"]);
    expect(screen.queryByText("RUN-4-REVIEW")).toBeNull();
    expect(screen.getByText(/Showing run 5/)).toBeTruthy();
  });

  it("clears `lead` on close and keeps `run`", async () => {
    window.history.replaceState(null, "", "/#/queue?run=5&lead=61310");
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(await screen.findByRole("button", { name: /close/i }));

    expect(window.location.hash).toBe("#/queue?run=5");
    // The run filter is a separate decision from which lead is open, and outlives it.
    expect(queueTitles()).toEqual(["RUN-5-LEAD", "RUN-5-OTHER"]);
  });

  it("writes `lead` into the hash when a row is opened", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(screen.getByText("RUN-4-LEAD"));

    expect(window.location.hash).toBe("#/queue?lead=61312");
  });

  it("ignores and clears a lead id that is not on the page", async () => {
    window.history.replaceState(null, "", "/#/queue?lead=999999");
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    // No pane, no fetch for a lead that is not here, and the stale key is dropped from the URL.
    expect(vi.mocked(getDetail)).not.toHaveBeenCalledWith(999999);
    expect(window.location.hash).toBe("#/queue");
  });

  it("drops the run filter from the Show all runs control", async () => {
    window.history.replaceState(null, "", "/#/queue?run=5");
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    expect(queueTitles()).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Show all runs" }));

    expect(queueTitles()).toHaveLength(3);
    expect(window.location.hash).toBe("#/queue");
  });
});

describe("working state across a tab switch", () => {
  it("carries the run filter and the open lead back from the Runs tab", async () => {
    window.history.replaceState(null, "", "/#/queue?run=5&lead=61310");
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    /*
     * The `hashchange` a real browser fires off each of these navigations, dispatched explicitly:
     * jsdom queues it as a task, so back-to-back clicks in one turn would land BEFORE it and the
     * test would never exercise the re-parse that actually threatens the remembered params.
     */
    fireEvent.click(screen.getByRole("button", { name: "Runs" }));
    fireEvent(window, new HashChangeEvent("hashchange"));
    // `#/runs` stays bare — a runs URL must not carry a queue lead id.
    expect(window.location.hash).toBe("#/runs");

    fireEvent.click(screen.getByRole("button", { name: "Queue" }));
    fireEvent(window, new HashChangeEvent("hashchange"));

    // Both keys are back: the round trip is a navigation, not a reset. The page re-mounts and
    // re-fetches, so the list is awaited rather than read out of the click's own turn.
    expect(window.location.hash).toBe("#/queue?run=5&lead=61310");
    await screen.findByRole("grid", { name: "Queue" });
    expect(queueTitles()).toEqual(["RUN-5-LEAD", "RUN-5-OTHER"]);
  });


  it("restores the filter text, the score floor and both facets", async () => {
    const view = render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.change(screen.getByLabelText("Filter company, title, location"), {
      target: { value: "RUN-5" },
    });
    fireEvent.change(screen.getByLabelText("Minimum score"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /^not evaluated 1 —/ }));
    view.unmount();

    render(<App />);
    // The reason facet takes the apply lane off the page, so the chip is what says "loaded".
    await screen.findByRole("button", { name: /^not evaluated 1 —/ });

    expect(screen.getByLabelText("Filter company, title, location")).toHaveProperty(
      "value",
      "RUN-5",
    );
    expect(screen.getByLabelText("Minimum score")).toHaveProperty("value", "3");
    expect(
      screen.getByRole("button", { name: /^not evaluated 1 —/ }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("restores each lane's sort independently", async () => {
    const view = render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    fireEvent.click(
      within(screen.getByRole("grid", { name: "Queue" })).getByRole("button", { name: "company" }),
    );
    view.unmount();

    render(<App />);
    const queue = await screen.findByRole("grid", { name: "Queue" });

    // The apply lane kept its company sort. `aria-sort` is what a screen reader is told, so it is
    // what this asserts — not the row order, which a rank sort could coincidentally match.
    const header = within(queue)
      .getByRole("button", { name: "company" })
      .closest('[role="columnheader"]');
    expect(header?.getAttribute("aria-sort")).toBe("descending");
  });
});
