import type { Companion, RunSummary } from "../api/types";

/*
 * The health strip's judgement, kept pure so each colour is pinned by a test (T293).
 *
 *   red   — the last attempt failed (a nightly or intraday run, or a companion);
 *   amber — stale: no nightly started today and it is past 06:00 local, or a companion says so;
 *   green — otherwise.
 *
 * A run still `running` is green: the strip reports results, and T287 owns the live run.
 */

export type Tone = "green" | "amber" | "red";

export interface HealthCell {
  label: string;
  tone: Tone;
  /** The reason in words, never just a colour. */
  text: string;
}

const STALE_AFTER_HOUR = 6;

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function sameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function minutes(run: RunSummary): string {
  if (run.started == null || run.finished == null) return "";
  const m = Math.round((Date.parse(run.finished) - Date.parse(run.started)) / 60_000);
  return `, ${String(m)} min`;
}

function runCell(label: string, run: RunSummary | undefined, now: Date, nightly: boolean): HealthCell {
  if (run === undefined) return { label, tone: "amber", text: "none recorded" };
  const stale =
    nightly &&
    now.getHours() >= STALE_AFTER_HOUR &&
    (run.started == null || !sameLocalDay(new Date(run.started), now));
  if (run.status === "failed") {
    const at = run.finished ?? run.started;
    return { label, tone: "red", text: `failed${at == null ? "" : ` ${clock(at)}`}` };
  }
  if (run.status === "running") {
    return { label, tone: stale ? "amber" : "green", text: "running now" };
  }
  const ended = run.finished == null ? "ended" : `ended ${clock(run.finished)}`;
  if (stale) return { label, tone: "amber", text: `none today; last ${ended}` };
  return { label, tone: "green", text: `ok, ${ended}${minutes(run)}` };
}

const COMPANION_TONE: Record<Companion["state"], Tone> = {
  ok: "green",
  running: "green",
  stale: "amber",
  failed: "red",
};

export function pipelineHealth(runs: RunSummary[], companions: Companion[], now: Date): HealthCell[] {
  // `/api/runs` is newest first.
  const nightly = runs.find((r) => r.kind === "delivery" && r.incremental !== true);
  const intraday = runs.find((r) => r.incremental === true);
  return [
    runCell("Nightly run", nightly, now, true),
    runCell("Intraday pass", intraday, now, false),
    ...companions.map((c) => ({
      label: c.name,
      tone: COMPANION_TONE[c.state],
      text: c.summary,
    })),
  ];
}

export function worstTone(cells: HealthCell[]): Tone {
  if (cells.some((c) => c.tone === "red")) return "red";
  if (cells.some((c) => c.tone === "amber")) return "amber";
  return "green";
}
