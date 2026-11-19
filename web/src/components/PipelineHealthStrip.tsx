import { useEffect, useState } from "react";

import { getCompanions, getRuns } from "../api/client";
import { type HealthCell, pipelineHealth, type Tone, worstTone } from "../lib/pipelineHealth";

/*
 * One line on every page: the last nightly run, the last intraday pass and each companion's
 * last status (T293). The reason is always in words; the colour only repeats it.
 *
 * Checked on load and every minute. A failed check is silence, like `StaleViewerBanner`: the
 * pages below already say when the API itself is down.
 */

const CHECK_MS = 60_000;

const DOT: Record<Tone, string> = {
  green: "bg-ok",
  amber: "bg-warn",
  red: "bg-bad",
};

const WORD: Record<Tone, string> = { green: "OK", amber: "Stale", red: "Failed" };

export function PipelineHealthStrip() {
  const [cells, setCells] = useState<HealthCell[] | null>(null);

  useEffect(() => {
    let live = true;
    const check = () => {
      void Promise.resolve()
        .then(() => Promise.all([getRuns(), getCompanions()]))
        .then(([runs, companions]) => {
          if (live) setCells(pipelineHealth(runs.runs, companions.companions, new Date()));
        })
        .catch(() => {
          /* Advice, not a page failure. */
        });
    };
    check();
    const timer = window.setInterval(check, CHECK_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  if (cells === null) return null;
  const tone = worstTone(cells);
  return (
    <section
      aria-label="Pipeline health"
      data-tone={tone}
      className="mx-auto flex max-w-[100rem] flex-wrap items-center gap-x-5 gap-y-1 px-4 pt-3 sm:px-6 text-sm text-fg-2"
    >
      {cells.map((cell) => (
        <span key={cell.label} data-tone={cell.tone} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={`size-2 rounded-full ${DOT[cell.tone]}`} />
          <span className="font-medium text-fg">{cell.label}:</span>
          <span>
            <span className="sr-only">{WORD[cell.tone]}. </span>
            {cell.text}
          </span>
        </span>
      ))}
    </section>
  );
}
