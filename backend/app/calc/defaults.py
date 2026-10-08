"""Sichere Standardwerte der Rechner.

Das sind **Startwerte**, keine festen Regeln: Jede Person kann sie über ihre Einstellungen
(`PersonSettings`) und ihr Zielprofil überschreiben. Hier steht nichts Personenbezogenes.
"""

KCAL_PER_KG_BODY_MASS = 7700.0  # grobe Energie pro kg Körpermasse (Orientierungswert)

# Makros
PROTEIN_G_PER_KG_LOSE = 2.0
PROTEIN_G_PER_KG_MAINTAIN = 1.6
PROTEIN_G_PER_KG_GAIN = 1.8
FAT_PCT_OF_KCAL = 30.0

# Sicherheitsgrenzen
KCAL_FLOOR_ABSOLUTE = {"m": 1500.0, "f": 1200.0}
KCAL_FLOOR_BMR_FACTOR = 1.0  # nie unter 1,0 × Grundumsatz
PROTEIN_FLOOR_G_PER_KG = 1.2
MAX_RATE_KG_PER_WEEK = 1.0
MAX_RATE_PCT_BODY_WEIGHT = 1.0  # pro Woche
TAPER_WEIGHT_KG = 3.0  # Tempo sinkt linear auf 0, sobald das Gewicht so nah an der Grenze ist
TAPER_BF_PCT_POINTS = 2.0
BF_FLOOR_HINT_PCT = {"m": 10.0, "f": 18.0}  # nur Hinweis, nie Zwang
IMPLAUSIBLE_FLOOR_LEAN_FACTOR = 1.05  # Gewichtsgrenze < Magermasse × 1,05 → Hinweis
IMPLAUSIBLE_BF_PCT = 5.0

# Energiebedarf aus Gerätedaten und Kalibrierung am Gewichtstrend
TDEE_WINDOW_DAYS = 28
TDEE_MIN_WEIGHT_POINTS = 6
TDEE_CLAMP = (0.75, 1.15)  # Faktor auf den Gerätewert
TDEE_MAX_BLEND = 0.7

# Verteilung der Wochenenergie auf Tage nach Belastung (wird auf Mittel 1 normalisiert)
DAY_TYPE_WEIGHTS = {"rest": 0.95, "easy": 1.0, "moderate": 1.03, "hard": 1.08}

# Standard-Slots (Anteile werden normalisiert und sind je Person in den Einstellungen änderbar)
DEFAULT_SLOT_SHARES = {"breakfast": 0.3, "lunch": 0.3, "dinner": 0.4}

# Quellenpriorität, wenn mehrere Importe denselben Tag liefern (höchste zuerst)
SOURCE_PRIORITY = ["manual", "apple_health_xml", "hae_zip"]  # manuell eingetragene Werte gewinnen

# ---------------------------------------------------------------------------
# Phase 2: Zutaten, Nährwerte, Sättigung, Passung ins Tagesziel
# ---------------------------------------------------------------------------

# Schlüssel in `Ingredient.micros` (je 100 g) und `Nutrients.micros` (absolut)
MICRO_KEYS = [
    "sat_fat_g", "sugar_g", "omega3_g", "epa_dha_g", "sodium_mg", "potassium_mg", "calcium_mg",
    "magnesium_mg", "phosphorus_mg", "iron_mg", "zinc_mg", "iodine_ug", "vit_a_ug", "vit_d_ug",
    "vit_e_mg", "vit_k_ug", "vit_c_mg", "vit_b12_ug", "folate_ug",
]  # fmt: skip

# Einheiten: Schreibweise (klein) → normalisierte Einheit
UNIT_ALIASES = {
    "g": "g", "gr": "g", "gramm": "g", "kg": "kg", "kilo": "kg", "ml": "ml", "l": "l", "liter": "l",
    "el": "EL", "esslöffel": "EL", "tl": "TL", "teelöffel": "TL", "prise": "Prise", "prisen": "Prise",
    "stück": "Stück", "stk": "Stück", "stk.": "Stück", "zehe": "Zehe", "zehen": "Zehe",
    "bund": "Bund", "dose": "Dose", "dosen": "Dose", "packung": "Packung", "pck": "Packung",
    "pkg": "Packung", "päckchen": "Packung", "scheibe": "Scheibe", "scheiben": "Scheibe",
    "becher": "Becher", "tasse": "Tasse", "tassen": "Tasse", "handvoll": "Handvoll",
    "stange": "Stange", "stangen": "Stange", "zweig": "Zweig", "zweige": "Zweig",
    "blatt": "Blatt", "blätter": "Blatt", "einheit": "Stück", "einheiten": "Stück",
    "glas": "Glas", "würfel": "Würfel", "msp": "Prise", "msp.": "Prise",
}  # fmt: skip

# Milliliter je Einheit und ungefähre Gramm je Einheit (wenn weder `piece_g` noch Dichte vorliegen)
ML_PER_UNIT = {"EL": 15.0, "TL": 5.0, "Tasse": 240.0, "Becher": 150.0, "Glas": 200.0}
GRAMS_PER_UNIT = {
    "Prise": 0.4, "Zehe": 4.0, "Bund": 40.0, "Dose": 400.0, "Packung": 250.0, "Scheibe": 30.0,
    "Handvoll": 30.0, "Stange": 60.0, "Zweig": 2.0, "Blatt": 1.0, "Würfel": 10.0,
}  # fmt: skip
DEFAULT_PIECE_G = 100.0  # "1 Zwiebel" ohne bekanntes Stückgewicht

# Sättigungsscore: Teilwerte 0–1, linear zwischen (schlecht, gut)
SATIETY_WEIGHTS = {"density": 0.35, "volume": 0.20, "protein": 0.20, "fiber": 0.15, "warm": 0.10}
SATIETY_DENSITY_KCAL_100G = (250.0, 60.0)  # ≥ 250 kcal/100 g = 0, ≤ 60 = 1 (niedrig ist gut)
SATIETY_VOLUME_G = (200.0, 500.0)  # Gewicht einer Portion
SATIETY_PROTEIN_G_PER_100KCAL = (2.0, 8.0)
SATIETY_FIBER_G_PER_100KCAL = (0.5, 2.5)

# Passung ins Tagesziel
FIT_MIN_FACTOR = 0.5
FIT_MAX_FACTOR = 2.0
FIT_MACRO_WEIGHTS = {"kcal": 0.3, "protein": 0.4, "fat": 0.15, "carb": 0.15}
FIT_TOLERANCE_PCT = 10.0  # Abweichung bis hierhin = voller Score, danach sinkt er linear
FIT_ZERO_PCT = 60.0  # ab dieser Abweichung 0 Punkte
