import { isSafeHttpUrl } from "../lib/format";

/*
 * Apply URLs come from third-party boards. Only `http:` and `https:` become a link, and it opens
 * with `rel="noopener noreferrer"`. Anything else — a `javascript:` URL above all — renders as
 * inert text, so the owner can still see what the board supplied without it being clickable.
 *
 * This is the ONE place that decision is made. The row and the detail pane both route through it.
 */
const BUTTON =
  "inline-flex items-center rounded border px-3 transition-colors duration-[120ms] ease-snap";

/**
 * The focused row's `o` key. It routes through the same `isSafeHttpUrl` test as the link below, so
 * the keyboard path cannot become the one that opens a `javascript:` URL. Returns false when there
 * was nothing safe to open, which is what the caller reports to the reader.
 */
export function openApplyUrl(url: string | null): boolean {
  if (!isSafeHttpUrl(url) || url === null) return false;
  window.open(url, "_blank", "noopener,noreferrer");
  return true;
}

export function ApplyLink({
  url,
  compact = false,
  emphasis = false,
  label,
}: {
  url: string | null;
  compact?: boolean;
  /** The row's leading control, so it is not one of three identical grey pills. */
  emphasis?: boolean;
  /** Names the lead in the accessible name; a list of 347 links all called "Apply" is unusable. */
  label?: string;
}) {
  // In a row the control is one tab stop among four unless it opts out — see `QueueTable`. The
  // focused row's `o` key opens the same URL, so nothing becomes mouse-only.
  const size = compact ? "min-h-8 text-xs" : "min-h-11 text-sm";

  if (isSafeHttpUrl(url) && url !== null) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        {...(compact ? { tabIndex: -1 } : {})}
        {...(label ? { "aria-label": `Open apply link: ${label}` } : {})}
        {...(compact ? { title: "Open the board's apply page. Key: o" } : {})}
        className={`${BUTTON} ${size} ${
          emphasis
            ? "border-fg-2 text-fg hover:border-fg hover:bg-surface-2"
            : "border-control text-fg-2 hover:border-fg-2 hover:text-fg"
        }`}
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
    <span className={`${BUTTON} ${size} border-divider text-fg-3`} title={explanation}>
      {compact ? "no link" : explanation}
    </span>
  );
}
