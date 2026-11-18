import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { RunTrendPoint, RunTrends as RunTrendsData } from "../api/types";
import { median, segments, slowReadout } from "../lib/runTrends";

vi.mock("../api/client", () => ({
  getRunTrends: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getRunTrends } from "../api/client";
import { RunTrends } from "../components/RunTrends";

function point(id: number, overrides: Partial<RunTrendPoint> = {}): RunTrendPoint {
  return {
    id,
    started: null,
    finished: null,
    seconds: 1200,
    new_count: 100,
    stage_seconds: { scan: 600, tailor: 300 },
    newly_eligible: 3000,
    resumes_built: 8,
    ...overrides,
  };
}

async function renderTrends(data: RunTrendsData): Promise<HTMLElement> {
  vi.mocked(getRunTrends).mockResolvedValue(data);
  render(<RunTrends />);
  return screen.findByRole("region", { name: "Run trends" });
}

it("draws one sparkline per measure with the latest value in text", async () => {
  const strip = await renderTrends({
    stage_names: ["scan", "tailor"],
    runs: [point(1), point(2), point(3, { seconds: 1260, new_count: 4321 })],
  });

  for (const label of ["run length", "scan", "tailor", "new postings", "newly eligible", "résumés built"]) {
    expect(within(strip).getByText(label)).toBeDefined();
  }
  // The latest value is printed, not only drawn.
  expect(within(strip).getByRole("img", { name: /new postings, last 3 runs, latest 4,321/ })).toBeDefined();
  expect(within(strip).getByRole("img", { name: /run length, last 3 runs, latest 21 min/ })).toBeDefined();
});

it("names the slow run and the stage that made it slow", async () => {
  const usual = { scan: 600, tailor: 300 };
  const strip = await renderTrends({
    stage_names: ["scan", "tailor"],
    runs: [
      point(1, { seconds: 900, stage_seconds: usual }),
      point(2, { seconds: 900, stage_seconds: usual }),
      point(3, { seconds: 900, stage_seconds: usual }),
      point(4, { seconds: 2100, stage_seconds: { scan: 620, tailor: 1500 } }),
    ],
  });

  // Median of the three before it is 15 min; the newest took 35 min. Scan is +20 s, tailor +1200 s.
  expect(within(strip).getByText(/Run 4 took 35 min, 2\.3× the 15 min median/)).toBeDefined();
  expect(within(strip).getByText(/Furthest over its usual: tailor, 25 min against 5\.0 min/)).toBeDefined();
});

it("says an ordinary run is in line with the median", async () => {
  const steady = await renderTrends({
    stage_names: [],
    runs: [point(1), point(2), point(3), point(4, { seconds: 1250 })],
  });
  expect(within(steady).getByText(/Run 4 took 21 min, in line with the 20 min median/)).toBeDefined();
});

it("does not call a run slow on fewer than three earlier runs", () => {
  expect(slowReadout([point(1), point(2), point(3, { seconds: 99999 })])).toBeNull();
});

it("shows a run that was not measured as a gap and counts it, never as zero", async () => {
  const strip = await renderTrends({
    stage_names: ["scan"],
    runs: [
      point(1),
      point(2, { resumes_built: null, stage_seconds: null, newly_eligible: null }),
      point(3),
      point(4, { resumes_built: null }),
    ],
  });

  // The newest run's own value is missing: an em dash, not 0.
  const built = within(strip).getByRole("img", { name: /résumés built, last 4 runs, latest —/ });
  expect(built.closest("li")?.textContent).toContain("2 not measured");
  expect(built.closest("li")?.textContent).not.toMatch(/\b0\b/);
  // Run 2 has no stage times at all, and the stage's median ignores it.
  expect(within(strip).getByRole("img", { name: /^scan, last 4 runs, latest 10 min/ })).toBeDefined();
});

it("breaks the line at a gap instead of joining across it", () => {
  const parts = segments([5, null, 7, 9, null, 2], 100, 20, 2);
  expect(parts.map((part) => part.length)).toEqual([1, 2, 1]);
  // x keeps the run order, so a gap leaves the space it occupied.
  expect(parts[1]?.[0]?.[0]).toBeCloseTo(2 + 2 * ((100 - 4) / 5));
  // From zero: the series maximum sits at the top, a zero-only series sits flat on the floor.
  expect(parts[1]?.[1]?.[1]).toBe(2);
  expect(segments([0, 0], 100, 20, 2)[0]?.map(([, y]) => y)).toEqual([18, 18]);
});

it("takes the median of the measured values only", () => {
  expect(median([null, 4, null, 10, 6])).toBe(6);
  expect(median([null, null])).toBeNull();
});

it("says so when the trends cannot be loaded, and draws nothing for an empty history", async () => {
  vi.mocked(getRunTrends).mockRejectedValue(new Error("404"));
  const { unmount } = render(<RunTrends />);
  expect(await screen.findByText(/Run trends could not be loaded/)).toBeDefined();
  unmount();

  vi.mocked(getRunTrends).mockClear();
  vi.mocked(getRunTrends).mockResolvedValue({ stage_names: [], runs: [] });
  const { container } = render(<RunTrends />);
  await vi.waitFor(() => {
    expect(vi.mocked(getRunTrends)).toHaveBeenCalledTimes(1);
  });
  // Let the resolved request land before reading the DOM.
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(container.textContent).toBe("");
});
