import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AppliedRow } from "../api/types";
import { applicationPace } from "../lib/applicationPace";
import { appliedResponse, appliedRow } from "../test/rows";

/*
 * T297, application pace. Every expected number below is written out by hand from the fixture
 * rows' own days, never recomputed with `applicationPace` or any other code under test.
 *
 * Instants are built from LOCAL calendar fields (`new Date(y, m, d, h, min)`), so the suite means
 * the same thing in every time zone it runs in: "23:30 yesterday" is 23:30 yesterday on this
 * machine's clock, and the page buckets by that same clock.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
  getApplied: vi.fn(),
  setApplicationStatus: vi.fn(),
  addApplicationNote: vi.fn(),
  getApplicationEvents: vi.fn(),
  markApplied: vi.fn(),
  markSkipped: vi.fn(),
  unskip: vi.fn(),
  unapply: vi.fn(),
  setJobFollowUp: vi.fn(),
  clearJobFollowUp: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

import { getApplied, getQueue } from "../api/client";
import { App } from "../App";

// Tuesday 17 November 2026, mid-afternoon. A month boundary and a US daylight-saving change both
// sit inside the 30-day window behind it.
const NOW = new Date(2026, 10, 17, 14, 0);

const GREENHOUSE = "https://boards.greenhouse.io/acme/jobs/1";
const LEVER = "https://jobs.lever.co/acme/1";
const ASHBY = "https://jobs.ashbyhq.com/acme/1";

/** A submitted application `daysAgo` local days before NOW, at the given local time. */
function sent(
  daysAgo: number,
  hour: number,
  minute: number,
  overrides: Partial<AppliedRow> = {},
): AppliedRow {
  const at = new Date(2026, 10, 17 - daysAgo, hour, minute).toISOString();
  return appliedRow({ submitted_at: at, created_at: at, ...overrides });
}

/** The ten rows of the table of facts: seven count, three do not. */
function fixtureRows(): AppliedRow[] {
  return [
    sent(0, 0, 30, { apply_url: GREENHOUSE, provider: "greenhouse" }), // a: today, just past midnight
    sent(0, 13, 0, { apply_url: GREENHOUSE, provider: "greenhouse", status: "interviewing" }), // b
    sent(1, 23, 30, { apply_url: LEVER, provider: "lever" }), // c: yesterday, 23:30
    sent(3, 9, 0, { apply_url: LEVER, provider: "lever", status: "offer" }), // d
    sent(6, 9, 0, { apply_url: ASHBY, provider: "ashby", status: "rejected" }), // e: 7th day back
    sent(7, 9, 0, { apply_url: GREENHOUSE, provider: "greenhouse" }), // f: in 30, not in 7
    sent(29, 9, 0, { apply_url: null, provider: null }), // g: oldest day of the window
    sent(30, 9, 0, { apply_url: GREENHOUSE, provider: "greenhouse" }), // h: one day too old
    sent(0, 10, 0, { apply_url: GREENHOUSE, provider: "greenhouse", status: "withdrawn" }), // i
    appliedRow({
      status: "interested",
      submitted_at: null,
      created_at: new Date(2026, 10, 17, 8, 0).toISOString(),
      apply_url: GREENHOUSE,
      provider: "greenhouse",
    }), // j: tracked, never submitted
  ];
}

describe("applicationPace", () => {
  it("buckets submitted applications by local day over exactly 30 days", () => {
    const pace = applicationPace(fixtureRows(), NOW);

    expect(pace.days).toHaveLength(30);
    // Index 0 is 29 days back (g), index 29 is today (a, b). The 23:30 application (c) is on
    // yesterday's bar and the 00:30 one (a) on today's, whatever the UTC offset is.
    // d is 3 days back (index 26), e 6 back (23), f 7 back (22). h (30 back) and the withdrawn
    // and never-submitted rows appear nowhere.
    const expected = new Array<number>(30).fill(0);
    expected[0] = 1;
    expected[22] = 1;
    expected[23] = 1;
    expected[26] = 1;
    expected[28] = 1;
    expected[29] = 2;
    expect(pace.days.map((day) => day.count)).toEqual(expected);
    expect(pace.total).toBe(7);
    expect(pace.peak).toBe(2);
  });

  it("averages the last 7 days including today, over 7", () => {
    // a, b, c, d, e fall in the last seven days; f (7 back) does not. 5 / 7.
    expect(applicationPace(fixtureRows(), NOW).average).toBeCloseTo(5 / 7, 10);
  });

  it("splits by apply board and by discovery source, ties by label", () => {
    const pace = applicationPace(fixtureRows(), NOW);
    // Counted over the seven in-window applications: a, b, f on greenhouse; c, d on lever; e on
    // ashby; g with neither a link nor a provider.
    expect(pace.byBoard).toEqual([
      { label: "greenhouse", count: 3 },
      { label: "lever", count: 2 },
      { label: "ashby", count: 1 },
      { label: "no link recorded", count: 1 },
    ]);
    expect(pace.bySource).toEqual([
      { label: "greenhouse", count: 3 },
      { label: "lever", count: 2 },
      { label: "ashby", count: 1 },
      { label: "not recorded", count: 1 },
    ]);
  });

  it("reads an old server's row with no provider key as not recorded", () => {
    const row = sent(2, 9, 0, { apply_url: LEVER });
    delete row.provider;
    expect(applicationPace([row], NOW).bySource).toEqual([{ label: "not recorded", count: 1 }]);
  });

  it("folds a long tail into one other line that keeps the total", () => {
    // Eight providers with 8, 7, 6, 5, 4, 3, 2, 1 applications: five stay, three fold to 3+2+1.
    const rows: AppliedRow[] = [];
    const sizes: [string, number][] = [
      ["p1", 8],
      ["p2", 7],
      ["p3", 6],
      ["p4", 5],
      ["p5", 4],
      ["p6", 3],
      ["p7", 2],
      ["p8", 1],
    ];
    for (const [provider, size] of sizes) {
      for (let i = 0; i < size; i += 1) rows.push(sent(1, 9, i, { provider }));
    }
    expect(applicationPace(rows, NOW).bySource).toEqual([
      { label: "p1", count: 8 },
      { label: "p2", count: 7 },
      { label: "p3", count: 6 },
      { label: "p4", count: 5 },
      { label: "p5", count: 4 },
      { label: "other", count: 6 },
    ]);
  });

  it("returns a full window of zeros for no rows", () => {
    const pace = applicationPace([], NOW);
    expect(pace.days.map((day) => day.count)).toEqual(new Array<number>(30).fill(0));
    expect(pace.total).toBe(0);
    expect(pace.average).toBe(0);
    expect(pace.byBoard).toEqual([]);
  });
});

async function renderApplied(rows: AppliedRow[]): Promise<void> {
  vi.mocked(getApplied).mockResolvedValue(appliedResponse(rows));
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  window.sessionStorage.clear();
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
      lane_copy: 0,
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

/** The same short date the chart prints, for a day `daysAgo` before NOW. */
function dayText(daysAgo: number): string {
  return new Date(2026, 10, 17 - daysAgo).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/** The daily bars list, apart from the two split lists beside it. */
function chart(section: HTMLElement): HTMLElement {
  return within(section).getByRole("list", { name: "Applications per day, oldest first" });
}

describe("the pace section on the applied page", () => {
  it("shows the totals, the 30 daily bars and both splits", async () => {
    await renderApplied(fixtureRows());
    const section = screen.getByRole("region", { name: /Application pace/ });

    // 7 in the window, 5 in the last seven days: 5 / 7 = 0.71 -> "0.7".
    expect(section.textContent).toContain("7 submitted");
    expect(within(section).getByText("0.7")).toBeTruthy();

    const bars = within(chart(section)).getAllByRole("listitem");
    expect(bars).toHaveLength(30);
    expect(bars.at(-1)?.textContent).toBe(`${dayText(0)}: 2 applications`);
    expect(bars.at(-2)?.textContent).toBe(`${dayText(1)}: 1 application`);
    expect(bars.at(0)?.textContent).toBe(`${dayText(29)}: 1 application`);

    const board = within(section).getByRole("heading", { name: "By apply board" }).parentElement;
    expect(board?.textContent).toContain("greenhouse3");
    expect(board?.textContent).toContain("no link recorded1");
    const source = within(section).getByRole("heading", { name: "By discovery source" })
      .parentElement;
    expect(source?.textContent).toContain("lever2");
    expect(source?.textContent).toContain("not recorded1");
  });

  it("words a day with none as a count, with no failure language anywhere in the section", async () => {
    await renderApplied(fixtureRows());
    const section = screen.getByRole("region", { name: /Application pace/ });
    const bars = within(chart(section)).getAllByRole("listitem");
    // Two days back had no application in the fixture.
    expect(bars.at(-3)?.textContent).toBe(`${dayText(2)}: 0 applications`);
    expect(section.textContent).not.toMatch(
      /miss|fail|nothing|none sent|no applications sent|behind|slow|goal|target/i,
    );
  });

  it("says plainly that the window is empty, and still draws the thirty zero bars", async () => {
    await renderApplied([sent(45, 9, 0)]);
    const section = screen.getByRole("region", { name: /Application pace/ });
    expect(section.textContent).toContain("No submitted applications are recorded in these 30 days.");
    expect(within(chart(section)).getAllByRole("listitem")).toHaveLength(30);
    expect(section.textContent).toContain("0 submitted");
    expect(section.textContent).not.toMatch(/miss|fail|nothing|behind|slow/i);
  });
});
