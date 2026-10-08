"""Nährwerte von Rezepten und Baukasten-Mahlzeiten, Sättigungsscore und Passung ins Slot-Ziel.

Reine Funktionen ohne Datenbank (siehe docs/PHASE2.md, Abschnitte 4.2 und 6).
"""

from collections.abc import Mapping, Sequence

from app.calc import defaults
from app.calc.types import (
    ComponentChoice,
    LineNutrition,
    Nutrients,
    NutrientsPer100,
    RecipeNutrition,
    SatietyScore,
    SlotFit,
    SlotTarget,
)

# Salz (g) = Natrium (g) × 2,5, also Natrium in mg × 2,5 / 1000
SALT_PER_SODIUM = 2.5
_SATIETY_PARTS = ("density", "volume", "protein", "fiber", "warm")
_MACROS = ("kcal", "protein", "fat", "carb")
_MACRO_LABELS = {"fat": "Fett", "carb": "Kohlenhydrate"}
_PROTEIN_UNDER_PENALTY = 1.5  # Protein unter Ziel zählt bei der Abweichung 1,5-fach
_SIZE_LARGE = 1.5
_SIZE_SMALL = 0.7
_OVER_TARGET_NOTE_PCT = 30.0


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _fmt(value: float, digits: int = 1) -> str:
    """Zahl mit deutschem Komma, ohne überflüssige Nachkommastellen (2.0 → "2", 1.75 → "1,8")."""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text.replace(".", ",")


def _linear(value: float, bad: float, good: float) -> float:
    """0 bei `bad`, 1 bei `good`, dazwischen linear, außerhalb auf 0..1 begrenzt (bad > good erlaubt)."""
    if good == bad:
        return 1.0 if value >= good else 0.0
    return min(1.0, max(0.0, (value - bad) / (good - bad)))


def _merged_weights(
    base: Mapping[str, float], override: Mapping[str, float] | None, allowed: Sequence[str]
) -> dict[str, float]:
    """Standardgewichte, für die angegebenen Schlüssel überschrieben, danach auf Summe 1 normalisiert."""
    weights = {key: float(base.get(key, 0.0)) for key in allowed}
    if override:
        unknown = set(override) - set(allowed)
        if unknown:
            raise ValueError(f"Unbekannte Gewichte: {', '.join(sorted(unknown))}")
        for key, value in override.items():
            weights[key] = float(value)
    if any(w < 0 for w in weights.values()):
        raise ValueError("Gewichte dürfen nicht negativ sein.")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Mindestens ein Gewicht muss größer als 0 sein.")
    return {key: w / total for key, w in weights.items()}


def _scale(n: Nutrients, factor: float) -> Nutrients:
    return Nutrients(
        kcal=n.kcal * factor,
        protein_g=n.protein_g * factor,
        fat_g=n.fat_g * factor,
        carb_g=n.carb_g * factor,
        fiber_g=n.fiber_g * factor,
        salt_g=n.salt_g * factor,
        micros={key: value * factor for key, value in n.micros.items()},
    )


def sum_micros(*parts: Mapping[str, float]) -> dict[str, float]:
    """Addiert Mikronährstoff-Mengen schlüsselweise."""
    result: dict[str, float] = {}
    for part in parts:
        for key, value in part.items():
            result[key] = result.get(key, 0.0) + value
    return result


def add_nutrients(*items: Nutrients) -> Nutrients:
    """Summe beliebig vieler Nährwerte (inkl. Mikros)."""
    return Nutrients(
        kcal=sum(i.kcal for i in items),
        protein_g=sum(i.protein_g for i in items),
        fat_g=sum(i.fat_g for i in items),
        carb_g=sum(i.carb_g for i in items),
        fiber_g=sum(i.fiber_g for i in items),
        salt_g=sum(i.salt_g for i in items),
        micros=sum_micros(*(i.micros for i in items)),
    )


# ---------------------------------------------------------------------------
# Skalierung und Summen
# ---------------------------------------------------------------------------


def scale_nutrients(per100: NutrientsPer100, grams: float) -> Nutrients:
    """Rechnet Werte je 100 g auf eine Menge um. Unbekannte Werte (None) zählen als 0.

    Fehlt `salt_g`, aber `micros["sodium_mg"]` liegt vor, wird das Salz aus dem Natrium berechnet
    (Salz = Natrium × 2,5).
    """
    factor = grams / 100.0
    salt_100 = per100.salt_g
    if salt_100 is None:
        sodium_mg = per100.micros.get("sodium_mg")
        salt_100 = sodium_mg * SALT_PER_SODIUM / 1000.0 if sodium_mg is not None else 0.0
    return Nutrients(
        kcal=(per100.kcal or 0.0) * factor,
        protein_g=(per100.protein_g or 0.0) * factor,
        fat_g=(per100.fat_g or 0.0) * factor,
        carb_g=(per100.carb_g or 0.0) * factor,
        fiber_g=(per100.fiber_g or 0.0) * factor,
        salt_g=salt_100 * factor,
        micros={key: value * factor for key, value in per100.micros.items()},
    )


def recipe_nutrition(lines: Sequence[LineNutrition], servings: float) -> RecipeNutrition:
    """Summe und Wert je Portion über alle Zutatenzeilen.

    - Optionale Zeilen zählen weder in die Summe noch als fehlend.
    - Eine Zeile geht in Summe und Gewicht ein, wenn sie Menge und zugeordnete Zutat hat. Fehlt
      ihr kcal-Wert, bleibt sie trotzdem in der Summe (übrige Werte), gilt aber als fehlend.
    - `coverage` = Anteil der nicht optionalen Zeilen mit Menge, Zutat und bekanntem kcal-Wert
      (leere Liste → 0,0).
    """
    if servings <= 0:
        raise ValueError("Die Portionszahl muss größer als 0 sein.")
    parts: list[Nutrients] = []
    weight = 0.0
    relevant = 0
    covered = 0
    missing: list[str] = []
    for line in lines:
        if line.optional:
            continue
        relevant += 1
        if line.grams is None or line.per100 is None:
            missing.append(line.label)
            continue
        if line.grams < 0:
            raise ValueError(f"Negative Menge bei Zeile {line.label!r}.")
        parts.append(scale_nutrients(line.per100, line.grams))
        weight += line.grams
        if line.per100.kcal is None:
            missing.append(line.label)
        else:
            covered += 1
    total = add_nutrients(*parts)
    per_serving = _scale(total, 1.0 / servings)
    density = total.kcal / weight * 100.0 if weight > 0 else None
    return RecipeNutrition(
        total=total,
        per_serving=per_serving,
        servings=servings,
        total_weight_g=weight,
        serving_weight_g=weight / servings,
        energy_density_kcal_per_100g=density,
        coverage=covered / relevant if relevant else 0.0,
        missing=missing,
    )


def component_meal(choices: Sequence[ComponentChoice]) -> RecipeNutrition:
    """Baukasten-Mahlzeit (z. B. Frühstück) aus Komponenten und Mengen; Ausgabe wie bei einem Rezept.

    `missing` enthält die Komponenten ohne kcal-Wert.
    """
    lines = [LineNutrition(label=c.label, grams=c.grams, per100=c.per100) for c in choices]
    return recipe_nutrition(lines, 1.0)


# ---------------------------------------------------------------------------
# Sättigung
# ---------------------------------------------------------------------------


def satiety_score(
    nutrition: RecipeNutrition, *, warm: bool = False, weights: dict[str, float] | None = None
) -> SatietyScore:
    """Sättigungsscore 0–100 (höher = sättigender) mit Teilwerten 0–1.

    Teile: `density` (niedrige Energiedichte ist gut; unbekannt → 0,5), `volume` (Gewicht der Portion),
    `protein` und `fiber` je 100 kcal der Portion, `warm` (1 oder 0). Schwellen und Standardgewichte
    stehen in `defaults.SATIETY_*`. `weights` überschreibt einzelne Standardgewichte; danach werden
    alle Gewichte auf Summe 1 normalisiert.
    """
    per = nutrition.per_serving
    density_100 = nutrition.energy_density_kcal_per_100g
    parts = {
        "density": 0.5 if density_100 is None else _linear(density_100, *defaults.SATIETY_DENSITY_KCAL_100G),
        "volume": _linear(nutrition.serving_weight_g, *defaults.SATIETY_VOLUME_G),
        "protein": _linear(
            per.protein_g / per.kcal * 100.0 if per.kcal > 0 else 0.0,
            *defaults.SATIETY_PROTEIN_G_PER_100KCAL,
        ),
        "fiber": _linear(
            per.fiber_g / per.kcal * 100.0 if per.kcal > 0 else 0.0,
            *defaults.SATIETY_FIBER_G_PER_100KCAL,
        ),
        "warm": 1.0 if warm else 0.0,
    }
    w = _merged_weights(defaults.SATIETY_WEIGHTS, weights, _SATIETY_PARTS)
    score = sum(w[key] * parts[key] for key in _SATIETY_PARTS) * 100.0
    return SatietyScore(score=score, parts=parts)


# ---------------------------------------------------------------------------
# Passung ins Slot-Ziel
# ---------------------------------------------------------------------------


def _deviation_pct(actual: float, target: float) -> float:
    if target > 0:
        return (actual - target) / target * 100.0
    return 0.0 if actual <= 0 else 100.0


def _macro_part(macro: str, deviation: float) -> float:
    """Teilwert 0–1: voll bis `FIT_TOLERANCE_PCT`, dann linear fallend auf 0 bei `FIT_ZERO_PCT`."""
    size = abs(deviation)
    if macro == "protein" and deviation < 0:
        size *= _PROTEIN_UNDER_PENALTY
    tolerance, zero = defaults.FIT_TOLERANCE_PCT, defaults.FIT_ZERO_PCT
    if size <= tolerance:
        return 1.0
    return max(0.0, 1.0 - (size - tolerance) / (zero - tolerance))


def fit_to_target(
    per_serving: Nutrients,
    serving_weight_g: float,
    target: SlotTarget,
    *,
    min_factor: float = defaults.FIT_MIN_FACTOR,
    max_factor: float = defaults.FIT_MAX_FACTOR,
    weights: dict[str, float] | None = None,
) -> SlotFit:
    """Bewertet, wie gut eine Portion ins Ziel einer Mahlzeit passt (docs/PHASE2.md, Abschnitt 6).

    Der Portionsfaktor (Ziel-kcal / kcal je Portion) wird auf [min_factor, max_factor] begrenzt.
    Abweichungen je Makro in % vom Ziel; `fit_score` (0–100) gewichtet die Teilwerte (Standard:
    `defaults.FIT_MACRO_WEIGHTS`, Schlüssel kcal/protein/fat/carb). Protein unter Ziel wiegt bei
    der Abweichung 1,5-fach. Bei kcal ≤ 0 je Portion oder Ziel-kcal ≤ 0 bleibt der Faktor 1.
    """
    if min_factor <= 0 or max_factor < min_factor:
        raise ValueError("Ungültige Grenzen für den Portionsfaktor.")
    notes: list[str] = []
    size_notes_ok = True
    if per_serving.kcal <= 0:
        unclamped = 1.0
        size_notes_ok = False
        notes.append("Für diese Portion sind keine Kalorien bekannt; der Faktor bleibt bei 1.")
    elif target.kcal <= 0:
        unclamped = 1.0
        size_notes_ok = False
        notes.append("Für diese Mahlzeit gibt es kein Kalorienziel; der Faktor bleibt bei 1.")
    else:
        unclamped = target.kcal / per_serving.kcal
    factor = min(max_factor, max(min_factor, unclamped))
    scaled = _scale(per_serving, factor)

    if size_notes_ok:
        if unclamped > _SIZE_LARGE:
            notes.append(f"Portion wäre {_fmt(unclamped)}-fach: sehr groß")
        elif unclamped < _SIZE_SMALL:
            notes.append(f"Portion wäre {_fmt(unclamped)}-fach: sehr klein")
        if unclamped > max_factor:
            notes.append(f"Ziel-kcal wird mit maximal {_fmt(max_factor)}-facher Portion nicht erreicht")
        elif unclamped < min_factor:
            notes.append(f"Ziel-kcal wird schon mit {_fmt(min_factor)}-facher Portion überschritten")

    actual = {
        "kcal": scaled.kcal,
        "protein": scaled.protein_g,
        "fat": scaled.fat_g,
        "carb": scaled.carb_g,
    }
    goal = {"kcal": target.kcal, "protein": target.protein_g, "fat": target.fat_g, "carb": target.carb_g}
    deviation = {m: _deviation_pct(actual[m], goal[m]) for m in _MACROS}

    protein_gap = target.protein_g - scaled.protein_g
    if target.protein_g > 0 and round(protein_gap) >= 1:
        notes.append(f"Protein {_fmt(protein_gap, 0)} g unter Ziel")
    for macro in ("fat", "carb"):
        if deviation[macro] > _OVER_TARGET_NOTE_PCT:
            notes.append(f"{_MACRO_LABELS[macro]} deutlich über Ziel (+{_fmt(deviation[macro], 0)} %)")

    w = _merged_weights(defaults.FIT_MACRO_WEIGHTS, weights, _MACROS)
    score = sum(w[m] * _macro_part(m, deviation[m]) for m in _MACROS) * 100.0
    return SlotFit(
        factor=factor,
        unclamped_factor=unclamped,
        grams=serving_weight_g * factor,
        scaled=scaled,
        deviation_pct=deviation,
        fit_score=score,
        notes=notes,
    )
