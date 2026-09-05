import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { RunFunnel, RunSummary } from "../api/types";
import { funnelStage, runFunnel, runSummary } from "../test/rows";

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

function gateBand(): HTMLElement {
  return screen.getByRole("region", { name: "Final eligibility gate" });
}

/** The value beside a `<dt>`, which is how every metric pair on this page is built. */
function valueFor(scope: HTMLElement, label: string): string {
  return within(scope).getByText(label).nextElementSibling?.textContent ?? "";
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

it("renders the gate's five numbers and says in words when batches failed open", async () => {
  await renderRuns(
    runFunnel({
      gate: {
        instrumented: true,
        judged: 812,
        eligible: 466,
        ineligible: 291,
        uncertain: 55,
        failed_open_batches: 2,
      },
    }),
  );

  const band = gateBand();
  expect(valueFor(band, "judged")).toBe("812");
  expect(valueFor(band, "eligible")).toBe("466");
  expect(valueFor(band, "ineligible")).toBe("291");
  expect(valueFor(band, "uncertain")).toBe("55");
  expect(valueFor(band, "failed open")).toBe("2");
  // The one number that changes what the reader does, so it is said in words as well as weighted:
  // colour alone would carry the whole signal.
  expect(within(band).getByText(/2 batches failed open/)).toBeDefined();
});

it("says a missing gate was not instrumented, and never prints it as zero", async () => {
  await renderRuns(runFunnel({ gate: null }));

  const band = gateBand();
  expect(band.textContent).toContain("not instrumented");
  // `gate_to_dict` emits nulls, never zeros, for exactly this reason: nobody took the measurement.
  expect(band.textContent).not.toContain("0");
});

it("shows a stage's wall clock beside its name", async () => {
  await renderRuns(
    runFunnel({
      stages: [funnelStage({ name: "eligibility" })],
      stage_durations: [
        { name: "eligibility", seconds: 12.345 },
        { name: "lanes", seconds: 390.2 },
      ],
    }),
  );

  expect(screen.getByText("12.3 s")).toBeDefined();
});

it("shows a stage note's first sentence and collapses the rest", async () => {
  await renderRuns(
    runFunnel({
      stages: [
        funnelStage({
          name: "shortlist",
          note:
            "The stage D-016 exists for: the `hidden_below_cutoff` bucket. It is the remainder " +
            "of the others, so the stage balances by construction.",
        }),
      ],
    }),
  );

  const first = screen.getByText(/The stage D-016 exists for/);
  expect(first.closest("details")).toBeNull();
  // A backtick span is code, not a literal backtick in prose.
  expect(screen.getByText("hidden_below_cutoff").tagName).toBe("CODE");

  const rest = screen.getByText(/It is the remainder of the others/);
  const details = rest.closest("details");
  expect(details).not.toBeNull();
  expect(details?.open).toBe(false);
});

it("links a run's leads to that run's slice of the queue", async () => {
  await renderRuns(runFunnel(), [runSummary({ id: 5, leads: 8 })]);

  const link = screen.getByRole("link", { name: "8" });
  expect(link.getAttribute("href")).toBe("#/queue?run=5");
});

it("calls a run nothing has closed running, in the picker and in the summary", async () => {
  await renderRuns(runFunnel(), [runSummary({ id: 5, finished: null, status: "running" })]);

  expect(screen.getByRole("option", { name: /5 · started .* · running/ })).toBeDefined();
  expect(valueFor(screen.getByRole("region", { name: "Run summary" }), "status")).toBe("running");
});
