import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StaleViewerBanner } from "../components/StaleViewerBanner";

/*
 * The stale-viewer banner. Two skews, two remedies: code changed under the running process
 * (restart it) and a newer page on disk than the tab loaded (reload). A failed check says nothing.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getVersion: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { getVersion } from "../api/client";

function loadedScript(name: string | null): void {
  document.head.querySelectorAll("script[data-test-entry]").forEach((node) => {
    node.remove();
  });
  if (name === null) return;
  const script = document.createElement("script");
  script.type = "module";
  script.setAttribute("src", `/assets/${name}`);
  script.setAttribute("data-test-entry", "");
  document.head.append(script);
}

async function renderBanner(): Promise<void> {
  render(<StaleViewerBanner />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  loadedScript(null);
});

describe("the stale-viewer banner", () => {
  it("says nothing while the page and the code are the ones on disk", async () => {
    loadedScript("index-AAA.js");
    vi.mocked(getVersion).mockResolvedValue({ bundle: "index-AAA.js", code_changed: false });
    await renderBanner();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("offers a reload when a newer page is on disk than the one this tab loaded", async () => {
    loadedScript("index-AAA.js");
    vi.mocked(getVersion).mockResolvedValue({ bundle: "index-BBB.js", code_changed: false });
    await renderBanner();
    expect(screen.getByText("A newer version of this page is on disk.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
  });

  it("asks for a restart, not a reload, when the code changed under the viewer", async () => {
    loadedScript("index-AAA.js");
    vi.mocked(getVersion).mockResolvedValue({ bundle: "index-BBB.js", code_changed: true });
    await renderBanner();
    expect(screen.getByText(/Stop it and start `boardwatch web` again/)).toBeTruthy();
    // A reload cannot fix this half, so it is not offered as if it could.
    expect(screen.queryByRole("button", { name: "Reload" })).toBeNull();
  });

  it("notices a change made while the page is open, on the next check", async () => {
    loadedScript("index-AAA.js");
    vi.mocked(getVersion).mockResolvedValue({ bundle: "index-AAA.js", code_changed: false });
    await renderBanner();
    expect(screen.queryByRole("status")).toBeNull();

    vi.mocked(getVersion).mockResolvedValue({ bundle: "index-AAA.js", code_changed: true });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("says nothing when the check fails or the dev server loaded no built page", async () => {
    loadedScript("index-AAA.js");
    vi.mocked(getVersion).mockRejectedValue(new Error("404 from /api/version"));
    await renderBanner();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not claim a newer page under the dev server, which loads no /assets/ entry", async () => {
    loadedScript(null);
    vi.mocked(getVersion).mockResolvedValue({ bundle: "index-BBB.js", code_changed: false });
    await renderBanner();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
