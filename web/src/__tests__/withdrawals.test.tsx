import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getWithdrawals: vi.fn() }));

import { getWithdrawals } from "../api/client";
import { Withdrawals } from "../components/Withdrawals";

it("keeps pulled-back and declined withdrawals apart and shows each reason", async () => {
  vi.mocked(getWithdrawals).mockResolvedValue({
    withdrawals: [
      {
        application_id: 1,
        kind: "after_applying",
        withdrawn_at: "2026-11-02T12:00:00+00:00",
        days_after_applying: 1.5,
        note: "role filled",
        job_id: 10,
        posting_id: 10,
        title: "SWE",
        company: "Acme",
      },
      {
        application_id: 2,
        kind: "before_applying",
        withdrawn_at: "2026-11-01T12:00:00+00:00",
        days_after_applying: null,
        note: null,
        job_id: 11,
        posting_id: 11,
        title: "Research study",
        company: "Acme",
      },
    ],
  });
  render(<Withdrawals />);
  const section = await screen.findByRole("region", { name: "Withdrawals" });
  expect(
    within(section).getByText(
      /2 withdrawn across 1 company: 1 pulled back after applying, 1 declined before sending\./,
    ),
  ).toBeDefined();
  expect(
    within(section).getByText(/withdrawn 1\.5 days after applying/),
  ).toBeDefined();
  expect(within(section).getByText("role filled")).toBeDefined();
  expect(within(section).getByText("No reason recorded.")).toBeDefined();
});

it("re-reads the withdrawals when the applied list reloads", async () => {
  vi.mocked(getWithdrawals).mockClear();
  vi.mocked(getWithdrawals).mockResolvedValue({ withdrawals: [] });
  const first: unknown[] = [];
  const { rerender } = render(<Withdrawals refresh={first} />);
  await vi.waitFor(() => expect(getWithdrawals).toHaveBeenCalledTimes(1));
  rerender(<Withdrawals refresh={[]} />);
  await vi.waitFor(() => expect(getWithdrawals).toHaveBeenCalledTimes(2));
});
