import { useCallback } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import type { QueueRow } from "../api/types";
import type { SortKey, SortState } from "../lib/sort";
import { GRID_TEMPLATE, QueueRowItem, WIDE_ONLY } from "./QueueRowItem";

function SortButton({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (key: SortKey) => void;
}) {
  const active = sort.key === sortKey;
  return (
    <button
      type="button"
      onClick={() => {
        onSort(sortKey);
      }}
      title={`Sort by ${label}`}
      className={`inline-flex min-h-11 min-w-11 items-center gap-1 rounded-sm px-1 label-micro transition-colors duration-[120ms] ease-snap ${
        active ? "text-fg" : "text-fg-3 hover:text-fg-2"
      }`}
    >
      {label}
      {/*
        * The glyph is always drawn, dimmed when the column is not the one sorting. It used to be
        * `opacity-0`, which meant an unsorted header carried NO signal that it could be sorted at
        * all — the affordance existed only for the column you had already found.
        */}
      <span aria-hidden="true" className={active ? "" : "opacity-50"}>
        {active ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}
      </span>
    </button>
  );
}

function ariaSort(sort: SortState, ...keys: SortKey[]): "ascending" | "descending" | "none" {
  // VARIADIC because one columnheader can carry more than one sort control: title and company
  // share a cell. Keyed on `title` alone, sorting by company left EVERY header reading
  // `aria-sort="none"` while the list was in fact sorted — a screen reader was told the table
  // was unsorted by the same markup that had just re-ordered it.
  if (!keys.includes(sort.key)) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
}

/*
 * A `role="grid"` whose focusable unit is the ROW, which the ARIA practices allow for a collection
 * the reader works down rather than cell by cell — and which this list needs, because the previous
 * markup had two defects that compound.
 *
 * SEMANTICS. `role="row"` and eight `role="columnheader"` were emitted with no `role="grid"` or
 * `role="rowgroup"` above them and no row or cell role on any of the 347 data rows. An orphaned
 * columnheader is dropped by assistive tech, so every `aria-sort` this component set was announced
 * to nothing and the table read as an undifferentiated wall of buttons.
 *
 * TAB STOPS. Four focusable controls per row measured **1,399 tab stops** on one queue page.
 * Nothing below the list — the review lane, the detail pane — was reachable by keyboard in any
 * practical sense. So the tab stop is the row, exactly one per table (roving `tabIndex`), and the
 * per-row controls opt out with `tabIndex={-1}`. Every one of them keeps a single-key equivalent
 * on the focused row, so this removes tab stops WITHOUT removing keyboard access to anything:
 *
 *   ↓ / j   next row          Enter   open the detail pane
 *   ↑ / k   previous row      o       open the apply link
 *   Home    first row         a       mark applied
 *   End     last row          s       skip
 *
 * The keys are handled HERE, on the grid, not on `window`: `a` and `s` write, and a global
 * listener would fire them while the reader was typing a company name into the filter box.
 */
export function QueueTable({
  label,
  rows,
  rankOf,
  sort,
  onSort,
  selectedId,
  activeId,
  onActivate,
  collapsing,
  onSelect,
  onOpenApply,
  onApplied,
  onSkip,
  emptyHint = "Clear the text box or lower the minimum score.",
}: {
  label: string;
  rows: QueueRow[];
  rankOf: (row: QueueRow) => number;
  sort: SortState;
  onSort: (key: SortKey) => void;
  selectedId: number | null;
  activeId: number | null;
  onActivate: (postingId: number) => void;
  collapsing: ReadonlySet<number>;
  onSelect: (row: QueueRow) => void;
  onOpenApply: (row: QueueRow) => void;
  onApplied: (row: QueueRow) => void;
  onSkip: (row: QueueRow) => void;
  /* Names the levers that would bring rows back. A verdict facet is a lever the two default
     sentences do not mention, so the empty state must say so or it points at the wrong control. */
  emptyHint?: string;
}) {
  // The roving stop. When the cursor is on a row of the OTHER table — or on none — the first row
  // holds it, so the grid is always reachable in one Tab and never becomes a dead region.
  const activeIndex = rows.findIndex((row) => row.posting_id === activeId);
  const stopId = (activeIndex === -1 ? rows[0]?.posting_id : activeId) ?? null;

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
        default:
          return;
      }
    },
    [rows, onActivate, onSelect, onOpenApply, onApplied, onSkip],
  );

  return (
    <div
      role="grid"
      aria-label={label}
      aria-rowcount={rows.length + 1}
      onKeyDown={onKeyDown}
      className="@container rounded-md bg-surface shadow-[0_1px_0_0_var(--color-divider)_inset,0_16px_40px_-24px_rgb(0_0_0/0.9)]"
    >
      {/*
        * Sticky, below the app header. Past roughly row twelve the score, verdict and coverage
        * columns were three unlabelled numbers; on a 347-row list that is most of the list.
        * The background is opaque so rows do not bleed through it.
        *
        * The stickiness lives on the ROWGROUP, not on the row inside it. A sticky element is
        * clipped by its own parent's box, and a rowgroup wrapping only the header row is exactly
        * as tall as that row — so the header unpinned and scrolled away the moment the first data
        * row passed it, which is the failure this was added to fix.
        */}
      <div role="rowgroup" className="sticky top-header z-10">
        <div
          role="row"
          className={`grid ${GRID_TEMPLATE} items-center gap-3 rounded-t-md border-b border-divider bg-surface px-4`}
        >
          <span role="columnheader" aria-sort={ariaSort(sort, "rank")} className={WIDE_ONLY}>
            <SortButton label="#" sortKey="rank" sort={sort} onSort={onSort} />
          </span>
          <span
            role="columnheader"
            aria-sort={ariaSort(sort, "title", "company")}
            className="flex items-center gap-2"
          >
            <SortButton label="title" sortKey="title" sort={sort} onSort={onSort} />
            <span aria-hidden="true" className="text-divider">
              |
            </span>
            <SortButton label="company" sortKey="company" sort={sort} onSort={onSort} />
          </span>
          <span role="columnheader" aria-sort={ariaSort(sort, "location")} className={WIDE_ONLY}>
            <SortButton label="location · remote" sortKey="location" sort={sort} onSort={onSort} />
          </span>
          <span
            role="columnheader"
            aria-sort={ariaSort(sort, "age")}
            className={`${WIDE_ONLY} justify-self-end`}
          >
            <SortButton label="age" sortKey="age" sort={sort} onSort={onSort} />
          </span>
          <span role="columnheader" aria-sort={ariaSort(sort, "score")} className="justify-self-end">
            <SortButton label="score" sortKey="score" sort={sort} onSort={onSort} />
          </span>
          <span role="columnheader" className="px-1 label-micro text-fg-3">
            verdict
          </span>
          <span role="columnheader" aria-sort={ariaSort(sort, "coverage")} className={WIDE_ONLY}>
            <SortButton label="coverage · flags" sortKey="coverage" sort={sort} onSort={onSort} />
          </span>
          <span
            role="columnheader"
            className={`${WIDE_ONLY} px-1 text-right label-micro text-fg-3`}
          >
            actions
          </span>
        </div>
      </div>

      {rows.length === 0 ? (
        // Still a row and a cell: a bare `<p>` is not a permitted child of `role="grid"`, and an
        // empty state that falls out of the accessibility tree is the one a reader most needs.
        <div role="rowgroup">
          <div role="row">
            <p role="gridcell" className="px-4 py-10 text-center text-sm text-fg-2">
              No lead matches this filter. {emptyHint}
            </p>
          </div>
        </div>
      ) : (
        <div role="rowgroup">
          {rows.map((row) => (
            <QueueRowItem
              key={row.posting_id}
              row={row}
              rank={rankOf(row)}
              selected={selectedId === row.posting_id}
              active={stopId === row.posting_id}
              collapsing={collapsing.has(row.posting_id)}
              onSelect={() => {
                onActivate(row.posting_id);
                onSelect(row);
              }}
              onApplied={() => {
                onApplied(row);
              }}
              onSkip={() => {
                onSkip(row);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
