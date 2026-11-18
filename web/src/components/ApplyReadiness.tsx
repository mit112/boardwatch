import { useEffect, useMemo, useState } from "react";

import { getCompanions } from "../api/client";
import type { AppliedRow, Companion } from "../api/types";
import { applicationPace } from "../lib/applicationPace";
import {
  applyReadiness,
  LOW_DAYS,
  type ReadinessEntry,
} from "../lib/applyReadiness";

/*
 * T296: fillable leads by board, dropped and waiting by reason, and days of capacity at the
 * trailing 7-day pace. The plan is a companion's report; the pace is this page's own rows, so the
 * pace line shows even with no companion installed.
 */

function Entries({
  heading,
  entries,
}: {
  heading: string;
  entries: ReadinessEntry[];
}) {
  if (entries.length === 0) return null;
  return (
    <div className="flex min-w-40 flex-1 flex-col gap-1">
      <h3 className="label-micro text-fg-3">{heading}</h3>
      <ul className="flex flex-col gap-0.5 text-sm text-fg-2">
        {entries.map((e) => (
          <li
            key={e.label}
            className="flex items-baseline justify-between gap-4"
          >
            <span>{e.label}</span>
            <span className="tabular-nums text-fg">
              {e.count.toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ApplyReadiness({ rows }: { rows: AppliedRow[] }) {
  const [companions, setCompanions] = useState<Companion[]>([]);
  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getCompanions())
      .then((c) => {
        if (live) setCompanions(c.companions);
      })
      .catch(() => {
        /* No plan shown rather than a wrong one; the pace line still stands. */
      });
    return () => {
      live = false;
    };
  }, []);

  const perDay = useMemo(
    () => applicationPace(rows, new Date()).average,
    [rows],
  );
  const r = applyReadiness(companions, perDay);
  const pace = `${perDay.toFixed(1)} applications a day over the last 7 days`;

  return (
    <section
      aria-label="Apply-lane readiness"
      className="rounded-md bg-surface p-4"
    >
      <h2 className="text-base text-fg">Ready to apply</h2>
      {r.source === null ? (
        <p className="mt-1 text-sm text-fg-2">
          No apply plan reported. Pace: {pace}.
        </p>
      ) : (
        <>
          <p className="mt-1 text-sm text-fg">
            <span className="tabular-nums">
              {r.fillableTotal.toLocaleString()}
            </span>{" "}
            fillable leads
            {r.days === null ? (
              <>
                {" "}
                · no applications in the last 7 days, so no capacity estimate
              </>
            ) : (
              <>
                {" "}
                · about{" "}
                <span className="tabular-nums">{r.days.toFixed(1)}</span> days
                at {pace}
              </>
            )}
          </p>
          {r.low ? (
            <p data-tone="amber" className="mt-1 text-sm text-warn">
              Under {String(LOW_DAYS)} days of ready leads.
            </p>
          ) : null}
          <p className="mt-1 text-xs text-fg-3">
            From {r.source}
            {r.updatedAt === null
              ? ""
              : `, updated ${new Date(r.updatedAt).toLocaleString()}`}
          </p>
          <div className="mt-3 flex flex-wrap gap-6">
            <Entries heading="Fillable by board" entries={r.fillable} />
            <Entries heading="Dropped by reason" entries={r.dropped} />
            <Entries heading="Waiting by reason" entries={r.waiting} />
          </div>
        </>
      )}
    </section>
  );
}
