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

/** Dispatched on `window` whenever a credential is captured AFTER load, so a page already showing
 *  its 401 card can retry instead of telling the reader to re-open a URL they just opened. */
export const TOKEN_EVENT = "boardwatch:token";

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

/** Reads the fragment and, when it holds a credential rather than a route, captures and scrubs
 *  it. Returns whether it captured anything. */
function captureFromFragment(): boolean {
  const raw = window.location.hash.replace(/^#/, "");
  if (raw === "" || raw.startsWith("/")) return false;
  const value = raw.startsWith("token=") ? raw.slice("token=".length) : raw;
  bearer = decodeURIComponent(value);
  storage()?.setItem(STORAGE_KEY, bearer);
  // Immediately, and before the first render or the first fetch.
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${window.location.search}${DEFAULT_ROUTE}`,
  );
  return true;
}

export function captureToken(): void {
  // No credential in the fragment: this is a reload, a bookmark, or an in-app route. Fall back
  // to the one a previous visit stored, which is the whole point of storing it.
  if (!captureFromFragment()) bearer = storage()?.getItem(STORAGE_KEY) ?? null;
}

/*
 * The SECOND way a token arrives, and the one the load-time capture cannot see: pasting the CLI's
 * URL into a tab that already has this app open is a same-document navigation, so the browser
 * fires `hashchange` and reloads nothing. Without this the credential was neither read nor
 * scrubbed — the page stayed 401 while its own card told the reader to re-open the URL they had
 * just opened, and the secret stayed in the address bar.
 *
 * Registered at module scope, so it is live from the same moment `captureToken()` is: there is no
 * window in which a paste is dropped. `replaceState` does not fire `hashchange`, so the scrub
 * inside the handler cannot re-enter it.
 */
window.addEventListener("hashchange", () => {
  if (!captureFromFragment()) return;
  window.dispatchEvent(new CustomEvent(TOKEN_EVENT));
});

/** Drop the credential, in memory and on disk. Called when the server rejects it, so a rotated
 *  token cannot wedge the viewer permanently. */
export function forgetToken(): void {
  bearer = null;
  storage()?.removeItem(STORAGE_KEY);
}

export function authHeaders(): HeadersInit {
  return bearer === null ? {} : { Authorization: `Bearer ${bearer}` };
}
