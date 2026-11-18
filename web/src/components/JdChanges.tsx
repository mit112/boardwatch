import { useEffect, useState } from "react";

import { getJdChanges, getVersionDiff } from "../api/client";
import type { JdChangeRow, JdChanges as JdChangesData, VersionDiff } from "../api/types";
import { formatCount, isSafeHttpUrl } from "../lib/format";

/*
 * T309: postings whose JD changed after a résumé was built, and after an application was sent. The
 * two lists are never merged: a changed JD after a build means the tailored résumé may be stale;
 * after applying, a requirement may have been added that the application never answered.
 *
 * The title links to the board's own posting; "Compare version A with B" opens the line diff of the
 * two versions under the row (T316). Added and removed lines carry a + or − sign, never colour alone. Imports with no recorded applied date are counted apart and
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

const SIGN = { add: "+", del: "−", same: " ", hunk: "" } as const;
const SIGN_NAME = { add: "added: ", del: "removed: ", same: "", hunk: "" } as const;

function DiffLines({ diff }: { diff: VersionDiff }) {
  if (diff.lines.length === 0) {
    return <p className="mt-1 text-fg-2">No line differs between the two versions.</p>;
  }
  return (
    <ul
      aria-label={`Changes from version ${String(diff.from)} to ${String(diff.to)}`}
      className="mt-1 overflow-x-auto rounded-sm bg-surface-2 p-2 font-mono text-xs"
    >
      {diff.lines.map((l, i) => (
        <li
          key={i}
          className={`whitespace-pre-wrap break-words ${
            l.kind === "add" ? "text-ok" : l.kind === "del" ? "text-bad" : "text-fg-2"
          }`}
        >
          {l.kind === "hunk" ? (
            l.text
          ) : (
            <>
              <span aria-hidden="true">{SIGN[l.kind]} </span>
              <span className="sr-only">{SIGN_NAME[l.kind]}</span>
              {l.text}
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

/** The compare button and, once opened, the diff under the row. Fetched on first open only. */
function Compare({ row, from }: { row: JdChangeRow; from: number }) {
  const [open, setOpen] = useState(false);
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [failed, setFailed] = useState(false);
  const to = row.latest_version_id;

  function toggle() {
    const next = !open;
    setOpen(next);
    if (!next || diff !== null) return;
    setFailed(false);
    void Promise.resolve()
      .then(() => getVersionDiff(row.posting_id, from, to))
      .then(setDiff)
      .catch(() => {
        setFailed(true);
      });
  }

  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className="rounded-sm text-accent underline underline-offset-2"
      >
        Compare version {from} with {to}
      </button>
      {open ? (
        <div className="mt-1 text-xs" aria-live="polite">
          {failed ? (
            <p className="text-fg-2">The diff could not be loaded.</p>
          ) : diff === null ? (
            <p className="text-fg-2">Loading the diff…</p>
          ) : (
            <DiffLines diff={diff} />
          )}
        </div>
      ) : null}
    </>
  );
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
                · built {when(r.built_at)} · {revisions(r, "the version it was built from")} ·{" "}
              </span>
              <Compare key={`${String(r.posting_id)}:${String(r.built_version_id)}:${String(r.latest_version_id)}`} row={r} from={r.built_version_id} />
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
                · sent {when(r.submitted_at)}, now {r.status} · {revisions(r, "applying")} ·{" "}
                {r.sent_version_id === null
                  ? `no version was captured when it was sent (latest is version ${String(r.latest_version_id)})`
                  : null}
              </span>
              {r.sent_version_id === null ? null : <Compare key={`${String(r.posting_id)}:${String(r.sent_version_id)}:${String(r.latest_version_id)}`} row={r} from={r.sent_version_id} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
