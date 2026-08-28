import { useCallback, useSyncExternalStore } from "react";

/**
 * A media query as RENDERED state. The detail pane is a full-screen modal sheet below `lg` and a
 * column beside the list at or above it, and the two tiers need opposite keyboard behaviour — so
 * the breakpoint has to be a value the markup reads on every render, not something an effect
 * samples once on mount. Subscribed rather than sampled, because a window can be resized across
 * the breakpoint while the pane is open.
 *
 * `useSyncExternalStore` and not `useState` + an effect: `matchMedia` IS an external store, and
 * reading it in an effect leaves a window between the first paint and the subscription in which
 * the answer can already be stale.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => {
        list.removeEventListener("change", onChange);
      };
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches);
}
