import { useEffect, useState } from "react";

import { getWithdrawals } from "../api/client";
import type { Withdrawal } from "../api/types";

/*
 * T311: every withdrawal with its reason. Withdrawals show where gating let something through,
 * so the reason is the point. Two kinds, never merged: an application pulled back after it was
 * sent, and a lead declined before it was sent. Outcomes past "applied" are out of scope.
 */

function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function Withdrawals() {
  const [rows, setRows] = useState<Withdrawal[] | null>(null);
  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getWithdrawals())
      .then((r) => {
        if (live) setRows(r.withdrawals);
      })
      .catch(() => {
        /* The applied list above still shows each withdrawn row's status. */
      });
    return () => {
      live = false;
    };
  }, []);
  if (rows === null || rows.length === 0) return null;
  const after = rows.filter((r) => r.kind === "after_applying").length;
  const companies = new Set(rows.map((r) => r.company ?? "")).size;

  return (
    <section aria-label="Withdrawals" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">Withdrawals</h2>
      <p className="mt-1 text-sm text-fg-2">
        {rows.length} withdrawn across {companies}{" "}
        {companies === 1 ? "company" : "companies"}: {after} pulled back after
        applying, {rows.length - after} declined before sending.
      </p>
      <ul className="mt-2 divide-y divide-divider text-sm">
        {rows.map((r) => (
          <li key={r.application_id} className="py-1.5">
            <span className="text-fg">
              {r.company ?? "Unknown company"} — {r.title ?? "untitled"}
            </span>{" "}
            <span className="text-fg-2">
              ·{" "}
              {r.kind === "after_applying"
                ? `withdrawn ${r.days_after_applying === null ? "" : `${r.days_after_applying.toFixed(1)} days `}after applying`
                : "declined before sending"}{" "}
              · {when(r.withdrawn_at)}
            </span>
            <p className="text-fg-2">{r.note ?? "No reason recorded."}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
