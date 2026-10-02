import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RejectedResponse, RejectedRow, RequirementView } from "../api/types";
import { queueRow } from "../test/rows";

/*
 * The filtered-out page (`#/rejected`): the list behind the queue's `ineligible` cell, named for
 * what it is — our rules' call, not an employer's answer. What a reader relies on: the independent
 * review's disagreements can be shown alone, "Why filtered out" names the failing rule first with
 * its quote, a flag is recorded and moves nothing, and "record application anyway" is the queue's
 * own mark.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
  getApplied: vi.fn(),
  getRejected: vi.fn(),
  disputeRejection: vi.fn(),
  undisputeRejection: vi.fn(),
  markApplied: vi.fn(),
  unapply: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import {
  disputeRejection,
  getDetail,
  getRejected,
  markApplied,
  unapply,
  undisputeRejection,
} from "../api/client";
import { App } from "../App";

let counter = 0;
function rejectedRow(overrides: Partial<RejectedRow> = {}): RejectedRow {
  counter += 1;
  return {
    posting_id: 9000 + counter,
    job_id: 8000 + counter,
    title: `Software Engineer ${String(counter)}`,
    company: `Acme ${String(counter)}`,
    provider: "greenhouse",
    location: "Austin, TX",
    remote_policy: null,
    posted_days: 3,
    first_seen: "2026-09-30T12:00:00+00:00",
    apply_url: "https://careers.acme.test/apply",
    delivered_run_id: 528,
    judge_verdict: null,
    pdf_available: true,
    disputed: false,
    ...overrides,
  };
}

function response(rows: RejectedRow[]): RejectedResponse {
  return {
    rows,
    counts: {
      total: rows.length,
      gate_eligible: rows.filter((row) => row.judge_verdict === "eligible").length,
      disputed: rows.filter((row) => row.disputed).length,
    },
  };
}

function requirement(overrides: Partial<RequirementView>): RequirementView {
  return {
    requirement: "work authorization",
    covered: false,
    rule: "work_auth:us_authorization_required",
    disposition: "unmet",
    profile_field: "facts.work_auth",
    quote: null,
    rationale: null,
    ...overrides,
  };
}

function bodyRows(): HTMLElement[] {
  return within(screen.getByRole("table"))
    .getAllByRole("row")
    .filter((row) => within(row).queryAllByRole("columnheader").length === 0);
}

async function settle(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function renderRejected(rows: RejectedRow[]): Promise<void> {
  vi.mocked(getRejected).mockResolvedValue(response(rows));
  render(<App />);
  await settle();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/#/rejected");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the filtered-out page", () => {
  it("is a tab of its own and shows only the gate's disagreements on request", async () => {
    await renderRejected([
      rejectedRow({ company: "Globex", judge_verdict: "eligible" }),
      rejectedRow({ company: "Initech" }),
    ]);
    expect(
      screen.getByRole("button", { name: "Filtered out" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(bodyRows()).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /^independent review found no blocker 1/ }));
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText("Globex")).toBeTruthy();
  });

  it("names the failing rule first, with its quote, and leaves coverage terms out", async () => {
    const row = rejectedRow({ company: "Globex", title: "Backend Engineer" });
    await renderRejected([row]);
    vi.mocked(getDetail).mockResolvedValue({
      row: queueRow({ posting_id: row.posting_id }),
      jd_body: "Applicants must be authorized to work in the United States.",
      requirements: [
        requirement({ rule: "degree:bachelors", disposition: "met", quote: "a degree" }),
        requirement({ quote: "must be authorized to work in the United States" }),
        requirement({ rule: null, requirement: "kubernetes", disposition: null }),
      ],
      board_target: null,
    });

    fireEvent.click(screen.getByRole("button", { name: "Why filtered out: Globex — Backend Engineer" }));
    await settle();

    expect(vi.mocked(getDetail)).toHaveBeenCalledWith(row.posting_id);
    const why = screen.getByRole("list", { name: "Why Globex — Backend Engineer was filtered out" });
    const items = within(why).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0] as HTMLElement).getByText("not met")).toBeTruthy();
    expect(
      within(items[0] as HTMLElement).getByText("“must be authorized to work in the United States”"),
    ).toBeTruthy();
    expect(within(why).queryByText("kubernetes")).toBeNull();
  });

  it("records a flag through its own route and offers to withdraw it", async () => {
    const row = rejectedRow({ company: "Globex", title: "Backend Engineer" });
    await renderRejected([row]);
    vi.mocked(disputeRejection).mockResolvedValue({ outcome: "disputed" });
    vi.mocked(getRejected).mockResolvedValue(response([{ ...row, disputed: true }]));

    fireEvent.click(screen.getByRole("button", { name: "Flag as wrongly filtered: Globex — Backend Engineer" }));
    await settle();

    expect(vi.mocked(disputeRejection)).toHaveBeenCalledWith(row.posting_id);
    expect(screen.getByText(/^Flagged the call on Globex/)).toBeTruthy();
    expect(within(screen.getByRole("table")).getByText("flagged as wrong")).toBeTruthy();

    vi.mocked(undisputeRejection).mockResolvedValue({ outcome: "undisputed" });
    fireEvent.click(
      screen.getByRole("button", { name: "Withdraw flag: Globex — Backend Engineer" }),
    );
    await settle();
    expect(vi.mocked(undisputeRejection)).toHaveBeenCalledWith(row.posting_id);
  });

  it("applies anyway through the queue's own mark, with its own undo", async () => {
    const row = rejectedRow({ company: "Globex", title: "Backend Engineer" });
    await renderRejected([row]);
    vi.mocked(markApplied).mockResolvedValue({ outcome: "created", job_id: row.job_id });
    vi.mocked(unapply).mockResolvedValue({ outcome: "transitioned", job_id: row.job_id });

    fireEvent.click(
      screen.getByRole("button", { name: "Record application anyway: Globex — Backend Engineer" }),
    );
    await settle();
    expect(vi.mocked(markApplied)).toHaveBeenCalledWith(row.posting_id);

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await settle();
    expect(vi.mocked(unapply)).toHaveBeenCalledWith(row.posting_id);
  });
});
