// Reine Hilfsfunktionen der Rezeptseiten (Formatierung, Umrechnung, Fehlertexte).
import { ApiError } from "../../api/client";
import { numDe } from "../../components/crud";
import { num } from "../../format";
import type { Macro, Nutrients, SlotName } from "./types";

/** Standard-Mahlzeit nach Tageszeit (Stunde 0–23). */
export function defaultSlotForHour(hour: number): SlotName {
  if (hour < 10) return "breakfast";
  if (hour < 15) return "lunch";
  if (hour < 21) return "dinner";
  return "snack";
}

/** „1,3-fache Portion“ */
export const factorText = (factor: number): string => `${numDe(factor)}-fache Portion`;

export function scaleNutrients(n: Nutrients, factor: number): Nutrients {
  return {
    kcal: n.kcal * factor,
    protein_g: n.protein_g * factor,
    fat_g: n.fat_g * factor,
    carb_g: n.carb_g * factor,
    fiber_g: n.fiber_g * factor,
    salt_g: n.salt_g * factor,
    micros: Object.fromEntries(Object.entries(n.micros).map(([k, v]) => [k, v * factor])),
  };
}

export type FitLevel = { label: string; kind: "ok" | "warn" | "error" };

/** Textliche Einstufung des Fit-Scores (0–100), damit die Farbe nie das einzige Merkmal ist. */
export function fitLevel(score: number): FitLevel {
  if (score >= 80) return { label: "sehr gut", kind: "ok" };
  if (score >= 60) return { label: "gut", kind: "ok" };
  if (score >= 40) return { label: "mäßig", kind: "warn" };
  return { label: "schlecht", kind: "error" };
}

export function satietyLevel(score: number): string {
  if (score >= 70) return "hoch";
  if (score >= 40) return "mittel";
  return "niedrig";
}

export const MACROS = [
  { key: "kcal", label: "Kalorien", unit: "kcal" },
  { key: "protein_g", label: "Protein", unit: "g" },
  { key: "fat_g", label: "Fett", unit: "g" },
  { key: "carb_g", label: "Kohlenhydrate", unit: "g" },
] as const;

export type MacroShare = {
  key: (typeof MACROS)[number]["key"];
  label: string;
  unit: string;
  value: number;
  target: number;
  /** Anteil am Slot-Ziel in Prozent (100 = Ziel getroffen); `null`, wenn das Ziel 0 ist */
  pct: number | null;
  /** Abweichung vom Ziel in Prozent (negativ = darunter) */
  deviation: number | null;
};

export function macroShares(scaled: Macro, target: Macro): MacroShare[] {
  return MACROS.map((m) => {
    const value = scaled[m.key];
    const goal = target[m.key];
    const pct = goal > 0 ? (value / goal) * 100 : null;
    return { key: m.key, label: m.label, unit: m.unit, value, target: goal, pct, deviation: pct === null ? null : pct - 100 };
  });
}

/** Makrowerte (kcal, Protein, Fett, Kohlenhydrate) mit Faktor skaliert. */
export const scaleMacro = (m: Macro, factor: number): Macro => ({
  kcal: m.kcal * factor,
  protein_g: m.protein_g * factor,
  fat_g: m.fat_g * factor,
  carb_g: m.carb_g * factor,
});

export function deviationText(deviation: number | null): string {
  if (deviation === null) return "kein Ziel";
  const rounded = Math.round(Math.abs(deviation));
  if (rounded === 0) return "trifft das Ziel";
  return deviation < 0 ? `${rounded} % unter dem Ziel` : `${rounded} % über dem Ziel`;
}

export function minutesText(prep: number | null, cook: number | null): string {
  if (prep === null && cook === null) return "–";
  return `${(prep ?? 0) + (cook ?? 0)} Min.`;
}

export function minutesDetail(prep: number | null, cook: number | null): string {
  const parts: string[] = [];
  if (prep !== null) parts.push(`${prep} Min. Vorbereitung`);
  if (cook !== null) parts.push(`${cook} Min. Kochen`);
  return parts.join(", ");
}

export const weightText = (g: number | null | undefined): string => num(g, 0, "g");

/** Menge und Einheit einer Zeile: „2 EL“, „200 g“ oder „–“. */
export function quantityText(quantity: number | null, unit: string | null): string {
  if (quantity === null) return "–";
  return unit ? `${numDe(quantity)} ${unit}` : numDe(quantity);
}

const LEADING_QUANTITY =
  /^[\s~≈]*(?:ca\.?|etwa)?\s*[\d½¼¾⅓⅔][\d.,/\-–\s½¼¾⅓⅔]*\s*(?:(?:g|gr|gramm|kg|kilo|ml|l|liter|el|tl|stk\.?|stück|prise[n]?|bund|zehen?|dosen?|packung(?:en)?|päckchen|scheiben?|pck\.?)\b\.?)?\s*/i;

/** Rät den Zutatennamen aus einer Rezeptzeile („200 g Mehl“ → „Mehl“), als Startwert für die Zutatensuche. */
export function guessName(raw: string): string {
  const withoutNote = raw.split(":")[0] ?? raw;
  const withoutBrackets = withoutNote.replace(/\([^)]*\)/g, " ");
  const stripped = withoutBrackets.replace(LEADING_QUANTITY, "").split(",")[0] ?? "";
  return stripped.replace(/\s+/g, " ").trim();
}

/** Zerlegt Freitext in Zeilen (eine Zutat je Zeile, ohne Leerzeilen). */
export function splitLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l !== "");
}

export type ErrorInfo = { status: number; message: string };

export function errorInfo(e: unknown): ErrorInfo {
  if (e instanceof ApiError) return { status: e.status, message: e.message };
  return { status: 0, message: "Unbekannter Fehler." };
}

/** Liest die Rezept-ID aus der 409-Meldung „Dieses Rezept ist schon vorhanden (ID 12).“ */
export function existingRecipeId(message: string): number | null {
  const m = /ID\s+(\d+)/.exec(message);
  return m ? Number(m[1]) : null;
}

export const SATIETY_PART_LABELS: Record<string, string> = {
  density: "Energiedichte (niedrig ist gut)",
  volume: "Gewicht der Portion",
  protein: "Protein je 100 kcal",
  fiber: "Ballaststoffe je 100 kcal",
  warm: "Warm serviert",
};

/** Mikronährstoffe, die in der Detailansicht gezeigt werden (Schlüssel → Name und Einheit). */
export const MICRO_ROWS: { key: string; label: string; unit: string }[] = [
  { key: "zinc_mg", label: "Zink", unit: "mg" },
  { key: "iron_mg", label: "Eisen", unit: "mg" },
  { key: "potassium_mg", label: "Kalium", unit: "mg" },
  { key: "magnesium_mg", label: "Magnesium", unit: "mg" },
  { key: "calcium_mg", label: "Calcium", unit: "mg" },
  { key: "sodium_mg", label: "Natrium", unit: "mg" },
];
