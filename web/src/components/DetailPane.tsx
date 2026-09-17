import { useEffect, useRef, useState } from "react";

import { openPdf, revealFolder } from "../api/client";
import type { Answers, QueueDetail, RequirementView } from "../api/types";
import { useMediaQuery } from "../hooks/useMediaQuery";
import {
  EM_DASH,
  followUpWindow,
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
import { JudgeVerdictBadge } from "./JudgeVerdictBadge";
import { ReviewReasonBadge } from "./ReviewReasonBadge";
import { VerdictChip } from "./VerdictChip";

/**
 * The `lg` breakpoint the pane's own `lg:` variants below are written against. When it MATCHES the
 * pane is a column beside the list; when it does not, the pane is `fixed inset-0` — an opaque
 * full-screen sheet, which makes it a modal. Exported because the page has to inert what the sheet
 * covers, and the two must never disagree about where the sheet begins.
 */
export const SIDE_BY_SIDE = "(min-width: 64rem)";

/**
 * The lead's title, which is what the sheet is ABOUT and therefore what names it to a screen
 * reader. One pane is open at a time, so a constant id is unambiguous.
 */
const TITLE_ID = "lead-detail-title";

/**
 * The follow-up date input. Exported because `QueuePage`'s `f` shortcut moves the cursor here,
 * and a shortcut that looked the element up by a hand-written selector would be a second copy of
 * this id. One pane is open at a time, so a constant id is unambiguous — the same reason
 * `TITLE_ID` is one.
 */
export const FOLLOW_UP_INPUT_ID = "lead-detail-follow-up";

/**
 * `note` is the server's own sentence about the number above it — the score's `why`, and nothing
 * else so far. It is prose rather than an instrument reading, so it is NOT `tabular-nums`.
 */
function Fact({
  label,
  value,
  note = null,
}: {
  label: string;
  value: string;
  note?: string | null;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="label-micro text-fg-3">{label}</span>
      <span className="text-sm text-fg tabular-nums">{value}</span>
      {note === null ? null : <span className="text-xs leading-snug text-fg-2">{note}</span>}
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  emphasis = "normal",
  title,
  ariaLabel,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  emphasis?: "normal" | "strong";
  title?: string;
  /* Only where the visible label is not a name on its own. It STARTS with the label wherever it
     is set, so Label in Name holds (SC 2.5.3). */
  ariaLabel?: string;
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
      {...(ariaLabel ? { "aria-label": ariaLabel } : {})}
      className={`inline-flex min-h-11 items-center rounded-sm border px-3 text-sm transition-colors duration-150 ease-in-out disabled:border-divider disabled:text-fg-3 ${skin}`}
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
      <div className="rounded-md border border-divider bg-surface-2 shadow-[0_16px_40px_-24px_rgb(0_0_0/0.9)] p-3">
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
          <h4 className="mb-1.5 label-micro text-fg-3">{group.title}</h4>
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
  onReport,
  onFollowUp,
  onToast,
  revealSupported = true,
}: {
  detail: QueueDetail | null;
  loading: boolean;
  error: string | null;
  answers: Answers | null;
  onClose: () => void;
  onApplied: () => void;
  onSkip: () => void;
  onReport: () => void;
  /** A `YYYY-MM-DD` date to pin, or `null` to clear the one this lead carries. */
  onFollowUp: (date: string | null) => void;
  onToast: (message: string, tone: "info" | "error") => void;
  /**
   * Whether THIS server can open a file manager at all. `false` omits the button rather than
   * leaving a control that can only ever answer with an error toast. Defaults to `true`, because
   * a viewer older than `meta.reveal_supported` sends nothing and a hidden control that would
   * have worked is the worse of the two mistakes.
   */
  revealSupported?: boolean;
}) {
  const [shown, setShown] = useState(false);
  /*
   * The description box's height. Collapsed by default at 36rem, which is roughly a screen of
   * prose on the pane's width — enough to see whether the JD is worth reading without the box
   * owning the rest of the scroll.
   */
  const [jdExpanded, setJdExpanded] = useState(false);
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
   * The other half is in `QueuePage`, which inerts what the sheet covers at that same tier: moving
   * focus in is worth nothing if Shift+Tab walks straight back out to a row behind the sheet.
   *
   * The cleanup hands focus back where it came from when the pane stops being a sheet WITHOUT
   * closing — growing the window across the breakpoint. Closing is not this effect's job: the
   * cursor goes back to the row for the lead's posting id, looked up at close time by
   * `QueuePage`'s `focusRow`, because by then the element remembered here can be the wrong one.
   *
   * SUBSCRIBED, not sampled. This used to read `matchMedia(...).matches` once on mount, which
   * answers for the tier the pane OPENED at and never again — so shrinking the window across the
   * breakpoint with a lead open turned the column into a modal sheet while focus stayed on
   * `<body>` behind it, exactly the state this effect exists to prevent, and now with the page
   * behind it inert as well. `useMediaQuery` re-runs the effect on the transition instead.
   */
  const sideBySide = useMediaQuery(SIDE_BY_SIDE);
  useEffect(() => {
    if (sideBySide) return;
    const opener = document.activeElement as HTMLElement | null;
    pane.current?.focus();
    return () => {
      opener?.focus();
    };
  }, [sideBySide]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  /*
   * The follow-up input's DRAFT, and the one commit path out of it.
   *
   * A commit per `onChange` wrote one POST per intermediate date: `<input type="date">` fires
   * `input` on every segment edit that leaves the value COMPLETE, so typing the year of
   * `2026-09-20` walked through `0002-09-20`, `0020-09-20` and `0202-09-20` first — four writes,
   * four stacked toasts whose undo carried an intermediate date, and a stored value decided by
   * response ordering rather than by the last keystroke. Commit on blur or Enter instead, which
   * is where a field's value is settled (`ux-interaction/forms/ux-form-validation-timing`).
   *
   * The PICKER still commits where it lands: one click in the browser's calendar is one whole
   * date and one intention, and making it wait for a blur would be a confirm step on the one
   * control here whose point is that it has none. The two are told apart by `typing`, which a
   * `keydown` on the input sets — the calendar popup is browser chrome, outside the document, so
   * a click in it dispatches no key event. Arrow keys inside the popup DO, and those fall to the
   * blur path, which is the safe direction: a deferred write, never a wrong one.
   *
   * `null` is "no edit in progress", NOT the empty string, and that is what keeps this to one
   * piece of state and no synchronising effect: with no draft the field simply renders the row,
   * so a rolled-back write, an undo and the reconciled echo all show through on their own. A
   * string means the reader is mid-edit and the draft wins until it is committed or abandoned.
   */
  const stored = detail?.row?.follow_up ?? "";
  const [draft, setDraft] = useState<string | null>(null);
  const shownFollowUp = draft ?? stored;
  const typing = useRef(false);
  const followUpBounds = followUpWindow();
  /* Takes the value rather than reading `shownFollowUp`, because the picker path commits from
     inside the same `onChange` that sets the draft and would read the render's stale copy. */
  const commitFollowUp = (value: string) => {
    typing.current = false;
    // Back to following the row, which is also why Enter and then a blur is ONE write: after
    // the first the field renders `stored`, so the second sees nothing to send.
    setDraft(null);
    // An EMPTY value writes nothing and the field snaps back: clearing is the button beside it,
    // never an emptied input. A date input reports "" for any INCOMPLETE date, so routing ""
    // to a clear would let an abandoned edit silently drop the stored date.
    if (value === "" || value === stored) return;
    onFollowUp(value);
  };

  const row = detail?.row ?? null;
  const requirements = detail?.requirements ?? [];
  /*
   * ONE fact, ONE place. `closed` and `unverifiable` each render a chip below with its reason
   * beside it, and `thin_jd` renders the chip that says why there is no coverage fraction — so a
   * `status` fact cell and a `coverage · —` fact cell above them were the same claim a second and
   * a third time. The fact cell is what goes: the chip carries the visible REASON, which is the
   * half a bare word cannot. Both cells stay wherever no chip renders.
   */
  const statusChipShown = row?.status === "closed" || row?.status === "unverifiable";
  const coverageChipShown = row?.thin_jd === true;
  const pdfPath = pathFromFileUri(row?.pdf_uri ?? null);
  const folder = parentDirectory(pdfPath);

  return (
    <aside
      ref={pane}
      tabIndex={-1}
      /*
       * A modal ONLY below `lg`. There the pane is `fixed inset-0` over a page `QueuePage` has
       * inerted — it blocks, so it says so, and a reader is told the rest of the page is gone
       * rather than left to discover it by tabbing. At or above `lg` it is a column beside a list
       * that stays fully operable, and a `dialog` role there would be a claim that is not true.
       *
       * Named by its own heading, which is the lead's title. `aria-label` is kept for the two
       * states that render no heading — loading, and a lead that failed to load — because an
       * `aria-labelledby` pointing at an element that does not exist yields no name at all.
       */
      role={sideBySide ? undefined : "dialog"}
      aria-modal={sideBySide ? undefined : true}
      aria-label={sideBySide || row === null ? "Lead detail" : undefined}
      aria-labelledby={!sideBySide && row !== null ? TITLE_ID : undefined}
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
        <span className="label-micro text-fg-3">Lead detail</span>
        <button
          type="button"
          onClick={onClose}
          className="min-h-11 min-w-11 rounded-sm text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg"
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
          <section className="rounded-md border border-divider bg-surface-2 shadow-[0_16px_40px_-24px_rgb(0_0_0/0.9)] p-4">
            <h2 id={TITLE_ID} className="text-lg leading-snug text-fg">
              {row.title}
            </h2>
            <p className="mt-0.5 text-sm text-fg-2">{row.company}</p>
            {/* Every location, comma-separated. The row can only afford the primary and a `+N`,
                so the pane is where the rest of the list has to be readable — and `?? []` for the
                usual reason: an older viewer omits the field (see `lib/format`'s header). */}
            {(row.locations ?? []).length > 0 ? (
              <p className="mt-0.5 text-sm text-fg-2">{(row.locations ?? []).join(", ")}</p>
            ) : row.location === null ? null : (
              <p className="mt-0.5 text-sm text-fg-2">{row.location}</p>
            )}

            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Fact label="remote policy" value={row.remote_policy ?? EM_DASH} />
              <Fact label="age" value={formatAge(row.posted_days)} />
              {statusChipShown ? null : <Fact label="status" value={row.status} />}
              <Fact label="score · as of now" value={formatScore(row.score)} note={row.why} />
              {coverageChipShown ? null : (
                <Fact label="coverage · as of now" value={formatFraction(row.coverage)} />
              )}
              <Fact label="first seen" value={formatTimestamp(row.first_seen)} />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <VerdictChip verdict={row.verdict} />
              {/* Directly beside the rules verdict, because the pane is opened to decide and the
                  two engines disagreeing is the fact that decides it. `showReason` for the reason
                  `unverifiable` and `thin JD` carry theirs visibly here: this chip asserts which
                  engine said what, and a bare `gate uncertain` invites the reader to read it as a
                  second opinion with the same standing as the chip beside it. It is not — a gate
                  `uncertain` does not move a lead out of the apply lane. */}
              <JudgeVerdictBadge verdict={row.judge_verdict} showReason />
              {row.status === "closed" ? (
                <Badge
                  label="closed"
                  emphasis="strong"
                  reason="The posting is no longer open on the board."
                  showReason
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

            {/* Reason VISIBLE, like `unverifiable` above: the pane is opened to decide what to do
                with a held lead, and a bare chip there invites the reader to guess wrong. */}
            {/* `== null` for the same reason as in ReviewReasonBadge: a viewer process older
                than the bundle it serves omits the field entirely. */}
            {row.review_reason == null ? null : (
              <div className="mt-3">
                <ReviewReasonBadge reason={row.review_reason} showReason />
              </div>
            )}

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

          {/*
            * Actions, in TWO groups with a rule between them, exactly as the row separates them.
            * The first group opens and copies and changes nothing; the second WRITES, and
            * "Mark applied" writes an application record the contract has no route to reverse.
            * One flat `flex-wrap` put "Mark applied" between "Reveal folder" and "Skip" as soon
            * as the seven buttons wrapped, which is the arrangement most likely to be misclicked.
            * Each group is its own flex box, so wrapping never interleaves them.
            *
            * "Copy PDF path" is the highest-value control in the app: both the macOS and the
            * Windows file dialog accept a pasted absolute path.
            */}
          <section className="flex flex-wrap items-start gap-2">
            <span className="flex flex-wrap items-center gap-2">
              <ApplyLink url={row.apply_url} />

              {pdfPath === null ? (
                <span className="inline-flex min-h-11 items-center rounded-sm border border-divider px-3 text-sm text-fg-3">
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
                  {!revealSupported ? null : (
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
                  )}
                </>
              )}
            </span>

            <span className="flex flex-wrap items-center gap-2 border-l border-divider pl-2">
              <ActionButton label="Mark applied" emphasis="strong" onClick={onApplied} />
              <ActionButton label="Skip" onClick={onSkip} />
              <ActionButton label="Report" onClick={onReport} />
            </span>

            {/*
              * The follow-up date, in the SAME action strip and behind its own rule, because it
              * is the one control here that writes without removing the lead: applied, skipped
              * and reported all take the row off the list, and this one pins a note to a row
              * that stays. No dialog and no confirm step — the platform's own date picker in
              * place, which is what a non-blocking input is for
              * (`anti-patterns/anti-modal-overuse`).
              *
              * A real `<label>` rather than an `aria-label`, so the words are visible and the
              * 44px hit target includes them. `?? ""` and never `?? undefined`: an uncontrolled
              * input that later becomes controlled is a React warning and a lost keystroke, and
              * an older server omits the field entirely. Clearing is the button, never the empty
              * input — see the `onChange` below.
              */}
            <span className="flex flex-wrap items-center gap-2 border-l border-divider pl-2">
              <label
                htmlFor={FOLLOW_UP_INPUT_ID}
                className="label-micro text-fg-3"
              >
                Follow up on
              </label>
              <input
                id={FOLLOW_UP_INPUT_ID}
                type="date"
                value={shownFollowUp}
                /* The same two-sided window the route enforces, so the picker cannot offer a
                   date that comes back a 400 — see `followUpWindow`. */
                min={followUpBounds.min}
                max={followUpBounds.max}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    // Enter settles the value without leaving the field, which is what a reader
                    // who typed a date expects of it. No `preventDefault`: there is no form to
                    // submit and the browser's own Enter handling here is a no-op.
                    commitFollowUp(shownFollowUp);
                    return;
                  }
                  typing.current = true;
                }}
                onChange={(event) => {
                  const next = event.target.value;
                  setDraft(next);
                  if (!typing.current) commitFollowUp(next);
                }}
                onBlur={() => {
                  commitFollowUp(shownFollowUp);
                }}
                className="min-h-11 rounded-sm border border-control bg-surface px-2 text-sm text-fg tabular-nums"
              />
              <ActionButton
                label="Clear"
                title="Remove this lead's follow-up date."
                ariaLabel="Clear follow-up"
                disabled={row.follow_up == null}
                onClick={() => {
                  onFollowUp(null);
                }}
              />
            </span>
          </section>

          <section>
            <h3 className="mb-2 label-micro text-fg-3">requirements</h3>
            <Requirements requirements={requirements} />
          </section>

          <section>
            <h3 className="mb-2 label-micro text-fg-3">evidence</h3>
            <Evidence requirements={requirements} />
          </section>

          {/* Roughly a thousand words, so it is what you read AFTER deciding — but BEFORE the
              answers panel, which is a clipboard tool rather than something to read. The
              requirements block above tells the reader to "read the description below" whenever
              nothing was extracted, and until this moved that instruction pointed past 779px of
              mostly-unset identity fields. Rendered as plain text: this is third-party content
              and never becomes markup. */}
          <section>
            <h3 className="mb-2 label-micro text-fg-3">
              job description
            </h3>
            {detail?.jd_body === null || detail === null ? (
              <p className="rounded-md border border-control p-3 text-sm text-fg-2">
                No current posting version, so the frozen description is unavailable. Nothing above
                was read from it.
              </p>
            ) : (
              <>
                {/*
                  * The frozen body carries NO newlines, so `whitespace-pre-wrap` has nothing to
                  * wrap and a 6,000-character JD renders as one unbroken paragraph. Nothing here
                  * alters or infers structure in third-party text — the only honest fixes
                  * available at render time are typographic: a 68ch measure so a line is a line
                  * rather than a 1,900px scan, and `leading-relaxed` (1.625) so the reader can
                  * find their way back to the start of the next one.
                  */}
                <div
                  className={`overflow-y-auto rounded-md border border-divider bg-bg p-3 ${
                    jdExpanded ? "" : "max-h-[36rem]"
                  }`}
                >
                  <p className="max-w-[68ch] text-sm leading-relaxed whitespace-pre-wrap text-fg-2">
                    {detail.jd_body}
                  </p>
                </div>
                <button
                  type="button"
                  aria-expanded={jdExpanded}
                  aria-label={`${jdExpanded ? "Collapse" : "Expand"} the job description`}
                  onClick={() => {
                    setJdExpanded((current) => !current);
                  }}
                  className="mt-2 inline-flex min-h-11 items-center rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg"
                >
                  {jdExpanded ? "Collapse" : "Expand"}
                </button>
              </>
            )}
          </section>

          {/* COLLAPSED when nothing was extracted, because there the requirements block's own
              copy sends the reader to the description above — and this panel, expanded, measured
              779px of a 2,050px pane on the live store, so it would sit between the instruction
              and the thing it points at. Expanded otherwise: the owner opened the pane on
              purpose. */}
          <AnswersPanel
            answers={answers}
            defaultOpen={requirements.length > 0}
            onError={(message) => {
              onToast(message, "error");
            }}
          />
        </div>
      )}
    </aside>
  );
}
