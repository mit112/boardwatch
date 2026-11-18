import { useEffect, useState } from "react";

import { getCompanions } from "../api/client";
import type { Companion } from "../api/types";

/*
 * T295: each companion that keeps a nightly history (`docs/companions.md`) gets a table here —
 * its current state and summary, then one row per night and one column per count label. The
 * page prints what the companion reports and computes nothing, so a missing count is a dash,
 * never a zero.
 */

function Table({ companion }: { companion: Companion }) {
  const history = companion.history ?? [];
  const columns = [...new Set(history.flatMap((h) => Object.keys(h.counts)))];
  return (
    <section aria-label={`${companion.name} history`} className="mt-6">
      <h3 className="text-base text-fg">{companion.name}</h3>
      <p className="text-sm text-fg-2">
        {companion.state}: {companion.summary}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="text-sm">
          <thead className="text-fg-3">
            <tr>
              <th className="pr-5 text-left font-normal">Night</th>
              {columns.map((c) => (
                <th key={c} className="pr-5 text-right font-normal">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-fg">
            {history.map((h) => (
              <tr key={h.label}>
                <th scope="row" className="pr-5 text-left font-normal">
                  {h.label}
                </th>
                {columns.map((c) => (
                  <td key={c} className="pr-5 text-right tabular-nums">
                    {c in h.counts ? String(h.counts[c]) : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function CompanionHistory() {
  const [companions, setCompanions] = useState<Companion[]>([]);
  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getCompanions())
      .then((c) => {
        if (live) setCompanions(c.companions);
      })
      .catch(() => {
        /* The health strip already says when a companion cannot be read. */
      });
    return () => {
      live = false;
    };
  }, []);
  const withHistory = companions.filter((c) => (c.history ?? []).length > 0);
  if (withHistory.length === 0) return null;
  return (
    <div>
      <h2 className="text-lg font-semibold text-fg">Companion nights</h2>
      {withHistory.map((c) => (
        <Table key={c.name} companion={c} />
      ))}
    </div>
  );
}
