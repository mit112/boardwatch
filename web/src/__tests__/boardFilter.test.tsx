import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

/* The job-board filter: narrows BOTH lanes by the row's `provider`, and its options count what is on the page. */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
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
  window.sessionStorage.setItem("boardwatch.review-open", "true");
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
    await screen.findByRole("grid", { name: "Queue" });

    const select = screen.getByLabelText("Job board");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "all boards",
      "linkedin (1)",
      "workday (2)",
    ]);

    fireEvent.change(select, { target: { value: "workday" } });
    expect(titles("Queue")).toEqual(["APPLY-WD"]);
    expect(titles("Review")).toEqual(["REVIEW-WD"]);

    fireEvent.change(select, { target: { value: "" } });
    expect(titles("Queue")).toEqual(["APPLY-WD", "APPLY-LI"]);
  });

  it("narrows to a board when its badge is clicked, and clears on a second click", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    const queue = within(screen.getByRole("grid", { name: "Queue" }));
    fireEvent.click(queue.getByText("linkedin"));
    expect(titles("Queue")).toEqual(["APPLY-LI"]);
    expect((screen.getByLabelText<HTMLSelectElement>("Job board")).value).toBe("linkedin");

    fireEvent.click(within(screen.getByRole("grid", { name: "Queue" })).getByText("linkedin"));
    expect(titles("Queue")).toEqual(["APPLY-WD", "APPLY-LI"]);
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
    await screen.findByRole("grid", { name: "Queue" });
    expect(titles("Queue")).toEqual(["APPLY-FULL", "APPLY-THIN", "APPLY-GONE"]);

    fireEvent.click(screen.getByLabelText("Hide thin JD"));
    expect(titles("Queue")).toEqual(["APPLY-FULL", "APPLY-GONE"]);
    fireEvent.click(screen.getByLabelText("Hide unverifiable"));
    expect(titles("Queue")).toEqual(["APPLY-FULL"]);
    fireEvent.click(screen.getByLabelText("Hide thin JD"));
    fireEvent.click(screen.getByLabelText("Hide unverifiable"));

    fireEvent.change(screen.getByLabelText("Work mode"), { target: { value: "onsite" } });
    expect(titles("Queue")).toEqual(["APPLY-THIN"]);
    fireEvent.change(screen.getByLabelText("Work mode"), { target: { value: "(not stated)" } });
    expect(titles("Queue")).toEqual(["APPLY-GONE"]);
  });
});
