import { isSafeHttpUrl } from "../lib/format";
import { Icon } from "./Icon";

/*
 * Apply URLs come from third-party boards. Only `http:` and `https:` become a link, and it opens
 * with `rel="noopener noreferrer"`. Anything else — a `javascript:` URL above all — renders as
 * inert text, so the owner can still see what the board supplied without it being clickable.
 *
 * This is the ONE place that decision is made.
 *
 * "Open application" opens the EMPLOYER'S page and nothing else. It never records anything — a
 * link that was opened is not an application that was sent, and the app asks "did you apply?" only
 * when the reader comes back (`ApplyReturnPrompt`) and records only on their yes.
 */

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
  onOpen,
  primary = true,
}: {
  url: string | null;
  /** Told when the link is followed, by a click or a middle-click, so the page can ask on return
   *  whether the reader applied. The browser still does the opening. */
  onOpen?: () => void;
  /** The filled forest button — the one primary action of the workspace. */
  primary?: boolean;
}) {
  const base =
    "inline-flex min-h-11 items-center gap-2 rounded-sm px-4 text-sm font-semibold transition-colors duration-150 ease-in-out";

  if (isSafeHttpUrl(url) && url !== null) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        title="Opens the employer’s page in a new tab. Nothing is recorded until you say you applied."
        {...(onOpen === undefined
          ? {}
          : {
              onClick: onOpen,
              onAuxClick: (event: React.MouseEvent) => {
                if (event.button === 1) onOpen();
              },
            })}
        className={`${base} ${
          primary
            ? "bg-primary text-on-primary hover:bg-primary-strong"
            : "bg-surface-2 text-fg hover:bg-surface-3"
        }`}
      >
        Open application
        <Icon name="external" />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    );
  }

  const explanation =
    url === null
      ? "The job board supplied no application link."
      : `Not an http(s) address, so it is not offered as a link: ${url}`;

  return (
    <span className={`${base} bg-surface-2 font-normal text-fg-3`} title={explanation}>
      No application link
      <span className="sr-only">{`. ${explanation}`}</span>
    </span>
  );
}
