"""Zielwerte pro Tag: `GET /api/me/targets`."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import CurrentPerson, Db, today_local
from app.services import targets as svc

router = APIRouter(tags=["Ziele berechnen"])


class MacroOut(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float


class TdeeOut(BaseModel):
    tdee_kcal: float
    device_kcal: float | None
    implied_kcal: float | None
    confidence: float
    method: str
    notes: list[str]


class WarningOut(BaseModel):
    code: str
    severity: str
    message: str


class BodyOut(BaseModel):
    weight_kg: float
    weight_date: date
    body_fat_pct: float | None
    lean_mass_kg: float | None
    height_cm: float
    age_years: float


class GoalOut(BaseModel):
    kind: str
    rate_kg_per_week: float | None
    applied_rate_kg_per_week: float | None
    valid_from: date | None


class TargetsOut(BaseModel):
    date: date
    day_type: str
    target: MacroOut
    slots: dict[str, MacroOut]
    shares: dict[str, float]
    tdee: TdeeOut
    body: BodyOut
    goal: GoalOut
    warnings: list[WarningOut]


@router.get("/me/targets", response_model=TargetsOut, summary="Tagesziel inkl. Mahlzeiten-Verteilung")
def get_targets(
    person: CurrentPerson,
    db: Db,
    on: Annotated[date | None, Query(alias="date", description="Stichtag, Standard: heute")] = None,
    shares: Annotated[
        str | None,
        Query(description="Slot-Anteile überschreiben, z. B. `breakfast:1,dinner:0.5`"),
    ] = None,
) -> TargetsOut:
    try:
        r = svc.compute_targets(
            db, person, on or today_local(), svc.parse_shares(shares) if shares else None
        )
    except svc.TargetsUnavailable as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    t = r.target
    return TargetsOut(
        date=r.day,
        day_type=r.day_type,
        target=MacroOut(kcal=t.kcal, protein_g=t.protein_g, fat_g=t.fat_g, carb_g=t.carb_g),
        slots={
            n: MacroOut(kcal=s.kcal, protein_g=s.protein_g, fat_g=s.fat_g, carb_g=s.carb_g)
            for n, s in r.slots.items()
        },
        shares=r.shares,
        tdee=TdeeOut(
            tdee_kcal=round(r.tdee.tdee_kcal, 1),
            device_kcal=None if r.tdee.device_kcal is None else round(r.tdee.device_kcal, 1),
            implied_kcal=None if r.tdee.implied_kcal is None else round(r.tdee.implied_kcal, 1),
            confidence=round(r.tdee.confidence, 2),
            method=r.tdee.method,
            notes=r.tdee.notes,
        ),
        body=BodyOut(
            weight_kg=r.profile.weight_kg,
            weight_date=r.weight_date,
            body_fat_pct=r.profile.body_fat_pct,
            lean_mass_kg=r.profile.lean_mass_kg,
            height_cm=r.profile.height_cm,
            age_years=round(r.profile.age_years, 1),
        ),
        goal=GoalOut(
            kind=r.goal.kind,
            rate_kg_per_week=r.goal.rate_kg_per_week,
            applied_rate_kg_per_week=r.applied_rate_kg_per_week,
            valid_from=r.goal_from,
        ),
        warnings=[WarningOut(code=w.code, severity=w.severity, message=w.message) for w in r.warnings],
    )
