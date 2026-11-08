import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/* The job-board filter: narrows BOTH lanes by the application URL, independently of discovery source, and its options count what is on the page. */

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
        queueRow({ title: "APPLY-WD", provider: "linkedin", apply_url: "https://example.wd5.myworkdayjobs.com/jobs/1" }),
        queueRow({ title: "APPLY-LI", provider: "indeed", apply_url: "https://www.linkedin.com/jobs/view/2" }),
      ],
      [queueRow({ title: "REVIEW-WD", provider: "jobapps", apply_url: "https://other.wd1.myworkdayjobs.com/jobs/3", review_reason: "unevaluated" })],
    ),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the job board filter", () => {
  it("lists each board with its count and narrows both lanes", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "No check held these back" });

    const select = screen.getByLabelText("Application site");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All sites",
      "linkedin (1)",
      "workday (2)",
    ]);

    fireEvent.change(select, { target: { value: "workday" } });
    expect(titles("No check held these back")).toEqual(["APPLY-WD"]);
    expect(titles("Needs review")).toEqual(["REVIEW-WD"]);

    fireEvent.change(select, { target: { value: "" } });
    expect(titles("No check held these back")).toEqual(["APPLY-WD", "APPLY-LI"]);
  });

  it("counts and filters manual jobs by destination too", async () => {
    const response = queueResponse([queueRow({ title: "APPLY-WD", provider: "linkedin", apply_url: "https://example.myworkdayjobs.com/1" })]);
    response.manual = [queueRow({ title: "APPLY-MANUAL", provider: "indeed", apply_route: "hand", apply_url: "https://other.myworkdayjobs.com/2" })];
    vi.mocked(getQueue).mockResolvedValue(response);
    render(<App />);
    await screen.findByRole("grid", { name: "No check held these back" });
    const select = screen.getByLabelText("Application site");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["All sites", "workday (2)"]);
    fireEvent.change(select, { target: { value: "workday" } });
    expect(screen.getByText("APPLY-MANUAL")).toBeTruthy();
    expect(screen.getAllByText("workday")).toHaveLength(2);
    expect(screen.queryByText("linkedin")).toBeNull();
    expect(screen.queryByText("indeed")).toBeNull();
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
    await screen.findByRole("grid", { name: "No check held these back" });
    expect(titles("No check held these back")).toEqual(["APPLY-FULL", "APPLY-THIN", "APPLY-GONE"]);

    fireEvent.click(screen.getByLabelText("Hide very short descriptions"));
    expect(titles("No check held these back")).toEqual(["APPLY-FULL", "APPLY-GONE"]);
    fireEvent.click(screen.getByLabelText("Hide postings I can’t verify are open"));
    expect(titles("No check held these back")).toEqual(["APPLY-FULL"]);
    fireEvent.click(screen.getByLabelText("Hide very short descriptions"));
    fireEvent.click(screen.getByLabelText("Hide postings I can’t verify are open"));

    fireEvent.change(screen.getByLabelText("Work arrangement"), { target: { value: "onsite" } });
    expect(titles("No check held these back")).toEqual(["APPLY-THIN"]);
    fireEvent.change(screen.getByLabelText("Work arrangement"), { target: { value: "(not stated)" } });
    expect(titles("No check held these back")).toEqual(["APPLY-GONE"]);
  });
});
