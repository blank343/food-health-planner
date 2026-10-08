"""Zutaten-API (`/api/ingredients`). Nur erfundene Daten."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import ingredients
from app.auth import generate_token, hash_token
from app.db import get_session
from app.models import Component, Ingredient, IngredientSynonym, Person, Recipe, RecipeIngredient
from app.services import catalog


@pytest.fixture
def token(session):
    tok = generate_token()
    session.add(
        Person(
            name="Test A", sex="m", birth_date=date(1992, 2, 21), height_cm=190.0, token_hash=hash_token(tok)
        )
    )
    session.commit()
    return tok


@pytest.fixture
def client(engine, token):
    app = FastAPI()
    app.include_router(ingredients.router, prefix="/api")
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def bls_onion(session):
    ing = Ingredient(
        name="Speisezwiebel roh", source="bls", source_code="G100100", category="Gemüse", kcal_100=30.0,
        protein_100=1.2, fat_100=0.2, carb_100=5.0, fiber_100=1.5, salt_100=0.02, micros={"zinc_mg": 0.2},
    )  # fmt: skip
    session.add(ing)
    session.commit()
    return ing


MANUAL = {
    "name": "Eigener Skyr",
    "kcal_100": 63.0,
    "protein_100": 11.0,
    "fat_100": 0.2,
    "carb_100": 4.0,
    "salt_100": 0.1,
    "micros": {"zinc_mg": 0.5},
    "piece_g": 150.0,
}


def test_requires_token(client):
    assert client.get("/api/ingredients").status_code == 401
    assert client.get("/api/ingredients/1").status_code == 401
    assert client.post("/api/ingredients", json=MANUAL).status_code == 401
    assert client.patch("/api/ingredients/1", json={"hidden": True}).status_code == 401
    assert client.delete("/api/ingredients/1").status_code == 401
    assert client.post("/api/ingredients/1/synonyms", json={"alias": "x"}).status_code == 401
    assert client.delete("/api/ingredients/1/synonyms/x").status_code == 401


def test_create_manual_ingredient(client, auth):
    r = client.post("/api/ingredients", json=MANUAL, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "manual" and body["source_code"] is None and body["synonyms"] == []
    assert body["nutrients"] == {
        "kcal": 63.0, "protein_g": 11.0, "fat_g": 0.2, "carb_g": 4.0, "fiber_g": None, "salt_g": 0.1,
        "micros": {"zinc_mg": 0.5},
    }  # fmt: skip
    assert body["piece_g"] == 150.0 and body["hidden"] is False and body["is_fish"] is False
    assert client.get(f"/api/ingredients/{body['id']}", headers=auth).json() == body


def test_create_validation_and_duplicates(client, auth):
    for bad in (
        {**MANUAL, "name": "   "},
        {**MANUAL, "kcal_100": -1},
        {**MANUAL, "kcal_100": 5000},
        {**MANUAL, "protein_100": 60, "fat_100": 30, "carb_100": 30},
        {**MANUAL, "piece_g": 0},
        {**MANUAL, "micros": {"zinc_mg": -1}},
        {**MANUAL, "density_g_per_ml": 0},
    ):
        assert client.post("/api/ingredients", json=bad, headers=auth).status_code == 422, bad
    assert client.post("/api/ingredients", json={"kcal_100": 1}, headers=auth).status_code == 422
    assert client.post("/api/ingredients", json=MANUAL, headers=auth).status_code == 201
    dup = client.post("/api/ingredients", json={**MANUAL, "name": "eigener SKYR"}, headers=auth)
    assert dup.status_code == 409 and "schon" in dup.json()["detail"]


def test_list_search_filters_and_paging(client, auth, bls_onion):
    client.post("/api/ingredients", json=MANUAL, headers=auth)
    client.post(
        "/api/ingredients", json={**MANUAL, "name": "Eigene Zwiebelsoße", "hidden": True}, headers=auth
    )
    everything = client.get("/api/ingredients", headers=auth).json()
    assert everything["total"] == 2 and everything["limit"] == 25 and everything["offset"] == 0
    assert [i["name"] for i in everything["items"]] == [
        "Eigener Skyr",
        "Speisezwiebel roh",
    ]  # Ausgeblendetes fehlt
    found = client.get("/api/ingredients", params={"q": "zwiebel"}, headers=auth).json()
    assert [i["name"] for i in found["items"]] == ["Speisezwiebel roh"]
    assert found["items"][0]["nutrients"]["kcal"] == 30.0
    manual = client.get("/api/ingredients", params={"source": "manual"}, headers=auth).json()
    assert [i["name"] for i in manual["items"]] == ["Eigener Skyr"]
    with_hidden = client.get(
        "/api/ingredients", params={"q": "zwiebel", "include_hidden": "true"}, headers=auth
    ).json()
    assert {i["name"] for i in with_hidden["items"]} == {"Speisezwiebel roh", "Eigene Zwiebelsoße"}
    page = client.get("/api/ingredients", params={"limit": 1, "offset": 1}, headers=auth).json()
    assert page["total"] == 2 and [i["name"] for i in page["items"]] == ["Speisezwiebel roh"]
    for bad in ({"limit": 0}, {"limit": 500}, {"offset": -1}, {"source": "usda"}):
        assert client.get("/api/ingredients", params=bad, headers=auth).status_code == 422


def test_get_detail_with_synonyms_and_404(client, auth, bls_onion, session):
    catalog.add_synonym(session, bls_onion.id, "Zwiebel")
    catalog.add_synonym(session, bls_onion.id, "Küchenzwiebel")
    body = client.get(f"/api/ingredients/{bls_onion.id}", headers=auth).json()
    assert body["synonyms"] == ["küchenzwiebel", "zwiebel"]
    assert body["category"] == "Gemüse" and body["source_code"] == "G100100"
    assert body["nutrients"]["micros"] == {"zinc_mg": 0.2}
    r = client.get("/api/ingredients/9999", headers=auth)
    assert r.status_code == 404 and "nicht gefunden" in r.json()["detail"]


def test_patch_manual_ingredient(client, auth):
    created = client.post("/api/ingredients", json=MANUAL, headers=auth).json()
    url = f"/api/ingredients/{created['id']}"
    r = client.patch(url, json={"name": "Skyr Natur", "kcal_100": 65.0, "piece_g": None}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Skyr Natur" and body["nutrients"]["kcal"] == 65.0 and body["piece_g"] is None
    assert body["nutrients"]["protein_g"] == 11.0  # nicht gesendet: bleibt
    # zusammengeführter Datensatz wird geprüft
    assert client.patch(url, json={"fat_100": 95.0}, headers=auth).status_code == 422
    assert client.patch(url, json={"kcal_100": 1000}, headers=auth).status_code == 422
    assert client.patch(url, json={"name": None}, headers=auth).status_code == 422
    assert client.patch(url, json={"is_fish": None}, headers=auth).status_code == 422
    assert client.patch(url, json={"micros": None}, headers=auth).json()["nutrients"]["micros"] == {}
    other = client.post("/api/ingredients", json={**MANUAL, "name": "Anderer Quark"}, headers=auth).json()
    assert client.patch(url, json={"name": "anderer quark"}, headers=auth).status_code == 409
    assert (
        client.patch(
            f"/api/ingredients/{other['id']}", json={"name": "Anderer Quark"}, headers=auth
        ).status_code
        == 200
    )
    assert client.patch("/api/ingredients/9999", json={"hidden": True}, headers=auth).status_code == 404


def test_patch_bls_ingredient_is_limited(client, auth, bls_onion):
    url = f"/api/ingredients/{bls_onion.id}"
    ok = client.patch(
        url, json={"hidden": True, "piece_g": 80, "density_g_per_ml": 0.9, "shelf_days": 14}, headers=auth
    )
    assert ok.status_code == 200
    body = ok.json()
    assert (body["hidden"], body["piece_g"], body["density_g_per_ml"], body["shelf_days"]) == (
        True,
        80.0,
        0.9,
        14,
    )
    assert body["name"] == "Speisezwiebel roh" and body["nutrients"]["kcal"] == 30.0
    for forbidden in ({"name": "Neu"}, {"kcal_100": 1.0}, {"micros": {}}, {"is_fish": True}):
        r = client.patch(url, json=forbidden, headers=auth)
        assert r.status_code == 422 and "importierter Zutaten" in r.json()["detail"], forbidden
    assert client.patch(url, json={"piece_g": -5}, headers=auth).status_code == 422
    assert client.patch(url, json={"hidden": None}, headers=auth).status_code == 422


def test_delete_rules(client, auth, bls_onion, session):
    # BLS: nie löschen
    r = client.delete(f"/api/ingredients/{bls_onion.id}", headers=auth)
    assert r.status_code == 409 and "ausblenden" in r.json()["detail"]
    # manuell ohne Verwendung: löschen
    free = client.post("/api/ingredients", json=MANUAL, headers=auth).json()
    assert client.delete(f"/api/ingredients/{free['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/ingredients/{free['id']}", headers=auth).status_code == 404
    assert client.delete(f"/api/ingredients/{free['id']}", headers=auth).status_code == 404
    # in einem Rezept verwendet: 409
    used = client.post("/api/ingredients", json={**MANUAL, "name": "Im Rezept"}, headers=auth).json()
    recipe = Recipe(title="R", servings=1.0, status="ready")
    recipe.ingredients = [RecipeIngredient(position=0, raw_text="100 g Im Rezept", ingredient_id=used["id"])]
    session.add(recipe)
    session.commit()
    r = client.delete(f"/api/ingredients/{used['id']}", headers=auth)
    assert r.status_code == 409 and "verwendet" in r.json()["detail"]
    # im Baukasten verwendet: 409
    comp = client.post("/api/ingredients", json={**MANUAL, "name": "Im Baukasten"}, headers=auth).json()
    session.add(Component(name="Eiweiß", kind="protein", ingredient_id=comp["id"]))
    session.commit()
    assert client.delete(f"/api/ingredients/{comp['id']}", headers=auth).status_code == 409


def test_add_and_remove_synonyms(client, auth, bls_onion, session):
    url = f"/api/ingredients/{bls_onion.id}/synonyms"
    r = client.post(url, json={"alias": "  Rote ZWIEBELN "}, headers=auth)
    assert r.status_code == 201 and r.json()["synonyms"] == ["rot zwiebel"]
    assert (
        client.post(url, json={"alias": "rot Zwiebel"}, headers=auth).status_code == 201
    )  # gleiches Ziel: ok
    assert client.get(f"/api/ingredients/{bls_onion.id}", headers=auth).json()["synonyms"] == ["rot zwiebel"]

    other = client.post("/api/ingredients", json=MANUAL, headers=auth).json()
    conflict = client.post(
        f"/api/ingredients/{other['id']}/synonyms", json={"alias": "rot zwiebel"}, headers=auth
    )
    assert conflict.status_code == 409 and "Speisezwiebel roh" in conflict.json()["detail"]
    assert client.post(url, json={"alias": "   "}, headers=auth).status_code == 422
    assert client.post(url, json={"alias": ""}, headers=auth).status_code == 422
    assert client.post("/api/ingredients/9999/synonyms", json={"alias": "x"}, headers=auth).status_code == 404

    gone = client.delete(f"/api/ingredients/{bls_onion.id}/synonyms/rote%20Zwiebeln", headers=auth)
    assert gone.status_code == 204
    assert session.query(IngredientSynonym).count() == 0
    again = client.delete(f"/api/ingredients/{bls_onion.id}/synonyms/rot%20zwiebel", headers=auth)
    assert again.status_code == 404
    assert client.delete("/api/ingredients/9999/synonyms/x", headers=auth).status_code == 404
