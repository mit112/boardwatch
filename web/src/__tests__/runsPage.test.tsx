import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { RunFunnel, RunSummary } from "../api/types";
import { runFunnel, runSummary } from "../test/rows";

/*
 * The runs page against its own artifact. Every finding here is the same shape: the funnel
 * carries the answer and the page did not print it, so each test names a value that exists in
 * `reports/run_funnel.funnel_to_dict` and asserts the reader can see it.
 *
 * The client is mocked rather than the fixture server driven, because `src/fixtures/` may only be
 * reached through the dynamic import in `api/client.ts` and no test may import it.
 */
vi.mock("../api/client", () => ({
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getFunnel, getRuns } from "../api/client";
import { RunsPage } from "../routes/RunsPage";

async function renderRuns(funnel: RunFunnel, runs: RunSummary[] = [runSummary()]): Promise<void> {
  vi.mocked(getRuns).mockResolvedValue({ runs });
  vi.mocked(getFunnel).mockResolvedValue(funnel);
  render(<RunsPage />);
  // The funnel section only exists once both requests have settled.
  await screen.findByText(/^funnel · artifact/);
}

it("prints the run's fatal reason, not just that it was fatal", async () => {
  await renderRuns(
    runFunnel({
      fatal: "cohort incomplete: 10 shortlisted candidates unaccounted: 4288, 20797, …",
      errors: ["no leads emitted"],
    }),
  );

  // The reason is the whole diagnostic; "this run ended fatally" above an empty list is not.
  expect(
    screen.getByText(/cohort incomplete: 10 shortlisted candidates unaccounted/),
  ).toBeDefined();
  expect(screen.getByText("no leads emitted")).toBeDefined();
});
