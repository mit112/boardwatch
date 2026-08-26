/*
 * The bearer token arrives in the URL FRAGMENT, is read once, and is erased from the address bar
 * before anything else can observe it. It lives in a module-scoped variable for the life of the
 * page and is sent only as an `Authorization: Bearer` header — never in a query string, never in
 * `localStorage`, so nothing token-bearing reaches browser history, a referrer, or a bookmark the
 * owner did not deliberately save.
 *
 * Both `#<token>` and `#token=<token>` are accepted. A fragment beginning with `/` is a route, not
 * a token, so a reload after `replaceState` does not mistake `#/runs` for a credential.
 */

const DEFAULT_ROUTE = "#/queue";

let bearer: string | null = null;

export function captureToken(): void {
  const raw = window.location.hash.replace(/^#/, "");
  if (raw === "" || raw.startsWith("/")) return;
  const value = raw.startsWith("token=") ? raw.slice("token=".length) : raw;
  bearer = decodeURIComponent(value);
  // Immediately, and before the first render or the first fetch.
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${window.location.search}${DEFAULT_ROUTE}`,
  );
}

export function hasToken(): boolean {
  return bearer !== null;
}

export function authHeaders(): HeadersInit {
  return bearer === null ? {} : { Authorization: `Bearer ${bearer}` };
}
