import type { Verdict } from "../api/types";

/*
 * The three verdicts are NOT a good-to-bad ramp, so they are not three steps of one colour.
 *
 *   eligible    filled, inverted — the brightest thing on the row
 *   ineligible  filled, and the label is struck through: the negation of the fill above, not a
 *               dimmer version of it
 *   uncertain   OUTLINED and unfilled — orthogonal to both. It means "not yet known", roughly half
 *               of these are real engineering roles the taxonomy did not recognise, and it is
 *               therefore never styled as a warning or an error.
 *
 * Every chip carries its word and a distinct glyph, so no meaning is carried by colour alone. The
 * verdict always arrives from the API verbatim; nothing here computes or infers one.
 */

const STYLES: Record<Verdict, { className: string; glyph: string; hint: string }> = {
  eligible: {
    className: "bg-fg text-bg font-medium",
    glyph: "●",
    hint: "Affirmatively eligible: a rule cleared every requirement it read.",
  },
  uncertain: {
    className: "border border-control text-fg-2",
    glyph: "○",
    hint: "Not yet known. A rule abstained; this is its own bucket, never folded into eligible.",
  },
  ineligible: {
    className: "bg-fg-3 text-bg line-through decoration-1",
    glyph: "✕",
    hint: "Ineligible, with a quoted span from the frozen job description.",
  },
};

export function VerdictChip({ verdict }: { verdict: Verdict | null }) {
  if (verdict === null) {
    return (
      <span
        className="inline-flex min-h-5 items-center gap-1.5 rounded-sm border border-dashed border-control px-2 py-0.5 text-xs text-fg-3"
        title="No eligibility verdict is recorded for this posting."
      >
        <span aria-hidden="true">{"–"}</span>
        no verdict
      </span>
    );
  }
  const style = STYLES[verdict];
  return (
    <span
      className={`inline-flex min-h-5 items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs ${style.className}`}
      title={style.hint}
    >
      <span aria-hidden="true" className="no-underline">
        {style.glyph}
      </span>
      {verdict}
    </span>
  );
}
