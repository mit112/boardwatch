import { useCallback, useRef, useState } from "react";

export interface Toast {
  id: number;
  message: string;
  tone: "info" | "error";
  /** Present only while the undo is genuinely available — the toast IS the undo window. */
  undo?: () => void;
  undoLabel?: string;
}

export interface ToastRequest {
  message: string;
  tone?: "info" | "error";
  undo?: () => void;
  undoLabel?: string;
  ttlMs?: number;
}

const DEFAULT_TTL_MS = 7000;

let nextId = 1;

export function useToasts(): {
  toasts: Toast[];
  push: (request: ToastRequest) => void;
  dismiss: (id: number) => void;
  hold: (id: number) => void;
  release: (id: number) => void;
} {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef(new Map<number, number>());
  const ttls = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
    ttls.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const arm = useCallback(
    (id: number, ttlMs: number) => {
      const existing = timers.current.get(id);
      if (existing !== undefined) window.clearTimeout(existing);
      timers.current.set(
        id,
        window.setTimeout(() => {
          dismiss(id);
        }, ttlMs),
      );
    },
    [dismiss],
  );

  /*
   * WCAG 2.2 SC 2.2.1 Timing Adjustable. The toast IS the undo window, and it is the only way back
   * from a mark-applied or a skip — so a countdown the reader cannot stop is a time limit on
   * recovering from a mistake. Pointing at the toast, or tabbing into it, stops the clock; leaving
   * it starts a fresh full-length one rather than resuming a nearly-expired remainder.
   */
  const hold = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer === undefined) return;
    window.clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  const release = useCallback(
    (id: number) => {
      const ttl = ttls.current.get(id);
      if (ttl === undefined) return;
      arm(id, ttl);
    },
    [arm],
  );

  const push = useCallback(
    (request: ToastRequest) => {
      const id = nextId;
      nextId += 1;
      const toast: Toast = {
        id,
        message: request.message,
        tone: request.tone ?? "info",
        ...(request.undo === undefined ? {} : { undo: request.undo }),
        ...(request.undoLabel === undefined ? {} : { undoLabel: request.undoLabel }),
      };
      setToasts((current) => [...current, toast]);
      const ttl = request.ttlMs ?? DEFAULT_TTL_MS;
      ttls.current.set(id, ttl);
      arm(id, ttl);
    },
    [arm],
  );

  return { toasts, push, dismiss, hold, release };
}
