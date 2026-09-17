import { isFollowUpDue } from "../lib/format";
import { Badge } from "./Badge";

/*
 * The pinned follow-up, and whether it has arrived.
 *
 * DUE is carried by the WORD "due" in the label and by the strong treatment — two channels, never
 * colour alone (SC 1.4.1), so the state survives grayscale and a glance. `== null` because an
 * older server omits the field entirely, and the honest render for "the server cannot say" is no
 * chip at all.
 *
 * ONE component for the queue row and the applied history, because the two surfaces answer the
 * same question about the same stored date: a second spelling of "follow-up due <date>" is how one
 * of them starts saying something different from the other.
 */
export function FollowUpBadge({ followUp }: { followUp: string | null | undefined }) {
  if (followUp == null) return null;
  const due = isFollowUpDue(followUp);
  return (
    <Badge
      label={`follow-up ${due ? "due " : ""}${followUp}`}
      emphasis={due ? "strong" : "normal"}
      reason={
        due
          ? `Pinned to look at again on ${followUp} — that date has arrived.`
          : `Pinned to look at again on ${followUp}.`
      }
    />
  );
}
