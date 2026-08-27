/*
 * The only place the application talks HTTP. The token is attached here and nowhere else, and the
 * fixture switch lives here so no component knows whether the data came from the API or from
 * `src/fixtures/`.
 *
 * `?live=1` forces the real API, `?fixtures=1` forces the fixtures, and otherwise the build-time
 * `VITE_FIXTURES` decides — which `.env.development` sets, so `npm run dev` is demonstrable with
 * no server running while a production build always talks to the real one.
 *
 * PACKAGING TRAP — read before touching the fixture branches below.
 *
 * `src/fixtures/` must not reach the built bundle. It holds placeholder identity data, and the
 * repository's generalization gate scans every tracked file, so a fixture string compiled into
 * the committed bundle fails the gate and ships inside every wheel. `VITE_FIXTURES` alone cannot
 * prevent that: it only decides which branch RUNS, while a top-level `import` keeps the module in
 * the graph and Rollup emits it regardless. Every reference to `../fixtures/` must therefore be
 * a dynamic `import()` behind a literal `import.meta.env.DEV`, which Vite replaces with `false`
 * in a production build so the branch is provably dead and the module has no importer left.
 */
import { authHeaders } from "./token";
import type {
  Answers,
  AppliedResponse,
  QueueDetail,
  QueueResponse,
  RevealResponse,
  RunFunnel,
  RunsResponse,
  SkipResponse,
} from "./types";

function resolveFixtureMode(): boolean {
  // A production bundle holds no fixtures to serve, so no query parameter may claim otherwise.
  if (!import.meta.env.DEV) return false;
  const params = new URLSearchParams(window.location.search);
  if (params.get("live") === "1") return false;
  if (params.get("fixtures") === "1") return true;
  return import.meta.env.VITE_FIXTURES === "1";
}

export const FIXTURE_MODE = resolveFixtureMode();

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, method: "GET" | "POST" = "GET"): Promise<T> {
  if (import.meta.env.DEV && FIXTURE_MODE) {
    const { FixtureError, fixtureFetch } = await import("../fixtures/server");
    try {
      return (await fixtureFetch(path, method)) as T;
    } catch (error) {
      if (error instanceof FixtureError) throw new ApiError(error.status, error.message);
      throw error;
    }
  }
  const response = await fetch(path, {
    method,
    headers: { ...authHeaders(), Accept: "application/json" },
    // Loopback, same origin, no cookies: the bearer header is the only credential.
    credentials: "omit",
    mode: "same-origin",
    redirect: "error",
  });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 401
        ? "Not authorised. Re-open the URL the CLI printed — it carries the token."
        : `${String(response.status)} from ${path}`,
    );
  }
  return (await response.json()) as T;
}

export const getQueue = (): Promise<QueueResponse> => request<QueueResponse>("/api/queue");

export const getDetail = (postingId: number): Promise<QueueDetail> =>
  request<QueueDetail>(`/api/queue/${String(postingId)}`);

export const markApplied = (postingId: number): Promise<AppliedResponse> =>
  request<AppliedResponse>(`/api/queue/${String(postingId)}/applied`, "POST");

export const markSkipped = (postingId: number): Promise<SkipResponse> =>
  request<SkipResponse>(`/api/queue/${String(postingId)}/skipped`, "POST");

export const unskip = (postingId: number): Promise<SkipResponse> =>
  request<SkipResponse>(`/api/queue/${String(postingId)}/unskip`, "POST");

export const revealFolder = (postingId: number): Promise<RevealResponse> =>
  request<RevealResponse>(`/api/queue/${String(postingId)}/reveal`, "POST");

export const getAnswers = (): Promise<Answers> => request<Answers>("/api/answers");

export const getRuns = (): Promise<RunsResponse> => request<RunsResponse>("/api/runs");

export const getFunnel = (runId: number): Promise<RunFunnel> =>
  request<RunFunnel>(`/api/runs/${String(runId)}`);

/**
 * The PDF endpoint needs the bearer header, so it cannot be a plain `window.open` on the URL —
 * that request would carry no `Authorization` and come back 401. The bytes are fetched, wrapped in
 * a blob URL and opened in a new tab, which is what "inline, new tab" means once the endpoint is
 * authenticated.
 */
export async function openPdf(postingId: number): Promise<void> {
  if (import.meta.env.DEV && FIXTURE_MODE) {
    throw new ApiError(501, "Fixture mode holds no PDF bytes. Run against the API to open it.");
  }
  const response = await fetch(`/api/pdf/${String(postingId)}`, {
    headers: authHeaders(),
    credentials: "omit",
    mode: "same-origin",
    redirect: "error",
  });
  if (!response.ok) throw new ApiError(response.status, `could not fetch the PDF`);
  const url = URL.createObjectURL(await response.blob());
  window.open(url, "_blank", "noopener,noreferrer");
  // The tab has the bytes by the time the task queue drains; holding the URL leaks it.
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 60_000);
}
