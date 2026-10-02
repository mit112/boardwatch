import type { QueueDetail, QueueRow, RequirementView, ReviewReason, Verdict } from "../api/types";

/*
 * What a job's status MEANS to the person reading it, in the words of what they would do next.
 *
 * The server sends four independent facts about a posting, and this file keeps them independent:
 *
 *   requirements    the rules engine's verdict and the per-requirement evidence behind it
 *   review          the final gate's own read of the job description
 *   availability    whether the posting is still up, and whether anything can know
 *   materials       whether a résumé was built for it
 *
 * NOTHING HERE COMBINES THEM. There is no score, no "confidence", no overall grade: two engines
 * that disagree stay two readings, and a reading that was never taken stays "not assessed". The
 * only thing this module decides is which sentence to print — it never decides a verdict, and it
 * never reads a missing value as a passed check.
 *
 * Every function is a pure function of fields already on the wire. The word for each state lives
 * here and nowhere else, so a row, the detail pane and the status disclosure cannot drift into
 * three vocabularies for one fact.
 */

/** `ok` is only ever "a check came back clear". `quiet` is "nothing was said", never "all clear". */
export type Tone = "ok" | "warn" | "bad" | "quiet";

/** Words for a tone's glyph. A mark is never carried by colour alone (SC 1.4.1). */
export const TONE_GLYPH: Record<Tone, string> = { ok: "✓", warn: "?", bad: "✕", quiet: "–" };

export interface Mark {
  label: string;
  tone: Tone;
  /** This line already says that the rules and the independent review differ, with both readings,
   *  so a list row need not say it again. */
  coversDisagreement?: boolean;
}

/* ------------------------------------------------------------------------------------ reasons */

/**
 * Plain words for each review reason: `next` is the short line a list row carries, `detail` is the
 * sentence the detail pane gives. Exhaustive over the closed `ReviewReason` set, so a member added
 * server-side is a compile error here rather than a row that quietly says nothing.
 *
 * Each sentence says what we KNOW, never more. An abstain is worded as an abstain: "check", not
 * "failed". The two absences — nothing extracted, not evaluated — are worded as absences of ours.
 */
export const REASON_PLAIN: Record<ReviewReason, { next: string; detail: string }> = {
  eligibility_unconfirmed: {
    next: "Check work authorization or clearance",
    detail:
      "A work-authorization or clearance rule could not decide this either way. That is not a finding that you are ineligible — read what the posting says before spending time on it.",
  },
  experience_requirement: {
    next: "Check the experience requirement",
    detail:
      "The posting states an experience requirement that your profile does not confirm you meet. It may well be satisfied — the rules cannot tell — so read the line below.",
  },
  form_question_hard_stop: {
    next: "Application form has a hard-stop question",
    detail:
      "The employer's application form asks a citizenship or export-control question that the job description never mentions. Read the quoted question before you apply.",
  },
  ineligible_verdict: {
    next: "Rules found a blocker",
    detail: "The rules engine found a blocker. The quoted evidence shows what it read.",
  },
  judged_ineligible_verdict: {
    next: "Independent review found a blocker",
    detail:
      "An independent read of the job description found a blocker, while the rules engine did not. Read the quoted evidence and decide.",
  },
  no_requirements_found: {
    next: "No requirements extracted — read the posting",
    detail:
      "No requirements could be extracted from this description, so nothing was checked. That says nothing about the job itself — read the posting.",
  },
  non_us_location: {
    next: "Location is outside the US",
    detail: "The location check confirmed a location outside the US.",
  },
  provider_employment_type: {
    next: "May not be full-time",
    detail:
      "The job board's own employment-type field says this is not a full-time role, though the description says nothing that could be quoted. Check the posting.",
  },
  revised_since_build: {
    next: "Posting changed after your résumé was built",
    detail:
      "The employer revised this posting after the résumé was prepared for it. Read the current description and check the résumé still fits.",
  },
  role_gate_unmeasured: {
    next: "Role not checked — no role list set up",
    detail:
      "No role list is configured, so the role check could not read this title. That is not a judgement about the role.",
  },
  role_unconfirmed: {
    next: "Check that the role is software",
    detail:
      "The role check would not positively call this title software. That is an abstain, not a veto — the job may be exactly what you want.",
  },
  role_vetoed: {
    next: "Role check flagged the title",
    detail: "The role check flagged this title. The detail below says which words it matched.",
  },
  seniority_above_band: {
    next: "Title may be above your target level",
    detail: "The title reads as more senior than the level you are targeting.",
  },
  seniority_judged_above_band: {
    next: "Description reads senior",
    detail:
      "The title looks entry-level, but an independent read of the description describes a more senior role. Read it before applying.",
  },
  unevaluated: {
    next: "Not evaluated yet",
    detail:
      "Nothing has evaluated this job yet, so no requirement has been checked. A later run may fix that on its own.",
  },
};

/* ------------------------------------------------------------------------------- the four marks */

/** The rules engine's verdict as a mark. `eligible` is "a rule cleared what it read", not "every
 *  requirement is satisfied" — the wording keeps that distinction. */
export function requirementsMark(verdict: Verdict | null | undefined): Mark {
  switch (verdict) {
    case "eligible":
      return { label: "Rules found no blocker", tone: "ok" };
    case "uncertain":
      return { label: "Some requirements aren’t confirmed", tone: "warn" };
    case "ineligible":
      return { label: "Rules found a blocker", tone: "bad" };
    default:
      return { label: "Requirements not assessed yet", tone: "quiet" };
  }
}

/** The final gate's reading. `null` is the gate NOT having spoken — never the gate clearing it. */
export function reviewMark(verdict: Verdict | null | undefined): Mark {
  switch (verdict) {
    case "eligible":
      return { label: "Independent review found no blocker", tone: "ok" };
    case "uncertain":
      return { label: "Independent review is unsure", tone: "warn" };
    case "ineligible":
      return { label: "Independent review found a blocker", tone: "bad" };
    default:
      return { label: "No independent review yet", tone: "quiet" };
  }
}

/** Whether the posting is still up. `unverifiable` is a fact about what we can know, not about the
 *  employer: nothing scans that company's board, so "still open" was never measured. */
export function availabilityMark(status: QueueRow["status"] | null | undefined): Mark {
  switch (status) {
    case "open":
      return { label: "Listed as open", tone: "quiet" };
    case "closed":
      return { label: "Posting is closed", tone: "bad" };
    case "unverifiable":
      return { label: "Posting availability hasn’t been verified", tone: "warn" };
    default:
      return { label: "Availability unknown", tone: "quiet" };
  }
}

export function materialsMark(pdfAvailable: boolean | null | undefined): Mark {
  return pdfAvailable === true
    ? { label: "Résumé ready", tone: "ok" }
    : { label: "No résumé built for this job", tone: "warn" };
}

/**
 * The two engines disagree. Only a pair that BOTH spoke can disagree — a missing gate row is not a
 * disagreement, it is a reading nobody took. The case worth a person's attention is rules clear
 * and gate not, or the reverse; either way the pane shows both readings side by side.
 */
export function reviewsDiffer(row: Pick<QueueRow, "verdict" | "judge_verdict">): boolean {
  const rules = row.verdict;
  const gate = row.judge_verdict;
  if (rules == null || gate == null) return false;
  return rules !== gate;
}

/** Both readings in one line, when they differ: neither is dropped and neither is blended into the
 *  other. `null` when they agree or when either engine has not spoken. */
function disagreementMark(row: Pick<QueueRow, "verdict" | "judge_verdict">): Mark | null {
  if (!reviewsDiffer(row)) return null;
  const rules = requirementsMark(row.verdict).label;
  const gate = reviewMark(row.judge_verdict).label;
  return {
    label: `${rules}; ${gate.charAt(0).toLowerCase()}${gate.slice(1)}`,
    tone: row.verdict === "ineligible" || row.judge_verdict === "ineligible" ? "bad" : "warn",
    coversDisagreement: true,
  };
}

/* ----------------------------------------------------------------------------------- the list */

/**
 * The ONE line a list row carries about status: the thing most likely to change what the reader
 * does next, or `null` when nothing does. In priority order — a closed posting beats everything,
 * a named review reason beats a bare verdict, and so on. A row with no note is not "approved"; it
 * is a row with nothing to flag, and the detail pane still shows every reading.
 */
export function rowNote(row: QueueRow): Mark | null {
  if (row.status === "closed") return { label: "Posting is closed", tone: "bad" };
  if (row.review_reason != null && row.review_reason in REASON_PLAIN) {
    return {
      label: REASON_PLAIN[row.review_reason].next,
      tone:
        row.review_reason === "ineligible_verdict" ||
        row.review_reason === "judged_ineligible_verdict" ||
        row.review_reason === "role_vetoed" ||
        row.review_reason === "non_us_location"
          ? "bad"
          : "warn",
    };
  }
  /* The body-seniority reading on an apply-lane job, where nothing else carries it while the hold
     that would act on it is off. A recorded reading nobody can see is a monitoring failure. */
  if (row.judge_seniority_above_band === true) {
    return { label: REASON_PLAIN.seniority_judged_above_band.next, tone: "warn" };
  }
  const differ = disagreementMark(row);
  if (differ !== null) return differ;
  if (row.judge_verdict === "ineligible") return reviewMark("ineligible");
  if (row.judge_verdict === "uncertain") return reviewMark("uncertain");
  if (row.verdict === "uncertain") return requirementsMark("uncertain");
  if (row.status === "unverifiable") return availabilityMark("unverifiable");
  if (row.pdf_available !== true) return materialsMark(false);
  return null;
}

/* ------------------------------------------------------------------------------- requirements */

/*
 * Four states, never folded. The wire carries `covered: boolean`, which is `disposition === "met"`
 * and therefore reads `unknown` as NOT covered — and the pane used to list those under "Missing".
 * An unknown is not an unmet: it means the rule could not decide (the profile has no value, or the
 * text was ambiguous). The `disposition` is on the wire next to it and is what is read here.
 */
export type RequirementState = "satisfied" | "unmet" | "unconfirmed" | "not_assessed";

/**
 * An entry is ELIGIBILITY evidence when it carries a rule or a disposition. An entry with neither
 * is a résumé KEYWORD (`covered` = "appears in the master résumé"), which is a different question
 * with a different answer and must never be listed beside the requirements as if it were one.
 */
export function isEligibilityEntry(item: RequirementView): boolean {
  return item.rule !== null || item.disposition !== null;
}

export function requirementState(item: RequirementView): RequirementState {
  switch (item.disposition) {
    case "met":
      return "satisfied";
    case "unmet":
      return "unmet";
    case "unknown":
      return "unconfirmed";
    default:
      // No disposition on an eligibility entry: nothing was assessed. Deliberately NOT `covered`.
      return "not_assessed";
  }
}

export interface ClassifiedRequirements {
  satisfied: RequirementView[];
  unmet: RequirementView[];
  unconfirmed: RequirementView[];
  notAssessed: RequirementView[];
  /** Résumé keywords the posting uses that the master résumé contains. */
  keywordsPresent: RequirementView[];
  /** Résumé keywords the posting uses that the master résumé does not contain. */
  keywordsAbsent: RequirementView[];
}

export function classifyRequirements(items: readonly RequirementView[]): ClassifiedRequirements {
  const out: ClassifiedRequirements = {
    satisfied: [],
    unmet: [],
    unconfirmed: [],
    notAssessed: [],
    keywordsPresent: [],
    keywordsAbsent: [],
  };
  for (const item of items) {
    if (!isEligibilityEntry(item)) {
      (item.covered ? out.keywordsPresent : out.keywordsAbsent).push(item);
      continue;
    }
    const state = requirementState(item);
    if (state === "satisfied") out.satisfied.push(item);
    else if (state === "unmet") out.unmet.push(item);
    else if (state === "unconfirmed") out.unconfirmed.push(item);
    else out.notAssessed.push(item);
  }
  return out;
}

/* ---------------------------------------------------------------------------------- what to check */

export interface CheckItem {
  key: string;
  tone: Tone;
  /** The thing to check, in a sentence. */
  headline: string;
  /** What we know about it, or why it is flagged. */
  body?: string;
  /** A span quoted from the frozen posting, verbatim, when the evidence has one. */
  quote?: string | null;
}

/**
 * Everything on one job that could change the decision, in the order a person would want it:
 * confirmed blockers first, then what could not be confirmed, then the posting and the readings.
 * Material unresolved issues are NEVER dropped to make the list shorter — an empty result means
 * nothing was flagged, and the caller says exactly that and no more.
 */
export function whatToCheck(detail: QueueDetail): CheckItem[] {
  const { row } = detail;
  const items: CheckItem[] = [];
  const classified = classifyRequirements(detail.requirements);

  for (const item of classified.unmet) {
    items.push({
      key: `unmet:${item.rule ?? ""}:${item.requirement}`,
      tone: "bad",
      headline: `Not met: ${item.requirement}`,
      ...(item.rationale === null ? {} : { body: item.rationale }),
      quote: item.quote,
    });
  }

  if (row.status === "closed") {
    items.push({
      key: "closed",
      tone: "bad",
      headline: "The employer has taken this posting down",
      body: "It is no longer open on the board, so there is nothing to apply to.",
    });
  }

  if (row.review_reason != null && row.review_reason in REASON_PLAIN) {
    items.push({
      key: `reason:${row.review_reason}`,
      tone: rowNote(row)?.tone ?? "warn",
      headline: REASON_PLAIN[row.review_reason].next,
      body:
        row.review_reason === "role_vetoed" && row.off_target_reason != null
          ? `${REASON_PLAIN[row.review_reason].detail} ${row.off_target_reason}`
          : REASON_PLAIN[row.review_reason].detail,
      quote:
        row.review_reason === "form_question_hard_stop"
          ? (row.form_question ?? null)
          : row.review_reason === "provider_employment_type"
            ? (row.provider_employment_type ?? null)
            : null,
    });
  }

  if (row.judge_seniority_above_band === true && row.review_reason !== "seniority_judged_above_band") {
    items.push({
      key: "seniority-body",
      tone: "warn",
      headline: REASON_PLAIN.seniority_judged_above_band.next,
      body: `${REASON_PLAIN.seniority_judged_above_band.detail} The hold that would act on this is off, so the job is still in Jobs to explore.`,
    });
  }

  for (const item of classified.unconfirmed) {
    items.push({
      key: `unconfirmed:${item.rule ?? ""}:${item.requirement}`,
      tone: "warn",
      headline: `Check: ${item.requirement}`,
      body:
        item.rationale ??
        "The rules could not confirm this either way, so it is neither met nor unmet.",
      quote: item.quote,
    });
  }

  if (reviewsDiffer(row)) {
    items.push({
      key: "differ",
      tone: "warn",
      headline: "The rules and the independent review read this differently",
      body: `${requirementsMark(row.verdict).label}; ${reviewMark(row.judge_verdict).label.toLowerCase()}. Both readings are under “Why this status?”.`,
    });
  } else if (row.judge_verdict === "uncertain" && row.review_reason == null) {
    items.push({
      key: "judge-unsure",
      tone: "warn",
      headline: reviewMark("uncertain").label,
      body: "It read the description and could not decide. Read the description before applying.",
    });
  }

  if (row.status === "unverifiable") {
    items.push({
      key: "unverifiable",
      tone: "warn",
      headline: availabilityMark("unverifiable").label,
      body: "Nothing scans this company’s board, so there is no way to tell whether the posting is still open. Open the application to find out.",
    });
  }

  if (row.thin_jd) {
    items.push({
      key: "thin",
      tone: "warn",
      headline: "The description is very short",
      body: "Résumé keyword coverage could not be worked out from it. Read the posting itself.",
    });
  }

  return items;
}

/** One sentence for the empty "What to check" list. Says what was and was not assessed, never that
 *  the job is approved: a missing reading is named as missing. */
export function nothingFlaggedSentence(row: QueueRow, requirementsSeen: number): string {
  const gate =
    row.judge_verdict === "eligible"
      ? "and the independent review found no blocker"
      : row.judge_verdict == null
        ? "and there is no independent review yet"
        : "";
  if (row.verdict === "eligible" && requirementsSeen > 0) {
    return `Nothing flagged: the rules found no blocker ${gate}`.trim() + ".";
  }
  if (requirementsSeen === 0) {
    return "Nothing flagged — but no requirements were extracted from this posting, so nothing was actually checked. Read the description.";
  }
  return "Nothing flagged.";
}
