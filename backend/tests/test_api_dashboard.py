"""Dashboard-API. Nur erfundene Daten, "heute" ist fest (Mittwoch, 18.03.2026)."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api import dashboard
from app.auth import generate_token, hash_token
from app.db import get_session
from app.main import app
from app.models import HealthDaily, ImportJob, LabReport, LabResult, Person, Workout

TODAY = date(2026, 3, 18)
MONDAY = date(2026, 3, 16)
APPLE, HAE = "apple_health_xml", "hae_zip"


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(factory, monkeypatch):
    def _override():
        with factory() as s:
            yield s

    monkeypatch.setattr(dashboard, "today_local", lambda: TODAY)
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _make(session, name) -> dict[str, str]:
    token = generate_token()
    session.add(Person(name=name, sex="m", birth_date=date(1990, 5, 1), token_hash=hash_token(token)))
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


@pytest.fixture
def filled(session, a):
    """Person A: 30 Tage Gewicht (-0,1 kg/Tag), 10 Tage Energie, Workouts, Labor, Importe."""
    p = pid(session, "Person A")
    rows = []
    for i in range(30):
        day = TODAY - timedelta(days=i)
        rows.append(HealthDaily(person_id=p, day=day, source=APPLE, weight_kg=round(80.0 + 0.1 * i, 2)))
    for i in range(10):
        day = TODAY - timedelta(days=i)
        rows.append(HealthDaily(person_id=p, day=day, source=HAE, active_kcal=500.0, basal_kcal=1500.0))
    rows.append(HealthDaily(person_id=p, day=TODAY - timedelta(days=120), source=APPLE, weight_kg=90.0))
    rows.append(
        HealthDaily(person_id=p, day=TODAY + timedelta(days=2), source=APPLE, weight_kg=1.0)
    )  # Zukunft
    session.add_all(rows)

    def wo(type_, start, minutes, source=APPLE):
        return Workout(person_id=p, type=type_, start=start, duration_min=minutes, source=source)

    session.add_all(
        [
            wo("Laufen", datetime(2026, 3, 16, 7, 0), 30.0),
            wo("Laufen", datetime(2026, 3, 16, 7, 4), 30.0, HAE),  # dasselbe Training aus der anderen Quelle
            wo("Kraft", datetime(2026, 3, 17, 18, 0), 60.5),
            wo("Laufen", datetime(2026, 3, 11, 7, 0), 45.0),  # Vorwoche (09.03.-15.03.)
            wo("Laufen", datetime(2026, 1, 20, 7, 0), 20.0),  # genau 8 Wochen zurück (ISO-Woche 4): zu alt
            wo("Laufen", datetime(2026, 1, 26, 7, 0), 25.0),  # älteste angezeigte Woche
            wo("Kraft", datetime(2026, 3, 19, 18, 0), 40.0),  # morgen: noch nicht gezählt
        ]
    )
    rep = LabReport(
        person_id=p, order_no="X-1", report_type="Endbefund", sample_datetime=datetime(2026, 2, 1, 8, 0)
    )
    rep.results = [
        LabResult(analyte="Alpha", unit="u", value=1.0, flag="H"),
        LabResult(analyte="Beta", unit="u", value=1.0, flag=None),
    ]
    rep2 = LabReport(
        person_id=p, order_no="X-2", report_type="Teilbefund", sample_datetime=datetime(2026, 3, 1, 8, 0)
    )
    rep2.results = [
        LabResult(analyte="Alpha", unit="u", value=1.0, flag="L"),  # ersetzt den alten Alpha-Wert
        LabResult(analyte="Beta", unit="u", value=None, pending=True),
        LabResult(analyte="Gamma", unit="u", value=None, pending=True),
    ]
    session.add_all([rep, rep2])
    for i in range(4):
        session.add(ImportJob(person_id=p, kind="hae", status="done", filename=f"datei{i}.zip"))
    session.commit()


def test_requires_auth(client):
    assert client.get("/api/me/dashboard").status_code == 401


def test_dashboard_with_data(client, a, filled):
    resp = client.get("/api/me/dashboard", headers=a)
    assert resp.status_code == 200
    d = resp.json()
    assert set(d) == {"weight", "energy", "workouts", "data", "labs", "imports"}

    w = d["weight"]
    assert w["latest_kg"] == 80.0
    assert w["latest_date"] == "2026-03-18"  # Zukunft zählt nicht
    assert w["trend_kg_per_week"] == pytest.approx(-0.7, abs=0.01)
    assert w["trend_n_points"] == 28
    assert len(w["points"]) == 30  # Punkt von vor 120 Tagen liegt außerhalb der 90 Tage
    assert w["points"][0] == {"day": "2026-02-17", "kg": 82.9}
    assert w["points"][-1] == {"day": "2026-03-18", "kg": 80.0}
    assert [p["day"] for p in w["points"]] == sorted(p["day"] for p in w["points"])

    e = d["energy"]
    assert e["avg_active_kcal"] == 500.0
    assert e["avg_basal_kcal"] == 1500.0
    assert e["device_tdee_kcal"] == 2000.0
    assert e["n_days"] == 10
    assert e["coverage"] == pytest.approx(10 / 28, abs=0.001)
    assert e["last_day"] == "2026-03-18"

    assert [x["source"] for x in d["data"]] == [APPLE, HAE]
    apple, hae = d["data"]
    assert apple == {"source": APPLE, "first_day": "2025-11-18", "last_day": "2026-03-20", "days": 32}
    assert hae == {"source": HAE, "first_day": "2026-03-09", "last_day": "2026-03-18", "days": 10}

    labs = d["labs"]
    assert labs["latest_report_date"] == "2026-03-01"
    assert labs["latest_report_type"] == "Teilbefund"
    assert labs["flagged_count"] == 1  # nur Alpha=L zählt (alter H-Wert ist überholt)
    assert labs["pending_count"] == 2

    jobs = d["imports"]
    assert [j["filename"] for j in jobs] == ["datei3.zip", "datei2.zip", "datei1.zip"]
    assert jobs[0]["status"] == "done"


def test_dashboard_workouts_per_iso_week(client, a, filled):
    weeks = client.get("/api/me/dashboard", headers=a).json()["workouts"]
    assert len(weeks) == 8
    assert [w["week_start"] for w in weeks][-1] == "2026-03-16"
    assert weeks[0]["week_start"] == "2026-01-26"
    assert weeks[-1]["iso_week"] == "2026-W12"
    assert all(date.fromisoformat(w["week_start"]).weekday() == 0 for w in weeks)

    this_week, last_week, oldest = weeks[-1], weeks[-2], weeks[0]
    assert this_week["count"] == 2  # Dublette aus HAE zählt nicht doppelt, morgen zählt nicht
    assert this_week["total_minutes"] == 90.5
    assert this_week["by_type"] == {
        "Laufen": {"count": 1, "minutes": 30.0},
        "Kraft": {"count": 1, "minutes": 60.5},
    }
    assert last_week["count"] == 1 and last_week["total_minutes"] == 45.0
    assert oldest["count"] == 1 and oldest["by_type"] == {"Laufen": {"count": 1, "minutes": 25.0}}
    assert sum(w["count"] for w in weeks) == 4
    assert [w["count"] for w in weeks[1:-2]] == [0, 0, 0, 0, 0]


def test_dashboard_duplicate_follows_source_priority(client, a, filled):
    client.put("/api/me/settings", json={"source_priority": [HAE, APPLE]}, headers=a)
    this_week = client.get("/api/me/dashboard", headers=a).json()["workouts"][-1]
    assert this_week["count"] == 2  # weiterhin eine Laufeinheit, nur aus der anderen Quelle


def test_dashboard_empty(client, a):
    resp = client.get("/api/me/dashboard", headers=a)
    assert resp.status_code == 200
    d = resp.json()
    assert d["weight"] == {
        "latest_kg": None, "latest_date": None, "trend_kg_per_week": None, "trend_n_points": 0, "points": [],
    }  # fmt: skip
    assert d["energy"] == {
        "avg_active_kcal": None, "avg_basal_kcal": None, "device_tdee_kcal": None, "n_days": 0,
        "coverage": 0.0, "last_day": None,
    }  # fmt: skip
    assert len(d["workouts"]) == 8
    assert all(w["count"] == 0 and w["total_minutes"] == 0 and w["by_type"] == {} for w in d["workouts"])
    assert d["data"] == []
    assert d["labs"] == {
        "latest_report_date": None, "latest_report_type": None, "flagged_count": 0, "pending_count": 0,
    }  # fmt: skip
    assert d["imports"] == []


def test_dashboard_sparse_weight_has_no_trend(client, session, a):
    p = pid(session, "Person A")
    session.add(HealthDaily(person_id=p, day=TODAY - timedelta(days=3), source=HAE, weight_kg=75.5))
    session.commit()
    w = client.get("/api/me/dashboard", headers=a).json()["weight"]
    assert w["latest_kg"] == 75.5
    assert w["trend_kg_per_week"] is None
    assert len(w["points"]) == 1


def test_dashboard_isolated_between_persons(client, a, b, filled):
    d = client.get("/api/me/dashboard", headers=b).json()
    assert d["weight"]["latest_kg"] is None
    assert d["energy"]["n_days"] == 0
    assert sum(w["count"] for w in d["workouts"]) == 0
    assert d["data"] == [] and d["imports"] == []
    assert d["labs"]["latest_report_date"] is None
    # und A sieht seine Daten weiterhin
    assert client.get("/api/me/dashboard", headers=a).json()["weight"]["latest_kg"] == 80.0
