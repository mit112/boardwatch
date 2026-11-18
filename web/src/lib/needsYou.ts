import type { Companion, QueueResponse, ReviewReason } from "../api/types";
import { REASON_PLAIN } from "./jobStatus";
import { REVIEW_REASON_LABELS } from "./reviewReasons";

/*
 * T300: one list of what only the owner can settle. Read-only: each row says what to do, and the
 * settling still happens where it does today.
 *
 *   - held leads (the review lane), grouped by hold reason;
 *   - apply-lane leads the rules left `uncertain`;
 *   - companion items marked `needs_owner` (T294).
 */

export interface NeedsLead {
  postingId: number;
  title: string;
  company: string;
}

export interface NeedsGroup {
  key: string;
  heading: string;
  todo: string;
  leads: NeedsLead[];
  /** Companion items carry their own label, reason and link instead of a lead. */
  items: { label: string; reason: string | null; link: string | null }[];
}

const lead = (r: { posting_id: number; title: string; company: string }): NeedsLead => ({
  postingId: r.posting_id,
  title: r.title,
  company: r.company,
});

export function needsYou(queue: QueueResponse | null, companions: Companion[]): NeedsGroup[] {
  const groups: NeedsGroup[] = [];
  if (queue !== null) {
    const byReason = new Map<ReviewReason, NeedsLead[]>();
    const unreasoned: NeedsLead[] = [];
    for (const row of queue.review) {
      const reason = row.review_reason;
      if (reason != null && reason in REASON_PLAIN) {
        byReason.set(reason, [...(byReason.get(reason) ?? []), lead(row)]);
      } else {
        // Never dropped: a held lead with no catalogued reason is still the owner's to settle.
        unreasoned.push(lead(row));
      }
    }
    for (const [reason, leads] of [...byReason].sort((a, b) => b[1].length - a[1].length)) {
      groups.push({
        key: `held:${reason}`,
        heading: `Held: ${REVIEW_REASON_LABELS[reason]}`,
        todo: REASON_PLAIN[reason].next,
        leads,
        items: [],
      });
    }
    if (unreasoned.length > 0) {
      groups.push({
        key: "held:other",
        heading: "Held: no reason given",
        todo: "Open the lead and decide to apply or skip",
        leads: unreasoned,
        items: [],
      });
    }
    const uncertain = queue.rows.filter((r) => r.verdict === "uncertain").map(lead);
    if (uncertain.length > 0) {
      groups.push({
        key: "uncertain",
        heading: "Rules could not decide",
        todo: "Read the job description and confirm you qualify before applying",
        leads: uncertain,
        items: [],
      });
    }
  }
  for (const c of companions) {
    const items = c.items
      .filter((i) => i.needs_owner === true)
      .map((i) => ({ label: i.label, reason: i.reason ?? null, link: i.link ?? null }));
    if (items.length > 0) {
      groups.push({
        key: `companion:${c.name}`,
        heading: `From ${c.name}`,
        todo: "Settle each item in the tool that reported it",
        leads: [],
        items,
      });
    }
  }
  return groups;
}

export function needsCount(groups: NeedsGroup[]): number {
  return groups.reduce((n, g) => n + g.leads.length + g.items.length, 0);
}
