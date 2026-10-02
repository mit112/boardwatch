import { useEffect, useRef } from "react";

import { Icon } from "./Icon";

/*
 * The apply session: an OPTIONAL way to work down the list without choosing the next job each time.
 *
 * The loop is review a job → use its materials → open the employer's page → come back → say you
 * applied → continue. Nothing in it records an application except the person saying so: opening a
 * link records nothing, coming back to the tab records nothing, and the only write is the explicit
 * "Record application" (or "Yes" to the return prompt).
 *
 * What these three pieces deliberately are not: there is no goal to set before starting, no streak,
 * no countdown, no "you're behind", and nothing that goes quiet or sad when you stop. A batch of
 * five is a quiet link that can be taken or ignored; reaching it offers "Keep going" and "Finish
 * for now" as two equal choices.
 */

const QUIET_BUTTON =
  "inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface-3 hover:text-fg";

const FILLED_BUTTON =
  "inline-flex min-h-11 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-on-primary transition-colors duration-150 ease-in-out hover:bg-primary-strong";

/** The default batch, when someone chooses to use one. Small enough to finish in a sitting. */
export const DEFAULT_BATCH = 5;

/**
 * The strip above the list while a session is on. The count is announced politely, because it is a
 * meaningful state change and a screen-reader reader otherwise never hears that a write landed.
 * It counts APPLICATIONS THAT WERE ACTUALLY RECORDED — a failed write never moves it.
 */
export function SessionBar({
  count,
  batch,
  onSetBatch,
  onEnd,
}: {
  count: number;
  batch: number | null;
  onSetBatch: (batch: number | null) => void;
  onEnd: () => void;
}) {
  return (
    <section
      aria-label="Apply session"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-surface-2 px-4 py-1.5"
    >
      <span className="text-sm font-semibold text-fg">Apply session</span>
      <span role="status" className="text-sm text-fg-2 tabular-nums">
        {count.toLocaleString()} recorded{batch === null ? "" : ` of ${String(batch)}`} this session
      </span>
      {batch === null ? (
        <button
          type="button"
          onClick={() => {
            onSetBatch(DEFAULT_BATCH);
          }}
          className={QUIET_BUTTON}
        >
          Work in a batch of {DEFAULT_BATCH}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => {
            onSetBatch(null);
          }}
          className={QUIET_BUTTON}
        >
          No batch limit
        </button>
      )}
      <button type="button" onClick={onEnd} className={`${QUIET_BUTTON} sm:ml-auto`}>
        End session
      </button>
    </section>
  );
}

/**
 * What the workspace shows right after "Record application" when NO session is running. The job
 * has already left the list, so the workspace says what just happened — the real write, in the
 * past tense — and offers the three things that follow: continue, undo, or go back.
 *
 * Focus lands on "Continue to next role": it opens the next job and writes nothing, so a repeated
 * Enter on it is harmless, which is exactly why it and not "Record application" is what takes it.
 */
export function RecordedPanel({
  company,
  title,
  hasNext,
  pending,
  onContinue,
  onUndo,
  onBack,
}: {
  company: string;
  title: string;
  hasNext: boolean;
  /** The write has not been answered yet. Nothing here may claim it landed until it has. */
  pending: boolean;
  onContinue: () => void;
  onUndo: () => void;
  onBack: () => void;
}) {
  const primary = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    primary.current?.focus();
  }, []);
  /* Escape leaves the panel like the workspace it replaces; below `lg` it is a modal dialog. */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onBack]);
  return (
    <div role="status" className="flex flex-col gap-4 px-6 py-8">
      <span
        className={`inline-flex size-10 items-center justify-center rounded-full bg-surface-2 ${pending ? "text-fg-3" : "text-ok"}`}
      >
        <Icon name={pending ? "dash" : "check"} size={22} />
      </span>
      <div>
        <h2 className="text-xl text-fg">
          {pending
            ? `Recording your application for ${company}…`
            : `Application recorded for ${company}.`}
        </h2>
        <p className="mt-1 max-w-[56ch] text-sm text-fg-2">
          {pending
            ? `Waiting for the store to confirm. If it does not go through, ${title} comes back to your list.`
            : `${title} is off your list. If that was a mistake, undo it and the job comes straight back.`}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {hasNext ? (
          <button ref={primary} type="button" onClick={onContinue} className={FILLED_BUTTON}>
            Continue to next role
            <Icon name="arrowRight" />
          </button>
        ) : null}
        <button
          type="button"
          onClick={onUndo}
          disabled={pending}
          className={`${QUIET_BUTTON} bg-surface-2 disabled:text-fg-3`}
        >
          Undo
        </button>
        <button
          ref={hasNext ? undefined : primary}
          type="button"
          onClick={onBack}
          className={QUIET_BUTTON}
        >
          Back to the list
        </button>
      </div>
    </div>
  );
}

export type SessionEnd = "batch" | "end-of-list";

/**
 * The end of a batch, or of the list. Two equal choices and no pressure: keep going, or finish for
 * now. The sentence says only what happened. At the end of a list the "keep going" offer is the
 * other list, when it has anything in it, and is simply absent when it does not — a button that
 * leads nowhere is worse than none.
 */
export function SessionDone({
  kind,
  count,
  keepGoingLabel,
  onKeepGoing,
  onFinish,
}: {
  kind: SessionEnd;
  count: number;
  /** What "keep going" would do here, or `null` when there is nothing to keep going to. */
  keepGoingLabel: string | null;
  onKeepGoing: () => void;
  onFinish: () => void;
}) {
  const primary = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    primary.current?.focus();
  }, []);
  return (
    <section role="status" aria-label="Session" className="rounded-md bg-surface p-6 shadow-card">
      <h2 className="text-xl text-fg">
        {kind === "batch"
          ? `${count.toLocaleString()} recorded.`
          : "That was the last job in this list."}
      </h2>
      <p className="mt-1 max-w-[56ch] text-sm text-fg-2">
        {count.toLocaleString()} {count === 1 ? "application" : "applications"} recorded this
        session.{" "}
        {kind === "end-of-list" && keepGoingLabel === null
          ? "Nothing else is waiting in the other list."
          : "Keep going when you like, or stop here — everything stays where it is."}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {keepGoingLabel === null ? null : (
          <button ref={primary} type="button" onClick={onKeepGoing} className={FILLED_BUTTON}>
            {keepGoingLabel}
          </button>
        )}
        <button
          ref={keepGoingLabel === null ? primary : undefined}
          type="button"
          onClick={onFinish}
          className={`${QUIET_BUTTON} bg-surface-2`}
        >
          Finish for now
        </button>
      </div>
    </section>
  );
}
