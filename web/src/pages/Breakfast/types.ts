// Typen und Beschriftungen des Frühstücks-Baukastens.
import type { components } from "../../api/schema";

export type ComponentOut = components["schemas"]["ComponentOut"];
export type ComponentIn = components["schemas"]["ComponentIn"];
export type VariantOut = components["schemas"]["VariantOut"];
export type VariantIn = components["schemas"]["VariantIn"];
export type MealOut = components["schemas"]["MealOut"];
export type MealFitOut = components["schemas"]["MealFitOut"];
export type MealIn = components["schemas"]["MealIn"];
export type MealItemIn = components["schemas"]["MealItemIn"];
export type SeedOut = components["schemas"]["SeedOut"];
export type TargetsOut = components["schemas"]["TargetsOut"];
export type Kind = ComponentIn["kind"];
export type SlotName = NonNullable<MealIn["slot"]>;

export const KIND_ORDER: Kind[] = ["protein", "carb", "dairy", "fruit", "veg", "other"];
export const KIND_LABELS: Record<string, string> = {
  protein: "Eiweiß",
  carb: "Kohlenhydrate",
  dairy: "Milchprodukt",
  fruit: "Obst",
  veg: "Gemüse",
  other: "Sonstiges",
};
export const kindLabel = (k: string): string => KIND_LABELS[k] ?? k;
export const isKind = (v: string): v is Kind => (KIND_ORDER as string[]).includes(v);

export const SLOT_ORDER: SlotName[] = ["breakfast", "lunch", "dinner", "snack"];
export const SLOT_NAMES: Record<string, string> = {
  breakfast: "Frühstück",
  lunch: "Mittagessen",
  dinner: "Abendessen",
  snack: "Snack",
};
export const slotName = (s: string): string => SLOT_NAMES[s] ?? s;
export const isSlot = (v: string): v is SlotName => (SLOT_ORDER as string[]).includes(v);
