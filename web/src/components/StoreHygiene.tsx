import { useEffect, useState } from "react";

import { getStoreHygiene } from "../api/client";
import type { StoreHygiene as StoreHygieneData } from "../api/types";
import { EM_DASH, formatCount, formatTimestamp } from "../lib/format";

/*
 * T313: is the quarantine draining, how often does grouping merge duplicates, how big is the store.
 * A bucket that holds bodies and never drains is a leak, so a stalled drain is said in words, not
 * left to a number. Table sizes are counts where one finishes in time and the highest row id
 * (marked ≈) where not. Store growth per run comes from the size each nightly funnel recorded;
 * a run before that, or an unreadable file, shows a dash, never 0, and with no recorded run at
 * all the panel says so instead of drawing a table.
 */

function gigabytes(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

function megabytes(bytes: number | null): string {
  return bytes === null ? EM_DASH : `${(bytes / 1e6).toFixed(1)} MB`;
}

function growth(bytes: number | null): string {
  if (bytes === null) return EM_DASH;
  const sign = bytes < 0 ? "\u2212" : "+";
  return `${sign}${(Math.abs(bytes) / 1e6).toFixed(1)} MB`;
}

function days(value: number | null): string {
  return value === null ? EM_DASH : `${value.toFixed(1)} d`;
}

export function StoreHygiene() {
  const [data, setData] = useState<StoreHygieneData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getStoreHygiene())
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
      <section
        aria-label="Store hygiene"
        className="rounded-md bg-surface p-4 text-sm text-fg-2"
      >
        Store hygiene could not be loaded.
      </section>
    );
  }
  if (data === null) return null;
  const { quarantine: q, grouping: g, store, tables } = data;

  return (
    <section aria-label="Store hygiene" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">Store hygiene</h2>

      <h3 className="label-micro mt-3 text-fg-3">Quarantine</h3>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(q.held)} bodies held, {formatCount(q.drained)} drained. Oldest
        held {days(q.oldest_held_days)}; last drain{" "}
        {q.days_since_drain === null
          ? "never"
          : `${q.days_since_drain.toFixed(1)} d ago`}
        .
      </p>
      {q.stalled ? (
        <p role="alert" className="mt-1 text-sm text-fg">
          The drain has stalled: {formatCount(q.held)} bodies are held and none
          has drained in the last {q.stall_days} days.
        </p>
      ) : null}
      {q.weekly.length === 0 ? null : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Quarantine by week">
          <table className="mt-2 text-sm">
            <caption className="sr-only">Quarantine by week</caption>
            <thead className="text-fg-3">
              <tr>
                <th className="pr-6 text-left font-normal">Week of</th>
                <th className="pr-6 text-right font-normal">Quarantined</th>
                <th className="text-right font-normal">Drained</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {q.weekly.map((w) => (
                <tr key={w.week_start}>
                  <th scope="row" className="pr-6 text-left font-normal">
                    {w.week_start}
                  </th>
                  <td className="pr-6 text-right tabular-nums">
                    {formatCount(w.quarantined)}
                  </td>
                  <td className="text-right tabular-nums">
                    {formatCount(w.drained)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="label-micro mt-4 text-fg-3">Duplicate grouping</h3>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(g.merges)} merge events (a posting can move more than once)
        {g.per_1000_postings === null
          ? "."
          : `, ${g.per_1000_postings.toFixed(2)} per 1,000 of about ${formatCount(g.postings_approx)} postings stored.`}{" "}
        {g.methods
          .map(
            (m) =>
              `${formatCount(m.count)} by ${m.method}${m.algorithm_version === null ? "" : ` ${m.algorithm_version}`}`,
          )
          .join(", ")}
      </p>
      {g.weekly.length === 0 ? null : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Merges by week">
          <table className="mt-2 text-sm">
            <caption className="sr-only">Merges by week</caption>
            <thead className="text-fg-3">
              <tr>
                <th className="pr-6 text-left font-normal">Week of</th>
                <th className="text-right font-normal">Merged</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {g.weekly.map((w) => (
                <tr key={w.week_start}>
                  <th scope="row" className="pr-6 text-left font-normal">
                    {w.week_start}
                  </th>
                  <td className="text-right tabular-nums">
                    {formatCount(w.merges)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="label-micro mt-4 text-fg-3">Store size</h3>
      <p className="mt-1 text-sm text-fg-2">
        {gigabytes(store.total_bytes)} on disk ({gigabytes(store.db_bytes)}{" "}
        database, {gigabytes(store.wal_bytes)} write-ahead log).{" "}
        {store.growth_recorded
          ? ""
          : "No run shown has a recorded size yet, so no growth is shown."}
      </p>
      {store.growth_recorded ? (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Store size by run">
          <table className="mt-2 text-sm">
            <caption className="sr-only">Store size by run</caption>
            <thead className="text-fg-3">
              <tr>
                <th className="pr-6 text-left font-normal">Run</th>
                <th className="pr-6 text-left font-normal">Finished</th>
                <th className="pr-6 text-right font-normal">Database</th>
                <th className="pr-6 text-right font-normal">Log</th>
                <th className="text-right font-normal">Database growth</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {store.series.map((r) => (
                <tr key={r.run_id}>
                  <th scope="row" className="pr-6 text-left font-normal">
                    {r.run_id}
                  </th>
                  <td className="pr-6">{formatTimestamp(r.finished)}</td>
                  <td className="pr-6 text-right tabular-nums">
                    {r.db_bytes === null ? EM_DASH : gigabytes(r.db_bytes)}
                  </td>
                  <td className="pr-6 text-right tabular-nums">
                    {megabytes(r.wal_bytes)}
                  </td>
                  <td className="text-right tabular-nums">
                    {growth(r.growth_bytes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {tables.rows.length === 0 ? null : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Largest tables by rows">
          <table className="mt-2 text-sm">
            <caption className="label-micro pb-1 text-left text-fg-3">
              Largest tables, by rows (≈ marks an estimate)
            </caption>
            <thead className="text-fg-3">
              <tr>
                <th className="pr-6 text-left font-normal">Table</th>
                <th className="text-right font-normal">Rows</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {tables.rows.map((t) => (
                <tr key={t.name}>
                  <th scope="row" className="pr-6 text-left font-normal">
                    {t.name}
                  </th>
                  <td className="text-right tabular-nums">
                    {t.exact ? "" : "≈ "}
                    {formatCount(t.rows)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
