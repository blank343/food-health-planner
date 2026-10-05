// Anzeigehilfen der Verwaltungsseiten.
import { ApiError } from "../../api/client";

const nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

/** Zahl in deutscher Schreibweise, höchstens zwei Nachkommastellen (`1,5`, `2.000`). */
export const numDe = (n: number): string => nf.format(n);

/** Leerer Text wird zu `null` (der Server erwartet `null` statt `""`). */
export function optText(s: string): string | null {
  const t = s.trim();
  return t === "" ? null : t;
}

/** Entfernt die englische Pydantic-Vorsilbe aus Servermeldungen. */
export function cleanMessage(message: string): string {
  return message.replace(/(^|[:;]\s)Value error, /g, "$1");
}

/** Deutsche Fehlermeldung zu einer beliebigen Ausnahme. */
export function errorText(e: unknown): string {
  return e instanceof ApiError ? cleanMessage(e.message) : "Unbekannter Fehler.";
}

/** `HH:MM:SS` → `HH:MM` (für Anzeige und Zeitfeld). */
export function hhmm(t: string | null | undefined): string {
  return t ? t.slice(0, 5) : "";
}
