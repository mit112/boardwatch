import { useEffect, useState } from "react";

import { getJdChanges } from "../api/client";
import type { JdChangeRow, JdChanges as JdChangesData } from "../api/types";
import { formatCount, isSafeHttpUrl } from "../lib/format";

/*
 * T309: postings whose JD changed after a résumé was built, and after an application was sent. The
 * two lists are never merged: a changed JD after a build means the tailored résumé may be stale;
 * after applying, a requirement may have been added that the application never answered.
 *
 * There is no version-diff view in the app, so the title links to the board's own posting and the
 * row names both version ids to compare. Imports with no recorded applied date are counted apart and
 * never compared.
 */

function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function Title({ row }: { row: JdChangeRow }) {
  const label = `${row.company} — ${row.title}`;
  if (row.url === null || !isSafeHttpUrl(row.url)) return <span className="text-fg">{label}</span>;
  return (
    <a
      href={row.url}
      target="_blank"
      rel="noopener noreferrer"
      title="Open the board's posting in a new tab."
      className="rounded-sm text-fg underline decoration-divider underline-offset-2 hover:decoration-fg-2"
    >
      {label}
    </a>
  );
}

function revisions(row: JdChangeRow, since: string): string {
  const n = row.revisions;
  return `${formatCount(n)} ${n === 1 ? "revision" : "revisions"} after ${since}, latest ${when(row.latest_revised_at)}`;
}

/** `refresh` changes whenever the applied list reloads, so a status change shows here too. */
export function JdChanges({ refresh }: { refresh?: unknown }) {
  const [data, setData] = useState<JdChangesData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getJdChanges())
      .then((d) => {
        if (!live) return;
        setData(d);
        setFailed(false);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [refresh]);

  if (failed) {
    return (
      <section aria-label="JD changes" className="rounded-md bg-surface p-4 text-sm text-fg-2">
        JD changes could not be loaded.
      </section>
    );
  }
  if (data === null) return null;
  const { built, applied } = data;

  return (
    <section aria-label="JD changes" className="rounded-md bg-surface p-4">
      <h2 className="text-base text-fg">JD changed after building or applying</h2>

      <h3 className="mt-3 text-sm text-fg">Changed after the résumé was built</h3>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(built.stale)} of {formatCount(built.checked)} postings with a tailored résumé
        were revised after the version it was built from, so that résumé may be stale.
        {built.stale > built.rows.length
          ? ` Showing the ${formatCount(built.rows.length)} most recently changed.`
          : ""}
      </p>
      {built.rows.length === 0 ? null : (
        <ul aria-label="Changed after building" className="mt-2 divide-y divide-divider text-sm">
          {built.rows.map((r) => (
            <li key={r.posting_id} className="py-1.5">
              <Title row={r} />{" "}
              <span className="text-fg-2">
                · built {when(r.built_at)} · {revisions(r, "the build")} · compare version{" "}
                {r.built_version_id} with {r.latest_version_id}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="mt-4 text-sm text-fg">Changed after the application was sent</h3>
      <p className="mt-1 text-sm text-fg-2">
        {formatCount(applied.changed)} of {formatCount(applied.checked)} dated applications are on a
        posting revised after they were sent, so a requirement may have been added.
        {applied.changed > applied.rows.length
          ? ` Showing the ${formatCount(applied.rows.length)} most recently changed.`
          : ""}{" "}
        {formatCount(applied.excluded_imports)} imported with no recorded applied date{" "}
        {applied.excluded_imports === 1 ? "was" : "were"} not compared
        {applied.no_posting_version > 0
          ? `, and ${formatCount(applied.no_posting_version)} name no posting version`
          : ""}
        .
      </p>
      {applied.rows.length === 0 ? null : (
        <ul aria-label="Changed after applying" className="mt-2 divide-y divide-divider text-sm">
          {applied.rows.map((r) => (
            <li key={r.application_id} className="py-1.5">
              <Title row={r} />{" "}
              <span className="text-fg-2">
                · sent {when(r.submitted_at)}, now {r.status} · {revisions(r, "applying")} · compare version{" "}
                {r.sent_version_id === null ? "(none captured)" : r.sent_version_id} with{" "}
                {r.latest_version_id}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
