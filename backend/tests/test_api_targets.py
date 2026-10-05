from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import targets
from app.auth import generate_token, hash_token
from app.db import get_session
from app.models import GoalProfile, HealthDaily, Person

TODAY = date(2026, 10, 5)


@pytest.fixture
def token(session):
    tok = generate_token()
    p = Person(
        name="Test A", sex="m", birth_date=date(1992, 2, 21), height_cm=190.0, token_hash=hash_token(tok)
    )
    session.add(p)
    session.commit()
    session.info["person_id"] = p.id
    return tok


@pytest.fixture
def client(engine, token):
    app = FastAPI()
    app.include_router(targets.router, prefix="/api")
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed(session, pid):
    for i in range(30):
        session.add(
            HealthDaily(
                person_id=pid, day=TODAY - timedelta(days=29 - i), source="hae_zip",
                weight_kg=80.0, active_kcal=750.0, basal_kcal=2000.0,
            )
        )  # fmt: skip
    session.add(GoalProfile(person_id=pid, kind="lose", rate_kg_per_week=0.5, valid_from=date(2026, 1, 1)))
    session.commit()


def test_requires_token(client):
    assert client.get("/api/me/targets").status_code == 401


def test_without_weight_gives_german_422(client, token):
    r = client.get("/api/me/targets", headers=_auth(token))
    assert r.status_code == 422 and "Gewicht" in r.json()["detail"]


def test_targets_response(client, token, session):
    _seed(session, session.info["person_id"])
    r = client.get("/api/me/targets", params={"date": TODAY.isoformat()}, headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == TODAY.isoformat()
    assert body["target"]["kcal"] == pytest.approx(2200, abs=10)
    assert body["tdee"]["method"] == "device"
    assert body["goal"]["kind"] == "lose" and body["goal"]["applied_rate_kg_per_week"] == pytest.approx(0.5)
    assert body["body"]["weight_kg"] == 80.0
    assert set(body["slots"]) == {"breakfast", "lunch", "dinner"}


def test_shares_parameter_and_bad_value(client, token, session):
    _seed(session, session.info["person_id"])
    r = client.get(
        "/api/me/targets", params={"date": TODAY.isoformat(), "shares": "breakfast:1"}, headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.json()["slots"]["breakfast"]["kcal"] == pytest.approx(r.json()["target"]["kcal"], abs=0.5)
    bad = client.get("/api/me/targets", params={"shares": "breakfast:x"}, headers=_auth(token))
    assert bad.status_code == 422
