import type { ReactNode } from "react";

import { Icon } from "./Icon";

/*
 * The top of the job list: where to start, what has moved, what you have done.
 *
 * It replaces a band of sixteen pipeline counters. The three things a person opens this page to
 * learn are all here and all in one short line each:
 *
 *   new         what arrived since the last visit, as a filter you can switch on
 *   recorded    applications you recorded today and in the past 7 days — YOUR effort, counted from
 *               the same ledger the Applied page reads, so it stays visible while employers answer
 *   attention   only what is actionable now (a follow-up date has arrived; an application has had
 *               no update recorded for weeks) — and nothing at all when nothing is
 *
 * The pipeline's own counts (eligible, uncertain, gate, ineligible, closed, lane copies...) are one
 * click away under "Pipeline counts" at the foot of the list, not gone.
 *
 * No streaks, no goals, no countdown, and no number that goes down when you stop: a zero is
 * printed as a zero.
 */

function Stat({ children }: { children: ReactNode }) {
  return <div className="flex min-w-0 flex-col gap-1">{children}</div>;
}

const LINK_BUTTON =
  "inline-flex min-h-11 items-center rounded-sm px-1 text-left text-sm font-medium text-accent underline underline-offset-4 transition-colors duration-150 ease-in-out hover:text-fg";

export type RecordedState =
  | { kind: "loading" }
  | { kind: "ready"; today: number; week: number }
  /** The history could not be read. `sessionOnly` is what this visit has recorded, which is the
   *  one count that is still known. */
  | { kind: "failed"; sessionOnly: number };

export function QueueSummary({
  newCount,
  newActive,
  onToggleNew,
  recorded,
  onRetryRecorded,
  followUpsDue,
  followUpsActive,
  onToggleFollowUps,
  quietApplications,
  quietHref,
  onStart,
  startLabel,
  canStart,
}: {
  newCount: number;
  newActive: boolean;
  onToggleNew: () => void;
  recorded: RecordedState;
  onRetryRecorded: () => void;
  followUpsDue: number;
  followUpsActive: boolean;
  onToggleFollowUps: () => void;
  /** Applications still `applied` with nothing logged for three weeks, or `null` if unknown. */
  quietApplications: number | null;
  quietHref: string;
  onStart: () => void;
  startLabel: string;
  canStart: boolean;
}) {
  const attention: ReactNode[] = [];
  if (followUpsDue > 0) {
    attention.push(
      <button
        key="follow-ups"
        type="button"
        aria-pressed={followUpsActive}
        onClick={onToggleFollowUps}
        className={LINK_BUTTON}
      >
        {followUpsDue.toLocaleString()} {followUpsDue === 1 ? "follow-up" : "follow-ups"} due
        {followUpsActive ? " — showing only these" : ""}
      </button>,
    );
  }
  if (quietApplications !== null && quietApplications > 0) {
    attention.push(
      <a key="quiet" href={quietHref} className={LINK_BUTTON}>
        {quietApplications.toLocaleString()}{" "}
        {quietApplications === 1 ? "application has" : "applications have"} no update recorded
      </a>,
    );
  }

  return (
    <section
      aria-label="Summary"
      className="grid gap-x-8 gap-y-4 rounded-md bg-surface p-4 shadow-card sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-center"
    >
      <Stat>
        <span className="label-micro text-fg-2">New</span>
        <button
          type="button"
          aria-pressed={newActive}
          onClick={onToggleNew}
          className="inline-flex min-h-11 items-center gap-2 rounded-sm px-1 text-left transition-colors duration-150 ease-in-out hover:bg-surface-2"
        >
          <span className="text-2xl leading-none font-semibold text-fg tabular-nums">
            {newCount.toLocaleString()}
          </span>
          <span className="text-sm text-fg-2">
            {newActive ? "new since your last visit — showing only these" : "since your last visit"}
          </span>
        </button>
      </Stat>

      <Stat>
        <span className="label-micro text-fg-2">Applications recorded</span>
        {recorded.kind === "loading" ? (
          <span role="status" className="flex min-h-11 items-center gap-2" aria-label="Counting your applications">
            <span className="skeleton h-6 w-32" />
          </span>
        ) : recorded.kind === "failed" ? (
          <span className="flex min-h-11 flex-wrap items-center gap-x-2 text-sm text-fg-2">
            <span>
              Couldn’t read your history
              {recorded.sessionOnly > 0
                ? ` — ${String(recorded.sessionOnly)} recorded this visit`
                : ""}
              .
            </span>
            <button type="button" onClick={onRetryRecorded} className={LINK_BUTTON}>
              Try again
            </button>
          </span>
        ) : (
          <p className="flex min-h-11 flex-wrap items-center gap-x-3 text-sm text-fg-2">
            <span>
              <span className="text-2xl leading-none font-semibold text-fg tabular-nums">
                {recorded.today.toLocaleString()}
              </span>{" "}
              today
            </span>
            <span>
              <span className="text-2xl leading-none font-semibold text-fg tabular-nums">
                {recorded.week.toLocaleString()}
              </span>{" "}
              in the past 7 days
            </span>
          </p>
        )}
      </Stat>

      <Stat>
        <span className="label-micro text-fg-2">Needs attention</span>
        {attention.length === 0 ? (
          <p className="flex min-h-11 items-center text-sm text-fg-2">Nothing right now.</p>
        ) : (
          <div className="flex flex-col">{attention}</div>
        )}
      </Stat>

      <div className="sm:col-span-2 lg:col-span-1 lg:justify-self-end">
        <button
          type="button"
          onClick={onStart}
          disabled={!canStart}
          className="inline-flex min-h-11 items-center gap-2 rounded-sm bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-in-out hover:bg-primary-strong disabled:bg-surface-3 disabled:text-fg-3"
        >
          {startLabel}
          <Icon name="arrowRight" />
        </button>
      </div>
    </section>
  );
}

export type Lens = "explore" | "review" | "all";

export const LENSES: readonly { key: Lens; label: string; blurb: string }[] = [
  {
    key: "explore",
    label: "Jobs to explore",
    blurb:
      "A résumé is prepared and no check held these back. That is not the same as verified — open a job to see what to check before you apply.",
  },
  {
    key: "review",
    label: "Needs review",
    blurb:
      "Each of these has something the automatic checks couldn’t settle. Read what to check first; many are still worth applying to.",
  },
  {
    key: "all",
    label: "All jobs",
    blurb:
      "Jobs to explore and Needs review together, with no job counted twice. Filtered-out, closed, skipped and already-applied jobs are not included.",
  },
];

/*
 * The three lists, as a group of toggle buttons. Each count is the number of jobs IN THAT LIST
 * that match the current search, place and work arrangement — never a sum across lists that could
 * overlap — and the sentence under the buttons says what the selected list is and what "All"
 * leaves out. A tab-panel pattern would promise arrow-key semantics the buttons do not have, so
 * this is `aria-pressed` buttons in a labelled group.
 */
export function LensTabs({
  lens,
  onLens,
  counts,
}: {
  lens: Lens;
  onLens: (lens: Lens) => void;
  counts: Record<Lens, number>;
}) {
  const current = LENSES.find((entry) => entry.key === lens) ?? LENSES[0];
  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label="Which jobs to list" className="flex flex-wrap gap-2">
        {LENSES.map((entry) => {
          const active = entry.key === lens;
          return (
            <button
              key={entry.key}
              type="button"
              aria-pressed={active}
              /* The visible words, then the number, so the name carries both and starts with the
                 label (SC 2.5.3) — two adjacent spans would otherwise read "Needs review2". */
              aria-label={`${entry.label} ${counts[entry.key].toLocaleString()}`}
              onClick={() => {
                onLens(entry.key);
              }}
              className={`inline-flex min-h-11 items-center gap-2 rounded-sm px-4 text-sm font-medium transition-colors duration-150 ease-in-out ${
                active
                  ? "bg-primary text-on-primary"
                  : "bg-surface text-fg-2 shadow-card hover:bg-surface-2 hover:text-fg"
              }`}
            >
              {entry.label}
              <span className={`tabular-nums ${active ? "text-on-primary" : "text-fg-3"}`}>
                {counts[entry.key].toLocaleString()}
              </span>
            </button>
          );
        })}
      </div>
      <p className="max-w-[72ch] text-sm text-fg-2">{current?.blurb}</p>
    </div>
  );
}
