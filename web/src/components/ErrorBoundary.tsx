import { Component, createRef } from "react";
import type { ErrorInfo, ReactNode } from "react";

/*
 * The containment this application had none of. A single component that throws while rendering
 * unmounts the whole React tree and leaves an EMPTY `<body>` — which is exactly how a queue page
 * went blank on one undefined field (D-360). The field itself is guarded now; this is the
 * structural half, so the next one costs a card instead of the page.
 *
 * WHAT IT CATCHES, and the limit matters: errors thrown during RENDER, in a lifecycle, or in a
 * constructor, below this point in the tree. It does NOT catch errors in event handlers, in
 * `setTimeout`, or in a rejected promise — React never sees those, so they stay the caller's job.
 * The queue's fetches already carry their own `.catch`, and this does not replace them.
 *
 * A class, because a boundary is one of the two things React still has no hook for. That is the
 * platform feature rather than a preference, and it is why no dependency was added for it: the
 * viewer's only runtime deps are `react` and `react-dom` and this does not change that.
 */

const NO_KEYS: readonly unknown[] = [];

function keysChanged(before: readonly unknown[], after: readonly unknown[]): boolean {
  if (before.length !== after.length) return true;
  return before.some((value, index) => !Object.is(value, after[index]));
}

type Props = {
  /** One line, in the reader's terms, naming WHAT failed — never a bare "something went wrong". */
  title: string;
  /** One line saying what still works and what to do. This is what stops it being a dead end. */
  hint: string;
  /** The recovery button's label. Names the action at THIS site; never a generic "Try again". */
  action: string;
  /**
   * What the recovery button DOES. Defaults to re-rendering the children, which is the right
   * recovery almost everywhere. Override it where a redraw is not — the detail pane passes its
   * `onClose`, because a failed pane leaves the lead selected, and a selected lead is what holds
   * the queue behind it `inert` at the narrow tier; redrawing would leave the reader looking at a
   * card with a frozen list behind it and no way to unfreeze it.
   *
   * An override REPLACES the reset, so it must either move a `resetKeys` value or unmount this
   * boundary outright. Otherwise the error state it leaves behind is the one nothing clears.
   */
  onAction?: () => void;
  /**
   * Clearing the error when the reader navigates away from whatever broke. Without it a boundary
   * that has caught once keeps showing its card forever — switch route, pick another lead, and
   * the fallback follows you, because nothing else ever resets the state.
   */
  resetKeys?: readonly unknown[];
  children: ReactNode;
};

type State = {
  error: Error | null;
  keys: readonly unknown[];
};

export class ErrorBoundary extends Component<Props, State> {
  private readonly retry = createRef<HTMLButtonElement>();
  private readonly card = createRef<HTMLDivElement>();

  override state: State = { error: null, keys: NO_KEYS };

  static getDerivedStateFromError(error: Error): Pick<State, "error"> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): State | null {
    const keys = props.resetKeys ?? NO_KEYS;
    // Runs before every render, including the one that follows `getDerivedStateFromError` — where
    // the keys have NOT moved, so returning null there preserves the error just caught.
    if (!keysChanged(state.keys, keys)) return null;
    return { error: null, keys };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    /*
     * The component stack is the only thing that says WHICH component threw, and it exists
     * nowhere else. Kept in the shipped bundle on purpose: this viewer serves its JS from disk
     * while running the Python it imported at startup (D-360), so version skew is structural and
     * the operator debugging it is the same person reading the page.
     */
    console.error("[boardwatch] render failed:", this.props.title, error, info.componentStack);
  }

  override componentDidUpdate(_prevProps: Props, prevState: State): void {
    if (prevState.error !== null || this.state.error === null) return;
    /*
     * Focus is restored ONLY when the crash destroyed the element that had it — React unmounts the
     * failed subtree, and focus then falls to `<body>`, stranding a keyboard reader at the top of
     * the document. Moving it in any other case would hijack a reader who is somewhere else on the
     * page entirely; a boundary further down the tree can fire without touching their focus at all.
     * `role="alert"` below is what tells them regardless, so the announcement never depends on this.
     */
    const active = document.activeElement;
    if (active === null || active === document.body) {
      this.retry.current?.focus();
      return;
    }
    /*
     * Focus survived, so it cannot be relied on to carry the reader here — and focus surviving is
     * NOT the same as this card being visible. The crash can leave focus in a live region outside
     * this subtree (the toaster is deliberately not inerted), and below `lg` this card renders as
     * the second row of a single-column grid, i.e. BELOW the whole queue table, while a still-set
     * `selected` keeps that table `inert`. That combination is a page that ignores every click
     * with no visible reason. Scrolling costs nothing when the card is already on screen, and
     * `block: "nearest"` means no jump in that case. No smooth behaviour: nothing here should
     * animate under `prefers-reduced-motion`.
     */
    this.card.current?.scrollIntoView({ block: "nearest" });
  }

  private readonly reset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (error === null) return this.props.children;

    /*
     * Same card as the queue's own load failure — `border-fg-2` on `surface`, no red, because the
     * palette has no danger token and meaning is carried by the words. Two lines then one action:
     * what failed, what still works, what to press.
     */
    return (
      <div ref={this.card} role="alert" className="rounded-md border border-fg-2 bg-surface p-4">
        <p className="text-sm text-fg">{this.props.title}</p>
        <p className="mt-1 text-sm text-fg-2">{this.props.hint}</p>
        <button
          ref={this.retry}
          type="button"
          onClick={this.props.onAction ?? this.reset}
          className="mt-3 min-h-11 rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg"
        >
          {this.props.action}
        </button>
        {/*
          * Folded, not hidden. The reader here is the operator, and the message is the only
          * specific thing on the card — without it "the pane could not be drawn" sends them to
          * devtools to learn anything at all. Collapsed so it never outweighs the recovery action.
          */}
        <details className="mt-3">
          <summary className="min-h-11 cursor-pointer content-center text-sm text-fg-3">
            Technical detail
          </summary>
          <pre className="mt-1 overflow-x-auto text-xs whitespace-pre-wrap text-fg-3">
            {error.message}
          </pre>
        </details>
      </div>
    );
  }
}
