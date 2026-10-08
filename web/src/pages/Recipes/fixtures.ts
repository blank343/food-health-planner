// Testdaten für die Rezeptseiten (nur in Tests verwendet).
import type { Fit, Line, RecipeCard, RecipeDetail, Targets } from "./types";

export const TODAY = "2026-10-06";

export function targets(over: Partial<Targets> = {}): Targets {
  return {
    date: TODAY,
    day_type: "moderate",
    target: { kcal: 2150, protein_g: 150, fat_g: 70, carb_g: 240 },
    slots: {
      snack: { kcal: 0, protein_g: 0, fat_g: 0, carb_g: 0 },
      dinner: { kcal: 750, protein_g: 55, fat_g: 25, carb_g: 80 },
      breakfast: { kcal: 500, protein_g: 35, fat_g: 15, carb_g: 60 },
      lunch: { kcal: 900, protein_g: 60, fat_g: 30, carb_g: 100 },
    },
    shares: { breakfast: 0.25, lunch: 0.4, dinner: 0.35, snack: 0 },
    tdee: { tdee_kcal: 2600, device_kcal: 2500, implied_kcal: 2700, confidence: 0.82, method: "calibrated", notes: [] },
    body: { weight_kg: 80.5, weight_date: "2026-10-01", body_fat_pct: 18.5, lean_mass_kg: null, height_cm: 180, age_years: 35.2 },
    goal: { kind: "lose", rate_kg_per_week: -0.5, applied_rate_kg_per_week: -0.4, valid_from: "2026-09-01" },
    warnings: [],
    ...over,
  };
}

export const NO_TARGETS = {
  status: 422,
  body: { detail: "Es liegt kein Gewicht vor. Bitte zuerst Gesundheitsdaten importieren." },
};

export function card(over: Partial<RecipeCard> = {}): RecipeCard {
  return {
    id: 1,
    title: "Hafer-Bowl",
    image_url: null,
    source_site: "beispiel.de",
    favorite: false,
    status: "ready",
    servings: 2,
    prep_min: 10,
    cook_min: 35,
    tag: {
      slot_types: ["breakfast"],
      cuisine: null,
      main_ingredient: null,
      batch_cookable: false,
      transportable: false,
      warm: false,
      shelf_days: null,
      season: null,
    },
    kcal: 600,
    protein_g: 36,
    fat_g: 18,
    carb_g: 80,
    serving_weight_g: 380,
    satiety_score: 72,
    coverage: 1,
    my_rating: null,
    avg_rating: null,
    fit_score: null,
    fit_factor: null,
    ...over,
  };
}

export function list(items: RecipeCard[], total = items.length) {
  return { items, total, limit: 100, offset: 0 };
}

export function line(over: Partial<Line> = {}): Line {
  return {
    id: 11,
    position: 0,
    raw_text: "200 g Haferflocken",
    quantity: 200,
    unit: "g",
    grams: 200,
    optional: false,
    ingredient: { id: 5, name: "Haferflocken", source: "bls" },
    nutrients: null,
    ...over,
  };
}

export function fit(over: Partial<Fit> = {}): Fit {
  return {
    slot: "lunch",
    date: TODAY,
    factor: 1.5,
    unclamped_factor: 1.5,
    grams: 570,
    scaled: { kcal: 900, protein_g: 54, fat_g: 27, carb_g: 120, fiber_g: 9, salt_g: 1, micros: {} },
    deviation_pct: { kcal: 0, protein_g: -10, fat_g: -10, carb_g: 20 },
    fit_score: 87,
    notes: ["Protein 6 g unter Ziel."],
    slot_target: { kcal: 900, protein_g: 60, fat_g: 30, carb_g: 100 },
    warnings: [],
    ...over,
  };
}

export function detail(over: Partial<RecipeDetail> = {}): RecipeDetail {
  const base = card({ id: 7, title: "Hafer-Bowl" });
  return {
    ...base,
    source_url: "https://beispiel.de/hafer-bowl",
    instructions: "Haferflocken kochen.\nObst dazugeben.",
    notes: null,
    lines: [
      line(),
      line({
        id: 12,
        position: 1,
        raw_text: "1 Prise Zimt",
        quantity: 1,
        unit: "Prise",
        grams: null,
        ingredient: null,
      }),
    ],
    total: {
      kcal: 1200,
      protein_g: 72,
      fat_g: 36,
      carb_g: 160,
      fiber_g: 20,
      salt_g: 1.2,
      micros: { zinc_mg: 6, iron_mg: 8, potassium_mg: 1400, magnesium_mg: 200 },
    },
    per_serving: {
      kcal: 600,
      protein_g: 36,
      fat_g: 18,
      carb_g: 80,
      fiber_g: 10,
      salt_g: 0.6,
      micros: { zinc_mg: 3, iron_mg: 4, potassium_mg: 700, magnesium_mg: 100 },
    },
    total_weight_g: 760,
    energy_density_kcal_per_100g: 158,
    missing: ["1 Prise Zimt"],
    satiety: { score: 72, parts: { density: 0.8, volume: 0.6, protein: 0.5, fiber: 0.4, warm: 0 } },
    ratings: [
      { person_id: 1, person_name: "Test A", rating: 4 },
      { person_id: 2, person_name: "Test B", rating: 2 },
    ],
    fit: fit(),
    warnings: [],
    coverage: 0.83,
    my_rating: 4,
    avg_rating: 3,
    fit_score: 87,
    fit_factor: 1.5,
    ...over,
  };
}
