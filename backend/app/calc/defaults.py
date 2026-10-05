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
