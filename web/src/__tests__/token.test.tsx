import { beforeEach, describe, expect, it, vi } from "vitest";

/*
 * `api/token.ts` is the whole security surface of the viewer: the bearer arrives in the URL
 * FRAGMENT, is read once, and is scrubbed from the address bar before the first fetch. The bearer
 * is a MODULE-scoped `let`, so each test resets the module and re-imports to start from `null` —
 * otherwise the first capture would leak into every test after it.
 *
 * `.test.tsx`, not `.test.ts`, only because the vitest gate's `include` is `src/**\/*.test.tsx`.
 */

// A fresh module per test, so `bearer` starts null and one test's capture cannot satisfy the next.
async function freshToken() {
  vi.resetModules();
  return import("../api/token");
}

// jsdom starts at http://localhost/ with an empty fragment; each test sets its own hash and
// history so the scrub target ("#/queue") is unambiguous.
beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("captureToken", () => {
  it("reads a bare `#<token>` fragment and sends it as a Bearer header", async () => {
    window.location.hash = "#abc123";
    const { captureToken, hasToken, authHeaders } = await freshToken();

    captureToken();

    expect(hasToken()).toBe(true);
    expect(authHeaders()).toEqual({ Authorization: "Bearer abc123" });
  });

  it("reads the `#token=<token>` form to the SAME token as the bare form", async () => {
    window.location.hash = "#token=abc123";
    const { captureToken, authHeaders } = await freshToken();

    captureToken();

    // The `token=` prefix is stripped, so both spellings resolve to the identical credential.
    expect(authHeaders()).toEqual({ Authorization: "Bearer abc123" });
  });

  it("URL-decodes the token before sending it", async () => {
    window.location.hash = "#token=a%20b%2Bc";
    const { captureToken, authHeaders } = await freshToken();

    captureToken();

    expect(authHeaders()).toEqual({ Authorization: "Bearer a b+c" });
  });

  it("scrubs the fragment to the default route after capture", async () => {
    window.location.hash = "#token=secret";
    const { captureToken } = await freshToken();

    captureToken();

    // The credential is gone from the address bar — a reload, a bookmark or a referrer can no
    // longer carry it — and what is left is the router's default route, not the empty string.
    expect(window.location.hash).toBe("#/queue");
    expect(window.location.href).not.toContain("secret");
  });

  it.each(["#/queue", "#/runs"])(
    "treats a route fragment %s as a route, never as a token",
    async (route) => {
      window.location.hash = route;
      const { captureToken, hasToken, authHeaders } = await freshToken();

      captureToken();

      // A fragment beginning with `/` is the router's, so nothing is captured and no
      // `Authorization: Bearer /queue` is ever assembled from a route the user navigated to.
      expect(hasToken()).toBe(false);
      expect(authHeaders()).toEqual({});
      // And because nothing was captured, the route the reader is on is left untouched.
      expect(window.location.hash).toBe(route);
    },
  );

  it("captures nothing from an empty fragment", async () => {
    window.location.hash = "";
    const { captureToken, hasToken, authHeaders } = await freshToken();

    captureToken();

    expect(hasToken()).toBe(false);
    expect(authHeaders()).toEqual({});
  });
});
