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
      {/* Normal emphasis, not strong: this is "not known", not a veto and not bad news. */}
      {row.status === "unverifiable" ? (
        <Badge
          label="unverifiable"
          reason="Nothing enumerates this company's board, so the posting cannot be confirmed still open."
        />
      ) : null}
    </>
  );
}

/*
 * `tabIndex={-1}`, always, and that is deliberate — see `QueueTable`. The row is the tab stop; a
 * per-row button that were also one would put four stops on every row, which measured 1,399 on a
 * 347-lead queue. Every one of these has a single-key equivalent on the focused row, so nothing
 * here is mouse-only.
 */
function RowAction({
  label,
  hint,
  onClick,
  title,
}: {
  label: string;
  hint: string;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      tabIndex={-1}
      onClick={onClick}
      aria-label={hint}
      {...(title ? { title } : {})}
      className="min-h-8 rounded border border-control px-2.5 text-xs text-fg-2 transition-colors duration-[120ms] ease-snap hover:border-fg-2 hover:text-fg"
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
  active,
  collapsing,
  onSelect,
  onApplied,
  onSkip,
}: {
  row: QueueRow;
  rank: number;
  selected: boolean;
  /** Carries the roving tab stop. Exactly one row per table is `true`. */
  active: boolean;
  collapsing: boolean;
  onSelect: () => void;
  onApplied: () => void;
  onSkip: () => void;
}) {
  const where = row.location ?? EM_DASH;
  const named = `${row.title} at ${row.company}`;
  return (
    <div
      role="presentation"
      className={`grid overflow-hidden transition-[grid-template-rows,opacity] duration-200 ease-in-out ${
        collapsing ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100"
      }`}
      aria-hidden={collapsing}
    >
      <div role="presentation" className="min-h-0">
        <div
          role="row"
          data-row-id={row.posting_id}
          tabIndex={active ? 0 : -1}
          aria-selected={selected}
          className={`grid ${GRID_TEMPLATE} min-h-9 cursor-default items-center gap-3 border-b border-divider px-3 transition-colors duration-[120ms] ease-snap focus-visible:outline-offset-[-2px] ${
            selected
              ? "bg-surface-2 shadow-[inset_2px_0_0_0_var(--color-accent)]"
              : "hover:bg-surface-2/60"
          }`}
          onClick={onSelect}
        >
          <span role="gridcell" className={`${WIDE_ONLY} text-sm text-fg-3 tabular-nums`}>
            {rank}
          </span>

          <div role="gridcell" className="min-w-0">
            {/* Title AND company are inside the button, which gives the control an accessible
                name that names the employer. `title` on both, because either can truncate and a
                truncated value with no way to read it in full is information destroyed. */}
            <button
              type="button"
              tabIndex={-1}
              onClick={(event) => {
                event.stopPropagation();
                onSelect();
              }}
              className="flex min-h-9 w-full flex-col justify-center text-left leading-tight transition-colors duration-[120ms] ease-snap hover:text-accent"
            >
              <span className="max-w-full truncate text-sm text-fg" title={row.title}>
                {row.title}
              </span>
              <span className="max-w-full truncate text-xs text-fg-2" title={row.company}>
                {row.company}
              </span>
            </button>
            {/* Narrow tier only: everything the collapsed columns were carrying. */}
            <span className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3 @min-[78rem]:hidden">
              <span className="tabular-nums">#{rank}</span>
              <span>{where}</span>
              <span>{row.remote_policy ?? EM_DASH}</span>
              <span className="tabular-nums">{formatAge(row.posted_days)}</span>
              <span className="tabular-nums">cov {formatFraction(row.coverage)}</span>
              <Flags row={row} />
            </span>
          </div>

          <div role="gridcell" className={`${WIDE_ONLY} min-w-0 leading-tight`}>
            <span className="block truncate text-sm text-fg-2" title={where}>
              {where}
            </span>
            <span className="block truncate text-xs text-fg-3">
              {row.remote_policy ?? EM_DASH}
            </span>
          </div>

          <span
            role="gridcell"
            className={`${WIDE_ONLY} text-right text-sm text-fg-2 tabular-nums`}
            title="Age from the board's published date."
          >
            {formatAge(row.posted_days)}
          </span>

          <span
            role="gridcell"
            className="text-right text-sm text-fg tabular-nums"
            title="Score, as of now."
          >
            {formatScore(row.score)}
          </span>

          <span role="gridcell" className="justify-self-start">
            <VerdictChip verdict={row.verdict} />
          </span>

          <div role="gridcell" className="hidden flex-wrap items-center gap-1.5 @min-[78rem]:flex">
            <span
              className="w-11 text-right text-xs text-fg-2 tabular-nums"
              title="Résumé keyword coverage, as of now."
            >
              {formatFraction(row.coverage)}
            </span>
            <Flags row={row} />
          </div>

          <div
            role="gridcell"
            className="hidden items-center justify-end gap-1.5 @min-[78rem]:flex"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            {/*
              * `Apply` opens a third-party board; `Applied` writes an application record that the
              * contract has no route to reverse. They were adjacent, identical grey pills whose
              * labels differ by two characters, 347 times down one page. So `Apply` now carries
              * the row's emphasis and the two marking actions sit behind a rule — the misclick
              * this prevents is the expensive one.
              */}
            <ApplyLink url={row.apply_url} compact emphasis label={named} />
            <span className="flex items-center gap-1.5 border-l border-divider pl-2">
              <RowAction
                label="Applied"
                hint={`Mark applied: ${named}`}
                onClick={onApplied}
                title="Mark this job as applied. Key: a"
              />
              <RowAction
                label="Skip"
                hint={`Skip: ${named}`}
                onClick={onSkip}
                title="Skip this lead. Key: s"
              />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
