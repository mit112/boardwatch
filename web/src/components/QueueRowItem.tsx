import type { QueueRow } from "../api/types";
import { materialsMark, reviewsDiffer, rowNote } from "../lib/jobStatus";
import { describeGroup } from "../lib/similar";
import type { SimilarGroup } from "../lib/similar";
import { FollowUpBadge } from "./FollowUpBadge";
import { Icon } from "./Icon";
import { StatusMark } from "./StatusMark";

/*
 * ONE row of the job list: a compact, scannable block, not a card and not a table row.
 *
 * The list sits beside a workspace, so it is a narrow column and every fact on a row has to earn
 * its place by changing the NEXT ACTION. That leaves four lines at most:
 *
 *   role                                   how long ago it was posted
 *   company · where · work arrangement
 *   the one thing to check first           (omitted when nothing is flagged)
 *   quiet facts: board, group, follow-up   résumé ready / not built
 *
 * What is NOT here, deliberately: the ranking score and the keyword coverage (neither says whether
 * to apply — both live under "Why this status?" in the workspace), per-row action buttons (the
 * workspace beside the list holds the actions and every one has a key on the focused row), and a
 * stack of outlined badges. An absent line is not an approval: a row with no status line is a row
 * with nothing to flag, and the workspace still shows every reading.
 *
 * The visible words are the status model's (`lib/jobStatus`), so a row, the workspace and the
 * "Why this status?" disclosure cannot drift into three vocabularies for one fact.
 */

/** "3d ago", "today" — or nothing when the board published no date. Never "0d". */
function postedLabel(days: number | null): string | null {
  if (days == null) return null;
  return days === 0 ? "today" : `${String(days)}d ago`;
}

/*
 * The selection checkbox. `tabIndex={-1}` for the same reason every other per-row control is —
 * the row is the tab stop — and its single-key equivalent is `x` on the focused row.
 *
 * The checkbox IS the second channel selection is carried by (SC 1.4.1): the row's fill is colour,
 * and a checked box is not. Its name carries the row's identity rather than a bare "Select", so a
 * reader tabbing a screen reader down the column hears which job each box belongs to.
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
    <span role="gridcell" className="flex min-h-9 items-start pt-1">
      <input
        type="checkbox"
        tabIndex={-1}
        checked={checked}
        aria-label={`Select: ${label}`}
        title="Select this job for a bulk action. Key: x"
        onClick={(event) => {
          // The row's own `onClick` opens the workspace; selecting a row must not.
          event.stopPropagation();
        }}
        onChange={onToggle}
        className="size-4 cursor-pointer"
      />
    </span>
  );
}

export function QueueRowItem({
  row,
  selected,
  active,
  collapsing,
  onSelect,
  marked,
  onMark,
  similar,
}: {
  row: QueueRow;
  /** Open in the workspace. Reported as `aria-current`, NOT as `aria-selected` — see below. */
  selected: boolean;
  /** Carries the roving tab stop. Exactly one row per table is `true`. */
  active: boolean;
  collapsing: boolean;
  onSelect: () => void;
  /** Picked out for a BULK action. `undefined` on a table with no selection column at all. */
  marked?: boolean;
  onMark?: () => void;
  /** What this row's group of similar postings holds, when it has one in this list. */
  similar?: SimilarGroup | undefined;
}) {
  /*
   * `location` is the PRIMARY location and `locations` is the whole list, so the line reads
   * "Austin, TX +2" rather than a joined string that truncates. `?? []` because an older viewer
   * omits the field entirely (see `lib/format`'s header).
   */
  const locations = row.locations ?? [];
  const alsoWhere = locations.length - 1;
  const whereTitle = locations.length > 1 ? locations.join(", ") : (row.location ?? "");
  const named = `${row.title} at ${row.company}`;
  const note = rowNote(row);
  const posted = postedLabel(row.posted_days);
  const materials = materialsMark(row.pdf_available);
  const facts = [
    row.location === null
      ? null
      : `${row.location}${alsoWhere > 0 ? ` +${String(alsoWhere)}` : ""}`,
    row.remote_policy,
  ].filter((part): part is string => part !== null && part !== "");

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
           * `aria-selected` is the BULK selection and `aria-current` is the row the workspace is
           * showing. One attribute cannot carry both, and in a `role="grid"` `aria-selected` means
           * selection — so the open row, which is "the one you are looking at" rather than "one
           * of the ones you picked", is the reading that moves.
           */
          aria-selected={marked === undefined ? undefined : marked}
          {...(selected ? { "aria-current": true as const } : {})}
          className={`flex cursor-default items-start gap-3 border-b border-divider px-4 py-3 transition-colors duration-[120ms] ease-snap focus-visible:outline-offset-[-2px] ${
            selected
              ? "bg-surface-3 shadow-[inset_0_0_0_1px_var(--color-accent)]"
              : marked
                ? "bg-surface-2"
                : "hover:bg-surface-2"
          }`}
          onClick={onSelect}
        >
          {marked === undefined || onMark === undefined ? null : (
            <SelectCell label={named} checked={marked} onToggle={onMark} />
          )}

          <div role="gridcell" className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              {/* Role AND company inside the button, so the control's accessible name names the
                  employer. Two lines for the role before it truncates: a title is the one fact the
                  reader is choosing by, and a one-line clip hid the part that differs. */}
              <button
                type="button"
                tabIndex={-1}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect();
                }}
                className="min-w-0 flex-1 text-left"
              >
                <span
                  className="line-clamp-2 text-[0.9375rem] leading-snug font-semibold break-words text-fg"
                  title={row.title}
                >
                  {row.title}
                </span>
                <span className="mt-0.5 block truncate text-sm text-fg-2" title={row.company}>
                  {row.company}
                </span>
              </button>
              {posted === null ? null : (
                <span className="shrink-0 pt-0.5 text-xs text-fg-3 tabular-nums" title="Posted">
                  {posted}
                </span>
              )}
            </div>

            <p className="mt-0.5 truncate text-[0.8125rem] text-fg-3" title={whereTitle}>
              {facts.length === 0 ? "Location not listed" : facts.join(" · ")}
            </p>

            {note === null ? null : <StatusMark mark={note} className="mt-1.5" />}
            {/* Both engines spoke and they differ. The status line says so itself when the pair is
                what it is about; whenever it is about something else (a held reason, a closed
                posting) this says it on its own line, so a disagreement is never only inside the
                workspace. */}
            {reviewsDiffer(row) && note?.coversDisagreement !== true ? (
              <StatusMark
                mark={{ label: "Rules and independent review differ", tone: "warn" }}
                className="mt-1"
              />
            ) : null}

            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-3">
              {note?.label === materials.label ? null : (
                <span
                  className={`inline-flex items-center gap-1 ${materials.tone === "ok" ? "text-ok" : "text-warn"}`}
                >
                  <Icon name={materials.tone === "ok" ? "file" : "question"} size={13} />
                  {materials.tone === "ok" ? "Résumé ready" : "No résumé"}
                </span>
              )}
              {row.provider == null ? null : (
                <span title={`Posted on ${row.provider}`}>{row.provider}</span>
              )}
              {similar === undefined ? null : (
                <span title="Postings at this company with the same title once formatting is ignored. They may be one job in several places or separate openings; each stays listed.">
                  {describeGroup(similar)}
                </span>
              )}
              <FollowUpBadge followUp={row.follow_up} />
              {(row.applied_identical_jd ?? []).length > 0 ? (
                <span title="You applied to another posting at this company with an identical description. Open the job for where and when.">
                  Applied to an identical posting
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
