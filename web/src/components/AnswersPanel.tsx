import { useState } from "react";

import type { Answers } from "../api/types";
import { CopyButton } from "./CopyButton";

/*
 * Read-and-copy only. Nothing here types into an employer's page.
 *
 * Two rules this panel exists to keep:
 *   - `note` is SHOWN and never copied. Its most important use is a warning that the answer must
 *     not be reused as written, and that warning must never reach the clipboard with the answer.
 *   - the identity block gets one "copy the whole block" control, which turns seven copy-paste
 *     round trips into one.
 */
function fieldLabel(key: string): string {
  return key.replace(/_/g, " ");
}

function KeyValueRows({
  entries,
  onError,
}: {
  entries: [string, string | null][];
  onError: (message: string) => void;
}) {
  return (
    <dl className="divide-y divide-divider">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-3 py-1.5">
          <dt className="w-40 shrink-0 text-xs text-fg-3">{fieldLabel(key)}</dt>
          <dd className="min-w-0 flex-1 truncate text-sm text-fg">{value ?? "not set"}</dd>
          {value === null ? null : (
            <CopyButton value={value} label="Copy" onError={onError} title={`Copy ${key}`} />
          )}
        </div>
      ))}
    </dl>
  );
}

export function AnswersPanel({
  answers,
  onError,
}: {
  answers: Answers | null;
  onError: (message: string) => void;
}) {
  // Expanded by default: the owner opened this pane on purpose.
  const [open, setOpen] = useState(true);

  const identityEntries = Object.entries(answers?.identity ?? {});
  const identityBlock = identityEntries
    .filter((entry): entry is [string, string] => entry[1] !== null)
    .map(([key, value]) => `${fieldLabel(key)}: ${value}`)
    .join("\n");

  return (
    <section className="rounded border border-divider bg-surface">
      <button
        type="button"
        onClick={() => {
          setOpen((current) => !current);
        }}
        aria-expanded={open}
        className="flex min-h-11 w-full items-center justify-between px-4 text-left text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface-2"
      >
        <span>Application answers</span>
        <span aria-hidden="true" className="text-fg-3">
          {open ? "collapse" : "expand"}
        </span>
      </button>

      {!open ? null : answers === null ? (
        <p className="px-4 pb-4 text-sm text-fg-2">Loading answers…</p>
      ) : (
        <div className="flex flex-col gap-5 border-t border-divider px-4 py-4">
          <div>
            <div className="mb-1.5 flex items-center justify-between gap-3">
              <h3 className="text-[11px] tracking-wide text-fg-3 uppercase">identity</h3>
              <CopyButton
                value={identityBlock}
                label="Copy whole block"
                variant="primary"
                onError={onError}
                title="Every identity field, one field per line."
              />
            </div>
            <KeyValueRows entries={identityEntries} onError={onError} />
          </div>

          <div>
            <h3 className="mb-1.5 text-[11px] tracking-wide text-fg-3 uppercase">
              work authorisation
            </h3>
            <KeyValueRows entries={Object.entries(answers.work_auth)} onError={onError} />
          </div>

          <div>
            <h3 className="mb-1.5 text-[11px] tracking-wide text-fg-3 uppercase">education</h3>
            <div className="flex flex-col gap-3">
              {answers.education.map((entry, index) => (
                <KeyValueRows
                  key={index}
                  entries={Object.entries(entry)}
                  onError={onError}
                />
              ))}
            </div>
          </div>

          <div>
            <h3 className="mb-1.5 text-[11px] tracking-wide text-fg-3 uppercase">questions</h3>
            <ul className="flex flex-col gap-3">
              {answers.questions.map((question) => (
                <li key={question.q} className="border-t border-divider pt-3">
                  <p className="text-xs text-fg-3">{question.q}</p>
                  <div className="mt-1 flex items-start gap-3">
                    <p className="min-w-0 flex-1 text-sm whitespace-pre-wrap text-fg">
                      {question.a}
                    </p>
                    <CopyButton value={question.a} label="Copy" onError={onError} />
                  </div>
                  {question.note ? (
                    <p className="mt-2 border-l-2 border-control pl-3 text-xs text-fg-2">
                      <span className="mr-1.5 tracking-wide text-fg-3 uppercase">note</span>
                      {question.note}
                      <span className="mt-1 block text-fg-3">
                        Shown here only. The copy button above copies the answer, never this note.
                      </span>
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
