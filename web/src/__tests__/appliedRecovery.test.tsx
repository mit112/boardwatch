import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appliedResponse, appliedRow } from "../test/rows";

/*
 * The Applied page when its read is slow or fails. The page used to print "Loading…" for as long as
 * the server took — more than a minute on the live store before the read path was fixed — with no
 * way out. It now holds its layout, says when it is taking longer than it should, offers a retry,
 * and on failure says so in words rather than printing a status code.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getApplied: vi.fn(),
  getQueue: vi.fn(),
}));

import { getApplied } from "../api/client";
import { App } from "../App";

const SLOW_MS = 8_000;

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/#/applied");
});

afterEach(() => {
  vi.useRealTimers();
});

async function settle(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("a slow read", () => {
  it("says so after a while, keeps the layout, and offers a retry that works", async () => {
    vi.mocked(getApplied).mockReturnValue(new Promise(() => undefined));
    render(<App />);
    await settle();
    screen.getByText("Loading your applied history…");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();

    await settle(SLOW_MS + 100);
    screen.getByText(/Still loading your applied history — this is taking longer than usual\./);

    vi.mocked(getApplied).mockResolvedValue(appliedResponse([appliedRow({ company: "Acme Corp" })]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await settle();
    expect(screen.getByText("Acme Corp")).toBeTruthy();
  });
});

describe("a failed read", () => {
  it("says what happened in words, with the transport text kept small, and retries on request", async () => {
    vi.mocked(getApplied).mockRejectedValueOnce(new Error("503 from /api/applied"));
    render(<App />);
    await settle();

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Your applied history could not be loaded.");
    expect(alert.textContent).toContain("Nothing was changed");

    vi.mocked(getApplied).mockResolvedValue(appliedResponse([appliedRow({ company: "Acme Corp" })]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await settle();
    expect(screen.getByText("Acme Corp")).toBeTruthy();
  });
});

describe("an application with no update", () => {
  it("is described as having no update RECORDED, never as unanswered by the employer", async () => {
    vi.mocked(getApplied).mockResolvedValue(
      appliedResponse([
        appliedRow({
          company: "Acme Corp",
          status: "applied",
          quiet: true,
          last_activity_at: new Date(Date.now() - 25 * 86_400_000).toISOString(),
        }),
      ]),
    );
    render(<App />);
    await settle();

    screen.getByText(/^No update recorded · 25 d/);
    // The absence of a log entry is all the page knows. It does not say anyone failed to reply.
    expect(document.body.textContent).not.toMatch(/no reply|not replied|unanswered|ghost/i);
    const badge = screen.getByText(/^No update recorded · 25 d/);
    expect(badge.getAttribute("title")).toMatch(/absence of a record, not evidence/);
  });
});
