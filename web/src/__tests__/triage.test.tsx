import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueDetail, QueueRow, RequirementView } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { describeGroup, firstOfEachGroup, normaliseTitle, relatedPostings, similarGroups } from "../lib/similar";
import { queueResponse, queueRow } from "../test/rows";

/*
 * The queue's triage accelerators: similar roles, select-by-company, "did you apply?" on return,
 * follow-up presets, the evidence jump into the description, and saved views. Each test names the
 * behaviour a reader relies on; the pure helpers are pinned on the shapes measured on the live
 * queue (city and formatting variants of one title).
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
  report: vi.fn(),
  unreport: vi.fn(),
  setFollowUp: vi.fn(),
  clearFollowUp: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getAnswers, getDetail, getQueue, markApplied } from "../api/client";
import { App } from "../App";

function grid(): HTMLElement {
  return screen.getByRole("grid", { name: "Jobs to explore" });
}

function dataRows(): HTMLElement[] {
  return within(grid())
    .getAllByRole("row")
    .filter((element) => element.hasAttribute("data-row-id"));
}

function rowFor(text: string): HTMLElement {
  const found = dataRows().find((row) => within(row).queryAllByText(text).length > 0);
  if (found === undefined) throw new Error(`no row for ${text}`);
  return found;
}

async function settle(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function renderQueue(rows = defaultRows()) {
  lastRows = rows;
  vi.mocked(getQueue).mockResolvedValue(queueResponse(rows));
  vi.mocked(getAnswers).mockResolvedValue({ identity: {}, work_auth: {}, education: [], questions: [] });
  render(<App />);
  await settle();
  return rows;
}

let lastRows: QueueRow[] = [];
function rows0(): QueueRow {
  const first = lastRows[0];
  if (first === undefined) throw new Error("no rows");
  return first;
}

function defaultRows() {
  return [
    queueRow({ company: "Globex", title: "Software Engineer, New Grad", location: "Austin, TX" }),
    queueRow({ company: "Globex", title: "Software Engineer - New Grad (Remote)", location: "Remote" }),
    queueRow({ company: "globex ", title: "Data Analyst" }),
    queueRow({ company: "Initech", title: "Backend Engineer" }),
  ];
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  window.sessionStorage.clear();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/#/queue");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("similar roles", () => {
  it("folds case, dashes, punctuation and a work-mode suffix out of a title", () => {
    expect(normaliseTitle("Software Engineer, New Grad")).toBe("software engineer new grad");
    expect(normaliseTitle("Software Engineer - New Grad (Remote)")).toBe(
      "software engineer new grad",
    );
    expect(normaliseTitle("Backend Engineer – Hybrid")).toBe("backend engineer");
    // A parenthetical that is NOT a work mode is part of the role and stays.
    expect(normaliseTitle("Engineer (Payments)")).toBe("engineer payments");
  });

  it("groups two or more, says what a group holds, and keeps the first of each in the order given", () => {
    const rows = defaultRows();
    const groups = similarGroups(rows);
    // Two groups' worth of members, each knowing its own size and how many places it spans.
    expect([...groups.values()].map((group) => group.count)).toEqual([2, 2]);
    expect([...groups.values()].map((group) => group.locations)).toEqual([2, 2]);
    expect(groups.has(rows[2]?.posting_id ?? -1)).toBe(false);
    expect(describeGroup(groups.get(rows[0]?.posting_id ?? -1) ?? { count: 0, locations: 0, boards: 0 })).toBe(
      "2 related postings · 2 locations",
    );
    expect(firstOfEachGroup(rows).map((row) => row.posting_id)).toEqual(
      [rows[0], rows[2], rows[3]].map((row) => row?.posting_id),
    );
    // What the fold hides is still reachable: the siblings of the one that stays.
    expect(relatedPostings(rows[0] as QueueRow, rows).map((row) => row.posting_id)).toEqual([
      rows[1]?.posting_id,
    ]);
  });

  it("does not call differently-placed postings one job: the group says how many places it spans", () => {
    const rows = [
      queueRow({ company: "Globex", title: "Engineer", location: "Austin, TX", provider: "greenhouse" }),
      queueRow({ company: "Globex", title: "Engineer", location: "Boston, MA", provider: "workday" }),
    ];
    const group = similarGroups(rows).get(rows[0]?.posting_id ?? -1);
    expect(group).toEqual({ count: 2, locations: 2, boards: 2 });
    expect(describeGroup(group ?? { count: 0, locations: 0, boards: 0 })).toBe(
      "2 related postings · 2 locations · 2 job boards",
    );
  });

  it("marks both grouped rows, folds the second under the first on request, and keeps it reachable", async () => {
    await renderQueue();
    expect(screen.getAllByText("2 related postings · 2 locations")).toHaveLength(2);
    expect(dataRows()).toHaveLength(4);

    fireEvent.click(screen.getByRole("checkbox", { name: "Collapse similar roles" }));
    expect(dataRows()).toHaveLength(3);
    // The one left still says how many it stands for.
    expect(screen.getAllByText("2 related postings · 2 locations")).toHaveLength(1);

    // And the one that was folded is not discarded: opening the survivor lists it, by place.
    const survivor = rows0();
    vi.mocked(getDetail).mockResolvedValue({
      row: survivor,
      jd_body: "A description.",
      requirements: [],
      board_target: null,
    });
    fireEvent.click(within(rowFor("Software Engineer, New Grad")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    screen.getByRole("heading", { name: "Related postings (1)" });
    screen.getByRole("button", { name: /^Remote/ });

    fireEvent.click(screen.getByRole("checkbox", { name: "Collapse similar roles" }));
    expect(dataRows()).toHaveLength(4);
  });
});

describe("select by company", () => {
  it("adds every listed lead at the row's company to the selection on c", async () => {
    await renderQueue();
    const row = rowFor("Data Analyst");
    row.focus();
    fireEvent.keyDown(row, { key: "c" });

    // Three at Globex, whatever the case and stray spaces of the company name; not Initech.
    expect(screen.getByText("3 selected")).toBeTruthy();
    expect(rowFor("Backend Engineer").getAttribute("aria-selected")).toBe("false");
  });
});

describe("did you apply? on return", () => {
  beforeEach(() => {
    vi.spyOn(window, "open").mockReturnValue(null);
  });

  /* jsdom's tab never hides, so the visibility the listener reads is driven by hand. */
  function setVisibility(state: "hidden" | "visible"): void {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
    document.dispatchEvent(new Event("visibilitychange"));
  }

  function leaveAndReturn(): void {
    act(() => {
      setVisibility("hidden");
      setVisibility("visible");
    });
  }

  it("asks after o opened the apply page and the reader came back, and a records it", async () => {
    const rows = await renderQueue();
    vi.mocked(markApplied).mockResolvedValue({ outcome: "created", job_id: 1 });
    const row = rowFor("Backend Engineer");
    row.focus();
    fireEvent.keyDown(row, { key: "o" });
    leaveAndReturn();

    const prompt = screen.getByRole("dialog", { name: /Did you apply\?/ });
    expect(within(prompt).getByText(/Back from Initech — Backend Engineer/)).toBeTruthy();
    expect(document.activeElement?.textContent).toBe("Record application");

    fireEvent.keyDown(prompt, { key: "a" });
    await settle();
    expect(vi.mocked(markApplied)).toHaveBeenCalledWith(rows[3]?.posting_id);
    expect(screen.queryByRole("dialog", { name: /Did you apply\?/ })).toBeNull();
  });

  it("asks nothing when the tab was never hidden, however the window's focus moved", async () => {
    await renderQueue();
    const row = rowFor("Backend Engineer");
    row.focus();
    fireEvent.keyDown(row, { key: "o" });
    // Switching to another application and back: the window blurs and focuses, the tab stays
    // visible throughout.
    act(() => {
      window.dispatchEvent(new Event("blur"));
      window.dispatchEvent(new Event("focus"));
      setVisibility("visible");
    });
    expect(screen.queryByRole("dialog", { name: /Did you apply\?/ })).toBeNull();
  });

  it("asks after a click on the workspace's Open application link too, and Escape dismisses without a write", async () => {
    const rows = await renderQueue();
    const lead = rows[3];
    if (lead === undefined) throw new Error("no lead");
    vi.mocked(getDetail).mockResolvedValue({
      row: lead,
      jd_body: "A description.",
      requirements: [],
      board_target: null,
    });
    fireEvent.click(within(rowFor("Backend Engineer")).getAllByRole("button")[0] as HTMLElement);
    await settle();
    const link = screen.getByRole("link", { name: /Open application/ });
    // Cancel the navigation jsdom would attempt: the click's EFFECT on the page is what is tested.
    link.addEventListener("click", (event) => {
      event.preventDefault();
    });
    fireEvent.click(link);
    // Opening the page recorded nothing — it only armed the question.
    expect(vi.mocked(markApplied)).not.toHaveBeenCalled();
    leaveAndReturn();

    const prompt = screen.getByRole("dialog", { name: /Did you apply\?/ });
    fireEvent.keyDown(prompt, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /Did you apply\?/ })).toBeNull();
    expect(vi.mocked(markApplied)).not.toHaveBeenCalled();
    // Asked once: a second return without a new open asks nothing.
    leaveAndReturn();
    expect(screen.queryByRole("dialog", { name: /Did you apply\?/ })).toBeNull();
  });

  it("asks nothing about a lead already marked applied before the reader came back", async () => {
    await renderQueue();
    vi.mocked(markApplied).mockResolvedValue({ outcome: "created", job_id: 1 });
    const row = rowFor("Backend Engineer");
    row.focus();
    fireEvent.keyDown(row, { key: "o" });
    fireEvent.keyDown(row, { key: "a" });
    await settle();
    leaveAndReturn();
    expect(screen.queryByRole("dialog", { name: /Did you apply\?/ })).toBeNull();
  });
});

describe("the detail pane", () => {
  function isoDaysFromToday(days: number): string {
    const when = new Date();
    when.setDate(when.getDate() + days);
    const month = String(when.getMonth() + 1).padStart(2, "0");
    const day = String(when.getDate()).padStart(2, "0");
    return `${String(when.getFullYear())}-${month}-${day}`;
  }

  function requirement(overrides: Partial<RequirementView>): RequirementView {
    return {
      requirement: "degree",
      covered: true,
      rule: "degree:bachelors",
      disposition: "cleared",
      profile_field: "education",
      quote: null,
      rationale: null,
      ...overrides,
    };
  }

  function renderPane(detail: QueueDetail, onFollowUp = vi.fn()) {
    render(
      <DetailPane
        detail={detail}
        loading={false}
        error={null}
        answers={null}
        onClose={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
        onFollowUp={onFollowUp}
        onToast={() => undefined}
      />,
    );
    return onFollowUp;
  }

  it("pins a whole date in one click from the presets", () => {
    const onFollowUp = renderPane({
      row: queueRow(),
      jd_body: "A description.",
      requirements: [],
      board_target: null,
    });
    const presets = screen.getByRole("group", { name: "Follow up in" });
    fireEvent.click(within(presets).getByRole("button", { name: "In 1 week" }));
    expect(onFollowUp).toHaveBeenCalledWith(isoDaysFromToday(7));
  });

  it("jumps from an evidence quote to the same words in the description", () => {
    renderPane({
      row: queueRow(),
      jd_body: "About us. A Bachelor's degree in Computer Science is required. We ship weekly.",
      requirements: [
        requirement({ quote: "bachelor's degree in computer science" }),
        // Not in the body: no button, because there is nowhere to jump to.
        requirement({ rule: "years:three", quote: "three years of Go" }),
      ],
      board_target: null,
    });

    const buttons = screen.getAllByRole("button", { name: "Show in description" });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0] as HTMLElement);

    const mark = document.querySelector("mark");
    // The description's own casing, found case-folded.
    expect(mark?.textContent).toBe("Bachelor's degree in Computer Science");
    expect(document.activeElement).toBe(mark);
  });

  it("scrolls to the same quote again when it is asked for again", () => {
    renderPane({
      row: queueRow(),
      jd_body: "About us. A degree is required. We ship weekly.",
      requirements: [requirement({ quote: "A degree is required" })],
      board_target: null,
    });
    const scrolled = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrolled;
    const show = screen.getByRole("button", { name: "Show in description" });
    fireEvent.click(show);
    fireEvent.click(show);
    expect(scrolled).toHaveBeenCalledTimes(2);
  });

  it("does not case-fold where folding would shift the offsets", () => {
    renderPane({
      row: queueRow(),
      jd_body: "İ experience matters",
      requirements: [requirement({ quote: "EXPERIENCE" })],
      board_target: null,
    });
    // No safe location, so no jump is offered rather than a highlight on the wrong letters.
    expect(screen.queryByRole("button", { name: "Show in description" })).toBeNull();
  });

  it("selects every listed lead at the company from the pane, through the page", async () => {
    const rows = await renderQueue();
    const lead = rows[3];
    if (lead === undefined) throw new Error("no lead");
    const globex = rows[0];
    if (globex === undefined) throw new Error("no lead");
    vi.mocked(getDetail).mockResolvedValue({
      row: globex,
      jd_body: "A description.",
      requirements: [],
      board_target: null,
    });
    fireEvent.click(within(rowFor("Software Engineer, New Grad")).getAllByRole("button")[0] as HTMLElement);
    await settle();

    fireEvent.click(screen.getByRole("button", { name: "Select all 3 at Globex" }));
    expect(screen.getByText("3 selected")).toBeTruthy();
    expect(lead.company).toBe("Initech");
  });
});

describe("saved views", () => {
  it("ignores a stored view whose values are not all text, instead of crashing the queue", async () => {
    window.localStorage.setItem(
      "boardwatch.queue.views",
      JSON.stringify([
        { name: "broken", view: { query: 42 } },
        { name: "fine", view: { query: "globex" } },
      ]),
    );
    await renderQueue();
    const picker = screen.getByRole("combobox", { name: "Saved view" });
    expect(within(picker).queryByRole("option", { name: "broken" })).toBeNull();
    fireEvent.change(picker, { target: { value: "fine" } });
    expect(dataRows()).toHaveLength(3);
  });

  it("saves the filters under a name and puts them back when chosen", async () => {
    await renderQueue();
    const filter = screen.getByRole("searchbox", { name: "Search" });
    fireEvent.change(filter, { target: { value: "globex" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Collapse similar roles" }));

    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    fireEvent.change(screen.getByRole("textbox", { name: "View name" }), {
      target: { value: "globex folded" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    fireEvent.change(filter, { target: { value: "" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Collapse similar roles" }));
    expect(dataRows()).toHaveLength(4);

    fireEvent.change(screen.getByRole("combobox", { name: "Saved view" }), {
      target: { value: "globex folded" },
    });
    expect((filter as HTMLInputElement).value).toBe("globex");
    expect(screen.getByRole<HTMLInputElement>("checkbox", { name: "Collapse similar roles" }).checked).toBe(
      true,
    );
    expect(dataRows()).toHaveLength(2);
  });

  it("refuses an unnamed view beside the box, and deletes a saved one", async () => {
    await renderQueue();
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("Name the view first.")).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Saved view" })).toBeNull();

    fireEvent.change(screen.getByRole("textbox", { name: "View name" }), {
      target: { value: "mine" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete the saved view mine" }));
    expect(screen.queryByRole("combobox", { name: "Saved view" })).toBeNull();
    expect(window.localStorage.getItem("boardwatch.queue.views")).toBe("[]");
  });
});
