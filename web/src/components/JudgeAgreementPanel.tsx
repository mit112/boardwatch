import { useEffect, useState } from "react";

import { getJudgeAgreement } from "../api/client";
import type { JudgeAgreement, JudgeAgreementRun } from "../api/types";

/*
 * T304: where the deterministic engine and the LLM judge read the same posting differently.
 * The judge promotes and a re-key demotes, so the movement is shown, not just a rate: a 3x3
 * matrix for the newest run per lane, the agreement over the last runs, and the final gate's
 * current splits with links to the postings.
 */

const VERDICTS = ["eligible", "uncertain", "ineligible", "none"] as const;
const LANE_LABEL: Record<string, string> = {
  final_gate: "Final gate (can block)",
  advisory: "Advisory extraction (cannot block)",
};

function Matrix({ run }: { run: JudgeAgreementRun }) {
  const cell = (d: string, j: string) =>
    run.cells.find((c) => c.deterministic === d && c.llm === j)?.count ?? 0;
  const rows = VERDICTS.filter((d) =>
    run.cells.some((c) => c.deterministic === d),
  );
  return (
    <table
      className="text-sm"
      aria-label={`Run ${String(run.run_id ?? "unknown")} agreement`}
    >
      <thead className="text-fg-3">
        <tr>
          <th className="pr-4 text-left font-normal">Engine \ judge</th>
          {VERDICTS.slice(0, 3).map((j) => (
            <th key={j} className="pr-4 text-right font-normal">
              {j}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="text-fg">
        {rows.map((d) => (
          <tr key={d}>
            <th scope="row" className="pr-4 text-left font-normal">
              {d === "none" ? "no engine verdict" : d}
            </th>
            {VERDICTS.slice(0, 3).map((j) => (
              <td
                key={j}
                className={`pr-4 text-right tabular-nums ${d === j ? "font-semibold" : ""}`}
              >
                {String(cell(d, j))}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function JudgeAgreementPanel() {
  const [data, setData] = useState<JudgeAgreement | null>(null);
  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getJudgeAgreement())
      .then((d) => {
        if (live) setData(d);
      })
      .catch(() => {
        /* Diagnostic, not page-critical. */
      });
    return () => {
      live = false;
    };
  }, []);
  if (data === null || Object.keys(data.lanes).length === 0) return null;

  return (
    <section
      aria-label="Engine and judge agreement"
      className="flex flex-col gap-3"
    >
      <h2 className="text-base text-fg">Deterministic engine vs LLM judge</h2>
      {Object.entries(data.lanes).map(([lane, runs]) => {
        const newest = runs[0];
        if (newest === undefined) return null;
        return (
          <div key={lane}>
            <h3 className="label-micro text-fg-3">
              {LANE_LABEL[lane] ?? lane}
            </h3>
            <p className="text-sm text-fg-2">
              Run {String(newest.run_id ?? "—")}: agreed on{" "}
              {newest.agree.toLocaleString()} of {newest.total.toLocaleString()}
              . Last {String(runs.length)} runs:{" "}
              {runs
                .map((r) =>
                  r.total === 0
                    ? "—"
                    : `${String(Math.round((r.agree / r.total) * 100))}%`,
                )
                .join(" · ")}
            </p>
            <Matrix run={newest} />
          </div>
        );
      })}
      <p className="text-sm text-fg-2">
        The final gate currently reads {data.final_gate_splits.toLocaleString()}{" "}
        postings differently from the engine.
        {data.split_rules.length > 0
          ? ` Engine rules unmet on those: ${data.split_rules.map((r) => `${r.rule_id} (${String(r.count)})`).join(", ")}.`
          : ""}
      </p>
      {data.splits.length > 0 ? (
        <ul className="text-sm" aria-label="Latest splits">
          {data.splits.map((s) => (
            <li key={s.posting_id}>
              <a
                className="text-accent underline underline-offset-4"
                href={`#/queue?lead=${String(s.posting_id)}`}
              >
                {s.title}
              </a>{" "}
              <span className="text-fg-2">
                · {s.company} · engine {s.deterministic}, judge {s.llm}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
