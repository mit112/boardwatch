import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearJobFollowUp,
  getApplied,
  markApplied,
  openPdf,
  setJobFollowUp,
  unapply,
} from "../api/client";
import type { AppliedCounts, AppliedRow } from "../api/types";
import { Badge } from "../components/Badge";
import { FollowUpBadge } from "../components/FollowUpBadge";
import type { ToastRequest } from "../hooks/useToasts";
import {
  EM_DASH,
  formatDateWithYear,
  formatTimestampWithYear,
  isFollowUpDue,
  isSafeHttpUrl,
  pathFromFileUri,
} from "../lib/format";
import { matchesAppliedQuery, sortAppliedRows } from "../lib/sort";
import type { AppliedSortKey, AppliedSortState } from "../lib/sort";

/*
 * The applied history: the third page, and the only read-only one.
 *
 * A lead LEAVES the queue the moment it is marked applied, so before this page the recorded
 * applications were reachable only from `boardwatch track` or by reading the `_applied/` folder
 * tree. What it has to answer, with the page open during a recruiter call, is four things at once:
 * what was applied to, when, whether the requisition is still up, and which résumé went out.
 *
 * Everything on it is a read except two, and neither touches `applications` beyond the writer it
 * already had: the unmark is the queue's EXISTING inverse route (`unapply` ->
 * `mark_job_unapplied`), and the follow-up writes `app_state` through a route keyed on the JOB.
 * That second one exists because 58 of 61 applications here were IMPORTED and carry no posting the
 * queue delivered, so the queue's posting-keyed routes could not reach the rows this page is for.
 */

/** The date every row is read by. `submitted_at` is when the application was MADE; `created_at`
 *  only stands in where the first is absent, which is an attempt that never reached `applied`. */
function appliedLabel(row: AppliedRow): string {
  const stamp = row.submitted_at ?? row.created_at ?? null;
  // WITH the year: this list spans years and is sorted by this column, so a label without one
  // prints the same text for two applications twelve months apart.
  return formatTimestampWithYear(stamp);
}

/** A text field off the wire, or an em dash. `== null` and never `=== null`: an older server omits
 *  a key entirely, so the read is `undefined` and a tightened guard would print "undefined". */
function text(value: string | null | undefined): string {
  return value == null || value === "" ? EM_DASH : value;
}

/**
 * The title, linked at the board's own page where there is a safe URL to link at.
 *
 * `apply_url` was emitted and rendered nowhere, so an applied row offered no route back to the
 * requisition — which is what a reader on a recruiter call reaches for first. The TITLE carries it
 * rather than a fourth button: it already names the lead, so the link needs no second label and the
 * row grows no control.
 *
 * `isSafeHttpUrl` is the app's ONE decision about a third-party URL (see `ApplyLink`): anything
 * that is not `http(s)` — a `javascript:` URL above all — is shown as inert text.
 */
function TitleCell({ row }: { row: AppliedRow }) {
  const label = text(row.title);
  const url = row.apply_url ?? null;
  if (!isSafeHttpUrl(url) || url === null) {
    return <span {...(url === null ? {} : { title: `Not an http(s) URL: ${url}` })}>{label}</span>;
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="Open the board's page for this posting, in a new tab."
      className="rounded-sm underline decoration-divider underline-offset-2 transition-colors duration-[120ms] ease-snap hover:decoration-fg-2 hover:text-fg"
    >
      {label}
    </a>
  );
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: AppliedSortKey;
  sort: AppliedSortState;
  onSort: (key: AppliedSortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort.key === sortKey;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
      className={`px-3 py-2 font-normal ${align === "right" ? "text-right" : "text-left"}`}
    >
      <button
        type="button"
        onClick={() => {
          onSort(sortKey);
        }}
        title={`Sort by ${label}`}
        className={`inline-flex min-h-11 min-w-11 items-center gap-1 rounded-sm px-1 label-micro transition-colors duration-[120ms] ease-snap ${
          active ? "text-fg" : "text-fg-3 hover:text-fg-2"
        }`}
      >
        {label}
        {/* Always drawn, dimmed when the column is not the one sorting — the queue's header does
            the same, so an unsorted column still advertises that it can be sorted. */}
        <span aria-hidden="true" className={active ? "" : "opacity-50"}>
          {active ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}

/**
 * The posting's standing, in WORDS. A closed posting carries "closed" plus the date it went down,
 * never a colour and never a colour plus an icon (SC 1.4.1) — the reader has to be able to tell a
 * dead requisition from a live one in a screenshot, in a high-contrast theme, and read aloud.
 *
 * `unverifiable` is rendered as itself and never collapsed into either neighbour: it means the
 * posting is open on a board nothing currently enumerates, so "still open" was never measured
 * (D-324). Saying "open" there would assert a measurement nobody took.
 */
function PostingStanding({ row }: { row: AppliedRow }) {
  const status = row.posting_status ?? null;
  if (status == null) {
    // The server could not say. No badge is the honest render, exactly as it is on a queue row.
    return <span className="text-sm text-fg-3">{EM_DASH}</span>;
  }
  if (status === "closed") {
    const when = row.closed_at ?? null;
    return (
      <Badge
        label={when == null ? "closed" : `closed ${formatDateWithYear(when)}`}
        emphasis="strong"
        reason="The employer has taken this requisition down since the application was sent."
      />
    );
  }
  if (status === "unverifiable") {
    return (
      <Badge
        label="unverifiable"
        reason="Open on a board nothing enumerates, so 'still open' was never measured (D-324)."
      />
    );
  }
  return <span className="text-sm text-fg-2">open</span>;
}

/** The counts band. Every member of the server's status catalog, zeros included, so a 0 here is a
 *  measurement rather than a bucket the reader has to guess was absent. */
function CountsBand({
  counts,
  showing,
  dueOnly,
  onToggleDue,
}: {
  counts: AppliedCounts;
  showing: number;
  dueOnly: boolean;
  onToggleDue: () => void;
}) {
  /* `?? {}` and `?? 0`: a server older than a field omits it, and the band must draw the cells it
     CAN fill rather than blanking the page over the one it cannot. */
  const byStatus = counts.by_status ?? {};
  const cells: [string, string, string | undefined][] = [
    ["applications", (counts.total ?? 0).toLocaleString(), undefined],
    [
      "posting closed",
      (counts.posting_closed ?? 0).toLocaleString(),
      "Applied, and the employer has since taken the requisition down. Counts only the attempts that still read as submitted — a withdrawn one is not an application waiting on anybody.",
    ],
    ...Object.entries(byStatus).map(
      ([status, count]): [string, string, string | undefined] => [
        status,
        (count ?? 0).toLocaleString(),
        undefined,
      ],
    ),
  ];
  return (
    <section aria-label="Applied history status" className="flex flex-col">
      <dl className="flex flex-wrap items-stretch divide-x divide-divider rounded-md border border-divider bg-surface">
        {cells.map(([label, value, note]) => (
          <div key={label} className="flex min-w-28 flex-col gap-1 px-4 py-3">
            <dt className="label-micro text-fg-3">{label}</dt>
            <dd
              className="font-display text-lg text-fg-2 tabular-nums"
              {...(note ? { title: note } : {})}
            >
              {value}
            </dd>
          </div>
        ))}
        {/*
          * The one cell on this band that is a FILTER, so it is a real `<button>`: role, keyboard
          * operation and the app's focus ring come for free, and `aria-pressed` carries the on/off
          * state that no visual treatment conveys to a screen reader. The pressed treatment is the
          * app's own active idiom — a fill plus an inset accent bar plus brighter text, three
          * channels and never colour alone (SC 1.4.1).
          *
          * The accessible name STARTS with the label and the value, so Label in Name holds
          * (SC 2.5.3), and then names the action.
          *
          * Drawn only when the server sent the figure. `== null` and never `=== null`: a server
          * older than the field omits it, and the honest render for a count nobody took is no cell
          * — not a zero, which would claim a measurement, and not a crash.
          */}
        {counts.follow_up_due == null ? null : (
          <div className="flex min-w-28 flex-col gap-1 px-4 py-3">
            <dt className={`label-micro ${dueOnly ? "text-fg-2" : "text-fg-3"}`}>
              follow-up due
            </dt>
            <dd>
              <button
                type="button"
                aria-pressed={dueOnly}
                aria-label={`follow-up due ${counts.follow_up_due.toLocaleString()} — ${
                  dueOnly ? "showing only these, activate to clear" : "show only these"
                }`}
                title="Applications whose pinned follow-up date has arrived — today or earlier, on this machine's calendar. Counted once per job, however many attempts it holds. Click to show only these."
                onClick={onToggleDue}
                className={`inline-flex min-h-11 w-full cursor-pointer items-center rounded-sm px-1 font-display text-lg tabular-nums transition-colors duration-[120ms] ease-snap ${
                  dueOnly
                    ? "bg-surface-3 text-fg shadow-[inset_0_-2px_0_0_var(--color-accent)]"
                    : "text-fg-2 hover:bg-surface-2"
                }`}
              >
                {counts.follow_up_due.toLocaleString()}
              </button>
            </dd>
          </div>
        )}
        {/* The only cell that answers "did my search match anything", so it is announced: a count
            that changes silently is a change a screen-reader reader never learns about (SC 4.1.3). */}
        <div
          role="status"
          className="ml-auto flex items-center px-4 py-3 text-sm text-fg-2 tabular-nums"
        >
          Showing {showing.toLocaleString()} of {(counts.total ?? 0).toLocaleString()}
        </div>
      </dl>
    </section>
  );
}

function RowAction({
  label,
  title,
  busy,
  onClick,
  ariaLabel,
  disabled = false,
}: {
  label: string;
  title: string;
  busy: boolean;
  onClick: () => void;
  /* Names the row in the accessible name. A column of 60 buttons all called "Clear" tells a
     screen-reader reader nothing about which application it would act on. */
  ariaLabel?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      aria-busy={busy}
      {...(ariaLabel ? { "aria-label": ariaLabel } : {})}
      title={title}
      className="inline-flex min-h-11 items-center rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg disabled:text-fg-3"
    >
      {label}
    </button>
  );
}

/**
 * The follow-up column: what is pinned, and the controls to pin or drop it.
 *
 * This is the surface the feature was missing. A follow-up survives `mark_job_applied` in the
 * store, but `queue_payload` is built on `delivered_unapplied` — so an applied lead was in neither
 * lane and nothing showed its date or let the owner set one, while the applied lead ("applied
 * 09-17, chase on 10-01") is exactly the one a follow-up is for.
 *
 * **The write is on BLUR and on Enter, not on every keystroke.** A `<input type="date">` fires
 * `change` for every value that is momentarily COMPLETE, so typing the year after the month and
 * day fires at `0002-09-20`, `0020-09-20`, `0202-09-20` and only then `2026-09-20` — four writes
 * and four undo toasts for one intention, with the stored value decided by response ordering. The
 * input is therefore uncontrolled and remounted (`key`) whenever the STORED date changes, so it
 * always shows what the store holds without a keystroke being able to write an intermediate one.
 *
 * EVERY row gets the input, including one the queue never delivered: the write is keyed on the
 * job, which every application has, and the store has only ever held one date per job. This is
 * unlike the unmark beside it, which really does need a delivered posting id.
 */
function FollowUpCell({
  row,
  onCommit,
  onClear,
}: {
  row: AppliedRow;
  onCommit: (row: AppliedRow, date: string) => void;
  onClear: (row: AppliedRow) => void;
}) {
  const pinned = row.follow_up ?? null;
  const named = `${text(row.company)} — ${text(row.title)}`;
  return (
    <span className="flex flex-wrap items-center gap-2">
      <FollowUpBadge followUp={row.follow_up} />
      {/* No visible label per row — the column header names the field and 60 repeated "Follow up
          on" labels would be noise — so the accessible name carries the company and the title,
          which is what tells a screen-reader reader WHICH row this input belongs to. */}
      <input
        key={pinned ?? ""}
        type="date"
        defaultValue={pinned ?? ""}
        aria-label={`Follow up on ${named}`}
        onBlur={(event) => {
          onCommit(row, event.target.value);
        }}
        onKeyDown={(event) => {
          // Enter commits, so the keyboard path does not depend on moving focus away.
          if (event.key === "Enter") event.currentTarget.blur();
        }}
        className="min-h-11 rounded-sm border border-control bg-surface px-2 text-sm text-fg tabular-nums"
      />
      <RowAction
        label="Clear"
        ariaLabel={`Clear follow-up for ${named}`}
        title="Remove this application's follow-up date."
        busy={false}
        disabled={pinned == null}
        onClick={() => {
          onClear(row);
        }}
      />
    </span>
  );
}

export function AppliedPage({ push }: { push: (request: ToastRequest) => void }) {
  const [rows, setRows] = useState<AppliedRow[] | null>(null);
  const [counts, setCounts] = useState<AppliedCounts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  /* Newest first, which is the order the payload already arrives in — so the default sort agrees
     with the server rather than re-ordering the list on first paint. */
  const [sort, setSort] = useState<AppliedSortState>({ key: "date", direction: "desc" });
  /* The applications a write is in flight for. Drives the button's disabled + `aria-busy` state,
     so a click has visible feedback before the round trip returns (Nielsen #1). */
  const [busy, setBusy] = useState<ReadonlySet<number>>(new Set());
  /* The band's one facet. Not stored in the URL or `sessionStorage`: the queue's facets are, and
     this page has no deep-link contract to keep — one piece of state, cleared by a reload. */
  const [dueOnly, setDueOnly] = useState(false);

  const load = useCallback(
    () =>
      getApplied()
        .then((response) => {
          setRows(response.rows);
          setCounts(response.counts);
          setError(null);
        })
        .catch((caught: unknown) => {
          setError(
            caught instanceof Error ? caught.message : "Could not load the applied history.",
          );
        }),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const onSort = useCallback((key: AppliedSortKey) => {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : // A new column starts descending on the date and ascending on the two text columns,
          // which is "most recent first" and "A first" — the reading each one is wanted in.
          { key, direction: key === "date" ? "desc" : "asc" },
    );
  }, []);

  const mark = useCallback(
    (id: number, inFlight: boolean) => {
      setBusy((current) => {
        const next = new Set(current);
        if (inFlight) next.add(id);
        else next.delete(id);
        return next;
      });
    },
    [],
  );

  /*
   * The optimistic half of a follow-up, patched on the JOB and not on the row. The store holds ONE
   * date per job (`queue.followup.<job_id>`), so a job with two attempts shows two rows that must
   * move together — patching only the clicked row would put two dates on screen for one stored
   * value.
   */
  const applyFollowUp = useCallback((jobId: number, value: string | null) => {
    setRows((current) =>
      current === null
        ? current
        : current.map((row) => (row.job_id === jobId ? { ...row, follow_up: value } : row)),
    );
  }, []);

  /*
   * Pin a follow-up date, or drop one, on the JOB — the id every row here has, and the id the
   * store has always keyed the date under. The undo restores the PREVIOUS value through the same
   * two routes rather than repainting the row, so a toast that says it put the old date back has
   * actually written it: the rule `unapply` established for the applied toast.
   *
   * `load()` follows a settled write because the band's `follow_up_due` is the SERVER's figure,
   * counted once per job and gated on the submitted statuses — a client-side recount here would
   * be a second copy of that rule, and this page already refetches after its other write.
   */
  const writeFollowUp = useCallback(
    (row: AppliedRow, next: string | null) => {
      /*
       * An EMPTY value writes nothing, and clearing is the button beside the input. A date input
       * reports `value === ""` for any incomplete date, so routing "" to a clear would let an
       * in-progress edit silently drop the stored date and then write a second one.
       */
      if (next === "") return;
      const previous = row.follow_up ?? null;
      if (previous === next) return;
      applyFollowUp(row.job_id, next);
      const named = `${text(row.company)} — ${text(row.title)}`;
      const write = (value: string | null): Promise<unknown> =>
        value === null ? clearJobFollowUp(row.job_id) : setJobFollowUp(row.job_id, value);
      void write(next)
        .then(() => {
          push({
            message:
              next === null
                ? `Cleared the follow-up on ${named}`
                : `Follow up on ${named} on ${next}`,
            undo: () => {
              applyFollowUp(row.job_id, previous);
              void write(previous)
                .then(() => load())
                .catch((caught: unknown) => {
                  applyFollowUp(row.job_id, next);
                  push({
                    message:
                      caught instanceof Error
                        ? caught.message
                        : "Could not undo that follow-up.",
                    tone: "error",
                  });
                });
            },
          });
          return load();
        })
        .catch((caught: unknown) => {
          applyFollowUp(row.job_id, previous);
          push({
            message:
              caught instanceof Error
                ? caught.message
                : "The write failed and the date was restored.",
            tone: "error",
          });
        });
    },
    [applyFollowUp, load, push],
  );

  /** Clearing is its own control, so it is its own callback rather than an inline arrow that
   *  would be a new identity on every render of every row. */
  const onClearFollowUp = useCallback(
    (row: AppliedRow) => {
      writeFollowUp(row, null);
    },
    [writeFollowUp],
  );

  /*
   * The page's one write: the queue's EXISTING `unapplied` route, whose undo is the queue's
   * existing `applied` route. Both refetch rather than patching the row in place, so the band and
   * the row always agree and the count logic lives in exactly one place — the server.
   *
   * `outcome === "unchanged"` is reported as itself. `mark_job_unapplied` answers that for an
   * attempt that does not read as applied (still `interested`, already `withdrawn`), and a toast
   * claiming a withdrawal there would be a false statement about what the click did.
   */
  const onUnmark = useCallback(
    (row: AppliedRow) => {
      const postingId = row.posting_id;
      if (postingId == null) return;
      mark(row.application_id, true);
      void unapply(postingId)
        .then((result) => {
          if (result.outcome === "unchanged") {
            push({
              message: `Nothing to withdraw for ${text(row.company)} — that attempt does not read as applied.`,
            });
            return;
          }
          push({
            message: `Withdrawn: ${text(row.company)} — ${text(row.title)}. Undo marks it applied again.`,
            undo: () => {
              void markApplied(postingId)
                .then(() => load())
                .catch((caught: unknown) => {
                  push({
                    message:
                      caught instanceof Error
                        ? caught.message
                        : "Could not mark that application applied again.",
                    tone: "error",
                  });
                });
            },
          });
          return load();
        })
        .catch((caught: unknown) => {
          push({
            message:
              caught instanceof Error
                ? caught.message
                : "Could not withdraw that application.",
            tone: "error",
          });
        })
        .finally(() => {
          mark(row.application_id, false);
        });
    },
    [push, load, mark],
  );

  const visible = useMemo(() => {
    const needle = query.trim();
    const matched = (rows ?? []).filter(
      (row) =>
        matchesAppliedQuery(row, needle.toLowerCase()) &&
        // `isFollowUpDue` is `<= today` on the BROWSER's calendar, which is the server's own: the
        // viewer only ever talks to loopback. It guards `== null`, so a row from a server that
        // omits the field is simply not due rather than a throw.
        (!dueOnly || isFollowUpDue(row.follow_up)),
    );
    return sortAppliedRows(matched, sort);
  }, [rows, query, sort, dueOnly]);

  if (error !== null) {
    // Announced, not merely printed: this replaces the whole page with no other signal.
    return (
      <p role="alert" className="rounded-md border border-fg-2 bg-surface p-4 text-sm text-fg">
        {error}
      </p>
    );
  }
  if (rows === null || counts === null) {
    return (
      <p role="status" className="p-4 text-sm text-fg-2">
        Loading the applied history…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <CountsBand
        counts={counts}
        showing={visible.length}
        dueOnly={dueOnly}
        onToggleDue={() => {
          setDueOnly((current) => !current);
        }}
      />

      <label className="flex min-w-64 max-w-md flex-col gap-1.5">
        <span className="label-micro text-fg-3">Filter company, title, location</span>
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          placeholder="e.g. acme, backend, austin"
          className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
        />
      </label>

      {/* A real `<table>` with real `<th scope="col">`, and the stickiness on the header cells
          themselves (`ux-table-sticky`): a duplicated absolutely-positioned header row would
          break the row/column association a screen reader navigates by. Borders are rationed to
          the divider between rows and the line under the header (`ux-table-scannable`) — padding
          does the rest of the separating. */}
      <div className="overflow-x-auto rounded-md bg-surface shadow-[0_1px_0_0_var(--color-divider)_inset,0_16px_40px_-24px_rgb(0_0_0/0.9)]">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Every application boardwatch has recorded, newest first.
          </caption>
          <thead>
            <tr className="sticky top-header z-10 bg-surface label-micro text-fg-3 [&>*]:border-b [&>*]:border-divider">
              <SortHeader
                label="applied"
                sortKey="date"
                sort={sort}
                onSort={onSort}
                align="right"
              />
              <SortHeader label="company" sortKey="company" sort={sort} onSort={onSort} />
              <th scope="col" className="px-3 py-2 text-left font-normal">
                title
              </th>
              <th scope="col" className="px-3 py-2 text-left font-normal">
                location
              </th>
              <th scope="col" className="px-3 py-2 text-left font-normal">
                status
              </th>
              <SortHeader
                label="posting"
                sortKey="posting_status"
                sort={sort}
                onSort={onSort}
              />
              <th scope="col" className="px-3 py-2 text-left font-normal">
                source
              </th>
              <SortHeader label="follow up" sortKey="follow_up" sort={sort} onSort={onSort} />
              <th scope="col" className="px-3 py-2 text-right font-normal">
                actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-divider">
            {visible.map((row) => {
              /* The absolute path behind the delivered PDF, which is what both the macOS and the
                 Windows upload dialog accept pasted. `pathFromFileUri` guards `== null`, so a
                 server that never learned to send `pdf_uri` costs the tooltip and nothing else. */
              const pdfPath = pathFromFileUri(row.pdf_uri ?? null);
              const postingId = row.posting_id ?? null;
              const inFlight = busy.has(row.application_id);
              return (
                <tr key={row.application_id} className="hover:bg-surface-2">
                  <td className="px-3 py-1.5 text-right whitespace-nowrap text-fg tabular-nums">
                    {appliedLabel(row)}
                  </td>
                  <td className="px-3 py-1.5 text-fg">{text(row.company)}</td>
                  <td className="px-3 py-1.5 text-fg-2">
                    <TitleCell row={row} />
                  </td>
                  <td className="px-3 py-1.5 text-fg-3">{text(row.location)}</td>
                  <td className="px-3 py-1.5">
                    {/* Verbatim off the wire and never indexed into a map, so a status this
                        bundle has never heard of reads as itself instead of throwing. */}
                    <Badge label={text(row.status)} />
                  </td>
                  <td className="px-3 py-1.5">
                    <PostingStanding row={row} />
                  </td>
                  <td className="px-3 py-1.5 text-fg-3">{text(row.source)}</td>
                  <td className="px-3 py-1.5">
                    <FollowUpCell row={row} onCommit={writeFollowUp} onClear={onClearFollowUp} />
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="flex flex-wrap items-center justify-end gap-2">
                      {/* Offered exactly when `GET /api/pdf/<posting_id>` would serve it: the
                          server probes the canonical artifact, and there is no posting id to ask
                          with on a row the queue never delivered. */}
                      {row.pdf_available === true && postingId != null ? (
                        <RowAction
                          label="Open PDF"
                          title={
                            pdfPath == null
                              ? "Opens inline, in a new tab."
                              : `Opens inline, in a new tab · ${pdfPath}`
                          }
                          busy={false}
                          onClick={() => {
                            void openPdf(postingId).catch((caught: unknown) => {
                              push({
                                message:
                                  caught instanceof Error
                                    ? caught.message
                                    : "Could not open the PDF.",
                                tone: "error",
                              });
                            });
                          }}
                        />
                      ) : null}
                      {postingId == null ? (
                        /* No posting id, so neither control has one to act on. Said in words
                           rather than left as two missing buttons the reader cannot account for. */
                        <span className="text-xs text-fg-3">
                          never delivered — no résumé, no unmark
                        </span>
                      ) : row.can_unmark === true ? (
                        <RowAction
                          label="Unmark applied"
                          title="Withdraws the application record and returns the lead to the queue. Undoable from the toast."
                          busy={inFlight}
                          onClick={() => {
                            onUnmark(row);
                          }}
                        />
                      ) : (
                        /* The write is per JOB — it withdraws the job's LATEST attempt — so on any
                           other attempt the control would act on a row the reader did not click.
                           The server's own answer decides (`can_unmark`), and `=== true` withholds
                           it for a server that never learned to send the field. The RULE is stated
                           rather than which half of it this row failed: the page cannot tell an
                           earlier attempt from a latest one that no longer reads as submitted, and
                           guessing between them would put words on the row the payload cannot
                           support. */
                        <span className="text-xs text-fg-3">
                          no unmark — only a job&apos;s latest attempt, still reading as submitted,
                          can be withdrawn
                        </span>
                      )}
                    </span>
                  </td>
                </tr>
              );
            })}
            {visible.length > 0 ? null : (
              <tr>
                <td colSpan={9} className="mx-auto px-4 py-10 text-center text-sm text-fg-2">
                  {/* The lever that would bring rows back, named for the filter that hid them.
                      The search box is tested first because it is the one the reader typed into;
                      with no text in it and rows on the wire, the facet is the only thing left
                      that can have emptied the list. */}
                  {rows.length === 0
                    ? "Nothing applied yet — mark a lead applied from the queue, or `boardwatch track add <posting_id>`."
                    : query.trim() !== ""
                      ? "No application matches that search. Clear the text box to see them all."
                      : "No application's follow-up date has arrived. Take the follow-up due cell again to see them all."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
