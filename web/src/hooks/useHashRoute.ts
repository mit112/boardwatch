import { useEffect, useState } from "react";

/** Two routes. Hash-based, so the loopback server needs no SPA fallback and no dependency is
 * added for what is a switch between two pages. */
export type Route = "queue" | "runs";

function readRoute(): Route {
  return window.location.hash === "#/runs" ? "runs" : "queue";
}

export function useHashRoute(): [Route, (next: Route) => void] {
  const [route, setRoute] = useState<Route>(readRoute);

  useEffect(() => {
    const onChange = () => {
      setRoute(readRoute());
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);

  return [
    route,
    (next: Route) => {
      window.location.hash = next === "runs" ? "#/runs" : "#/queue";
    },
  ];
}
