from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import HealthDaily, LabReport, LabResult, Person, PersonSettingsRow


def _person(session, name="Test A"):
    p = Person(name=name, sex="m", birth_date=date(1990, 1, 1), height_cm=180)
    session.add(p)
    session.commit()
    return p


def test_person_name_unique(session):
    _person(session)
    session.add(Person(name="Test A", sex="f", birth_date=date(1992, 2, 2)))
    with pytest.raises(IntegrityError):
        session.commit()


def test_health_daily_unique_per_source(session):
    p = _person(session)
    session.add(HealthDaily(person_id=p.id, day=date(2026, 1, 1), source="hae_zip", weight_kg=80))
    session.add(HealthDaily(person_id=p.id, day=date(2026, 1, 1), source="apple_health_xml", weight_kg=80.2))
    session.commit()  # verschiedene Quellen am selben Tag sind erlaubt
    session.add(HealthDaily(person_id=p.id, day=date(2026, 1, 1), source="hae_zip", weight_kg=81))
    with pytest.raises(IntegrityError):
        session.commit()


def test_lab_report_cascade_and_unique_result(session):
    p = _person(session)
    rep = LabReport(person_id=p.id, order_no="123", report_type="Endbefund",
                    sample_datetime=datetime(2026, 1, 1, 10, 0))
    rep.results = [LabResult(analyte="CRP", unit="mg/l", value=0.5)]
    session.add(rep)
    session.commit()
    rep.results.append(LabResult(analyte="CRP", unit="mg/l", value=0.6))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_delete_person_cascades(session):
    p = _person(session)
    session.add(PersonSettingsRow(person_id=p.id, data={"weight_floor_kg": 70}))
    session.add(HealthDaily(person_id=p.id, day=date(2026, 1, 1), source="hae_zip", weight_kg=80))
    session.commit()
    session.delete(p)
    session.commit()
    assert session.query(HealthDaily).count() == 0
    assert session.query(PersonSettingsRow).count() == 0
