import type { QueueRow } from "../api/types";
import { EM_DASH, formatAge, formatFraction, formatScore } from "../lib/format";
import { ApplyLink } from "./ApplyLink";
import { Badge } from "./Badge";
import { ReviewReasonBadge } from "./ReviewReasonBadge";
import { VerdictChip } from "./VerdictChip";

/*
 * The row grid. It buys one thing over cards — the ability to compare eight jobs at once — and
 * that is what the track rules here are protecting.
 *
 * Every row is its own grid, so EVERY track has to resolve to the same width in every row or the
 * columns jitter row to row. So no `auto` and no content-based minimum appears in ANY tier below:
 * the flexible tracks are `minmax(0,Nfr)` over free space that is identical on every row, and
 * every other track is a fixed length.
 *
 * FOUR tiers, driven by a CONTAINER query rather than the viewport, because the list also narrows
 * when the detail pane opens — and a viewport breakpoint cannot see that. Whatever a tier drops
 * reappears in the title cell's meta line, so no tier loses a fact; it only stops being a column.
 *
 * The CONTAINER width each tier is designed for, measured in a browser against the live store:
 *
 *   tier      container      the viewport that produces it              columns added
 *   phone     under 40rem    390 (container 21.4rem)                    title · verdict
 *   narrow    40 – 52rem     a hand-narrowed window                     + score
 *   middle    52 – 78rem     1440 pane open (54rem); 1000, where the    + location · actions
 *                            pane is a sheet and the list is 59.5rem
 *   wide      78rem and up   1440 pane closed (87rem); 2560 pane        + rank · age · coverage
 *                            open (124rem)
 *
 * The MIDDLE tier is the one the audit found missing. `main` used to cap at 110rem, which left the
 * list container 1184px with the pane open on a 2560 display and 864px at 1440 — both under 78rem,
 * so the eight-column tier was unreachable whenever a lead was open and the reader dropped to
 * three columns. The cap is now 160rem (`App.tsx`), which restores the wide tier at 2560; this
 * tier covers 1440.
 *
 * Its fixed tracks total 24.5rem, and with `gap-3` across five columns plus the row's own `px-4`
 * that is 29.5rem of overhead — so at the 54rem floor the two flexible tracks share 24.5rem, or
 * 261px of title over 131px of location. Below 52rem the title falls under the ~235px at which
 * every row reads "Software E…", which is where the tier stops. The wide tier's fixed tracks
 * total 45rem and it keeps its measured 78rem threshold for the same reason.
 */
export const GRID_TEMPLATE =
  "grid-cols-[minmax(0,1fr)_7.5rem] " +
  "@min-[40rem]:grid-cols-[minmax(0,1fr)_4.5rem_7.5rem] " +
  "@min-[52rem]:grid-cols-[minmax(0,2.4fr)_minmax(0,1.2fr)_4.5rem_7.5rem_12.5rem] " +
  "@min-[78rem]:grid-cols-[3rem_minmax(0,2.4fr)_minmax(0,1.2fr)_4rem_4.5rem_7.5rem_13rem_13rem]";

/** Rank, age and coverage · flags: the wide tier alone. */
export const WIDE_ONLY = "hidden @min-[78rem]:block";

/** Location · remote and the per-row actions: the middle tier and up. */
export const MIDDLE_UP = "hidden @min-[52rem]:block";

/** Score: every tier but the phone one, where 150px of title is worth more than the number. */
export const SCORE_UP = "hidden @min-[40rem]:block";

function Flags({ row }: { row: QueueRow }) {
  return (
    <>
      {/* FIRST, because it is the one flag that explains which of the page's two lists the row is
          in. It renders on review rows only — `review_reason` is `null` off the lane — and it is
          not the same question as `off target` below, which is `not_swe` alone. On a `role_vetoed`
          row it carries the gate's per-title reason (`off_target_reason`) as its tooltip, so the
          `off target` chip below can stay suppressed rather than repeat one decision. */}
      <ReviewReasonBadge
        reason={row.review_reason}
        detailReason={row.review_reason === "role_vetoed" ? row.off_target_reason : null}
      />
      {row.thin_jd ? (
        <Badge label="thin JD" reason="No coverage fraction could be computed." />
      ) : null}
      {/* Suppressed on `role_vetoed` rows: there `off_target` is the SAME `role_verdict(title)`
          decision the badge above already renders (D-412 follow-up), and that badge now carries its
          per-title evidence in its tooltip, so an `off target` chip here would be one decision shown
          twice. It still renders for a non-role `off_target` (there is none today — `off_target` is
          `not_swe` alone — but the guard keeps the two claims separable if that changes). */}
      {row.off_target && row.review_reason !== "role_vetoed" ? (
        <Badge label="off target" reason={row.off_target_reason} />
      ) : null}
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
      className="min-h-8 rounded-sm px-2.5 text-xs text-fg-3 transition-colors duration-[120ms] ease-snap hover:bg-surface-3 hover:text-fg"
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
  onReport,
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
  onReport: () => void;
}) {
  /*
   * `location` is the PRIMARY location and `locations` is the whole list, so the cell reads
   * "Austin, TX +2" rather than a joined string that truncates into "Austin, TX; Hillsboro, O…".
   * `?? []` because an older viewer omits the field entirely (see `lib/format`'s header).
   */
  const locations = row.locations ?? [];
  const where = row.location ?? EM_DASH;
  const alsoWhere = locations.length - 1;
  // The tooltip is the ONLY place the reader can recover a truncated list, so it carries all of
  // them whenever there is more than one and the primary alone otherwise.
  const whereTitle = locations.length > 1 ? locations.join(", ") : where;
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
          className={`grid ${GRID_TEMPLATE} min-h-11 cursor-default items-center gap-3 border-b border-divider px-4 transition-colors duration-[120ms] ease-snap focus-visible:outline-offset-[-2px] ${
            selected
              ? "bg-surface-3 shadow-[inset_2px_0_0_0_var(--color-accent)]"
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
            {/* Everything the tier above this row's own has as a column. Each item hides at the
                width where it becomes one, so a fact is never shown twice and never lost. */}
            <span className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3 @min-[78rem]:hidden">
              <span className="tabular-nums @min-[78rem]:hidden">#{rank}</span>
              <span className="@min-[52rem]:hidden" title={whereTitle}>
                {where}
                {alsoWhere > 0 ? ` +${String(alsoWhere)}` : ""}
              </span>
              <span className="@min-[52rem]:hidden">{row.remote_policy ?? EM_DASH}</span>
              <span className="tabular-nums @min-[40rem]:hidden">{formatScore(row.score)}</span>
              <span className="tabular-nums @min-[78rem]:hidden">{formatAge(row.posted_days)}</span>
              <span className="tabular-nums @min-[78rem]:hidden">
                cov {formatFraction(row.coverage)}
              </span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1 @min-[78rem]:hidden">
                <Flags row={row} />
              </span>
            </span>
          </div>

          <div role="gridcell" className={`${MIDDLE_UP} min-w-0 leading-tight`}>
            <span className="block truncate text-sm text-fg-2" title={whereTitle}>
              {where}
              {alsoWhere > 0 ? (
                <span className="ml-1 text-fg-3">{`+${String(alsoWhere)}`}</span>
              ) : null}
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
            className={`${SCORE_UP} text-right text-sm text-fg tabular-nums`}
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
            className="hidden items-center justify-end gap-1.5 @min-[52rem]:flex"
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
              <RowAction
                label="Report"
                hint={`Report as wrongly eligible: ${named}`}
                onClick={onReport}
                title="Report this lead as wrongly marked eligible, for investigation. Key: r"
              />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
