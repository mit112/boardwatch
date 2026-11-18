import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getJdChanges: vi.fn() }));

import { getJdChanges } from "../api/client";
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
  expect(within(built).getByText(/2 revisions after the build/)).toBeDefined();
  expect(within(built).getByText(/compare version 11 with 30/)).toBeDefined();
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
  expect(within(applied).getByText(/compare version \(none captured\) with 30/)).toBeDefined();
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
