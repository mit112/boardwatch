import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/* The job-board filter: narrows BOTH lanes by the row's `provider`, and its options count what is on the page. */

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

import { getQueue } from "../api/client";
import { App } from "../App";

function titles(grid: string): string[] {
  return within(screen.getByRole("grid", { name: grid }))
    .getAllByRole("row")
    .filter((row) => row.hasAttribute("data-row-id"))
    .map((row) => within(row).getByText(/^(APPLY|REVIEW)/).textContent ?? "");
}

beforeEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
  // Both lists on one page: the board filter has to reach both, and says so.
  window.sessionStorage.setItem("boardwatch.queue.lens", "all");
  vi.mocked(getQueue).mockResolvedValue(
    queueResponse(
      [
        queueRow({ title: "APPLY-WD", provider: "workday" }),
        queueRow({ title: "APPLY-LI", provider: "linkedin" }),
      ],
      [queueRow({ title: "REVIEW-WD", provider: "workday", review_reason: "unevaluated" })],
    ),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the job board filter", () => {
  it("lists each board with its count and narrows both lanes", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });

    const select = screen.getByLabelText("Job board");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All boards",
      "linkedin (1)",
      "workday (2)",
    ]);

    fireEvent.change(select, { target: { value: "workday" } });
    expect(titles("Jobs to explore")).toEqual(["APPLY-WD"]);
    expect(titles("Needs review")).toEqual(["REVIEW-WD"]);

    fireEvent.change(select, { target: { value: "" } });
    expect(titles("Jobs to explore")).toEqual(["APPLY-WD", "APPLY-LI"]);
  });

  it("hides thin-JD and unverifiable rows, and filters by work mode", async () => {
    vi.mocked(getQueue).mockResolvedValue(
      queueResponse(
        [
          queueRow({ title: "APPLY-FULL", remote_policy: "remote" }),
          queueRow({ title: "APPLY-THIN", thin_jd: true, remote_policy: "onsite" }),
          queueRow({ title: "APPLY-GONE", status: "unverifiable", remote_policy: null }),
        ],
        [],
      ),
    );
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    expect(titles("Jobs to explore")).toEqual(["APPLY-FULL", "APPLY-THIN", "APPLY-GONE"]);

    fireEvent.click(screen.getByLabelText("Hide very short descriptions"));
    expect(titles("Jobs to explore")).toEqual(["APPLY-FULL", "APPLY-GONE"]);
    fireEvent.click(screen.getByLabelText("Hide postings I can’t verify are open"));
    expect(titles("Jobs to explore")).toEqual(["APPLY-FULL"]);
    fireEvent.click(screen.getByLabelText("Hide very short descriptions"));
    fireEvent.click(screen.getByLabelText("Hide postings I can’t verify are open"));

    fireEvent.change(screen.getByLabelText("Work arrangement"), { target: { value: "onsite" } });
    expect(titles("Jobs to explore")).toEqual(["APPLY-THIN"]);
    fireEvent.change(screen.getByLabelText("Work arrangement"), { target: { value: "(not stated)" } });
    expect(titles("Jobs to explore")).toEqual(["APPLY-GONE"]);
  });
});
