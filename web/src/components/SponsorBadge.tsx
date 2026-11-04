import type { SponsorSeen } from "../api/types";
import { Badge } from "./Badge";

/*
 * "H-1B filer": this employer has been seen filing H-1B applications for computing roles in the
 * public DOL disclosure files. It is evidence that they filed. It is not a promise of sponsorship,
 * and the tooltip says so in the words the owner chose.
 *
 * An absent record renders NOTHING: no "unknown", no empty space. No record is not evidence that an
 * employer does not sponsor (a new company, a renamed one and one outside the files look alike),
 * so there is no negative form of this badge at all.
 *
 * The tooltip text is reachable three ways, because `title` alone is mouse-only. A pointer reads
 * it from `title`. A screen reader reads it from the visually hidden sentence beside the label
 * (the job row is the keyboard stop, and its contents are read when it takes focus). A sighted
 * keyboard user opens the job, where the workspace passes `showReason` and prints it as text.
 */
export function sponsorSentence(seen: SponsorSeen): string {
  const rows = seen.computing_rows;
  const filed = `Seen filing H-1B applications for ${String(rows)} computing ${rows === 1 ? "role" : "roles"}`;
  const low = `${String(seen.computing_low_wage_rows)} at wage level I or II`;
  const latest = seen.latest_decision === null ? "" : `, latest decision ${seen.latest_decision}`;
  return `${filed}, ${low}${latest}, from public DOL filings; not a promise of sponsorship.`;
}

export function SponsorBadge({
  seen,
  showReason = false,
}: {
  seen: SponsorSeen | null | undefined;
  showReason?: boolean;
}) {
  if (seen == null) return null;
  const sentence = sponsorSentence(seen);
  return (
    <>
      <Badge label="H-1B filer" reason={sentence} showReason={showReason} />
      {showReason ? null : <span className="sr-only">{`. ${sentence}`}</span>}
    </>
  );
}
