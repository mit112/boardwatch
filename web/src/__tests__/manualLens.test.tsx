import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/*
 * Apply by hand: a fourth list, a bulk move into it from Jobs to explore, a bulk move back out,
 * and ONE write with ONE undo each way. A move lands the rows in ANOTHER list, so the page
 * re-reads the queue after the write — `getQueue` is mocked per call below to play the server.
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
  skipMany: vi.fn(),
  unskipMany: vi.fn(),
  manualMany: vi.fn(),
  unmanualMany: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getQueue, manualMany, skipMany, unmanualMany } from "../api/client";
import { App } from "../App";

const COLLAPSE_MS = 200;

function titlesIn(name: string): string[] {
  return within(screen.getByRole("grid", { name }))
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"))
    .map((row) => within(row).getByText(/Engineer|Analyst|Technician/).textContent ?? "");
}

function lensTab(label: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(`^${label} \\d+$`) });
}

async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const a = queueRow({ company: "Globex", title: "Backend Engineer" });
const b = queueRow({ company: "Initech", title: "Data Analyst" });
const c = queueRow({ company: "Acme Corp", title: "Field Technician" });

function withManual(rows: typeof a[], manual: typeof a[]) {
  const response = queueResponse(rows);
  return { ...response, manual, counts: { ...response.counts, manual: manual.length } };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Apply by hand", () => {
  it("lists the server's `manual` rows under its own lens, and no others", async () => {
    vi.mocked(getQueue).mockResolvedValue(withManual([a, b], [c]));
    render(<App />);
    await settle();

    expect(titlesIn("Jobs to explore")).toEqual(["Backend Engineer", "Data Analyst"]);
    expect(lensTab("Apply by hand").getAttribute("aria-label")).toBe("Apply by hand 1");

    fireEvent.click(lensTab("Apply by hand"));
    expect(titlesIn("Apply by hand")).toEqual(["Field Technician"]);
    expect(screen.queryByRole("grid", { name: "Jobs to explore" })).toBeNull();
  });

  it("moves a selection in ONE call, re-reads the queue, and undoes in ONE call", async () => {
    vi.mocked(getQueue)
      .mockResolvedValueOnce(withManual([a, b, c], []))
      .mockResolvedValueOnce(withManual([b], [a, c]))
      .mockResolvedValueOnce(withManual([a, b, c], []));
    vi.mocked(manualMany).mockResolvedValue({ manual: [a.job_id, c.job_id], failed: [] });
    vi.mocked(unmanualMany).mockResolvedValue({ manual: [a.job_id, c.job_id], failed: [] });
    render(<App />);
    await settle();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select: Backend Engineer at Globex" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select: Field Technician at Acme Corp" }));
    fireEvent.click(screen.getByRole("button", { name: /^Move to manual 2 selected/ }));
    await settle(COLLAPSE_MS);

    expect(vi.mocked(manualMany)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(manualMany)).toHaveBeenCalledWith([a.job_id, c.job_id]);
    // Never a skip: the two are different dimensions on the server.
    expect(vi.mocked(skipMany)).not.toHaveBeenCalled();
    expect(titlesIn("Jobs to explore")).toEqual(["Data Analyst"]);
    expect(screen.getByText("Moved to Apply by hand: 2")).toBeTruthy();

    // The rows are in the other list, without a reload.
    fireEvent.click(lensTab("Apply by hand"));
    expect(titlesIn("Apply by hand")).toEqual(["Backend Engineer", "Field Technician"]);

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await settle();
    expect(vi.mocked(unmanualMany)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(unmanualMany)).toHaveBeenCalledWith([a.job_id, c.job_id]);
  });

  it("on the Apply by hand list the bar moves the selection back, and never offers Skip", async () => {
    vi.mocked(getQueue)
      .mockResolvedValueOnce(withManual([b], [a, c]))
      .mockResolvedValueOnce(withManual([a, b], [c]))
      .mockResolvedValueOnce(withManual([b], [a, c]));
    vi.mocked(unmanualMany).mockResolvedValue({ manual: [a.job_id], failed: [] });
    vi.mocked(manualMany).mockResolvedValue({ manual: [a.job_id], failed: [] });
    render(<App />);
    await settle();

    fireEvent.click(lensTab("Apply by hand"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select: Backend Engineer at Globex" }));
    expect(screen.queryByRole("button", { name: /^Skip 1 selected/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Move back 1 selected/ }));
    await settle(COLLAPSE_MS);

    expect(vi.mocked(unmanualMany)).toHaveBeenCalledWith([a.job_id]);
    expect(titlesIn("Apply by hand")).toEqual(["Field Technician"]);

    // The undo is the inverse: back into Apply by hand, in one call.
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await settle();
    expect(vi.mocked(manualMany)).toHaveBeenCalledWith([a.job_id]);
  });

  it("asks \"Did you apply?\" after a manual lead's apply page was opened — the list exists for that", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    vi.mocked(getQueue).mockResolvedValue(withManual([b], [a]));
    render(<App />);
    await settle();

    fireEvent.click(lensTab("Apply by hand"));
    const row = within(screen.getByRole("grid", { name: "Apply by hand" }))
      .getAllByRole("row")
      .find((candidate) => within(candidate).queryAllByText("Backend Engineer").length > 0);
    if (row === undefined) throw new Error("the manual row is not listed");
    row.focus();
    fireEvent.keyDown(row, { key: "o" });
    act(() => {
      for (const state of ["hidden", "visible"] as const) {
        Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
        document.dispatchEvent(new Event("visibilitychange"));
      }
    });

    expect(screen.getByRole("dialog", { name: /Did you apply\?/ })).toBeTruthy();
  });
});
