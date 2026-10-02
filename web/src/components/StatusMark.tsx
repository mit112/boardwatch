import type { Mark, Tone } from "../lib/jobStatus";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

/*
 * One reading, as an icon and a sentence. The tone is carried by the ICON'S SHAPE and the WORDS as
 * well as the colour (SC 1.4.1): a tick, a question mark, a cross and a dash read the same in
 * grayscale, and the sentence says the same thing a third time for a screen reader.
 *
 * Plain text rather than an outlined badge on purpose. A row used to carry up to six bordered
 * chips, which turned a list the reader scans into a list of boxes; one sentence per row is what
 * the next decision needs.
 */
const ICONS: Record<Tone, IconName> = { ok: "check", warn: "question", bad: "x", quiet: "dash" };
const COLORS: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
  quiet: "text-fg-3",
};

export function StatusMark({
  mark,
  size = "sm",
  className = "",
}: {
  mark: Mark;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-start gap-1.5 ${size === "md" ? "text-sm" : "text-[0.8125rem]"} leading-snug ${COLORS[mark.tone]} ${className}`}
    >
      <Icon name={ICONS[mark.tone]} size={size === "md" ? 16 : 14} className="mt-[0.2em]" />
      <span>{mark.label}</span>
    </span>
  );
}
