import { useEffect, useState } from "react";

import { getCompanions, getQueue } from "../api/client";
import type { Companion, QueueResponse } from "../api/types";
import { FormQuestionBankPanel } from "../components/FormQuestionBank";
import { type NeedsGroup, needsCount, needsYou } from "../lib/needsYou";

/*
 * T300: what only the owner can settle, in one list. Read-only — each group says what to do, and
 * a lead opens in the Jobs view, where it is settled as it is today.
 *
 * The two sources load independently: a companion folder that cannot be read must not hide the
 * held leads, and the other way round.
 */

export function NeedsYouPage() {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [companions, setCompanions] = useState<Companion[]>([]);
  const [failed, setFailed] = useState<string[]>([]);
  const [settled, setSettled] = useState(0);

  useEffect(() => {
    let live = true;
    const done = () => {
      if (live) setSettled((n) => n + 1);
    };
    void Promise.resolve()
      .then(() => getQueue())
      .then((q) => {
        if (live) setQueue(q);
      })
      .catch(() => {
        if (live) setFailed((f) => [...f, "the job list"]);
      })
      .finally(done);
    void Promise.resolve()
      .then(() => getCompanions())
      .then((c) => {
        if (live) setCompanions(c.companions);
      })
      .catch(() => {
        if (live) setFailed((f) => [...f, "companion status"]);
      })
      .finally(done);
    return () => {
      live = false;
    };
  }, []);

  const groups = needsYou(queue, companions);
  const total = needsCount(groups);

  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <header>
        <h1 className="page-title">Needs you</h1>
        <p className="mt-1 text-sm text-fg-2">
          {settled < 2
            ? "Loading items to review…"
            : total === 0
              ? "No lead or companion is waiting on you."
              : `${String(total)} ${total === 1 ? "item needs" : "items need"} your review.`}
        </p>
      </header>
      {failed.length > 0 ? (
        <p role="alert" className="mt-3 rounded-md bg-surface-2 p-3 text-sm text-fg">
          Could not load {failed.join(" or ")}, so this list may be incomplete.
        </p>
      ) : null}
      {settled < 2 ? null : (
        <>
          {groups.length === 0 ? null : (
            <div className="flex flex-col gap-2">
              {groups.map((group) => <Group key={group.key} group={group} />)}
            </div>
          )}
          <FormQuestionBankPanel />
        </>
      )}
    </div>
  );
}

function Group({ group }: { group: NeedsGroup }) {
  const n = group.leads.length + group.items.length;
  const title = group.key.startsWith("held:") && group.key !== "held:other" ? group.todo : group.heading;
  return (
    <details aria-label={title} className="ledger">
      <summary>
        <span className="ml-1">{title}</span>
        <span className="float-right ml-3 text-sm text-fg-2 tabular-nums">{n.toLocaleString()}</span>
      </summary>
      {title === group.todo ? null : (
        <p className="bg-surface-2 px-4 py-3 text-sm text-fg-2">{group.todo}</p>
      )}
      <ul className="divide-y divide-divider">
        {group.leads.map((l) => (
          <li key={l.postingId} className="text-sm">
            <a
                className="flex min-h-11 flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2 text-accent hover:bg-surface-2"
              href={`#/queue?lead=${String(l.postingId)}`}
            >
              <span className="font-medium underline underline-offset-4">{l.title}</span>
              <span className="text-fg-2">{l.company}</span>
            </a>
          </li>
        ))}
        {group.items.map((i, idx) => (
          <li key={`${i.label}-${String(idx)}`} className="px-3 py-2 text-sm">
            {i.link !== null && /^https?:\/\//.test(i.link) ? (
              <a
                className="text-accent underline underline-offset-4"
                href={i.link}
                target="_blank"
                rel="noreferrer noopener"
              >
                {i.label}
              </a>
            ) : (
              <span className="text-fg">{i.label}</span>
            )}
            {i.reason !== null ? <span className="text-fg-2"> · {i.reason}</span> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
