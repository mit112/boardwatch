import { useCallback, useEffect, useRef, useState } from "react";

/** Two routes. Hash-based, so the loopback server needs no SPA fallback and no dependency is
 * added for what is a switch between two pages. */
export type Route = "queue" | "runs";

/**
 * The queue's ADDRESSABLE state, carried as a query string on the hash:
 * `#/queue?run=5&lead=61310`. Both keys are optional and order-independent.
 *
 * These two are in the URL rather than in `sessionStorage` — where the filter text, the score
 * floor and the sorts live — because they are the two a reader sends to someone else or bookmarks:
 * "this lead" and "this run's leads". A filter box is a thing you are doing; a lead is a thing you
 * are pointing at.
 */
export interface RouteParams {
  /** Show only leads `delivered_run_id === run`. */
  run: number | null;
  /** The posting whose detail pane is open. */
  lead: number | null;
}

/** Ids only. A non-numeric, negative or fractional value is not an id, so it is dropped rather
 *  than passed on to become a filter that matches nothing with no way to see why. */
function readId(query: URLSearchParams, key: string): number | null {
  const raw = query.get(key);
  if (raw === null) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

function parse(): { route: Route; params: RouteParams } {
  const raw = window.location.hash.replace(/^#/, "");
  const separator = raw.indexOf("?");
  const path = separator === -1 ? raw : raw.slice(0, separator);
  const query = new URLSearchParams(separator === -1 ? "" : raw.slice(separator + 1));
  return {
    route: path === "/runs" ? "runs" : "queue",
    params: { run: readId(query, "run"), lead: readId(query, "lead") },
  };
}

/** `#/runs` stays bare — the params belong to the queue, and a runs URL carrying a queue's lead id
 *  would be a URL that means something different from what it shows. */
function href(route: Route, params: RouteParams): string {
  if (route === "runs") return "#/runs";
  const query = new URLSearchParams();
  if (params.run !== null) query.set("run", String(params.run));
  if (params.lead !== null) query.set("lead", String(params.lead));
  const search = query.toString();
  return search === "" ? "#/queue" : `#/queue?${search}`;
}

export function useHashRoute(): [
  Route,
  (next: Route) => void,
  RouteParams,
  (patch: Partial<RouteParams>) => void,
] {
  const [state, setState] = useState(parse);
  /*
   * Read by the two setters so they can stay identity-stable without taking `state` as a
   * dependency — and so neither of them writes `window.location.hash` from inside a `setState`
   * updater, which StrictMode calls twice.
   */
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  }, [state]);

  useEffect(() => {
    const onChange = () => {
      setState((current) => {
        const next = parse();
        /*
         * The queue's params are REMEMBERED across a visit to Runs, whose URL cannot carry them.
         * Without this, taking the Runs tab and coming straight back closed the open lead and
         * dropped the run filter — the "a tab switch discards all working state" complaint, for
         * the two pieces of state that do not live in `sessionStorage`.
         */
        return next.route === "runs" ? { route: next.route, params: current.params } : next;
      });
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);

  /*
   * State is set HERE as well as by the `hashchange` listener, deliberately: the browser fires
   * that event as a task, so a render that depended on it alone would lag one turn behind the
   * click that caused it. The listener re-parses to the same values and settles.
   */
  const setRoute = useCallback((next: Route) => {
    const { params } = latest.current;
    window.location.hash = href(next, params);
    setState({ route: next, params });
  }, []);

  /** Patches ONE key without clobbering the other: opening a lead must not drop the run filter. */
  const setParams = useCallback((patch: Partial<RouteParams>) => {
    const { route } = latest.current;
    const params = { ...latest.current.params, ...patch };
    window.location.hash = href(route, params);
    setState({ route, params });
  }, []);

  return [state.route, setRoute, state.params, setParams];
}
