import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { openPdf, revealFolder } from "../api/client";
import type { AppliedIdenticalJd, Answers, QueueDetail, QueueRow, RequirementView } from "../api/types";
import { useMediaQuery } from "../hooks/useMediaQuery";
import {
  EM_DASH,
  followUpWindow,
  formatDateWithYear,
  formatFraction,
  formatScore,
  formatTimestamp,
  isoDaysFromToday,
  parentDirectory,
  pathFromFileUri,
} from "../lib/format";
import {
  availabilityMark,
  classifyRequirements,
  materialsMark,
  nothingFlaggedSentence,
  requirementsMark,
  reviewMark,
  reviewsDiffer,
  whatToCheck,
} from "../lib/jobStatus";
import { AnswersPanel } from "./AnswersPanel";
import { ApplyLink } from "./ApplyLink";
import { Badge } from "./Badge";
import { CopyButton } from "./CopyButton";
import { Icon } from "./Icon";
import { StatusMark } from "./StatusMark";

/**
 * The `lg` breakpoint the pane's own `lg:` variants below are written against. When it MATCHES the
 * workspace is a column beside the list; when it does not, it is `fixed inset-0` — an opaque
 * full-screen sheet, which makes it a modal. Exported because the page has to inert what the sheet
 * covers, and the two must never disagree about where the sheet begins.
 */
export const SIDE_BY_SIDE = "(min-width: 64rem)";

/** The workspace's own element, so the page can put focus back into the sheet after a prompt that
 *  sat above it closes. */
export const PANE_ID = "lead-detail";

/** The job's title, which is what the workspace is ABOUT and therefore what names it to a screen
 *  reader. One workspace is open at a time, so a constant id is unambiguous. */
const TITLE_ID = "lead-detail-title";

/** The follow-up date input. Exported because `QueuePage`'s `f` shortcut moves the cursor here. */
export const FOLLOW_UP_INPUT_ID = "lead-detail-follow-up";

/** The description's own anchor, so "Show in description" has one place to land. */
const DESCRIPTION_ID = "lead-detail-description";

/** Descriptions under this many characters are shown whole, with no fold and no box to scroll. */
const SHORT_DESCRIPTION = 2800;

const BUTTON =
  "inline-flex min-h-11 items-center gap-2 rounded-sm px-3.5 text-sm font-medium transition-colors duration-150 ease-in-out disabled:text-fg-3";

function ActionButton({
  label,
  onClick,
  tone = "quiet",
  title,
  ariaLabel,
  disabled = false,
  icon,
}: {
  label: string;
  onClick: () => void;
  tone?: "quiet" | "filled";
  title?: string;
  /* Only where the visible label is not a name on its own. It STARTS with the label wherever it
     is set, so Label in Name holds (SC 2.5.3). */
  ariaLabel?: string;
  disabled?: boolean;
  icon?: "file" | "folder" | "external";
}) {
  const skin =
    tone === "filled"
      ? "bg-surface-3 text-fg hover:bg-surface-2"
      : "text-fg-2 hover:bg-surface-3 hover:text-fg";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      {...(title ? { title } : {})}
      {...(ariaLabel ? { "aria-label": ariaLabel } : {})}
      className={`${BUTTON} ${skin}`}
    >
      {icon === undefined ? null : <Icon name={icon} />}
      {label}
    </button>
  );
}

function Section({
  title,
  id,
  hint,
  children,
}: {
  title: string;
  id?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section {...(id === undefined ? {} : { id })} className="flex flex-col gap-3">
      <div>
        <h3 className="text-base text-fg">{title}</h3>
        {hint === undefined ? null : <p className="mt-0.5 text-sm text-fg-2">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

/**
 * Where a quoted span sits in the description, as `[start, end)`, or null when it is not there.
 * Exact first — the engine slices its quotes out of this same frozen body — and case-folded as the
 * fallback. Never fuzzier than that: a highlight on text the rule did not read would be a claim
 * about the evidence that is not true.
 */
export function locateQuote(body: string, quote: string): [number, number] | null {
  if (quote === "") return null;
  let start = body.indexOf(quote);
  // Only where lower-casing keeps every length: "İ" lower-cases to two code units, and an offset
  // found in the folded copy would then slice the wrong characters out of the original.
  const folded = body.toLowerCase();
  const foldedQuote = quote.toLowerCase();
  if (start === -1 && folded.length === body.length && foldedQuote.length === quote.length) {
    start = folded.indexOf(foldedQuote);
  }
  return start === -1 ? null : [start, start + quote.length];
}

/** A button that jumps to a quoted span in the description. Offered only where the span is really
 *  there, so it never promises a jump it cannot make. */
function ShowInDescription({
  quote,
  jdBody,
  onShow,
}: {
  quote: string | null | undefined;
  jdBody: string | null;
  onShow: (quote: string) => void;
}) {
  if (quote == null || jdBody === null || locateQuote(jdBody, quote) === null) return null;
  return (
    <button
      type="button"
      onClick={() => {
        onShow(quote);
      }}
      className="mt-1 inline-flex min-h-11 items-center rounded-sm px-1 text-sm text-accent underline underline-offset-4 transition-colors duration-150 ease-in-out hover:text-fg"
    >
      Show in description
    </button>
  );
}

/**
 * WHAT TO CHECK. The decision-relevant things, each with the words the posting actually uses.
 *
 * Confirmed blockers come first, then what could not be confirmed. An unconfirmed requirement is
 * "Check: …", never "Missing": the rule could not decide, so it is neither met nor unmet, and the
 * wire's `covered: false` for it is a fact about a boolean, not about the job. When nothing is
 * flagged the sentence says what was and was not checked — it never says the job is approved.
 */
function WhatToCheck({
  detail,
  onShow,
}: {
  detail: QueueDetail;
  onShow: (quote: string) => void;
}) {
  const items = whatToCheck(detail);
  const eligibilitySeen = detail.requirements.filter(
    (item) => item.rule !== null || item.disposition !== null,
  ).length;
  return (
    <Section title="What to check">
      {items.length === 0 ? (
        <p className="flex items-start gap-2 text-sm text-fg-2">
          {/* A tick only when something was checked and cleared; "nothing was checked" is a dash. */}
          {detail.row.verdict === "eligible" && eligibilitySeen > 0 ? (
            <Icon name="check" className="mt-0.5 text-ok" />
          ) : (
            <Icon name="dash" className="mt-0.5 text-fg-3" />
          )}
          <span>{nothingFlaggedSentence(detail.row, eligibilitySeen)}</span>
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <li key={item.key} className="rounded-md bg-surface-2 p-3.5">
              <StatusMark mark={{ label: item.headline, tone: item.tone }} size="md" className="font-medium" />
              {item.body === undefined ? null : (
                <p className="mt-1 max-w-[62ch] pl-[1.375rem] text-sm text-fg-2">{item.body}</p>
              )}
              {item.quote == null ? null : (
                <blockquote className="mt-2 ml-[1.375rem] max-w-[62ch] rounded-sm bg-surface px-3 py-2 text-sm text-fg">
                  “{item.quote}”
                </blockquote>
              )}
              <div className="pl-[1.375rem]">
                <ShowInDescription quote={item.quote} jdBody={detail.jd_body} onShow={onShow} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** One rule's finding: its words, the profile field it read, and the span it quoted. Technical
 *  detail, so it lives under "Why this status?" and the rule's name is the one place mono is used. */
function EvidenceRow({
  item,
  jdBody,
  onShow,
}: {
  item: RequirementView;
  jdBody: string | null;
  onShow: (quote: string) => void;
}) {
  return (
    <li className="rounded-sm bg-surface px-3 py-2">
      <p className="text-sm text-fg">{item.requirement}</p>
      <p className="mt-0.5 text-xs text-fg-3">
        {item.rule === null ? null : <span className="font-mono">{item.rule}</span>}
        {item.profile_field === null ? null : (
          <>
            {" · read "}
            <span className="font-mono">{item.profile_field}</span>
          </>
        )}
      </p>
      {item.rationale === null ? null : (
        <p className="mt-1 text-sm text-fg-2">{item.rationale}</p>
      )}
      {item.quote === null ? null : (
        <blockquote className="mt-1 text-sm text-fg-2 italic">“{item.quote}”</blockquote>
      )}
      <ShowInDescription quote={item.quote} jdBody={jdBody} onShow={onShow} />
    </li>
  );
}

function RequirementGroup({
  title,
  explain,
  items,
  jdBody,
  onShow,
}: {
  title: string;
  explain: string;
  items: RequirementView[];
  jdBody: string | null;
  onShow: (quote: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-sm font-semibold text-fg">
        {title} ({items.length})
      </h4>
      <p className="mb-1.5 text-xs text-fg-3">{explain}</p>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <EvidenceRow
            key={`${item.rule ?? ""}-${item.requirement}`}
            item={item}
            jdBody={jdBody}
            onShow={onShow}
          />
        ))}
      </ul>
    </div>
  );
}

/**
 * WHY THIS STATUS. Every reading, side by side and never merged: the rules, the independent
 * review, the posting, the résumé. Two readings that disagree are both printed. The four
 * requirement states are kept apart — confirmed satisfied, confirmed unmet, not confirmed, not
 * assessed — and résumé keywords are a separate question under their own heading.
 */
function WhyThisStatus({
  detail,
  onShow,
}: {
  detail: QueueDetail;
  onShow: (quote: string) => void;
}) {
  const { row } = detail;
  const classified = classifyRequirements(detail.requirements);
  const keywordTotal = classified.keywordsPresent.length + classified.keywordsAbsent.length;
  return (
    <details className="group rounded-md bg-surface-2">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-md px-4 text-base font-semibold text-fg [&::-webkit-details-marker]:hidden">
        Why this status?
        <Icon name="chevronDown" className="transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-5 px-4 pt-1 pb-4">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {(
            [
              ["Requirements (rules)", requirementsMark(row.verdict)],
              ["Independent review", reviewMark(row.judge_verdict)],
              ["Posting availability", availabilityMark(row.status)],
              ["Résumé", materialsMark(row.pdf_available)],
            ] as const
          ).map(([name, mark]) => (
            <div key={name}>
              <dt className="text-xs text-fg-3">{name}</dt>
              <dd className="mt-0.5">
                <StatusMark mark={mark} size="md" />
              </dd>
            </div>
          ))}
        </dl>
        {reviewsDiffer(row) ? (
          <p className="text-sm text-fg-2">
            The rules and the independent review read this job differently. Neither overrides the
            other; both stay as they are, so you can weigh them.
          </p>
        ) : null}

        {detail.requirements.length === 0 ? (
          <p className="text-sm text-fg-2">
            No requirements were extracted from this description, so none was checked. That is not
            the same as none being met.
          </p>
        ) : null}
        <RequirementGroup
          title="Not met"
          explain="The rules read this and found it unmet, and quoted the words."
          items={classified.unmet}
          jdBody={detail.jd_body}
          onShow={onShow}
        />
        <RequirementGroup
          title="Not confirmed"
          explain="The rules could not decide — neither met nor unmet. Read the quoted words."
          items={classified.unconfirmed}
          jdBody={detail.jd_body}
          onShow={onShow}
        />
        <RequirementGroup
          title="Confirmed satisfied"
          explain="The rules read this against your profile and found it met."
          items={classified.satisfied}
          jdBody={detail.jd_body}
          onShow={onShow}
        />
        <RequirementGroup
          title="Not assessed"
          explain="Evidence for these was recorded without a finding."
          items={classified.notAssessed}
          jdBody={detail.jd_body}
          onShow={onShow}
        />

        {keywordTotal === 0 ? null : (
          <div>
            <h4 className="text-sm font-semibold text-fg">Résumé keywords</h4>
            <p className="mb-1.5 text-xs text-fg-3">
              {classified.keywordsPresent.length.toLocaleString()} of {keywordTotal.toLocaleString()}{" "}
              keywords from the posting appear in your résumé
              {row.coverage === null ? "" : ` (${formatFraction(row.coverage)})`}. This counts
              words, not experience: it does not show you meet a requirement, and it is not a chance
              of being hired.
            </p>
            {classified.keywordsAbsent.length === 0 ? null : (
              <p className="text-sm text-fg-2">
                <span className="text-fg">Not in your résumé: </span>
                {classified.keywordsAbsent.map((item) => item.requirement).join(", ")}
              </p>
            )}
            {classified.keywordsPresent.length === 0 ? null : (
              <p className="mt-1 text-sm text-fg-2">
                <span className="text-fg">In your résumé: </span>
                {classified.keywordsPresent.map((item) => item.requirement).join(", ")}
              </p>
            )}
          </div>
        )}

        <div className="text-sm text-fg-2">
          <p>
            <span className="text-fg">Ranking score {formatScore(row.score)}</span> — it only orders
            the list and was recomputed just now, not as delivered. It is not a chance of being
            hired or proof you qualify.
            {row.why === null ? "" : ` ${row.why}`}
          </p>
          <p className="mt-1 text-xs text-fg-3">
            {row.delivered_run_id === null
              ? "Not delivered by a run."
              : `Delivered by run ${String(row.delivered_run_id)}.`}
            {` First seen ${formatTimestamp(row.first_seen)}.`}
            {detail.board_target === null ? "" : ` Board target ${detail.board_target}.`}
            {row.target_flag === true ? " A company you target." : ""}
          </p>
        </div>
      </div>
    </details>
  );
}

/** Where, and when when it is known: an imported application may carry no submission date. */
function twinWhere(twin: AppliedIdenticalJd): string {
  const where = twin.location ?? EM_DASH;
  return twin.applied_at == null ? where : `${where} · ${formatDateWithYear(twin.applied_at)}`;
}

/*
 * T125. Other postings at this company with a byte-identical job description, already applied to.
 * The first names where and when; `+N` says there are more, and a native disclosure holds every
 * one of them, so nothing is truncated without a way to read it.
 */
function AppliedIdenticalJdLine({ twins }: { twins: AppliedIdenticalJd[] }) {
  const [first] = twins;
  if (first === undefined) return null;
  const line = `Applied to an identical description: ${twinWhere(first)}`;
  if (twins.length === 1) return <p className="text-sm text-fg-2">{line}</p>;
  return (
    <details className="text-sm text-fg-2">
      <summary className="cursor-pointer">{`${line} +${String(twins.length - 1)}`}</summary>
      <ul className="mt-1 flex flex-col gap-0.5 pl-4 text-xs">
        {twins.map((twin) => (
          <li key={twin.posting_id}>{`${twinWhere(twin)} · ${twin.title}`}</li>
        ))}
      </ul>
    </details>
  );
}

/**
 * Postings the list folds under this one — same company, same title once formatting is ignored.
 * They may be one job in several places or separate openings, so each is named with its place and
 * board and each opens in this workspace: collapsing the list never discards an opening.
 */
function RelatedPostings({
  related,
  onOpen,
}: {
  related: QueueRow[];
  onOpen: (row: QueueRow) => void;
}) {
  if (related.length === 0) return null;
  return (
    <Section
      title={`Related postings (${String(related.length)})`}
      hint="Same company and title. They may be the same job in another place or a separate opening — each is its own posting, so check before treating them as one."
    >
      <ul className="flex flex-col gap-1.5">
        {related.map((row) => (
          <li key={row.posting_id}>
            <button
              type="button"
              onClick={() => {
                onOpen(row);
              }}
              className="flex min-h-11 w-full flex-wrap items-center justify-between gap-x-4 rounded-sm bg-surface-2 px-3 py-2 text-left text-sm transition-colors duration-150 ease-in-out hover:bg-surface-3"
            >
              <span className="text-fg">{row.location ?? "Location not listed"}</span>
              <span className="text-fg-3">
                {[row.remote_policy, row.provider].filter(Boolean).join(" · ")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Section>
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
  onApplyOpened,
  companyCount,
  onSelectCompany,
  related = [],
  onOpenRelated,
  position,
  onPrevious,
  onNext,
  banner,
}: {
  detail: QueueDetail | null;
  loading: boolean;
  error: string | null;
  answers: Answers | null;
  onClose: () => void;
  /** "Record application": the owner says they sent it. The ONLY thing that writes an application. */
  onApplied: () => void;
  onSkip: () => void;
  onReport: () => void;
  /** A `YYYY-MM-DD` date to pin, or `null` to clear the one this job carries. */
  onFollowUp: (date: string | null) => void;
  onToast: (message: string, tone: "info" | "error") => void;
  /**
   * Whether THIS server can open a file manager at all. `false` omits the button rather than
   * leaving a control that can only ever answer with an error toast. Defaults to `true`, because
   * a viewer older than `meta.reveal_supported` sends nothing and a hidden control that would
   * have worked is the worse of the two mistakes.
   */
  revealSupported?: boolean;
  /** The application link was followed, so the page can ask "did you apply?" on return. */
  onApplyOpened?: () => void;
  /** Apply-lane jobs listed at this company, with the action that selects them. Both omitted for
   *  a job outside the apply lane, which has no selection to add to. */
  companyCount?: number;
  onSelectCompany?: () => void;
  /** The postings the list folds under this one, and the way to open one. */
  related?: QueueRow[];
  onOpenRelated?: (row: QueueRow) => void;
  /** "3 of 120" and the way to the neighbours IN THE VISIBLE ORDER. All omitted when the job is
   *  not in a list the workspace can step through. */
  position?: string;
  onPrevious?: () => void;
  onNext?: () => void;
  /** Session status and acknowledgements, above the job. */
  banner?: ReactNode;
}) {
  const [shown, setShown] = useState(false);
  /* The description's fold. Short descriptions are never folded; this only matters for long ones. */
  const [jdExpanded, setJdExpanded] = useState(false);
  /* The evidence quote being shown in the description, and the mark that shows it. */
  const [highlight, setHighlight] = useState<string | null>(null);
  /* Bumped on every jump, so asking for the same quote twice scrolls to it twice. */
  const [jump, setJump] = useState(0);
  const mark = useRef<HTMLElement | null>(null);
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
   * Focus, but only where the workspace is a full-screen SHEET — below `lg` it is `fixed inset-0`
   * over everything, and a keyboard reader who opened it was left behind it with no way in. Above
   * `lg` it is a column beside the list, and stealing focus there would break the fast path the
   * list exists for: Enter to look, ↓ to carry on down the queue.
   *
   * The other half is in `QueuePage`, which inerts what the sheet covers at that same tier.
   *
   * SUBSCRIBED, not sampled: shrinking the window across the breakpoint with a job open turns the
   * column into a modal sheet, and focus has to follow on the transition.
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

  /*
   * Bring the shown span into view and give it focus, so a keyboard or screen-reader reader lands
   * on the words the rule read rather than being told they are highlighted somewhere below.
   * `?.` on `scrollIntoView` because jsdom has none.
   */
  useEffect(() => {
    if (highlight === null) return;
    mark.current?.scrollIntoView?.({ block: "center" });
    mark.current?.focus({ preventScroll: true });
  }, [highlight, jump]);

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
   * `2026-09-20` walked through `0002-09-20`, `0020-09-20` and `0202-09-20` first. Commit on blur
   * or Enter instead, which is where a field's value is settled. The PICKER still commits where it
   * lands: one click in the browser's calendar is one whole date and one intention. The two are
   * told apart by `typing`, which a `keydown` on the input sets.
   *
   * `null` is "no edit in progress", NOT the empty string: with no draft the field simply renders
   * the row, so a rolled-back write, an undo and the reconciled echo all show through on their
   * own. A string means the reader is mid-edit and the draft wins until it is committed.
   */
  const stored = detail?.row?.follow_up ?? "";
  const [draft, setDraft] = useState<string | null>(null);
  const shownFollowUp = draft ?? stored;
  const typing = useRef(false);
  const followUpBounds = followUpWindow();
  const commitFollowUp = (value: string) => {
    typing.current = false;
    setDraft(null);
    // An EMPTY value writes nothing and the field snaps back: clearing is the button beside it,
    // never an emptied input. A date input reports "" for any INCOMPLETE date.
    if (value === "" || value === stored) return;
    onFollowUp(value);
  };

  const row = detail?.row ?? null;
  const pdfPath = pathFromFileUri(row?.pdf_uri ?? null);
  const folder = parentDirectory(pdfPath);
  const fileName = pdfPath === null ? null : (pdfPath.split(/[/\\]/).pop() ?? pdfPath);
  const body = detail?.jd_body ?? null;
  const longBody = body !== null && body.length > SHORT_DESCRIPTION;

  const showQuote = (quote: string) => {
    setJdExpanded(true);
    setHighlight(quote);
    setJump((current) => current + 1);
  };

  // "More" menu: closed by Escape and by a press anywhere outside it.
  const more = useRef<HTMLDetailsElement | null>(null);
  useEffect(() => {
    const close = (event: Event) => {
      const menu = more.current;
      if (menu === null || !menu.open) return;
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof MouseEvent && event.target instanceof Node && menu.contains(event.target)) {
        return;
      }
      menu.open = false;
    };
    window.addEventListener("keydown", close);
    window.addEventListener("mousedown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("mousedown", close);
    };
  }, []);

  const locations = row === null ? [] : (row.locations ?? []);
  const where = locations.length > 0 ? locations.join(" · ") : (row?.location ?? null);
  const subline =
    row === null
      ? []
      : [
          row.remote_policy,
          row.posted_days === null
            ? null
            : row.posted_days === 0
              ? "Posted today"
              : `Posted ${String(row.posted_days)}d ago`,
          row.provider ?? null,
        ].filter((part): part is string => part !== null && part !== "");

  return (
    <aside
      id={PANE_ID}
      ref={pane}
      tabIndex={-1}
      /*
       * A modal ONLY below `lg`. There the workspace is `fixed inset-0` over a page `QueuePage` has
       * inerted — it blocks, so it says so. At or above `lg` it is a column beside a list that
       * stays fully operable, and a `dialog` role there would be a claim that is not true.
       *
       * Named by its own heading, which is the job's title. `aria-label` is kept for the two
       * states that render no heading — loading, and a job that failed to load.
       */
      role={sideBySide ? undefined : "dialog"}
      aria-modal={sideBySide ? undefined : true}
      aria-label={sideBySide || row === null ? "Job workspace" : undefined}
      aria-labelledby={!sideBySide && row !== null ? TITLE_ID : undefined}
      /*
       * A flex column: header, a scrolling middle, and the action bar. The bar is a SIBLING of the
       * scroller rather than `position: sticky` inside it, so it can never cover content, and a
       * control scrolled into view stops clear of it (`scroll-margin-bottom` in `index.css`).
       * `lg:top-header` and `lg:z-auto` stop it at the sticky app header without outranking it.
       */
      className={`fixed inset-0 z-40 flex flex-col bg-surface transition-[opacity,translate] duration-[180ms] ease-out lg:sticky lg:inset-auto lg:top-header lg:z-auto lg:h-[calc(100vh-var(--spacing-header))] lg:rounded-lg lg:shadow-card ${
        shown ? "translate-x-0 opacity-100" : "translate-x-2 opacity-0"
      }`}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-divider px-3 py-1.5">
        <button
          type="button"
          onClick={onClose}
          className={`${BUTTON} text-fg-2 hover:bg-surface-2 hover:text-fg lg:hidden`}
        >
          <Icon name="arrowLeft" />
          Back to list
        </button>
        <span className="hidden text-sm text-fg-3 lg:inline">Job workspace</span>
        <span className="flex items-center gap-1">
          {position === undefined ? null : (
            <span className="px-2 text-sm text-fg-3 tabular-nums" aria-live="polite">
              {position}
            </span>
          )}
          {onPrevious === undefined ? null : (
            <button
              type="button"
              onClick={onPrevious}
              aria-label="Previous job"
              title="Previous job in the list"
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-sm text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface-2 hover:text-fg"
            >
              <Icon name="chevronUp" size={18} />
            </button>
          )}
          {onNext === undefined ? null : (
            <button
              type="button"
              onClick={onNext}
              aria-label="Next job"
              title="Next job in the list"
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-sm text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface-2 hover:text-fg"
            >
              <Icon name="chevronDown" size={18} />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="hidden min-h-11 min-w-11 items-center justify-center rounded-sm text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface-2 hover:text-fg lg:inline-flex"
            aria-label="Close detail"
          >
            <Icon name="x" size={18} />
          </button>
        </span>
      </div>

      {loading || row === null || detail === null ? (
        <div className="flex-1 overflow-y-auto px-5 py-6">
          {error === null ? (
            <div role="status" aria-label="Loading the job" className="flex flex-col gap-3">
              <span className="skeleton h-7 w-3/4" />
              <span className="skeleton h-4 w-1/2" />
              <span className="skeleton mt-4 h-24 w-full" />
              <span className="skeleton h-24 w-full" />
            </div>
          ) : (
            <p role="alert" className="text-sm text-fg">
              {error}
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-[46rem] flex-col gap-7 px-5 py-5">
              {banner}

              <header>
                <h2 id={TITLE_ID} className="text-xl leading-snug text-fg">
                  {row.title}
                </h2>
                <p className="mt-0.5 text-base text-fg-2">{row.company}</p>
                {where === null ? (
                  <p className="mt-1 text-sm text-fg-3">Location not listed</p>
                ) : (
                  <p className="mt-1 text-sm text-fg-2">{where}</p>
                )}
                {subline.length === 0 ? null : (
                  <p className="mt-0.5 text-sm text-fg-3">{subline.join(" · ")}</p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {row.target_flag === true ? <Badge label="Company you target" /> : null}
                  {row.thin_jd ? <Badge label="Very short description" /> : null}
                </div>
                <div className="mt-2">
                  <AppliedIdenticalJdLine twins={row.applied_identical_jd ?? []} />
                </div>
              </header>

              <WhatToCheck detail={detail} onShow={showQuote} />

              <Section
                title="Prepared materials"
                hint="Everything you need to fill in the application, ready to copy. Nothing here is sent anywhere."
              >
                {pdfPath === null ? (
                  <div className="rounded-md bg-surface-2 p-4">
                    <StatusMark mark={materialsMark(false)} size="md" className="font-medium" />
                    <p className="mt-1 max-w-[62ch] pl-[1.375rem] text-sm text-fg-2">
                      No résumé file was built for this job, so there is nothing to upload from
                      here. You can still open the application and use your own résumé, or skip the
                      job.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-md bg-surface-2 p-4">
                    <p className="flex flex-wrap items-center gap-x-2 text-sm font-medium text-ok">
                      <Icon name="file" />
                      Résumé ready
                      {fileName === null ? null : (
                        <span className="font-mono text-xs font-normal break-all text-fg-3">
                          {fileName}
                        </span>
                      )}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <CopyButton
                        value={pdfPath}
                        label="Copy résumé path for upload"
                        variant="primary"
                        onError={(message) => {
                          onToast(message, "error");
                        }}
                        title={`Paste this straight into the employer's file-upload dialog: ${pdfPath}`}
                      />
                      <ActionButton
                        label="Preview résumé"
                        icon="file"
                        title="Opens the PDF in a new tab."
                        onClick={() => {
                          void openPdf(row.posting_id).catch((caught: unknown) => {
                            onToast(
                              caught instanceof Error ? caught.message : "Could not open the résumé.",
                              "error",
                            );
                          });
                        }}
                      />
                      {!revealSupported ? null : (
                        <ActionButton
                          label="Reveal folder"
                          icon="folder"
                          {...(folder === null ? {} : { title: `Show where the résumé is saved: ${folder}` })}
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
                    </div>
                    <p className="mt-2 text-xs text-fg-3">
                      The macOS and Windows file dialogs both accept a pasted path, so you can skip
                      browsing for the file.
                    </p>
                  </div>
                )}

                <AnswersPanel
                  answers={answers}
                  defaultOpen={false}
                  onError={(message) => {
                    onToast(message, "error");
                  }}
                />
              </Section>

              {/*
                * The follow-up, folded: it is the one control here that writes without removing
                * the job, and it is not part of preparing an application, so it sits where it is
                * found rather than competing with the materials above. The summary still says the
                * date when one is pinned, so a follow-up is never hidden by being folded.
                */}
              <details className="group rounded-md bg-surface-2" open={row.follow_up != null}>
                <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-md px-4 text-base font-semibold text-fg [&::-webkit-details-marker]:hidden">
                  <span>
                    Follow up later
                    {row.follow_up == null ? null : (
                      <span className="ml-2 text-sm font-normal text-fg-2">on {row.follow_up}</span>
                    )}
                  </span>
                  <Icon name="chevronDown" className="transition-transform group-open:rotate-180" />
                </summary>
                <div className="flex flex-wrap items-center gap-2 px-4 pt-1 pb-4">
                  <label htmlFor={FOLLOW_UP_INPUT_ID} className="text-sm text-fg-2">
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
                        // Enter settles the value without leaving the field.
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
                    title="Remove this job's follow-up date."
                    ariaLabel="Clear follow-up"
                    disabled={row.follow_up == null}
                    onClick={() => {
                      onFollowUp(null);
                    }}
                  />
                  <span role="group" aria-label="Follow up in" className="flex flex-wrap gap-1">
                    {(
                      [
                        ["In 3 days", 3],
                        ["In 1 week", 7],
                        ["In 2 weeks", 14],
                      ] as const
                    ).map(([label, days]) => (
                      <ActionButton
                        key={days}
                        label={label}
                        tone="filled"
                        title={`Follow up on ${isoDaysFromToday(days)}.`}
                        onClick={() => {
                          onFollowUp(isoDaysFromToday(days));
                        }}
                      />
                    ))}
                  </span>
                </div>
              </details>

              <RelatedPostings
                related={related}
                onOpen={(other) => {
                  onOpenRelated?.(other);
                }}
              />

              <Section title="Job description">
                {body === null ? (
                  <p className="rounded-md bg-surface-2 p-3 text-sm text-fg-2">
                    The posting’s description isn’t available, so nothing above was read from it.
                    Open the application to read it on the employer’s page.
                  </p>
                ) : (
                  <>
                    {/*
                      * Third-party text, rendered as plain text and never as markup. The frozen
                      * body carries NO newlines, so `whitespace-pre-wrap` has nothing to wrap and
                      * nothing here invents structure — the only honest fixes at render time are
                      * typographic: a 68ch measure and generous leading. A short description is
                      * shown whole, with no box to scroll; a long one is folded to a readable
                      * height (never an inner scrollbar) and opens in place.
                      */}
                    <div
                      id={DESCRIPTION_ID}
                      className={`relative ${longBody && !jdExpanded ? "max-h-[26rem] overflow-hidden" : ""}`}
                    >
                      <p className="max-w-[68ch] text-[0.9375rem] leading-[1.7] whitespace-pre-wrap text-fg-2">
                        {(() => {
                          const span = highlight === null ? null : locateQuote(body, highlight);
                          if (span === null) return body;
                          const [start, end] = span;
                          return (
                            <>
                              {body.slice(0, start)}
                              <mark
                                ref={mark}
                                tabIndex={-1}
                                className="rounded-sm bg-surface-3 text-fg shadow-[inset_0_-2px_0_0_var(--color-accent)]"
                              >
                                {body.slice(start, end)}
                              </mark>
                              {body.slice(end)}
                            </>
                          );
                        })()}
                      </p>
                      {longBody && !jdExpanded ? (
                        <span
                          aria-hidden="true"
                          className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-surface to-transparent"
                        />
                      ) : null}
                    </div>
                    {!longBody ? null : (
                      <button
                        type="button"
                        aria-expanded={jdExpanded}
                        onClick={() => {
                          setJdExpanded((current) => !current);
                        }}
                        className={`${BUTTON} self-start bg-surface-2 text-fg hover:bg-surface-3`}
                      >
                        {jdExpanded ? "Show less" : "Show the full description"}
                      </button>
                    )}
                  </>
                )}
              </Section>

              <WhyThisStatus detail={detail} onShow={showQuote} />
            </div>
          </div>

          <div
            role="group"
            aria-label="Application actions"
            className="shrink-0 border-t border-divider bg-surface px-4 py-3"
          >
            <div className="mx-auto flex max-w-[46rem] flex-wrap items-center gap-2">
              <ApplyLink
                url={row.apply_url}
                {...(onApplyOpened === undefined ? {} : { onOpen: onApplyOpened })}
              />
              <button
                type="button"
                onClick={onApplied}
                onKeyDown={(event) => {
                  // A held Enter repeats `click` on a focused button. Recording is a write, so a
                  // repeat must never reach it — see the lock in `QueuePage` for the other half.
                  if (event.repeat) event.preventDefault();
                }}
                title="Record that you submitted this application. Opening the page records nothing. Key on the list: a"
                className={`${BUTTON} bg-surface-3 text-fg hover:bg-surface-2`}
              >
                <Icon name="check" />
                Record application
              </button>
              <span className="mx-1 hidden h-6 w-px bg-divider sm:block" aria-hidden="true" />
              <ActionButton label="Skip" onClick={onSkip} title="Skip this job. Key on the list: s" />
              <details ref={more} className="relative">
                <summary
                  className={`${BUTTON} cursor-pointer list-none text-fg-2 hover:bg-surface-2 hover:text-fg [&::-webkit-details-marker]:hidden`}
                >
                  More
                  <Icon name="chevronUp" size={14} />
                </summary>
                <div className="absolute right-0 bottom-full z-10 mb-2 flex w-64 flex-col gap-1 rounded-md bg-surface p-2 shadow-card ring-1 ring-divider">
                  <ActionButton
                    label="Report a problem with this job"
                    onClick={() => {
                      if (more.current !== null) more.current.open = false;
                      onReport();
                    }}
                    title="Flag this job as wrongly marked eligible, for investigation. It is held out of the list until looked at. Key on the list: r"
                  />
                  {companyCount === undefined ||
                  companyCount < 2 ||
                  onSelectCompany === undefined ? null : (
                    <ActionButton
                      label={`Select all ${String(companyCount)} at ${row.company}`}
                      title="Add every listed job at this company to the selection, so the bulk bar can skip them in one write. Key on the list: c"
                      onClick={() => {
                        if (more.current !== null) more.current.open = false;
                        onSelectCompany();
                      }}
                    />
                  )}
                </div>
              </details>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
