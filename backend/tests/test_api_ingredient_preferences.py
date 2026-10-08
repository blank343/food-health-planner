"""Tests der Zutaten-Vorlieben (`/api/me/ingredient-preferences`). Alle Daten sind erfunden."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import ingredient_preferences
from app.auth import generate_token, hash_token
from app.db import get_session
from app.models import Ingredient, IngredientPreference, Person

URL = "/api/me/ingredient-preferences"


@pytest.fixture
def tokens(session):
    out = {}
    for name in ("Test A", "Test B"):
        tok = generate_token()
        session.add(Person(name=name, sex="m", birth_date=date(1990, 1, 1), token_hash=hash_token(tok)))
        out[name] = tok
    session.commit()
    return out


@pytest.fixture
def client(engine, tokens):
    app = FastAPI()
    app.include_router(ingredient_preferences.router, prefix="/api")
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def ing(session):
    rows = {n: Ingredient(name=n, source="manual") for n in ("Zucchini", "Anchovis", "Mandel")}
    session.add_all(rows.values())
    session.commit()
    return {n: r.id for n, r in rows.items()}


def a(tokens):
    return {"Authorization": f"Bearer {tokens['Test A']}"}


def b(tokens):
    return {"Authorization": f"Bearer {tokens['Test B']}"}


def test_requires_token(client, ing):
    zid = ing["Zucchini"]
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/{zid}", json={"level": "like"}).status_code == 401
    assert client.delete(f"{URL}/{zid}").status_code == 401
    assert client.get(URL, headers={"Authorization": "Bearer falsch"}).status_code == 401


def test_empty_list(client, tokens):
    r = client.get(URL, headers=a(tokens))
    assert r.status_code == 200 and r.json() == []


def test_put_creates_and_updates(client, tokens, ing, session):
    zid = ing["Zucchini"]
    r = client.put(f"{URL}/{zid}", json={"level": "like"}, headers=a(tokens))
    assert r.status_code == 200
    assert r.json() == {"ingredient_id": zid, "ingredient_name": "Zucchini", "level": "like"}

    r = client.put(f"{URL}/{zid}", json={"level": "never"}, headers=a(tokens))
    assert r.status_code == 200 and r.json()["level"] == "never"
    assert session.query(IngredientPreference).count() == 1  # aktualisiert, nicht doppelt

    r = client.get(URL, headers=a(tokens))
    assert r.json() == [{"ingredient_id": zid, "ingredient_name": "Zucchini", "level": "never"}]


def test_list_sorted_by_name_and_filter_by_level(client, tokens, ing):
    for name, level in (("Zucchini", "like"), ("Anchovis", "never"), ("Mandel", "like")):
        client.put(f"{URL}/{ing[name]}", json={"level": level}, headers=a(tokens))
    r = client.get(URL, headers=a(tokens)).json()
    assert [x["ingredient_name"] for x in r] == ["Anchovis", "Mandel", "Zucchini"]
    likes = client.get(URL, params={"level": "like"}, headers=a(tokens)).json()
    assert [x["ingredient_name"] for x in likes] == ["Mandel", "Zucchini"]
    assert client.get(URL, params={"level": "dislike"}, headers=a(tokens)).json() == []
    assert client.get(URL, params={"level": "egal"}, headers=a(tokens)).status_code == 422


def test_invalid_level_is_422(client, tokens, ing):
    zid = ing["Zucchini"]
    for body in ({"level": "love"}, {}, {"level": None}, {"level": "like", "extra": 1}):
        assert client.put(f"{URL}/{zid}", json=body, headers=a(tokens)).status_code == 422, body
    assert client.get(URL, headers=a(tokens)).json() == []


def test_unknown_ingredient_is_404(client, tokens):
    r = client.put(f"{URL}/999", json={"level": "like"}, headers=a(tokens))
    assert r.status_code == 404 and "nicht gefunden" in r.json()["detail"]


def test_delete(client, tokens, ing):
    zid = ing["Zucchini"]
    client.put(f"{URL}/{zid}", json={"level": "dislike"}, headers=a(tokens))
    assert client.delete(f"{URL}/{zid}", headers=a(tokens)).status_code == 204
    assert client.get(URL, headers=a(tokens)).json() == []
    r = client.delete(f"{URL}/{zid}", headers=a(tokens))  # nichts mehr da
    assert r.status_code == 404 and "nicht gefunden" in r.json()["detail"]
    assert client.delete(f"{URL}/999", headers=a(tokens)).status_code == 404


def test_preferences_are_separate_per_person(client, tokens, ing, session):
    zid, aid = ing["Zucchini"], ing["Anchovis"]
    client.put(f"{URL}/{zid}", json={"level": "like"}, headers=a(tokens))
    client.put(f"{URL}/{aid}", json={"level": "never"}, headers=a(tokens))
    client.put(f"{URL}/{zid}", json={"level": "dislike"}, headers=b(tokens))

    mine = {x["ingredient_name"]: x["level"] for x in client.get(URL, headers=a(tokens)).json()}
    theirs = {x["ingredient_name"]: x["level"] for x in client.get(URL, headers=b(tokens)).json()}
    assert mine == {"Zucchini": "like", "Anchovis": "never"}
    assert theirs == {"Zucchini": "dislike"}

    # B kann As Vorliebe weder löschen noch sehen: 404, und A bleibt unverändert
    assert client.delete(f"{URL}/{aid}", headers=b(tokens)).status_code == 404
    assert client.get(URL, params={"level": "never"}, headers=b(tokens)).json() == []
    assert {x["ingredient_name"] for x in client.get(URL, headers=a(tokens)).json()} == {
        "Zucchini",
        "Anchovis",
    }

    client.delete(f"{URL}/{zid}", headers=b(tokens))
    assert {x["ingredient_name"]: x["level"] for x in client.get(URL, headers=a(tokens)).json()}[
        "Zucchini"
    ] == "like"
    assert session.query(IngredientPreference).count() == 2


def test_preferences_are_removed_with_ingredient(client, tokens, ing, session):
    client.put(f"{URL}/{ing['Mandel']}", json={"level": "like"}, headers=a(tokens))
    session.query(Ingredient).filter_by(id=ing["Mandel"]).delete()
    session.commit()
    assert client.get(URL, headers=a(tokens)).json() == []
    assert session.query(IngredientPreference).count() == 0
