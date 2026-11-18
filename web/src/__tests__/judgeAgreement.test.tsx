import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getJudgeAgreement: vi.fn() }));

import { getJudgeAgreement } from "../api/client";
import { JudgeAgreementPanel } from "../components/JudgeAgreementPanel";

it("draws the newest run's matrix per lane and the current splits", async () => {
  vi.mocked(getJudgeAgreement).mockResolvedValue({
    lanes: {
      final_gate: [
        {
          run_id: 2853,
          total: 6,
          agree: 3,
          cells: [
            { deterministic: "eligible", llm: "eligible", count: 2 },
            { deterministic: "uncertain", llm: "uncertain", count: 1 },
            { deterministic: "uncertain", llm: "eligible", count: 2 },
            { deterministic: "none", llm: "ineligible", count: 1 },
          ],
        },
        { run_id: 2851, total: 4, agree: 1, cells: [] },
      ],
    },
    final_gate_splits: 1,
    split_rules: [
      { rule_id: "experience_years:scoped_years_preferred", count: 1 },
    ],
    splits: [
      {
        posting_id: 7,
        title: "SWE",
        company: "Acme",
        deterministic: "uncertain",
        llm: "eligible",
      },
    ],
  });
  render(<JudgeAgreementPanel />);
  const panel = await screen.findByRole("region", {
    name: "Engine and judge agreement",
  });
  expect(
    within(panel).getByText(/agreed on 3 of 6\. Last 2 runs: 50% · 25%/),
  ).toBeDefined();
  const matrix = within(panel).getByRole("table", {
    name: "Run 2853 agreement",
  });
  expect(
    within(matrix)
      .getAllByRole("row")
      .map((r) => r.textContent),
  ).toEqual([
    "Engine \\ judgeeligibleuncertainineligible",
    "eligible200",
    "uncertain210",
    "no engine verdict001",
  ]);
  expect(
    within(panel).getByRole("link", { name: "SWE" }).getAttribute("href"),
  ).toBe("#/queue?lead=7");
});

it("draws nothing when no LLM verdicts exist", async () => {
  vi.mocked(getJudgeAgreement).mockResolvedValue({
    lanes: {},
    final_gate_splits: 0,
    split_rules: [],
    splits: [],
  });
  const { container } = render(<JudgeAgreementPanel />);
  await Promise.resolve();
  expect(container.textContent).toBe("");
});
