import { useEffect, useState } from "react";

import { getRunTrends } from "../api/client";
import type { RunTrendPoint, RunTrends as RunTrendsData } from "../api/types";
import { EM_DASH, formatCount } from "../lib/format";
import { formatDuration, median, segments, slowReadout } from "../lib/runTrends";

/*
 * Sparklines over the last nightly runs: how long each took, which stage made a long one long,
 * and the three counts a night is judged by. Small multiples, each on its own scale from zero,
 * so a flat line means a steady stage and not a squeezed axis.
 *
 * A run that was not measured is a GAP in the line. The server sends `null`, the path breaks
 * there, and a lone point between two gaps is drawn as a dot — never joined across, never 0.
 */

const WIDTH = 160;
const HEIGHT = 28;
const PAD = 3;

function Sparkline({
  values,
  description,
}: {
  values: readonly (number | null)[];
  description: string;
}) {
  const parts = segments(values, WIDTH, HEIGHT, PAD);
  const last = values[values.length - 1] ?? null;
  const tail = last == null ? null : parts[parts.length - 1]?.at(-1);
  return (
    <svg
      role="img"
      aria-label={description}
      viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
      width={WIDTH}
      height={HEIGHT}
      className="shrink-0 text-fg-2"
    >
      <line
        x1={PAD}
        x2={WIDTH - PAD}
        y1={HEIGHT - PAD}
        y2={HEIGHT - PAD}
        stroke="currentColor"
        strokeOpacity={0.25}
      />
      {parts.map((points) =>
        points.length === 1 ? (
          <circle
            key={`${String(points[0]?.[0])}`}
            cx={points[0]?.[0]}
            cy={points[0]?.[1]}
            r={1.5}
            fill="currentColor"
          />
        ) : (
          <polyline
            key={`${String(points[0]?.[0])}`}
            points={points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinejoin="round"
          />
        ),
      )}
      {tail == null ? null : <circle cx={tail[0]} cy={tail[1]} r={2.5} className="fill-fg" />}
    </svg>
  );
}

interface Row {
  key: string;
  label: string;
  indent: boolean;
  values: (number | null)[];
  format: (value: number) => string;
}

function rowsFor(data: RunTrendsData): Row[] {
  const series = (pick: (run: RunTrendPoint) => number | null | undefined) =>
    data.runs.map((run) => pick(run) ?? null);
  const count = (value: number) => value.toLocaleString();
  return [
    { key: "length", label: "run length", indent: false, values: series((r) => r.seconds), format: formatDuration },
    ...data.stage_names.map((name) => ({
      key: `stage:${name}`,
      label: name,
      indent: true,
      values: series((r) => r.stage_seconds?.[name]),
      format: formatDuration,
    })),
    { key: "new", label: "new postings", indent: false, values: series((r) => r.new_count), format: count },
    { key: "eligible", label: "newly eligible", indent: false, values: series((r) => r.newly_eligible), format: count },
    { key: "built", label: "résumés built", indent: false, values: series((r) => r.resumes_built), format: count },
  ];
}

function Readout({ data }: { data: RunTrendsData }) {
  const slow = slowReadout(data.runs);
  if (slow === null) return null;
  const usual = formatDuration(slow.usual);
  if (!slow.slow) {
    return (
      <p className="text-sm text-fg-2">
        Run {slow.runId} took {formatDuration(slow.seconds)}, in line with the {usual} median.
      </p>
    );
  }
  return (
    <p className="text-sm text-fg">
      Run {slow.runId} took {formatDuration(slow.seconds)}, {slow.ratio.toFixed(1)}× the {usual}{" "}
      median.
      {slow.stage === null
        ? " It has no stage times, so the slow stage cannot be named."
        : ` Furthest over its usual: ${slow.stage.name}, ${formatDuration(slow.stage.seconds)} against ${formatDuration(slow.stage.usual)}.`}
    </p>
  );
}

type State = { kind: "loading" } | { kind: "ready"; data: RunTrendsData } | { kind: "failed" };

export function RunTrends() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    void getRunTrends()
      .then((data) => {
        if (live) setState({ kind: "ready", data });
      })
      .catch(() => {
        if (live) setState({ kind: "failed" });
      });
    return () => {
      live = false;
    };
  }, []);

  if (state.kind === "loading") return null;
  if (state.kind === "failed") {
    return (
      <p className="text-sm text-fg-3">
        Run trends could not be loaded. The runs below are unaffected.
      </p>
    );
  }
  const { data } = state;
  // `runs` is checked as well as `length`: an older server answers a path it does not know with
  // something other than this shape, and that must not throw inside the render.
  if (!Array.isArray(data.runs) || data.runs.length === 0) return null;

  return (
    <section
      aria-label="Run trends"
      className="flex flex-col gap-2 rounded-md border border-divider bg-surface px-4 py-3"
    >
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-sm text-fg">Run trends</h2>
        <span className="label-micro text-fg-3">
          last {data.runs.length.toLocaleString()} nightly {data.runs.length === 1 ? "run" : "runs"}
        </span>
      </div>
      <Readout data={data} />
      <ul className="divide-y divide-divider">
        {rowsFor(data).map((row) => {
          const last = row.values[row.values.length - 1] ?? null;
          const usual = median(row.values);
          const latest = last == null ? EM_DASH : row.format(last);
          const unmeasured = row.values.filter((value) => value == null).length;
          return (
            <li key={row.key} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-1.5">
              <span
                className={`w-36 shrink-0 text-sm ${row.indent ? "pl-4 text-fg-3" : "text-fg-2"}`}
              >
                {row.label}
              </span>
              <Sparkline
                values={row.values}
                description={`${row.label}, last ${String(row.values.length)} runs, latest ${latest}`}
              />
              <span className="w-24 shrink-0 text-sm text-fg tabular-nums">{latest}</span>
              <span className="text-xs text-fg-3 tabular-nums">
                {usual == null ? "not measured" : `median ${row.format(usual)}`}
                {unmeasured === 0 || usual == null
                  ? ""
                  : ` · ${formatCount(unmeasured)} not measured`}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
