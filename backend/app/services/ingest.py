"""Schreibt Importergebnisse in die Datenbank (idempotent) und führt Import-Jobs aus."""

import logging
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.importers.types import HealthImport, LabReport
from app.models import HealthDaily, ImportJob, LabResult, Person, Workout
from app.models import LabReport as LabReportRow

log = logging.getLogger(__name__)

DAILY_FIELDS = (
    "weight_kg", "body_fat_pct", "lean_mass_kg", "active_kcal", "basal_kcal",
    "steps", "resting_hr", "hrv_ms", "sleep_h",
)  # fmt: skip
WORKOUT_FIELDS = ("duration_min", "active_kcal", "avg_hr", "max_hr", "distance_km")


def jsonable(value):
    """Macht Statistiken JSON-tauglich (Datum/Zeit → ISO-Text), auch verschachtelt."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(v) for v in value]
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _clip(value: str | None, column) -> str | None:
    """Kürzt Text auf die Spaltenlänge (Postgres lehnt zu lange Werte ab, SQLite nicht)."""
    if value is None:
        return None
    length = column.property.columns[0].type.length
    return value[:length] if length and len(value) > length else value


class ImportRejected(Exception):
    """Import wird abgelehnt (deutsche, für Nutzer gedachte Meldung)."""


# ---------------------------------------------------------------- Gesundheitsdaten
def ingest_health(session: Session, person: Person, result: HealthImport) -> dict:
    """Upsert von Tageswerten und Workouts. Mehrfaches Importieren ändert nichts."""
    stats = {"daily_new": 0, "daily_updated": 0, "workout_new": 0, "workout_updated": 0}

    existing_daily = {
        d.day: d
        for d in session.scalars(
            select(HealthDaily).where(HealthDaily.person_id == person.id, HealthDaily.source == result.source)
        )
    }
    for row in result.daily:
        values = {f: getattr(row, f) for f in DAILY_FIELDS if getattr(row, f) is not None}
        if not values:
            continue
        obj = existing_daily.get(row.day)
        if obj is None:
            obj = HealthDaily(person_id=person.id, day=row.day, source=result.source, **values)
            session.add(obj)
            existing_daily[row.day] = obj
            stats["daily_new"] += 1
        else:
            changed = False
            for f, v in values.items():
                if getattr(obj, f) != v:
                    setattr(obj, f, v)
                    changed = True
            stats["daily_updated"] += int(changed)

    existing_workouts = {
        (w.start, w.type): w
        for w in session.scalars(
            select(Workout).where(Workout.person_id == person.id, Workout.source == result.source)
        )
    }
    for w in result.workouts:
        obj = existing_workouts.get((w.start, _clip(w.type, Workout.type)))
        if obj is None:
            obj = Workout(
                person_id=person.id, type=_clip(w.type, Workout.type), start=w.start, source=result.source,
                **{f: getattr(w, f) for f in WORKOUT_FIELDS},
            )  # fmt: skip
            session.add(obj)
            existing_workouts[(w.start, obj.type)] = obj
            stats["workout_new"] += 1
        else:
            changed = False
            for f in WORKOUT_FIELDS:
                v = getattr(w, f)
                if v is not None and getattr(obj, f) != v:
                    setattr(obj, f, v)
                    changed = True
            stats["workout_updated"] += int(changed)

    # Profil ergänzen, nie überschreiben
    height = result.profile.get("height_cm")
    if person.height_cm is None and isinstance(height, int | float):
        person.height_cm = float(height)
        stats["height_set"] = True

    w = result.weight_report
    stats["weight_raw"] = w.raw
    stats["weight_kept"] = w.kept
    stats["weight_placeholders_removed"] = len(w.placeholders)
    stats["weight_outliers_removed"] = len(w.outliers)
    stats["weight_out_of_range"] = w.out_of_range
    if result.daily:
        stats["date_from"] = min(r.day for r in result.daily).isoformat()
        stats["date_to"] = max(r.day for r in result.daily).isoformat()
    stats["importer"] = jsonable(result.stats)
    session.flush()
    return stats


# ---------------------------------------------------------------- Laborbefunde
def ingest_lab_report(session: Session, person: Person, report: LabReport, filename: str | None) -> dict:
    """Speichert einen Laborbefund. Teilbefunde werden bei Nachlieferung ergänzt.

    Der Patientenname wird **nicht** gespeichert. Das Geburtsdatum des Berichts muss zur Person passen.
    """
    if report.birth_date is None:
        raise ImportRejected("Im Befund wurde kein Geburtsdatum gefunden. Zuordnung nicht möglich.")
    if report.birth_date != person.birth_date:
        raise ImportRejected(
            "Das Geburtsdatum im Befund passt nicht zu deinem Profil. "
            "Der Befund wurde nicht gespeichert (gehört er zu einer anderen Person?)."
        )
    if not report.results:
        raise ImportRejected("Im Befund wurden keine Laborwerte erkannt.")

    row = None
    if report.order_no:
        row = session.scalar(
            select(LabReportRow).where(
                LabReportRow.person_id == person.id,
                LabReportRow.order_no == _clip(report.order_no, LabReportRow.order_no),
            )
        )
    stats = {"report_new": 0, "report_updated": 0, "results_new": 0, "results_updated": 0, "pending": 0}
    if row is None:
        row = LabReportRow(
            person_id=person.id, order_no=_clip(report.order_no, LabReportRow.order_no),
            report_type=_clip(report.report_type, LabReportRow.report_type),
            lab_name=_clip(report.lab_name, LabReportRow.lab_name),
            sample_datetime=report.sample_datetime,
            source_filename=_clip(filename, LabReportRow.source_filename),
        )  # fmt: skip
        session.add(row)
        session.flush()
        stats["report_new"] = 1
    else:
        row.report_type = _clip(report.report_type, LabReportRow.report_type)
        row.source_filename = _clip(filename, LabReportRow.source_filename) or row.source_filename
        row.lab_name = _clip(report.lab_name, LabReportRow.lab_name) or row.lab_name
        row.sample_datetime = report.sample_datetime or row.sample_datetime
        stats["report_updated"] = 1

    existing = {(r.analyte, r.unit): r for r in row.results}
    for r in report.results:
        analyte = _clip(r.analyte, LabResult.analyte)
        unit = _clip(r.unit, LabResult.unit)
        cur = existing.get((analyte, unit))
        fields = dict(
            value=r.value, value_op=_clip(r.value_op, LabResult.value_op), flag=_clip(r.flag, LabResult.flag),
            ref_low=r.ref_low, ref_high=r.ref_high, ref_op=_clip(r.ref_op, LabResult.ref_op),
            pending=r.pending, method=_clip(r.method, LabResult.method),
            material=_clip(r.material, LabResult.material),
        )  # fmt: skip
        if cur is None:
            row.results.append(LabResult(analyte=analyte, unit=unit, **fields))
            existing[(analyte, unit)] = row.results[-1]
            stats["results_new"] += 1
        elif r.pending and not cur.pending:
            continue  # ein vorhandener Wert wird nie durch „folgt“ ersetzt
        else:
            changed = any(getattr(cur, k) != v for k, v in fields.items())
            for k, v in fields.items():
                setattr(cur, k, v)
            stats["results_updated"] += int(changed)
        stats["pending"] += int(r.pending)
    session.flush()
    stats["report_id"] = row.id
    stats["results_total"] = len(row.results)
    return stats


# ---------------------------------------------------------------- Import-Jobs
def create_job(session: Session, person: Person, kind: str, filename: str | None) -> ImportJob:
    job = ImportJob(person_id=person.id, kind=kind, filename=filename, status="queued")
    session.add(job)
    session.commit()
    return job


def run_import_job(
    session_factory: sessionmaker[Session],
    job_id: int,
    path: Path,
    *,
    delete_file: bool = True,
    importers: dict[str, Callable] | None = None,
) -> None:
    """Führt einen Import im Hintergrund aus. Eigene Session, schreibt Status und Statistik in den Job.

    `importers` erlaubt Tests, die Importer zu ersetzen (kind → Funktion(path, progress)).
    """
    if importers is None:
        from app.importers.apple_health import import_apple_health
        from app.importers.hae import import_hae
        from app.importers.lab_pdf import import_lab_pdf

        importers = {
            "hae": import_hae,
            "apple_health": import_apple_health,
            "labs": lambda p, progress=None: import_lab_pdf(p),
        }

    started = time.monotonic()
    with session_factory() as session:
        job = session.get(ImportJob, job_id)
        if job is None:
            return
        job.status, job.started_at = "running", datetime.now()
        session.commit()

        def progress(fraction: float, message: str) -> None:
            job.progress, job.message = max(0.0, min(1.0, fraction)), message[:200]
            session.commit()

        try:
            person = session.get(Person, job.person_id)
            result = importers[job.kind](path, progress)
            if isinstance(result, LabReport):
                stats = ingest_lab_report(session, person, result, job.filename)
            else:
                stats = ingest_health(session, person, result)
            job.status, job.progress, job.message = "done", 1.0, "Import abgeschlossen"
            job.stats = {**stats, "seconds": round(time.monotonic() - started, 1)}
        except ImportRejected as e:
            session.rollback()
            job.status, job.error = "failed", str(e)
        except Exception:  # noqa: BLE001  (Hintergrund-Job: Fehler in den Job schreiben, nicht abstürzen)
            session.rollback()
            log.exception("Import-Job %s fehlgeschlagen", job_id)
            job.status = "failed"
            job.error = "Der Import ist fehlgeschlagen. Die Datei konnte nicht gelesen werden."
        finally:
            job.finished_at = datetime.now()
            session.commit()
            if delete_file:
                path.unlink(missing_ok=True)
