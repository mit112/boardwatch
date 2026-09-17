import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Bulk skip: selection in the apply-lane table, the toolbar's bulk bar, and ONE write with ONE
 * undo. The queue holds 392 leads growing by 20-30 a night and the owner triages by whole
 * companies and whole title families, so the assertions here are about the *count* of calls as
 * much as their arguments — N requests where one was asked for is the defect this replaces.
 *
 * Fake timers for the same reason `queueMutations` uses them: the optimistic removal is scheduled
 * behind the `COLLAPSE_MS` row animation, so the write resolves on the far side of a timer.
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
  skipMany: vi.fn(),
  unskipMany: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getQueue, markApplied, skipMany, unskipMany } from "../api/client";
import { App } from "../App";
import { GRID_TEMPLATE, SELECT_GRID_TEMPLATE, SELECT_TRACK } from "../components/QueueRowItem";

const COLLAPSE_MS = 200;

function grid(): HTMLElement {
  return screen.getByRole("grid", { name: "Queue" });
}

function dataRows(): HTMLElement[] {
  return within(grid())
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"));
}

function rowFor(title: string): HTMLElement {
  const found = dataRows().find((row) => within(row).queryByText(title) !== null);
  if (found === undefined) throw new Error(`no row for ${title}`);
  return found;
}

function titles(): string[] {
  return dataRows().map((row) => within(row).getByText(/Engineer|Analyst|Technician/).textContent ?? "");
}

function bulkBar(): HTMLElement | null {
  return screen.queryByRole("group", { name: "Bulk actions" });
}

/** One status-band cell's figure, read through its label rather than by position. */
function bandCell(label: string): string {
  const cell = screen.getByText(label).parentElement;
  if (cell === null) throw new Error(`no band cell for ${label}`);
  return (cell.lastElementChild?.textContent ?? "").trim();
}

beforeEach(() => {
  vi.useFakeTimers();
  // The client mock is module-level, so a call made by one test is still on the spy in the next
  // one — which would make the Cmd+A guard below pass on a neighbour's `skipMany` call.
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

async function renderRows() {
  const a = queueRow({ company: "Globex", title: "Backend Engineer" });
  const b = queueRow({ company: "Initech", title: "Data Analyst" });
  const c = queueRow({ company: "Acme Corp", title: "Field Technician" });
  vi.mocked(getQueue).mockResolvedValue(queueResponse([a, b, c]));
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(dataRows()).toHaveLength(3);
  return { a, b, c };
}

describe("bulk skip", () => {
  it("templatesAgree: the selectable grid is the plain one with one track in front", () => {
    /*
     * The two templates are written out separately because Tailwind only generates a class for a
     * candidate that appears LITERALLY in the source — so this is the drift guard that replaces
     * deriving one from the other. Flip a track width in `GRID_TEMPLATE` and forget the twin, and
     * the selectable table silently loses a column's width at one tier only.
     */
    expect(SELECT_GRID_TEMPLATE).toBe(
      GRID_TEMPLATE.replaceAll("grid-cols-[", `grid-cols-[${SELECT_TRACK}`),
    );
  });

  it("renders no bulk bar until at least one row is selected", async () => {
    await renderRows();

    // Nothing selected: the bar takes no space at all, per the bulk-actions card.
    expect(bulkBar()).toBeNull();
    expect(screen.queryByRole("button", { name: /^Skip 1 selected/ })).toBeNull();

    // The paired half, which is what makes the refusal above falsifiable.
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Select: Backend Engineer at Globex" }),
    );
    expect(bulkBar()).not.toBeNull();
    expect(within(bulkBar() as HTMLElement).getByText("1 selected")).toBeTruthy();

    // ...and it goes away again on Clear, rather than sitting there reading "0 selected".
    fireEvent.click(screen.getByRole("button", { name: /^Clear/ }));
    expect(bulkBar()).toBeNull();
  });

  it("skips the selection in ONE call and undoes it in ONE call with the same ids", async () => {
    const { a, c } = await renderRows();
    vi.mocked(skipMany).mockResolvedValue({ skipped: [a.job_id, c.job_id], failed: [] });
    vi.mocked(unskipMany).mockResolvedValue({ skipped: [a.job_id, c.job_id], failed: [] });

    fireEvent.click(
      screen.getByRole("checkbox", { name: "Select: Backend Engineer at Globex" }),
    );
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Select: Field Technician at Acme Corp" }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Skip 2 selected/ }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(COLLAPSE_MS);
    });
    // ONE call, carrying exactly the two selected job ids and not the third row's.
    expect(vi.mocked(skipMany)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(skipMany)).toHaveBeenCalledWith([a.job_id, c.job_id]);
    expect(titles()).toEqual(["Data Analyst"]);
    // The selection is spent, so the bar is gone with it.
    expect(bulkBar()).toBeNull();
    // The status band's skipped cell moved by two, the way one skip moves it by one.
    expect(bandCell("skipped")).toBe("2");

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(unskipMany)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(unskipMany)).toHaveBeenCalledWith([a.job_id, c.job_id]);
    expect(titles()).toEqual(["Backend Engineer", "Data Analyst", "Field Technician"]);
  });

  it("names the ids the server refused and leaves those rows in the list", async () => {
    const { a, b, c } = await renderRows();
    // The server wrote two of the three and reported the third: an id that is in no lane is
    // `failed`, never a 500, so the client has to put exactly that row back.
    vi.mocked(skipMany).mockResolvedValue({ skipped: [a.job_id, b.job_id], failed: [c.job_id] });
    vi.mocked(unskipMany).mockResolvedValue({ skipped: [a.job_id, b.job_id], failed: [] });

    fireEvent.click(screen.getByRole("checkbox", { name: "Select all 3 visible leads" }));
    fireEvent.click(screen.getByRole("button", { name: /^Skip 3 selected/ }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(COLLAPSE_MS);
    });

    expect(screen.getByText("Skipped 2, 1 failed")).toBeTruthy();
    expect(titles()).toEqual(["Field Technician"]);

    // The undo covers the two that were written and never the one that was not.
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(unskipMany)).toHaveBeenCalledWith([a.job_id, b.job_id]);
  });

  it("x toggles the focused row and shift+x extends the selection from the anchor", async () => {
    await renderRows();

    fireEvent.keyDown(rowFor("Backend Engineer"), { key: "x" });
    expect(within(bulkBar() as HTMLElement).getByText("1 selected")).toBeTruthy();

    // The anchor is the row `x` last acted on, so this takes rows one through three.
    fireEvent.keyDown(rowFor("Field Technician"), { key: "X", shiftKey: true });
    expect(within(bulkBar() as HTMLElement).getByText("3 selected")).toBeTruthy();

    // A second `x` on the same row un-selects it: one key, both directions.
    fireEvent.keyDown(rowFor("Data Analyst"), { key: "x" });
    expect(within(bulkBar() as HTMLElement).getByText("2 selected")).toBeTruthy();
  });

  it("selection is not carried by colour: the row reports aria-selected", async () => {
    await renderRows();

    expect(rowFor("Backend Engineer").getAttribute("aria-selected")).toBe("false");
    fireEvent.keyDown(rowFor("Backend Engineer"), { key: "x" });
    expect(rowFor("Backend Engineer").getAttribute("aria-selected")).toBe("true");
    expect(rowFor("Data Analyst").getAttribute("aria-selected")).toBe("false");
  });

  it("Cmd+A on a focused row still selects no rows and marks nothing applied", async () => {
    await renderRows();

    const row = rowFor("Backend Engineer");
    fireEvent.keyDown(row, { key: "a", metaKey: true });
    fireEvent.keyDown(row, { key: "x", metaKey: true });
    fireEvent.keyDown(row, { key: "a", ctrlKey: true });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(COLLAPSE_MS);
    });

    // A text-selection reflex must not write, and must not select rows either.
    expect(vi.mocked(markApplied)).not.toHaveBeenCalled();
    expect(vi.mocked(skipMany)).not.toHaveBeenCalled();
    expect(bulkBar()).toBeNull();
    expect(titles()).toEqual(["Backend Engineer", "Data Analyst", "Field Technician"]);
  });
});
