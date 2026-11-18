import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { Companion } from "../api/types";
import { applyReadiness } from "../lib/applyReadiness";
import { appliedRow } from "../test/rows";

vi.mock("../api/client", () => ({ getCompanions: vi.fn() }));

import { getCompanions } from "../api/client";
import { ApplyReadiness } from "../components/ApplyReadiness";

function plan(
  counts: Record<string, number>,
  over: Partial<Companion> = {},
): Companion {
  return {
    schema: "boardwatch.companion/1",
    name: "planner",
    updated_at: "2026-11-17T10:00:00+00:00",
    state: "ok",
    summary: "plan built",
    counts,
    items: [],
    ...over,
  };
}

const COUNTS = {
  "fillable:ashby": 150,
  "fillable:greenhouse": 107,
  "dropped:apply by hand": 416,
  "waiting:cloudflare": 241,
  asked: 80,
};

it("divides fillable by the 7-day rate: 257 at 17/day is about 15.1 days", () => {
  const r = applyReadiness([plan(COUNTS)], 17);
  expect(r.fillableTotal).toBe(257);
  expect(r.fillable).toEqual([
    { label: "ashby", count: 150 },
    { label: "greenhouse", count: 107 },
  ]);
  expect(r.dropped).toEqual([{ label: "apply by hand", count: 416 }]);
  expect(r.waiting).toEqual([{ label: "cloudflare", count: 241 }]);
  expect(r.days).toBeCloseTo(15.118, 2);
  expect(r.low).toBe(false);
});

it("is low under 2 days and not at exactly 2", () => {
  expect(applyReadiness([plan({ "fillable:ashby": 19 })], 10).low).toBe(true);
  expect(applyReadiness([plan({ "fillable:ashby": 20 })], 10).low).toBe(false);
});

it("gives no estimate with no applications, and no plan from a failed or plan-less companion", () => {
  expect(applyReadiness([plan(COUNTS)], 0).days).toBeNull();
  expect(
    applyReadiness([plan(COUNTS, { state: "failed" })], 5).source,
  ).toBeNull();
  expect(applyReadiness([plan({ asked: 3 })], 5).source).toBeNull();
});

it("shows the pace with no companion installed", async () => {
  vi.mocked(getCompanions).mockResolvedValue({ companions: [] });
  render(
    <ApplyReadiness
      rows={[appliedRow({ submitted_at: new Date().toISOString() })]}
    />,
  );
  const section = screen.getByRole("region", { name: "Apply-lane readiness" });
  // One application today over a 7-day window is 1/7 = 0.1 a day.
  expect(
    await within(section).findByText(
      /No apply plan reported\. Pace: 0\.1 applications a day/,
    ),
  ).toBeDefined();
});

it("shows the days of capacity and the amber line from a companion plan", async () => {
  vi.mocked(getCompanions).mockResolvedValue({
    companions: [plan({ "fillable:ashby": 1 })],
  });
  const today = new Date().toISOString();
  const rows = Array.from({ length: 7 }, () =>
    appliedRow({ submitted_at: today }),
  );
  render(<ApplyReadiness rows={rows} />);
  // 7 today over 7 days is 1 a day; 1 fillable lead is 1.0 day, under the 2-day line.
  expect(await screen.findByText("Under 2 days of ready leads.")).toBeDefined();
  expect(screen.getByText("1.0")).toBeDefined();
});
