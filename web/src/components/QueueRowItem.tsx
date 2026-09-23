import type { QueueRow } from "../api/types";
import { EM_DASH, formatAge, formatFraction, formatScore } from "../lib/format";
import { ApplyLink } from "./ApplyLink";
import { Badge } from "./Badge";
import { FollowUpBadge } from "./FollowUpBadge";
import { JudgeVerdictBadge } from "./JudgeVerdictBadge";
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
/*
 * The actions track is 16rem in both tiers, MEASURED: Apply (58px) + Applied (63) + Skip (44) +
 * Report (58) + three 6px gaps + the 8px rule = 250px. At 13rem the four buttons overflowed their
 * cell leftward (a `justify-end` flex row overflows on the start side, where `scrollWidth` does
 * not report it) and sat on top of the verdict chip in the middle tier.
 */
export const GRID_TEMPLATE =
  "grid-cols-[minmax(0,1fr)_7.5rem] " +
  "@min-[40rem]:grid-cols-[minmax(0,1fr)_4.5rem_7.5rem] " +
  "@min-[52rem]:grid-cols-[minmax(0,2.4fr)_minmax(0,1.2fr)_4.5rem_7.5rem_16rem] " +
  "@min-[78rem]:grid-cols-[3rem_minmax(0,2.4fr)_minmax(0,1.2fr)_4rem_4.5rem_7.5rem_13rem_16rem]";

/** The width of the selection track. Fixed, like every other non-flexible track here. */
export const SELECT_TRACK = "2.25rem_";

/**
 * `GRID_TEMPLATE` with the selection checkbox's track prepended to every tier.
 *
 * It is written out rather than derived from `GRID_TEMPLATE`, and that is not laziness: Tailwind
 * generates a class only for a candidate that appears LITERALLY in the source, so a template built
 * by string surgery at runtime would produce four class names no stylesheet contains. The
 * `templatesAgree` assertion in `bulkSkip.test.tsx` is what keeps the two from drifting.
 */
export const SELECT_GRID_TEMPLATE =
  "grid-cols-[2.25rem_minmax(0,1fr)_7.5rem] " +
  "@min-[40rem]:grid-cols-[2.25rem_minmax(0,1fr)_4.5rem_7.5rem] " +
  "@min-[52rem]:grid-cols-[2.25rem_minmax(0,2.4fr)_minmax(0,1.2fr)_4.5rem_7.5rem_16rem] " +
  "@min-[78rem]:grid-cols-[2.25rem_3rem_minmax(0,2.4fr)_minmax(0,1.2fr)_4rem_4.5rem_7.5rem_13rem_16rem]";

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
        detailReason={
          row.review_reason === "role_vetoed"
            ? row.off_target_reason
            : /* The QUOTED application-form question, routed exactly as the role gate's
                 per-title evidence is above. `?? null` because the field is optional on the
                 wire: an older server omits it, and the badge then falls back to its own copy
                 rather than rendering `undefined`. */
              row.review_reason === "form_question_hard_stop"
              ? (row.form_question ?? null)
              : /* T92. The provider's own employment type, routed exactly as the two above are:
                   this reason names something the JD does not state, so the chip has to be able
                   to quote the field. */
                row.review_reason === "provider_employment_type"
                ? (row.provider_employment_type ?? null)
                : null
        }
      />
      {/* WHAT THE FINAL GATE SAID, which is not what the `VerdictChip` beside this cell says.
          On the measured apply lane 42 of 390 judged leads read `uncertain` here on rows the
          rules engine had cleared, and the page showed them identically — the strongest signal in
          the system, hidden. Unconditional and self-labelling: it renders nothing where the gate
          has not spoken (see the component), so there is no case to suppress it for. It sits
          here, in `Flags`, rather than inside the verdict cell because that cell is a MEASURED
          7.5rem track in every tier and a second chip would overflow it; `Flags` is the app's
          existing home for every per-row marker and, in the wide tier, the column immediately
          beside the verdict. */}
      <JudgeVerdictBadge verdict={row.judge_verdict} />
      {/* The BODY-seniority reading on an APPLY row. Suppressed when the badge above already
          says it: on a review row the same reading arrives as `seniority_judged_above_band` and
          rendering both would show one decision twice, the way `off target` is suppressed on a
          `role_vetoed` row. So this chip appears exactly where the reading is otherwise
          invisible — the apply lane, which is where it lands while `gate.seniority_hold` is off.
          `=== true` rather than a bare truthiness test because an older server omits the field
          (see the type), and `undefined` must render nothing rather than throw. */}
      {row.judge_seniority_above_band === true &&
      row.review_reason !== "seniority_judged_above_band" ? (
        <Badge
          label="body reads senior"
          reason="The title looks entry-level but an independent read of the job description describes a more senior role. The hold that would act on this is off, so this lead is still in the apply lane. Read the JD before applying."
        />
      ) : null}
      {/* The pinned follow-up, and whether it has arrived. The applied history renders the same
          component: one date, one wording, one place it is decided. */}
      <FollowUpBadge followUp={row.follow_up} />
      {/* T125. A note, like the follow-up beside it: the lead is still listed and ranked as it
          would be without it. The pane names where and when. `?? []` for an older server. */}
      {(row.applied_identical_jd ?? []).length > 0 ? (
        <Badge
          label="applied: identical JD"
          reason="You applied to another posting at this company with an identical job description. Open the lead for where and when."
        />
      ) : null}
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
 * The selection checkbox. `tabIndex={-1}` for the same reason every other per-row control is —
 * the row is the tab stop — and its single-key equivalent is `x` on the focused row.
 *
 * The checkbox IS the second channel selection is carried by (SC 1.4.1): the row's fill and left
 * rule are colour, and a checked box is not. Its name carries the row's identity rather than a
 * bare "Select", so a reader tabbing a screen reader down the column hears which lead each box
 * belongs to.
 */
export function SelectCell({
  label,
  checked,
  onToggle,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <span role="gridcell" className="flex items-center">
      <input
        type="checkbox"
        tabIndex={-1}
        checked={checked}
        aria-label={`Select: ${label}`}
        title="Select this lead for a bulk action. Key: x"
        onClick={(event) => {
          // The row's own `onClick` opens the detail pane; selecting a row must not.
          event.stopPropagation();
        }}
        onChange={onToggle}
        className="size-4 cursor-pointer accent-accent"
      />
    </span>
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
  marked,
  onMark,
}: {
  row: QueueRow;
  rank: number;
  /** Open in the detail pane. Reported as `aria-current`, NOT as `aria-selected` — see below. */
  selected: boolean;
  /** Carries the roving tab stop. Exactly one row per table is `true`. */
  active: boolean;
  collapsing: boolean;
  onSelect: () => void;
  onApplied: () => void;
  onSkip: () => void;
  onReport: () => void;
  /** Picked out for a BULK action. `undefined` on a table with no selection column at all. */
  marked?: boolean;
  onMark?: () => void;
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
          /*
           * `aria-selected` is the BULK selection and `aria-current` is the row the detail pane is
           * showing. One attribute cannot carry both, and in a `role="grid"` `aria-selected` means
           * selection — so the pane's row, which is "the one you are looking at" rather than "one
           * of the ones you picked", is the reading that moves. Nothing visual changes for it.
           */
          aria-selected={marked === undefined ? undefined : marked}
          {...(selected ? { "aria-current": true as const } : {})}
          className={`grid ${marked === undefined ? GRID_TEMPLATE : SELECT_GRID_TEMPLATE} min-h-11 cursor-default items-center gap-3 border-b border-divider px-4 transition-colors duration-[120ms] ease-snap focus-visible:outline-offset-[-2px] ${
            selected
              ? "bg-surface-3 shadow-[inset_2px_0_0_0_var(--color-accent)]"
              : marked
                ? "bg-surface-2"
                : "hover:bg-surface-2/60"
          }`}
          onClick={onSelect}
        >
          {marked === undefined || onMark === undefined ? null : (
            <SelectCell label={named} checked={marked} onToggle={onMark} />
          )}

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
              {/* The ATS sits on the company line because it is a fact about the COMPANY's
                  board, and because the owner works the queue in ATS batches — sorting by it
                  (`lib/sort`) is useless if the blocks are not labelled. One `Badge`, no colour
                  of its own: an ATS is not a state, and a palette per vendor would spend the
                  row's whole colour budget on something that conveys nothing on its own.
                  `== null` so an older server's absent field renders nothing (D-360). */}
              <span className="flex w-full min-w-0 items-center gap-1.5">
                {/* `min-w-0`: a flex item's default `min-width: auto` refuses to shrink below
                    its content, so without it a long employer name overflows the cell instead
                    of truncating — which is what `max-w-full` was doing before the row became
                    a flex row. The label beside it is `shrink-0` for the opposite reason: it
                    is three characters the reader is grouping BY, so it is the company name
                    that gives way, never the ATS. */}
                <span className="min-w-0 truncate text-xs text-fg-2" title={row.company}>
                  {row.company}
                </span>
                {row.provider == null ? null : (
                  <span className="shrink-0">
                    <Badge
                      label={row.provider}
                      reason={`Applicant tracking system: ${row.provider}. Sort by "ats" to work the queue one form at a time.`}
                    />
                  </span>
                )}
              </span>
            </button>
            {/* Everything the tier above this row's own has as a column. Each item hides at the
                width where it becomes one, so a fact is never shown twice and never lost. */}
            <span className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3 @min-[78rem]:hidden">
              <span className="tabular-nums @min-[78rem]:hidden">#{rank}</span>
              <span className="@min-[52rem]:hidden" title={whereTitle}>
                {where}
                {alsoWhere > 0 ? ` +${String(alsoWhere)}` : ""}
              </span>
              <span className="@min-[52rem]:hidden">{row.remote_policy ?? EM_DASH}</span>
              {/* Labelled, unlike the location and the age beside it: a bare `0.90` next to
                  `cov 62%` is two unlabelled fractions and no way to tell which is which. */}
              <span
                className="tabular-nums @min-[40rem]:hidden"
                title={row.why ?? "Score, as of now."}
              >
                score {formatScore(row.score)}
              </span>
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

          {/* The tooltip is the server's OWN explanation when it sent one. Nothing here infers a
              reason from the number: the ranker is the only thing that knows what it weighed. */}
          <span
            role="gridcell"
            className={`${SCORE_UP} text-right text-sm text-fg tabular-nums`}
            title={row.why ?? "Score, as of now."}
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
