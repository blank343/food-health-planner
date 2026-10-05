from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.importers.types import (
    DailyRow,
    HealthImport,
    LabReport,
    LabResultRow,
    WeightCleanReport,
    WorkoutRow,
)
from app.models import HealthDaily, ImportJob, Person, Workout
from app.models import LabReport as LabReportRow
from app.services.ingest import (
    ImportRejected,
    create_job,
    ingest_health,
    ingest_lab_report,
    run_import_job,
)


@pytest.fixture
def person(session):
    p = Person(name="Test A", sex="m", birth_date=date(1990, 1, 1))
    session.add(p)
    session.commit()
    return p


def _health(weight=80.0, source="hae_zip", height=None):
    return HealthImport(
        source=source,
        daily=[
            DailyRow(day=date(2026, 1, 1), weight_kg=weight, active_kcal=700, basal_kcal=2000, steps=9000),
            DailyRow(day=date(2026, 1, 2), steps=5000),
            DailyRow(day=date(2026, 1, 3)),  # leer: wird übersprungen
        ],
        workouts=[WorkoutRow(type="Running", start=datetime(2026, 1, 1, 7, 0), duration_min=40, avg_hr=150)],
        profile={"height_cm": height} if height else {},
        weight_report=WeightCleanReport(raw=3, kept=1, placeholders=[81.0]),
    )


def test_health_ingest_is_idempotent(session, person):
    s1 = ingest_health(session, person, _health())
    session.commit()
    assert (s1["daily_new"], s1["workout_new"]) == (2, 1)
    assert s1["weight_placeholders_removed"] == 1
    s2 = ingest_health(session, person, _health())
    session.commit()
    assert (s2["daily_new"], s2["daily_updated"], s2["workout_new"], s2["workout_updated"]) == (0, 0, 0, 0)
    assert session.query(HealthDaily).count() == 2


def test_health_update_changes_value(session, person):
    ingest_health(session, person, _health(weight=80.0))
    session.commit()
    s = ingest_health(session, person, _health(weight=79.5))
    session.commit()
    assert s["daily_updated"] == 1
    day = session.scalar(select(HealthDaily).where(HealthDaily.day == date(2026, 1, 1)))
    assert day.weight_kg == 79.5


def test_two_sources_same_day_are_kept_separately(session, person):
    ingest_health(session, person, _health(source="hae_zip"))
    ingest_health(session, person, _health(source="apple_health_xml"))
    session.commit()
    assert session.query(HealthDaily).count() == 4
    assert session.query(Workout).count() == 2


def test_height_only_filled_if_missing(session, person):
    ingest_health(session, person, _health(height=181.0))
    assert person.height_cm == 181.0
    ingest_health(session, person, _health(height=170.0))
    assert person.height_cm == 181.0


def _lab(birth=date(1990, 1, 1), pending=True, order="42"):
    results = [
        LabResultRow(
            analyte="CRP", unit="mg/l", value=0.6, ref_high=5.0, ref_op="<", method="TURB", material="S"
        ),
        LabResultRow(analyte="Vitamin D", unit="µg/l", value=None if pending else 55.0, pending=pending),
    ]
    return LabReport(
        report_type="Teilbefund" if pending else "Endbefund",
        lab_name="Testlabor",
        order_no=order,
        sample_datetime=datetime(2026, 1, 5, 9, 0),
        patient_name="Muster Max",
        birth_date=birth,
        results=results,
    )


def test_lab_birth_date_mismatch_rejected(session, person):
    with pytest.raises(ImportRejected, match="Geburtsdatum"):
        ingest_lab_report(session, person, _lab(birth=date(1991, 1, 1)), "x.pdf")
    assert session.query(LabReportRow).count() == 0


def test_lab_missing_birth_date_and_empty_results_rejected(session, person):
    rep = _lab()
    rep.birth_date = None
    with pytest.raises(ImportRejected):
        ingest_lab_report(session, person, rep, None)
    rep = _lab()
    rep.results = []
    with pytest.raises(ImportRejected):
        ingest_lab_report(session, person, rep, None)


def test_lab_partial_then_complete_report(session, person):
    s1 = ingest_lab_report(session, person, _lab(pending=True), "a.pdf")
    session.commit()
    assert s1["report_new"] == 1 and s1["pending"] == 1
    s2 = ingest_lab_report(session, person, _lab(pending=False), "b.pdf")
    session.commit()
    assert s2["report_updated"] == 1
    rep = session.scalar(select(LabReportRow))
    assert rep.report_type == "Endbefund"
    vit = next(r for r in rep.results if r.analyte == "Vitamin D")
    assert vit.value == 55.0 and vit.pending is False
    assert len(rep.results) == 2  # keine Duplikate


def test_lab_value_never_replaced_by_pending(session, person):
    ingest_lab_report(session, person, _lab(pending=False), "a.pdf")
    session.commit()
    ingest_lab_report(session, person, _lab(pending=True), "b.pdf")
    session.commit()
    rep = session.scalar(select(LabReportRow))
    vit = next(r for r in rep.results if r.analyte == "Vitamin D")
    assert vit.value == 55.0 and vit.pending is False


def test_patient_name_is_not_stored(session, person):
    ingest_lab_report(session, person, _lab(), "a.pdf")
    session.commit()
    cols = {c.name for c in LabReportRow.__table__.columns}
    assert not any("patient" in c or c == "name" for c in cols)


# ---------------------------------------------------------------- Jobs
def _factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_job_success_updates_status_and_deletes_file(engine, session, person, tmp_path):
    f = tmp_path / "up.zip"
    f.write_text("x")
    job = create_job(session, person, "hae", "up.zip")

    def fake(path, progress=None):
        progress(0.5, "halb")
        return _health()

    run_import_job(_factory(engine), job.id, f, importers={"hae": fake})
    with _factory(engine)() as s:
        j = s.get(ImportJob, job.id)
        assert j.status == "done" and j.progress == 1.0
        assert j.stats["daily_new"] == 2 and "seconds" in j.stats
        assert j.started_at and j.finished_at
    assert not f.exists()


def test_job_rejected_lab_report_is_failed_with_message(engine, session, person, tmp_path):
    f = tmp_path / "b.pdf"
    f.write_text("x")
    job = create_job(session, person, "labs", "b.pdf")
    run_import_job(
        _factory(engine), job.id, f, importers={"labs": lambda p, progress=None: _lab(birth=date(2000, 1, 1))}
    )
    with _factory(engine)() as s:
        j = s.get(ImportJob, job.id)
        assert j.status == "failed" and "Geburtsdatum" in j.error


def test_job_unexpected_error_is_failed_without_leaking_details(engine, session, person, tmp_path):
    f = tmp_path / "c.zip"
    f.write_text("x")
    job = create_job(session, person, "hae", "c.zip")

    def boom(path, progress=None):
        raise RuntimeError("geheimer interner Pfad C:/x")

    run_import_job(_factory(engine), job.id, f, importers={"hae": boom})
    with _factory(engine)() as s:
        j = s.get(ImportJob, job.id)
        assert j.status == "failed"
        assert "geheim" not in j.error and "fehlgeschlagen" in j.error
    assert not f.exists()


def test_stats_with_dates_are_json_safe(session, person):
    hi = _health()
    hi.stats = {"date_from": date(2026, 1, 1), "files": ["a"], "nested": {"t": datetime(2026, 1, 1, 8, 0)}}
    stats = ingest_health(session, person, hi)
    job = ImportJob(person_id=person.id, kind="hae", stats=stats)
    session.add(job)
    session.commit()  # würde bei date-Objekten im JSON fehlschlagen
    assert session.get(ImportJob, job.id).stats["importer"]["date_from"] == "2026-01-01"
    assert session.get(ImportJob, job.id).stats["importer"]["nested"]["t"] == "2026-01-01T08:00:00"


def test_too_long_texts_are_clipped_to_column_length(session, person):
    """SQLite prüft Längen nicht, Postgres schon: Texte müssen vor dem Speichern gekürzt werden."""
    rep = _lab(pending=False)
    rep.lab_name = "L" * 400
    rep.results[0].analyte = "A" * 300
    rep.results[0].unit = "U" * 80
    rep.results[0].method = "M" * 50
    ingest_lab_report(session, person, rep, "f" * 400)
    session.commit()
    row = session.scalar(select(LabReportRow))
    assert len(row.lab_name) == 120 and len(row.source_filename) == 255
    long_result = next(r for r in row.results if r.analyte.startswith("AAAA"))
    assert len(long_result.analyte) == 120 and len(long_result.unit) == 30 and len(long_result.method) == 20
    # ein zweiter Import mit denselben langen Namen erzeugt keine Duplikate
    ingest_lab_report(session, person, rep, "f" * 400)
    session.commit()
    assert len(session.scalar(select(LabReportRow)).results) == 2


def test_long_workout_type_is_clipped(session, person):
    hi = _health()
    hi.workouts[0].type = "W" * 200
    ingest_health(session, person, hi)
    ingest_health(session, person, hi)  # idempotent trotz Kürzung
    session.commit()
    assert [len(w.type) for w in session.scalars(select(Workout))] == [60]
