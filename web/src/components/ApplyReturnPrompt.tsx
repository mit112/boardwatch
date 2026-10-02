import { useEffect, useId, useRef } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import type { QueueRow } from "../api/types";

/*
 * "Did you apply?", asked when the reader comes back from a lead's apply page.
 *
 * The expensive failure this exists for is the application that was sent and never marked: the
 * lead comes back every run, and the dedup that would learn from it never does. The question is
 * asked at the one moment the answer is fresh, and answered with one key.
 *
 * Non-modal: it sits at the top of the page, below the header, clear of the toasts at the bottom
 * (the mark it triggers raises one), and nothing behind it is blocked. Focus moves to its primary
 * button because the reader has just returned to this tab and the question is the next thing to
 * do; `a` marks applied and Escape dismisses, and both are stopped here so the detail pane's own
 * Escape (a window listener) does not also close the lead.
 */
export function ApplyReturnPrompt({
  row,
  onApplied,
  onDismiss,
}: {
  row: QueueRow;
  onApplied: () => void;
  onDismiss: () => void;
}) {
  const yes = useRef<HTMLButtonElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    yes.current?.focus();
  }, [row.posting_id]);

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onDismiss();
      return;
    }
    // Auto-repeat refused, as on the grid: the prompt closes on the first press, and a held key
    // must not land on whatever takes focus next.
    if (event.key === "a" && !event.repeat) {
      event.preventDefault();
      event.stopPropagation();
      onApplied();
    }
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 top-header z-50 flex justify-center p-4">
      <div
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        className="pointer-events-auto flex w-full max-w-xl flex-wrap items-center gap-3 rounded-md bg-surface-2 px-4 py-3 shadow-card ring-1 ring-control"
      >
        <p id={titleId} className="min-w-0 flex-1 text-sm text-fg">
          Back from {row.company} — {row.title}. Did you apply?
        </p>
        <span className="flex items-center gap-2">
          <button
            ref={yes}
            type="button"
            onClick={onApplied}
            title="Record the application. Key: a. Undoable from the toast."
            className="min-h-11 rounded-sm bg-primary px-4 text-sm font-semibold text-on-primary transition-colors duration-150 ease-in-out hover:bg-primary-strong"
          >
            Record application
          </button>
          <button
            type="button"
            onClick={onDismiss}
            title="Leave the job on your list. Key: Esc"
            className="min-h-11 rounded-sm px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg"
          >
            Not yet
          </button>
        </span>
      </div>
    </div>
  );
}
