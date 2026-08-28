import type { QueueCounts } from "../api/types";
import { EM_DASH, formatTimestamp } from "../lib/format";

/*
 * The status band. Tabular numerals throughout, so a figure that changes does not shift the ones
 * beside it.
 *
 * `eligible` is the headline yield, and `uncertain`, `review` and `ineligible` each get their own
 * cell. `in_queue` counts the APPLY lane, so the band reconciles instead of leaving a remainder
 * nobody can name: a delivered lead is in the apply lane, held in `review`, or `ineligible`.
 * `review` and `ineligible` fail differently and are never merged — an ineligible lead is
 * REJECTED and not listed anywhere, a review lead is UNVERIFIED and listed in its own section. They are never added together,
 * anywhere: the repository's rule is that an abstain is never folded into either neighbour in any
 * report, and a page is a report. `applied ever`, not applied today — with zero applications ever
 * recorded the two are indistinguishable, and only the first says whether the tool works.
 */
function Metric({
  label,
  value,
  note,
  emphasis = false,
}: {
  label: string;
  value: string;
  note?: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex min-w-24 flex-col gap-1 px-4 py-3">
      <span className="text-[11px] tracking-wide text-fg-3 uppercase">{label}</span>
      <span
        className={`tabular-nums ${emphasis ? "text-2xl text-fg" : "text-xl text-fg-2"}`}
        {...(note ? { title: note } : {})}
      >
        {value}
      </span>
    </div>
  );
}

export function StatusBand({
  counts,
  showing,
  total,
}: {
  counts: QueueCounts;
  showing: number;
  total: number;
}) {
  return (
    <section
      aria-label="Queue status"
      className="flex flex-wrap items-stretch divide-x divide-divider rounded border border-divider bg-surface"
    >
      <Metric label="in queue" value={counts.in_queue.toLocaleString()} emphasis />
      <Metric
        label="eligible"
        value={counts.eligible.toLocaleString()}
        emphasis
        note="Affirmatively eligible. Never includes uncertain."
      />
      <Metric
        label="uncertain"
        value={counts.uncertain.toLocaleString()}
        note="Its own bucket: not yet known, and never added into eligible."
      />
      <Metric
        label="review"
        value={counts.review.toLocaleString()}
        note="Held for a look, not blindly appliable: outside the US, or a title the role gate will not positively call software. Listed below the queue; folders sit in _review."
      />
      <Metric
        label="ineligible"
        value={counts.ineligible.toLocaleString()}
        note="Rejected by the eligibility gate, so not in the queue. Folders drain to _ineligible."
      />
      <Metric label="applied ever" value={counts.applied_ever.toLocaleString()} />
      <Metric label="skipped" value={counts.skipped.toLocaleString()} />
      <Metric
        label="last run"
        value={
          counts.last_run_finished === null
            ? EM_DASH
            : `${formatTimestamp(counts.last_run_finished)} · ${counts.delivered_last_run.toLocaleString()}`
        }
        note="When the most recent run finished, and how many of its leads are still in the queue."
      />
      {/*
        * `border-l-0` because `divide-x` was drawing this cell's rule against `ml-auto`'s dead
        * space, leaving a hairline floating 600px from the nearest content. `role="status"` because
        * this is the only readout that answers "did my filter match anything", and a count that
        * changes silently is a change a screen-reader reader never learns about (SC 4.1.3).
        */}
      <div
        role="status"
        className="ml-auto flex items-center border-l-0 px-4 py-3 text-sm text-fg-2 tabular-nums"
      >
        Showing {showing.toLocaleString()} of {total.toLocaleString()}
      </div>
    </section>
  );
}
