"""Authentifizierung: Bearer-Token, nur als Hash gespeichert."""

import hashlib
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.auth import authenticate, generate_token, hash_token
from app.db import get_session
from app.main import app
from app.models import Person


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


def make_person(session, name="Testperson A", active=True) -> tuple[Person, str]:
    token = generate_token()
    person = Person(
        name=name,
        sex="f",
        birth_date=date(1990, 5, 1),
        height_cm=170.0,
        token_hash=hash_token(token),
        is_active=active,
    )
    session.add(person)
    session.commit()
    return person, token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_token_is_urlsafe_and_long_enough():
    token = generate_token()
    assert len(token) >= 43
    assert token != generate_token()


def test_hash_is_sha256_hex():
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_stored_only_as_hash(session):
    person, token = make_person(session)
    stored = session.scalar(select(Person.token_hash).where(Person.id == person.id))
    assert stored == hash_token(token)
    assert token not in stored and stored != token


def test_authenticate(session):
    person, token = make_person(session)
    assert authenticate(session, token).id == person.id
    assert authenticate(session, token + "x") is None
    assert authenticate(session, "") is None
    assert authenticate(session, None) is None
    # der Hash selbst ist kein gültiges Token
    assert authenticate(session, person.token_hash) is None


def test_person_without_token_cannot_log_in(session):
    person, token = make_person(session)
    person.token_hash = None
    session.commit()
    assert authenticate(session, token) is None


def test_missing_token_401(client):
    resp = client.get("/api/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Nicht angemeldet. Bitte Zugangstoken angeben."
    assert resp.headers["www-authenticate"] == "Bearer"


def test_invalid_token_401(client, session):
    make_person(session)
    assert client.get("/api/me", headers=bearer("falsch")).status_code == 401


def test_wrong_scheme_401(client, session):
    _, token = make_person(session)
    assert client.get("/api/me", headers={"Authorization": f"Basic {token}"}).status_code == 401


def test_inactive_person_401(client, session):
    _, token = make_person(session, active=False)
    resp = client.get("/api/me", headers=bearer(token))
    assert resp.status_code == 401


def test_valid_token_returns_profile(client, session):
    person, token = make_person(session)
    resp = client.get("/api/me", headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json() == {
        "id": person.id,
        "name": "Testperson A",
        "sex": "f",
        "birth_date": "1990-05-01",
        "height_cm": 170.0,
    }
    assert "token" not in resp.text


def test_deactivation_takes_effect_immediately(client, session):
    person, token = make_person(session)
    assert client.get("/api/me", headers=bearer(token)).status_code == 200
    person.is_active = False
    session.commit()
    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_all_crud_routes_require_auth(client):
    for path in ("supplements", "nutrient-rules", "training-plan", "lab-rules"):
        assert client.get(f"/api/me/{path}").status_code == 401
        assert client.post(f"/api/me/{path}", json={}).status_code == 401
        assert client.get(f"/api/me/{path}/1").status_code == 401
    assert client.get("/api/me/settings").status_code == 401
    assert client.get("/api/me/goals").status_code == 401
    assert client.get("/api/me/goals/active").status_code == 401
