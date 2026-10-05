"""Tages- und Wochenziele für Energie und Makronährstoffe.

Reine Funktionen. 4/4/9 kcal pro g Protein/Kohlenhydrate/Fett.
"""

import math

from app.calc import defaults
from app.calc.types import DayTarget, DayType, GoalSpec, PersonProfile, PersonSettings

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

# Wird nur verwendet, wenn ein Ziel weder Tempo noch Prozentwert angibt.
_DEFAULT_MODIFIER_PCT = {"lose": -10.0, "maintain": 0.0, "gain": 5.0}
_DAYS_PER_WEEK = 7


def _protein_g_per_kg(goal: GoalSpec) -> float:
    if goal.protein_g_per_kg is not None:
        return goal.protein_g_per_kg
    return {
        "lose": defaults.PROTEIN_G_PER_KG_LOSE,
        "maintain": defaults.PROTEIN_G_PER_KG_MAINTAIN,
        "gain": defaults.PROTEIN_G_PER_KG_GAIN,
    }[goal.kind]


def energy_delta_kcal(goal: GoalSpec, tdee_kcal: float, kcal_per_kg: float) -> float:
    """Tägliche Energieabweichung vom Bedarf (Defizit negativ, Überschuss positiv).

    Tempo (kg/Woche) hat Vorrang vor `kcal_modifier_pct`. Bei "lose" ist die Abweichung immer
    negativ, bei "gain" positiv, bei "maintain" null. Ohne Angabe gilt -10 % bzw. +5 %.
    """
    if goal.kind == "maintain":
        return 0.0
    sign = -1.0 if goal.kind == "lose" else 1.0
    if goal.rate_kg_per_week is not None:
        return sign * abs(goal.rate_kg_per_week) * kcal_per_kg / _DAYS_PER_WEEK
    pct = goal.kcal_modifier_pct if goal.kcal_modifier_pct is not None else _DEFAULT_MODIFIER_PCT[goal.kind]
    return sign * abs(pct) / 100.0 * tdee_kcal


def implied_rate_kg_per_week(goal: GoalSpec, tdee_kcal: float, kcal_per_kg: float) -> float:
    """Gewichtsänderungstempo (kg/Woche, immer >= 0), das zur Energieabweichung des Ziels gehört."""
    return abs(energy_delta_kcal(goal, tdee_kcal, kcal_per_kg)) * _DAYS_PER_WEEK / kcal_per_kg


def compose_day_target(kcal: float, protein_g: float, fat_g: float, day_type: DayType = "easy") -> DayTarget:
    """Baut ein konsistentes Tagesziel aus Energie, Protein und Fett; Kohlenhydrate sind der Rest.

    Übersteigen Protein und Fett die Energie, wird zuerst das Fett gesenkt (und nie unter 0);
    reicht auch das nicht, wird das Protein auf die Energie begrenzt. Rundung auf 1 kcal und 0,1 g,
    die Kohlenhydrate werden aus dem gerundeten Rest berechnet, damit die Summe passt.
    """
    kcal_r = float(max(0, round(kcal)))
    protein_max = math.floor(kcal_r / KCAL_PER_G_PROTEIN * 10) / 10
    protein_r = min(round(max(0.0, protein_g), 1), protein_max)
    fat_max = max(0.0, (kcal_r - KCAL_PER_G_PROTEIN * protein_r) / KCAL_PER_G_FAT)
    fat_r = round(min(max(0.0, fat_g), fat_max), 1)
    if fat_r > fat_max:  # Rundung nach oben darf die Energie nicht überschreiten
        fat_r = math.floor(fat_max * 10) / 10
    carb_r = max(0.0, (kcal_r - KCAL_PER_G_PROTEIN * protein_r - KCAL_PER_G_FAT * fat_r) / KCAL_PER_G_CARB)
    return DayTarget(
        kcal=kcal_r, protein_g=protein_r, fat_g=fat_r, carb_g=round(carb_r, 1), day_type=day_type
    )


def _grams(profile: PersonProfile, goal: GoalSpec, kcal: float) -> tuple[float, float]:
    """Gewünschte Gramm Protein (g/kg Körpergewicht) und Fett (Anteil der Energie)."""
    protein = _protein_g_per_kg(goal) * profile.weight_kg
    fat_pct = goal.fat_pct if goal.fat_pct is not None else defaults.FAT_PCT_OF_KCAL
    fat = fat_pct / 100.0 * kcal / KCAL_PER_G_FAT
    return protein, fat


def daily_target(
    profile: PersonProfile,
    goal: GoalSpec,
    tdee_kcal: float,
    settings: PersonSettings,
    day_type: DayType = "easy",
) -> DayTarget:
    """Tagesziel aus Bedarf, Ziel und Einstellungen.

    Energie = Bedarf + Abweichung (siehe `energy_delta_kcal`). Protein in g/kg Körpergewicht,
    Fett als Anteil der Energie, Rest Kohlenhydrate (nie negativ). `day_type` kennzeichnet nur das
    Ergebnis; die Verteilung nach Belastung übernimmt `weekly_targets`. Die Sicherheitsgrenzen
    (Tempo, Untergrenzen) wendet `safety.apply_safety_limits` an.
    """
    kcal = max(0.0, tdee_kcal + energy_delta_kcal(goal, tdee_kcal, settings.kcal_per_kg))
    protein, fat = _grams(profile, goal, kcal)
    return compose_day_target(kcal, protein, fat, day_type)


def weekly_targets(
    profile: PersonProfile,
    goal: GoalSpec,
    tdee_kcal: float,
    settings: PersonSettings,
    week_day_types: dict[int, str],
) -> list[DayTarget]:
    """Sieben Tagesziele (Index 0 = Montag) mit nach Belastung verteilter Wochenenergie.

    Wochenenergie = 7 x Tagesziel. Die Gewichte aus `settings.day_type_weights` werden auf Mittel 1
    normalisiert (unbekannte oder fehlende Tagestypen zählen als "easy"), die Wochensumme bleibt
    erhalten (Rundung kumulativ, Abweichung höchstens 1 kcal). Protein und Fett sind an jedem Tag
    gleich, mehr oder weniger Energie geht in die Kohlenhydrate.
    """
    base_kcal = max(0.0, tdee_kcal + energy_delta_kcal(goal, tdee_kcal, settings.kcal_per_kg))
    protein, fat = _grams(profile, goal, base_kcal)
    easy_weight = settings.day_type_weights.get("easy", 1.0)
    types: list[str] = [week_day_types.get(i, "easy") for i in range(_DAYS_PER_WEEK)]
    raw = [settings.day_type_weights.get(t, easy_weight) for t in types]
    mean = sum(raw) / _DAYS_PER_WEEK
    weights = [w / mean for w in raw] if mean > 0 else [1.0] * _DAYS_PER_WEEK

    result: list[DayTarget] = []
    cumulative = 0.0
    rounded_before = 0
    for t, w in zip(types, weights, strict=True):
        cumulative += base_kcal * w
        rounded_now = round(cumulative)
        day_kcal = rounded_now - rounded_before
        rounded_before = rounded_now
        day_type: DayType = t if t in ("rest", "easy", "moderate", "hard") else "easy"  # type: ignore[assignment]
        result.append(compose_day_target(day_kcal, protein, fat, day_type))
    return result
