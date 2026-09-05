import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { getFunnel, getRuns } from "../api/client";
import type { FunnelStage, RunFunnel, RunSummary } from "../api/types";
import { EM_DASH, formatCount, formatFraction, formatTimestamp } from "../lib/format";

/*
 * Stage and drop notes are the decision log speaking to an engineer: "The stage D-016 exists
 * for: …", "D-006's silent degrade", with literal backticks around the identifiers. Two small
 * splitters render that as prose instead of as a paste.
 *
 * Deliberately NOT a markdown library. Backtick spans are the only markup these notes contain,
 * a dependency for that is the wrong trade in a bundle served off localhost, and a general
 * renderer would also interpret the `*` and `_` that appear in identifiers.
 */

/** `\`code\`` spans become `<code>`; everything else is text, never markup. */
function withCode(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(`[^`]+`)/).map((part, index) =>
    part.length > 1 && part.startsWith("`") && part.endsWith("`") ? (
      <code key={`${keyPrefix}:${String(index)}`} className="font-display text-fg-2">
        {part.slice(1, -1)}
      </code>
    ) : (
      part
    ),
  );
}

/**
 * The first sentence, and the rest. These notes lead with the answer and follow with the
 * argument, so the split is where the card stops being a readout and starts being a rationale.
 * A note with no sentence break is entirely first sentence and gets no disclosure.
 */
function splitFirstSentence(note: string): [string, string] {
  const match = /^(.*?[.!?])\s+(\S.*)$/s.exec(note);
  if (match === null) return [note, ""];
  return [match[1] ?? note, match[2] ?? ""];
}

/** A stage's wall clock. One decimal, tabular, in seconds throughout — the durations run from
 * fractions of a second to tens of minutes and a mixed unit makes two of them incomparable. */
function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

function StageNote({ name, note }: { name: string; note: string }) {
  const [lead, rest] = splitFirstSentence(note);
  return (
    <div className="mt-1">
      <p className="text-xs text-fg-3">{withCode(lead, `${name}:note`)}</p>
      {rest === "" ? null : (
        <details>
          <summary className="flex min-h-11 cursor-pointer items-center label-micro text-fg-3 transition-colors duration-150 ease-in-out hover:text-fg-2">
            why
          </summary>
          <p className="pb-1 text-xs text-fg-3">{withCode(rest, `${name}:why`)}</p>
        </details>
      )}
    </div>
  );
}

function StageCard({
  stage,
  last,
  seconds,
}: {
  stage: FunnelStage;
  last: boolean;
  seconds: number | undefined;
}) {
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

      <div className="rounded-md border border-divider bg-surface p-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm text-fg">{stage.name}</h3>
          {seconds === undefined ? null : (
            <p className="text-sm text-fg-2 tabular-nums">{formatSeconds(seconds)}</p>
          )}
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
              className="rounded-sm border border-control px-1.5 py-0.5 label-micro text-fg-2"
              title="One drop bucket is the remainder of the others, so this stage balances by construction. Bookkeeping, not evidence."
            >
              derived · bookkeeping
            </span>
          ) : null}
          {stage.reconciled === false ? (
            <span className="rounded-sm border border-fg-2 px-1.5 py-0.5 label-micro text-fg">
              does not reconcile
            </span>
          ) : null}
        </div>

        {stage.note === "" ? null : <StageNote name={stage.name} note={stage.note} />}

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
                  // Shown whole: a drop note is one clause, and hiding half of it would cost more
                  // than it saves. Its backticks are still backticks.
                  <span className="text-xs text-fg-3">
                    {withCode(drop.note, `${drop.reason}:note`)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}

        {stage.run_scoped_attribution == null ? null : (
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

function GateBand({ funnel }: { funnel: RunFunnel }) {
  /*
   * The T42 final gate: the only thing on this page that says whether the delivered slate was
   * judged at all, and STATE's own check for a run ("judged > 0, fatal absent") could not be read
   * off this page before it existed.
   *
   * An artifact older than the gate omits the key entirely, which is the same statement as a run
   * whose gate was never armed — both are answered in words rather than as a block of zeros, the
   * convention `gate_to_dict` goes out of its way to keep on the wire.
   */
  const gate = funnel.gate as RunFunnel["gate"] | undefined;
  if (gate == null || !gate.instrumented) {
    return (
      <section
        aria-label="Final eligibility gate"
        className="rounded-md border border-divider bg-surface px-4 py-3"
      >
        <span className="label-micro text-fg-3">final gate</span>
        <p className="mt-1 text-sm text-fg-2">
          not instrumented — no judge ran over this run&apos;s slate, which is not the same as
          judging nothing
        </p>
      </section>
    );
  }
  const failedOpen = gate.failed_open_batches ?? 0;
  const cells: [string, string, boolean][] = [
    ["judged", formatCount(gate.judged), false],
    ["eligible", formatCount(gate.eligible), false],
    ["ineligible", formatCount(gate.ineligible), false],
    ["uncertain", formatCount(gate.uncertain), false],
    ["failed open", formatCount(gate.failed_open_batches), failedOpen > 0],
  ];
  return (
    <section aria-label="Final eligibility gate" className="flex flex-col">
      <dl className="flex flex-wrap items-stretch divide-x divide-divider rounded-md border border-divider bg-surface">
        {cells.map(([label, value, emphasis]) => (
          <div key={label} className="flex min-w-32 flex-col gap-1 px-4 py-3">
            <dt className="label-micro text-fg-3">{label}</dt>
            <dd className={`text-lg tabular-nums ${emphasis ? "text-fg" : "text-fg-2"}`}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
      {/* Said in words as well as weighted. A fail-open batch is the one number here that changes
          what the reader does with the leads, and weight alone would carry the whole signal. */}
      {failedOpen > 0 ? (
        <p className="mt-1.5 text-sm text-fg-2">
          {formatCount(failedOpen)} {failedOpen === 1 ? "batch" : "batches"} failed open — those
          leads were delivered without a judge verdict.
        </p>
      ) : null}
    </section>
  );
}

function CoverageBand({ funnel }: { funnel: RunFunnel }) {
  /*
   * Unlike every other payload on this page, a funnel is read straight off DISK and passed through
   * unchanged, so its shape follows the artifact's AGE, not the API's version — older runs predate
   * both `coverage` and `run_scoped_attribution`. Only `RUNS_LIMIT = 20` keeps those artifacts out
   * of the selector today, and that constant was not chosen for this reason.
   */
  const coverage = funnel.coverage as RunFunnel["coverage"] | undefined;
  if (coverage == null) return null;
  const cells: [string, string][] = [
    ["leads measured", formatCount(coverage.leads_measured)],
    ["with a fraction", formatCount(coverage.leads_with_fraction)],
    ["mean", formatFraction(coverage.mean_fraction)],
    ["median", formatFraction(coverage.median_fraction)],
  ];
  return (
    <section
      aria-label="Résumé coverage"
      className="flex flex-wrap items-stretch divide-x divide-divider rounded-md border border-divider bg-surface"
    >
      {cells.map(([label, value]) => (
        <div key={label} className="flex min-w-32 flex-col gap-1 px-4 py-3">
          <span className="label-micro text-fg-3">{label}</span>
          <span className="text-lg text-fg-2 tabular-nums">{value}</span>
        </div>
      ))}
      <div className="flex flex-1 flex-col gap-1 px-4 py-3">
        <span className="label-micro text-fg-3">most-missed terms</span>
        <span className="text-sm text-fg-2">
          {coverage.top_missing.length === 0
            ? EM_DASH
            : coverage.top_missing
                .map((item) => `${item.term} (${String(item.count)})`)
                .join(", ")}
        </span>
      </div>
    </section>
  );
}

function LanesAccordion({ funnel }: { funnel: RunFunnel }) {
  /*
   * The JD-acquisition lanes. Deliberately not a funnel stage — a lane ADDS to the corpus, so its
   * attempts enter no stage's `entered` — which is exactly why nothing on this page showed them.
   *
   * `[]` is a run with no lane and renders nothing; `undefined` is an artifact older than the
   * block. The ten `counts` keys are printed WHOLE, zeros included: dropping the empty ones turns
   * a measured zero back into an absence, which is the confusion the catalog exists to end.
   */
  const lanes = funnel.lanes as RunFunnel["lanes"] | undefined;
  if (lanes == null || lanes.length === 0) return null;
  const headings = ["lane", "attempted", "resolved", "admitted", "refused", "fetch", "apply"];
  return (
    <details className="rounded-md border border-divider bg-surface">
      <summary className="flex min-h-11 cursor-pointer items-center px-4 text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface-2">
        Lanes ({lanes.length.toLocaleString()})
      </summary>
      <div className="overflow-x-auto border-t border-divider">
        <table className="w-full text-sm">
          <thead>
            <tr className="label-micro text-fg-3">
              {headings.map((heading) => (
                <th key={heading} className="px-3 py-2 text-left font-normal">
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          {lanes.map((lane) => (
            // One `tbody` per lane, so the outcome catalog stays attached to the row it belongs to
            // and the divider falls between lanes rather than between a lane and its own counts.
            <tbody key={lane.name} className="divide-y divide-divider border-t border-divider">
              <tr>
                <td className="px-3 py-1.5 text-fg">
                  {lane.name}
                  {lane.is_silent_outage ? (
                    <span className="ml-2 rounded-sm border border-fg-2 px-1.5 py-0.5 label-micro text-fg">
                      silent outage
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {lane.attempted.toLocaleString()}
                </td>
                <td className="px-3 py-1.5 text-fg tabular-nums">
                  {lane.resolved.toLocaleString()}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {lane.admitted.length.toLocaleString()}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {lane.refused.length.toLocaleString()}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {lane.fetch_seconds == null ? EM_DASH : formatSeconds(lane.fetch_seconds)}
                </td>
                <td className="px-3 py-1.5 text-fg-2 tabular-nums">
                  {lane.apply_seconds == null ? EM_DASH : formatSeconds(lane.apply_seconds)}
                </td>
              </tr>
              <tr>
                <td colSpan={headings.length} className="px-3 pb-2 text-xs text-fg-3">
                  {Object.entries(lane.counts)
                    .map(([outcome, count]) => `${outcome} ${count.toLocaleString()}`)
                    .join(" · ")}
                </td>
              </tr>
            </tbody>
          ))}
        </table>
      </div>
    </details>
  );
}

function BoardsAccordion({ funnel }: { funnel: RunFunnel }) {
  const [filter, setFilter] = useState("");
  // 670 rows on a live run, and the reader arrives knowing which board they came for. Matched
  // against the three identifying columns only — a number is found by reading the row, not by
  // typing it.
  const needle = filter.trim().toLowerCase();
  const shown =
    needle === ""
      ? funnel.sources
      : funnel.sources.filter((source) =>
          [source.provider, source.board_slug, source.company_source].some((field) =>
            field.toLowerCase().includes(needle),
          ),
        );
  return (
    <details className="rounded-md border border-divider bg-surface">
      <summary className="flex min-h-11 cursor-pointer items-center px-4 text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface-2">
        Boards ({funnel.sources.length.toLocaleString()})
      </summary>
      <label className="flex flex-wrap items-center gap-3 border-t border-divider px-4 py-2">
        <span className="label-micro text-fg-3">filter</span>
        <input
          type="search"
          value={filter}
          onChange={(event) => {
            setFilter(event.target.value);
          }}
          placeholder="provider, board or source"
          className="min-h-11 min-w-64 rounded-sm border border-control bg-bg px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:border-fg-2"
        />
        {needle === "" ? null : (
          <span className="text-sm text-fg-2 tabular-nums">
            {shown.length.toLocaleString()} of {funnel.sources.length.toLocaleString()}
          </span>
        )}
      </label>
      <div className="overflow-x-auto border-t border-divider">
        <table className="w-full text-sm">
          <thead>
            <tr className="label-micro text-fg-3">
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
            {shown.map((source) => (
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
            {shown.length > 0 ? null : (
              <tr>
                <td colSpan={8} className="px-3 py-2 text-sm text-fg-2">
                  no board matches that filter
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/**
 * How a run reads in the picker. `finished_at` NULL means only that nothing ever CLOSED the row
 * (`store/queries.finish_run`) — in flight, killed, or a standalone lane that raised — so
 * "running" is the narrowest true thing to say, and the status column says the same word for all
 * three. Before this, such a run printed its START time in the FINISH position with no marker.
 */
function runLabel(run: RunSummary): string {
  if (run.finished === null) {
    return `${run.id} · started ${formatTimestamp(run.started)} · running`;
  }
  return `${run.id} · ${formatTimestamp(run.finished)} · ${run.status ?? "unknown"}`;
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
  /* `stage_durations` names its own stages, and the two lists agree only by convention — a stage
   * the timer never marked simply has no duration, which is why this is a lookup and not a zip. */
  const durations = new Map(
    (funnel?.stage_durations ?? []).map((row) => [row.name, row.seconds] as const),
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="label-micro text-fg-3">run</span>
          <select
            value={runId ?? ""}
            onChange={(event) => {
              setFunnel(null);
              setError(null);
              setRunId(Number(event.target.value));
            }}
            className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:border-fg-2"
          >
            {(runs ?? []).map((run) => (
              <option key={run.id} value={run.id}>
                {runLabel(run)}
              </option>
            ))}
          </select>
        </label>

        {selected === null ? null : (
          <section aria-label="Run summary">
            <dl className="flex flex-wrap items-stretch divide-x divide-divider rounded-md border border-divider bg-surface">
              {(
                [
                  // Only on a run nothing has closed. A finished run's status is already in the
                  // picker, and a cell that reads "complete" on every other run is noise.
                  ...(selected.finished === null
                    ? ([["status", "running", false]] as [string, ReactNode, boolean][])
                    : []),
                  ["boards", `${formatCount(selected.boards_complete)} / ${formatCount(selected.boards_attempted)}`, false],
                  ["partial", formatCount(selected.boards_partial), false],
                  ["unchanged", formatCount(selected.boards_unchanged), false],
                  // The ONE cell in this row whose value changes what you should do about the run,
                  // and it was rendered in the same weight as the zeros beside it.
                  ["failed", formatCount(selected.boards_failed), (selected.boards_failed ?? 0) > 0],
                  ["postings seen", formatCount(selected.postings_seen), false],
                  ["new", formatCount(selected.new_count), false],
                  // The run's leads are a QUERY the other page can answer, and this was the only
                  // place on either page that knew which run a lead came from. Hash-routed, so
                  // the loopback server still needs no SPA fallback.
                  [
                    "leads",
                    (selected.leads ?? 0) > 0 ? (
                      <a
                        href={`#/queue?run=${String(selected.id)}`}
                        className="underline underline-offset-4 transition-colors duration-150 ease-in-out hover:text-fg"
                      >
                        {formatCount(selected.leads)}
                      </a>
                    ) : (
                      formatCount(selected.leads)
                    ),
                    false,
                  ],
                ] as [string, ReactNode, boolean][]
              ).map(([label, value, emphasis]) => (
                <div key={label} className="flex min-w-28 flex-col gap-1 px-4 py-2">
                  <dt className="label-micro text-fg-3">{label}</dt>
                  <dd className={`text-lg tabular-nums ${emphasis ? "text-fg" : "text-fg-2"}`}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}
      </div>

      {error !== null ? (
        // Announced, not just printed: this replaces the whole funnel with no other signal.
        <p role="alert" className="rounded-md border border-fg-2 bg-surface p-4 text-sm text-fg">
          {error}
        </p>
      ) : funnel === null ? (
        <p role="status" className="p-4 text-sm text-fg-2">
          Loading the run&apos;s funnel artifact…
        </p>
      ) : (
        <>
          {funnel.fatal !== null || funnel.errors.length > 0 ? (
            <section className="rounded-md border border-fg-2 bg-surface p-4">
              <h2 className="text-sm text-fg">
                {funnel.fatal === null ? "This run recorded errors." : "This run ended fatally."}
              </h2>
              {/* The reason, verbatim and selectable: it names the unaccounted posting ids, which
                  is the only part of a fatal a reader can act on. Mono because it is an artifact
                  string, not prose. */}
              {funnel.fatal === null ? null : (
                <p className="mt-2 font-display text-sm break-words text-fg">{funnel.fatal}</p>
              )}
              <ul className="mt-2 flex flex-col gap-1">
                {funnel.errors.map((message, index) => (
                  // Keyed on position AND text: two identical errors are two errors, and a
                  // message-keyed list silently renders one of them.
                  <li key={`${String(index)}:${message}`} className="text-sm text-fg-2">
                    {message}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <GateBand funnel={funnel} />

          <CoverageBand funnel={funnel} />

          <LanesAccordion funnel={funnel} />

          <section>
            <h2 className="mb-3 label-micro text-fg-3">
              funnel · artifact v{funnel.artifact_version} ·{" "}
              {funnel.reconciles ? "reconciles" : "does NOT reconcile"}
            </h2>
            {/* Bounded measure. At full width a stage card was a 1,568px box holding "38
                malformed_payload", with a `divide-y` rule running the whole way across it — the
                numbers and their labels ended up a screen apart. */}
            <ol className="flex max-w-5xl flex-col gap-3">
              {funnel.stages.map((stage, index) => (
                <StageCard
                  key={stage.name}
                  stage={stage}
                  last={index === funnel.stages.length - 1}
                  seconds={durations.get(stage.name)}
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
