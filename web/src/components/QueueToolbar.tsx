/*
 * At roughly 540 entries growing by about 230 a day, neither of these controls is optional: today's
 * lead set alone contains twelve same-company-same-title duplicate groups covering 28 rows.
 */
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
    <div className="flex flex-wrap items-end gap-4">
      <label className="flex min-w-64 flex-1 flex-col gap-1.5">
        <span className="text-[11px] tracking-wide text-fg-3 uppercase">
          Filter company, title, location
        </span>
        <input
          type="search"
          value={query}
          onChange={(event) => {
            onQuery(event.target.value);
          }}
          placeholder="e.g. intel, backend, boston"
          className="min-h-11 rounded border border-control bg-surface px-3 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
        />
      </label>
      <label className="flex w-40 flex-col gap-1.5">
        <span className="text-[11px] tracking-wide text-fg-3 uppercase">Minimum score</span>
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
          className="min-h-11 rounded border border-control bg-surface px-3 text-sm text-fg tabular-nums placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
        />
      </label>
    </div>
  );
}
