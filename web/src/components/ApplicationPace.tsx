import { useMemo } from "react";

import type { AppliedRow } from "../api/types";
import { AVERAGE_DAYS, PACE_DAYS, applicationPace } from "../lib/applicationPace";
import type { PaceSplitEntry } from "../lib/applicationPace";

/*
 * Application pace: a bar per day for the last 30 days, the 7-day average, and where the
 * applications went (apply board) and where they came from (discovery source).
 *
 * The chart is a plain `<ol>` of 30 items rather than an SVG: every day is a list item whose
 * accessible text is its own date and count, so a screen-reader reader gets all thirty values in
 * order and sighted readers get the bar. The count is also in each bar's tooltip. A day with none
 * is a bar of zero height and the sentence "0 applications" — a quantity, never a verdict.
 *
 * It counts SUBMITTED applications from the rows the page holds, in the reader's local calendar
 * (`lib/applicationPace.ts`), and it ignores the page's search box and facet: the pace of the
 * whole history does not change because a filter hid some rows.
 */

const CHART_HEIGHT_PX = 96;

function dayLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function applicationsWord(count: number): string {
  return count === 1 ? "1 application" : `${count.toLocaleString()} applications`;
}

function SplitList({ heading, entries }: { heading: string; entries: PaceSplitEntry[] }) {
  return (
    <div className="flex min-w-40 flex-1 flex-col gap-1">
      <h3 className="label-micro text-fg-3">{heading}</h3>
      <ul className="flex flex-col gap-0.5 text-sm text-fg-2">
        {entries.map((entry) => (
          <li key={entry.label} className="flex items-baseline justify-between gap-4">
            <span>{entry.label}</span>
            <span className="tabular-nums text-fg">{entry.count.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ApplicationPace({ rows }: { rows: readonly AppliedRow[] }) {
  const pace = useMemo(() => applicationPace(rows, new Date()), [rows]);
  const first = pace.days[0];
  const last = pace.days[pace.days.length - 1];
  return (
    <section
      aria-labelledby="application-pace-heading"
      className="flex flex-col gap-3 rounded-md border border-divider bg-surface px-4 py-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 id="application-pace-heading" className="label-micro text-fg-3">
          Application pace, last {PACE_DAYS} days
        </h2>
        <p className="text-sm text-fg-2 tabular-nums">
          <span className="font-display text-lg text-fg">{pace.total.toLocaleString()}</span>{" "}
          submitted
          <span aria-hidden="true"> · </span>
          <span className="sr-only">, </span>
          <span className="font-display text-lg text-fg">
            {pace.average.toLocaleString(undefined, {
              minimumFractionDigits: 1,
              maximumFractionDigits: 1,
            })}
          </span>{" "}
          a day over the last {AVERAGE_DAYS} days
        </p>
      </div>

      <figure className="flex flex-col gap-1">
        <div className="flex gap-2">
          <span
            aria-hidden="true"
            className="w-6 shrink-0 text-right text-xs text-fg-3 tabular-nums"
          >
            {pace.peak}
          </span>
          <ol
            aria-label="Applications per day, oldest first"
            className="flex flex-1 items-end gap-0.5 border-b border-control"
            style={{ height: CHART_HEIGHT_PX }}
          >
            {pace.days.map((day) => {
              const text = `${dayLabel(day.date)}: ${applicationsWord(day.count)}`;
              return (
                <li
                  key={day.key}
                  title={text}
                  className="flex h-full flex-1 items-end"
                >
                  <span className="sr-only">{text}</span>
                  <span
                    aria-hidden="true"
                    className="w-full rounded-t-sm bg-accent"
                    style={{ height: `${String((day.count / pace.peak) * 100)}%` }}
                  />
                </li>
              );
            })}
          </ol>
        </div>
        {first !== undefined && last !== undefined ? (
          <figcaption
            aria-hidden="true"
            className="ml-8 flex justify-between text-xs text-fg-3 tabular-nums"
          >
            <span>{dayLabel(first.date)}</span>
            <span>{dayLabel(last.date)}</span>
          </figcaption>
        ) : null}
      </figure>

      {pace.total === 0 ? (
        <p className="text-sm text-fg-2">
          No submitted applications are recorded in these {PACE_DAYS} days.
        </p>
      ) : (
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          <SplitList heading="By apply board" entries={pace.byBoard} />
          <SplitList heading="By discovery source" entries={pace.bySource} />
        </div>
      )}
    </section>
  );
}
