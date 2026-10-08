// Beschriftungen, Typen und Anzeigehilfen für Zutaten.
import type { components } from "../../api/schema";

export type IngredientOut = components["schemas"]["IngredientOut"];
export type IngredientDetail = components["schemas"]["IngredientDetailOut"];
export type IngredientIn = components["schemas"]["IngredientIn"];
export type IngredientPatch = components["schemas"]["IngredientPatch"];
export type Per100 = components["schemas"]["NutrientsPer100Out"];
export type PreferenceOut = components["schemas"]["PreferenceOut"];
export type PrefLevel = components["schemas"]["PreferenceIn"]["level"];

export type Source = "bls" | "off" | "manual";

export const SOURCE_LABELS: Record<string, string> = {
  bls: "BLS",
  manual: "Manuell",
  off: "Open Food Facts",
};
export const sourceLabel = (s: string): string => SOURCE_LABELS[s] ?? s;

/** Mikronährstoffe in fester Reihenfolge (Schlüssel wie im Backend, je 100 g). */
export const MICRO_LABELS: Record<string, string> = {
  sat_fat_g: "Gesättigte Fettsäuren (g)",
  sugar_g: "Zucker (g)",
  omega3_g: "Omega-3 (g)",
  epa_dha_g: "EPA/DHA (g)",
  sodium_mg: "Natrium (mg)",
  potassium_mg: "Kalium (mg)",
  calcium_mg: "Calcium (mg)",
  magnesium_mg: "Magnesium (mg)",
  phosphorus_mg: "Phosphor (mg)",
  iron_mg: "Eisen (mg)",
  zinc_mg: "Zink (mg)",
  iodine_ug: "Jod (µg)",
  vit_a_ug: "Vitamin A (µg)",
  vit_d_ug: "Vitamin D (µg)",
  vit_e_mg: "Vitamin E (mg)",
  vit_k_ug: "Vitamin K (µg)",
  vit_c_mg: "Vitamin C (mg)",
  vit_b12_ug: "Vitamin B12 (µg)",
  folate_ug: "Folat (µg)",
};
export const MICRO_KEYS = Object.keys(MICRO_LABELS);

export const LEVELS: PrefLevel[] = ["like", "dislike", "never"];
export const LEVEL_LABELS: Record<PrefLevel, string> = {
  like: "Mag ich",
  dislike: "Mag ich nicht",
  never: "Nie",
};
export const LEVEL_HELP: Record<PrefLevel, string> = {
  like: "Der Planer bevorzugt diese Zutat später.",
  dislike: "Der Planer vermeidet diese Zutat später nach Möglichkeit.",
  never: "Harte Grenze: Der Planer verwendet diese Zutat später nie.",
};
export const levelLabel = (level: string): string => LEVEL_LABELS[level as PrefLevel] ?? level;
export const isLevel = (v: string): v is PrefLevel => (LEVELS as string[]).includes(v);

const nf3 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 3 });
/** Zahl mit höchstens drei Nachkommastellen; `null` wird zu „–“. */
export function fmt(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "–" : nf3.format(v);
}

/** Salz in g je 100 g; fehlt der Wert, wird er aus Natrium (mg) abgeleitet (Salz = Natrium × 2,5). */
export function saltOf(n: Per100): number | null {
  if (n.salt_g !== null && n.salt_g !== undefined) return n.salt_g;
  const sodium = n.micros?.sodium_mg;
  return typeof sodium === "number" ? (sodium * 2.5) / 1000 : null;
}

/** Mikronährstoffe als [Schlüssel, Beschriftung, Wert]: bekannte zuerst in fester Reihenfolge, dann unbekannte. */
export function microEntries(micros: Record<string, number>): [string, string, number][] {
  const known = MICRO_KEYS.filter((k) => k in micros).map((k) => [k, MICRO_LABELS[k] ?? k, micros[k] as number] as [string, string, number]);
  const unknown = Object.keys(micros)
    .filter((k) => !(k in MICRO_LABELS))
    .sort()
    .map((k) => [k, k, micros[k] as number] as [string, string, number]);
  return [...known, ...unknown];
}
