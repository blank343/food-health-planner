"""Sicherheitsgrenzen für Tagesziele und verständliche Warnungen.

Grenzen sind Einstellungen der Person (`PersonSettings`) mit sicheren Standardwerten aus
`defaults.py`. Gewichts- und Körperfettgrenzen sind frei wählbar; auffällige Werte erzeugen nur
Hinweise, keine Blockade.

Vorgehen bei Anpassungen: Das übergebene Tagesziel bleibt die Grundlage (inklusive Tagestyp-Gewicht
aus `weekly_targets`). Ändert sich das Tempo, wird die Energiedifferenz
`(gewünscht - angewendet) x kcal_pro_kg / 7` auf die Energie des Ziels addiert (bei Zunahme
abgezogen). Protein und Fett bleiben in Gramm gleich, die Differenz geht in die Kohlenhydrate
(`macros.compose_day_target`). Das entspricht einer Neuberechnung des Defizits bei gleichem Bedarf,
ohne dass Bedarf oder Ziel erneut übergeben werden müssen.
"""

import math
from dataclasses import dataclass

from app.calc import defaults
from app.calc.energy import bmr_mifflin
from app.calc.macros import KCAL_PER_G_PROTEIN, compose_day_target
from app.calc.types import (
    DayTarget,
    GoalKind,
    PersonProfile,
    PersonSettings,
    SafetyResult,
    Warning,
)

_EPS = 1e-9
_DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class CurrentBody:
    """Aktuelle Körperdaten (geglättetes Gewicht, Körperfett und Magermasse falls bekannt)."""

    weight_kg: float
    body_fat_pct: float | None = None
    lean_mass_kg: float | None = None


def kcal_floor(profile: PersonProfile, limits: PersonSettings, weight_kg: float) -> float:
    """Energie-Untergrenze: Einstellung, sonst max(absolute Grenze je Geschlecht, Faktor x Grundumsatz)."""
    if limits.kcal_floor:
        return limits.kcal_floor
    bmr = bmr_mifflin(weight_kg, profile.height_cm, profile.age_years, profile.sex)
    return max(defaults.KCAL_FLOOR_ABSOLUTE[profile.sex], defaults.KCAL_FLOOR_BMR_FACTOR * bmr)


def max_rate_kg_per_week(limits: PersonSettings, weight_kg: float) -> float:
    """Maximales Tempo in kg/Woche: Einstellung, sonst min(absolute Grenze, Prozent vom Gewicht)."""
    if limits.max_rate_kg_per_week:
        return limits.max_rate_kg_per_week
    return min(defaults.MAX_RATE_KG_PER_WEEK, defaults.MAX_RATE_PCT_BODY_WEIGHT / 100.0 * weight_kg)


def _taper_factor(distance: float, taper_range: float) -> float:
    """1 weit weg von der Grenze, linear bis 0 an der Grenze (und darunter)."""
    if distance <= 0:
        return 0.0
    if taper_range > 0 and distance < taper_range:
        return distance / taper_range
    return 1.0


def _lean_mass(current: CurrentBody) -> float | None:
    if current.lean_mass_kg is not None:
        return current.lean_mass_kg
    if current.body_fat_pct is not None:
        return current.weight_kg * (1.0 - current.body_fat_pct / 100.0)
    return None


def apply_safety_limits(
    target: DayTarget,
    profile: PersonProfile,
    limits: PersonSettings,
    current: CurrentBody,
    *,
    requested_rate_kg_per_week: float | None = None,
    goal_kind: GoalKind = "lose",
) -> SafetyResult:
    """Wendet Sicherheitsgrenzen auf ein Tagesziel an und liefert Warnungen.

    - Tempo (nur wenn `requested_rate_kg_per_week` gegeben; bei Zielen mit Prozentwert vorher mit
      `macros.implied_rate_kg_per_week` bestimmen): begrenzt auf das Maximaltempo; bei "lose"
      zusätzlich linearer Auslauf auf 0, wenn Gewicht (`taper_weight_kg`) oder Körperfett
      (`taper_bf_pct_points`) sich ihrer Grenze nähern. Die strengere Grenze gilt. Bei "maintain"
      wird das Tempo nicht verändert.
    - Energie-Untergrenze: wird bei Unterschreitung angehoben (Warnung "kcal_floor").
    - Protein-Untergrenze (g/kg): wird bei Unterschreitung angehoben, Energie bleibt gleich.
    - Hinweise (blockieren nie): unplausible Gewichtsgrenze, Körperfett unter Richtwert ohne Grenze.

    Rückgabe: `SafetyResult(target, warnings, applied_rate_kg_per_week)`; das angewendete Tempo ist
    None, wenn kein Tempo übergeben wurde.
    """
    warnings: list[Warning] = []
    weight = current.weight_kg
    kpk = limits.kcal_per_kg
    kcal = target.kcal
    protein = target.protein_g
    fat = target.fat_g
    applied: float | None = None

    # 1. Tempo
    if requested_rate_kg_per_week is not None and goal_kind != "maintain":
        requested = abs(requested_rate_kg_per_week)
        applied = requested
        max_rate = max_rate_kg_per_week(limits, weight)
        if applied > max_rate + _EPS:
            applied = max_rate
            warnings.append(
                Warning(
                    "rate_capped",
                    "warn",
                    f"Das gewünschte Tempo von {requested:.2f} kg pro Woche ist zu schnell. "
                    f"Es wurde auf {max_rate:.2f} kg pro Woche begrenzt, damit der Körper nicht "
                    "zu viel Muskulatur und Energie verliert.",
                )
            )
        if goal_kind == "lose":
            applied = _apply_floor_taper(applied, limits, current, warnings)
        if applied < requested - _EPS:
            sign = 1.0 if goal_kind == "lose" else -1.0
            kcal += sign * (requested - applied) * kpk / _DAYS_PER_WEEK

    # 2. Energie-Untergrenze
    floor = math.ceil(kcal_floor(profile, limits, weight))
    if round(kcal) < floor:
        if applied is not None and goal_kind == "lose":
            applied = max(0.0, applied - (floor - kcal) * _DAYS_PER_WEEK / kpk)
        warnings.append(
            Warning(
                "kcal_floor",
                "block",
                f"Das Tagesziel lag unter der Mindestmenge von {floor} kcal und wurde darauf "
                "angehoben. Zu wenig Energie über längere Zeit schadet Muskeln, Hormonen und "
                "Leistungsfähigkeit.",
            )
        )
        kcal = float(floor)

    # 3. Protein-Untergrenze (Energie bleibt gleich, Kohlenhydrate geben nach)
    protein_floor = limits.protein_floor_g_per_kg * weight
    if protein < protein_floor - _EPS and kcal >= KCAL_PER_G_PROTEIN * protein_floor:
        warnings.append(
            Warning(
                "protein_floor",
                "warn",
                f"Das Protein-Ziel lag unter {limits.protein_floor_g_per_kg:.1f} g pro kg Körpergewicht "
                f"und wurde auf {protein_floor:.0f} g angehoben, damit die Muskulatur erhalten bleibt.",
            )
        )
        protein = protein_floor

    result = compose_day_target(kcal, protein, fat, target.day_type)

    # 4. Hinweise
    _add_hints(warnings, profile, limits, current)

    return SafetyResult(target=result, warnings=warnings, applied_rate_kg_per_week=applied)


def _apply_floor_taper(
    rate: float, limits: PersonSettings, current: CurrentBody, warnings: list[Warning]
) -> float:
    """Senkt das Tempo linear auf 0, wenn Gewicht oder Körperfett der Grenze nahe kommen."""
    factors: list[tuple[float, str, str]] = []
    if limits.weight_floor_kg is not None:
        distance = current.weight_kg - limits.weight_floor_kg
        f = _taper_factor(distance, limits.taper_weight_kg)
        factors.append((f, f"Dein Gewicht ({current.weight_kg:.1f} kg)", f"{limits.weight_floor_kg:.1f} kg"))
    if limits.bf_floor_pct is not None and current.body_fat_pct is not None:
        distance = current.body_fat_pct - limits.bf_floor_pct
        f = _taper_factor(distance, limits.taper_bf_pct_points)
        factors.append(
            (f, f"Dein Körperfettanteil ({current.body_fat_pct:.1f} %)", f"{limits.bf_floor_pct:.1f} %")
        )
    if not factors:
        return rate
    factor, subject, limit = min(factors, key=lambda x: x[0])
    if factor >= 1.0:
        return rate
    if factor <= 0.0:
        warnings.append(
            Warning(
                "floor_reached",
                "block",
                f"{subject} hat die Grenze von {limit} erreicht. Das Abnehmtempo ist deshalb 0, "
                "das Tagesziel entspricht dem Erhalt.",
            )
        )
        return 0.0
    warnings.append(
        Warning(
            "rate_tapered",
            "info",
            f"{subject} nähert sich der Grenze von {limit}. Das Abnehmtempo wird deshalb "
            f"schrittweise auf {rate * factor:.2f} kg pro Woche gesenkt.",
        )
    )
    return rate * factor


def _add_hints(
    warnings: list[Warning], profile: PersonProfile, limits: PersonSettings, current: CurrentBody
) -> None:
    """Nicht blockierende Hinweise zu Gewichts- und Körperfettgrenzen."""
    lean = _lean_mass(current)
    floor_w = limits.weight_floor_kg
    if floor_w is not None and lean is not None:
        implied_bf = (floor_w - lean) / floor_w * 100.0
        too_close = floor_w < lean * defaults.IMPLAUSIBLE_FLOOR_LEAN_FACTOR
        if too_close or implied_bf < defaults.IMPLAUSIBLE_BF_PCT:
            warnings.append(
                Warning(
                    "implausible_weight_floor",
                    "warn",
                    f"Deine Gewichtsgrenze von {floor_w:.1f} kg liegt sehr nah an deiner geschätzten "
                    f"Magermasse von {lean:.1f} kg (Körperfett dann nur etwa {max(implied_bf, 0):.0f} %). "
                    "Die Grenze wird trotzdem angewendet; bitte prüfe, ob sie so gewollt ist.",
                )
            )
    if (
        limits.bf_floor_pct is None
        and current.body_fat_pct is not None
        and current.body_fat_pct < defaults.BF_FLOOR_HINT_PCT[profile.sex]
    ):
        hint = defaults.BF_FLOOR_HINT_PCT[profile.sex]
        warnings.append(
            Warning(
                "bf_hint",
                "info",
                f"Dein Körperfettanteil ({current.body_fat_pct:.1f} %) liegt unter dem üblichen "
                f"Richtwert von {hint:.0f} %. Du hast keine Körperfett-Grenze gesetzt; "
                "eine weitere Gewichtsabnahme sollte gut überlegt sein.",
            )
        )
