import { useEffect, useState } from "react";

import { getCompanyHiring } from "../api/client";
import type { CompanyHiring as CompanyHiringData } from "../api/types";
import { EM_DASH, formatAge, formatCount } from "../lib/format";

/*
 * T308: who posts steadily, and how much of it is eligible. Rows are sorted by eligible per week.
 * "New" is postings first seen inside the trailing window. "Eligible" is the posting's CURRENT
 * deterministic verdict, so it counts a posting that arrived in the window and reads eligible now;
 * an abstain is neither eligible nor ineligible and is not shown as either. Applied and withdrawn
 * are jobs, all time. With no profile there is no verdict, and the eligible columns read as dashes,
 * never zero. The first load after a run is slow (the server reads the whole evaluation table
 * once, then keeps the answer), so the loading line says so.
 */

function perWeek(value: number | null): string {
  return value == null
    ? EM_DASH
    : value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function CompanyHiring() {
  const [data, setData] = useState<CompanyHiringData | null>(null);
  const [failed, setFailed] = useState(false);
  const [watchedOnly, setWatchedOnly] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getCompanyHiring())
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
        aria-label="Company hiring"
        className="rounded-md bg-surface p-4 text-sm text-fg-2"
      >
        Company hiring could not be loaded.
      </section>
    );
  }
  if (data === null) {
    return (
      <section
        aria-label="Company hiring"
        className="rounded-md bg-surface p-4 text-sm text-fg-2"
      >
        Loading company hiring. The first load after a run can take a minute.
      </section>
    );
  }

  const weeks = data.window_days / 7;
  const rows = watchedOnly ? data.watched_rows : data.rows;

  return (
    <section aria-label="Company hiring" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">Company hiring</h2>
      <p className="mt-1 text-sm text-fg-2">
        Postings first seen in the last {formatCount(data.window_days)} days ({formatCount(weeks)}{" "}
        weeks): {formatCount(data.new)} new across {formatCount(data.companies)} companies
        {data.eligible === null ? "" : `, ${formatCount(data.eligible)} eligible now`}. Sorted by
        eligible per week, then new per week. Eligible is the current deterministic verdict;
        abstains are neither eligible nor ineligible and are not counted as either. Applied and
        withdrawn are jobs, all time; a job whose application was withdrawn counts under
        withdrawn, not applied.
      </p>
      {data.eligible_known ? null : (
        <p className="mt-1 text-sm text-fg">
          There is no profile, so no posting has a verdict: eligible is not measured.
        </p>
      )}
      <label className="mt-1 flex min-h-11 items-center gap-2 text-sm text-fg-2">
        <input
          type="checkbox"
          checked={watchedOnly}
          onChange={(event) => {
            setWatchedOnly(event.target.checked);
          }}
        />
        Watched companies only
      </label>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-fg-2">
          {watchedOnly
            ? "No watched company has a new posting in this window."
            : "No company has a new posting in this window."}
        </p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="text-sm">
            <caption className="label-micro pb-1 text-left text-fg-3">
              Top {formatCount(rows.length)} {watchedOnly ? "watched " : ""}companies
            </caption>
            <thead className="text-fg-3">
              <tr>
                <th className="pr-5 text-left font-normal">Company</th>
                <th className="pr-5 text-right font-normal">New / wk</th>
                <th className="pr-5 text-right font-normal">Eligible / wk</th>
                <th className="pr-5 text-right font-normal">New</th>
                <th className="pr-5 text-right font-normal">Eligible</th>
                <th className="pr-5 text-right font-normal">Applied</th>
                <th className="pr-5 text-right font-normal">Withdrawn</th>
                <th className="text-left font-normal">Newest open eligible role</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {rows.map((r) => (
                <tr key={r.company_id}>
                  <th scope="row" className="pr-5 text-left font-normal">
                    {r.company}
                    <span className="pl-2 text-xs text-fg-3">{r.provider}</span>
                  </th>
                  <td className="pr-5 text-right tabular-nums">{perWeek(r.new_per_week)}</td>
                  <td className="pr-5 text-right tabular-nums">{perWeek(r.eligible_per_week)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(r.new)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(r.eligible)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(r.applied)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(r.withdrawn)}</td>
                  <td className="text-left">
                    {r.newest_open_eligible === null ? (
                      EM_DASH
                    ) : (
                      <>
                        {r.newest_open_eligible.title}
                        <span className="pl-2 text-xs text-fg-3">
                          {formatAge(Math.floor(r.newest_open_eligible.age_days))}
                        </span>
                      </>
                    )}
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
