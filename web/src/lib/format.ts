/**
 * Display helpers. Every one of them has a defined answer for `null`, and none of them is `0`.
 *
 * Every guard here is `== null`, deliberately loose, so it catches `undefined` as well. The types
 * say `undefined` cannot arrive; `boardwatch web` says otherwise, because it serves this bundle
 * from DISK while answering from the Python it imported at STARTUP, so a long-lived viewer can
 * serve a bundle that reads a field its own API never learned to send. An absent field then
 * arrives as `undefined`, `=== null` waves it through, and `undefined.toLocaleString()` throws
 * during render — which is how one absent field blanked the whole page (D-360). These helpers sit
 * under nearly every number the viewer prints, so this is the cheapest place to hold that line.
 */

export const EM_DASH = "\u2014";

/**
 * Age from the board's published date. `null` means the board published no date and renders as an
 * em dash — never `0d`, which would claim the posting went up today. A genuine zero says "today".
 */
export function formatAge(days: number | null): string {
  if (days == null) return EM_DASH;
  if (days === 0) return "today";
  return `${String(days)}d`;
}

/** A coverage fraction. `null` is "not measured", which is exactly the thin-JD case. */
export function formatFraction(fraction: number | null): string {
  if (fraction == null) return EM_DASH;
  return `${(fraction * 100).toFixed(0)}%`;
}

/**
 * TWO decimals, not one. Measured on the live store: every row on the first screen printed 0.9 or
 * 1.0, so the column that the list sorts by carried no information at all — one decimal collapses
 * the whole ranked head onto two values. The scale is not fixed at 0..1 (the fixtures run to ~90),
 * so this is a precision change rather than a percentage.
 */
export function formatScore(score: number | null): string {
  if (score == null) return EM_DASH;
  return score.toFixed(2);
}

export function formatTimestamp(iso: string | null): string {
  if (iso == null) return EM_DASH;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return EM_DASH;
  return when.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatCount(value: number | null): string {
  return value == null ? EM_DASH : value.toLocaleString();
}

/**
 * Today as `YYYY-MM-DD` in the BROWSER's local zone, built from the local parts.
 *
 * Never `toISOString().slice(0, 10)`, which is UTC: west of Greenwich that answers tomorrow's
 * date for the whole evening, so every follow-up pinned for tomorrow would read as due tonight.
 * The server answers the same question in its own local zone (`delivery/api.local_today`), and
 * this viewer only ever talks to loopback, so the two are the same wall calendar.
 */
export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${String(now.getFullYear())}-${month}-${day}`;
}

/**
 * Whether a pinned follow-up has arrived. `<=`, never `==`: a date that slipped past unread is
 * the one that most needs surfacing. ISO-8601 dates compare lexicographically exactly as they
 * compare chronologically, so this needs no `Date` parse and no zone.
 *
 * `== null` for the usual reason — an older server omits the field entirely.
 */
export function isFollowUpDue(followUp: string | null | undefined): boolean {
  if (followUp == null) return false;
  return followUp <= todayIso();
}

/**
 * The window a follow-up may be pinned in, as the `min`/`max` a date input takes.
 *
 * The same 366 days as `delivery/server.FOLLOWUP_MAX_DAYS`, and two-sided for the same reason
 * that guard is: a date input fills its segments left to right, so typing the year of a date
 * walks the value through `0002-…`, `0020-…` and `0202-…`, and every one of those is `<= today`
 * and therefore due forever. A control that offers a value the route refuses is a 400 the reader
 * could not have predicted. A recent PAST date is inside the window — overdue is a real state.
 *
 * Local parts, never `toISOString()`, for the reason `todayIso` gives.
 */
const FOLLOW_UP_MAX_DAYS = 366;

export function followUpWindow(): { min: string; max: string } {
  const bound = (days: number): string => {
    const when = new Date();
    when.setDate(when.getDate() + days);
    const month = String(when.getMonth() + 1).padStart(2, "0");
    const day = String(when.getDate()).padStart(2, "0");
    return `${String(when.getFullYear())}-${month}-${day}`;
  };
  return { min: bound(-FOLLOW_UP_MAX_DAYS), max: bound(FOLLOW_UP_MAX_DAYS) };
}

/**
 * Only `http:` and `https:` may become a link. Apply URLs come from third-party boards, so
 * anything else — `javascript:`, `data:`, a relative path — is rendered as inert text instead.
 */
export function isSafeHttpUrl(value: string | null): boolean {
  if (value == null) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * The absolute filesystem path behind a `file://` URI. This is what "Copy PDF path" puts on the
 * clipboard: both the macOS and the Windows file dialog accept a pasted absolute path, which
 * replaces a three-to-five action detour through the file manager with one paste.
 */
export function pathFromFileUri(uri: string | null): string | null {
  if (uri == null) return null;
  if (!uri.startsWith("file://")) return uri;
  let path = decodeURIComponent(uri.slice("file://".length));
  // `file:///C:/x` — a Windows path keeps its drive letter and loses the leading slash.
  if (/^\/[A-Za-z]:/.test(path)) path = path.slice(1);
  return path;
}

/** The queue folder is the PDF's parent directory; shown so "Reveal folder" is not a mystery. */
export function parentDirectory(path: string | null): string | null {
  if (path == null) return null;
  const index = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return index <= 0 ? null : path.slice(0, index);
}
