import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BoardHealthResponse, BoardHealthRow } from "../api/types";

/*
 * T305: the board-health section prints what the server decided, with the action in words, and
 * renders a status it has never heard of as "unknown status" instead of dropping the row.
 */

vi.mock("../api/client", () => ({ getBoardHealth: vi.fn() }));

import { getBoardHealth } from "../api/client";
import { BoardHealth } from "../components/BoardHealth";

function row(over: Partial<BoardHealthRow> = {}): BoardHealthRow {
  return {
    company_id: 1,
    name: "Acme",
    provider: "greenhouse",
    slug: "acme",
    issue: "dead",
    label: "dead",
    action: "remove the board or fix its slug",
    last_health: "dead",
    scan_status: "failed",
    error: "404",
    reported_total: null,
    enumerated: null,
    missing: null,
    scanned_at: "2026-11-17T04:10:00+00:00",
    ...over,
  };
}

function response(over: Partial<BoardHealthResponse> = {}): BoardHealthResponse {
  return {
    watched_boards: 3,
    providers: [
      {
        provider: "greenhouse",
        boards: 2,
        healthy: 1,
        dead: 1,
        unreachable: 0,
        error: 0,
        mismatch: 0,
        partial: 0,
        empty: 0,
        unknown: 0,
        gated_boards: 0,
        gated_postings: 0,
        seconds_avg: 2.5,
        seconds_max: 3,
      },
      {
        provider: "workday",
        boards: 1,
        healthy: 0,
        dead: 0,
        unreachable: 0,
        error: 0,
        mismatch: 1,
        partial: 0,
        empty: 0,
        unknown: 0,
        gated_boards: 1,
        gated_postings: 30,
        seconds_avg: null,
        seconds_max: null,
      },
    ],
    boards: [row()],
    slowest: [
      {
        company_id: 9,
        name: "Slow Co",
        provider: "workday",
        seconds: 30,
        scan_status: "complete",
        scanned_at: "2026-11-17T04:10:00+00:00",
      },
    ],
    ...over,
  };
}

describe("BoardHealth", () => {
  it("prints each problem board with the action its status calls for", async () => {
    vi.mocked(getBoardHealth).mockResolvedValue(
      response({
        boards: [
          row(),
          row({
            company_id: 2,
            name: "Short Board",
            provider: "workday",
            issue: "mismatch",
            label: "count mismatch",
            action: "postings may be missing; re-scan",
            last_health: "ok",
            scan_status: "partial",
            error: null,
            reported_total: 100,
            enumerated: 60,
            missing: 40,
          }),
        ],
      }),
    );
    render(<BoardHealth />);

    const table = await screen.findByRole("table", { name: "Boards that need attention" });
    const dead = within(table).getByText("Acme").closest("tr");
    expect(dead).not.toBeNull();
    expect(within(dead as HTMLElement).getByText("dead")).toBeTruthy();
    expect(within(dead as HTMLElement).getByText("remove the board or fix its slug")).toBeTruthy();
    const short = within(table).getByText("Short Board").closest("tr") as HTMLElement;
    expect(within(short).getByText("postings may be missing; re-scan")).toBeTruthy();
    expect(within(short).getByText(/board says 100, scan counted 60/)).toBeTruthy();
  });

  it("renders a status it does not know as 'unknown status', never dropping the row", async () => {
    vi.mocked(getBoardHealth).mockResolvedValue(
      response({
        boards: [row({ company_id: 5, name: "Odd Co", issue: "weird", label: "weird", action: "" })],
      }),
    );
    render(<BoardHealth />);

    const table = await screen.findByRole("table", { name: "Boards that need attention" });
    const odd = within(table).getByText("Odd Co").closest("tr") as HTMLElement;
    expect(within(odd).getByText("unknown status")).toBeTruthy();
    expect(within(odd).getByText(/not recognised; check the board by hand/)).toBeTruthy();
    expect(within(odd).queryByText("weird")).toBeNull();
  });

  it("shows the provider rollup, the gate as a count not a failure, and the slowest boards", async () => {
    vi.mocked(getBoardHealth).mockResolvedValue(response());
    render(<BoardHealth />);

    const rollup = await screen.findByRole("table", { name: "Board health by provider" });
    const workday = within(rollup).getByText("workday").closest("tr") as HTMLElement;
    expect(within(workday).getByText("30 on 1")).toBeTruthy();
    const greenhouse = within(rollup).getByText("greenhouse").closest("tr") as HTMLElement;
    expect(within(greenhouse).getByText("2.5 s")).toBeTruthy();
    expect(screen.getByText("Slow Co")).toBeTruthy();
    expect(screen.getByText("30.0 s")).toBeTruthy();
  });

  it("says so when nothing needs attention", async () => {
    vi.mocked(getBoardHealth).mockResolvedValue(response({ boards: [] }));
    render(<BoardHealth />);
    expect(await screen.findByText("No watched board needs attention.")).toBeTruthy();
  });

  it("caps the list and reveals every board on request", async () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      row({ company_id: i + 1, name: `Board ${String(i + 1)}` }),
    );
    vi.mocked(getBoardHealth).mockResolvedValue(response({ boards: many }));
    render(<BoardHealth />);

    const table = await screen.findByRole("table", { name: "Boards that need attention" });
    expect(within(table).getAllByRole("row")).toHaveLength(26); // header + 25
    fireEvent.click(screen.getByRole("button", { name: "Show all 30 boards" }));
    expect(within(table).getAllByRole("row")).toHaveLength(31);
  });

  it("renders nothing when the endpoint fails", async () => {
    vi.mocked(getBoardHealth).mockRejectedValue(new Error("down"));
    const { container } = render(<BoardHealth />);
    await Promise.resolve();
    await Promise.resolve();
    expect(container.textContent).toBe("");
  });
});
