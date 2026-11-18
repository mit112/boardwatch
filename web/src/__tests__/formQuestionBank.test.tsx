import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { FormQuestionBank } from "../api/types";

vi.mock("../api/client", () => ({ getFormQuestionBank: vi.fn() }));

import { getFormQuestionBank } from "../api/client";
import { FormQuestionBankPanel } from "../components/FormQuestionBank";

function bank(over: Partial<FormQuestionBank> = {}): FormQuestionBank {
  return {
    forms: {
      stored: 9,
      eligible: 4,
      abstain: 3,
      ineligible: 0,
      unevaluated: 0,
      closed: 1,
      superseded: 1,
    },
    answers_readable: true,
    distinct: 2,
    unanswered: 1,
    standard_fields: ["first name", "email"],
    questions: [
      { question: "Desired salary?", count: 3, answered: false },
      { question: "Are you authorized?", count: 4, answered: true },
    ],
    ...over,
  };
}

it("lists each question with its count and answered state, in the order served", async () => {
  vi.mocked(getFormQuestionBank).mockResolvedValue(bank());
  render(<FormQuestionBankPanel />);
  const section = await screen.findByRole("region", { name: "Form questions" });
  const rows = within(section)
    .getAllByRole("listitem")
    .map((r) => r.textContent);
  expect(rows).toEqual(["Unanswered3Desired salary?", "Answered4Are you authorized?"]);
  expect(section.textContent).toMatch(/2 questions across 4 open eligible forms, 1 unanswered\./);
  // Abstaining forms are named apart, not folded into the 4.
  expect(section.textContent).toMatch(/Abstaining forms \(3\) are not counted/);
  expect(within(section).queryByRole("alert")).toBeNull();
});

it("says so, and marks no question, when the answers file could not be read", async () => {
  vi.mocked(getFormQuestionBank).mockResolvedValue(
    bank({
      answers_readable: false,
      unanswered: null,
      questions: [{ question: "Desired salary?", count: 3, answered: null }],
    }),
  );
  render(<FormQuestionBankPanel />);
  const section = await screen.findByRole("region", { name: "Form questions" });
  expect(within(section).getByRole("alert").textContent).toMatch(/could not be read/);
  expect(within(section).getByText("Unknown")).toBeDefined();
  expect(section.textContent).toMatch(/2 questions across 4 open eligible forms\. Abstaining/);
});

it("reports a failed load instead of vanishing", async () => {
  vi.mocked(getFormQuestionBank).mockRejectedValue(new Error("503"));
  render(<FormQuestionBankPanel />);
  expect(await screen.findByText("Form questions could not be loaded.")).toBeDefined();
});
