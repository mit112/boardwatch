import { useEffect, useState } from "react";

import { getLeadAging } from "../api/client";
import type { AgingSummary, LeadAging as LeadAgingData } from "../api/types";

/*
 * T298: how long a delivered lead waits before it is applied to, closed or skipped, and how many
 * closed before anyone applied, by the source that found them. Every delivered lead counts once,
 * from its first delivery, including leads held for review.
 */

const OUTCOME_LABEL = { applied: "Applied", closed: "Closed first", skipped: "Skipped" } as const;

function days(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} d`;
}

export function LeadAging() {
  const [data, setData] = useState<LeadAgingData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getLeadAging())
      .then((d) => {
        if (live) setData(d);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, []);

  if (failed) {
    return (
      <section aria-label="Lead aging" className="rounded-md bg-surface p-4 text-sm text-fg-2">
        Lead aging could not be loaded.
      </section>
    );
  }
  if (data === null) return null;
  const outcomes = Object.entries(data.outcomes) as [keyof typeof OUTCOME_LABEL, AgingSummary][];
  const boards = Object.entries(data.closed_before_applied_by_board);

  return (
    <section aria-label="Lead aging" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">Lead aging</h2>
      <p className="mt-1 text-sm text-fg-2">
        {data.leads.toLocaleString()} delivered leads, each counted once from its first delivery;{" "}
        {data.still_waiting.toLocaleString()} have no outcome yet.
        {(data.applied_date_unknown ?? 0) > 0
          ? ` ${data.applied_date_unknown!.toLocaleString()} were applied on a date nobody recorded (imported), so they are not in the waits.`
          : ""}
      </p>
      <table className="mt-3 text-sm">
        <thead className="text-fg-3">
          <tr>
            <th className="pr-6 text-left font-normal">Outcome</th>
            <th className="pr-6 text-right font-normal">Leads</th>
            <th className="pr-6 text-right font-normal">Median wait</th>
            <th className="text-right font-normal">90th percentile</th>
          </tr>
        </thead>
        <tbody className="text-fg">
          {outcomes.map(([key, s]) => (
            <tr key={key}>
              <th scope="row" className="pr-6 text-left font-normal">
                {OUTCOME_LABEL[key]}
              </th>
              <td className="pr-6 text-right tabular-nums">{s.count.toLocaleString()}</td>
              <td className="pr-6 text-right tabular-nums">{days(s.median_days)}</td>
              <td className="text-right tabular-nums">{days(s.p90_days)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {boards.length === 0 ? null : (
        <div className="mt-3">
          <h3 className="label-micro text-fg-3">Closed before anyone applied, by source</h3>
          <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-0.5 text-sm text-fg-2">
            {boards.map(([board, n]) => (
              <li key={board}>
                {board} <span className="tabular-nums text-fg">{n.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
