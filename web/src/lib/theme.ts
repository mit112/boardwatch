/*
 * The theme choice. There are two explicit themes and a default that follows the system: with no
 * stored choice `<html>` carries no `data-theme` and the stylesheet's `prefers-color-scheme` rule
 * decides, so a fresh browser gets whatever its operating system is set to. Choosing a theme
 * stores it in `localStorage` — a per-viewer convenience, kept in this browser only — and sets
 * `data-theme`, which outranks the system rule.
 *
 * Every storage access is wrapped: storage throws when it is disabled, and a viewer that cannot
 * remember a theme must still be a viewer that works.
 */

export type Theme = "light" | "dark";

const THEME_KEY = "boardwatch.theme";

export function readTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

/** Applies a stored explicit choice, or nothing — leaving the system preference in charge. Called
 *  once, before the first render, so the page does not flash the wrong theme. */
export function applyStoredTheme(): void {
  const stored = readTheme();
  if (stored !== null) document.documentElement.dataset["theme"] = stored;
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset["theme"] = theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* Not remembering is not a failure. */
  }
}

/** The theme actually in force: the explicit one on `<html>`, else what the system asks for. */
export function effectiveTheme(): Theme {
  const explicit = document.documentElement.dataset["theme"];
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
