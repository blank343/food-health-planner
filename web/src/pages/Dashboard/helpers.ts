import { dayNumber } from "../../charts/scale";
import { num } from "../../format";

export const STALE_WEIGHT_DAYS = 30;

const SOURCE_NAMES: Record<string, string> = {
  apple_health_xml: "Apple Health",
  hae_zip: "Health Auto Export",
  manual: "Manuell",
};

export function sourceName(source: string): string {
  return SOURCE_NAMES[source] ?? source;
}

const IMPORT_KINDS: Record<string, string> = {
  apple_health: "Apple Health",
  hae: "Health Auto Export",
};

export function importKindName(kind: string): string {
  return IMPORT_KINDS[kind] ?? SOURCE_NAMES[kind] ?? kind;
}

export function importStatus(status: string): { label: string; kind?: "ok" | "warn" | "error" } {
  switch (status) {
    case "done":
      return { label: "Fertig", kind: "ok" };
    case "failed":
      return { label: "Fehlgeschlagen", kind: "error" };
    case "running":
      return { label: "Läuft", kind: "warn" };
    case "queued":
      return { label: "Wartet" };
    default:
      return { label: status };
  }
}

/** Ganze Tage von `fromIso` bis `toIso` (positiv, wenn `toIso` später liegt). */
export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round(dayNumber(toIso) - dayNumber(fromIso));
}

/** Mit Vorzeichen, z. B. „+0,30“ / „-0,40“. */
export function signed(value: number | null | undefined, digits: number, unit: string): string {
  if (value === null || value === undefined) return "–";
  return `${value > 0 ? "+" : ""}${num(value, digits, unit)}`;
}

/** `2026-W41` → `41` */
export function weekNumber(isoWeek: string): string {
  const m = /W(\d{1,2})$/.exec(isoWeek);
  return m ? String(Number(m[1])) : isoWeek;
}
