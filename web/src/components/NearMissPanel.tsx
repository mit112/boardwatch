import { useEffect, useState } from "react";

import { getNearMisses } from "../api/client";
import type { NearMissRule, NearMissesResponse } from "../api/types";

/*
 * T303: the near-miss list. Open postings blocked by exactly one unmet requirement, grouped by that
 * requirement — where a ruling or a profile fact turns into applications. Read only: a ruling still
 * goes through policy.
 *
 * The cohort is narrowed to postings that pass the pipeline's title and location gates, so the
 * number is "real leads but for one requirement", not every posting with one unmet row. A posting
 * with that one unmet row AND an abstain on a blocking rule is counted apart and never added to the
 * near-miss count: an abstain is not a pass.
 *
 * This is the store as it stands now, not the run selected above.
 */

const CLAUSE_LABEL: Record<string, string> = {
  excluded_title: "an excluded title",
  remote_only: "not remote",
  non_us_location: "outside the target countries",
  foreign_ad_marker: "a foreign job ad",
  out_of_field: "outside the role taxonomy",
};

function RuleRow({ rule, peak }: { rule: NearMissRule; peak: number }) {
  return (
    <li className="flex flex-col gap-1">
      <div className="grid grid-cols-[minmax(0,22rem)_1fr_auto] items-center gap-3 text-sm">
        <span className="truncate text-fg" title={rule.rule_id}>
          {rule.rule_id}
        </span>
        <span aria-hidden="true" className="h-2 rounded-full bg-surface-3">
          <span
            className="block h-2 rounded-full bg-bad"
            style={{ width: `${String((rule.count / peak) * 100)}%` }}
          />
        </span>
        <span className="tabular-nums text-fg">
          {rule.count.toLocaleString()} near-misses
        </span>
      </div>
      {rule.requirements.length > 0 ? (
        <p className="text-xs text-fg-3">
          Asked:{" "}
          {rule.requirements
            .map((r) => `${r.text} (${r.count.toLocaleString()})`)
            .join(" · ")}
        </p>
      ) : null}
      {rule.with_abstain > 0 ? (
        <p className="text-xs text-fg-3">
          {rule.with_abstain.toLocaleString()} more have this one unmet
          requirement and an abstain on a blocking rule. Not counted above.
        </p>
      ) : null}
      {rule.samples.length > 0 ? (
        <details>
          <summary className="flex min-h-11 cursor-pointer items-center label-micro text-fg-3 transition-colors duration-150 ease-in-out hover:text-fg-2">
            sample postings
          </summary>
          <ul className="flex flex-col gap-2 pb-2">
            {rule.samples.map((s) => (
              <li key={s.posting_id} className="text-sm">
                <span className="text-fg">{s.title}</span>{" "}
                <span className="text-fg-2">· {s.company}</span>
                <blockquote className="mt-1 border-l border-divider pl-3 text-xs break-words text-fg-2">
                  {s.quote}
                </blockquote>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </li>
  );
}

export function NearMissPanel() {
  const [data, setData] = useState<NearMissesResponse | null>(null);
  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getNearMisses())
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
  if (data === null) return null;
  if (!data.available)
    return (
      <section aria-label="Near-miss list" className="text-sm text-fg-2">
        Near-misses are computed at the end of each nightly run; none has run yet.
      </section>
    );
  if (!data.profile) return null;

  const gatedOut = data.gated_out.reduce((sum, g) => sum + g.count, 0);
  const peak = data.rules[0]?.count || 1;

  return (
    <section aria-label="Near-miss list" className="flex flex-col gap-2">
      <h2 className="text-base text-fg">Near-misses: one unmet requirement</h2>
      <p className="text-xs text-fg-2">As of the end of run {data.run_id}.</p>
      <p className="text-sm text-fg-2">
        {data.near_misses.toLocaleString()} open postings that pass the title
        and location gates are blocked by exactly one unmet requirement and
        nothing undecided. Of {data.blocked.toLocaleString()} blocked postings,{" "}
        {data.one_unmet.toLocaleString()} hold exactly one blocking unmet
        requirement.
        {gatedOut > 0
          ? ` The gates left out ${gatedOut.toLocaleString()}: ${data.gated_out
              .map(
                (g) =>
                  `${g.count.toLocaleString()} ${CLAUSE_LABEL[g.clause] ?? g.clause}`,
              )
              .join(", ")}.`
          : ""}
        {data.with_abstain > 0
          ? ` ${data.with_abstain.toLocaleString()} more also abstain on a blocking rule and are not counted.`
          : ""}
      </p>
      {data.rules.length > 0 ? (
        <ol className="mt-1 flex flex-col gap-3" aria-label="Near-misses by rule">
          {data.rules.map((rule) => (
            <RuleRow key={rule.rule_id} rule={rule} peak={peak} />
          ))}
        </ol>
      ) : null}
    </section>
  );
}
