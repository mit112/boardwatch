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
} {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

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
      timers.current.set(
        id,
        window.setTimeout(() => {
          dismiss(id);
        }, request.ttlMs ?? DEFAULT_TTL_MS),
      );
    },
    [dismiss],
  );

  return { toasts, push, dismiss };
}
