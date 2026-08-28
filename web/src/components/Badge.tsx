/*
 * A small outlined label. `reason` is never optional decoration: where a badge represents a veto,
 * the reason carries the text the shipped gate actually matched, so the veto is auditable rather
 * than mysterious. The row shows it as a tooltip; the detail pane shows it as visible text.
 */
export function Badge({
  label,
  reason,
  showReason = false,
  emphasis = "normal",
}: {
  label: string;
  reason?: string | null;
  showReason?: boolean;
  emphasis?: "normal" | "strong";
}) {
  const tone =
    emphasis === "strong"
      ? "border-fg-2 text-fg"
      : "border-control text-fg-2";
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span
        className={`inline-flex min-h-5 items-center rounded-sm border px-1.5 py-0.5 label-micro ${tone}`}
        {...(reason ? { title: reason } : {})}
      >
        {label}
      </span>
      {showReason && reason ? (
        <span className="text-xs text-fg-2">{reason}</span>
      ) : null}
    </span>
  );
}
