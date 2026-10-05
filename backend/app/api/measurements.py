"""Manuelle Messwerte: `POST /api/me/health/manual` (Gewicht, Körperfett).

Manuelle Einträge sind eine eigene Quelle (`manual`) und haben in der Standard-Priorität Vorrang vor
Importen. Sinnvoll, wenn die Waage kaum oder nur Platzhalterwerte nach Apple Health schreibt.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentPerson, Db, today_local
from app.models import HealthDaily

router = APIRouter(tags=["Messwerte"])

SOURCE = "manual"


class ManualMeasurementIn(BaseModel):
    day: date | None = Field(default=None, description="Datum, Standard: heute")
    weight_kg: float | None = Field(default=None, ge=30, le=300)
    body_fat_pct: float | None = Field(default=None, ge=2, le=60)
    lean_mass_kg: float | None = Field(default=None, ge=20, le=200)


class ManualMeasurementOut(BaseModel):
    day: date
    weight_kg: float | None
    body_fat_pct: float | None
    lean_mass_kg: float | None


@router.post(
    "/me/health/manual",
    response_model=ManualMeasurementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Gewicht/Körperfett von Hand eintragen",
)
def add_manual_measurement(body: ManualMeasurementIn, person: CurrentPerson, db: Db) -> ManualMeasurementOut:
    if body.weight_kg is None and body.body_fat_pct is None and body.lean_mass_kg is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Bitte mindestens einen Wert angeben."
        )
    day = body.day or today_local()
    if day > today_local():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Das Datum liegt in der Zukunft.")
    row = db.scalar(
        select(HealthDaily).where(
            HealthDaily.person_id == person.id, HealthDaily.day == day, HealthDaily.source == SOURCE
        )
    )
    if row is None:
        row = HealthDaily(person_id=person.id, day=day, source=SOURCE)
        db.add(row)
    for field in ("weight_kg", "body_fat_pct", "lean_mass_kg"):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value)
    db.commit()
    return ManualMeasurementOut(
        day=row.day, weight_kg=row.weight_kg, body_fat_pct=row.body_fat_pct, lean_mass_kg=row.lean_mass_kg
    )
