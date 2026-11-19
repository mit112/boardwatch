import { useEffect, useState } from "react";

import { getBuildEconomics } from "../api/client";
import type { BuildEconomics as BuildEconomicsData } from "../api/types";
import { EM_DASH, formatCount, formatFraction, formatTimestamp } from "../lib/format";
import { formatDuration } from "../lib/runTrends";

/*
 * T310: does building a résumé ahead of the fill session pay off? Each job counts once, at its first
 * delivery. A build that was never applied to is WASTED only once it has closed or the owner skipped
 * it: a lead still open is waiting, not wasted, and is left out of the settled rate. A lead delivered
 * only as an unrendered review-lane stub cost no build and is counted apart.
 *
 * No run stores a per-lead tailor time, so the cost is the run's whole tailor stage divided by what
 * it built: an average, and an upper bound. A run that was not timed, or built nothing, is a dash.
 */

export function BuildEconomics() {
  const [data, setData] = useState<BuildEconomicsData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getBuildEconomics())
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
      <section aria-label="Résumé build economics" className="rounded-md bg-surface p-4 text-sm text-fg-2">
        Résumé build economics could not be loaded.
      </section>
    );
  }
  // `Array.isArray`: an older server answers a path it does not know with another shape.
  if (data === null || !Array.isArray(data.runs) || !Array.isArray(data.boards)) return null;

  const { totals } = data;
  const wasted = totals.closed + totals.skipped;

  return (
    <section aria-label="Résumé build economics" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">Résumé build economics</h2>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(totals.built)} résumés built, one per job at its first delivery.{" "}
        {formatCount(totals.applied)} were applied to ({formatFraction(totals.apply_rate)}).{" "}
        <span className="text-fg">
          {formatCount(wasted)} were wasted: {formatCount(totals.closed)} closed without being
          applied to and {formatCount(totals.skipped)} skipped.
        </span>{" "}
        {formatCount(totals.open)} are still open and are not counted as wasted. Of the builds whose
        outcome is settled, {formatFraction(totals.settled_rate)} were applied to.
      </p>
      {data.not_rendered_leads === 0 ? null : (
        <p className="mt-1 text-sm text-fg-2">
          {formatCount(data.not_rendered_leads)} leads were delivered without a rendered PDF (an
          unrendered review stub or a failed compile), so no résumé was built for them and they are
          in none of these counts.
        </p>
      )}
      {data.applied_before_build_leads === 0 ? null : (
        <p className="mt-1 text-sm text-fg-2">
          {formatCount(data.applied_before_build_leads)} leads were applied to before their résumé
          was built, so the build was not what was sent and they are in none of these counts.
        </p>
      )}

      {data.boards.length === 0 ? null : (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Résumé builds by board">
          <table className="mt-3 text-sm">
            <caption className="label-micro pb-1 text-left text-fg-3">
              By board (the source that first delivered the job)
            </caption>
            <thead className="text-fg-3">
              <tr>
                <th className="pr-5 text-left font-normal">Board</th>
                <th className="pr-5 text-right font-normal">Built</th>
                <th className="pr-5 text-right font-normal">Applied</th>
                <th className="pr-5 text-right font-normal">Closed, not applied</th>
                <th className="pr-5 text-right font-normal">Skipped</th>
                <th className="pr-5 text-right font-normal">Still open</th>
                <th className="pr-5 text-right font-normal">Applied ÷ built</th>
                <th className="text-right font-normal">Applied ÷ settled</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {data.boards.map((b) => (
                <tr key={b.board}>
                  <th scope="row" className="pr-5 text-left font-normal">
                    {b.board}
                  </th>
                  <td className="pr-5 text-right tabular-nums">{formatCount(b.built)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(b.applied)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(b.closed)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(b.skipped)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatCount(b.open)}</td>
                  <td className="pr-5 text-right tabular-nums">{formatFraction(b.apply_rate)}</td>
                  <td className="text-right tabular-nums">{formatFraction(b.settled_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.runs.length === 0 ? null : (
        <details className="mt-3">
          <summary className="flex min-h-11 cursor-pointer items-center text-sm text-fg-2 hover:text-fg">
            The latest {formatCount(data.runs.length)} finished nightly runs, newest first (the totals above are all time)
          </summary>
          <p className="text-xs text-fg-3">
            Seconds per résumé is an average: the run&apos;s whole tailor stage divided by the
            résumés it built. No per-lead time is stored, and the stage also delivers review stubs
            and runs the gate backlog, so the real cost per résumé is lower.
          </p>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Résumé builds by run">
            <table className="mt-1 text-sm">
              <thead className="text-fg-3">
                <tr>
                  <th className="pr-5 text-left font-normal">Run</th>
                  <th className="pr-5 text-left font-normal">Finished</th>
                  <th className="pr-5 text-right font-normal">Built</th>
                  <th className="pr-5 text-right font-normal">Not rendered</th>
                  <th className="pr-5 text-right font-normal">Tailor stage</th>
                  <th className="text-right font-normal">Average per résumé</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                {data.runs.map((r) => (
                  <tr key={r.id}>
                    <th scope="row" className="pr-5 text-left font-normal">
                      {r.id}
                    </th>
                    <td className="pr-5 text-fg-2">{formatTimestamp(r.finished)}</td>
                    <td className="pr-5 text-right tabular-nums">{formatCount(r.built)}</td>
                    <td className="pr-5 text-right tabular-nums">{formatCount(r.not_rendered)}</td>
                    <td className="pr-5 text-right tabular-nums">
                      {r.tailor_seconds == null ? EM_DASH : formatDuration(r.tailor_seconds)}
                    </td>
                    <td className="text-right tabular-nums">
                      {r.seconds_per_resume == null ? EM_DASH : formatDuration(r.seconds_per_resume)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}
