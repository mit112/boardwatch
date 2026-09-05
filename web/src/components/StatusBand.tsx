import type { QueueCounts } from "../api/types";
import { EM_DASH, formatTimestamp } from "../lib/format";

/**
 * The band cells a reader can click to see only that bucket. `eligible` and `uncertain` are
 * VERDICTS: each filters the apply lane AND the review lane, exactly as the text search and score
 * floor do — a review-lane lead can be `eligible` (held only for its location), and dropping it
 * would be the documented "make the review list look empty for a matching filter" failure.
 *
 * `review` is a LANE, not a verdict, so it behaves differently: it shows the review lane alone and
 * hides the apply queue, the way opening only that section would. `ineligible` is deliberately NOT a
 * facet: it is drained, never listed, so a toggle there could only ever show an empty list.
 */
export type QueueFacet = "eligible" | "uncertain" | "review";

/*
 * The status band. Tabular numerals throughout, so a figure that changes does not shift the ones
 * beside it.
 *
 * `eligible` is the headline yield, and `uncertain`, `review`, `ineligible` and `closed` each get
 * their own cell. `in_queue` counts the APPLY lane, so the band reconciles instead of leaving a
 * remainder nobody can name: a delivered lead is in the apply lane, held in `review`, `ineligible`,
 * or `closed` because the employer took the posting down.
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
  active,
  onToggle,
}: {
  label: string;
  value: string;
  note?: string;
  emphasis?: boolean;
  /* Drives the entry stagger and nothing else. Hand-written rather than a `map` index, because
     each cell below carries its own `note` and is therefore written out one by one. */
  order?: number;
  /* When `onToggle` is set the whole cell becomes a filter toggle and `active` is its pressed
     state; left undefined the cell is a plain readout, byte-for-byte as before. */
  active?: boolean;
  onToggle?: () => void;
}) {
  const shell = "enter-up flex min-w-28 flex-col gap-2 px-6 py-5";
  const stagger = { "--stagger": `${String(order * 40)}ms` } as React.CSSProperties;
  const body = (
    <>
      <span className={`label-micro ${active ? "text-fg-2" : "text-fg-3"}`}>{label}</span>
      {/* The emphasis jump is deliberately large — 2.25rem against 1.25rem. `in queue` and
          `eligible` are the two figures the owner opens the page to read; the rest of the row is
          context for them, and a band where every cell shouts equally has no headline at all. */}
      <span
        className={`font-display tabular-nums ${emphasis ? "text-4xl leading-none" : "text-xl leading-none"} ${active || emphasis ? "text-fg" : "text-fg-2"}`}
        {...(note ? { title: note } : {})}
      >
        {value}
      </span>
    </>
  );

  if (onToggle === undefined) {
    return (
      <div className={shell} style={stagger}>
        {body}
      </div>
    );
  }

  /*
   * A real `<button>`, so role, keyboard operation and the global focus ring come for free, and
   * `aria-pressed` carries the on/off state. The pressed treatment is the app's own active idiom
   * (see `NavTab`): a fill plus an inset accent bar plus brighter text — three channels, never
   * colour alone (SC 1.4.1). The `aria-label` STARTS with the visible label and value so Label in
   * Name holds (SC 2.5.3), then names the action, which `aria-pressed` alone never conveys.
   */
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={`${label} ${value} — ${active ? "showing only these, activate to clear" : "show only these"}`}
      onClick={onToggle}
      className={`${shell} cursor-pointer text-left transition-colors duration-[120ms] ease-snap ${
        active
          ? "bg-surface-3 shadow-[inset_0_-2px_0_0_var(--color-accent)]"
          : "hover:bg-surface-2"
      }`}
      style={stagger}
    >
      {body}
    </button>
  );
}

export function StatusBand({
  counts,
  showing,
  total,
  activeFacet,
  onToggleFacet,
}: {
  counts: QueueCounts;
  showing: number;
  total: number;
  activeFacet: QueueFacet | null;
  onToggleFacet: (facet: QueueFacet) => void;
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
        note="Affirmatively eligible. Never includes uncertain. Click to show only these."
        order={1}
        active={activeFacet === "eligible"}
        onToggle={() => {
          onToggleFacet("eligible");
        }}
      />
      <Metric
        label="uncertain"
        value={counts.uncertain.toLocaleString()}
        note="Its own bucket: not yet known, and never added into eligible. Click to show only these."
        order={2}
        active={activeFacet === "uncertain"}
        onToggle={() => {
          onToggleFacet("uncertain");
        }}
      />
      <Metric
        label="review"
        value={counts.review.toLocaleString()}
        note="Held for a look, not blindly appliable: outside the US, or a title the role gate will not positively call software. Click to show only this lane."
        order={3}
        active={activeFacet === "review"}
        onToggle={() => {
          onToggleFacet("review");
        }}
      />
      <Metric
        label="ineligible"
        value={counts.ineligible.toLocaleString()}
        note="Rejected by the eligibility gate, so not in the queue. Folders drain to _ineligible."
        order={4}
      />
      <Metric
        label="closed"
        value={counts.closed.toLocaleString()}
        note="The employer took the posting down; drained to _closed, never judged."
        order={5}
      />
      <Metric label="applied ever" value={counts.applied_ever.toLocaleString()} order={6} />
      <Metric label="skipped" value={counts.skipped.toLocaleString()} order={7} />
      <Metric
        label="reported"
        value={counts.reported.toLocaleString()}
        note="Flagged as wrongly-eligible and held for investigation. Its own cell, never folded into skipped, and taken out of the queue like a skip."
        order={8}
      />
      <Metric
        label="last run"
        value={
          counts.last_run_finished === null
            ? EM_DASH
            : `${formatTimestamp(counts.last_run_finished)} · ${counts.delivered_last_run.toLocaleString()}`
        }
        note="When the most recent run finished, and how many of its leads are still in the queue."
        order={9}
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
