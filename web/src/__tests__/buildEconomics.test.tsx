import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { BuildEconomics as BuildEconomicsData } from "../api/types";

vi.mock("../api/client", () => ({ getBuildEconomics: vi.fn() }));

import { getBuildEconomics } from "../api/client";
import { BuildEconomics } from "../components/BuildEconomics";

const NAME = "Résumé build economics";

const DATA: BuildEconomicsData = {
  not_rendered_leads: 7,
  totals: { built: 10, applied: 2, closed: 3, skipped: 1, open: 4, apply_rate: 0.2, settled_rate: 2 / 6 },
  boards: [
    { board: "ashby", built: 6, applied: 2, closed: 1, skipped: 0, open: 3, apply_rate: 2 / 6, settled_rate: 2 / 3 },
    { board: "linkedin", built: 4, applied: 0, closed: 2, skipped: 1, open: 1, apply_rate: 0, settled_rate: 0 },
  ],
  runs: [
    { id: 12, finished: null, built: 3, not_rendered: 1, tailor_seconds: 90, seconds_per_resume: 30 },
    { id: 11, finished: null, built: 0, not_rendered: 2, tailor_seconds: 40, seconds_per_resume: null },
    { id: 10, finished: null, built: 5, not_rendered: 0, tailor_seconds: null, seconds_per_resume: null },
  ],
};

it("separates wasted builds from leads that are still open", async () => {
  vi.mocked(getBuildEconomics).mockResolvedValue(DATA);
  render(<BuildEconomics />);
  const section = await screen.findByRole("region", { name: NAME });
  expect(within(section).getByText(/10 résumés built, one per job/)).toBeDefined();
  // Wasted is closed + skipped = 3 + 1; the 4 open ones are named as not wasted.
  expect(within(section).getByText(/4 were wasted: 3 closed without being applied to and 1 skipped/)).toBeDefined();
  expect(within(section).getByText(/4 are still open and are not counted as wasted/)).toBeDefined();
  expect(within(section).getByText(/33% were applied to/)).toBeDefined();
  expect(within(section).getByText(/7 leads were delivered only as an unrendered review stub/)).toBeDefined();
});

it("prints the board table with the all-in and the settled rate", async () => {
  vi.mocked(getBuildEconomics).mockResolvedValue(DATA);
  render(<BuildEconomics />);
  const section = await screen.findByRole("region", { name: NAME });
  expect(within(section).getByRole("row", { name: /^ashby/ }).textContent).toBe(
    "ashby6210333%67%",
  );
  expect(within(section).getByRole("row", { name: /^linkedin/ }).textContent).toBe(
    "linkedin402110%0%",
  );
});

it("draws an untimed run, or one that built nothing, as dashes and never zero seconds", async () => {
  vi.mocked(getBuildEconomics).mockResolvedValue(DATA);
  render(<BuildEconomics />);
  const section = await screen.findByRole("region", { name: NAME });
  const row = (id: string) =>
    within(section).getByRole("row", { name: new RegExp(`^${id} `), hidden: true });
  const cells = (id: string) => [...row(id).querySelectorAll("th, td")].map((c) => c.textContent);
  // Run 12: 90 s over 3 builds is 30 s each.
  expect(cells("12")).toEqual(["12", "—", "3", "1", "1.5 min", "30 s"]);
  // Run 11 timed 40 s but built nothing; run 10 built five but was not timed.
  expect(cells("11")).toEqual(["11", "—", "0", "2", "40 s", "—"]);
  expect(cells("10")).toEqual(["10", "—", "5", "0", "—", "—"]);
  expect(within(section).getByText(/is an average/)).toBeDefined();
});

it("says nothing about stubs when there are none, and shows dashes for unmeasured rates", async () => {
  vi.mocked(getBuildEconomics).mockResolvedValue({
    not_rendered_leads: 0,
    totals: { built: 0, applied: 0, closed: 0, skipped: 0, open: 0, apply_rate: null, settled_rate: null },
    boards: [],
    runs: [],
  });
  render(<BuildEconomics />);
  const section = await screen.findByRole("region", { name: NAME });
  expect(within(section).queryByText(/unrendered review stub/)).toBeNull();
  expect(within(section).getByText(/— were applied to/)).toBeDefined();
});

it("reports a failed load without taking the page down", async () => {
  vi.mocked(getBuildEconomics).mockRejectedValue(new Error("503"));
  render(<BuildEconomics />);
  expect(await screen.findByText(/could not be loaded/)).toBeDefined();
});
