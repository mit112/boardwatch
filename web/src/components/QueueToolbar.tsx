/*
 * The filters above the job list.
 *
 * The three controls a person reaches for first — a search, a place, a work arrangement — are in
 * the first row and always visible. Everything else (the job board, the score floor, the three
 * "hide" switches, saved views) sits behind ONE "More filters" disclosure, which says in its own
 * label how many of them are on, so a hidden filter can never be silently narrowing the list.
 *
 * When anything is filtering, a single sentence names every active filter and ends in a Reset
 * button. That sentence is the only place filters are listed, and it is announced politely, so the
 * way back out of an empty list is always on the page.
 */

import type { ReactNode } from "react";

import type { SortState } from "../lib/sort";
import { Icon } from "./Icon";

/** Named so the `/` shortcut can reach it without threading a ref through two components. */
export const FILTER_INPUT_ID = "queue-filter";

const FIELD =
  "min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2";

function Key({ children }: { children: string }) {
  return (
    <kbd className="rounded-sm border border-control bg-surface px-1.5 font-sans text-[11px] text-fg-2">
      {children}
    </kbd>
  );
}

/*
 * The bulk bar. It exists ONLY while at least one row is selected — a selection column and an
 * action bar that are always drawn cost every single-row visit some clarity, and there is no
 * "0 selected" state to read.
 *
 * No confirmation dialog, deliberately: skip is cheaply reversible and the toast's Undo is the
 * route back, which is the same bargain the single-row skip already makes.
 *
 * Both accessible names START with the visible label (SC 2.5.3 Label in Name) before naming what
 * the control does to the count.
 */
function BulkBar({
  count,
  onSkip,
  onClear,
}: {
  count: number;
  onSkip: () => void;
  onClear: () => void;
}) {
  const leads = `${count.toLocaleString()} ${count === 1 ? "job" : "jobs"}`;
  return (
    <div
      role="group"
      aria-label="Bulk actions"
      className="flex flex-wrap items-center gap-3 rounded-sm bg-surface-3 px-3 py-1.5"
    >
      <span className="text-sm text-fg tabular-nums">{count.toLocaleString()} selected</span>
      <button
        type="button"
        onClick={onSkip}
        aria-label={`Skip ${count.toLocaleString()} selected ${count === 1 ? "job" : "jobs"}`}
        title="Skip every selected job. One write, undoable from the toast."
        className="min-h-11 rounded-sm bg-surface px-3 text-sm text-fg shadow-card transition-colors duration-150 ease-in-out hover:bg-surface-2"
      >
        Skip {count.toLocaleString()}
      </button>
      <button
        type="button"
        onClick={onClear}
        aria-label={`Clear the selection of ${leads}`}
        className="min-h-11 rounded-sm px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg"
      >
        Clear
      </button>
    </div>
  );
}

/** The sort choices, in the words of what the order is for. Each maps to the page's own
 *  `SortState`, so a stored sort and the control can never disagree about what is selected. */
const SORT_CHOICES: readonly { label: string; sort: SortState }[] = [
  { label: "Default order", sort: { key: "rank", direction: "asc" } },
  { label: "Newest posted", sort: { key: "age", direction: "asc" } },
  { label: "Company A–Z", sort: { key: "company", direction: "asc" } },
  { label: "Title A–Z", sort: { key: "title", direction: "asc" } },
  { label: "Location A–Z", sort: { key: "location", direction: "asc" } },
  { label: "Job board", sort: { key: "provider", direction: "asc" } },
  { label: "Follow-up date", sort: { key: "follow_up", direction: "asc" } },
  { label: "Ranking score, high to low", sort: { key: "score", direction: "desc" } },
  { label: "Résumé keyword match, high to low", sort: { key: "coverage", direction: "desc" } },
];

const encode = (sort: SortState): string => `${sort.key}:${sort.direction}`;

export function QueueToolbar({
  query,
  onQuery,
  location,
  onLocation,
  mode,
  onMode,
  modes,
  sort,
  onSort,
  board,
  onBoard,
  boards,
  minScore,
  onMinScore,
  hideThin,
  onHideThin,
  hideUnverifiable,
  onHideUnverifiable,
  hideSimilar,
  onHideSimilar,
  views,
  moreActive,
  activeFilters,
  onReset,
  selectedCount,
  onSkipSelected,
  onClearSelection,
}: {
  query: string;
  onQuery: (value: string) => void;
  location: string;
  onLocation: (value: string) => void;
  mode: string;
  onMode: (value: string) => void;
  modes: readonly (readonly [string, number])[];
  sort: SortState;
  onSort: (sort: SortState) => void;
  board: string;
  onBoard: (value: string) => void;
  boards: readonly (readonly [string, number])[];
  minScore: string;
  onMinScore: (value: string) => void;
  hideThin: boolean;
  onHideThin: (on: boolean) => void;
  hideUnverifiable: boolean;
  onHideUnverifiable: (on: boolean) => void;
  hideSimilar: boolean;
  onHideSimilar: (on: boolean) => void;
  /** The saved-views control, inside "More filters". */
  views?: ReactNode;
  /** How many of the filters behind "More filters" are on. */
  moreActive: number;
  /** Every active filter in words. Empty when nothing is filtering. */
  activeFilters: readonly string[];
  onReset: () => void;
  selectedCount: number;
  onSkipSelected: () => void;
  onClearSelection: () => void;
}) {
  const known = SORT_CHOICES.some((choice) => encode(choice.sort) === encode(sort));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-56 flex-[2_1_16rem] flex-col gap-1">
          <span className="label-micro text-fg-2">Search</span>
          <span className="relative">
            <Icon
              name="search"
              className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-3"
            />
            <input
              id={FILTER_INPUT_ID}
              type="search"
              value={query}
              onChange={(event) => {
                onQuery(event.target.value);
              }}
              placeholder="Company, title or place"
              className={`${FIELD} w-full pl-9`}
            />
          </span>
        </label>
        <label className="flex min-w-40 flex-[1_1_10rem] flex-col gap-1">
          <span className="label-micro text-fg-2">Location</span>
          <input
            type="search"
            value={location}
            onChange={(event) => {
              onLocation(event.target.value);
            }}
            placeholder="e.g. Boston"
            className={FIELD}
          />
        </label>
        <label className="flex w-40 flex-col gap-1">
          <span className="label-micro text-fg-2">Work arrangement</span>
          <select
            value={mode}
            onChange={(event) => {
              onMode(event.target.value);
            }}
            className={FIELD}
          >
            <option value="">Any</option>
            {modes.map(([name, count]) => (
              <option key={name} value={name}>
                {name} ({count.toLocaleString()})
              </option>
            ))}
          </select>
        </label>
        <label className="flex w-48 flex-col gap-1">
          <span className="label-micro text-fg-2">Sort by</span>
          <select
            value={encode(sort)}
            onChange={(event) => {
              const next = SORT_CHOICES.find((choice) => encode(choice.sort) === event.target.value);
              if (next !== undefined) onSort(next.sort);
            }}
            className={FIELD}
          >
            {known ? null : (
              <option value={encode(sort)}>{`${sort.key} (${sort.direction === "asc" ? "ascending" : "descending"})`}</option>
            )}
            {SORT_CHOICES.map((choice) => (
              <option key={encode(choice.sort)} value={encode(choice.sort)}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <details className="group rounded-sm">
        <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-sm px-1 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg [&::-webkit-details-marker]:hidden">
          <Icon name="filter" />
          More filters
          {moreActive === 0 ? null : (
            <span className="rounded-full bg-surface-3 px-2 text-xs text-fg tabular-nums">
              {moreActive} on
            </span>
          )}
          <Icon name="chevronDown" size={14} className="transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-2 flex flex-col gap-3 rounded-md bg-surface-2 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex w-48 flex-col gap-1">
              <span className="label-micro text-fg-2">Job board</span>
              <select
                value={board}
                onChange={(event) => {
                  onBoard(event.target.value);
                }}
                className={FIELD}
              >
                <option value="">All boards</option>
                {boards.map(([name, count]) => (
                  <option key={name} value={name}>
                    {name} ({count.toLocaleString()})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex w-48 flex-col gap-1">
              <span className="label-micro text-fg-2">Minimum ranking score</span>
              <input
                type="number"
                inputMode="decimal"
                step="1"
                min="0"
                value={minScore}
                onChange={(event) => {
                  onMinScore(event.target.value);
                }}
                placeholder="Any"
                title="The ranking score only orders the list. It is not a chance of being hired or proof you qualify."
                className={`${FIELD} tabular-nums`}
              />
            </label>
            {views === undefined ? null : <div className="ml-auto">{views}</div>}
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-fg-2">
            <label className="flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                checked={hideThin}
                onChange={(event) => {
                  onHideThin(event.target.checked);
                }}
              />
              Hide very short descriptions
            </label>
            <label className="flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                checked={hideUnverifiable}
                onChange={(event) => {
                  onHideUnverifiable(event.target.checked);
                }}
              />
              Hide postings I can’t verify are open
            </label>
            <label
              className="flex min-h-11 items-center gap-2"
              title="Show one job per company and title — the best-placed one — and fold the rest of the group under it. Each folded posting stays one click away from that job's workspace."
            >
              <input
                type="checkbox"
                checked={hideSimilar}
                onChange={(event) => {
                  onHideSimilar(event.target.checked);
                }}
              />
              Collapse similar roles
            </label>
          </div>
        </div>
      </details>

      {activeFilters.length === 0 ? null : (
        <p role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-2">
          <span>Filtering by {activeFilters.join(", ")}.</span>
          <button
            type="button"
            onClick={onReset}
            className="inline-flex min-h-11 items-center rounded-sm px-2 text-sm font-medium text-accent underline underline-offset-4 transition-colors duration-150 ease-in-out hover:text-fg"
          >
            Reset filters
          </button>
        </p>
      )}

      {selectedCount === 0 ? null : (
        <BulkBar count={selectedCount} onSkip={onSkipSelected} onClear={onClearSelection} />
      )}

      {/*
        * Shortcuts, folded. Every key has a visible button equivalent in the workspace, so this is
        * an accelerator rather than the only route — but a queue worked at speed every day is
        * exactly where an undiscovered accelerator is a wasted one, so it is one click away rather
        * than gone. Hidden under `(hover: none)`: a touch device has no keyboard to press them on.
        */}
      <details className="text-xs text-fg-3 [@media(hover:none)]:hidden">
        <summary className="inline-flex min-h-8 cursor-pointer items-center rounded-sm px-1 hover:text-fg-2">
          Keyboard shortcuts
        </summary>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span>
            <Key>/</Key> search
          </span>
          <span>
            <Key>Tab</Key> list
          </span>
          <span>
            <Key>↑</Key> <Key>↓</Key> move
          </span>
          <span>
            <Key>Enter</Key> open
          </span>
          <span>
            <Key>o</Key> open application
          </span>
          <span>
            <Key>a</Key> record application
          </span>
          <span>
            <Key>s</Key> skip
          </span>
          <span>
            <Key>x</Key> select
          </span>
          <span>
            <Key>c</Key> select company
          </span>
          <span>
            <Key>r</Key> report
          </span>
          <span>
            <Key>Esc</Key> close
          </span>
        </p>
      </details>
    </div>
  );
}
