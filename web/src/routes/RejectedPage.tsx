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
import { JudgeVerdictBadge } from "../components/JudgeVerdictBadge";
import type { ToastRequest } from "../hooks/useToasts";
import { EM_DASH, isSafeHttpUrl } from "../lib/format";

/*
 * The rejected leads: what the rules turned away, which the queue only COUNTS in its `ineligible`
 * cell. Read to catch a wrong rejection — each lead's evidence names the rule and quotes the span
 * it read — and to act on one: apply anyway (an owner statement outranks a derived verdict), or
 * dispute it, which records the disagreement for the next precision audit and moves nothing.
 *
 * Leads the final gate called eligible arrive first and can be shown alone: the rules and the gate
 * disagreeing is the likeliest sign of a false reject.
 */

const BUTTON =
  "inline-flex min-h-11 items-center rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg disabled:text-fg-3";

/** Evidence rows the rules recorded — the ones carrying a `rule` — with what failed first. A row
 *  without a rule is a résumé-coverage term, which is not about the rejection. */
const ORDER: Record<string, number> = { unmet: 0, unknown: 1, met: 2 };

function evidenceRows(requirements: RequirementView[]): RequirementView[] {
  return requirements
    .filter((item) => item.rule !== null)
    .sort((a, b) => (ORDER[a.disposition ?? ""] ?? 3) - (ORDER[b.disposition ?? ""] ?? 3));
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
        if (live) setFailed(caught instanceof Error ? caught.message : "Could not load the evidence.");
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
        <p className="text-sm text-fg-2">No eligibility rule recorded evidence against this posting.</p>
      ) : (
        <ul aria-label={`Why ${named} was rejected`} className="flex flex-col gap-3">
          {rows.map((item) => (
            <li
              key={`${item.rule ?? ""}-${item.requirement}`}
              className="border-l-2 border-control pl-3"
            >
              <p className="flex flex-wrap items-center gap-2 text-xs text-fg-2">
                <span className="text-fg">{item.rule}</span>
                {/* In words: "not met" is the reading that rejects, and it must not be told apart
                    from "unknown" by colour alone. */}
                {item.disposition === "unmet" ? (
                  <Badge label="not met" emphasis="strong" />
                ) : (
                  <span>{item.disposition ?? EM_DASH}</span>
                )}
                {item.profile_field === null ? null : (
                  <span>
                    read <span className="font-mono">{item.profile_field}</span>
                  </span>
                )}
              </p>
              {item.rationale === null ? null : (
                <p className="mt-1 text-xs text-fg-2">{item.rationale}</p>
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
          <p className="mt-2 max-h-96 max-w-[68ch] overflow-y-auto leading-relaxed whitespace-pre-wrap">
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
          setError(caught instanceof Error ? caught.message : "Could not load the rejected leads.");
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
              ? `Withdrew the dispute on ${named}.`
              : `Disputed the rejection of ${named}. It stays rejected; the dispute is kept for the next audit.`,
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
      const named = `${row.company} — ${row.title}`;
      mark(row.posting_id, true);
      void markApplied(row.posting_id)
        .then(() => {
          push({
            message: `Marked applied: ${named}. Undo withdraws it.`,
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
            message: caught instanceof Error ? caught.message : "Could not mark that applied.",
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
      <p role="alert" className="rounded-md border border-fg-2 bg-surface p-4 text-sm text-fg">
        {error}
      </p>
    );
  }
  if (data === null) {
    return (
      <p role="status" className="p-4 text-sm text-fg-2">
        Loading the rejected leads…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Rejected leads status" className="flex flex-col">
        <dl className="flex flex-wrap items-stretch divide-x divide-divider rounded-md border border-divider bg-surface">
          <div className="flex min-w-28 flex-col gap-1 px-4 py-3">
            <dt className="label-micro text-fg-3">rejected</dt>
            <dd className="font-display text-lg text-fg-2 tabular-nums">
              {data.counts.total.toLocaleString()}
            </dd>
          </div>
          <div className="flex min-w-28 flex-col gap-1 px-4 py-3">
            <dt className={`label-micro ${gateOnly ? "text-fg-2" : "text-fg-3"}`}>gate eligible</dt>
            <dd>
              <button
                type="button"
                aria-pressed={gateOnly}
                aria-label={`gate eligible ${data.counts.gate_eligible.toLocaleString()} — ${
                  gateOnly ? "showing only these, activate to clear" : "show only these"
                }`}
                title="Rejected by the rules, but the final gate read the posting as eligible. Click to show only these."
                onClick={() => {
                  setGateOnly((current) => !current);
                }}
                className={`inline-flex min-h-11 w-full cursor-pointer items-center rounded-sm px-1 font-display text-lg tabular-nums transition-colors duration-[120ms] ease-snap ${
                  gateOnly
                    ? "bg-surface-3 text-fg shadow-[inset_0_-2px_0_0_var(--color-accent)]"
                    : "text-fg-2 hover:bg-surface-2"
                }`}
              >
                {data.counts.gate_eligible.toLocaleString()}
              </button>
            </dd>
          </div>
          <div className="flex min-w-28 flex-col gap-1 px-4 py-3">
            <dt className="label-micro text-fg-3">disputed</dt>
            <dd className="font-display text-lg text-fg-2 tabular-nums">
              {data.counts.disputed.toLocaleString()}
            </dd>
          </div>
          <div
            role="status"
            className="ml-auto flex items-center px-4 py-3 text-sm text-fg-2 tabular-nums"
          >
            Showing {visible.length.toLocaleString()} of {data.counts.total.toLocaleString()}
          </div>
        </dl>
      </section>

      <p className="max-w-[80ch] text-sm text-fg-2">
        Leads the eligibility rules rejected after a run delivered them. They are not in the queue
        and their folders sit in <code className="text-fg-3">_ineligible</code>. Open “Why” to read
        the rule and the words it quoted. Dispute records that you disagree and changes nothing
        else; apply anyway if you are sure.
      </p>

      <label className="flex min-w-64 max-w-md flex-col gap-1.5">
        <span className="label-micro text-fg-3">Filter company, title, location</span>
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
        />
      </label>

      <div className="overflow-x-auto rounded-md bg-surface shadow-[0_1px_0_0_var(--color-divider)_inset,0_16px_40px_-24px_rgb(0_0_0/0.9)]">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Leads the eligibility rules rejected, those the final gate called eligible first.
          </caption>
          <thead>
            {/* Not sticky: inside `overflow-x-auto` the wrapper is the sticky container, and the
                app header's offset would push this row down over the first lead. */}
            <tr className="bg-surface label-micro text-fg-3 [&>*]:border-b [&>*]:border-divider">
              <th scope="col" className="px-3 py-2 text-left font-normal">company</th>
              <th scope="col" className="px-3 py-2 text-left font-normal">title</th>
              <th scope="col" className="px-3 py-2 text-left font-normal">location</th>
              <th scope="col" className="px-3 py-2 text-left font-normal">gate</th>
              <th scope="col" className="px-3 py-2 text-right font-normal">actions</th>
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
                            label="disputed"
                            reason="You disputed this rejection. The verdict stands until the rules change."
                          />
                        ) : null}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-fg-3">{row.location ?? EM_DASH}</td>
                    <td className="px-3 py-1.5">
                      <JudgeVerdictBadge verdict={row.judge_verdict} />
                    </td>
                    <td className="px-3 py-1.5">
                      <span className="flex flex-wrap items-center justify-end gap-2">
                        <button
                          type="button"
                          aria-expanded={isOpen}
                          aria-controls={evidenceId}
                          aria-label={`Why: ${named}`}
                          onClick={() => {
                            setOpen((current) => {
                              const next = new Set(current);
                              if (!next.delete(row.posting_id)) next.add(row.posting_id);
                              return next;
                            });
                          }}
                          className={BUTTON}
                        >
                          Why
                        </button>
                        {isSafeHttpUrl(url) && url !== null ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`Open apply link: ${named}`}
                            className={BUTTON}
                          >
                            Apply link
                          </a>
                        ) : null}
                        {row.pdf_available ? (
                          <button
                            type="button"
                            aria-label={`Open PDF: ${named}`}
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
                            Open PDF
                          </button>
                        ) : null}
                        <button
                          type="button"
                          disabled={inFlight}
                          aria-busy={inFlight}
                          aria-label={`${row.disputed ? "Withdraw dispute" : "Dispute"}: ${named}`}
                          title={
                            row.disputed
                              ? "Withdraw your dispute of this rejection."
                              : "Record that you think this rejection is wrong. The lead stays rejected."
                          }
                          onClick={() => {
                            onDispute(row);
                          }}
                          className={BUTTON}
                        >
                          {row.disputed ? "Withdraw dispute" : "Dispute"}
                        </button>
                        <button
                          type="button"
                          disabled={inFlight}
                          aria-busy={inFlight}
                          aria-label={`Mark applied anyway: ${named}`}
                          title="You applied despite the rejection. Moves it to the Applied page; undoable from the toast."
                          onClick={() => {
                            onApplied(row);
                          }}
                          className={BUTTON}
                        >
                          Mark applied anyway
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
                    ? "No delivered lead is rejected right now."
                    : query.trim() !== ""
                      ? "No rejected lead matches that search. Clear the text box to see them all."
                      : "No rejected lead was called eligible by the final gate. Take the gate eligible cell again to see them all."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
