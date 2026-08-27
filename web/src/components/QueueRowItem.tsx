import type { QueueRow } from "../api/types";
import { EM_DASH, formatAge, formatFraction, formatScore } from "../lib/format";
import { ApplyLink } from "./ApplyLink";
import { Badge } from "./Badge";
import { VerdictChip } from "./VerdictChip";

/*
 * Every row is its own grid, so EVERY track has to resolve to the same width in every row or the
 * columns jitter row to row — which destroys the one thing a row layout buys over cards, the
 * ability to compare eight jobs at once. So no `auto` and no content-based minimum appears here:
 * the flexible tracks are `minmax(0,Nfr)` over free space that is identical on every row, and
 * every other track is a fixed length.
 *
 * Two tiers, driven by a CONTAINER query rather than the viewport, because the list also narrows
 * when the detail pane opens — and a viewport breakpoint cannot see that. On the narrow tier the
 * rank, location, age, flags and per-row actions collapse into the title cell's meta line; the
 * detail pane carries the actions there.
 */
/*
 * The wide tier's fixed tracks total 45rem; below roughly 78rem of CONTAINER width there is not
 * enough left for a title and a location to be readable rather than truncated, so that is where
 * the tiers switch. Measured, not guessed: at 64rem the eight-column layout left the title 234px
 * and every row read "Software E…".
 */
export const GRID_TEMPLATE =
  "grid-cols-[minmax(0,1fr)_4.5rem_7.5rem] " +
  "@min-[78rem]:grid-cols-[3rem_minmax(0,2.4fr)_minmax(0,1.2fr)_4rem_4.5rem_7.5rem_13rem_13rem]";

export const WIDE_ONLY = "hidden @min-[78rem]:block";

function Flags({ row }: { row: QueueRow }) {
  return (
    <>
      {row.thin_jd ? (
        <Badge label="thin JD" reason="No coverage fraction could be computed." />
      ) : null}
      {row.off_target ? <Badge label="off target" reason={row.off_target_reason} /> : null}
      {row.status === "closed" ? (
        <Badge
          label="closed"
          emphasis="strong"
          reason="The posting is no longer open on the board."
        />
      ) : null}
    </>
  );
}

function RowAction({
  label,
  onClick,
  title,
}: {
  label: string;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      {...(title ? { title } : {})}
      className="min-h-11 rounded border border-control px-2.5 text-xs text-fg-2 transition-colors duration-[120ms] ease-snap hover:border-fg-2 hover:text-fg"
    >
      {label}
    </button>
  );
}

/*
 * Rows, not cards. Apply, Mark applied and Skip live HERE as well as in the detail pane: requiring
 * a pane-open per lead costs one extra action multiplied by the size of the queue.
 */
export function QueueRowItem({
  row,
  rank,
  selected,
  collapsing,
  onSelect,
  onApplied,
  onSkip,
}: {
  row: QueueRow;
  rank: number;
  selected: boolean;
  collapsing: boolean;
  onSelect: () => void;
  onApplied: () => void;
  onSkip: () => void;
}) {
  return (
    <div
      className={`grid overflow-hidden transition-[grid-template-rows,opacity] duration-200 ease-in-out ${
        collapsing ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100"
      }`}
      aria-hidden={collapsing}
    >
      <div className="min-h-0">
        <div
          className={`grid ${GRID_TEMPLATE} items-center gap-3 border-b border-divider px-3 transition-colors duration-[120ms] ease-snap ${
            selected
              ? "bg-surface-2 shadow-[inset_2px_0_0_0_var(--color-accent)]"
              : "hover:bg-surface"
          }`}
          onClick={onSelect}
        >
          <span className={`${WIDE_ONLY} text-sm text-fg-3 tabular-nums`}>{rank}</span>

          <div className="min-w-0 py-1">
            {/* Title AND company are inside the button, which makes the target 44px tall without
                a spacer and gives the control an accessible name that names the employer. */}
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onSelect();
              }}
              className="flex min-h-11 w-full flex-col justify-center text-left transition-colors duration-[120ms] ease-snap hover:text-accent"
            >
              <span className="max-w-full truncate text-sm text-fg">{row.title}</span>
              <span className="max-w-full truncate text-xs text-fg-2">{row.company}</span>
            </button>
            {/* Narrow tier only: everything the collapsed columns were carrying. */}
            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3 @min-[78rem]:hidden">
              <span className="tabular-nums">#{rank}</span>
              <span>{row.location ?? EM_DASH}</span>
              <span>{row.remote_policy ?? EM_DASH}</span>
              <span className="tabular-nums">{formatAge(row.posted_days)}</span>
              <span className="tabular-nums">cov {formatFraction(row.coverage)}</span>
              <Flags row={row} />
            </span>
          </div>

          <div className={`${WIDE_ONLY} min-w-0`}>
            <span className="block truncate text-sm text-fg-2">{row.location ?? EM_DASH}</span>
            <span className="block truncate text-xs text-fg-3">
              {row.remote_policy ?? EM_DASH}
            </span>
          </div>

          <span
            className={`${WIDE_ONLY} text-right text-sm text-fg-2 tabular-nums`}
            title="Age from the board's published date."
          >
            {formatAge(row.posted_days)}
          </span>

          <span className="text-right text-sm text-fg tabular-nums" title="Score, as of now.">
            {formatScore(row.score)}
          </span>

          <span className="justify-self-start">
            <VerdictChip verdict={row.verdict} />
          </span>

          <div className="hidden flex-wrap items-center gap-1.5 @min-[78rem]:flex">
            <span
              className="text-xs text-fg-2 tabular-nums"
              title="Résumé keyword coverage, as of now."
            >
              cov {formatFraction(row.coverage)}
            </span>
            <Flags row={row} />
          </div>

          <div
            className="hidden items-center justify-end gap-1.5 @min-[78rem]:flex"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <ApplyLink url={row.apply_url} compact />
            <RowAction label="Applied" onClick={onApplied} title="Mark this job as applied." />
            <RowAction label="Skip" onClick={onSkip} title="Skip this lead." />
          </div>
        </div>
      </div>
    </div>
  );
}
