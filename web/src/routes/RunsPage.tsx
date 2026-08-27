import { useEffect, useState } from "react";

import { getFunnel, getRuns } from "../api/client";
import type { FunnelStage, RunFunnel, RunSummary } from "../api/types";
import { EM_DASH, formatCount, formatFraction, formatTimestamp } from "../lib/format";

function StageCard({ stage, last }: { stage: FunnelStage; last: boolean }) {
  return (
    <li className="relative pl-6">
      {/* The connector. Decorative only: it carries no meaning that is not also in the text. */}
      {last ? null : (
        <span
          aria-hidden="true"
          className="absolute top-3 left-[0.3125rem] h-full w-px bg-divider"
        />
      )}
      <span
        aria-hidden="true"
        className="absolute top-2.5 left-0 size-2.5 rounded-full border border-control bg-bg"
      />

      <div className="rounded border border-divider bg-surface p-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm text-fg">{stage.name}</h3>
          {stage.instrumented ? (
            <p className="text-sm text-fg-2 tabular-nums">
              {formatCount(stage.entered)} entered {"→"} {formatCount(stage.advanced)} advanced
            </p>
          ) : (
            <p className="text-sm text-fg-2">
              not instrumented — this stage reported nothing, which is not the same as measuring
              zero
            </p>
          )}
          {stage.derived ? (
            <span
              className="rounded border border-control px-1.5 py-0.5 text-[11px] tracking-wide text-fg-2 uppercase"
              title="One drop bucket is the remainder of the others, so this stage balances by construction. Bookkeeping, not evidence."
            >
              derived · bookkeeping
            </span>
          ) : null}
          {stage.reconciled === false ? (
            <span className="rounded border border-fg-2 px-1.5 py-0.5 text-[11px] tracking-wide text-fg uppercase">
              does not reconcile
            </span>
          ) : null}
        </div>

        {stage.note === "" ? null : <p className="mt-1 text-xs text-fg-3">{stage.note}</p>}

        {!stage.instrumented ? null : stage.drops.length === 0 ? (
          <p className="mt-2 text-xs text-fg-3">no drops recorded at this stage</p>
        ) : (
          <ul className="mt-2 divide-y divide-divider">
            {stage.drops.map((drop) => (
              <li key={drop.reason} className="flex items-baseline gap-3 py-1">
                <span className="w-24 shrink-0 text-right text-sm text-fg tabular-nums">
                  {drop.count.toLocaleString()}
                </span>
                <span className="text-sm text-fg-2">{drop.reason}</span>
                {drop.note === "" ? null : (
                  <span className="text-xs text-fg-3">{drop.note}</span>
                )}
              </li>
            ))}
          </ul>
        )}

        {stage.run_scoped_attribution === null ? null : (
          <p className="mt-2 text-xs text-fg-3">
            run-scoped attribution ·{" "}
            {Object.entries(stage.run_scoped_attribution)
              .map(([key, value]) => `${key} ${String(value)}`)
              .join(" · ")}
          </p>
        )}
      </div>
    </li>
  );
}

function CoverageBand({ funnel }: { funnel: RunFunnel }) {
  const cells: [string, string][] = [
    ["leads measured", formatCount(funnel.coverage.leads_measured)],
    ["with a fraction", formatCount(funnel.coverage.leads_with_fraction)],
    ["mean", formatFraction(funnel.coverage.mean_fraction)],
    ["median", formatFraction(funnel.coverage.median_fraction)],
  ];
  return (
    <section
      aria-label="Résumé coverage"
      className="flex flex-wrap items-stretch divide-x divide-divider rounded border border-divider bg-surface"
    >
      {cells.map(([label, value]) => (
        <div key={label} className="flex min-w-32 flex-col gap-1 px-4 py-3">
          <span className="text-[11px] tracking-wide text-fg-3 uppercase">{label}</span>
          <span className="text-lg text-fg-2 tabular-nums">{value}</span>
        </div>
      ))}
      <div className="flex flex-1 flex-col gap-1 px-4 py-3">
        <span className="text-[11px] tracking-wide text-fg-3 uppercase">most-missed terms</span>
        <span className="text-sm text-fg-2">
          {funnel.coverage.top_missing.length === 0
            ? EM_DASH
            : funnel.coverage.top_missing
                .map((item) => `${item.term} (${String(item.count)})`)
                .join(", ")}
        </span>
      </div>
    </section>
  );
}

function BoardsAccordion({ funnel }: { funnel: RunFunnel }) {
  return (
    <details className="rounded border border-divider bg-surface">
      <summary className="flex min-h-11 cursor-pointer items-center px-4 text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface-2">
        Boards ({funnel.sources.length.toLocaleString()})
      </summary>
      <div className="overflow-x-auto border-t border-divider">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] tracking-wide text-fg-3 uppercase">
              {["provider", "board", "source", "open", "unique", "assisted", "eligible", "leads"].map(
                (heading) => (
                  <th key={heading} className="px-3 py-2 text-left font-normal">
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-divider">
            {funnel.sources.map((source) => (
              <tr key={`${source.provider}:${source.board_slug}`}>
                <td className="px-3 py-1.5 text-fg-2">{source.provider}</td>
                <td className="px-3 py-1.5 text-fg">{source.board_slug}</td>
                <td className="px-3 py-1.5 text-fg-3">{source.company_source}</td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {source.open_postings.toLocaleString()}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {formatCount(source.unique)}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {formatCount(source.assisted)}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {source.eligible.toLocaleString()}
                </td>
                <td className="px-3 py-1.5 text-fg tabular-nums">
                  {source.leads.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [funnel, setFunnel] = useState<RunFunnel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getRuns()
      .then((response) => {
        setRuns(response.runs);
        setRunId(response.runs[0]?.id ?? null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load the run list.");
      });
  }, []);

  useEffect(() => {
    if (runId === null) return;
    let live = true;
    void getFunnel(runId)
      .then((response) => {
        if (live) setFunnel(response);
      })
      .catch((caught: unknown) => {
        if (live) {
          setError(
            caught instanceof Error ? caught.message : "Could not load that run's funnel artifact.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [runId]);

  const selected = runs?.find((run) => run.id === runId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] tracking-wide text-fg-3 uppercase">run</span>
          <select
            value={runId ?? ""}
            onChange={(event) => {
              setFunnel(null);
              setError(null);
              setRunId(Number(event.target.value));
            }}
            className="min-h-11 rounded border border-control bg-surface px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:border-fg-2"
          >
            {(runs ?? []).map((run) => (
              <option key={run.id} value={run.id}>
                {run.id} · {formatTimestamp(run.finished ?? run.started)} · {run.status ?? "unknown"}
              </option>
            ))}
          </select>
        </label>

        {selected === null ? null : (
          <dl className="flex flex-wrap items-stretch divide-x divide-divider rounded border border-divider bg-surface">
            {[
              ["boards", `${formatCount(selected.boards_complete)} / ${formatCount(selected.boards_attempted)}`],
              ["postings seen", formatCount(selected.postings_seen)],
              ["new", formatCount(selected.new_count)],
              ["leads", formatCount(selected.leads)],
            ].map(([label, value]) => (
              <div key={label} className="flex min-w-28 flex-col gap-1 px-4 py-2">
                <dt className="text-[11px] tracking-wide text-fg-3 uppercase">{label}</dt>
                <dd className="text-lg text-fg-2 tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      {error !== null ? (
        <p className="rounded border border-fg-2 bg-surface p-4 text-sm text-fg">{error}</p>
      ) : funnel === null ? (
        <p className="p-4 text-sm text-fg-2">Loading the run's funnel artifact…</p>
      ) : (
        <>
          {funnel.fatal || funnel.errors.length > 0 ? (
            <section className="rounded border border-fg-2 bg-surface p-4">
              <h2 className="text-sm text-fg">
                {funnel.fatal ? "This run ended fatally." : "This run recorded errors."}
              </h2>
              <ul className="mt-2 flex flex-col gap-1">
                {funnel.errors.map((message) => (
                  <li key={message} className="text-sm text-fg-2">
                    {message}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <CoverageBand funnel={funnel} />

          <section>
            <h2 className="mb-3 text-[11px] tracking-wide text-fg-3 uppercase">
              funnel · artifact v{funnel.artifact_version} ·{" "}
              {funnel.reconciles ? "reconciles" : "does NOT reconcile"}
            </h2>
            <ol className="flex flex-col gap-3">
              {funnel.stages.map((stage, index) => (
                <StageCard
                  key={stage.name}
                  stage={stage}
                  last={index === funnel.stages.length - 1}
                />
              ))}
            </ol>
          </section>

          <BoardsAccordion funnel={funnel} />
        </>
      )}
    </div>
  );
}
