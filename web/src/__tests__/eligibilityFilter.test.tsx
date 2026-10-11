import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queueResponse, queueRow } from "../test/rows";

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getApplied: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
}));

import { getQueue } from "../api/client";
import { App } from "../App";

beforeEach(() => {
  vi.mocked(getQueue).mockResolvedValue(
    queueResponse(
      [
        queueRow({ title: "BOTH-CLEAR", judge_verdict: "eligible" }),
        queueRow({ title: "RULES-ONLY", judge_verdict: "uncertain" }),
        queueRow({ title: "UNJUDGED", judge_verdict: null }),
        queueRow({ title: "MISSING-JUDGE" }),
        queueRow({ title: "MISSING-RULES", verdict: null, judge_verdict: "eligible" }),
        queueRow({ title: "SECOND-CLEAR", company: "Another Company", judge_verdict: "eligible" }),
        queueRow({ title: "NO-RESUME", judge_verdict: "eligible", pdf_available: false }),
        queueRow({ title: "UNVERIFIABLE", judge_verdict: "eligible", status: "unverifiable" }),
        queueRow({ title: "OFF-TARGET", judge_verdict: "eligible", off_target: true }),
        queueRow({ title: "THIN-JD", judge_verdict: "eligible", thin_jd: true }),
        queueRow({ title: "TOO-SENIOR", judge_verdict: "eligible", judge_seniority_above_band: true }),
        queueRow({ title: "NO-LINK", judge_verdict: "eligible", apply_url: null }),
        queueRow({ title: "UNSAFE-LINK", judge_verdict: "eligible", apply_url: "javascript:alert(1)" }),
        queueRow({ title: "ALREADY-APPLIED", judge_verdict: "eligible", applied_identical_jd: [{ posting_id: 99, title: "Earlier job", location: "Remote", applied_at: null }] }),
      ],
      [
        queueRow({ title: "REVIEW-CLEAR", judge_verdict: "eligible", review_reason: "non_us_location" }),
        queueRow({ title: "JUDGE-ONLY", verdict: "uncertain", judge_verdict: "eligible", review_reason: "eligibility_unconfirmed" }),
        queueRow({ title: "NEITHER-CLEAR", verdict: "uncertain", judge_verdict: "uncertain", review_reason: "eligibility_unconfirmed" }),
      ],
    ),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the apply-first filter", () => {
  it("requires both affirmative verdicts and no known warnings, and composes with search", async () => {
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    fireEvent.click(screen.getByRole("button", { name: /^All jobs/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "Eligibility" }), {
      target: { value: "eligible" },
    });

    expect(screen.getByText("BOTH-CLEAR")).toBeTruthy();
    expect(screen.getByText("SECOND-CLEAR")).toBeTruthy();
    for (const title of [
      "RULES-ONLY", "UNJUDGED", "MISSING-JUDGE", "MISSING-RULES", "JUDGE-ONLY", "NEITHER-CLEAR",
      "REVIEW-CLEAR", "NO-RESUME", "UNVERIFIABLE", "OFF-TARGET", "THIN-JD", "TOO-SENIOR",
      "NO-LINK", "UNSAFE-LINK", "ALREADY-APPLIED",
    ]) {
      expect(screen.queryByText(title)).toBeNull();
    }
    expect(screen.getByRole("button", { name: "All jobs 2" })).toBeTruthy();
    expect(screen.getByText("Filtering by apply first (both checks eligible, résumé ready, no known flags).")).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), {
      target: { value: "Another Company" },
    });
    expect(screen.queryByText("BOTH-CLEAR")).toBeNull();
    expect(screen.getByText("SECOND-CLEAR")).toBeTruthy();
  });

  it("remembers the choice after remounting and resets it with the other filters", async () => {
    const view = render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });
    fireEvent.change(screen.getByRole("combobox", { name: "Eligibility" }), {
      target: { value: "eligible" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    fireEvent.change(screen.getByRole("textbox", { name: "View name" }), {
      target: { value: "Apply first" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    view.unmount();
    render(<App />);
    await screen.findByRole("grid", { name: "Jobs to explore" });

    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Eligibility" }).value).toBe("eligible");
    expect(screen.queryByText("RULES-ONLY")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Eligibility" }).value).toBe("");
    expect(screen.getByText("RULES-ONLY")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "Saved view" }), {
      target: { value: "Apply first" },
    });
    expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "Eligibility" }).value).toBe("eligible");
    expect(screen.queryByText("RULES-ONLY")).toBeNull();
  });
});
