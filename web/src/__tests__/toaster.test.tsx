import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Toaster } from "../components/Toaster";
import type { Toast } from "../hooks/useToasts";

/*
 * Using a toast's own button removes the button that holds focus. The browser then leaves focus on
 * `<body>`, which strands a keyboard reader at the top of the document. The Toaster puts it on the
 * page's main region instead, and leaves alone focus that was moved somewhere real.
 */

function Harness({ undo }: { undo: () => void }) {
  const [toasts, setToasts] = useState<Toast[]>([
    { id: 1, message: "Skipped Acme — Engineer", tone: "info", undo },
  ]);
  return (
    <>
      <input aria-label="Elsewhere" />
      <main id="view" tabIndex={-1}>
        main content
      </main>
      <Toaster
        toasts={toasts}
        onDismiss={(id) => {
          setToasts((current) => current.filter((toast) => toast.id !== id));
        }}
        onHold={() => undefined}
        onRelease={() => undefined}
      />
    </>
  );
}

describe("focus after a toast's own button is used", () => {
  it("lands on the main region after Undo, not on the body", () => {
    const undo = vi.fn();
    render(<Harness undo={undo} />);
    const button = screen.getByRole("button", { name: "Undo" });
    button.focus();
    fireEvent.click(button);

    expect(undo).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    expect(document.activeElement).toBe(document.getElementById("view"));
  });

  it("lands on the main region after Dismiss too", () => {
    render(<Harness undo={vi.fn()} />);
    const dismiss = screen.getByRole("button", { name: "Dismiss" });
    dismiss.focus();
    fireEvent.click(dismiss);
    expect(document.activeElement).toBe(document.getElementById("view"));
  });

  it("leaves focus alone when an Undo moved it somewhere real", () => {
    render(<Harness undo={() => { screen.getByLabelText("Elsewhere").focus(); }} />);
    const button = screen.getByRole("button", { name: "Undo" });
    button.focus();
    fireEvent.click(button);
    expect(document.activeElement).toBe(screen.getByLabelText("Elsewhere"));
  });
});
