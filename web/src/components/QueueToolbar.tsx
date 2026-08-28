/*
 * At roughly 540 entries growing by about 230 a day, neither of these controls is optional: today's
 * lead set alone contains twelve same-company-same-title duplicate groups covering 28 rows.
 */

/** Named so the `/` shortcut can reach it without threading a ref through two components. */
export const FILTER_INPUT_ID = "queue-filter";

function Key({ children }: { children: string }) {
  return (
    <kbd className="rounded-sm border border-control px-1 font-sans text-[11px] text-fg-2">
      {children}
    </kbd>
  );
}

export function QueueToolbar({
  query,
  onQuery,
  minScore,
  onMinScore,
}: {
  query: string;
  onQuery: (value: string) => void;
  minScore: string;
  onMinScore: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex min-w-64 flex-1 flex-col gap-1.5">
          <span className="label-micro text-fg-3">
            Filter company, title, location
          </span>
          <input
            id={FILTER_INPUT_ID}
            type="search"
            value={query}
            onChange={(event) => {
              onQuery(event.target.value);
            }}
            placeholder="e.g. intel, backend, boston"
            className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
          />
        </label>
        <label className="flex w-40 flex-col gap-1.5">
          <span className="label-micro text-fg-3">Minimum score</span>
          <input
            type="number"
            inputMode="decimal"
            step="1"
            min="0"
            value={minScore}
            onChange={(event) => {
              onMinScore(event.target.value);
            }}
            placeholder="any"
            className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg tabular-nums placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
          />
        </label>
      </div>

      {/*
        * Stated, not hidden behind a `?` dialog. Every key here has a visible button equivalent on
        * the row, so this is an accelerator rather than the only route — but a queue worked at
        * speed every morning is exactly the case where an undiscovered accelerator is a wasted
        * one. `Tab` reaches the list in a single stop, by construction: see `QueueTable`.
        */}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-3">
        <span>
          <Key>/</Key> filter
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
          <Key>o</Key> apply link
        </span>
        <span>
          <Key>a</Key> applied
        </span>
        <span>
          <Key>s</Key> skip
        </span>
        <span>
          <Key>Esc</Key> close
        </span>
      </p>
    </div>
  );
}
