import { useEffect, useState } from "react";

import { getFormQuestionBank } from "../api/client";
import type { FormQuestionBank } from "../api/types";

/*
 * T312: the questions employers ask most across open, eligible postings, and whether a standing
 * answer exists for each. Answering the top unanswered ones once speeds every fill. The page is
 * sent only the yes/no: the answers stay in the owner's local `answers.yaml`. Abstaining
 * postings are named apart and are not in any count.
 */

function status(answered: boolean | null): string {
  if (answered === null) return "Unknown";
  return answered ? "Answered" : "Unanswered";
}

export function FormQuestionBankPanel() {
  const [bank, setBank] = useState<FormQuestionBank | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.resolve()
      .then(() => getFormQuestionBank())
      .then((b) => {
        if (live) setBank(b);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, []);

  if (failed) {
    return (
      <section aria-label="Form questions" className="mt-8 rounded-md bg-surface p-4 text-sm text-fg-2">
        Form questions could not be loaded.
      </section>
    );
  }
  if (bank === null) return null;

  const { forms } = bank;
  return (
    <section aria-label="Form questions" className="mt-8 rounded-md bg-surface p-4">
      <h3 className="text-base font-medium text-fg">Form questions</h3>
      <p className="mt-1 text-sm text-fg-2">
        {String(bank.distinct)} {bank.distinct === 1 ? "question" : "questions"} across{" "}
        {String(forms.eligible)} open eligible {forms.eligible === 1 ? "form" : "forms"}
        {bank.unanswered === null ? "" : `, ${String(bank.unanswered)} unanswered`}. Abstaining
        forms ({String(forms.abstain)}) are not counted. Answer the unanswered ones once, in your
        answers file; this page never receives the answers.
      </p>
      {!bank.answers_readable ? (
        <p role="alert" className="mt-2 text-sm text-fg">
          Your answers file could not be read, so no question is marked answered or unanswered.
        </p>
      ) : null}
      {bank.questions.length === 0 ? (
        <p className="mt-2 text-sm text-fg-2">No questions to show yet.</p>
      ) : (
        <ul className="mt-2 divide-y divide-divider text-sm">
          {bank.questions.map((q) => (
            <li key={q.question} className="flex items-baseline gap-3 py-1.5">
              <span className="w-24 shrink-0 text-fg">{status(q.answered)}</span>
              <span className="w-10 shrink-0 text-right tabular-nums text-fg-2">
                {String(q.count)}
              </span>
              <span className="min-w-0 break-words text-fg">{q.question}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-fg-2">
        Count is open eligible postings that ask it. Left out as built-ins every form asks:{" "}
        {bank.standard_fields.join(", ")}.
      </p>
    </section>
  );
}
