import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/*
 * Pasting the CLI's URL into an ALREADY-OPEN tab.
 *
 * `captureToken()` ran once, at load. Navigating an open tab to `http://127.0.0.1:8799/#<token>`
 * is a same-document navigation — the browser fires `hashchange` and reloads nothing — so the
 * credential was never read and never scrubbed: the page stayed 401 while its own card told the
 * reader to re-open the URL they had just opened, and the secret sat in the address bar.
 *
 * ONE module instance for the whole file, reset with `forgetToken()` — deliberately NOT
 * `vi.resetModules()` the way `token.test.tsx` does. The `hashchange` listener is registered at
 * module scope, so a second instance would leave a second listener on the same `window`: the older
 * one would capture and scrub first and every assertion below would pass against a module the test
 * is not holding.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
  markApplied: vi.fn(),
  markSkipped: vi.fn(),
  unskip: vi.fn(),
  unapply: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

import { getQueue } from "../api/client";
import { TOKEN_EVENT, authHeaders, captureToken, forgetToken } from "../api/token";
import { App } from "../App";
import { queueResponse, queueRow } from "../test/rows";

/** jsdom queues `hashchange` off the assignment; dispatching it directly keeps the ordering
 *  explicit rather than depending on when that task drains. */
function navigateHash(hash: string): void {
  window.location.hash = hash;
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

beforeEach(() => {
  window.history.replaceState(null, "", "/#/queue");
  window.localStorage.clear();
  forgetToken();
  captureToken();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("a token arriving by hashchange", () => {
  it("captures it, stores it and scrubs the fragment", () => {
    expect(authHeaders()).toEqual({});

    navigateHash("#pasted-secret");

    expect(authHeaders()).toEqual({ Authorization: "Bearer pasted-secret" });
    expect(window.localStorage.getItem("boardwatch.web-token")).toBe("pasted-secret");
    // Scrubbed exactly as at load: the address bar must not keep the credential.
    expect(window.location.hash).toBe("#/queue");
    expect(window.location.href).not.toContain("pasted-secret");
  });

  it("accepts the `#token=` spelling and announces the capture", () => {
    const heard = vi.fn();
    window.addEventListener(TOKEN_EVENT, heard);

    navigateHash("#token=pasted-secret");

    expect(authHeaders()).toEqual({ Authorization: "Bearer pasted-secret" });
    // The announcement is the whole contract with the page: without it nothing retries.
    expect(heard).toHaveBeenCalledTimes(1);
    window.removeEventListener(TOKEN_EVENT, heard);
  });

  it("ignores a ROUTE fragment, and announces nothing", () => {
    const heard = vi.fn();
    window.addEventListener(TOKEN_EVENT, heard);

    navigateHash("#/runs");

    // Navigating between the app's own views must never assemble `Bearer /runs`.
    expect(authHeaders()).toEqual({});
    expect(window.location.hash).toBe("#/runs");
    expect(heard).not.toHaveBeenCalled();
    window.removeEventListener(TOKEN_EVENT, heard);
  });
});

describe("the queue page's response to a captured token", () => {
  it("re-loads with the new bearer, clearing the 401 card", async () => {
    vi.mocked(getQueue).mockRejectedValueOnce(
      new Error("Not authorised. Re-open the URL the CLI printed — it carries the token."),
    );
    render(<App />);
    await screen.findByRole("alert");
    expect(vi.mocked(getQueue)).toHaveBeenCalledTimes(1);

    vi.mocked(getQueue).mockResolvedValue(queueResponse([queueRow({ title: "AFTER-TOKEN" })]));
    await act(async () => {
      navigateHash("#pasted-secret");
      await Promise.resolve();
    });

    expect(vi.mocked(getQueue)).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("AFTER-TOKEN")).toBeTruthy();
    // The card is gone: leaving it up would tell the reader to do what they just did.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
