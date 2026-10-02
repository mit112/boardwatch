import { useCallback, useEffect, useRef } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import type { QueueRow } from "../api/types";
import type { SimilarGroup } from "../lib/similar";
import { QueueRowItem } from "./QueueRowItem";

/**
 * Multi-select, when the caller offers it. A table handed no `Selection` renders no checkbox
 * column and handles no `x` — which is how the review lane stays exactly as it was.
 *
 * `onMarkMany` takes the whole range in one call rather than one call per row: the caller holds
 * the selection in a `Set`, and N functional updates to select 40 rows is N renders of a
 * 392-row list.
 */
export interface Selection {
  marked: ReadonlySet<number>;
  onMark: (postingId: number) => void;
  onMarkMany: (postingIds: number[], marked: boolean) => void;
}

/**
 * "Select all visible", and `visible` is the word that matters: it takes the rows this table is
 * currently showing, never the whole lane behind the filter.
 *
 * The `indeterminate` DOM property — set through a ref, because React has no JSX prop for it — is
 * what makes a partial selection announce as `aria-checked="mixed"`. Setting `aria-checked` by
 * hand on a native checkbox is not the same thing: the host language owns that state, and the two
 * would then disagree.
 */
function SelectAll({ rows, selection }: { rows: QueueRow[]; selection: Selection }) {
  const box = useRef<HTMLInputElement>(null);
  const count = rows.filter((row) => selection.marked.has(row.posting_id)).length;
  const all = count > 0 && count === rows.length;
  useEffect(() => {
    if (box.current !== null) box.current.indeterminate = count > 0 && !all;
  }, [count, all]);
  return (
    <span role="columnheader" className="flex items-center">
      <input
        ref={box}
        type="checkbox"
        checked={all}
        aria-label={`Select all ${String(rows.length)} visible leads`}
        title="Select every lead this filter is showing"
        onChange={() => {
          selection.onMarkMany(
            rows.map((row) => row.posting_id),
            !all,
          );
        }}
        className="size-4 cursor-pointer accent-accent"
      />
    </span>
  );
}

/*
 * A `role="grid"` whose focusable unit is the ROW, which the ARIA practices allow for a collection
 * the reader works down rather than cell by cell — and which this list needs, because the previous
 * markup had two defects that compound.
 *
 * SEMANTICS. Rows and cells carry their ARIA roles under a real `role="grid"` and `role="rowgroup"`;
 * an orphaned row or columnheader is dropped by assistive tech and the list reads as an
 * undifferentiated wall of buttons. Sorting is a single labelled control above the list (it was a
 * column of header buttons, which a one-column list has no room for).
 *
 * TAB STOPS. Four focusable controls per row measured **1,399 tab stops** on one queue page.
 * Nothing below the list — the review lane, the detail pane — was reachable by keyboard in any
 * practical sense. So the tab stop is the row, exactly one per table (roving `tabIndex`), and the
 * per-row controls opt out with `tabIndex={-1}`. Every one of them keeps a single-key equivalent
 * on the focused row, so this removes tab stops WITHOUT removing keyboard access to anything:
 *
 *   ↓ / j   next row          Enter   open the job in the workspace
 *   ↑ / k   previous row      o       open the application page
 *   Home    first row         a       record that you applied
 *   End     last row          s       skip
 *   x       select the row    shift+x extend the selection from the anchor
 *   r       report the job    f       focus the workspace's follow-up date input
 *
 * The keys are handled HERE, on the grid, not on `window`: `a` and `s` write, and a global
 * listener would fire them while the reader was typing a company name into the filter box.
 */
export function QueueTable({
  label,
  rows,
  selectedId,
  activeId,
  onActivate,
  collapsing,
  onSelect,
  onOpenApply,
  onApplied,
  onSkip,
  onReport,
  onFollowUp,
  selection,
  similarOf,
  onSelectCompany,
  emptyHint = "Clear the search or loosen a filter.",
}: {
  label: string;
  rows: QueueRow[];
  selectedId: number | null;
  activeId: number | null;
  onActivate: (postingId: number) => void;
  collapsing: ReadonlySet<number>;
  onSelect: (row: QueueRow) => void;
  onOpenApply: (row: QueueRow) => void;
  onApplied: (row: QueueRow) => void;
  onSkip: (row: QueueRow) => void;
  onReport: (row: QueueRow) => void;
  /** `f`: move the cursor INTO the pane's date input. Never sets a date by itself — see below. */
  onFollowUp: (row: QueueRow) => void;
  /** Omitted on a table with no multi-select: no checkbox column, no `x`. */
  selection?: Selection;
  /** What the row's group of similar postings holds, or undefined when it has none in this list. */
  similarOf?: (row: QueueRow) => SimilarGroup | undefined;
  /** `c`: add every listed lead at this row's company to the selection. Needs `selection`. */
  onSelectCompany?: (row: QueueRow) => void;
  /* Names the levers that would bring rows back. A verdict facet is a lever the two default
     sentences do not mention, so the empty state must say so or it points at the wrong control. */
  emptyHint?: string;
}) {
  // The roving stop. When the cursor is on a row of the OTHER table — or on none — the first row
  // holds it, so the grid is always reachable in one Tab and never becomes a dead region.
  const activeIndex = rows.findIndex((row) => row.posting_id === activeId);
  const stopId = (activeIndex === -1 ? rows[0]?.posting_id : activeId) ?? null;

  /*
   * The shift-extend ANCHOR: the row `x` last acted on. A ref rather than state — nothing renders
   * from it, and a re-render per keystroke on a 392-row list is exactly what this feature exists
   * to stop. It deliberately survives a shift-extend, so extending twice from one anchor grows
   * and shrinks the same block rather than walking it down the list.
   */
  const anchor = useRef<number | null>(null);

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement;
      // Only when the ROW itself has focus. A click inside a row's buttons must not turn the next
      // keystroke into a write.
      if (target.getAttribute("role") !== "row") return;
      // A held modifier means the keystroke belongs to the BROWSER or the OS, not to this grid.
      // Without this, Cmd+A on a focused row is `event.key === "a"` and marks the lead applied
      // while also selecting the page, and Cmd+S skips one on the way to a save dialog. `a` and
      // `s` are the two writes here and the only route back from either is a toast that expires,
      // so the shortcut that must never fire by accident is exactly the one a text-selection
      // reflex produces. Shift needs no guard: it yields "A"/"S", which match no case below.
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const id = Number(target.dataset["rowId"]);
      const index = rows.findIndex((row) => row.posting_id === id);
      const row = rows[index];
      if (row === undefined) return;

      const move = (next: number) => {
        const target_ = rows[Math.max(0, Math.min(rows.length - 1, next))];
        if (target_ === undefined) return;
        event.preventDefault();
        onActivate(target_.posting_id);
        const element = event.currentTarget.querySelector<HTMLElement>(
          `[data-row-id="${String(target_.posting_id)}"]`,
        );
        element?.focus();
      };

      switch (event.key) {
        case "ArrowDown":
        case "j":
          return move(index + 1);
        case "ArrowUp":
        case "k":
          return move(index - 1);
        case "Home":
          return move(0);
        case "End":
          return move(rows.length - 1);
        case "Enter":
          event.preventDefault();
          return onSelect(row);
        // The three ACTING keys refuse auto-repeat, and the navigation keys above deliberately
        // allow it — holding `j` to run down the list is the point. Held `a` is not: the row
        // leaves the list, focus lands on its successor after the collapse, and the next repeat
        // marks THAT lead applied, walking a write down the queue for as long as the key is
        // down. Idempotency at the API is no defence, because every repeat hits a different
        // posting. Held `o` opens a browser tab per repeat.
        case "o":
          event.preventDefault();
          if (event.repeat) return;
          return onOpenApply(row);
        case "a":
          event.preventDefault();
          if (event.repeat) return;
          return onApplied(row);
        case "s":
          event.preventDefault();
          if (event.repeat) return;
          return onSkip(row);
        /*
         * SELECTION, not a write — so unlike `a`/`s`/`r` the row stays put and nothing is
         * recoverable-by-toast here. Auto-repeat is still refused: a held `x` flips one boolean
         * as fast as the key repeats, so where it lands is decided by the parity of a repeat
         * count nobody counted.
         *
         * `X` is the shifted key, which is why the modifier guard above deliberately does not
         * cover Shift. Cmd+X is still the browser's cut, refused up there with Cmd+A.
         */
        case "x":
        case "X":
          if (selection === undefined) return;
          event.preventDefault();
          if (event.repeat) return;
          if (event.shiftKey && anchor.current !== null) {
            const from = rows.findIndex((r) => r.posting_id === anchor.current);
            if (from === -1) return;
            const [lo, hi] = from <= index ? [from, index] : [index, from];
            return selection.onMarkMany(
              rows.slice(lo, hi + 1).map((r) => r.posting_id),
              true,
            );
          }
          anchor.current = row.posting_id;
          return selection.onMark(row.posting_id);
        /*
         * `f` opens the pane and puts the cursor in its date input. It deliberately writes
         * NOTHING: every other acting key here has one obvious value to write and this one does
         * not — a blind "+7 days" would be a guess, and the only undo is a toast that expires.
         * So the keystroke buys the reader the control, and the control takes the date.
         *
         * Auto-repeat is refused like every other acting key: a held `f` would re-open and
         * re-focus on every repeat, stealing the cursor back out of the input it just gave it.
         */
        case "f":
          event.preventDefault();
          if (event.repeat) return;
          return onFollowUp(row);
        // Refuses auto-repeat for the same reason `a` and `s` do: the row leaves the list on the
        // first press, so a held `r` would walk a report down the queue onto its successors.
        case "r":
          event.preventDefault();
          if (event.repeat) return;
          return onReport(row);
        // SELECTION, like `x`: it writes nothing, so a mis-press costs a Clear, not an undo.
        case "c":
          if (selection === undefined || onSelectCompany === undefined) return;
          event.preventDefault();
          if (event.repeat) return;
          return onSelectCompany(row);
        default:
          return;
      }
    },
    [
      rows,
      onActivate,
      onSelect,
      onOpenApply,
      onApplied,
      onSkip,
      onReport,
      onFollowUp,
      selection,
      onSelectCompany,
    ],
  );

  return (
    <div
      role="grid"
      aria-label={label}
      aria-rowcount={rows.length + (selection === undefined ? 0 : 1)}
      onKeyDown={onKeyDown}
      className="@container overflow-hidden rounded-md bg-surface shadow-card"
    >
      {/* Only where a bulk selection exists. The one header this list has: "select all" over the
          rows it is currently showing, never the whole lane behind the filter. */}
      {selection === undefined ? null : (
        <div role="rowgroup">
          <div role="row" className="flex items-center gap-3 border-b border-divider px-4 py-1.5">
            <SelectAll rows={rows} selection={selection} />
            <span role="columnheader" className="text-[0.8125rem] text-fg-3">
              Select all {rows.length.toLocaleString()} shown
            </span>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        // Still a row and a cell: a bare `<p>` is not a permitted child of `role="grid"`, and an
        // empty state that falls out of the accessibility tree is the one a reader most needs.
        <div role="rowgroup">
          <div role="row">
            <p role="gridcell" className="mx-auto max-w-[68ch] px-4 py-10 text-center text-sm text-fg-2">
              No job matches. {emptyHint}
            </p>
          </div>
        </div>
      ) : (
        <div role="rowgroup">
          {rows.map((row) => (
            <QueueRowItem
              key={row.posting_id}
              row={row}
              selected={selectedId === row.posting_id}
              active={stopId === row.posting_id}
              collapsing={collapsing.has(row.posting_id)}
              {...(selection === undefined
                ? {}
                : {
                    marked: selection.marked.has(row.posting_id),
                    onMark: () => {
                      anchor.current = row.posting_id;
                      selection.onMark(row.posting_id);
                    },
                  })}
              onSelect={() => {
                onActivate(row.posting_id);
                onSelect(row);
              }}
              similar={similarOf?.(row)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
