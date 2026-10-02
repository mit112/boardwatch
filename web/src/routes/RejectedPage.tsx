import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import {
  disputeRejection,
  getDetail,
  getRejected,
  markApplied,
  openPdf,
  unapply,
  undisputeRejection,
} from "../api/client";
import type { QueueDetail, RejectedResponse, RejectedRow, RequirementView } from "../api/types";
import { Badge } from "../components/Badge";
import { Icon } from "../components/Icon";
import { StatusMark } from "../components/StatusMark";
import type { ToastRequest } from "../hooks/useToasts";
import { EM_DASH, isSafeHttpUrl } from "../lib/format";
import { requirementState, reviewMark } from "../lib/jobStatus";

/*
 * FILTERED OUT: the jobs the automatic rules turned away, which the queue only COUNTS in its
 * `ineligible` cell. Read to catch a wrong call — each job's evidence names the rule and quotes
 * the span it read — and to act on one: record that you applied anyway (an owner statement
 * outranks a derived verdict), or flag the call as wrong, which records the disagreement for the
 * next precision audit and moves nothing.
 *
 * The page is NOT called "Rejected". That word belongs to an employer's answer to an application
 * you sent, and nothing was sent for any job here: these are our rules' calls, and they can be
 * wrong. (The route key and the `/api/rejected` endpoint keep their names.)
 *
 * Jobs the independent review found no blocker in arrive first and can be shown alone: the rules
 * and the review disagreeing is the likeliest sign of a wrong call.
 */

const BUTTON =
  "inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface-3 hover:text-fg disabled:text-fg-3";

/** Evidence rows the rules recorded — the ones carrying a `rule` — with what failed first. A row
 *  without a rule is a résumé-coverage term, which is not about the rejection. */
const ORDER: Record<string, number> = { unmet: 0, unconfirmed: 1, not_assessed: 2, satisfied: 3 };

function evidenceRows(requirements: RequirementView[]): RequirementView[] {
  return requirements
    .filter((item) => item.rule !== null)
    .sort((a, b) => (ORDER[requirementState(a)] ?? 4) - (ORDER[requirementState(b)] ?? 4));
}

function Evidence({ postingId, named }: { postingId: number; named: string }) {
  const [detail, setDetail] = useState<QueueDetail | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void getDetail(postingId)
      .then((response) => {
        if (live) setDetail(response);
      })
      .catch((caught: unknown) => {
        if (live) {
          setFailed(
            caught instanceof Error
              ? "The evidence for this job could not be loaded just now. Closing and opening it again usually works."
              : "Could not load the evidence.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [postingId]);

  if (failed !== null) {
    return (
      <p role="alert" className="px-3 py-3 text-sm text-fg">
        {failed}
      </p>
    );
  }
  if (detail === null) {
    return (
      <p role="status" className="px-3 py-3 text-sm text-fg-2">
        Loading the evidence…
      </p>
    );
  }
  const rows = evidenceRows(detail.requirements);
  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {rows.length === 0 ? (
        <p className="text-sm text-fg-2">No eligibility rule recorded evidence for this posting.</p>
      ) : (
        <ul aria-label={`Why ${named} was filtered out`} className="flex flex-col gap-3">
          {rows.map((item) => (
            <li key={`${item.rule ?? ""}-${item.requirement}`} className="rounded-sm bg-surface px-3 py-2">
              <p className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
                <span className="font-mono text-xs text-fg">{item.rule}</span>
                {/* In words: "not met" is the reading that filters, and it must not be told apart
                    from "not confirmed" by colour alone. */}
                {requirementState(item) === "unmet" ? (
                  <Badge label="not met" emphasis="strong" />
                ) : (
                  <span>
                    {requirementState(item) === "satisfied"
                      ? "met"
                      : requirementState(item) === "unconfirmed"
                        ? "not confirmed"
                        : EM_DASH}
                  </span>
                )}
                {item.profile_field === null ? null : (
                  <span>
                    read <span className="font-mono">{item.profile_field}</span>
                  </span>
                )}
              </p>
              {item.rationale === null ? null : (
                <p className="mt-1 text-sm text-fg-2">{item.rationale}</p>
              )}
              {item.quote === null ? null : (
                <blockquote className="mt-1 text-sm text-fg italic">“{item.quote}”</blockquote>
              )}
            </li>
          ))}
        </ul>
      )}
      {detail.jd_body === null ? null : (
        <details className="text-sm text-fg-2">
          <summary className="inline-flex min-h-11 cursor-pointer items-center">
            The job description
          </summary>
          {/* Third-party text, rendered as text and never as markup. */}
          <p className="mt-2 max-w-[68ch] leading-[1.7] whitespace-pre-wrap">
            {detail.jd_body}
          </p>
        </details>
      )}
    </div>
  );
}

export function RejectedPage({ push }: { push: (request: ToastRequest) => void }) {
  const [data, setData] = useState<RejectedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [gateOnly, setGateOnly] = useState(false);
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const [busy, setBusy] = useState<ReadonlySet<number>>(new Set());

  const load = useCallback(
    () =>
      getRejected()
        .then((response) => {
          setData(response);
          setError(null);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof Error ? caught.message : "Could not load the filtered-out jobs.");
        }),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const mark = useCallback((postingId: number, on: boolean) => {
    setBusy((current) => {
      const next = new Set(current);
      if (on) next.add(postingId);
      else next.delete(postingId);
      return next;
    });
  }, []);

  /* Dispute and its withdrawal, each a real write; the refetch settles the row AND the count. */
  const onDispute = useCallback(
    (row: RejectedRow) => {
      const named = `${row.company} — ${row.title}`;
      const write = row.disputed ? undisputeRejection : disputeRejection;
      mark(row.posting_id, true);
      void write(row.posting_id)
        .then(() => {
          push({
            message: row.disputed
              ? `Withdrew the flag on ${named}.`
              : `Flagged the call on ${named} as wrong. It stays filtered out; the flag is kept for the next audit.`,
          });
          return load();
        })
        .catch((caught: unknown) => {
          push({
            message: caught instanceof Error ? caught.message : "Could not record that.",
            tone: "error",
          });
        })
        .finally(() => {
          mark(row.posting_id, false);
        });
    },
    [load, mark, push],
  );

  /* Apply anyway: the queue's own mark, whose undo is the queue's own withdrawal. */
  const onApplied = useCallback(
    (row: RejectedRow) => {
      mark(row.posting_id, true);
      void markApplied(row.posting_id)
        .then(() => {
          push({
            message: `Application recorded for ${row.company} — ${row.title}. Undo withdraws it.`,
            undo: () => {
              void unapply(row.posting_id)
                .then(() => load())
                .catch((caught: unknown) => {
                  push({
                    message:
                      caught instanceof Error ? caught.message : "Could not withdraw that application.",
                    tone: "error",
                  });
                });
            },
          });
          return load();
        })
        .catch((caught: unknown) => {
          push({
            message: caught instanceof Error ? caught.message : "Could not record that application.",
            tone: "error",
          });
        })
        .finally(() => {
          mark(row.posting_id, false);
        });
    },
    [load, mark, push],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.rows ?? []).filter(
      (row) =>
        (!gateOnly || row.judge_verdict === "eligible") &&
        (needle === "" ||
          [row.company, row.title, row.location ?? ""].some((field) =>
            field.toLowerCase().includes(needle),
          )),
    );
  }, [data, query, gateOnly]);

  if (error !== null) {
    return (
      <div role="alert" className="max-w-2xl rounded-md bg-surface-2 p-5">
        <h2 className="text-base text-fg">The filtered-out jobs could not be loaded.</h2>
        <p className="mt-1 text-sm text-fg-2">
          Your jobs are unaffected. Trying again usually works.
        </p>
        <p className="mt-2 text-xs text-fg-3">{error}</p>
        <button
          type="button"
          onClick={() => {
            setError(null);
            void load();
          }}
          className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-on-primary transition-colors duration-150 ease-in-out hover:bg-primary-strong"
        >
          <Icon name="refresh" />
          Try again
        </button>
      </div>
    );
  }
  if (data === null) {
    return (
      <div aria-busy="true" className="flex flex-col gap-3">
        <p role="status" className="text-sm text-fg-2">
          Loading the filtered-out jobs…
        </p>
        <span className="skeleton h-16 w-full max-w-xl" />
        <span className="skeleton h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Filtered-out jobs status" className="flex flex-col">
        <dl className="flex flex-wrap items-stretch gap-x-8 gap-y-2 rounded-md bg-surface p-4 shadow-card">
          <div className="flex min-w-28 flex-col gap-1">
            <dt className="label-micro text-fg-2">Filtered out</dt>
            <dd className="text-2xl leading-none font-semibold text-fg tabular-nums">
              {data.counts.total.toLocaleString()}
            </dd>
          </div>
          <div className="flex min-w-28 flex-col gap-1">
            <dt className={`label-micro ${gateOnly ? "text-fg" : "text-fg-2"}`}>
              Independent review found no blocker
            </dt>
            <dd>
              <button
                type="button"
                aria-pressed={gateOnly}
                aria-label={`independent review found no blocker ${data.counts.gate_eligible.toLocaleString()} — ${
                  gateOnly ? "showing only these, activate to clear" : "show only these"
                }`}
                title="Filtered out by the rules, but the independent review read the posting and found no blocker. Click to show only these."
                onClick={() => {
                  setGateOnly((current) => !current);
                }}
                className={`inline-flex min-h-11 cursor-pointer items-center rounded-sm px-2 text-2xl leading-none font-semibold tabular-nums transition-colors duration-[120ms] ease-snap ${
                  gateOnly ? "bg-primary text-on-primary" : "text-fg hover:bg-surface-2"
                }`}
              >
                {data.counts.gate_eligible.toLocaleString()}
              </button>
            </dd>
          </div>
          <div className="flex min-w-28 flex-col gap-1">
            <dt className="label-micro text-fg-2">Flagged as wrong</dt>
            <dd className="text-2xl leading-none font-semibold text-fg tabular-nums">
              {data.counts.disputed.toLocaleString()}
            </dd>
          </div>
          <div role="status" className="ml-auto flex items-end text-sm text-fg-2 tabular-nums">
            Showing {visible.length.toLocaleString()} of {data.counts.total.toLocaleString()} filtered-out jobs
          </div>
        </dl>
      </section>

      <p className="max-w-[80ch] text-sm text-fg-2">
        Jobs the automatic eligibility rules filtered out after a run delivered them. This is our
        rules’ call, not an employer’s answer — nothing was sent for any of them, and a call can be
        wrong. They are not in your job lists, and their folders sit in{" "}
        <code className="font-mono text-fg-3">_ineligible</code>. Open “Why filtered out” to read the
        rule and the words it quoted. “Flag as wrongly filtered” records that you disagree and
        changes nothing else; record an application anyway if you are sure.
      </p>

      <label className="flex min-w-64 max-w-md flex-col gap-1.5">
        <span className="label-micro text-fg-2">Search</span>
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          placeholder="Company, title or place"
          className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
        />
      </label>

      <div className="overflow-x-auto rounded-md bg-surface shadow-card">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Jobs the eligibility rules filtered out, those the independent review found no blocker in first.
          </caption>
          <thead>
            {/* Not sticky: inside `overflow-x-auto` the wrapper is the sticky container, and the
                app header's offset would push this row down over the first lead. */}
            <tr className="bg-surface text-fg-2 [&>*]:border-b [&>*]:border-divider">
              <th scope="col" className="px-3 py-2 text-left text-sm font-medium">Company</th>
              <th scope="col" className="px-3 py-2 text-left text-sm font-medium">Title</th>
              <th scope="col" className="px-3 py-2 text-left text-sm font-medium">Location</th>
              <th scope="col" className="px-3 py-2 text-left text-sm font-medium">Independent review</th>
              <th scope="col" className="px-3 py-2 text-right text-sm font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-divider">
            {visible.map((row) => {
              const named = `${row.company} — ${row.title}`;
              const isOpen = open.has(row.posting_id);
              const evidenceId = `why-${String(row.posting_id)}`;
              const inFlight = busy.has(row.posting_id);
              const url = row.apply_url;
              return (
                <Fragment key={row.posting_id}>
                  <tr className="hover:bg-surface-2">
                    <td className="px-3 py-1.5 text-fg">{row.company}</td>
                    <td className="px-3 py-1.5 text-fg-2">
                      <span className="flex flex-wrap items-center gap-2">
                        {row.title}
                        {row.disputed ? (
                          <Badge
                            label="flagged as wrong"
                            reason="You flagged this call as wrong. It stands until the rules change."
                          />
                        ) : null}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-fg-3">{row.location ?? EM_DASH}</td>
                    <td className="px-3 py-1.5">
                      {row.judge_verdict == null ? (
                        <span className="text-sm text-fg-3">Not reviewed</span>
                      ) : (
                        <StatusMark mark={reviewMark(row.judge_verdict)} />
                      )}
                    </td>
                    <td className="px-3 py-1.5">
                      <span className="flex flex-wrap items-center justify-end gap-2">
                        <button
                          type="button"
                          aria-expanded={isOpen}
                          aria-controls={evidenceId}
                          aria-label={`Why filtered out: ${named}`}
                          onClick={() => {
                            setOpen((current) => {
                              const next = new Set(current);
                              if (!next.delete(row.posting_id)) next.add(row.posting_id);
                              return next;
                            });
                          }}
                          className={BUTTON}
                        >
                          Why filtered out
                        </button>
                        {isSafeHttpUrl(url) && url !== null ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`Open application: ${named}`}
                            className={BUTTON}
                          >
                            Open application
                          </a>
                        ) : null}
                        {row.pdf_available ? (
                          <button
                            type="button"
                            aria-label={`Preview résumé: ${named}`}
                            onClick={() => {
                              void openPdf(row.posting_id).catch((caught: unknown) => {
                                push({
                                  message:
                                    caught instanceof Error ? caught.message : "Could not open the PDF.",
                                  tone: "error",
                                });
                              });
                            }}
                            className={BUTTON}
                          >
                            Preview résumé
                          </button>
                        ) : null}
                        <button
                          type="button"
                          disabled={inFlight}
                          aria-busy={inFlight}
                          aria-label={`${row.disputed ? "Withdraw flag" : "Flag as wrongly filtered"}: ${named}`}
                          title={
                            row.disputed
                              ? "Withdraw your flag on this call."
                              : "Record that you think this call is wrong. The job stays filtered out."
                          }
                          onClick={() => {
                            onDispute(row);
                          }}
                          className={BUTTON}
                        >
                          {row.disputed ? "Withdraw flag" : "Flag as wrongly filtered"}
                        </button>
                        <button
                          type="button"
                          disabled={inFlight}
                          aria-busy={inFlight}
                          aria-label={`Record application anyway: ${named}`}
                          title="You applied despite the filter. Moves it to the Applied page; undoable from the toast."
                          onClick={() => {
                            onApplied(row);
                          }}
                          className={BUTTON}
                        >
                          Record application anyway
                        </button>
                      </span>
                    </td>
                  </tr>
                  {isOpen ? (
                    <tr id={evidenceId} className="bg-surface-2">
                      <td colSpan={5}>
                        <Evidence postingId={row.posting_id} named={named} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
            {visible.length > 0 ? null : (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-sm text-fg-2">
                  {data.rows.length === 0
                    ? "No delivered job has been filtered out right now."
                    : query.trim() !== ""
                      ? "No filtered-out job matches that search. Clear the search to see them all."
                      : "None of these was read as clear by the independent review. Press the count above again to see them all."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
