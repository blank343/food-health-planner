// Deutsche Bezeichnungen für bekannte Schlüssel. Nur Anzeigehilfe: unbekannte Schlüssel bleiben unverändert sichtbar.

export const NUTRIENT_LABELS: Record<string, string> = {
  salt_g: "Salz (g)",
  zinc_mg: "Zink (mg)",
  magnesium_mg: "Magnesium (mg)",
  vitamin_d_ug: "Vitamin D (µg)",
  epa_dha_mg: "EPA/DHA (mg)",
  folate_ug: "Folat (µg)",
  vitamin_k2_ug: "Vitamin K2 (µg)",
  creatine_g: "Kreatin (g)",
  potassium_salt: "Kaliumsalz",
  fatty_fish_portions: "Fetter Fisch (Portionen)",
  licorice: "Lakritz",
  grapefruit: "Grapefruit",
  fiber_g: "Ballaststoffe (g)",
  sodium_mg: "Natrium (mg)",
};

/** Schlüsselvorschläge für Supplemente (Beitrag pro Tag). */
export const SUPPLEMENT_NUTRIENT_KEYS = [
  "zinc_mg",
  "magnesium_mg",
  "vitamin_d_ug",
  "epa_dha_mg",
  "folate_ug",
  "vitamin_k2_ug",
  "creatine_g",
];

/** Gegenstandsvorschläge für Ernährungsregeln. */
export const RULE_SUBJECT_KEYS = [
  "salt_g",
  "zinc_mg",
  "potassium_salt",
  "epa_dha_mg",
  "fatty_fish_portions",
  "licorice",
  "grapefruit",
  "fiber_g",
  "sodium_mg",
];

export const EFFECT_LABELS: Record<string, string> = {
  boost_iron_vitc: "Eisen mit Vitamin C kombinieren",
  boost_vitamin_d: "Vitamin-D-Zufuhr erhöhen",
  limit_sodium: "Natrium begrenzen",
  boost_unsaturated_fat: "Ungesättigte Fette bevorzugen",
  boost_fiber: "Ballaststoffe erhöhen",
};

export const EFFECT_KEYS = Object.keys(EFFECT_LABELS);

export const nutrientLabel = (key: string): string => NUTRIENT_LABELS[key] ?? key;
export const effectLabel = (key: string): string => EFFECT_LABELS[key] ?? key;

/** Optionen für `<datalist>`: Wert = Schlüssel, Beschriftung = deutscher Name (falls bekannt). */
export function suggestionOptions(keys: string[], labels: Record<string, string>) {
  return keys.map((k) => ({ value: k, label: labels[k] }));
}
