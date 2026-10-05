"""Gemeinsame Sicht auf die Gesundheitsdaten einer Person.

Mehrere Quellen (Apple-Health-Export, Health Auto Export) können denselben Tag liefern. Je Feld
gewinnt die Quelle mit der höchsten Priorität (`PersonSettings.source_priority`); fehlt das Feld dort,
wird es aus der nächsten Quelle ergänzt.
"""

from dataclasses import fields
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calc.types import DayEnergy
from app.importers.types import DailyRow
from app.models import HealthDaily

_VALUE_FIELDS = [f.name for f in fields(DailyRow) if f.name != "day"]


def age_years(birth_date: date, on: date) -> float:
    """Alter in Jahren (mit Nachkommastellen) am Stichtag."""
    return (on - birth_date).days / 365.2425


def _rank(source: str, priority: list[str]) -> tuple[int, str]:
    return (priority.index(source), source) if source in priority else (len(priority), source)


def merged_daily(
    session: Session,
    person_id: int,
    priority: list[str],
    start: date | None = None,
    end: date | None = None,
) -> list[DailyRow]:
    """Tageswerte, je Tag aus allen Quellen zusammengeführt, aufsteigend nach Datum."""
    stmt = select(HealthDaily).where(HealthDaily.person_id == person_id)
    if start:
        stmt = stmt.where(HealthDaily.day >= start)
    if end:
        stmt = stmt.where(HealthDaily.day <= end)
    by_day: dict[date, list[HealthDaily]] = {}
    for row in session.scalars(stmt):
        by_day.setdefault(row.day, []).append(row)

    merged: list[DailyRow] = []
    for day in sorted(by_day):
        rows = sorted(by_day[day], key=lambda r: _rank(r.source, priority))
        out = DailyRow(day=day)
        for name in _VALUE_FIELDS:
            for r in rows:
                v = getattr(r, name)
                if v is not None:
                    setattr(out, name, v)
                    break
        merged.append(out)
    return merged


def latest_value(rows: list[DailyRow], field: str) -> tuple[date, float] | None:
    """Jüngster vorhandener Wert eines Feldes."""
    for r in reversed(rows):
        v = getattr(r, field)
        if v is not None:
            return r.day, v
    return None


def weight_series(rows: list[DailyRow]) -> list[tuple[date, float]]:
    return [(r.day, r.weight_kg) for r in rows if r.weight_kg is not None]


def day_energy(rows: list[DailyRow]) -> list[DayEnergy]:
    return [DayEnergy(day=r.day, basal_kcal=r.basal_kcal, active_kcal=r.active_kcal) for r in rows]
