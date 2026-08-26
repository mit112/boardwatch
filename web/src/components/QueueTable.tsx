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
      className={`inline-flex min-h-11 min-w-11 items-center gap-1 rounded px-1 text-[11px] tracking-wide uppercase transition-colors duration-[120ms] ease-snap ${
        active ? "text-fg" : "text-fg-3 hover:text-fg-2"
      }`}
    >
      {label}
      <span aria-hidden="true" className={active ? "opacity-100" : "opacity-0"}>
        {sort.direction === "asc" ? "↑" : "↓"}
      </span>
    </button>
  );
}

function ariaSort(sort: SortState, key: SortKey): "ascending" | "descending" | "none" {
  if (sort.key !== key) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
}

export function QueueTable({
  rows,
  rankOf,
  sort,
  onSort,
  selectedId,
  collapsing,
  onSelect,
  onApplied,
  onSkip,
}: {
  rows: QueueRow[];
  rankOf: (row: QueueRow) => number;
  sort: SortState;
  onSort: (key: SortKey) => void;
  selectedId: number | null;
  collapsing: ReadonlySet<number>;
  onSelect: (row: QueueRow) => void;
  onApplied: (row: QueueRow) => void;
  onSkip: (row: QueueRow) => void;
}) {
  return (
    <div className="@container rounded border border-divider bg-surface">
      <div
        role="row"
        className={`grid ${GRID_TEMPLATE} items-center gap-3 border-b border-divider px-3`}
      >
        <span role="columnheader" aria-sort={ariaSort(sort, "rank")} className={WIDE_ONLY}>
          <SortButton label="#" sortKey="rank" sort={sort} onSort={onSort} />
        </span>
        <span
          role="columnheader"
          aria-sort={ariaSort(sort, "title")}
          className="flex items-center gap-2"
        >
          <SortButton label="title" sortKey="title" sort={sort} onSort={onSort} />
          <span aria-hidden="true" className="text-divider">
            |
          </span>
          <SortButton label="company" sortKey="company" sort={sort} onSort={onSort} />
        </span>
        <span
          role="columnheader"
          aria-sort={ariaSort(sort, "location")}
          className={WIDE_ONLY}
        >
          <SortButton label="location · remote" sortKey="location" sort={sort} onSort={onSort} />
        </span>
        <span
          role="columnheader"
          aria-sort={ariaSort(sort, "age")}
          className={`${WIDE_ONLY} justify-self-end`}
        >
          <SortButton label="age" sortKey="age" sort={sort} onSort={onSort} />
        </span>
        <span
          role="columnheader"
          aria-sort={ariaSort(sort, "score")}
          className="justify-self-end"
        >
          <SortButton label="score" sortKey="score" sort={sort} onSort={onSort} />
        </span>
        <span role="columnheader" className="px-1 text-[11px] tracking-wide text-fg-3 uppercase">
          verdict
        </span>
        <span
          role="columnheader"
          aria-sort={ariaSort(sort, "coverage")}
          className={WIDE_ONLY}
        >
          <SortButton label="coverage · flags" sortKey="coverage" sort={sort} onSort={onSort} />
        </span>
        <span
          role="columnheader"
          className={`${WIDE_ONLY} px-1 text-right text-[11px] tracking-wide text-fg-3 uppercase`}
        >
          actions
        </span>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-fg-2">
          No lead matches this filter. Clear the text box or lower the minimum score.
        </p>
      ) : (
        rows.map((row) => (
          <QueueRowItem
            key={row.posting_id}
            row={row}
            rank={rankOf(row)}
            selected={selectedId === row.posting_id}
            collapsing={collapsing.has(row.posting_id)}
            onSelect={() => {
              onSelect(row);
            }}
            onApplied={() => {
              onApplied(row);
            }}
            onSkip={() => {
              onSkip(row);
            }}
          />
        ))
      )}
    </div>
  );
}
