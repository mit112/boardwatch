import { useEffect, useState } from "react";
import type { Toast } from "../hooks/useToasts";

/*
 * The undo lives on the toast and is available for exactly as long as the toast is. A mark-applied
 * or a skip is otherwise unrecoverable from the page, and a mis-click on a 540-row list is not a
 * hypothetical.
 */
function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setShown(true);
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const border = toast.tone === "error" ? "border-fg-2" : "border-control";

  return (
    <div
      className={`flex items-center gap-4 rounded border ${border} bg-surface-2 px-4 py-3 shadow-lg transition-[opacity,translate] duration-[180ms] ease-out ${
        shown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      }`}
    >
      <span className="text-sm text-fg">
        {toast.tone === "error" ? <span className="mr-2 text-fg-2">failed</span> : null}
        {toast.message}
      </span>
      <div className="ml-auto flex items-center gap-2">
        {toast.undo ? (
          <button
            type="button"
            className="min-h-11 rounded border border-fg-2 px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface"
            onClick={() => {
              toast.undo?.();
              onDismiss(toast.id);
            }}
          >
            {toast.undoLabel ?? "Undo"}
          </button>
        ) : null}
        <button
          type="button"
          className="min-h-11 min-w-11 rounded text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg"
          onClick={() => {
            onDismiss(toast.id);
          }}
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export function Toaster({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4"
      role="status"
      aria-live="polite"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto w-full max-w-xl">
          <ToastItem toast={toast} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  );
}
