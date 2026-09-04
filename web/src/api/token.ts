/*
 * The bearer token arrives in the URL FRAGMENT, is read once, and is erased from the address bar
 * before anything else can observe it. It is sent only as an `Authorization: Bearer` header —
 * never in a query string, never in a cookie, so nothing token-bearing reaches browser history, a
 * referrer, or a bookmark the owner did not deliberately save.
 *
 * Both `#<token>` and `#token=<token>` are accepted. A fragment beginning with `/` is a route, not
 * a token, so a reload after `replaceState` does not mistake `#/runs` for a credential.
 *
 * **It is also mirrored into `localStorage`, and that is what makes the viewer's URL openable
 * whenever.** The fragment carries the credential exactly once; the router then owns the fragment
 * (`#/queue`, `#/runs`), so without somewhere to keep it, every reload and every bookmark landed
 * on a 401 and the CLI URL had to be dug out again. `localStorage` is the right home and a cookie
 * is not: a cookie is attached automatically to any request the browser is talked into making,
 * which is precisely the cross-site form post the token exists to defeat, whereas `localStorage`
 * is same-origin-readable only and is never sent by itself. It reaches no history entry, no
 * referrer and no bookmark either — those are properties of the URL, which this still scrubs.
 *
 * A persisted credential must be forgettable, or a server-side token rotation strands the reader
 * on a stale secret with no way back: `forgetToken` drops it, and the client calls that on 401 so
 * the "re-open the URL the CLI printed" message is true again by the time it is read.
 */

const DEFAULT_ROUTE = "#/queue";
const STORAGE_KEY = "boardwatch.web-token";

let bearer: string | null = null;

/** `localStorage` access throws outright when storage is disabled or the quota is gone, and a
 *  viewer that cannot remember a token must still be a viewer that runs. */
function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function captureToken(): void {
  const raw = window.location.hash.replace(/^#/, "");
  if (raw === "" || raw.startsWith("/")) {
    // No credential in the fragment: this is a reload, a bookmark, or an in-app route. Fall back
    // to the one a previous visit stored, which is the whole point of storing it.
    bearer = storage()?.getItem(STORAGE_KEY) ?? null;
    return;
  }
  const value = raw.startsWith("token=") ? raw.slice("token=".length) : raw;
  bearer = decodeURIComponent(value);
  storage()?.setItem(STORAGE_KEY, bearer);
  // Immediately, and before the first render or the first fetch.
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${window.location.search}${DEFAULT_ROUTE}`,
  );
}

/** Drop the credential, in memory and on disk. Called when the server rejects it, so a rotated
 *  token cannot wedge the viewer permanently. */
export function forgetToken(): void {
  bearer = null;
  storage()?.removeItem(STORAGE_KEY);
}

export function hasToken(): boolean {
  return bearer !== null;
}

export function authHeaders(): HeadersInit {
  return bearer === null ? {} : { Authorization: `Bearer ${bearer}` };
}
