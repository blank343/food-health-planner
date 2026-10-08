// Mengenlogik des Rechners: Gramm oder Stückzahl je Komponente, Grenzen und Umrechnung (rein, ohne Oberfläche).
import type { ComponentOut, MealItemIn, VariantOut } from "./types";

/** Auswahl einer Komponente: `amount` ist Gramm, bei einer Variante mit Stückgewicht die Stückzahl. */
export type Entry = { variantId: number | null; amount: number };

export type Resolved = {
  variant: VariantOut | null;
  /** Gramm je Einheit, wenn in Stück gerechnet wird. */
  gpu: number | null;
  min: number;
  max: number;
  step: number;
  grams: number;
};

const round = (n: number, digits = 2) => Math.round(n * 10 ** digits) / 10 ** digits;

export const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export function variantOf(c: ComponentOut, e: Entry): VariantOut | null {
  return c.variants.find((v) => v.id === e.variantId) ?? null;
}

/** Grenzen, Schritt und Gramm der aktuellen Menge (in Stück, falls die Variante ein Stückgewicht hat). */
export function resolve(c: ComponentOut, e: Entry): Resolved {
  const variant = variantOf(c, e);
  const gpu = variant?.grams_per_unit ?? null;
  if (gpu && gpu > 0) {
    const min = Math.ceil(c.min_g / gpu - 1e-9);
    const max = Math.max(min, Math.floor(c.max_g / gpu + 1e-9));
    const step = c.step_g >= gpu ? Math.max(1, Math.round(c.step_g / gpu)) : 1;
    return { variant, gpu, min, max, step, grams: round(e.amount * gpu, 1) };
  }
  return { variant, gpu: null, min: c.min_g, max: c.max_g, step: c.step_g, grams: e.amount };
}

/** Startmenge: übliche Menge, sonst die kleinste sinnvolle (mindestens ein Schritt). */
export function initialEntry(c: ComponentOut): Entry {
  const start = c.typical_g ?? Math.max(c.min_g, c.step_g);
  return { variantId: null, amount: clamp(start, c.min_g, c.max_g) };
}

/** Wechselt die Variante und rechnet die Menge um (Gramm ↔ Stück), begrenzt auf die Spanne. */
export function withVariant(c: ComponentOut, e: Entry, variantId: number | null): Entry {
  const grams = resolve(c, e).grams;
  const next: Entry = { variantId, amount: e.amount };
  const r = resolve(c, next);
  const amount = r.gpu ? Math.round(grams / r.gpu) : grams;
  return { variantId, amount: clamp(amount, r.min, r.max) };
}

/** Eintrag für `POST /components/meal` (Stück nur mit Variante mit Stückgewicht). */
export function toMealItem(c: ComponentOut, e: Entry): MealItemIn | null {
  if (!(e.amount > 0)) return null;
  const r = resolve(c, e);
  const item: MealItemIn = { component_id: c.id };
  if (r.variant) item.variant_id = r.variant.id;
  if (r.gpu) item.units = e.amount;
  else item.grams = e.amount;
  return item;
}

/** Werktag: die üblichen Komponenten ohne „Wochenende fest“; Wochenende: nur die festen Komponenten. */
export function presetSelection(components: ComponentOut[], preset: "weekday" | "weekend"): Record<number, Entry> {
  const weekday = components.filter((c) => !c.weekend_fixed);
  const usual = weekday.filter((c) => c.typical_g !== null);
  const chosen = preset === "weekend" ? components.filter((c) => c.weekend_fixed) : usual.length > 0 ? usual : weekday;
  return Object.fromEntries(chosen.map((c) => [c.id, initialEntry(c)]));
}
