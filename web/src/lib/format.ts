/** Display helpers. Every one of them has a defined answer for `null`, and none of them is `0`. */

export const EM_DASH = "\u2014";

/**
 * Age from the board's published date. `null` means the board published no date and renders as an
 * em dash — never `0d`, which would claim the posting went up today. A genuine zero says "today".
 */
export function formatAge(days: number | null): string {
  if (days === null) return EM_DASH;
  if (days === 0) return "today";
  return `${String(days)}d`;
}

/** A coverage fraction. `null` is "not measured", which is exactly the thin-JD case. */
export function formatFraction(fraction: number | null): string {
  if (fraction === null) return EM_DASH;
  return `${(fraction * 100).toFixed(0)}%`;
}

export function formatScore(score: number | null): string {
  if (score === null) return EM_DASH;
  return score.toFixed(1);
}

export function formatTimestamp(iso: string | null): string {
  if (iso === null) return EM_DASH;
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
  return value === null ? EM_DASH : value.toLocaleString();
}

/**
 * Only `http:` and `https:` may become a link. Apply URLs come from third-party boards, so
 * anything else — `javascript:`, `data:`, a relative path — is rendered as inert text instead.
 */
export function isSafeHttpUrl(value: string | null): boolean {
  if (value === null) return false;
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
  if (uri === null) return null;
  if (!uri.startsWith("file://")) return uri;
  let path = decodeURIComponent(uri.slice("file://".length));
  // `file:///C:/x` — a Windows path keeps its drive letter and loses the leading slash.
  if (/^\/[A-Za-z]:/.test(path)) path = path.slice(1);
  return path;
}

/** The queue folder is the PDF's parent directory; shown so "Reveal folder" is not a mystery. */
export function parentDirectory(path: string | null): string | null {
  if (path === null) return null;
  const index = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return index <= 0 ? null : path.slice(0, index);
}
