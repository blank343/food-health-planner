// Farbschema: "system" folgt dem Gerät, "hell"/"dunkel" überschreiben es.
// Gespeichert wird im Browser (localStorage, mit Schutz gegen gesperrten Speicher).
export type Theme = "system" | "light" | "dark";

export const THEME_KEY = "fhp.theme";

export function getStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function storeTheme(theme: Theme): void {
  try {
    if (theme === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* Speicher gesperrt: das Schema gilt dann nur bis zum Neuladen */
  }
}

export function applyTheme(theme: Theme): void {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}

/** Beim Start der App aufrufen, damit das gespeicherte Schema sofort gilt. */
export function applyStoredTheme(): void {
  applyTheme(getStoredTheme());
}
