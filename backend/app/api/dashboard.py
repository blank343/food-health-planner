"""Übersicht: Gewicht, Energie, Workouts pro Woche, Datenabdeckung, Labor, letzte Importe."""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentPerson, Db, today_local
from app.api.health_data import dedupe_workouts, source_priority
from app.api.imports import ImportJobOut
from app.api.labs import latest_values, load_reports, report_date
from app.calc import defaults
from app.calc.energy import device_tdee, weight_trend
from app.models import HealthDaily, ImportJob, Workout
from app.services.health_view import day_energy, latest_value, merged_daily, weight_series

router = APIRouter(prefix="/me", tags=["Übersicht"])

WEIGHT_POINTS_DAYS = 90
WORKOUT_WEEKS = 8


class WeightPoint(BaseModel):
    day: date
    kg: float


class WeightOut(BaseModel):
    """Gewicht aus der zusammengeführten Tagesreihe."""

    latest_kg: float | None
    latest_date: date | None
    trend_kg_per_week: float | None  # robuste Steigung der letzten 28 Tage, sonst None
    trend_n_points: int
    points: list[WeightPoint]  # letzte 90 Tage, aufsteigend


class EnergyOut(BaseModel):
    """Mittel über die letzten 28 Tage mit vollständigen Gerätedaten (Ruhe und aktiv)."""

    avg_active_kcal: float | None
    avg_basal_kcal: float | None
    device_tdee_kcal: float | None
    n_days: int
    coverage: float  # 0..1
    last_day: date | None  # letzter Tag mit vollständigen Daten


class WorkoutTypeStat(BaseModel):
    count: int
    minutes: float


class WorkoutWeekOut(BaseModel):
    week_start: date  # Montag
    iso_week: str  # z. B. "2026-W41"
    count: int
    total_minutes: float
    by_type: dict[str, WorkoutTypeStat]


class SourceCoverageOut(BaseModel):
    source: str
    first_day: date
    last_day: date
    days: int


class LabsSummaryOut(BaseModel):
    latest_report_date: date | None
    latest_report_type: str | None
    flagged_count: int  # auffällige (L/H) Werte unter den jüngsten Werten je Analyt
    pending_count: int  # ausstehende Ergebnisse in allen Berichten


class DashboardOut(BaseModel):
    weight: WeightOut
    energy: EnergyOut
    workouts: list[WorkoutWeekOut]  # letzte 8 ISO-Wochen, älteste zuerst, leere Wochen inklusive
    data: list[SourceCoverageOut]
    labs: LabsSummaryOut
    imports: list[ImportJobOut]  # letzte 3


def _weight(rows, today: date) -> WeightOut:
    series = weight_series(rows)
    latest = latest_value(rows, "weight_kg")
    trend = weight_trend(series)
    slope = trend.slope_kg_per_day
    return WeightOut(
        latest_kg=latest[1] if latest else None,
        latest_date=latest[0] if latest else None,
        trend_kg_per_week=round(slope * 7, 2) if slope is not None else None,
        trend_n_points=trend.n_points,
        points=[WeightPoint(day=d, kg=kg) for d, kg in series if (today - d).days < WEIGHT_POINTS_DAYS],
    )


def _energy(rows) -> EnergyOut:
    device = device_tdee(day_energy(rows))
    complete = [r for r in rows if r.basal_kcal is not None and r.active_kcal is not None]
    if not complete:
        return EnergyOut(
            avg_active_kcal=None, avg_basal_kcal=None, device_tdee_kcal=None, n_days=0, coverage=0.0,
            last_day=None,
        )  # fmt: skip
    last = max(r.day for r in complete)
    window = [r for r in complete if (last - r.day).days < defaults.TDEE_WINDOW_DAYS]
    return EnergyOut(
        avg_active_kcal=round(sum(r.active_kcal for r in window) / len(window), 1),
        avg_basal_kcal=round(sum(r.basal_kcal for r in window) / len(window), 1),
        device_tdee_kcal=round(device.kcal, 1) if device.kcal is not None else None,
        n_days=device.n_days,
        coverage=round(device.coverage, 3),
        last_day=last,
    )


def _workout_weeks(db, person, priority: list[str], today: date) -> list[WorkoutWeekOut]:
    this_monday = today - timedelta(days=today.weekday())
    mondays = [this_monday - timedelta(weeks=i) for i in range(WORKOUT_WEEKS - 1, -1, -1)]
    stmt = select(Workout).where(
        Workout.person_id == person.id,
        Workout.start >= datetime.combine(mondays[0], time.min),
        Workout.start < datetime.combine(today + timedelta(days=1), time.min),
    )
    rows = dedupe_workouts(list(db.scalars(stmt)), priority)
    weeks = {m: WorkoutWeekOut(week_start=m, iso_week=_iso(m), count=0, total_minutes=0.0, by_type={})
             for m in mondays}  # fmt: skip
    for w in rows:
        week = weeks[w.start.date() - timedelta(days=w.start.weekday())]
        stat = week.by_type.setdefault(w.type, WorkoutTypeStat(count=0, minutes=0.0))
        stat.count += 1
        stat.minutes = round(stat.minutes + w.duration_min, 1)
        week.count += 1
        week.total_minutes = round(week.total_minutes + w.duration_min, 1)
    return list(weeks.values())


def _iso(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


@router.get(
    "/dashboard",
    response_model=DashboardOut,
    summary="Übersicht",
    description=(
        "Gewicht und Trend, mittlere Energie, Workouts der letzten 8 Wochen, Datenabdeckung je Quelle, "
        "Laborstand und letzte Importe. Ohne Daten sind Werte `null` bzw. Listen leer."
    ),
)
def get_dashboard(person: CurrentPerson, db: Db):
    today = today_local()
    priority = source_priority(db, person)
    rows = merged_daily(db, person.id, priority, end=today)

    coverage = db.execute(
        select(HealthDaily.source, func.min(HealthDaily.day), func.max(HealthDaily.day), func.count())
        .where(HealthDaily.person_id == person.id)
        .group_by(HealthDaily.source)
        .order_by(HealthDaily.source)
    )
    reports = load_reports(db, person)
    pending = sum(1 for r in reports for res in r.results if res.pending)
    flagged = sum(1 for _, res in latest_values(reports) if res.flag in ("L", "H"))
    jobs = db.scalars(
        select(ImportJob).where(ImportJob.person_id == person.id).order_by(ImportJob.id.desc()).limit(3)
    )
    return DashboardOut(
        weight=_weight(rows, today),
        energy=_energy(rows),
        workouts=_workout_weeks(db, person, priority, today),
        data=[SourceCoverageOut(source=s, first_day=a, last_day=b, days=n) for s, a, b, n in coverage],
        labs=LabsSummaryOut(
            latest_report_date=report_date(reports[0]) if reports else None,
            latest_report_type=reports[0].report_type if reports else None,
            flagged_count=flagged,
            pending_count=pending,
        ),
        imports=[ImportJobOut.model_validate(j) for j in jobs],
    )
