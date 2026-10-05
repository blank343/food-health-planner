from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import today_local
from app.auth import generate_token, hash_token
from app.db import get_session
from app.main import app
from app.models import HealthDaily, Person
from app.services.health_view import merged_daily


@pytest.fixture
def client(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def auth(client, session):
    tok = generate_token()
    p = Person(name="Test A", sex="m", birth_date=date(1990, 1, 1), token_hash=hash_token(tok))
    session.add(p)
    session.commit()
    session.info["pid"] = p.id
    return {"Authorization": f"Bearer {tok}"}


def test_requires_token(client):
    assert client.post("/api/me/health/manual", json={"weight_kg": 80}).status_code == 401


def test_add_weight_today_and_update_same_day(client, auth, session):
    r = client.post("/api/me/health/manual", json={"weight_kg": 80.4}, headers=auth)
    assert r.status_code == 201 and r.json()["weight_kg"] == 80.4
    assert r.json()["day"] == today_local().isoformat()
    r2 = client.post("/api/me/health/manual", json={"body_fat_pct": 12.0}, headers=auth)
    # ergänzt, nicht überschrieben
    assert r2.json()["weight_kg"] == 80.4 and r2.json()["body_fat_pct"] == 12.0
    r3 = client.post("/api/me/health/manual", json={"weight_kg": 79.9}, headers=auth)
    assert r3.json()["weight_kg"] == 79.9
    assert session.query(HealthDaily).filter_by(source="manual").count() == 1


def test_validation(client, auth):
    assert client.post("/api/me/health/manual", json={}, headers=auth).status_code == 422
    assert client.post("/api/me/health/manual", json={"weight_kg": 5}, headers=auth).status_code == 422
    future = (today_local() + timedelta(days=1)).isoformat()
    r = client.post("/api/me/health/manual", json={"weight_kg": 80, "day": future}, headers=auth)
    assert r.status_code == 422


def test_manual_beats_imported_value_in_default_priority(client, auth, session):
    pid = session.info["pid"]
    day = today_local()
    session.add(HealthDaily(person_id=pid, day=day, source="hae_zip", weight_kg=81.0))
    session.commit()
    client.post("/api/me/health/manual", json={"weight_kg": 78.2}, headers=auth)
    settings = client.get("/api/me/settings", headers=auth).json()["effective"]
    (row,) = merged_daily(session, pid, settings["source_priority"], start=day, end=day)
    assert row.weight_kg == 78.2
    daily = client.get("/api/me/health/daily", headers=auth).json()
    assert daily[-1]["weight_kg"] == 78.2


def test_other_person_not_affected(client, auth, session):
    tok2 = generate_token()
    session.add(Person(name="Test B", sex="f", birth_date=date(1992, 2, 2), token_hash=hash_token(tok2)))
    session.commit()
    client.post("/api/me/health/manual", json={"weight_kg": 80}, headers=auth)
    assert client.get("/api/me/health/daily", headers={"Authorization": f"Bearer {tok2}"}).json() == []
