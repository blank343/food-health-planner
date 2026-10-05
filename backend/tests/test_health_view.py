from datetime import date

from app.models import HealthDaily, Person
from app.services.health_view import (
    age_years,
    day_energy,
    latest_value,
    merged_daily,
    weight_series,
)

PRIO = ["apple_health_xml", "hae_zip"]


def _person(session):
    p = Person(name="Test A", sex="m", birth_date=date(1990, 1, 1))
    session.add(p)
    session.commit()
    return p


def _add(session, p, day, source, **kw):
    session.add(HealthDaily(person_id=p.id, day=day, source=source, **kw))
    session.commit()


def test_priority_wins_and_gaps_are_filled(session):
    p = _person(session)
    d = date(2026, 1, 1)
    _add(session, p, d, "hae_zip", weight_kg=80.0, steps=8000, sleep_h=7.0)
    _add(session, p, d, "apple_health_xml", weight_kg=79.5, steps=None, hrv_ms=50.0)
    (row,) = merged_daily(session, p.id, PRIO)
    assert row.weight_kg == 79.5  # höhere Priorität
    assert row.steps == 8000 and row.sleep_h == 7.0  # Lücken aus der anderen Quelle
    assert row.hrv_ms == 50.0


def test_unknown_source_ranks_last(session):
    p = _person(session)
    d = date(2026, 1, 1)
    _add(session, p, d, "other", weight_kg=70.0)
    _add(session, p, d, "hae_zip", weight_kg=80.0)
    assert merged_daily(session, p.id, PRIO)[0].weight_kg == 80.0


def test_range_and_order(session):
    p = _person(session)
    for i in (3, 1, 2):
        _add(session, p, date(2026, 1, i), "hae_zip", weight_kg=80 + i)
    rows = merged_daily(session, p.id, PRIO, start=date(2026, 1, 2), end=date(2026, 1, 3))
    assert [r.day.day for r in rows] == [2, 3]


def test_other_person_not_included(session):
    a = _person(session)
    b = Person(name="Test B", sex="f", birth_date=date(1992, 2, 2))
    session.add(b)
    session.commit()
    _add(session, a, date(2026, 1, 1), "hae_zip", weight_kg=80)
    _add(session, b, date(2026, 1, 1), "hae_zip", weight_kg=60)
    assert [r.weight_kg for r in merged_daily(session, a.id, PRIO)] == [80]


def test_helpers(session):
    p = _person(session)
    _add(session, p, date(2026, 1, 1), "hae_zip", weight_kg=80, active_kcal=700, basal_kcal=2000)
    _add(session, p, date(2026, 1, 2), "hae_zip", steps=5000)
    rows = merged_daily(session, p.id, PRIO)
    assert latest_value(rows, "weight_kg") == (date(2026, 1, 1), 80)
    assert latest_value(rows, "steps") == (date(2026, 1, 2), 5000)
    assert latest_value(rows, "hrv_ms") is None
    assert weight_series(rows) == [(date(2026, 1, 1), 80)]
    de = day_energy(rows)
    assert de[0].basal_kcal == 2000 and de[1].basal_kcal is None


def test_age_years():
    assert abs(age_years(date(1990, 1, 1), date(2026, 1, 1)) - 36.0) < 0.05
