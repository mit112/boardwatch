import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getJdChanges: vi.fn(), getVersionDiff: vi.fn() }));

import { getJdChanges, getVersionDiff } from "../api/client";
import { JdChanges } from "../components/JdChanges";

const BASE = {
  posting_id: 1,
  job_id: 10,
  title: "SWE",
  company: "Acme",
  url: "https://boards.test/1",
  revisions: 2,
  latest_version_id: 30,
  latest_revised_at: "2026-11-07T12:00:00+00:00",
};

it("keeps the build list and the applied list apart, linking the posting and naming both versions", async () => {
  vi.mocked(getJdChanges).mockResolvedValue({
    limit: 1,
    built: {
      checked: 5,
      stale: 2,
      rows: [{ ...BASE, built_at: "2026-11-01T12:00:00+00:00", built_version_id: 11 }],
    },
    applied: {
      checked: 4,
      changed: 1,
      excluded_imports: 61,
      no_posting_version: 3,
      rows: [
        {
          ...BASE,
          posting_id: 2,
          title: "Backend",
          url: "javascript:alert(1)",
          revisions: 1,
          application_id: 7,
          status: "applied",
          submitted_at: "2026-11-06T12:00:00+00:00",
          sent_version_id: null,
        },
      ],
    },
  });
  render(<JdChanges />);
  const section = await screen.findByRole("region", { name: "JD changes" });

  const built = within(section).getByRole("list", { name: "Changed after building" });
  expect(within(built).getAllByRole("listitem")).toHaveLength(1);
  const link = within(built).getByRole("link", { name: "Acme — SWE" });
  expect(link.getAttribute("href")).toBe("https://boards.test/1");
  expect(within(built).getByText(/2 revisions after the version it was built from/)).toBeDefined();
  expect(within(built).getByRole("button", { name: "Compare version 11 with 30" })).toBeDefined();
  expect(
    within(section).getByText(/2 of 5 postings with a tailored résumé were revised/),
  ).toBeDefined();
  expect(within(section).getByText(/Showing the 1 most recently changed\./)).toBeDefined();

  const applied = within(section).getByRole("list", { name: "Changed after applying" });
  expect(within(applied).getAllByRole("listitem")).toHaveLength(1);
  // An unsafe URL is inert text, never a link.
  expect(within(applied).queryByRole("link")).toBeNull();
  expect(within(applied).getByText("Acme — Backend")).toBeDefined();
  expect(within(applied).getByText(/1 revision after applying/)).toBeDefined();
  // No version was live when it was sent: nothing to compare, so no button.
  expect(within(applied).queryByRole("button")).toBeNull();
  expect(within(applied).getByText(/no version was captured when it was sent/)).toBeDefined();
  expect(
    within(section).getByText(
      /1 of 4 dated applications are on a posting revised after they were sent/,
    ),
  ).toBeDefined();
  expect(
    within(section).getByText(
      /61 imported with no recorded applied date were not compared, and 3 name no posting version/,
    ),
  ).toBeDefined();
});

it("says so when nothing changed, with the counts as measurements", async () => {
  vi.mocked(getJdChanges).mockResolvedValue({
    limit: 50,
    built: { checked: 3, stale: 0, rows: [] },
    applied: { checked: 2, changed: 0, excluded_imports: 1, no_posting_version: 0, rows: [] },
  });
  render(<JdChanges />);
  const section = await screen.findByRole("region", { name: "JD changes" });
  expect(within(section).getByText(/0 of 3 postings with a tailored résumé/)).toBeDefined();
  expect(within(section).getByText(/0 of 2 dated applications/)).toBeDefined();
  expect(within(section).getByText(/1 imported with no recorded applied date was not compared\./)).toBeDefined();
  expect(within(section).queryAllByRole("list")).toHaveLength(0);
});

it("reports a failed load instead of vanishing", async () => {
  vi.mocked(getJdChanges).mockRejectedValue(new Error("down"));
  render(<JdChanges />);
  expect(await screen.findByText("JD changes could not be loaded.")).toBeDefined();
});

const ONE_BUILT = {
  limit: 50,
  built: {
    checked: 1,
    stale: 1,
    rows: [{ ...BASE, built_at: "2026-11-01T12:00:00+00:00", built_version_id: 11 }],
  },
  applied: { checked: 0, changed: 0, excluded_imports: 0, no_posting_version: 0, rows: [] },
};

it("opens the version diff under the row, with a sign on every added and removed line", async () => {
  vi.mocked(getJdChanges).mockResolvedValue(ONE_BUILT);
  vi.mocked(getVersionDiff).mockResolvedValue({
    posting_id: 1,
    from: 11,
    to: 30,
    lines: [
      { kind: "hunk", text: "@@ -1,3 +1,3 @@" },
      { kind: "same", text: "Requirements" },
      { kind: "del", text: "3+ years of Python" },
      { kind: "add", text: "5+ years of Python" },
    ],
  });
  render(<JdChanges />);
  const button = await screen.findByRole("button", { name: "Compare version 11 with 30" });
  expect(button.getAttribute("aria-expanded")).toBe("false");
  expect(getVersionDiff).not.toHaveBeenCalled();

  fireEvent.click(button);
  const list = await screen.findByRole("list", { name: "Changes from version 11 to 30" });
  expect(getVersionDiff).toHaveBeenCalledWith(1, 11, 30);
  expect(button.getAttribute("aria-expanded")).toBe("true");
  const items = within(list).getAllByRole("listitem");
  // The sign is visible text on each changed line, not colour alone.
  expect(items.map((i) => i.textContent)).toEqual([
    "@@ -1,3 +1,3 @@",
    "  Requirements",
    "− removed: 3+ years of Python",
    "+ added: 5+ years of Python",
  ]);

  // Closing hides it; opening again does not fetch twice.
  fireEvent.click(button);
  expect(screen.queryByRole("list", { name: /Changes from version/ })).toBeNull();
  fireEvent.click(button);
  await screen.findByRole("list", { name: "Changes from version 11 to 30" });
  expect(getVersionDiff).toHaveBeenCalledTimes(1);
});

it("says so when the two versions have no differing line", async () => {
  vi.mocked(getJdChanges).mockResolvedValue(ONE_BUILT);
  vi.mocked(getVersionDiff).mockResolvedValue({ posting_id: 1, from: 11, to: 30, lines: [] });
  render(<JdChanges />);
  fireEvent.click(await screen.findByRole("button", { name: "Compare version 11 with 30" }));
  expect(await screen.findByText("No line differs between the two versions.")).toBeDefined();
});

it("says so when the diff fails to load, and retries on the next open", async () => {
  vi.mocked(getJdChanges).mockResolvedValue(ONE_BUILT);
  vi.mocked(getVersionDiff).mockRejectedValue(new Error("down"));
  render(<JdChanges />);
  const button = await screen.findByRole("button", { name: "Compare version 11 with 30" });
  fireEvent.click(button);
  await waitFor(() => {
    expect(screen.getByText("The diff could not be loaded.")).toBeDefined();
  });
  vi.mocked(getVersionDiff).mockResolvedValue({ posting_id: 1, from: 11, to: 30, lines: [] });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(await screen.findByText("No line differs between the two versions.")).toBeDefined();
});

it("drops an open diff when a refresh moves the row to a newer version", async () => {
  vi.mocked(getVersionDiff).mockReset();
  vi.mocked(getJdChanges).mockResolvedValue(ONE_BUILT);
  vi.mocked(getVersionDiff).mockResolvedValue({
    posting_id: 1,
    from: 11,
    to: 30,
    lines: [{ kind: "add", text: "old pair" }],
  });
  const { rerender } = render(<JdChanges refresh={1} />);
  fireEvent.click(await screen.findByRole("button", { name: "Compare version 11 with 30" }));
  expect(await screen.findByText("old pair")).toBeDefined();

  const moved = structuredClone(ONE_BUILT);
  const first = moved.built.rows[0];
  if (first === undefined) throw new Error("fixture has a built row");
  first.latest_version_id = 31;
  vi.mocked(getJdChanges).mockResolvedValue(moved);
  rerender(<JdChanges refresh={2} />);
  const next = await screen.findByRole("button", { name: "Compare version 11 with 31" });
  expect(next.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText("old pair")).toBeNull();
});
