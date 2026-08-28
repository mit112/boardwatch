import { useEffect, useRef, useState } from "react";

/*
 * The label swaps to "Copied" for 1.2 seconds. No bounce, no keyframes — a CSS colour transition
 * only, so clicking it repeatedly cannot stutter.
 */
export function CopyButton({
  value,
  label,
  onError,
  variant = "quiet",
  title,
}: {
  value: string;
  label: string;
  onError?: (message: string) => void;
  variant?: "quiet" | "primary";
  title?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(
    () => () => {
      if (timer.current !== undefined) window.clearTimeout(timer.current);
    },
    [],
  );

  const onClick = () => {
    void (async () => {
      try {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        if (timer.current !== undefined) window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => {
          setCopied(false);
        }, 1200);
      } catch {
        onError?.("Clipboard is unavailable in this browser context.");
      }
    })();
  };

  const base =
    "inline-flex min-h-11 items-center justify-center rounded-sm border px-3 text-sm transition-colors duration-150 ease-in-out";
  const skin =
    variant === "primary"
      ? "border-fg-2 bg-surface-2 text-fg hover:border-fg hover:bg-surface"
      : "border-control text-fg-2 hover:border-fg-2 hover:text-fg";

  return (
    <button type="button" className={`${base} ${skin}`} onClick={onClick} title={title ?? value}>
      <span aria-live="polite">{copied ? "Copied" : label}</span>
    </button>
  );
}
