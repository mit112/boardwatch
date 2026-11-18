import type { FunnelAbstain, FunnelAbstainRule } from "../api/types";

/*
 * T301 and T302, from the funnel's own per-rule report (no new query: the run computed it once).
 *
 * T301 — which rules block the most: unmet requirement rows per rule, largest first.
 * T302 — every rule's met / unmet / ABSTAINED, in three columns that are never folded together
 * (the keystone invariant), with a rule that abstains on every row called out as a monitoring
 * failure rather than read as caution.
 *
 * Counts are requirement ROWS over the current evaluation of every open posting; one posting can
 * have several unmet rows, so these are not posting counts and the copy says so.
 */

const TOP = 15;

function pct(rate: number | null): string {
  return rate === null ? "—" : `${(rate * 100).toFixed(1)}%`;
}

export function flagFor(rule: FunnelAbstainRule): string | null {
  if (rule.not_applicable) return "not applicable to this profile";
  if (rule.fully_abstaining)
    return "abstains on every row: a monitoring failure, it can never decide";
  if (rule.never_fired) return "never fired";
  return null;
}

export function topBlockers(rules: FunnelAbstainRule[]): FunnelAbstainRule[] {
  return rules
    .filter((r) => r.unmet > 0)
    .sort((a, b) => b.unmet - a.unmet || a.rule_id.localeCompare(b.rule_id))
    .slice(0, TOP);
}

export function RuleDispositions({
  abstain,
}: {
  abstain: FunnelAbstain | undefined;
}) {
  if (abstain === undefined) {
    return (
      <p className="text-sm text-fg-2">
        This run's funnel predates the per-rule report.
      </p>
    );
  }
  const blockers = topBlockers(abstain.rules);
  const peak = blockers[0]?.unmet ?? 1;
  const flagged = abstain.rules.filter(
    (r) => flagFor(r) !== null && !r.not_applicable,
  );

  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Blocking rules">
        <h2 className="text-base text-fg">Why leads are not eligible</h2>
        <p className="text-sm text-fg-2">
          Unmet requirement rows per rule, over the current evaluation of every
          open posting. A posting can fail several rules, so these are rows, not
          postings.
        </p>
        <ol className="mt-2 flex flex-col gap-1 text-sm">
          {blockers.map((r) => (
            <li
              key={r.rule_id}
              className="grid grid-cols-[minmax(0,22rem)_1fr_auto] items-center gap-3"
            >
              <span className="truncate text-fg" title={r.rule_id}>
                {r.rule_id}
              </span>
              <span
                aria-hidden="true"
                className="h-2 rounded-full bg-surface-3"
              >
                <span
                  className="block h-2 rounded-full bg-bad"
                  style={{ width: `${String((r.unmet / peak) * 100)}%` }}
                />
              </span>
              <span className="tabular-nums text-fg">
                {r.unmet.toLocaleString()} unmet
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-label="Abstain rate per rule">
        <h2 className="text-base text-fg">Abstain rate per rule</h2>
        <p className="text-sm text-fg-2">
          {abstain.rule_count} rules over {abstain.total_rows.toLocaleString()}{" "}
          requirement rows. {abstain.fully_abstaining} abstain on every row,{" "}
          {abstain.never_fired} never fired.
          {abstain.out_of_catalog.length > 0
            ? ` ${String(abstain.out_of_catalog_rows)} rows name rules outside the catalog: ${abstain.out_of_catalog.join(", ")}.`
            : ""}
        </p>
        {flagged.length > 0 ? (
          <ul
            role="list"
            aria-label="Rules that cannot decide"
            className="mt-2 text-sm text-bad"
          >
            {flagged.map((r) => (
              <li key={r.rule_id}>
                {r.rule_id}: {flagFor(r)}
              </li>
            ))}
          </ul>
        ) : null}
        <div className="mt-2 overflow-x-auto">
          <table className="text-sm">
            <thead className="text-fg-3">
              <tr>
                <th className="pr-5 text-left font-normal">Rule</th>
                <th className="pr-5 text-right font-normal">Met</th>
                <th className="pr-5 text-right font-normal">Unmet</th>
                <th className="pr-5 text-right font-normal">Abstained</th>
                <th className="pr-5 text-right font-normal">Abstain rate</th>
                <th className="text-left font-normal">Note</th>
              </tr>
            </thead>
            <tbody className="text-fg">
              {abstain.rules.map((r) => (
                <tr key={r.rule_id}>
                  <th scope="row" className="pr-5 text-left font-normal">
                    {r.rule_id}
                  </th>
                  <td className="pr-5 text-right tabular-nums">
                    {r.met.toLocaleString()}
                  </td>
                  <td className="pr-5 text-right tabular-nums">
                    {r.unmet.toLocaleString()}
                  </td>
                  <td className="pr-5 text-right tabular-nums">
                    {r.abstained.toLocaleString()}
                  </td>
                  <td className="pr-5 text-right tabular-nums">
                    {pct(r.abstain_rate)}
                  </td>
                  <td className="text-fg-2">{flagFor(r) ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
