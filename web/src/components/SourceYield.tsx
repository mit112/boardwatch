import { useEffect, useState } from "react";

import { getSourceYield } from "../api/client";
import type { FunnelSource, SourceYieldResponse } from "../api/types";
import { sourceYield } from "../lib/sourceYield";

const count = (n: number | null): string =>
  n === null ? "—" : n.toLocaleString();

export function SourceYield({ boards }: { boards: FunnelSource[] }) {
  const [allTime, setAllTime] = useState<SourceYieldResponse["sources"] | null>(
    null,
  );
  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getSourceYield())
      .then((r) => {
        if (live) setAllTime(r.sources);
      })
      .catch(() => {
        /* The snapshot columns still stand; the all-time ones read as dashes. */
      });
    return () => {
      live = false;
    };
  }, []);
  const rows = sourceYield(boards, allTime);

  return (
    <section aria-label="Discovery yield per source">
      <h2 className="text-base text-fg">Discovery yield per source</h2>
      <p className="text-sm text-fg-2">
        Open and eligible are this run&apos;s snapshot. Built and applied are
        all time, each lead counted once for the source that first delivered it.
        Only applied ÷ built is a rate; the two scopes are not divided into each
        other.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="text-sm">
          <thead className="text-fg-3">
            <tr>
              <th className="pr-5 text-left font-normal">Source</th>
              <th className="pr-5 text-right font-normal">Open now</th>
              <th className="pr-5 text-right font-normal">Eligible now</th>
              <th className="pr-5 text-right font-normal">Résumés built</th>
              <th className="pr-5 text-right font-normal">Applied</th>
              <th className="text-right font-normal">Applied ÷ built</th>
            </tr>
          </thead>
          <tbody className="text-fg">
            {rows.map((r) => (
              <tr key={r.source}>
                <th scope="row" className="pr-5 text-left font-normal">
                  {r.source}
                </th>
                <td className="pr-5 text-right tabular-nums">
                  {count(r.open)}
                </td>
                <td className="pr-5 text-right tabular-nums">
                  {count(r.eligible)}
                </td>
                <td className="pr-5 text-right tabular-nums">
                  {count(r.built)}
                </td>
                <td className="pr-5 text-right tabular-nums">
                  {count(r.applied)}
                </td>
                <td className="text-right tabular-nums">
                  {r.applyRate === null
                    ? "—"
                    : `${(r.applyRate * 100).toFixed(0)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
