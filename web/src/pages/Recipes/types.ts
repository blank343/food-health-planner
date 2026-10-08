// Typen (aus der API-Beschreibung) und feste Bezeichnungen der Rezeptseiten.
import type { components } from "../../api/schema";

type S = components["schemas"];

export type RecipeCard = S["RecipeCardOut"];
export type RecipeListData = S["RecipeListOut"];
export type RecipeDetail = S["RecipeDetailOut"];
export type RecipePatch = S["RecipePatch"];
export type RecipeCreate = S["RecipeCreate"];
export type LineIn = S["LineIn"];
export type TagIn = S["TagIn"];
export type Line = S["LineOut"];
export type Fit = S["FitOut"];
export type Macro = S["MacroOut"];
export type Nutrients = S["NutrientsOut"];
export type Targets = S["TargetsOut"];
export type Match = S["MatchOut"];
export type Preview = S["ImportPreviewOut"];
export type PreviewLine = S["PreviewLineOut"];
export type UnassignedLine = S["UnassignedLineOut"];
export type UnassignedListData = S["UnassignedListOut"];
export type AssignOut = S["AssignOut"];
export type IngredientList = S["IngredientListOut"];
export type IngredientOut = S["IngredientOut"];

export const SLOTS = ["breakfast", "lunch", "dinner", "snack"] as const;
export type SlotName = (typeof SLOTS)[number];

export const SLOT_NAMES: Record<SlotName, string> = {
  breakfast: "Frühstück",
  lunch: "Mittagessen",
  dinner: "Abendessen",
  snack: "Snack",
};

export const isSlot = (value: string): value is SlotName => (SLOTS as readonly string[]).includes(value);

export const STATUS_OPTIONS = [
  { value: "", label: "Alle" },
  { value: "ready", label: "Bereit" },
  { value: "needs_review", label: "Prüfen" },
  { value: "draft", label: "Entwurf" },
] as const;

export type StatusFilter = (typeof STATUS_OPTIONS)[number]["value"];

export type SortKey = "title" | "newest" | "kcal" | "protein" | "satiety" | "rating" | "fit";

export const SORT_LABELS: Record<SortKey, string> = {
  title: "Titel",
  newest: "Neueste zuerst",
  kcal: "Kalorien (aufsteigend)",
  protein: "Protein (absteigend)",
  satiety: "Sättigung (absteigend)",
  rating: "Meine Bewertung",
  fit: "Passung (beste zuerst)",
};

export type ListFilters = {
  q: string;
  slot: "" | SlotName;
  untagged: boolean;
  favorite: boolean;
  status: StatusFilter;
  sort: SortKey;
};

export const DEFAULT_FILTERS: ListFilters = {
  q: "",
  slot: "",
  untagged: false,
  favorite: false,
  status: "",
  sort: "title",
};
