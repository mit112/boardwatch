import { useEffect, useRef, useState } from "react";
import type { Toast } from "../hooks/useToasts";

/*
 * The undo lives on the toast and is available for exactly as long as the toast is. A mark-applied
 * or a skip is otherwise unrecoverable from the page, and a mis-click on a 540-row list is not a
 * hypothetical.
 */
function ToastItem({
  toast,
  onDismiss,
  onHold,
  onRelease,
}: {
  toast: Toast;
  onDismiss: (id: number) => void;
  onHold: (id: number) => void;
  onRelease: (id: number) => void;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setShown(true);
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, []);

  // Refs, not state: nothing renders from them, and a re-render between a hover and a focus
  // would drop the other hold on the floor.
  const pointer = useRef(false);
  const keyboard = useRef(false);

  const border = toast.tone === "error" ? "border-fg-2" : "border-control";

  return (
    <div
      /*
       * Pointer and keyboard are two INDEPENDENT holds and releasing one must not release the
       * other. Hovering a toast, tabbing to its Undo, then moving the mouse away fired
       * `onMouseLeave` -> `release`, which rearmed the full timer while focus was still sitting
       * on Undo — so the toast expired out from under the focused control, which is the exact
       * SC 2.2.1 failure the hold was added to fix. Held while EITHER is engaged; released only
       * when both are gone.
       */
      onMouseEnter={() => {
        pointer.current = true;
        onHold(toast.id);
      }}
      onMouseLeave={() => {
        pointer.current = false;
        if (!keyboard.current) onRelease(toast.id);
      }}
      onFocusCapture={() => {
        keyboard.current = true;
        onHold(toast.id);
      }}
      onBlurCapture={() => {
        keyboard.current = false;
        if (!pointer.current) onRelease(toast.id);
      }}
      className={`flex items-center gap-4 rounded-md border ${border} bg-surface-2 px-4 py-3 shadow-lg transition-[opacity,translate] duration-[180ms] ease-out ${
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
            className="min-h-11 rounded-sm border border-fg-2 px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface"
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
          className="min-h-11 min-w-11 rounded-sm text-fg-2 transition-colors duration-150 ease-in-out hover:text-fg"
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
  onHold,
  onRelease,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
  onHold: (id: number) => void;
  onRelease: (id: number) => void;
}) {
  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4"
      role="status"
      aria-live="polite"
      /*
       * `role="status"` is implicitly `aria-atomic="true"`, so inserting a second toast while the
       * first is still up re-announces the WHOLE region — the earlier message and its controls
       * again. On keyboard triage, where two marks inside the seven-second TTL is normal, that
       * compounds. `false` announces only what was added.
       */
      aria-atomic="false"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto w-full max-w-xl">
          <ToastItem
            toast={toast}
            onDismiss={onDismiss}
            onHold={onHold}
            onRelease={onRelease}
          />
        </div>
      ))}
    </div>
  );
}
