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
  order = 0,
}: {
  label: string;
  value: string;
  note?: string;
  emphasis?: boolean;
  /* Drives the entry stagger and nothing else. Hand-written rather than a `map` index, because
     each cell below carries its own `note` and is therefore written out one by one. */
  order?: number;
}) {
  return (
    <div
      className="enter-up flex min-w-28 flex-col gap-2 px-6 py-5"
      style={{ "--stagger": `${String(order * 40)}ms` } as React.CSSProperties}
    >
      <span className="label-micro text-fg-3">{label}</span>
      {/* The emphasis jump is deliberately large — 2.25rem against 1.25rem. `in queue` and
          `eligible` are the two figures the owner opens the page to read; the rest of the row is
          context for them, and a band where every cell shouts equally has no headline at all. */}
      <span
        className={`font-display tabular-nums ${emphasis ? "text-4xl leading-none text-fg" : "text-xl leading-none text-fg-2"}`}
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
      className="flex flex-wrap items-stretch divide-x divide-divider rounded-md bg-surface shadow-[0_1px_0_0_var(--color-divider)_inset,0_16px_40px_-24px_rgb(0_0_0/0.9)]"
    >
      <Metric label="in queue" value={counts.in_queue.toLocaleString()} emphasis order={0} />
      <Metric
        label="eligible"
        value={counts.eligible.toLocaleString()}
        emphasis
        note="Affirmatively eligible. Never includes uncertain."
        order={1}
      />
      <Metric
        label="uncertain"
        value={counts.uncertain.toLocaleString()}
        note="Its own bucket: not yet known, and never added into eligible."
        order={2}
      />
      <Metric
        label="review"
        value={counts.review.toLocaleString()}
        note="Held for a look, not blindly appliable: outside the US, or a title the role gate will not positively call software. Listed below the queue; folders sit in _review."
        order={3}
      />
      <Metric
        label="ineligible"
        value={counts.ineligible.toLocaleString()}
        note="Rejected by the eligibility gate, so not in the queue. Folders drain to _ineligible."
        order={4}
      />
      <Metric label="applied ever" value={counts.applied_ever.toLocaleString()} order={5} />
      <Metric label="skipped" value={counts.skipped.toLocaleString()} order={6} />
      <Metric
        label="last run"
        value={
          counts.last_run_finished === null
            ? EM_DASH
            : `${formatTimestamp(counts.last_run_finished)} · ${counts.delivered_last_run.toLocaleString()}`
        }
        note="When the most recent run finished, and how many of its leads are still in the queue."
        order={7}
      />
      {/*
        * `border-l-0` because `divide-x` was drawing this cell's rule against `ml-auto`'s dead
        * space, leaving a hairline floating 600px from the nearest content. `role="status"` because
        * this is the only readout that answers "did my filter match anything", and a count that
        * changes silently is a change a screen-reader reader never learns about (SC 4.1.3).
        */}
      <div
        role="status"
        className="ml-auto flex items-center border-l-0 px-6 py-5 text-sm text-fg-2 tabular-nums"
      >
        Showing {showing.toLocaleString()} of {total.toLocaleString()}
      </div>
    </section>
  );
}
