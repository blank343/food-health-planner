// Deutsche Darstellung von Zahlen und Daten.
const nf = (digits: number) => new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const cache = new Map<number, Intl.NumberFormat>();

export function num(value: number | null | undefined, digits = 0, unit?: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  let f = cache.get(digits);
  if (!f) {
    f = nf(digits);
    cache.set(digits, f);
  }
  return unit ? `${f.format(value)} ${unit}` : f.format(value);
}

export const kcal = (v: number | null | undefined) => num(v, 0, "kcal");
export const grams = (v: number | null | undefined) => num(v, 0, "g");
export const kg = (v: number | null | undefined, digits = 1) => num(v, digits, "kg");

/** ISO-Datum (`2026-10-05`) → `05.10.2026`. Fremde Werte bleiben unverändert. */
export function dateDe(iso: string | null | undefined): string {
  if (!iso) return "–";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

/** Heutiges Datum als ISO-Text in Ortszeit. */
export function todayIso(now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

export const WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
