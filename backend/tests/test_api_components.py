"""Tests der Komponenten-API (`/api/components`). Alle Daten sind erfunden."""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import components
from app.auth import generate_token, hash_token
from app.db import get_session
from app.models import (
    Component,
    ComponentVariant,
    GoalProfile,
    HealthDaily,
    Ingredient,
    Person,
    PersonSettingsRow,
)

TODAY = date(2026, 10, 5)  # ein Montag


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
    app.include_router(components.router, prefix="/api")
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ids(session):
    """Erfundene Zutaten; Rückgabe: Name → ID."""
    rows = [
        Ingredient(name="Testei", source="manual", kcal_100=140, protein_100=12, fat_100=10, carb_100=1,
                   salt_100=0.37, micros={"zinc_mg": 1.3}),
        Ingredient(name="Testbrot", source="manual", kcal_100=250, protein_100=9, fat_100=2, carb_100=48,
                   fiber_100=7, salt_100=1.2),
        Ingredient(name="Testskyr", source="manual", kcal_100=63, protein_100=11, fat_100=0.2, carb_100=4,
                   micros={"sodium_mg": 40}),
    ]  # fmt: skip
    session.add_all(rows)
    session.commit()
    return {"egg": rows[0].id, "bread": rows[1].id, "skyr": rows[2].id}


def _make(client, token, **kw):
    body = {"name": "Ei", "kind": "protein", "ingredient_id": 1} | kw
    r = client.post("/api/components", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()


def _seed_person(session, shares=None, **settings):
    pid = session.info["person_id"]
    for i in range(30):
        session.add(
            HealthDaily(
                person_id=pid, day=TODAY - timedelta(days=29 - i), source="hae_zip",
                weight_kg=80.0, active_kcal=750.0, basal_kcal=2000.0,
            )
        )  # fmt: skip
    session.add(GoalProfile(person_id=pid, kind="lose", rate_kg_per_week=0.5, valid_from=date(2026, 1, 1)))
    data = dict(settings)
    if shares is not None:
        data["slot_shares"] = shares
    session.add(PersonSettingsRow(person_id=pid, data=data))
    session.commit()


# ---------------------------------------------------------------------------
# Zugriffsschutz
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("get", "/api/components", None),
        ("post", "/api/components", {"name": "X", "kind": "other", "ingredient_id": 1}),
        ("get", "/api/components/1", None),
        ("patch", "/api/components/1", {"name": "Y"}),
        ("delete", "/api/components/1", None),
        ("post", "/api/components/1/variants", {"name": "V"}),
        ("patch", "/api/components/1/variants/1", {"name": "V"}),
        ("delete", "/api/components/1/variants/1", None),
        ("post", "/api/components/seed-defaults", None),
        ("post", "/api/components/meal", {"items": [{"component_id": 1, "grams": 10}]}),
    ],
)
def test_requires_token(client, method, url, body):
    r = getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)
    assert r.status_code == 401
    r = getattr(client, method)(url, headers={"Authorization": "Bearer falsch"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_and_read_component(client, token, ids):
    c = _make(client, token, ingredient_id=ids["egg"], max_g=360, step_g=60, typical_g=120)
    assert c["name"] == "Ei" and c["ingredient_name"] == "Testei" and c["variants"] == []
    assert c["per100"]["kcal"] == 140 and c["per100"]["protein_g"] == 12 and c["per100"]["salt_g"] == 0.37
    assert c["per100"]["fiber_g"] is None and c["per100"]["micros"] == {"zinc_mg": 1.3}
    assert (c["min_g"], c["max_g"], c["step_g"], c["typical_g"], c["weekend_fixed"]) == (
        0,
        360,
        60,
        120,
        False,
    )

    got = client.get(f"/api/components/{c['id']}", headers=_auth(token))
    assert got.status_code == 200 and got.json() == c


def test_list_includes_variants_and_per100(client, token, ids):
    egg = _make(client, token, ingredient_id=ids["egg"])
    skyr = _make(client, token, name="Skyr", kind="dairy", ingredient_id=ids["skyr"])
    r = client.post(
        f"/api/components/{egg['id']}/variants",
        json={"name": "Stück", "grams_per_unit": 60},
        headers=_auth(token),
    )
    assert r.status_code == 201
    v = r.json()
    assert (
        v["component_id"] == egg["id"] and v["ingredient_id"] == ids["egg"]
    )  # Standard: Zutat der Komponente
    assert v["grams_per_unit"] == 60 and v["per100"]["kcal"] == 140

    lst = client.get("/api/components", headers=_auth(token)).json()
    assert [c["name"] for c in lst] == ["Skyr", "Ei"]  # sortiert nach Art, dann Name
    assert [x["name"] for x in lst[1]["variants"]] == ["Stück"]
    # Salz aus Natrium berechnet, wenn kein Salzwert vorliegt (40 mg × 2,5 = 0,1 g)
    assert lst[0]["id"] == skyr["id"] and lst[0]["per100"]["salt_g"] == pytest.approx(0.1)


def test_create_validation_errors(client, token, ids):
    h = _auth(token)
    base = {"name": "Ei", "kind": "protein", "ingredient_id": ids["egg"]}
    # Pydantic-Grenzen
    for bad in (
        {"name": ""}, {"kind": "meat"}, {"min_g": -1}, {"step_g": 0}, {"max_g": 0}, {"typical_g": -5},
        {"ingredient_id": 0}, {"unbekannt": 1}, {"max_g": 100_000},
    ):  # fmt: skip
        assert client.post("/api/components", json=base | bad, headers=h).status_code == 422, bad
    # fachliche Regeln mit deutscher Meldung
    r = client.post("/api/components", json=base | {"min_g": 200, "max_g": 100}, headers=h)
    assert r.status_code == 422 and "Mindestmenge" in r.json()["detail"]
    r = client.post("/api/components", json=base | {"typical_g": 900}, headers=h)
    assert r.status_code == 422 and "übliche Menge" in r.json()["detail"]
    r = client.post("/api/components", json=base | {"ingredient_id": 424242}, headers=h)
    assert r.status_code == 422 and "Zutat" in r.json()["detail"]
    assert client.get("/api/components", headers=h).json() == []


def test_duplicate_name_is_409(client, token, ids):
    _make(client, token, ingredient_id=ids["egg"])
    r = client.post(
        "/api/components",
        json={"name": "ei", "kind": "protein", "ingredient_id": ids["egg"]},
        headers=_auth(token),
    )
    assert r.status_code == 409 and "gibt es schon" in r.json()["detail"]


def test_patch_component(client, token, ids):
    h = _auth(token)
    c = _make(client, token, ingredient_id=ids["egg"], typical_g=100)
    r = client.patch(
        f"/api/components/{c['id']}",
        json={
            "name": "Eier",
            "max_g": 300,
            "typical_g": None,
            "weekend_fixed": True,
            "ingredient_id": ids["skyr"],
        },
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["name"], body["max_g"], body["typical_g"], body["weekend_fixed"]) == (
        "Eier",
        300,
        None,
        True,
    )
    assert body["ingredient_name"] == "Testskyr" and body["min_g"] == 0  # nicht gesendet: unverändert

    assert client.patch(f"/api/components/{c['id']}", json={"min_g": 400}, headers=h).status_code == 422
    assert client.patch(f"/api/components/{c['id']}", json={"name": None}, headers=h).status_code == 422
    assert client.patch(f"/api/components/{c['id']}", json={"id": 7}, headers=h).status_code == 422
    assert (
        client.patch(f"/api/components/{c['id']}", json={"ingredient_id": 9999}, headers=h).status_code == 422
    )
    other = _make(client, token, name="Skyr", ingredient_id=ids["skyr"])
    r = client.patch(f"/api/components/{other['id']}", json={"name": "EIER"}, headers=h)
    assert r.status_code == 409
    assert client.get(f"/api/components/{c['id']}", headers=h).json()["max_g"] == 300


def test_delete_component_removes_variants(client, token, ids, session):
    h = _auth(token)
    c = _make(client, token, ingredient_id=ids["egg"])
    client.post(
        f"/api/components/{c['id']}/variants", json={"name": "Stück", "grams_per_unit": 60}, headers=h
    )
    assert client.delete(f"/api/components/{c['id']}", headers=h).status_code == 204
    assert client.get(f"/api/components/{c['id']}", headers=h).status_code == 404
    assert client.delete(f"/api/components/{c['id']}", headers=h).status_code == 404
    session.expire_all()
    assert session.query(Component).count() == 0 and session.query(ComponentVariant).count() == 0


def test_missing_component_is_404(client, token):
    h = _auth(token)
    assert client.get("/api/components/999", headers=h).status_code == 404
    assert client.patch("/api/components/999", json={"name": "A"}, headers=h).status_code == 404
    assert client.post("/api/components/999/variants", json={"name": "A"}, headers=h).status_code == 404
    assert client.patch("/api/components/999/variants/1", json={"name": "A"}, headers=h).status_code == 404
    assert client.delete("/api/components/999/variants/1", headers=h).status_code == 404
    assert "nicht gefunden" in client.get("/api/components/999", headers=h).json()["detail"]


def test_variant_endpoints(client, token, ids):
    h = _auth(token)
    c = _make(client, token, ingredient_id=ids["egg"])
    url = f"/api/components/{c['id']}/variants"
    v = client.post(url, json={"name": "Stück", "grams_per_unit": 60}, headers=h).json()

    # Duplikat und ungültige Werte
    assert client.post(url, json={"name": "stück"}, headers=h).status_code == 409
    assert client.post(url, json={"name": "X", "grams_per_unit": 0}, headers=h).status_code == 422
    assert client.post(url, json={"name": "X", "ingredient_id": 9999}, headers=h).status_code == 422
    assert client.post(url, json={"name": ""}, headers=h).status_code == 422

    r = client.patch(f"{url}/{v['id']}", json={"grams_per_unit": 55, "ingredient_id": ids["skyr"]}, headers=h)
    assert r.status_code == 200
    assert (r.json()["grams_per_unit"], r.json()["ingredient_name"]) == (55, "Testskyr")
    assert (
        client.patch(f"{url}/{v['id']}", json={"grams_per_unit": None}, headers=h).json()["grams_per_unit"]
        is None
    )
    assert client.patch(f"{url}/{v['id']}", json={"ingredient_id": None}, headers=h).status_code == 422
    w = client.post(url, json={"name": "Zweite"}, headers=h).json()
    assert client.patch(f"{url}/{w['id']}", json={"name": "Stück"}, headers=h).status_code == 409

    # Variante einer anderen Komponente: 404
    other = _make(client, token, name="Skyr", kind="dairy", ingredient_id=ids["skyr"])
    other_url = f"/api/components/{other['id']}/variants"
    assert client.patch(f"{other_url}/{v['id']}", json={"name": "Q"}, headers=h).status_code == 404
    assert client.delete(f"{other_url}/{v['id']}", headers=h).status_code == 404

    assert client.delete(f"{url}/{v['id']}", headers=h).status_code == 204
    assert client.delete(f"{url}/{v['id']}", headers=h).status_code == 404
    assert [x["name"] for x in client.get(f"/api/components/{c['id']}", headers=h).json()["variants"]] == [
        "Zweite"
    ]


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def test_seed_defaults_endpoint(client, token, session):
    h = _auth(token)
    session.add_all(
        [
            Ingredient(name="Hühnerei", source="manual", kcal_100=140),
            Ingredient(name="Skyr", source="manual", kcal_100=63),
        ]
    )
    session.commit()
    r = client.post("/api/components/seed-defaults", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert {"Ei", "Skyr", "Rührei (Wochenende)"} <= set(body["created"])
    assert "Hummus (Wochenende)" in body["missing"] and body["matched"]["Ei"] == "Hühnerei"
    assert body["variants_created"] >= 2

    again = client.post("/api/components/seed-defaults", headers=h).json()
    assert again["created"] == [] and set(again["skipped"]) == set(body["created"])
    names = [c["name"] for c in client.get("/api/components", headers=h).json()]
    assert len(names) == len(set(names)) == len(body["created"])


def test_seed_defaults_with_empty_catalog(client, token):
    body = client.post("/api/components/seed-defaults", headers=_auth(token)).json()
    assert body["created"] == [] and body["missing"]


# ---------------------------------------------------------------------------
# Mahlzeit berechnen
# ---------------------------------------------------------------------------


@pytest.fixture
def parts(client, token, ids):
    egg = _make(client, token, ingredient_id=ids["egg"], max_g=360, step_g=60)
    v = client.post(
        f"/api/components/{egg['id']}/variants",
        json={"name": "Stück", "grams_per_unit": 60},
        headers=_auth(token),
    ).json()
    bread = _make(client, token, name="Brot", kind="carb", ingredient_id=ids["bread"], max_g=200)
    skyr = _make(client, token, name="Skyr", kind="dairy", ingredient_id=ids["skyr"], max_g=400)
    return egg, v, bread, skyr


def test_meal_by_hand(client, token, parts):
    egg, v, bread, skyr = parts
    r = client.post(
        "/api/components/meal",
        json={
            "items": [
                {"component_id": egg["id"], "variant_id": v["id"], "units": 2},
                {"component_id": bread["id"], "grams": 100},
                {"component_id": skyr["id"], "grams": 250},
            ]
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 168 + 250 + 157,5 kcal; Protein 14,4 + 9 + 27,5; Salz 0,444 + 1,2 + 0,25 (Skyr aus Natrium: 0,25 g)
    assert body["total"]["kcal"] == pytest.approx(575.5)
    assert body["total"]["protein_g"] == pytest.approx(50.9)
    assert body["total"]["salt_g"] == pytest.approx(0.444 + 1.2 + 0.25, abs=0.01)
    assert body["total"]["micros"]["zinc_mg"] == pytest.approx(1.56)
    assert body["weight_g"] == pytest.approx(470)
    assert body["energy_density_kcal_per_100g"] == pytest.approx(122.4, abs=0.1)
    assert body["coverage"] == 1.0 and body["missing"] == []
    assert 0 <= body["satiety"]["score"] <= 100 and set(body["satiety"]["parts"]) >= {"density", "volume"}
    assert body["fit"] is None
    assert [ln["grams"] for ln in body["lines"]] == [120, 100, 250]
    assert body["lines"][0]["units"] == 2 and body["lines"][0]["variant_name"] == "Stück"
    assert sum(ln["nutrients"]["kcal"] for ln in body["lines"]) == pytest.approx(575.5, abs=0.1)
    assert any(n.startswith("Mahlzeit wiegt 470 g") for n in body["notes"])


def test_meal_validation(client, token, parts):
    egg, v, bread, _ = parts
    h = _auth(token)
    url = "/api/components/meal"

    def post(body):
        return client.post(url, json=body, headers=h)

    assert post({"items": []}).status_code == 422
    assert post({"items": [{"component_id": bread["id"]}]}).status_code == 422  # weder Gramm noch Stück
    assert post({"items": [{"component_id": bread["id"], "grams": 1, "units": 1}]}).status_code == 422
    assert post({"items": [{"component_id": bread["id"], "grams": -1}]}).status_code == 422
    assert (
        post({"items": [{"component_id": bread["id"], "grams": 1}], "date": TODAY.isoformat()}).status_code
        == 422
    )
    assert (
        post({"items": [{"component_id": bread["id"], "grams": 1}], "slot": "elevenses"}).status_code == 422
    )
    # Fachfehler aus dem Dienst: deutsche Meldung
    r = post({"items": [{"component_id": bread["id"], "units": 2}]})
    assert r.status_code == 422 and "Gewicht je Einheit" in r.json()["detail"]
    r = post({"items": [{"component_id": bread["id"], "variant_id": v["id"], "grams": 10}]})
    assert r.status_code == 422 and "gehört nicht zur Komponente" in r.json()["detail"]
    r = post({"items": [{"component_id": 9999, "grams": 10}]})
    assert r.status_code == 404 and "nicht gefunden" in r.json()["detail"]


def test_meal_with_fit_for_current_person(client, token, parts, session):
    _seed_person(session, shares={"breakfast": 1.0})
    egg, v, bread, skyr = parts
    r = client.post(
        "/api/components/meal",
        json={
            "items": [
                {"component_id": egg["id"], "variant_id": v["id"], "units": 2},
                {"component_id": bread["id"], "grams": 100},
                {"component_id": skyr["id"], "grams": 250},
            ],
            "date": TODAY.isoformat(),
            "slot": "breakfast",
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    fit = r.json()["fit"]
    assert fit["slot"] == "breakfast" and fit["date"] == TODAY.isoformat()
    target = fit["target"]
    assert target["kcal"] == pytest.approx(2200, abs=10)  # gesamtes Tagesziel im Frühstück
    assert fit["deviation_pct"]["kcal"] == pytest.approx(
        (575.5 - target["kcal"]) / target["kcal"] * 100, abs=0.1
    )
    assert 0 <= fit["fit_score"] < 50
    assert any("Energie 576 kcal" in n for n in fit["notes"])
    assert not any("Portion wäre" in n for n in fit["notes"])  # keine Portionsskalierung


def test_meal_fit_uses_today_when_date_missing(client, token, parts, session):
    # ohne Datum gilt heute (Gewichtsdaten bis heute vorhanden)
    pid = session.info["person_id"]
    for i in range(10):
        session.add(
            HealthDaily(person_id=pid, day=date.today() - timedelta(days=i), source="hae_zip", weight_kg=80.0)
        )
    session.commit()
    r = client.post(
        "/api/components/meal",
        json={"items": [{"component_id": parts[3]["id"], "grams": 100}], "slot": "breakfast"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["fit"]["date"] == date.today().isoformat()


def test_meal_fit_unavailable_targets_give_422(client, token, parts):
    r = client.post(
        "/api/components/meal",
        json={
            "items": [{"component_id": parts[3]["id"], "grams": 100}],
            "date": TODAY.isoformat(),
            "slot": "breakfast",
        },
        headers=_auth(token),
    )
    assert r.status_code == 422 and "Gewicht" in r.json()["detail"]
    # ohne Slot kein Fit nötig, also Erfolg
    ok = client.post(
        "/api/components/meal",
        json={"items": [{"component_id": parts[3]["id"], "grams": 100}]},
        headers=_auth(token),
    )
    assert ok.status_code == 200


def test_meal_slot_not_in_plan_gives_422(client, token, parts, session):
    _seed_person(session, shares={"breakfast": 1.0})
    r = client.post(
        "/api/components/meal",
        json={
            "items": [{"component_id": parts[3]["id"], "grams": 100}],
            "date": TODAY.isoformat(),
            "slot": "dinner",
        },
        headers=_auth(token),
    )
    assert r.status_code == 422 and "kommt im Plan" in r.json()["detail"]


def test_meal_single_meal_warning(client, token, parts, session):
    _seed_person(session, shares={"breakfast": 1.0}, single_meal_max_kcal=600)
    egg, v, bread, skyr = parts
    r = client.post(
        "/api/components/meal",
        json={
            "items": [
                {"component_id": bread["id"], "grams": 200},
                {"component_id": skyr["id"], "grams": 400},
            ],
            "date": TODAY.isoformat(),
            "slot": "breakfast",
        },
        headers=_auth(token),
    )
    codes = [w["code"] for w in r.json()["fit"]["warnings"]]
    assert "meal_too_large" in codes
