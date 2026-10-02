import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

/*
 * Recovery. Run 529 was a résumé re-render: the store has a row for it and no funnel artifact, and
 * the page used to open on it and print "404 from /api/runs/529" as the whole page. These pin what
 * the reader gets instead — a real run, a plain sentence, and a way out — and that no status code
 * is the message.
 */
function notFound(runId: number): Error {
  return Object.assign(new Error(`404 from /api/runs/${String(runId)}`), { status: 404 });
}

function failing(runId: number): Error {
  return Object.assign(new Error(`503 from /api/runs/${String(runId)}`), { status: 503 });
}

describe("a run that has no stored funnel", () => {
  it("opens on the newest run that has one, and says which run it skipped", async () => {
    vi.mocked(getRuns).mockResolvedValue({
      runs: [runSummary({ id: 529 }), runSummary({ id: 528 })],
    });
    vi.mocked(getFunnel).mockImplementation((id: number) =>
      id === 529 ? Promise.reject(notFound(529)) : Promise.resolve(runFunnel({ run_id: id })),
    );
    render(<RunsPage />);

    await screen.findByText(/^funnel · artifact/);
    screen.getByText(/Showing run 528 — the newest run with a stored funnel\. Run 529 is listed but has none\./);
    // The picker still lists the run it skipped: nothing was hidden.
    expect(screen.getByRole("option", { name: /^529 ·/ })).toBeTruthy();
    expect(screen.queryByText(/404/)).toBeNull();
  });

  it("explains a run the reader picked, in words, and offers the way out", async () => {
    vi.mocked(getRuns).mockResolvedValue({
      runs: [runSummary({ id: 529 }), runSummary({ id: 528 })],
    });
    vi.mocked(getFunnel).mockImplementation((id: number) =>
      id === 529 ? Promise.reject(notFound(529)) : Promise.resolve(runFunnel({ run_id: id })),
    );
    render(<RunsPage />);
    await screen.findByText(/^funnel · artifact/);

    // The reader chooses the run with no funnel on purpose.
    fireEvent.change(screen.getByRole("combobox", { name: "run" }), { target: { value: "529" } });
    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("No funnel is stored for run 529.")).toBeTruthy();
    // Not a status code, and not a reason invented for the missing file.
    expect(notice.textContent).not.toMatch(/404|api\/runs/);
    expect(notice.textContent).not.toMatch(/because|probably|crashed/i);
    // The run's own summary is still on the page, so what is known is not taken away.
    expect(screen.getByRole("region", { name: "Run summary" })).toBeTruthy();

    fireEvent.click(within(notice).getByRole("button", { name: "Show the newest run that has one" }));
    await screen.findByText(/^funnel · artifact/);
  });

  it("skips a funnel file it cannot draw, instead of throwing, and says which run it skipped", async () => {
    // A file from an older writer, or a cut-off one: it comes back 200 but lacks `errors`,
    // `sources`, `lanes` and `coverage`. The server passes stored files through unchanged.
    const thin = { run_id: 529, stages: [], reconciles: true } as unknown as RunFunnel;
    vi.mocked(getRuns).mockResolvedValue({
      runs: [runSummary({ id: 529 }), runSummary({ id: 528 })],
    });
    vi.mocked(getFunnel).mockImplementation((id: number) =>
      Promise.resolve(id === 529 ? thin : runFunnel({ run_id: id })),
    );
    render(<RunsPage />);

    await screen.findByText(/^funnel · artifact/);
    screen.getByText(/Showing run 528 — the newest run with a stored funnel\. Run 529 is listed but has none\./);
    expect(screen.queryByText(/could not be drawn/)).toBeNull();
  });

  it("explains a picked run whose funnel file is incomplete, and offers the way out", async () => {
    const thin = { run_id: 529, stages: [] } as unknown as RunFunnel;
    vi.mocked(getRuns).mockResolvedValue({
      runs: [runSummary({ id: 529 }), runSummary({ id: 528 })],
    });
    vi.mocked(getFunnel).mockImplementation((id: number) =>
      Promise.resolve(id === 529 ? thin : runFunnel({ run_id: id })),
    );
    render(<RunsPage />);
    await screen.findByText(/^funnel · artifact/);

    fireEvent.change(screen.getByRole("combobox", { name: "run" }), { target: { value: "529" } });
    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("The funnel for run 529 can't be drawn.")).toBeTruthy();
    expect(notice.textContent).toMatch(/missing parts this page needs/);
    expect(notice.textContent).not.toMatch(/404|TypeError|undefined/);
    expect(within(notice).getByRole("button", { name: "Show the newest run that has one" })).toBeTruthy();
  });

  it("offers a retry, in words, when the request itself failed", async () => {
    vi.mocked(getRuns).mockResolvedValue({ runs: [runSummary({ id: 7 })] });
    vi.mocked(getFunnel).mockRejectedValueOnce(failing(7)).mockResolvedValue(runFunnel({ run_id: 7 }));
    render(<RunsPage />);

    const notice = await screen.findByRole("alert");
    within(notice).getByText(/This run['’]s details could not be loaded just now\./);
    expect(notice.textContent).not.toMatch(/503|api\/runs/);
    fireEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    await screen.findByText(/^funnel · artifact/);
  });

  it("does not walk the whole table when no run has a funnel", async () => {
    const runs = Array.from({ length: 40 }, (_, index) => runSummary({ id: 100 - index }));
    vi.mocked(getRuns).mockResolvedValue({ runs });
    // Counted from zero: the mock's call log is shared with every earlier test in this file.
    vi.mocked(getFunnel).mockClear();
    vi.mocked(getFunnel).mockImplementation((id: number) => Promise.reject(notFound(id)));
    render(<RunsPage />);

    await screen.findByText(/^No funnel is stored for run /);
    // A bounded look-back: a store with none costs a handful of fast 404s, not forty.
    expect(vi.mocked(getFunnel).mock.calls.length).toBeLessThanOrEqual(12);
  });
});

describe("a run list that cannot be loaded", () => {
  it("says so plainly and retries on request", async () => {
    vi.mocked(getRuns)
      .mockRejectedValueOnce(new Error("503 from /api/runs"))
      .mockResolvedValue({ runs: [runSummary({ id: 3 })] });
    vi.mocked(getFunnel).mockResolvedValue(runFunnel({ run_id: 3 }));
    render(<RunsPage />);

    const notice = await screen.findByRole("alert");
    within(notice).getByText("The run list could not be loaded.");
    expect(notice.textContent).not.toMatch(/503|api\/runs/);
    fireEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    await screen.findByText(/^funnel · artifact/);
  });

  it("says no runs are recorded, rather than loading forever, when the table is empty", async () => {
    vi.mocked(getRuns).mockResolvedValue({ runs: [] });
    render(<RunsPage />);
    await screen.findByText("No runs are recorded yet.");
  });
});
