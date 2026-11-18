import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { Companion } from "../api/types";
import { needsCount, needsYou } from "../lib/needsYou";
import { queueResponse, queueRow } from "../test/rows";

vi.mock("../api/client", () => ({ getQueue: vi.fn(), getCompanions: vi.fn() }));

import { getCompanions, getQueue } from "../api/client";
import { NeedsYouPage } from "../routes/NeedsYouPage";

function companion(items: Companion["items"]): Companion {
  return {
    schema: "boardwatch.companion/1",
    name: "planner",
    updated_at: "2026-11-17T10:00:00+00:00",
    state: "ok",
    summary: "plan built",
    counts: {},
    items,
  };
}

it("groups held leads by reason, adds uncertain apply leads and owner companion items", () => {
  const queue = queueResponse(
    [
      queueRow({ verdict: "eligible" }),
      queueRow({ verdict: "uncertain", title: "Maybe Role" }),
    ],
    [
      queueRow({ review_reason: "role_unconfirmed" }),
      queueRow({ review_reason: "role_unconfirmed" }),
      queueRow({ review_reason: "non_us_location" }),
      queueRow({ review_reason: null }),
    ],
  );
  const groups = needsYou(queue, [
    companion([
      { label: "Acme cap", reason: "application cap", needs_owner: true },
      { label: "not mine", needs_owner: false },
      { label: "unflagged" },
    ]),
  ]);
  expect(groups.map((g) => [g.key, g.leads.length + g.items.length])).toEqual([
    ["held:role_unconfirmed", 2],
    ["held:non_us_location", 1],
    ["held:other", 1],
    ["uncertain", 1],
    ["companion:planner", 1],
  ]);
  // 4 held + 1 uncertain + 1 owner item; the eligible lead and unflagged items are not counted.
  expect(needsCount(groups)).toBe(6);
  expect(groups.every((g) => g.todo.length > 0)).toBe(true);
});

it("the page lists the groups with what to do, and keeps held leads when companions fail", async () => {
  vi.mocked(getQueue).mockResolvedValue(
    queueResponse([], [queueRow({ review_reason: "non_us_location", title: "Abroad Role" })]),
  );
  vi.mocked(getCompanions).mockRejectedValue(new Error("503"));
  render(<NeedsYouPage />);
  const group = await screen.findByRole("region", { name: "Held: outside the US" });
  expect(within(group).getByRole("link", { name: "Abroad Role" })).toBeDefined();
  expect(within(group).getByText(/^To do: /)).toBeDefined();
  expect(screen.getByRole("alert").textContent).toMatch(/companion status/);
});

it("says nothing is waiting when the lists are empty", async () => {
  vi.mocked(getQueue).mockResolvedValue(queueResponse([]));
  vi.mocked(getCompanions).mockResolvedValue({ companions: [] });
  render(<NeedsYouPage />);
  expect(await screen.findByText("Nothing is waiting on you.")).toBeDefined();
});
