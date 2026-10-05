"""Gesundheitsdaten lesen: Tageswerte (zusammengeführt oder je Quelle) und Workouts."""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentPerson, Db
from app.calc.types import PersonSettings
from app.models import HealthDaily, Person, PersonSettingsRow, Workout
from app.services.health_view import merged_daily

router = APIRouter(prefix="/me", tags=["Gesundheitsdaten"])

Source = Literal["hae_zip", "apple_health_xml"]
FromDate = Annotated[date | None, Query(alias="from", description="Erster Tag (einschließlich).")]
ToDate = Annotated[date | None, Query(alias="to", description="Letzter Tag (einschließlich).")]

# Workouts verschiedener Quellen, die so nah beieinander starten, gelten als dasselbe Training.
DUPLICATE_WINDOW = timedelta(minutes=10)


class DailyOut(BaseModel):
    """Tageswerte. Einheiten: kg, Prozent 0-100, kcal, Schritte, Schläge/min, ms, Stunden."""

    model_config = ConfigDict(from_attributes=True)

    day: date
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    lean_mass_kg: float | None = None
    active_kcal: float | None = None
    basal_kcal: float | None = None
    steps: float | None = None
    resting_hr: float | None = None
    hrv_ms: float | None = None
    sleep_h: float | None = None


class WorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    start: datetime  # naive Ortszeit
    duration_min: float
    active_kcal: float | None
    avg_hr: float | None
    max_hr: float | None
    distance_km: float | None
    source: str


def source_priority(db: Session, person: Person) -> list[str]:
    """Quellenpriorität aus den gespeicherten Einstellungen der Person (sonst Standard)."""
    row = db.get(PersonSettingsRow, person.id)
    return PersonSettings.model_validate(row.data if row and row.data else {}).source_priority


def check_range(start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Das Startdatum liegt nach dem Enddatum."
        )


def dedupe_workouts(rows: list[Workout], priority: list[str]) -> list[Workout]:
    """Entfernt Dubletten aus verschiedenen Quellen (Start innerhalb von 10 Minuten).

    Es bleibt der Eintrag der Quelle mit der höchsten Priorität. Die Reihenfolge der Eingabe bleibt erhalten.
    """

    def rank(w: Workout) -> int:
        return priority.index(w.source) if w.source in priority else len(priority)

    kept: list[Workout] = []
    for w in sorted(rows, key=lambda w: (rank(w), w.start)):
        if not any(k.source != w.source and abs(k.start - w.start) <= DUPLICATE_WINDOW for k in kept):
            kept.append(w)
    keep_ids = {id(w) for w in kept}
    return [w for w in rows if id(w) in keep_ids]


@router.get(
    "/health/daily",
    response_model=list[DailyOut],
    summary="Tageswerte (aufsteigend nach Datum)",
    description=(
        "Ohne `source`: je Tag aus allen Quellen zusammengeführt, je Feld gewinnt die Quelle mit der "
        "höchsten Priorität aus den Einstellungen (`source_priority`). Mit `source`: nur die Rohzeilen "
        "dieser Quelle."
    ),
)
def get_daily(
    person: CurrentPerson,
    db: Db,
    from_: FromDate = None,
    to: ToDate = None,
    source: Annotated[Source | None, Query(description="Nur diese Quelle (Rohdaten).")] = None,
):
    check_range(from_, to)
    if source is None:
        return merged_daily(db, person.id, source_priority(db, person), from_, to)
    stmt = select(HealthDaily).where(HealthDaily.person_id == person.id, HealthDaily.source == source)
    if from_:
        stmt = stmt.where(HealthDaily.day >= from_)
    if to:
        stmt = stmt.where(HealthDaily.day <= to)
    return list(db.scalars(stmt.order_by(HealthDaily.day)))


@router.get(
    "/workouts",
    response_model=list[WorkoutOut],
    summary="Workouts (neueste zuerst)",
    description="Alle gespeicherten Workouts, auch wenn zwei Quellen dasselbe Training liefern (`source`).",
)
def get_workouts(
    person: CurrentPerson,
    db: Db,
    from_: FromDate = None,
    to: ToDate = None,
    type: Annotated[str | None, Query(description="Nur diese Trainingsart (exakt).")] = None,  # noqa: A002
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
):
    check_range(from_, to)
    stmt = select(Workout).where(Workout.person_id == person.id)
    if from_:
        stmt = stmt.where(Workout.start >= datetime.combine(from_, time.min))
    if to:
        stmt = stmt.where(Workout.start < datetime.combine(to + timedelta(days=1), time.min))
    if type:
        stmt = stmt.where(Workout.type == type)
    return list(db.scalars(stmt.order_by(Workout.start.desc(), Workout.id.desc()).limit(limit)))
