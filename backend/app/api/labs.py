"""Laborbefunde lesen. Patientennamen werden nie gespeichert und daher nie ausgegeben."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentPerson, Db, get_owned_or_404
from app.models import LabReport, LabResult, Person

router = APIRouter(prefix="/me/labs", tags=["Laborwerte"])


class LabResultOut(BaseModel):
    """Ein Laborwert. `value_op` ("<" oder ">") gilt für den Messwert, `ref_op` für einseitige Referenzen."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    analyte: str
    unit: str
    value: float | None
    value_op: str | None
    flag: str | None  # "L" (niedrig) | "H" (hoch)
    ref_low: float | None
    ref_high: float | None
    ref_op: str | None
    pending: bool  # Wert „folgt“ (Teilbefund)
    method: str | None
    material: str | None


class LabReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str | None
    lab_name: str | None
    report_type: str  # Endbefund | Teilbefund | ?
    sample_datetime: datetime | None
    source_filename: str | None
    created_at: datetime | None
    results: list[LabResultOut]


class LatestLabValueOut(BaseModel):
    """Jüngster vorhandener Wert eines Analyten über alle Berichte."""

    analyte: str
    unit: str
    value: float | None
    value_op: str | None
    flag: str | None
    ref_low: float | None
    ref_high: float | None
    ref_op: str | None
    report_id: int
    report_date: date | None  # Probenahme, sonst Importdatum


def report_date(report: LabReport) -> date | None:
    stamp = report.sample_datetime or report.created_at
    return stamp.date() if stamp else None


def _report_key(report: LabReport) -> tuple[datetime, int]:
    return (report.sample_datetime or report.created_at or datetime.min, report.id)


def load_reports(db: Session, person: Person) -> list[LabReport]:
    """Alle Berichte der Person mit Ergebnissen, neueste zuerst."""
    stmt = select(LabReport).where(LabReport.person_id == person.id).options(selectinload(LabReport.results))
    return sorted(db.scalars(stmt), key=_report_key, reverse=True)


def latest_values(reports: list[LabReport]) -> list[tuple[LabReport, LabResult]]:
    """Je Analyt und Einheit der jüngste Wert, der nicht aussteht. `reports` neueste zuerst.

    Analyte mit mehreren Einheiten (z. B. HbA1c in % und mmol/mol, Differentialblutbild absolut und
    in %) bleiben getrennt erhalten. Sortiert nach Analyt, dann Einheit.
    """
    seen: dict[tuple[str, str], tuple[LabReport, LabResult]] = {}
    for report in reports:
        for res in report.results:
            if not res.pending and (res.analyte, res.unit) not in seen:
                seen[(res.analyte, res.unit)] = (report, res)
    return [seen[k] for k in sorted(seen, key=lambda k: (k[0].casefold(), k[1]))]


def _is_flagged(res: LabResult) -> bool:
    return res.flag in ("L", "H")


@router.get(
    "",
    response_model=list[LabReportOut],
    summary="Laborberichte mit Ergebnissen (neueste zuerst)",
    description=(
        "Mit `flagged=true` nur Ergebnisse mit Kennzeichen L/H, mit `pending=true` nur ausstehende. "
        "Werden beide gesetzt, zählt, was mindestens eines davon erfüllt. Berichte ohne passende "
        "Ergebnisse entfallen."
    ),
)
def list_labs(
    person: CurrentPerson,
    db: Db,
    flagged: Annotated[bool, Query(description="Nur auffällige Werte (L/H).")] = False,
    pending: Annotated[bool, Query(description="Nur ausstehende Werte („folgt“).")] = False,
):
    reports = load_reports(db, person)
    if not (flagged or pending):
        return reports
    out = []
    for report in reports:
        hits = [r for r in report.results if (flagged and _is_flagged(r)) or (pending and r.pending)]
        if hits:
            out.append(LabReportOut.model_validate(report).model_copy(update={"results": hits}))
    return out


# Vor `/{report_id}` registrieren, sonst würde "latest" als Berichts-ID gelesen.
@router.get(
    "/latest",
    response_model=list[LatestLabValueOut],
    summary="Jüngster Wert je Analyt",
    description="Je Analyt der neueste nicht ausstehende Wert über alle Berichte, mit Datum und Referenz.",
)
def latest_labs(person: CurrentPerson, db: Db):
    return [
        LatestLabValueOut(
            analyte=res.analyte,
            unit=res.unit,
            value=res.value,
            value_op=res.value_op,
            flag=res.flag,
            ref_low=res.ref_low,
            ref_high=res.ref_high,
            ref_op=res.ref_op,
            report_id=report.id,
            report_date=report_date(report),
        )  # fmt: skip
        for report, res in latest_values(load_reports(db, person))
    ]


@router.get("/{report_id}", response_model=LabReportOut, summary="Ein Laborbericht")
def get_lab(report_id: int, person: CurrentPerson, db: Db):
    return get_owned_or_404(db, LabReport, report_id, person)
