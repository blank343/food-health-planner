"""Berechnet das Tagesziel einer Person aus Datenbank, Zielprofil, Trainingsplan und Rechnern."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calc import energy, macros, safety, slots
from app.calc.types import (
    DayTarget,
    DayType,
    GoalSpec,
    PersonProfile,
    PersonSettings,
    SlotTarget,
    TdeeEstimate,
    Warning,
)
from app.models import GoalProfile, Person, PersonSettingsRow, TrainingPlanItem
from app.services import health_view

LOOKBACK_DAYS = 120
STALE_WEIGHT_DAYS = 30
# Ohne Kalibrierung und Gerätedaten: Grundumsatz × Faktor (nur Notfall-Schätzung)
FORMULA_ACTIVITY_FACTOR = 1.5
_INTENSITY_RANK = {"easy": 1, "moderate": 2, "hard": 3}


class TargetsUnavailable(Exception):
    """Zielwerte lassen sich nicht berechnen (deutsche, für Nutzer gedachte Meldung)."""


@dataclass
class TargetsResult:
    day: date
    day_type: DayType
    target: DayTarget
    slots: dict[str, SlotTarget]
    tdee: TdeeEstimate
    profile: PersonProfile
    goal: GoalSpec
    goal_from: date | None
    weight_date: date
    applied_rate_kg_per_week: float | None
    shares: dict[str, float]
    warnings: list[Warning] = field(default_factory=list)


def load_settings(session: Session, person_id: int) -> PersonSettings:
    row = session.get(PersonSettingsRow, person_id)
    return PersonSettings(**(row.data if row and row.data else {}))


def active_goal(session: Session, person_id: int, on: date) -> GoalProfile | None:
    return session.scalars(
        select(GoalProfile)
        .where(GoalProfile.person_id == person_id, GoalProfile.valid_from <= on)
        .order_by(GoalProfile.valid_from.desc(), GoalProfile.id.desc())
        .limit(1)
    ).first()


def week_day_types(session: Session, person_id: int) -> dict[int, DayType]:
    """Belastungstyp je Wochentag (0 = Montag) aus dem Trainingsplan; ohne Einheit: rest."""
    items = session.scalars(
        select(TrainingPlanItem).where(TrainingPlanItem.person_id == person_id, TrainingPlanItem.enabled)
    )
    best: dict[int, str] = {}
    for it in items:
        if _INTENSITY_RANK.get(it.intensity, 0) > _INTENSITY_RANK.get(best.get(it.weekday, ""), 0):
            best[it.weekday] = it.intensity
    return {d: best.get(d, "rest") for d in range(7)}  # type: ignore[misc]


def parse_shares(text: str) -> dict[str, float]:
    """`breakfast:1,dinner:0.5` → {"breakfast": 1.0, "dinner": 0.5}."""
    out: dict[str, float] = {}
    for part in text.split(","):
        if not part.strip():
            continue
        name, _, val = part.partition(":")
        try:
            out[name.strip()] = float(val)
        except ValueError as e:
            raise TargetsUnavailable(f"Ungültige Slot-Angabe „{part.strip()}“.") from e
    if not out or sum(out.values()) <= 0 or any(v < 0 for v in out.values()):
        raise TargetsUnavailable("Die Slot-Anteile müssen positiv sein und eine Summe über 0 ergeben.")
    return out


def compute_targets(
    session: Session, person: Person, on: date, shares: dict[str, float] | None = None
) -> TargetsResult:
    settings = load_settings(session, person.id)
    warnings: list[Warning] = []

    rows = health_view.merged_daily(
        session, person.id, settings.source_priority, start=on - timedelta(days=LOOKBACK_DAYS), end=on
    )
    w = health_view.latest_value(rows, "weight_kg")
    if w is None:
        raise TargetsUnavailable(
            "Es liegt kein Gewicht vor. Bitte zuerst Gesundheitsdaten importieren, damit Ziele berechnet "
            "werden können."
        )
    weight_date, weight = w
    if person.height_cm is None:
        raise TargetsUnavailable(
            "Die Körpergröße fehlt. Bitte im Profil eintragen oder Gesundheitsdaten importieren."
        )

    bf = health_view.latest_value(rows, "body_fat_pct")
    lm = health_view.latest_value(rows, "lean_mass_kg")
    body_fat = bf[1] if bf else None
    lean = lm[1] if lm else (weight * (1 - body_fat / 100) if body_fat is not None else None)
    profile = PersonProfile(
        sex=person.sex,  # type: ignore[arg-type]
        age_years=health_view.age_years(person.birth_date, on),
        height_cm=person.height_cm,
        weight_kg=weight,
        body_fat_pct=body_fat,
        lean_mass_kg=lean,
    )
    age_days = (on - weight_date).days
    if age_days > STALE_WEIGHT_DAYS:
        warnings.append(
            Warning(
                "stale_weight", "warn",
                f"Das letzte Gewicht ist {age_days} Tage alt. Die Ziele beruhen auf diesem Wert, "
                "neue Messwerte machen sie genauer.",
            )
        )  # fmt: skip

    goal_row = active_goal(session, person.id, on)
    if goal_row is None:
        goal = GoalSpec(kind="maintain")
        warnings.append(
            Warning("no_goal", "info", "Es ist noch kein Ziel hinterlegt. Es wird das Gewicht gehalten.")
        )
    else:
        goal = GoalSpec(
            kind=goal_row.kind,  # type: ignore[arg-type]
            rate_kg_per_week=goal_row.rate_kg_per_week,
            kcal_modifier_pct=goal_row.kcal_modifier_pct,
            protein_g_per_kg=goal_row.protein_g_per_kg,
            fat_pct=goal_row.fat_pct,
        )

    # Energiebedarf: Gerätedaten, kalibriert am Gewichtstrend (wenn Zufuhr bekannt)
    device = energy.device_tdee(health_view.day_energy(rows))
    trend = energy.weight_trend(health_view.weight_series(rows))
    if settings.use_katch_mcardle and lean is not None:
        bmr = energy.bmr_katch_mcardle(lean)
    else:
        bmr = energy.bmr_mifflin(weight, profile.height_cm, profile.age_years, profile.sex)
    est = energy.calibrate_tdee(
        device,
        trend,
        settings.reported_intake_kcal if settings.tdee_calibration else None,
        kcal_per_kg=settings.kcal_per_kg,
        formula_kcal=bmr * FORMULA_ACTIVITY_FACTOR,
    )
    if est.method == "formula":
        warnings.append(
            Warning(
                "tdee_formula", "warn",
                "Es liegen keine Energiedaten aus der Uhr vor. Der Energiebedarf ist nur grob geschätzt.",
            )
        )  # fmt: skip

    # Tagesziel (Wochenenergie nach Belastung verteilt), danach Sicherheitsgrenzen
    types = week_day_types(session, person.id)
    week = macros.weekly_targets(profile, goal, est.tdee_kcal, settings, types)
    base = week[on.weekday()]
    requested = None
    if goal.kind in ("lose", "gain"):
        requested = (
            goal.rate_kg_per_week
            if goal.rate_kg_per_week is not None
            else macros.implied_rate_kg_per_week(goal, est.tdee_kcal, settings.kcal_per_kg)
        )
    safe = safety.apply_safety_limits(
        base,
        profile,
        settings,
        safety.CurrentBody(weight, body_fat, lean),
        requested_rate_kg_per_week=requested,
        goal_kind=goal.kind,
    )
    warnings.extend(safe.warnings)

    # Verteilung auf Mahlzeiten (Wochenende kann abweichen)
    if shares is None:
        weekend = on.weekday() >= 5 and settings.slot_shares_weekend is not None
        shares = settings.slot_shares_weekend if weekend else settings.slot_shares
    slot_targets = slots.distribute_to_slots(safe.target, shares)
    for name, st in slot_targets.items():
        if shares.get(name, 0) > 0:
            for w_ in slots.single_meal_check(st, settings):
                warnings.append(Warning(w_.code, w_.severity, f"{_slot_label(name)}: {w_.message}"))

    return TargetsResult(
        day=on,
        day_type=types[on.weekday()],
        target=safe.target,
        slots=slot_targets,
        tdee=est,
        profile=profile,
        goal=goal,
        goal_from=goal_row.valid_from if goal_row else None,
        weight_date=weight_date,
        applied_rate_kg_per_week=safe.applied_rate_kg_per_week,
        shares=shares,
        warnings=warnings,
    )


def _slot_label(name: str) -> str:
    return {"breakfast": "Frühstück", "lunch": "Mittagessen", "dinner": "Abendessen", "snack": "Snack"}.get(
        name, name
    )
