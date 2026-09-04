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
//
// `localStorage` is cleared too, and that is load-bearing rather than tidiness: the token now
// PERSISTS there, and jsdom shares one storage across every test in the file. Without this, a
// capture in one test would satisfy `captureToken` in the next and the route-fragment tests below
// would pass for the wrong reason.
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
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

describe("persistence — what makes the viewer's URL openable whenever", () => {
  it("restores a stored token when the fragment is a ROUTE, not a credential", async () => {
    // The exact shape the owner hit: the router owns the fragment after the first visit, so a
    // reload or a bookmark of `#/queue` arrives with no credential in the URL at all.
    window.localStorage.setItem("boardwatch.web-token", "stored-secret");
    window.location.hash = "#/queue";
    const { captureToken, hasToken, authHeaders } = await freshToken();

    captureToken();

    expect(hasToken()).toBe(true);
    expect(authHeaders()).toEqual({ Authorization: "Bearer stored-secret" });
    // The route is still the reader's; restoring a credential must not navigate them.
    expect(window.location.hash).toBe("#/queue");
  });

  it("restores a stored token when the fragment is EMPTY", async () => {
    window.localStorage.setItem("boardwatch.web-token", "stored-secret");
    window.location.hash = "";
    const { captureToken, authHeaders } = await freshToken();

    captureToken();

    expect(authHeaders()).toEqual({ Authorization: "Bearer stored-secret" });
  });

  it("persists a captured token so the NEXT page load needs no fragment", async () => {
    window.location.hash = "#token=fresh-secret";
    const first = await freshToken();
    first.captureToken();
    expect(window.localStorage.getItem("boardwatch.web-token")).toBe("fresh-secret");

    // A second load, arriving on the scrubbed route with no credential in the URL.
    const second = await freshToken();
    second.captureToken();
    expect(second.authHeaders()).toEqual({ Authorization: "Bearer fresh-secret" });
  });

  it("stores the DECODED token, not the percent-encoded fragment text", async () => {
    window.location.hash = "#token=a%20b%2Bc";
    const { captureToken } = await freshToken();

    captureToken();

    // Storing the raw fragment would double-decode on the next load and send a different secret.
    expect(window.localStorage.getItem("boardwatch.web-token")).toBe("a b+c");
  });

  it("forgetToken drops the credential from memory AND from storage", async () => {
    window.location.hash = "#token=stale-secret";
    const { captureToken, forgetToken, hasToken, authHeaders } = await freshToken();
    captureToken();
    expect(hasToken()).toBe(true);

    forgetToken();

    // Both halves matter: leaving it in storage would replay the rejected secret on every reload
    // and strand the reader, which is exactly what the 401 path calls this to prevent.
    expect(hasToken()).toBe(false);
    expect(authHeaders()).toEqual({});
    expect(window.localStorage.getItem("boardwatch.web-token")).toBeNull();
  });

  it("still captures from the fragment when localStorage THROWS", async () => {
    // Storage disabled: the viewer must degrade to the old per-page behaviour, never fail to load.
    const spy = vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    try {
      window.location.hash = "#token=abc123";
      const { captureToken, authHeaders } = await freshToken();

      captureToken();

      expect(authHeaders()).toEqual({ Authorization: "Bearer abc123" });
    } finally {
      spy.mockRestore();
    }
  });

  it("captures nothing when the fragment is empty and storage holds nothing", async () => {
    window.location.hash = "";
    const { captureToken, hasToken } = await freshToken();

    captureToken();

    expect(hasToken()).toBe(false);
  });
});
