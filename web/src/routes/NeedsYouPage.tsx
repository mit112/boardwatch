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

  if (settled < 2) return <p className="text-sm text-fg-2">Loading what needs you…</p>;
  const groups = needsYou(queue, companions);
  const total = needsCount(groups);

  return (
    <div className="max-w-4xl">
      <h2 className="text-lg font-semibold text-fg">Needs you</h2>
      <p className="mt-1 text-sm text-fg-2">
        {total === 0
          ? "No lead or companion is waiting on you."
          : `${String(total)} ${total === 1 ? "thing" : "things"} only you can settle. Open a lead to settle it in Jobs.`}
      </p>
      {failed.length > 0 ? (
        <p role="alert" className="mt-3 rounded-md bg-surface-2 p-3 text-sm text-fg">
          Could not load {failed.join(" or ")}, so this list may be incomplete.
        </p>
      ) : null}
      {groups.map((g) => (
        <Group key={g.key} group={g} />
      ))}
      <FormQuestionBankPanel />
    </div>
  );
}

function Group({ group }: { group: NeedsGroup }) {
  const n = group.leads.length + group.items.length;
  return (
    <section aria-label={group.heading} className="mt-6">
      <h3 className="text-base font-medium text-fg">
        {group.heading} <span className="text-fg-2">({String(n)})</span>
      </h3>
      <p className="text-sm text-fg-2">To do: {group.todo}</p>
      <ul className="mt-2 divide-y divide-divider rounded-md bg-surface">
        {group.leads.map((l) => (
          <li key={l.postingId} className="px-3 py-2 text-sm">
            <a
              className="text-accent underline underline-offset-4"
              href={`#/queue?lead=${String(l.postingId)}`}
            >
              {l.title}
            </a>{" "}
            <span className="text-fg-2">· {l.company}</span>
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
    </section>
  );
}
