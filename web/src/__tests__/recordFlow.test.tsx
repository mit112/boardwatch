import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueRow } from "../api/types";
import { appliedResponse, appliedRow, queueResponse, queueRow } from "../test/rows";

/*
 * Recording an application, and working down the list.
 *
 * The properties a person is relying on, each asserted as a behaviour and not as markup:
 *
 *   - OPENING an employer's page records nothing;
 *   - PROGRESS moves only after the server confirmed the write, and only that far — a failed write
 *     leaves the number where it was and says so, and an undo takes the application back out;
 *   - the NEXT job is the next one in the VISIBLE order (sort, search and all), never a re-ranked or
 *     different one;
 *   - the END of a list, and of a batch, is a place to stop or carry on, with no pressure;
 *   - a held key or a double click cannot record a job nobody has read.
 *
 * Fake timers throughout: the row collapses for 200ms, a record is locked out for 600ms, and the
 * history read has a 12s deadline, so time is something these tests drive rather than wait for.
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
  unapply: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

import { getAnswers, getApplied, getDetail, getQueue, markApplied, markSkipped, unapply } from "../api/client";
import { App } from "../App";

const COLLAPSE_MS = 200;
const LOCK_MS = 600;

async function settle(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** The apply list's rows, in the order they are on screen. */
function visibleTitles(): string[] {
  return within(screen.getByRole("grid", { name: "Jobs to explore" }))
    .getAllByRole("row")
    .filter((row) => row.hasAttribute("data-row-id"))
    .map((row) => within(row).getByText(/Engineer|Analyst/).textContent ?? "");
}

function rowOf(title: string): HTMLElement {
  const row = within(screen.getByRole("grid", { name: "Jobs to explore" }))
    .getByText(title)
    .closest('[role="row"]');
  if (row === null) throw new Error(`no row for ${title}`);
  return row as HTMLElement;
}

/** The job the workspace is showing, by its heading. */
function openTitle(): string | null {
  return document.getElementById("lead-detail-title")?.textContent ?? null;
}

function summary(): string {
  return screen.getByRole("region", { name: "Summary" }).textContent ?? "";
}

/** The two recorded figures as numbers. Read from the sentence the reader reads, not from a prop. */
function counts(): { today: number | null; week: number | null } {
  const text = summary();
  const find = (pattern: RegExp): number | null => {
    const match = pattern.exec(text);
    return match?.[1] === undefined ? null : Number(match[1]);
  };
  return { today: find(/(\d+)\s*today/), week: find(/(\d+)\s*in the past 7 days/) };
}


function serve(rows: QueueRow[], review: QueueRow[] = []): void {
  vi.mocked(getQueue).mockResolvedValue(queueResponse(rows, review));
  vi.mocked(getDetail).mockImplementation((id: number) => {
    const row = [...rows, ...review].find((candidate) => candidate.posting_id === id);
    if (row === undefined) return Promise.reject(new Error("no such job"));
    return Promise.resolve({
      row,
      jd_body: "A description of the work.",
      requirements: [],
      board_target: null,
    });
  });
  vi.mocked(getAnswers).mockResolvedValue({ identity: {}, work_auth: {}, education: [], questions: [] });
}

/** A history with a known shape: two submitted today, one two days ago, one ten days ago, and one
 *  withdrawn today (which is the undo of a record and must not count). */
function baseline() {
  const at = (daysAgo: number): string => new Date(Date.now() - daysAgo * 86_400_000).toISOString();
  return appliedResponse([
    appliedRow({ status: "applied", submitted_at: at(0) }),
    appliedRow({ status: "interviewing", submitted_at: at(0) }),
    appliedRow({ status: "applied", submitted_at: at(2) }),
    appliedRow({ status: "applied", submitted_at: at(10) }),
    appliedRow({ status: "withdrawn", submitted_at: at(0) }),
  ]);
}

function threeJobs(): QueueRow[] {
  return [
    queueRow({ company: "Zeta Co", title: "Zeta Engineer" }),
    queueRow({ company: "Alpha Co", title: "Alpha Engineer" }),
    queueRow({ company: "Mike Co", title: "Mike Engineer" }),
  ];
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/#/queue");
  vi.mocked(getApplied).mockResolvedValue(baseline());
  vi.mocked(markApplied).mockResolvedValue({ outcome: "created", job_id: 1 });
  vi.mocked(unapply).mockResolvedValue({ outcome: "transitioned", job_id: 1 });
  vi.mocked(markSkipped).mockResolvedValue({ outcome: "skipped" });
});

afterEach(() => {
  vi.useRealTimers();
});

async function mount(rows: QueueRow[], review: QueueRow[] = []): Promise<void> {
  firstId = rows[0]?.posting_id ?? -1;
  serve(rows, review);
  render(<App />);
  await settle();
}

describe("the recorded count", () => {
  it("counts submitted applications today and in the past 7 days — and not a withdrawn one", async () => {
    await mount(threeJobs());
    // Today: applied + interviewing. Past 7 days adds the one from two days ago. The ten-day-old
    // one is outside the window and the withdrawn one is the undo of a record.
    expect(counts().today).toBe(2);
    expect(counts().week).toBe(3);
  });

  it("says it could not read the history, and offers a retry, instead of loading forever", async () => {
    vi.mocked(getApplied).mockReturnValue(new Promise(() => undefined));
    await mount(threeJobs());
    // The jobs are there and usable while the count is still pending...
    expect(visibleTitles()).toHaveLength(3);

    await settle(12_100);
    // ...and after the deadline the summary says so and offers the way to try again.
    expect(summary()).toMatch(/Couldn’t read your history/);
    vi.mocked(getApplied).mockResolvedValue(baseline());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await settle();
    expect(counts().today).toBe(2);
  });

  it("does not make the jobs wait for the history", async () => {
    vi.mocked(getApplied).mockRejectedValue(new Error("503"));
    await mount(threeJobs());
    expect(visibleTitles()).toHaveLength(3);
    expect(summary()).toMatch(/Couldn’t read your history/);
  });
});

describe("what moves the count", () => {
  it("is not moved by opening an employer's page", async () => {
    const rows = threeJobs();
    await mount(rows);
    fireEvent.click(within(rowOf("Alpha Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    const link = screen.getByRole("link", { name: /Open application/ });
    link.addEventListener("click", (event) => {
      event.preventDefault();
    });
    fireEvent.click(link);
    await settle(1000);

    expect(vi.mocked(markApplied)).not.toHaveBeenCalled();
    expect(counts().today).toBe(2);
  });

  it("moves only after the server confirmed the write", async () => {
    await mount(threeJobs());
    let confirm: (value: { outcome: "created"; job_id: number }) => void = () => undefined;
    vi.mocked(markApplied).mockReturnValue(
      new Promise((resolve) => {
        confirm = resolve;
      }),
    );

    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);
    // The row has already left the list, optimistically — and the number has NOT moved.
    expect(visibleTitles()).not.toContain("Alpha Engineer");
    expect(counts().today).toBe(2);
    expect(screen.queryByText(/Application recorded/)).toBeNull();

    await act(async () => {
      confirm({ outcome: "created", job_id: 1 });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(counts().today).toBe(3);
    expect(counts().week).toBe(4);
    screen.getByText("Application recorded for Alpha Co.");
  });

  it("is left where it was by a failed write, which also says what state things are in", async () => {
    await mount(threeJobs());
    vi.mocked(markApplied).mockRejectedValue(new Error("500"));

    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);

    expect(counts().today).toBe(2);
    // Restored, with a sentence that says nothing was saved — and no success was ever announced.
    expect(visibleTitles()).toContain("Alpha Engineer");
    screen.getByText(/Could not record the application for Alpha Co — nothing was saved/);
    expect(screen.queryByText(/Application recorded/)).toBeNull();
  });

  it("is moved back by an undo, which also puts the job back in the list", async () => {
    await mount(threeJobs());
    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);
    expect(counts().today).toBe(3);

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await settle();

    expect(vi.mocked(unapply)).toHaveBeenCalledTimes(1);
    expect(counts().today).toBe(2);
    expect(visibleTitles()).toContain("Alpha Engineer");
  });

  it("does not move when the undo itself fails — the application still stands", async () => {
    await mount(threeJobs());
    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);
    vi.mocked(unapply).mockRejectedValue(new Error("500"));

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await settle();

    expect(counts().today).toBe(3);
    expect(visibleTitles()).not.toContain("Alpha Engineer");
  });

  it("counts a job recorded again after it was withdrawn — a withdrawn history row is not a record", async () => {
    const rows = threeJobs();
    const first = rows[1];
    if (first === undefined) throw new Error("no row");
    // The history already holds a WITHDRAWN attempt on this very posting.
    vi.mocked(getApplied).mockResolvedValue(
      appliedResponse([
        appliedRow({
          posting_id: first.posting_id,
          status: "withdrawn",
          submitted_at: new Date().toISOString(),
        }),
      ]),
    );
    await mount(rows);
    expect(counts().today).toBe(0);

    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);
    expect(counts().today).toBe(1);
  });
});

describe("recording from the workspace without a session", () => {
  it("says what happened, offers the next job and an undo, and keeps the place in the list", async () => {
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    expect(openTitle()).toBe("Zeta Engineer");

    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    // The workspace did not close: it says what the click did, in the past tense.
    screen.getByRole("heading", { name: "Application recorded for Zeta Co." });
    expect(screen.getAllByRole("button", { name: "Undo" }).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Continue to next role" }));
    await settle();
    // The next job in the list as it stands, and the recorded one is not in it.
    expect(openTitle()).toBe("Alpha Engineer");
    expect(visibleTitles()).toEqual(["Alpha Engineer", "Mike Engineer"]);
  });

  it("does not say the application is recorded until the server has answered", async () => {
    let answer: (value: Awaited<ReturnType<typeof markApplied>>) => void = () => undefined;
    vi.mocked(markApplied).mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    // Still waiting: the panel says so, claims nothing, and Undo has nothing to take back yet.
    screen.getByRole("heading", { name: /Recording your application for Zeta Co/ });
    expect(screen.queryByRole("heading", { name: /Application recorded/ })).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Undo" }).disabled).toBe(true);
    expect(vi.mocked(unapply)).not.toHaveBeenCalled();

    await act(async () => {
      answer({ outcome: "created", job_id: 1 });
      await vi.advanceTimersByTimeAsync(0);
    });
    screen.getByRole("heading", { name: "Application recorded for Zeta Co." });
    expect(screen.getAllByRole<HTMLButtonElement>("button", { name: "Undo" })[0]?.disabled).toBe(false);
  });

  it("never shows the recorded heading when the write fails", async () => {
    vi.mocked(markApplied).mockRejectedValue(new Error("down"));
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    expect(screen.queryByRole("heading", { name: /Application recorded/ })).toBeNull();
    expect(visibleTitles()).toContain("Zeta Engineer");
    expect(counts().today).toBe(2);
  });

  it("keeps focus in the workspace after the panel's Undo, and a second Undo changes nothing", async () => {
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    const buttons = screen.getAllByRole("button", { name: "Undo" });
    const panelUndo = buttons[0] as HTMLElement;
    const toastUndo = buttons[buttons.length - 1] as HTMLElement;
    fireEvent.click(panelUndo);
    await settle();
    expect(document.activeElement).not.toBe(document.body);
    expect(document.getElementById("lead-detail")?.contains(document.activeElement)).toBe(true);

    // The toast's Undo outlives the panel. Pressing it now finds the work done: it must not pull
    // the reader back to the job from wherever they have gone since.
    const search = screen.getByLabelText("Search");
    search.focus();
    fireEvent.click(toastUndo);
    await settle();
    expect(document.activeElement).toBe(search);
    expect(openTitle()).toBe("Zeta Engineer");
    expect(visibleTitles().filter((title) => title === "Zeta Engineer")).toHaveLength(1);
  });

  it("does not reopen the job when the toast's Undo is used after the reader left the panel", async () => {
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);
    const toastUndo = screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement;

    fireEvent.keyDown(window, { key: "Escape" });
    await settle();
    expect(openTitle()).toBeNull();

    fireEvent.click(toastUndo);
    await settle();
    // The job is back on the list, and the reader was left where they were.
    expect(visibleTitles()).toContain("Zeta Engineer");
    expect(openTitle()).toBeNull();
  });

  it("leaves the recorded panel on Escape", async () => {
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);
    screen.getByRole("heading", { name: "Application recorded for Zeta Co." });

    fireEvent.keyDown(window, { key: "Escape" });
    await settle();
    expect(screen.queryByRole("heading", { name: /Application recorded/ })).toBeNull();
    expect(openTitle()).toBeNull();
  });

  it("brings the job straight back when the recorded panel's Undo is used", async () => {
    await mount(threeJobs());
    fireEvent.click(within(rowOf("Zeta Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    fireEvent.click(screen.getAllByRole("button", { name: "Undo" })[0] as HTMLElement);
    await settle();

    expect(vi.mocked(unapply)).toHaveBeenCalledTimes(1);
    expect(openTitle()).toBe("Zeta Engineer");
    expect(visibleTitles()).toContain("Zeta Engineer");
  });
});

describe("the summary strip under a search", () => {
  it("says it is counting only this search, so an empty search is not read as nothing needing attention", async () => {
    await mount(threeJobs());
    expect(summary()).toContain("Nothing right now.");
    expect(summary()).not.toContain("in this search");

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "no such job anywhere" } });
    await settle();

    expect(summary()).toContain("Needs attention in this search");
    expect(summary()).toContain("Nothing in this search.");
    expect(summary()).not.toContain("Nothing right now.");
    // The workspace does not invite opening a job when none is listed.
    screen.getByRole("heading", { name: "No job to open", hidden: true });
  });
});

describe("the apply session", () => {
  it("is off until it is started, and starts on the first visible job", async () => {
    await mount(threeJobs());
    expect(screen.queryByRole("region", { name: "Apply session" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();

    expect(openTitle()).toBe("Zeta Engineer");
    expect(within(screen.getByRole("region", { name: "Apply session" })).getByText(/0 recorded this session/)).toBeTruthy();
  });

  it("moves on in the VISIBLE order — sorted and filtered — and never to a job outside it", async () => {
    const rows = [
      queueRow({ company: "Zeta Co", title: "Zeta Engineer" }),
      queueRow({ company: "Alpha Co", title: "Alpha Engineer" }),
      queueRow({ company: "Middle Co", title: "Middle Analyst" }),
      queueRow({ company: "Mike Co", title: "Mike Engineer" }),
    ];
    await mount(rows);
    // The reader's own view: sorted by company, narrowed to "Engineer". The ranker's order would
    // go Zeta, Alpha, Middle, Mike; the visible order is Alpha, Mike, Zeta and has no Analyst.
    fireEvent.change(screen.getByRole("combobox", { name: "Sort by" }), { target: { value: "company:asc" } });
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "Engineer" } });
    expect(visibleTitles()).toEqual(["Alpha Engineer", "Mike Engineer", "Zeta Engineer"]);

    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();
    expect(openTitle()).toBe("Alpha Engineer");

    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);
    // Next in the visible order is Mike — not Zeta (rank-next) and not Middle Analyst (filtered out).
    expect(openTitle()).toBe("Mike Engineer");
    // And the place the reader built survived: same search, same sort.
    expect(screen.getByLabelText<HTMLInputElement>("Search").value).toBe("Engineer");
    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Sort by" }).value).toBe("company:asc");
    expect(visibleTitles()).toEqual(["Mike Engineer", "Zeta Engineer"]);
  });

  it("skipping also moves the workspace on, because skipping is part of working the list", async () => {
    await mount(threeJobs());
    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();
    expect(openTitle()).toBe("Zeta Engineer");

    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    await settle(COLLAPSE_MS);

    expect(vi.mocked(markSkipped)).toHaveBeenCalledTimes(1);
    expect(openTitle()).toBe("Alpha Engineer");
    // A skip is not an application: the tally and the count are untouched.
    expect(within(screen.getByRole("region", { name: "Apply session" })).getByText(/0 recorded/)).toBeTruthy();
    expect(counts().today).toBe(2);
  });

  it("counts only recorded applications in its tally, and a failure takes the reader back to the job", async () => {
    await mount(threeJobs());
    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();

    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);
    expect(within(screen.getByRole("region", { name: "Apply session" })).getByText(/1 recorded/)).toBeTruthy();

    await settle(LOCK_MS);
    vi.mocked(markApplied).mockRejectedValue(new Error("500"));
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    // The write failed: the tally did not move, the job is back on the list AND in the workspace,
    // where the message about it is.
    expect(within(screen.getByRole("region", { name: "Apply session" })).getByText(/1 recorded/)).toBeTruthy();
    expect(openTitle()).toBe("Alpha Engineer");
    expect(visibleTitles()).toContain("Alpha Engineer");
    screen.getByText(/Could not record the application for Alpha Co/);
  });

  it("ends gracefully at the last job in the list, offering the other list when it has work", async () => {
    const review = [queueRow({ company: "Held Co", title: "Held Engineer", review_reason: "unevaluated" })];
    await mount([queueRow({ company: "Only Co", title: "Only Engineer" })], review);
    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();

    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    screen.getByRole("heading", { name: "That was the last job in this list." });
    // Two equal choices: carry on in the other list, or stop here.
    screen.getByRole("button", { name: "Look at jobs that need review (1)" });
    screen.getByRole("button", { name: "Finish for now" });

    fireEvent.click(screen.getByRole("button", { name: "Look at jobs that need review (1)" }));
    await settle();
    expect(openTitle()).toBe("Held Engineer");
  });

  it("offers only Finish for now when nothing else is waiting", async () => {
    await mount([queueRow({ company: "Only Co", title: "Only Engineer" })]);
    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    await settle(COLLAPSE_MS);

    screen.getByRole("heading", { name: "That was the last job in this list." });
    expect(screen.queryByRole("button", { name: /Keep going|Look at|Back to jobs/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Finish for now" }));
    expect(screen.queryByRole("region", { name: "Apply session" })).toBeNull();
  });

  it("offers a batch of five without requiring one, and closes it with two equal choices", async () => {
    const rows = Array.from({ length: 7 }, (_, index) =>
      queueRow({ company: `Co ${String(index)}`, title: `Job ${String(index)} Engineer` }),
    );
    await mount(rows);
    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();
    // No batch was asked for, and none is required: the session simply runs.
    const bar = screen.getByRole("region", { name: "Apply session" });
    expect(within(bar).getByText(/0 recorded this session/)).toBeTruthy();
    fireEvent.click(within(bar).getByRole("button", { name: "Work in a batch of 5" }));
    expect(within(bar).getByText(/0 recorded of 5 this session/)).toBeTruthy();

    for (let n = 0; n < 5; n += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Record application" }));
      await settle(COLLAPSE_MS);
      await settle(LOCK_MS);
    }

    screen.getByRole("heading", { name: "5 recorded." });
    expect(screen.getByRole("button", { name: "Keep going" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Finish for now" })).toBeTruthy();
    // Keeping going lifts the batch limit and opens the next job; nothing is pressed on anyone.
    fireEvent.click(screen.getByRole("button", { name: "Keep going" }));
    await settle();
    expect(openTitle()).toBe("Job 5 Engineer");
    expect(within(screen.getByRole("region", { name: "Apply session" })).getByText(/5 recorded this session/)).toBeTruthy();
  });
});

describe("a held key or a double click", () => {
  it("cannot record a job the reader has not seen", async () => {
    await mount(threeJobs());

    fireEvent.keyDown(rowOf("Zeta Engineer"), { key: "a" });
    // The OS repeat of that same held key, aimed at whatever row has focus by now.
    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a", repeat: true });
    // And a fresh press inside the lockout window — a double click, or a key bounce.
    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);

    expect(vi.mocked(markApplied)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(markApplied)).toHaveBeenCalledWith(threeJobsFirstId());

    // After the lockout a deliberate press works again, so the guard costs nothing.
    await settle(LOCK_MS);
    fireEvent.keyDown(rowOf("Alpha Engineer"), { key: "a" });
    await settle(COLLAPSE_MS);
    expect(vi.mocked(markApplied)).toHaveBeenCalledTimes(2);
  });

  it("cannot record the NEXT job in a session by repeating the click", async () => {
    await mount(threeJobs());
    fireEvent.click(screen.getByRole("button", { name: /Start applying/ }));
    await settle();

    const record = screen.getByRole("button", { name: "Record application" });
    fireEvent.click(record);
    // The workspace has moved on, but the button is the same element; a second click lands on it
    // before the next job has been read.
    fireEvent.click(record);
    await settle(COLLAPSE_MS);

    expect(vi.mocked(markApplied)).toHaveBeenCalledTimes(1);
  });
});

let firstId = -1;
function threeJobsFirstId(): number {
  return firstId;
}
