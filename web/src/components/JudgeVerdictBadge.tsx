import type { Verdict } from "../api/types";
import { Badge } from "./Badge";

/*
 * WHAT THE FINAL GATE SAID, as distinct from what the rules engine said.
 *
 * `VerdictChip` beside this one renders `row.verdict` — the deterministic engine's roll-up. This
 * renders `row.judge_verdict`, an independent read of the job description, and the two legitimately
 * disagree: on the measured apply lane 42 of 390 judged leads read `uncertain` here on rows the
 * rules engine had cleared, and nothing on the page said so. That is the monitoring failure this
 * exists to close, not decoration.
 *
 * So every label here is PREFIXED with the engine that said it. The word is `gate`, which is the
 * app's own name for this engine everywhere else it is visible — the runs page labels the same
 * readout `final gate` and its copy calls the thing behind it "a judge" — and without the prefix a
 * bare `uncertain` chip beside a bare `uncertain` chip is two chips and no way to tell which
 * engine produced either. The word, not the weight, is what distinguishes them: colour and
 * emphasis carry nothing here that the text does not already say (SC 1.4.1).
 *
 * `Badge` rather than a second `VerdictChip`: the chip's three treatments are a closed statement
 * about the LANE decision, and reusing them would say this verdict has the same standing. It does
 * not — `classify` reads only `judge_verdict == "eligible"`, and a gate `uncertain` does not move
 * a lead. A `Badge` is the app's marker for "a reading worth seeing that did not decide the lane",
 * which is exactly what every other member of `Flags` is.
 *
 * Keyed on the server's closed `Verdict` set, exactly as `VerdictChip` and `ReviewReasonBadge`
 * are: the wire carries the code, this file carries the words, so a member added server-side is a
 * compile error here rather than a row that renders bare.
 */
const WORDS: Record<Verdict, { label: string; reason: string }> = {
  eligible: {
    label: "gate eligible",
    reason:
      "The final gate read the job description independently and cleared it. This is a second opinion beside the rules verdict, not the same one twice.",
  },
  uncertain: {
    label: "gate uncertain",
    reason:
      "The final gate read the job description independently and could not decide. Its own bucket, never folded into eligible — the rules verdict beside it may well say eligible, and this is the disagreement worth reading the JD over.",
  },
  ineligible: {
    label: "gate ineligible",
    reason:
      "The final gate read the job description independently and found the lead ineligible, quoting a span from the frozen description. The rules engine did not agree, or this lead would not be listed here at all.",
  },
};

/**
 * Renders NOTHING when the gate has not spoken, and that is the honest render rather than a
 * fallback: `null` means no gate row exists for this lead, which says nothing about the lead. An
 * "unjudged" chip here would appear on every row of a queue served by a viewer whose API predates
 * the field — 392 chips carrying no information.
 *
 * The guard is `== null`, deliberately loose, for the reason `ReviewReasonBadge`'s is: an older
 * server omits the field entirely, so it arrives as `undefined`, and `WORDS[undefined].label`
 * is the exact throw that blanked the whole page (D-360). `=== null` waves it straight through.
 */
export function JudgeVerdictBadge({
  verdict,
  showReason = false,
}: {
  verdict: Verdict | null | undefined;
  showReason?: boolean;
}) {
  if (verdict == null) return null;
  const words = WORDS[verdict];
  return <Badge label={words.label} reason={words.reason} showReason={showReason} />;
}
