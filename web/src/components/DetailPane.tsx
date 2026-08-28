import { useEffect, useRef, useState } from "react";

import { openPdf, revealFolder } from "../api/client";
import type { Answers, QueueDetail, RequirementView } from "../api/types";
import {
  EM_DASH,
  formatAge,
  formatFraction,
  formatScore,
  formatTimestamp,
  parentDirectory,
  pathFromFileUri,
} from "../lib/format";
import { AnswersPanel } from "./AnswersPanel";
import { ApplyLink } from "./ApplyLink";
import { Badge } from "./Badge";
import { CopyButton } from "./CopyButton";
import { VerdictChip } from "./VerdictChip";

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] tracking-wide text-fg-3 uppercase">{label}</span>
      <span className="text-sm text-fg tabular-nums">{value}</span>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  emphasis = "normal",
  title,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  emphasis?: "normal" | "strong";
  title?: string;
  disabled?: boolean;
}) {
  const skin =
    emphasis === "strong"
      ? "border-fg-2 bg-surface-2 text-fg hover:border-fg hover:bg-surface"
      : "border-control text-fg-2 hover:border-fg-2 hover:text-fg";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      {...(title ? { title } : {})}
      className={`inline-flex min-h-11 items-center rounded border px-3 text-sm transition-colors duration-150 ease-in-out disabled:border-divider disabled:text-fg-3 ${skin}`}
    >
      {label}
    </button>
  );
}

/*
 * Requirements. When the job description yields NO recognised requirements the pane says so in
 * words: two empty lists read as "nothing missing", which is the most dangerous possible rendering,
 * and it is not rare — 3 of run 114's 10 leads were in exactly that state.
 */
function Requirements({ requirements }: { requirements: RequirementView[] }) {
  if (requirements.length === 0) {
    return (
      <div className="rounded border border-fg-2 bg-surface-2 p-3">
        <p className="text-sm text-fg">
          This job description yielded no recognised requirements.
        </p>
        <p className="mt-1 text-xs text-fg-2">
          Empty covered and missing lists here mean nothing was extracted — not that nothing is
          missing. Read the description below before deciding.
        </p>
      </div>
    );
  }
  const covered = requirements.filter((item) => item.covered);
  const missing = requirements.filter((item) => !item.covered);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {[
        { title: `covered (${String(covered.length)})`, items: covered },
        { title: `missing (${String(missing.length)})`, items: missing },
      ].map((group) => (
        <div key={group.title}>
          <h4 className="mb-1.5 text-[11px] tracking-wide text-fg-3 uppercase">{group.title}</h4>
          {group.items.length === 0 ? (
            <p className="text-xs text-fg-3">none</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {group.items.map((item) => (
                <li key={item.requirement} className="text-sm text-fg-2">
                  {item.requirement}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

/** One row per rule that fired, quoting the span it read out of the frozen description. */
function Evidence({ requirements }: { requirements: RequirementView[] }) {
  const evidence = requirements.filter((item) => item.rule !== null);
  if (evidence.length === 0) {
    return (
      <p className="text-xs text-fg-2">
        No eligibility rule recorded evidence against this posting.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {evidence.map((item) => (
        <li key={`${item.rule ?? ""}-${item.requirement}`} className="border-l-2 border-control pl-3">
          <p className="text-xs text-fg-2">
            <span className="text-fg">{item.rule}</span>
            {item.disposition === null ? null : (
              <>
                {" · "}
                {item.disposition}
              </>
            )}
            {item.profile_field === null ? null : (
              <>
                {" · read "}
                <span className="font-mono">{item.profile_field}</span>
              </>
            )}
          </p>
          {item.rationale === null ? null : (
            <p className="mt-1 text-xs text-fg-2">{item.rationale}</p>
          )}
          {item.quote === null ? null : (
            <blockquote className="mt-1 text-xs text-fg-3 italic">“{item.quote}”</blockquote>
          )}
        </li>
      ))}
    </ul>
  );
}

export function DetailPane({
  detail,
  loading,
  error,
  answers,
  onClose,
  onApplied,
  onSkip,
  onToast,
}: {
  detail: QueueDetail | null;
  loading: boolean;
  error: string | null;
  answers: Answers | null;
  onClose: () => void;
  onApplied: () => void;
  onSkip: () => void;
  onToast: (message: string, tone: "info" | "error") => void;
}) {
  const [shown, setShown] = useState(false);
  const pane = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setShown(true);
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, []);

  /*
   * Focus, but only where the pane is a full-screen SHEET — below `lg` it is `fixed inset-0` over
   * everything, and a keyboard reader who opened it was left behind it with no way in. Above `lg`
   * it is a column beside the list, and stealing focus there would break the fast path the list
   * exists for: Enter to look, ↓ to carry on down the queue.
   *
   * The trigger row is refocused on close so the cursor does not fall back to `<body>`.
   */
  useEffect(() => {
    if (window.matchMedia("(min-width: 64rem)").matches) return;
    const opener = document.activeElement as HTMLElement | null;
    pane.current?.focus();
    return () => {
      opener?.focus();
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const row = detail?.row ?? null;
  const pdfPath = pathFromFileUri(row?.pdf_uri ?? null);
  const folder = parentDirectory(pdfPath);

  return (
    <aside
      ref={pane}
      tabIndex={-1}
      aria-label="Lead detail"
      /*
       * `lg:top-header` and `lg:z-auto`, both load-bearing. At `top-0` with `z-40` the pane slid
       * OVER the sticky app header — measured at scroll 900, the pane's top was y=0 and the header
       * was covered from x=1072 rightward, taking the Queue/Runs tabs with it. It now stops at the
       * header's own height and no longer outranks it.
       */
      className={`fixed inset-0 z-40 flex flex-col overflow-y-auto border-divider bg-surface transition-[opacity,translate] duration-[180ms] ease-out lg:sticky lg:inset-auto lg:top-header lg:z-auto lg:h-[calc(100vh-var(--spacing-header))] lg:border-l ${
        shown ? "translate-x-0 opacity-100" : "translate-x-2 opacity-0"
      }`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-divider px-4 py-2">
        <span className="text-[11px] tracking-wide text-fg-3 uppercase">Lead detail</span>
        <button
          type="button"
          onClick={onClose}
          className="min-h-11 min-w-11 rounded text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg"
          aria-label="Close detail"
        >
          ✕
        </button>
      </div>

      {loading || row === null ? (
        <p className="px-4 py-6 text-sm text-fg-2">{error ?? "Loading lead…"}</p>
      ) : (
        <div className="flex flex-col gap-5 px-4 py-4">
          {/* THE DOMINANT CELL. Everything needed to decide, before any prose. */}
          <section className="rounded border border-fg-2 bg-surface-2 p-4">
            <h2 className="text-lg leading-snug text-fg">{row.title}</h2>
            <p className="mt-0.5 text-sm text-fg-2">
              {row.company}
              {row.location === null ? "" : ` · ${row.location}`}
            </p>

            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Fact label="remote policy" value={row.remote_policy ?? EM_DASH} />
              <Fact label="age" value={formatAge(row.posted_days)} />
              <Fact label="status" value={row.status} />
              <Fact label="score · as of now" value={formatScore(row.score)} />
              <Fact label="coverage · as of now" value={formatFraction(row.coverage)} />
              <Fact label="first seen" value={formatTimestamp(row.first_seen)} />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <VerdictChip verdict={row.verdict} />
              {row.status === "closed" ? (
                <Badge
                  label="closed"
                  emphasis="strong"
                  reason="The posting is no longer open on the board."
                />
              ) : null}
              {/* The reason is VISIBLE here, not a tooltip: "unverifiable" is a claim about what
                  boardwatch can know, and a bare word invites the reader to guess wrong. */}
              {row.status === "unverifiable" ? (
                <Badge
                  label="unverifiable"
                  reason="Nothing enumerates this company's board, so the posting cannot be confirmed still open or closed."
                  showReason
                />
              ) : null}
              {row.thin_jd ? (
                <Badge
                  label="thin JD"
                  reason="No coverage fraction could be computed from this description."
                  showReason
                />
              ) : null}
              {row.target_flag === true ? <Badge label="target company" /> : null}
            </div>

            {row.off_target ? (
              <div className="mt-3">
                <Badge label="off target" reason={row.off_target_reason} showReason />
              </div>
            ) : null}

            <p className="mt-4 text-xs text-fg-3">
              Score and coverage are recomputed now, not as delivered
              {row.delivered_run_id === null
                ? "."
                : ` (delivered by run ${String(row.delivered_run_id)}).`}
              {detail?.board_target === null || detail === null
                ? ""
                : ` Board target ${detail.board_target}.`}
            </p>
          </section>

          {/* Actions. "Copy PDF path" is the highest-value control in the app: both the macOS and
              the Windows file dialog accept a pasted absolute path. */}
          <section className="flex flex-wrap gap-2">
            <ApplyLink url={row.apply_url} />

            {pdfPath === null ? (
              <span className="inline-flex min-h-11 items-center rounded border border-divider px-3 text-sm text-fg-3">
                no PDF built
              </span>
            ) : (
              <>
                <CopyButton
                  value={pdfPath}
                  label="Copy PDF path"
                  variant="primary"
                  onError={(message) => {
                    onToast(message, "error");
                  }}
                  title={`Paste this straight into the file dialog: ${pdfPath}`}
                />
                <ActionButton
                  label="Open PDF"
                  title="Opens inline, in a new tab."
                  onClick={() => {
                    void openPdf(row.posting_id).catch((caught: unknown) => {
                      onToast(caught instanceof Error ? caught.message : "Could not open the PDF.", "error");
                    });
                  }}
                />
                <ActionButton
                  label="Reveal folder"
                  {...(folder === null ? {} : { title: folder })}
                  onClick={() => {
                    void revealFolder(row.posting_id)
                      .then((result) => {
                        if (!result.ok) {
                          onToast(result.reason ?? "The folder could not be revealed.", "error");
                        }
                      })
                      .catch((caught: unknown) => {
                        onToast(
                          caught instanceof Error ? caught.message : "Reveal failed.",
                          "error",
                        );
                      });
                  }}
                />
              </>
            )}

            <ActionButton label="Mark applied" emphasis="strong" onClick={onApplied} />
            <ActionButton label="Skip" onClick={onSkip} />
          </section>

          <section>
            <h3 className="mb-2 text-[11px] tracking-wide text-fg-3 uppercase">requirements</h3>
            <Requirements requirements={detail?.requirements ?? []} />
          </section>

          <section>
            <h3 className="mb-2 text-[11px] tracking-wide text-fg-3 uppercase">evidence</h3>
            <Evidence requirements={detail?.requirements ?? []} />
          </section>

          <AnswersPanel
            answers={answers}
            onError={(message) => {
              onToast(message, "error");
            }}
          />

          {/* Secondary. Roughly a thousand words, so it is what you read AFTER deciding. Rendered
              as plain text: this is third-party content and never becomes markup. */}
          <section>
            <h3 className="mb-2 text-[11px] tracking-wide text-fg-3 uppercase">
              job description
            </h3>
            {detail?.jd_body === null || detail === null ? (
              <p className="rounded border border-control p-3 text-sm text-fg-2">
                No current posting version, so the frozen description is unavailable. Nothing above
                was read from it.
              </p>
            ) : (
              <div className="max-h-96 overflow-y-auto rounded border border-divider bg-bg p-3">
                <p className="text-sm leading-relaxed whitespace-pre-wrap text-fg-2">
                  {detail.jd_body}
                </p>
              </div>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}
