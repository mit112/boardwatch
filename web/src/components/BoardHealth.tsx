import { useEffect, useState } from "react";

import { getBoardHealth } from "../api/client";
import type { BoardHealthProvider, BoardHealthResponse, BoardHealthRow } from "../api/types";
import { EM_DASH, formatCount, formatTimestamp } from "../lib/format";

/*
 * Board and provider health (T305): the boards that need an action, each with what to do, a
 * per-provider rollup, and the slowest boards. Everything is read from the store by
 * `GET /api/board-health`; this component decides nothing about a board's health, it prints
 * what the server decided. The one thing it does own is the unknown case: an `issue` this
 * bundle has never heard of renders as "unknown status", never as a dropped row.
 *
 * Advice, not a page failure: a failed or missing endpoint renders nothing, so the run page
 * above it is unaffected (same stance as `PipelineHealthStrip`).
 */

const KNOWN_ISSUES = new Set([
  "dead",
  "unreachable",
  "error",
  "mismatch",
  "partial",
  "empty",
  "unknown",
]);
const UNKNOWN_LABEL = "unknown status";
const UNKNOWN_ACTION = "the status is not recognised; check the board by hand";
const ROWS_SHOWN = 25;

const COUNT_COLUMNS: [keyof BoardHealthProvider, string][] = [
  ["dead", "dead"],
  ["unreachable", "unreachable"],
  ["error", "failing"],
  ["mismatch", "count mismatch"],
  ["partial", "partial"],
  ["empty", "empty"],
  ["unknown", "unknown"],
];

function seconds(value: number | null): string {
  return value == null ? EM_DASH : `${value.toFixed(1)} s`;
}

function label(row: BoardHealthRow): string {
  return KNOWN_ISSUES.has(row.issue) && row.label !== "" ? row.label : UNKNOWN_LABEL;
}

function action(row: BoardHealthRow): string {
  return KNOWN_ISSUES.has(row.issue) && row.action !== "" ? row.action : UNKNOWN_ACTION;
}

function detail(row: BoardHealthRow): string {
  const parts: string[] = [];
  if (row.last_health != null) parts.push(`probe ${row.last_health}`);
  if (row.scan_status != null) parts.push(`scan ${row.scan_status}`);
  if (row.missing != null && row.reported_total != null && row.enumerated != null) {
    parts.push(
      `board says ${formatCount(row.reported_total)}, scan counted ${formatCount(row.enumerated)}`,
    );
  }
  return parts.join(" · ");
}

export function BoardHealth() {
  const [data, setData] = useState<BoardHealthResponse | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let live = true;
    // `Promise.resolve().then` so a client mock with no such export is one rejected promise
    // here, not a throw during render of every page that mocks the client.
    void Promise.resolve()
      .then(() => getBoardHealth())
      .then((response) => {
        if (live) setData(response);
      })
      .catch(() => {
        /* Advice, not a page failure. */
      });
    return () => {
      live = false;
    };
  }, []);

  if (data === null) return null;
  const rows = showAll ? data.boards : data.boards.slice(0, ROWS_SHOWN);
  return (
    <section aria-label="Board health" className="flex flex-col gap-4">
      <h2 className="label-micro text-fg-3">
        board health · {formatCount(data.watched_boards)} watched boards ·{" "}
        {formatCount(data.boards.length)} need attention
      </h2>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Board health by provider</caption>
          <thead>
            <tr className="label-micro text-fg-3">
              <th scope="col" className="px-3 py-1 font-normal">
                provider
              </th>
              <th scope="col" className="px-3 py-1 text-right font-normal">
                boards
              </th>
              {COUNT_COLUMNS.map(([, heading]) => (
                <th key={heading} scope="col" className="px-3 py-1 text-right font-normal">
                  {heading}
                </th>
              ))}
              <th scope="col" className="px-3 py-1 text-right font-normal">
                listing gate skipped
              </th>
              <th scope="col" className="px-3 py-1 text-right font-normal">
                scan avg
              </th>
              <th scope="col" className="px-3 py-1 text-right font-normal">
                scan max
              </th>
            </tr>
          </thead>
          <tbody>
            {data.providers.map((p) => (
              <tr key={p.provider} className="border-t border-divider text-fg-2">
                <th scope="row" className="px-3 py-1 font-normal text-fg">
                  {p.provider}
                </th>
                <td className="px-3 py-1 text-right tabular-nums">{formatCount(p.boards)}</td>
                {COUNT_COLUMNS.map(([key]) => (
                  <td key={key} className="px-3 py-1 text-right tabular-nums">
                    {formatCount(p[key] as number)}
                  </td>
                ))}
                <td className="px-3 py-1 text-right tabular-nums">
                  {p.gated_postings === 0
                    ? EM_DASH
                    : `${formatCount(p.gated_postings)} on ${formatCount(p.gated_boards)}`}
                </td>
                <td className="px-3 py-1 text-right tabular-nums">{seconds(p.seconds_avg)}</td>
                <td className="px-3 py-1 text-right tabular-nums">{seconds(p.seconds_max)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-fg-3">
        The listing gate skips listings on purpose (a setting, not a failure), so it never makes a
        board need attention. Scan time is the latest scan that read the board.
      </p>

      {data.boards.length === 0 ? (
        <p role="status" className="text-sm text-fg-2">
          No watched board needs attention.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Boards that need attention</caption>
            <thead>
              <tr className="label-micro text-fg-3">
                {["board", "provider", "status", "what to do", "evidence", "scanned"].map((h) => (
                  <th key={h} scope="col" className="px-3 py-1 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={`${String(row.company_id)}:${row.issue}`}
                  data-issue={row.issue}
                  className="border-t border-divider align-top text-fg-2"
                >
                  <td className="px-3 py-1 text-fg">
                    {row.name}
                    <span className="block font-display text-xs text-fg-3">{row.slug}</span>
                  </td>
                  <td className="px-3 py-1">{row.provider}</td>
                  <td className="px-3 py-1 text-fg">{label(row)}</td>
                  <td className="px-3 py-1">{action(row)}</td>
                  <td className="px-3 py-1 text-xs">
                    {detail(row)}
                    {row.error == null || row.error === "" ? null : (
                      <span className="block break-words text-fg-3">{row.error}</span>
                    )}
                  </td>
                  <td className="px-3 py-1 text-xs tabular-nums">
                    {formatTimestamp(row.scanned_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.boards.length > ROWS_SHOWN && !showAll ? (
            <button
              type="button"
              onClick={() => {
                setShowAll(true);
              }}
              className="flex min-h-11 items-center text-sm text-fg-2 underline underline-offset-4 transition-colors duration-150 ease-in-out hover:text-fg"
            >
              Show all {formatCount(data.boards.length)} boards
            </button>
          ) : null}
        </div>
      )}

      {data.slowest.length === 0 ? null : (
        <div className="overflow-x-auto">
          <table className="w-full max-w-2xl text-left text-sm">
            <caption className="mb-1 text-left label-micro text-fg-3">slowest boards</caption>
            <tbody>
              {data.slowest.map((s) => (
                <tr key={s.company_id} className="border-t border-divider text-fg-2">
                  <td className="px-3 py-1 text-fg">{s.name}</td>
                  <td className="px-3 py-1">{s.provider}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{seconds(s.seconds)}</td>
                  <td className="px-3 py-1">{s.scan_status}</td>
                  <td className="px-3 py-1 text-xs tabular-nums">{formatTimestamp(s.scanned_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
