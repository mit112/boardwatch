import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Companion } from "../api/types";
import { pipelineHealth, worstTone } from "../lib/pipelineHealth";
import { runSummary } from "../test/rows";

/*
 * T293: the strip's colours, each pinned. Times are built in LOCAL time so "today" and "after
 * 06:00" mean the same thing in every test machine's zone.
 */

vi.mock("../api/client", () => ({ getRuns: vi.fn(), getCompanions: vi.fn() }));

import { getCompanions, getRuns } from "../api/client";
import { PipelineHealthStrip } from "../components/PipelineHealthStrip";

const at = (day: number, hour: number, minute = 0): string =>
  new Date(2026, 10, day, hour, minute).toISOString();
const NOW = new Date(2026, 10, 17, 11, 0);

const nightly = (over = {}) =>
  runSummary({
    kind: "delivery",
    incremental: false,
    status: "ok",
    started: at(17, 4, 0),
    finished: at(17, 4, 40),
    ...over,
  });

function companion(over: Partial<Companion> = {}): Companion {
  return {
    schema: "boardwatch.companion/1",
    name: "reviewer",
    updated_at: at(17, 10, 14),
    state: "ok",
    summary: "batch done 10:14",
    counts: {},
    items: [],
    ...over,
  };
}

describe("pipelineHealth", () => {
  it("is green when tonight's nightly ended ok and companions are ok", () => {
    const cells = pipelineHealth([nightly()], [companion()], NOW);
    expect(cells[0]).toMatchObject({ label: "Nightly run", tone: "green" });
    expect(cells[0]?.text).toMatch(/^ok, ended .*, 40 min$/);
    expect(cells[2]).toMatchObject({ label: "reviewer", tone: "green" });
  });

  it("is red when the last nightly failed", () => {
    const cells = pipelineHealth([nightly({ status: "failed" })], [], NOW);
    expect(cells[0]).toMatchObject({ tone: "red" });
    expect(cells[0]?.text).toMatch(/^failed /);
  });

  it("reads the NEWEST nightly: an older failure under a newer ok is green", () => {
    const runs = [nightly({ id: 9 }), nightly({ id: 8, status: "failed", started: at(16, 4) })];
    expect(pipelineHealth(runs, [], NOW)[0]?.tone).toBe("green");
  });

  it("is amber when no nightly started today and it is past 06:00", () => {
    const old = nightly({ started: at(16, 4), finished: at(16, 4, 40) });
    expect(pipelineHealth([old], [], NOW)[0]).toMatchObject({ tone: "amber" });
    expect(pipelineHealth([old], [], new Date(2026, 10, 17, 5, 59))[0]?.tone).toBe("green");
  });

  it("does not take an intraday pass or a scan for the nightly", () => {
    const runs = [
      runSummary({ kind: "delivery", incremental: true, status: "failed", started: at(17, 9) }),
      runSummary({ kind: "scan", incremental: false, status: "failed", started: at(17, 8) }),
      nightly(),
    ];
    const cells = pipelineHealth(runs, [], NOW);
    expect(cells[0]).toMatchObject({ label: "Nightly run", tone: "green" });
    expect(cells[1]).toMatchObject({ label: "Intraday pass", tone: "red" });
  });

  it("maps companion states: failed red, stale amber, running green", () => {
    const cells = pipelineHealth(
      [nightly()],
      [
        companion({ name: "a", state: "failed" }),
        companion({ name: "b", state: "stale" }),
        companion({ name: "c", state: "running" }),
      ],
      NOW,
    );
    expect(cells.slice(2).map((c) => c.tone)).toEqual(["red", "amber", "green"]);
    expect(worstTone(cells)).toBe("red");
  });

  it("is amber, not green, with no nightly on record", () => {
    expect(pipelineHealth([], [], NOW)[0]).toMatchObject({ tone: "amber", text: "none recorded" });
  });
});

it("the strip is red and names a failed companion's reason", async () => {
  vi.mocked(getRuns).mockResolvedValue({ runs: [nightly({ started: new Date().toISOString() })] });
  vi.mocked(getCompanions).mockResolvedValue({
    companions: [
      companion({
        state: "failed",
        summary: "reviewer batch done 10:14, store write failed: scan lock held",
      }),
    ],
  });
  render(<PipelineHealthStrip />);
  const strip = await screen.findByRole("region", { name: "Pipeline health" });
  expect(strip.dataset.tone).toBe("red");
  expect(within(strip).getByText(/store write failed: scan lock held/)).toBeDefined();
  expect(within(strip).getAllByText(/Failed\./).length).toBe(1);
});

