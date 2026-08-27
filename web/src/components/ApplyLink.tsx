import { isSafeHttpUrl } from "../lib/format";

/*
 * Apply URLs come from third-party boards. Only `http:` and `https:` become a link, and it opens
 * with `rel="noopener noreferrer"`. Anything else — a `javascript:` URL above all — renders as
 * inert text, so the owner can still see what the board supplied without it being clickable.
 *
 * This is the ONE place that decision is made. The row and the detail pane both route through it.
 */
const BUTTON =
  "inline-flex min-h-11 items-center rounded border px-3 transition-colors duration-[120ms] ease-snap";

export function ApplyLink({
  url,
  compact = false,
}: {
  url: string | null;
  compact?: boolean;
}) {
  if (isSafeHttpUrl(url) && url !== null) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={`${BUTTON} border-control text-fg-2 hover:border-fg-2 hover:text-fg ${compact ? "text-xs" : "text-sm"}`}
      >
        {compact ? "Apply" : "Open apply link"}
      </a>
    );
  }

  const explanation =
    url === null
      ? "The board supplied no apply URL."
      : `Not an http(s) URL, so it is not rendered as a link: ${url}`;

  return (
    <span
      className={`${BUTTON} border-divider text-fg-3 ${compact ? "text-xs" : "text-sm"}`}
      title={explanation}
    >
      {compact ? "no link" : explanation}
    </span>
  );
}
