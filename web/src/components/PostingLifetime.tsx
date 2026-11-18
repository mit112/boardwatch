import { useEffect, useState } from "react";

import { getPostingLifetime } from "../api/client";
import type { PostingLifetime as PostingLifetimeData } from "../api/types";
import { EM_DASH, formatCount, formatFraction } from "../lib/format";

/*
 * T307: how long postings stay open, against how fast we apply. Lifetime is first seen to the
 * posting's first close, so postings that never closed are NOT in any median here: they are
 * counted apart (a posting that reopened is in the closed group, at its first close). That makes
 * the lifetime read short, which is the cautious direction for an urgency signal. "Reopened" is the share of closed postings that came back, i.e. how far a "closed"
 * lead can be trusted. A missing median is a dash, never zero days.
 */

function days(value: number | null): string {
  return value === null ? EM_DASH : `${value.toFixed(1)} d`;
}

function urgency(value: boolean | null): string {
  return value === null ? EM_DASH : value ? "Yes" : "No";
}

export function PostingLifetime() {
  const [data, setData] = useState<PostingLifetimeData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getPostingLifetime())
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
        aria-label="Posting lifetime"
        className="rounded-md bg-surface p-4 text-sm text-fg-2"
      >
        Posting lifetime could not be loaded.
      </section>
    );
  }
  if (data === null) return null;

  return (
    <section aria-label="Posting lifetime" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">Posting lifetime</h2>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(data.closed.count)} closed postings: median life {days(data.closed.median_days)}
        , 90th percentile {days(data.closed.p90_days)}. Median time from first seen to applied{" "}
        {days(data.to_apply.median_days)} ({formatCount(data.to_apply.count)} applied).{" "}
        <span className="text-fg">
          {data.urgent === null
            ? "Urgency is not measured."
            : data.urgent
              ? "Postings close faster than we apply."
              : "We apply before the typical posting closes."}
        </span>
      </p>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(data.never_closed)} postings have never closed and are not in the medians.{" "}
        {formatCount(data.reopen.postings)} closed postings later reopened (
        {formatFraction(data.reopen.rate)} of closed), so a closed lead is not final.
      </p>
      <p className="mt-1 text-sm text-fg-2">
        Applications created by an import carry the import date, not the application date, so{" "}
        {formatCount(data.to_apply.excluded_imports)} imported jobs are left out of time to apply.
      </p>
      {data.providers.length === 0 ? null : (
        <table className="mt-3 text-sm">
          <caption className="label-micro pb-1 text-left text-fg-3">By provider</caption>
          <thead className="text-fg-3">
            <tr>
              <th className="pr-6 text-left font-normal">Provider</th>
              <th className="pr-6 text-right font-normal">Closed</th>
              <th className="pr-6 text-right font-normal">Never closed</th>
              <th className="pr-6 text-right font-normal">Median life</th>
              <th className="pr-6 text-right font-normal">90th percentile</th>
              <th className="pr-6 text-right font-normal">Median to apply</th>
              <th className="pr-6 text-right font-normal">Reopened</th>
              <th className="text-right font-normal">Urgent</th>
            </tr>
          </thead>
          <tbody className="text-fg">
            {data.providers.map((p) => (
              <tr key={p.provider}>
                <th scope="row" className="pr-6 text-left font-normal">
                  {p.provider}
                </th>
                <td className="pr-6 text-right tabular-nums">{formatCount(p.count)}</td>
                <td className="pr-6 text-right tabular-nums">{formatCount(p.never_closed)}</td>
                <td className="pr-6 text-right tabular-nums">{days(p.median_days)}</td>
                <td className="pr-6 text-right tabular-nums">{days(p.p90_days)}</td>
                <td className="pr-6 text-right tabular-nums">{days(p.to_apply.median_days)}</td>
                <td className="pr-6 text-right tabular-nums">{formatFraction(p.reopen_rate)}</td>
                <td className="text-right">{urgency(p.urgent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.companies.length === 0 ? null : (
        <table className="mt-3 text-sm">
          <caption className="label-micro pb-1 text-left text-fg-3">
            By company (at least 5 closed postings, most closed first)
          </caption>
          <thead className="text-fg-3">
            <tr>
              <th className="pr-6 text-left font-normal">Company</th>
              <th className="pr-6 text-left font-normal">Provider</th>
              <th className="pr-6 text-right font-normal">Closed</th>
              <th className="pr-6 text-right font-normal">Never closed</th>
              <th className="pr-6 text-right font-normal">Median life</th>
              <th className="text-right font-normal">90th percentile</th>
            </tr>
          </thead>
          <tbody className="text-fg">
            {data.companies.map((c) => (
              <tr key={`${c.provider}/${c.company}`}>
                <th scope="row" className="pr-6 text-left font-normal">
                  {c.company}
                </th>
                <td className="pr-6 text-fg-2">{c.provider}</td>
                <td className="pr-6 text-right tabular-nums">{formatCount(c.count)}</td>
                <td className="pr-6 text-right tabular-nums">{formatCount(c.never_closed)}</td>
                <td className="pr-6 text-right tabular-nums">{days(c.median_days)}</td>
                <td className="text-right tabular-nums">{days(c.p90_days)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
