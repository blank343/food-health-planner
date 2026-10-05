"""Daten-API: Tageswerte, Workouts, Laborwerte. Nur erfundene Daten."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.auth import generate_token, hash_token
from app.db import get_session
from app.main import app
from app.models import HealthDaily, LabReport, LabResult, Person, Workout

APPLE, HAE = "apple_health_xml", "hae_zip"


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(factory):
    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _make(session, name) -> dict[str, str]:
    token = generate_token()
    session.add(Person(name=name, sex="f", birth_date=date(1990, 5, 1), token_hash=hash_token(token)))
    session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def a(client, session):
    return _make(session, "Person A")


@pytest.fixture
def b(client, session):
    return _make(session, "Person B")


def pid(session, name) -> int:
    return session.scalar(select(Person.id).where(Person.name == name))


# --------------------------------------------------------------------------- Tageswerte


@pytest.fixture
def daily(session, a):
    p = pid(session, "Person A")
    session.add_all(
        [
            HealthDaily(person_id=p, day=date(2025, 3, 1), source=APPLE, weight_kg=70.0, active_kcal=400.0),
            HealthDaily(person_id=p, day=date(2025, 3, 1), source=HAE, weight_kg=71.0, steps=5000.0),
            HealthDaily(person_id=p, day=date(2025, 3, 2), source=HAE, weight_kg=71.5),
            HealthDaily(person_id=p, day=date(2025, 3, 3), source=APPLE, weight_kg=72.0),
        ]
    )
    session.commit()


def test_daily_requires_auth(client):
    assert client.get("/api/me/health/daily").status_code == 401


def test_daily_merged_by_default_priority(client, a, daily):
    rows = client.get("/api/me/health/daily", headers=a).json()
    assert [r["day"] for r in rows] == ["2025-03-01", "2025-03-02", "2025-03-03"]
    first = rows[0]
    assert first["weight_kg"] == 70.0  # Apple gewinnt (Standardpriorität)
    assert first["active_kcal"] == 400.0  # nur Apple
    assert first["steps"] == 5000.0  # fehlendes Feld aus HAE ergänzt
    assert first["sleep_h"] is None


def test_daily_merged_follows_stored_priority(client, a, daily):
    resp = client.put("/api/me/settings", json={"source_priority": [HAE, APPLE]}, headers=a)
    assert resp.status_code == 200
    first = client.get("/api/me/health/daily", headers=a).json()[0]
    assert first["weight_kg"] == 71.0
    assert first["active_kcal"] == 400.0


@pytest.mark.parametrize(("source", "days"), [(APPLE, 2), (HAE, 2)])
def test_daily_raw_source(client, a, daily, source, days):
    rows = client.get("/api/me/health/daily", params={"source": source}, headers=a).json()
    assert len(rows) == days
    if source == APPLE:
        assert [r["weight_kg"] for r in rows] == [70.0, 72.0]
        assert rows[0]["steps"] is None  # keine Ergänzung bei Rohdaten
    else:
        assert [r["weight_kg"] for r in rows] == [71.0, 71.5]
        assert rows[0]["steps"] == 5000.0


def test_daily_date_filter(client, a, daily):
    params = {"from": "2025-03-02", "to": "2025-03-02"}
    assert [r["day"] for r in client.get("/api/me/health/daily", params=params, headers=a).json()] == [
        "2025-03-02"
    ]
    raw = client.get("/api/me/health/daily", params={**params, "source": APPLE}, headers=a).json()
    assert raw == []


def test_daily_validation(client, a):
    assert client.get("/api/me/health/daily", params={"source": "unbekannt"}, headers=a).status_code == 422
    resp = client.get("/api/me/health/daily", params={"from": "2025-03-05", "to": "2025-03-01"}, headers=a)
    assert resp.status_code == 422
    assert "Startdatum" in resp.json()["detail"]
    assert client.get("/api/me/health/daily", params={"from": "kein-datum"}, headers=a).status_code == 422


def test_daily_empty_and_isolated(client, a, b, daily):
    assert client.get("/api/me/health/daily", headers=b).json() == []
    assert client.get("/api/me/health/daily", params={"source": HAE}, headers=b).json() == []


# --------------------------------------------------------------------------- Workouts


@pytest.fixture
def workouts(session, a):
    p = pid(session, "Person A")

    def wo(type_, start, minutes, source, **extra):
        return Workout(person_id=p, type=type_, start=start, duration_min=minutes, source=source, **extra)

    session.add_all(
        [
            wo("Laufen", datetime(2025, 3, 1, 7, 0), 30.0, APPLE, active_kcal=300.0, distance_km=5.0),
            wo("Kraft", datetime(2025, 3, 2, 18, 0), 60.0, HAE),
            wo("Laufen", datetime(2025, 3, 3, 23, 30), 45.0, HAE),
            wo("Laufen", datetime(2025, 3, 4, 0, 0), 20.0, HAE),
        ]
    )
    session.commit()


def test_workouts_newest_first_with_fields(client, a, workouts):
    rows = client.get("/api/me/workouts", headers=a).json()
    assert [r["start"][:10] for r in rows] == ["2025-03-04", "2025-03-03", "2025-03-02", "2025-03-01"]
    last = rows[-1]
    assert last["type"] == "Laufen"
    assert last["source"] == APPLE
    assert last["active_kcal"] == 300.0
    assert last["distance_km"] == 5.0
    assert last["avg_hr"] is None


def test_workouts_filters(client, a, workouts):
    def days(**params):
        return [r["start"][:10] for r in client.get("/api/me/workouts", params=params, headers=a).json()]

    assert days(type="Laufen") == ["2025-03-04", "2025-03-03", "2025-03-01"]
    assert days(type="Kraft") == ["2025-03-02"]
    assert days(type="Yoga") == []
    # "to" gilt einschließlich des ganzen Tages (auch 23:30)
    assert days(**{"from": "2025-03-02", "to": "2025-03-03"}) == ["2025-03-03", "2025-03-02"]
    assert days(**{"from": "2025-03-04"}) == ["2025-03-04"]
    assert days(to="2025-03-01") == ["2025-03-01"]
    assert days(type="Laufen", limit=1) == ["2025-03-04"]


def test_workouts_validation_and_isolation(client, a, b, workouts):
    for bad in ({"limit": 0}, {"limit": 5001}, {"from": "2025-03-05", "to": "2025-03-01"}):
        assert client.get("/api/me/workouts", params=bad, headers=a).status_code == 422
    assert client.get("/api/me/workouts", params={"limit": 5000}, headers=a).status_code == 200
    assert client.get("/api/me/workouts", headers=b).json() == []


# --------------------------------------------------------------------------- Labor


def _report(session, person_id, order_no, report_type, sample, results) -> LabReport:
    rep = LabReport(
        person_id=person_id, order_no=order_no, report_type=report_type, sample_datetime=sample,
        lab_name="Testlabor", source_filename=f"{order_no}.pdf",
    )  # fmt: skip
    for analyte, unit, value, flag, pending in results:
        rep.results.append(
            LabResult(
                analyte=analyte, unit=unit, value=value, flag=flag, pending=pending, ref_low=1.0, ref_high=2.0
            )
        )
    session.add(rep)
    session.commit()
    return rep


@pytest.fixture
def labs(session, a):
    p = pid(session, "Person A")
    old = _report(session, p, "A-1", "Endbefund", datetime(2025, 1, 10, 8, 0), [
        ("Alpha", "mg/dl", 1.5, None, False),
        ("Beta", "U/l", 9.0, "H", False),
        ("Gamma", "mmol/l", 1.1, None, False),
    ])  # fmt: skip
    new = _report(session, p, "A-2", "Teilbefund", datetime(2025, 3, 10, 8, 0), [
        ("Alpha", "mg/dl", 0.4, "L", False),
        ("Gamma", "mmol/l", None, None, True),
        ("Delta", "g/l", None, None, True),
    ])  # fmt: skip
    return old, new


def test_labs_newest_first_with_results(client, a, labs):
    old, new = labs
    reports = client.get("/api/me/labs", headers=a).json()
    assert [r["id"] for r in reports] == [new.id, old.id]
    assert reports[0]["report_type"] == "Teilbefund"
    assert [x["analyte"] for x in reports[1]["results"]] == ["Alpha", "Beta", "Gamma"]
    first = reports[1]["results"][1]
    assert first["flag"] == "H" and first["ref_low"] == 1.0 and first["unit"] == "U/l"
    assert set(reports[0]) == {  # keine Patientendaten im Schema
        "id", "order_no", "lab_name", "report_type", "sample_datetime", "source_filename", "created_at",
        "results",
    }  # fmt: skip


def test_labs_filters(client, a, labs):
    old, new = labs

    def names(**params):
        return {
            r["id"]: [x["analyte"] for x in r["results"]]
            for r in client.get("/api/me/labs", params=params, headers=a).json()
        }

    assert names(flagged="true") == {new.id: ["Alpha"], old.id: ["Beta"]}
    assert names(pending="true") == {new.id: ["Gamma", "Delta"]}
    assert names(flagged="true", pending="true") == {new.id: ["Alpha", "Gamma", "Delta"], old.id: ["Beta"]}
    assert names(flagged="false", pending="false") == {
        new.id: ["Alpha", "Gamma", "Delta"],
        old.id: ["Alpha", "Beta", "Gamma"],
    }


def test_labs_latest_per_analyte(client, a, labs):
    old, new = labs
    rows = client.get("/api/me/labs/latest", headers=a).json()
    by_name = {r["analyte"]: r for r in rows}
    assert [r["analyte"] for r in rows] == ["Alpha", "Beta", "Gamma"]  # sortiert, Delta nur ausstehend
    assert by_name["Alpha"]["value"] == 0.4 and by_name["Alpha"]["flag"] == "L"
    assert by_name["Alpha"]["report_id"] == new.id
    assert by_name["Alpha"]["report_date"] == "2025-03-10"
    # Gamma steht im neuen Bericht aus, es gilt der Wert aus dem alten
    assert by_name["Gamma"]["value"] == 1.1 and by_name["Gamma"]["report_id"] == old.id
    assert by_name["Gamma"]["report_date"] == "2025-01-10"
    assert by_name["Beta"]["ref_low"] == 1.0 and by_name["Beta"]["ref_high"] == 2.0


def test_labs_latest_keeps_same_analyte_in_two_units(client, a, session):
    person = session.scalar(select(Person).where(Person.name == "Person A"))
    rep = LabReport(
        person_id=person.id, order_no="U-1", report_type="Endbefund",
        sample_datetime=datetime(2025, 5, 1, 8, 0),
    )  # fmt: skip
    rep.results = [
        LabResult(analyte="Messgröße", unit="%", value=47.0, flag="H"),
        LabResult(analyte="Messgröße", unit="G/l", value=2.7),
    ]
    session.add(rep)
    session.commit()
    rows = client.get("/api/me/labs/latest", headers=a).json()
    assert [(r["analyte"], r["unit"]) for r in rows] == [("Messgröße", "%"), ("Messgröße", "G/l")] or [
        (r["analyte"], r["unit"]) for r in rows
    ] == [("Messgröße", "G/l"), ("Messgröße", "%")]
    assert sum(1 for r in rows if r["flag"] == "H") == 1


def test_lab_report_by_id_and_404(client, a, b, session, labs):
    old, new = labs
    body = client.get(f"/api/me/labs/{old.id}", headers=a).json()
    assert body["order_no"] == "A-1" and len(body["results"]) == 3
    assert client.get(f"/api/me/labs/{old.id}", headers=b).status_code == 404
    assert client.get("/api/me/labs/999999", headers=a).status_code == 404


def test_labs_empty_and_isolated(client, a, b, labs):
    assert client.get("/api/me/labs", headers=b).json() == []
    assert client.get("/api/me/labs/latest", headers=b).json() == []
    assert client.get("/api/me/labs", params={"flagged": "true"}, headers=b).json() == []
