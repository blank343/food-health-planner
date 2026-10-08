"""Rezept-API (`/api/recipes`, `/api/recipe-lines`). Nur erfundene Daten, kein Netzwerk."""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api import recipes as recipes_api
from app.auth import generate_token, hash_token
from app.db import get_session
from app.importers import recipe_web
from app.importers.recipe_web import RecipeImportError
from app.importers.types import ImportedRecipe
from app.models import HealthDaily, Ingredient, PersonSettingsRow, Recipe, RecipeRating
from app.models import Person as PersonRow
from app.services import catalog

MONDAY = date(2026, 10, 5)
CATALOG = [
    ("Speisezwiebel roh", "G100100", 30.0, 1.2, 0.2, 5.0, {"piece_g": 80.0}),
    ("Hühnerei roh", "E100100", 140.0, 12.5, 9.5, 0.5, {"piece_g": 60.0}),
    ("Weizen Mehl, Type 405", "C100100", 340.0, 10.0, 1.0, 70.0, {}),
    ("Olivenöl", "Q100000", 900.0, 0.0, 100.0, 0.0, {"density_g_per_ml": 0.9}),
    ("Speisesalz/Siedesalz/Tafelsalz", "R100000", 0.0, 0.0, 0.0, 0.0, {"salt_100": 100.0}),
]
LINES = ["200 g Mehl", "2 Eier", "1 EL Olivenöl", "1 Prise Salz", "1 Zwiebel"]


@pytest.fixture
def ings(session):
    out = {}
    for name, code, kcal, protein, fat, carb, extra in CATALOG:
        ing = Ingredient(
            name=name, source="bls", source_code=code, kcal_100=kcal, protein_100=protein, fat_100=fat,
            carb_100=carb, **extra,
        )  # fmt: skip
        session.add(ing)
        out[name] = ing
    session.commit()
    catalog.ensure_seed_synonyms(session)
    return out


def _add_person(session, name, sex, health: bool) -> dict[str, str]:
    tok = generate_token()
    p = PersonRow(
        name=name, sex=sex, birth_date=date(1992, 2, 21), height_cm=180.0, token_hash=hash_token(tok)
    )
    session.add(p)
    session.commit()
    if health:
        for i in range(40):
            session.add(
                HealthDaily(
                    person_id=p.id, day=MONDAY - timedelta(days=39 - i), source="hae_zip",
                    weight_kg=80.0, active_kcal=750.0, basal_kcal=2000.0,
                )
            )  # fmt: skip
        session.commit()
    session.info[name] = p.id
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def a(session):
    return _add_person(session, "Test A", "m", health=True)


@pytest.fixture
def b(session):
    return _add_person(session, "Test B", "f", health=False)


@pytest.fixture
def client(engine):
    app = FastAPI()
    app.include_router(recipes_api.router, prefix="/api")
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make(client, headers, **kw) -> dict:
    body = {"title": "Zwiebelkuchen", "servings": 2, "lines": [{"raw_text": t} for t in LINES]}
    body.update(kw)
    r = client.post("/api/recipes", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def fake_import(monkeypatch, imported=None, error=None):
    calls = []

    def fake(url):
        calls.append(url)
        if error:
            raise error
        return imported

    monkeypatch.setattr(recipe_web, "import_recipe_url", fake)
    return calls


def imported_recipe(**kw) -> ImportedRecipe:
    base = {
        "title": "Importierter Kuchen",
        "source_url": "https://www.example.org/kuchen",
        "source_site": "example.org",
        "servings": 2.0,
        "prep_min": 15,
        "cook_min": 30,
        "instructions": "Alles mischen.\nBacken.",
        "ingredient_lines": [*LINES, "1 Dose Kichererbsen"],
        "site_nutrients": {"kcal": 480.0},
        "warnings": ["Keine Zeitangabe gefunden"],
    }
    base.update(kw)
    return ImportedRecipe(**base)


# ---------------------------------------------------------------------------
# Zugriff und Anlegen
# ---------------------------------------------------------------------------


def test_requires_token(client):
    calls = [
        ("get", "/api/recipes"),
        ("post", "/api/recipes"),
        ("post", "/api/recipes/import-preview"),
        ("post", "/api/recipes/import"),
        ("get", "/api/recipes/1"),
        ("patch", "/api/recipes/1"),
        ("delete", "/api/recipes/1"),
        ("get", "/api/recipes/1/fit?slot=lunch"),
        ("put", "/api/recipes/1/rating"),
        ("delete", "/api/recipes/1/rating"),
        ("get", "/api/recipe-lines/unassigned"),
        ("post", "/api/recipe-lines/1/assign"),
    ]
    for method, url in calls:
        assert getattr(client, method)(url).status_code == 401, (method, url)


def test_create_recipe_returns_detail_with_nutrition(client, ings, a):
    d = make(client, a, tag={"slot_types": ["lunch"], "warm": True}, favorite=True, prep_min=10)
    assert d["status"] == "ready" and d["servings"] == 2 and d["favorite"] is True and d["prep_min"] == 10
    assert d["tag"]["slot_types"] == ["lunch"] and d["tag"]["warm"] is True
    assert [ln["raw_text"] for ln in d["lines"]] == LINES
    assert [ln["grams"] for ln in d["lines"]] == [200.0, 120.0, 13.5, 0.4, 80.0]
    egg = d["lines"][1]
    assert egg["ingredient"]["name"] == "Hühnerei roh" and egg["nutrients"]["kcal"] == 168.0
    assert d["total"]["kcal"] == pytest.approx(993.5) and d["per_serving"]["kcal"] == pytest.approx(
        496.8, abs=0.1
    )
    assert (d["kcal"], d["protein_g"], d["fat_g"], d["carb_g"]) == (
        pytest.approx(496.8, abs=0.1), pytest.approx(17.98), pytest.approx(13.53), pytest.approx(72.3),
    )  # fmt: skip
    assert d["per_serving"]["salt_g"] == pytest.approx(0.2)
    assert d["total_weight_g"] == pytest.approx(413.9) and d["serving_weight_g"] == pytest.approx(
        207.0, abs=0.1
    )
    assert d["energy_density_kcal_per_100g"] == pytest.approx(240.0, abs=0.5)
    assert d["coverage"] == 1.0 and d["missing"] == []
    assert 0 <= d["satiety"]["score"] <= 100 and set(d["satiety"]["parts"]) == {
        "density", "volume", "protein", "fiber", "warm",
    }  # fmt: skip
    assert d["satiety"]["parts"]["warm"] == 1.0
    assert d["ratings"] == [] and d["my_rating"] is None and d["avg_rating"] is None and d["fit"] is None
    assert client.get(f"/api/recipes/{d['id']}", headers=a).json() == d


def test_create_with_fixed_ingredient_lines(client, ings, a):
    d = make(
        client, a, lines=[{"ingredient_id": ings["Olivenöl"].id, "grams": 20}, {"raw_text": "1 Bund Rucola"}]
    )
    assert d["status"] == "needs_review"
    assert d["lines"][0]["ingredient"]["id"] == ings["Olivenöl"].id and d["lines"][0]["grams"] == 20.0
    assert d["lines"][1]["ingredient"] is None and d["missing"] == ["1 Bund Rucola"]
    assert d["coverage"] == 0.5


def test_create_validation(client, ings, a):
    base = {"title": "X", "lines": [{"raw_text": "1 Zwiebel"}]}
    bad_bodies = [
        {**base, "title": ""},
        {**base, "title": "x" * 301},
        {**base, "servings": 0},
        {**base, "servings": 1000},
        {**base, "prep_min": -1},
        {**base, "source_url": "ftp://example.org/x"},
        {**base, "image_url": "javascript:alert(1)"},
        {**base, "tag": {"slot_types": ["brunch"]}},
        {**base, "lines": [{}]},
        {**base, "lines": [{"ingredient_id": 1}]},
        {**base, "lines": [{"raw_text": "x" * 401}]},
        {**base, "lines": [{"ingredient_id": 1, "grams": -5}]},
        {**base, "lines": [{"raw_text": "1 Zwiebel"}] * 101},
        {"lines": []},
    ]
    for body in bad_bodies:
        assert client.post("/api/recipes", json=body, headers=a).status_code == 422, str(body)[:80]
    missing_ing = client.post(
        "/api/recipes", json={**base, "lines": [{"ingredient_id": 9999, "grams": 5}]}, headers=a
    )
    assert missing_ing.status_code == 422 and "Zutat 9999" in missing_ing.json()["detail"]
    assert client.post("/api/recipes", json=base, headers=a).status_code == 201
    assert (
        client.get("/api/recipes", headers=a).json()["total"] == 1
    )  # die fehlerhaften haben nichts angelegt


def test_get_404(client, a):
    r = client.get("/api/recipes/9999", headers=a)
    assert r.status_code == 404 and "nicht gefunden" in r.json()["detail"]
    assert client.patch("/api/recipes/9999", json={"title": "x"}, headers=a).status_code == 404
    assert client.delete("/api/recipes/9999", headers=a).status_code == 404
    assert client.get("/api/recipes/9999/fit", params={"slot": "lunch"}, headers=a).status_code == 404


# ---------------------------------------------------------------------------
# Ändern und Löschen
# ---------------------------------------------------------------------------


def test_patch_recipe(client, ings, a, session):
    d = make(client, a)
    url = f"/api/recipes/{d['id']}"
    r = client.patch(
        url, json={"title": "Neuer Titel", "servings": 4, "tag": {"batch_cookable": True}}, headers=a
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Neuer Titel" and body["servings"] == 4 and body["tag"]["batch_cookable"] is True
    assert body["kcal"] == pytest.approx(248.4, abs=0.1)  # halbe Portion
    assert body["lines"] == d["lines"] and body["total"] == d["total"]  # Zeilen unverändert

    # Zeilen ersetzen: `id` behält Zuordnung und Zeile
    egg = d["lines"][1]
    r = client.patch(
        url,
        json={
            "lines": [
                {"id": egg["id"], "raw_text": egg["raw_text"]},
                {"raw_text": "100 g Dinkelmehl"},
            ]
        },
        headers=a,
    )
    lines = r.json()["lines"]
    assert [ln["raw_text"] for ln in lines] == ["2 Eier", "100 g Dinkelmehl"]
    assert lines[0]["id"] == egg["id"] and lines[0]["ingredient"]["name"] == "Hühnerei roh"
    assert r.json()["status"] == "needs_review"  # die zweite Zeile ist unbekannt

    for bad in ({"title": None}, {"servings": None}, {"lines": None}, {"favorite": None}, {"title": ""}):
        assert client.patch(url, json=bad, headers=a).status_code == 422, bad
    assert client.patch(url, json={"lines": [{"id": 424242, "raw_text": "x"}]}, headers=a).status_code == 422
    assert client.patch(url, json={"tag": None}, headers=a).status_code == 200  # tag null: nichts ändern


def test_delete_recipe_removes_everything(client, ings, a, b, session):
    d = make(client, a)
    client.put(f"/api/recipes/{d['id']}/rating", json={"rating": 4}, headers=a)
    assert client.delete(f"/api/recipes/{d['id']}", headers=b).status_code == 204  # gemeinsam pflegbar
    assert client.get(f"/api/recipes/{d['id']}", headers=a).status_code == 404
    assert session.scalar(select(func.count()).select_from(RecipeRating)) == 0
    assert session.scalar(select(func.count()).select_from(Recipe)) == 0


# ---------------------------------------------------------------------------
# Liste
# ---------------------------------------------------------------------------


@pytest.fixture
def library(client, ings, a):
    light = make(
        client, a, title="Zwiebelsuppe", servings=1, tag={"slot_types": ["lunch", "dinner"], "warm": True},
        lines=[{"raw_text": "250 g Zwiebel"}, {"raw_text": "10 g Olivenöl"}],
    )  # fmt: skip
    rich = make(client, a, title="Kuchen", favorite=True, tag={"slot_types": ["breakfast"]})
    open_ = make(
        client, a, title="Bohnentopf", lines=[{"raw_text": "1 Dose Bohnen"}, {"raw_text": "1 Zwiebel"}]
    )
    return {"light": light, "rich": rich, "open": open_}


def test_list_cards(client, library, a):
    r = client.get("/api/recipes", headers=a).json()
    assert r["total"] == 3 and r["limit"] == 50 and r["offset"] == 0
    assert [c["title"] for c in r["items"]] == ["Bohnentopf", "Kuchen", "Zwiebelsuppe"]  # nach Titel
    soup = r["items"][2]
    assert set(soup) >= {
        "id", "title", "status", "servings", "prep_min", "cook_min", "tag", "kcal", "protein_g", "fat_g",
        "carb_g", "serving_weight_g", "satiety_score", "coverage", "my_rating", "avg_rating", "fit_score",
    }  # fmt: skip
    assert soup["kcal"] == pytest.approx(250 * 0.3 + 10 * 9.0, abs=0.1) and soup["serving_weight_g"] == 260.0
    assert soup["status"] == "ready" and soup["tag"]["warm"] is True and soup["fit_score"] is None
    assert r["items"][0]["status"] == "needs_review" and r["items"][0]["coverage"] == 0.5


def test_list_filters(client, library, a):
    def titles(**params):
        r = client.get("/api/recipes", params=params, headers=a)
        assert r.status_code == 200, r.text
        return [c["title"] for c in r.json()["items"]]

    assert titles(q="suppe") == ["Zwiebelsuppe"]
    assert titles(q="%") == []
    assert titles(favorite="true") == ["Kuchen"]
    assert titles(favorite="false") == ["Bohnentopf", "Zwiebelsuppe"]
    assert titles(status="needs_review") == ["Bohnentopf"]
    assert titles(slot="dinner") == ["Zwiebelsuppe"]
    assert titles(slot="breakfast") == ["Kuchen"]
    assert titles(slot="lunch", include_untagged="true") == ["Bohnentopf", "Zwiebelsuppe"]
    assert titles(limit=1, offset=1) == ["Kuchen"]
    for bad in (
        {"slot": "brunch"},
        {"status": "x"},
        {"sort": "x"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ):
        assert client.get("/api/recipes", params=bad, headers=a).status_code == 422, bad


def test_list_sorting(client, library, a):
    def titles(sort):
        return [
            c["title"] for c in client.get("/api/recipes", params={"sort": sort}, headers=a).json()["items"]
        ]

    assert titles("newest") == ["Bohnentopf", "Kuchen", "Zwiebelsuppe"]
    assert titles("kcal")[0] == "Bohnentopf"  # nur 1 Zeile mit Werten: die wenigsten kcal
    assert titles("protein")[0] == "Kuchen"
    client.put(f"/api/recipes/{library['light']['id']}/rating", json={"rating": 5}, headers=a)
    assert titles("rating")[0] == "Zwiebelsuppe"
    assert set(titles("satiety")) == {"Zwiebelsuppe", "Kuchen", "Bohnentopf"}


def test_list_with_fit_and_sort_by_fit(client, library, a):
    params = {"fit_slot": "lunch", "fit_date": MONDAY.isoformat(), "sort": "fit"}
    r = client.get("/api/recipes", params=params, headers=a)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    scores = [c["fit_score"] for c in items]
    assert all(s is not None for s in scores) and scores == sorted(scores, reverse=True)
    assert all(c["fit_factor"] is not None for c in items)
    # gleiche Zahl wie der Einzel-Endpunkt
    single = client.get(
        f"/api/recipes/{items[0]['id']}/fit", params={"slot": "lunch", "date": MONDAY.isoformat()}, headers=a
    ).json()
    assert single["fit_score"] == items[0]["fit_score"] and single["factor"] == items[0]["fit_factor"]
    # ohne sort=fit bleibt die Titelreihenfolge
    plain = client.get("/api/recipes", params={**params, "sort": "title"}, headers=a).json()["items"]
    assert [c["title"] for c in plain] == ["Bohnentopf", "Kuchen", "Zwiebelsuppe"]


def test_list_fit_errors_are_422(client, library, a, b, session):
    no_slot = client.get("/api/recipes", params={"sort": "fit"}, headers=a)
    assert no_slot.status_code == 422 and "fit_slot" in no_slot.json()["detail"]
    params = {"fit_slot": "lunch", "fit_date": MONDAY.isoformat()}
    no_data = client.get("/api/recipes", params=params, headers=b)  # Person B hat keine Gesundheitsdaten
    assert no_data.status_code == 422 and "Gewicht" in no_data.json()["detail"]
    snack = client.get("/api/recipes", params={**params, "fit_slot": "snack"}, headers=a)
    assert snack.status_code == 422 and "nicht vorgesehen" in snack.json()["detail"]
    assert client.get("/api/recipes", params={**params, "fit_slot": "brunch"}, headers=a).status_code == 422


def test_fit_is_always_for_logged_in_person(client, library, a, b, session):
    """Es gibt keinen person_id-Parameter: ein fremder Wert ändert nichts, B bekommt keine Daten von A."""
    rid = library["light"]["id"]
    params = {"slot": "lunch", "date": MONDAY.isoformat(), "person_id": session.info["Test A"]}
    assert client.get(f"/api/recipes/{rid}/fit", params=params, headers=a).status_code == 200
    r = client.get(f"/api/recipes/{rid}/fit", params=params, headers=b)
    assert r.status_code == 422 and "Gewicht" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Passung
# ---------------------------------------------------------------------------


def test_fit_endpoint_values(client, ings, a):
    d = make(client, a)
    r = client.get(
        f"/api/recipes/{d['id']}/fit", params={"slot": "lunch", "date": MONDAY.isoformat()}, headers=a
    )
    assert r.status_code == 200
    fit = r.json()
    assert fit["slot"] == "lunch" and fit["date"] == MONDAY.isoformat()
    target = fit["slot_target"]
    assert target["kcal"] == pytest.approx(825, abs=2)  # 30 % von ~2750 kcal
    assert fit["factor"] == pytest.approx(target["kcal"] / 496.75, abs=0.01)
    assert fit["scaled"]["kcal"] == pytest.approx(target["kcal"], abs=1)
    assert fit["deviation_pct"]["kcal"] == pytest.approx(0, abs=1)
    assert fit["grams"] == pytest.approx(fit["factor"] * d["serving_weight_g"], abs=0.5)
    assert 0 <= fit["fit_score"] <= 100 and any("fach" in n for n in fit["notes"])
    assert set(fit["deviation_pct"]) == {"kcal", "protein", "fat", "carb"} and fit["warnings"] == []


def test_fit_single_meal_warning_and_errors(client, ings, a, session):
    d = make(client, a)
    session.add(PersonSettingsRow(person_id=session.info["Test A"], data={"single_meal_max_kcal": 300}))
    session.commit()
    fit = client.get(
        f"/api/recipes/{d['id']}/fit", params={"slot": "lunch", "date": MONDAY.isoformat()}, headers=a
    )
    assert [w["code"] for w in fit.json()["warnings"]] == ["meal_too_large"]
    assert client.get(f"/api/recipes/{d['id']}/fit", headers=a).status_code == 422  # slot fehlt
    bad = client.get(f"/api/recipes/{d['id']}/fit", params={"slot": "brunch"}, headers=a)
    assert bad.status_code == 422
    snack = client.get(
        f"/api/recipes/{d['id']}/fit", params={"slot": "snack", "date": MONDAY.isoformat()}, headers=a
    )
    assert snack.status_code == 422 and "nicht vorgesehen" in snack.json()["detail"]


def test_detail_with_optional_fit(client, ings, a):
    d = make(client, a)
    params = {"fit_slot": "dinner", "fit_date": MONDAY.isoformat()}
    r = client.get(f"/api/recipes/{d['id']}", params=params, headers=a)
    assert r.status_code == 200 and r.json()["fit"]["slot"] == "dinner"
    assert r.json()["fit_score"] == r.json()["fit"]["fit_score"]
    no_fit = client.get(f"/api/recipes/{d['id']}", params={**params, "fit_slot": "snack"}, headers=a)
    assert no_fit.status_code == 422


# ---------------------------------------------------------------------------
# Bewertungen
# ---------------------------------------------------------------------------


def test_ratings_are_separate_per_person(client, ings, a, b):
    d = make(client, a)
    url = f"/api/recipes/{d['id']}/rating"
    put = client.put(url, json={"rating": 5}, headers=a).json()
    assert put["recipe_id"] == d["id"] and put["rating"] == 5
    assert (
        put["person_id"] == client.get(f"/api/recipes/{d['id']}", headers=a).json()["ratings"][0]["person_id"]
    )
    assert client.put(url, json={"rating": 2}, headers=b).status_code == 200
    mine_a = client.get(f"/api/recipes/{d['id']}", headers=a).json()
    mine_b = client.get(f"/api/recipes/{d['id']}", headers=b).json()
    assert (mine_a["my_rating"], mine_b["my_rating"]) == (5, 2)
    assert mine_a["avg_rating"] == 3.5
    assert [(r["person_name"], r["rating"]) for r in mine_a["ratings"]] == [("Test A", 5), ("Test B", 2)]
    listing = client.get("/api/recipes", headers=b).json()["items"][0]
    assert listing["my_rating"] == 2 and listing["avg_rating"] == 3.5

    client.put(url, json={"rating": 3}, headers=a)  # ändern statt doppelt
    assert client.get(f"/api/recipes/{d['id']}", headers=a).json()["my_rating"] == 3
    assert client.delete(url, headers=a).status_code == 204
    after = client.get(f"/api/recipes/{d['id']}", headers=b).json()
    assert after["my_rating"] == 2 and [r["person_name"] for r in after["ratings"]] == ["Test B"]
    assert client.delete(url, headers=a).status_code == 204  # nochmal: kein Fehler


def test_rating_validation_and_404(client, ings, a):
    d = make(client, a)
    url = f"/api/recipes/{d['id']}/rating"
    for bad in ({"rating": 0}, {"rating": 6}, {"rating": "gut"}, {}):
        assert client.put(url, json=bad, headers=a).status_code == 422, bad
    assert client.put("/api/recipes/9999/rating", json={"rating": 3}, headers=a).status_code == 404
    assert client.delete("/api/recipes/9999/rating", headers=a).status_code == 404


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def test_import_preview_saves_nothing(client, ings, a, monkeypatch, session):
    calls = fake_import(monkeypatch, imported_recipe())
    r = client.post(
        "/api/recipes/import-preview", json={"url": " https://www.example.org/kuchen "}, headers=a
    )
    assert r.status_code == 200, r.text
    assert calls == ["https://www.example.org/kuchen"]
    body = r.json()
    assert (
        body["title"] == "Importierter Kuchen"
        and body["servings"] == 2.0
        and body["site_nutrients"] == {"kcal": 480.0}
    )
    assert body["warnings"] == ["Keine Zeitangabe gefunden"]
    flour, egg, _, _, _, chickpeas = body["lines"]
    assert (
        flour["name"] == "Mehl"
        and flour["grams"] == 200.0
        and flour["ingredient_name"] == "Weizen Mehl, Type 405"
    )
    assert flour["matches"][0]["via"] == "synonym" and flour["matches"][0]["score"] == 100.0
    assert egg["ingredient_id"] == ings["Hühnerei roh"].id and egg["grams"] == 120.0
    assert (
        chickpeas["ingredient_id"] is None
        and chickpeas["ingredient_name"] is None
        and chickpeas["grams"] == 400.0
    )
    assert session.scalar(select(func.count()).select_from(Recipe)) == 0


def test_import_saves_and_returns_detail(client, ings, a, monkeypatch, session):
    fake_import(monkeypatch, imported_recipe())
    r = client.post("/api/recipes/import", json={"url": "https://www.example.org/kuchen"}, headers=a)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["title"] == "Importierter Kuchen" and d["source_url"] == "https://www.example.org/kuchen"
    assert d["source_site"] == "example.org" and d["prep_min"] == 15 and d["cook_min"] == 30
    assert d["instructions"] == "Alles mischen.\nBacken." and d["status"] == "needs_review"
    assert d["warnings"] == ["Keine Zeitangabe gefunden"]
    assert d["missing"] == ["1 Dose Kichererbsen"] and d["coverage"] == pytest.approx(5 / 6, abs=0.001)
    assert d["notes"] is None or "Hinweis" in d["notes"]
    assert (
        client.get(f"/api/recipes/{d['id']}", headers=a).json()["warnings"] == []
    )  # nur direkt nach dem Import
    again = client.post("/api/recipes/import", json={"url": "https://www.example.org/kuchen"}, headers=a)
    assert again.status_code == 409 and f"ID {d['id']}" in again.json()["detail"]
    assert session.scalar(select(func.count()).select_from(Recipe)) == 1


def test_import_notes_large_deviation_from_site_values(client, ings, a, monkeypatch):
    fake_import(monkeypatch, imported_recipe(site_nutrients={"kcal": 100.0}))
    d = client.post("/api/recipes/import", json={"url": "https://www.example.org/kuchen"}, headers=a).json()
    assert d["notes"] and "100 kcal" in d["notes"]


def test_import_errors(client, a, monkeypatch, session):
    fake_import(
        monkeypatch, error=RecipeImportError("Auf der Seite wurde kein Rezept (schema.org/Recipe) gefunden")
    )
    r = client.post("/api/recipes/import-preview", json={"url": "https://example.org/x"}, headers=a)
    assert r.status_code == 422 and "kein Rezept" in r.json()["detail"]
    fake_import(monkeypatch, error=RecipeImportError("Seite nicht gefunden (HTTP 404)"))
    for path in ("import-preview", "import"):
        r = client.post(f"/api/recipes/{path}", json={"url": "https://example.org/x"}, headers=a)
        assert r.status_code == 502 and "404" in r.json()["detail"]
    fake_import(monkeypatch, error=RecipeImportError("robots.txt verbietet den Abruf"))
    assert (
        client.post("/api/recipes/import", json={"url": "https://example.org/x"}, headers=a).status_code
        == 422
    )
    for bad in (
        {"url": "ftp://example.org/x"},
        {"url": "kein link"},
        {"url": ""},
        {},
        {"url": "https://x.de/" + "a" * 600},
    ):
        assert client.post("/api/recipes/import", json=bad, headers=a).status_code == 422, bad
    assert session.scalar(select(func.count()).select_from(Recipe)) == 0


def test_no_stack_trace_on_unexpected_input(client, a):
    r = client.post("/api/recipes", content=b"{kaputt", headers={**a, "Content-Type": "application/json"})
    assert r.status_code == 422 and "Traceback" not in r.text


# ---------------------------------------------------------------------------
# Prüfliste
# ---------------------------------------------------------------------------


def _unknown_recipes(client, headers):
    one = make(
        client, headers, title="Eins", lines=[{"raw_text": "200 g Mehl"}, {"raw_text": "50 g Dinkelflocken"}]
    )
    two = make(
        client, headers, title="Zwei", lines=[{"raw_text": "2 EL Dinkelflocken"}, {"raw_text": "1 Ei"}]
    )
    return one, two


def test_unassigned_list_and_assign(client, ings, a, session):
    one, two = _unknown_recipes(client, a)
    assert one["status"] == "needs_review" and two["status"] == "needs_review"
    r = client.get("/api/recipe-lines/unassigned", headers=a)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["limit"] == 50
    first = body["items"][0]
    assert (
        first["recipe_id"] == one["id"]
        and first["recipe_title"] == "Eins"
        and first["name"] == "Dinkelflocken"
    )
    assert (
        first["raw_text"] == "50 g Dinkelflocken" and first["similar_count"] == 2 and first["quantity"] == 50
    )
    assert (
        client.get("/api/recipe-lines/unassigned", params={"limit": 1, "offset": 1}, headers=a).json()[
            "items"
        ][0]["recipe_id"]
        == two["id"]
    )

    oats = Ingredient(name="Hafer Flocken", source="bls", source_code="C200000", kcal_100=370.0)
    session.add(oats)
    session.commit()
    done = client.post(
        f"/api/recipe-lines/{first['line_id']}/assign", json={"ingredient_id": oats.id}, headers=a
    )
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["synonym"] == "dinkelflocke" and len(out["assigned_line_ids"]) == 2
    assert out["recipe_ids"] == sorted([one["id"], two["id"]])
    assert out["line"]["ingredient"]["name"] == "Hafer Flocken" and out["line"]["grams"] == 50.0
    assert client.get("/api/recipe-lines/unassigned", headers=a).json() == {
        "items": [], "total": 0, "limit": 50, "offset": 0,
    }  # fmt: skip
    for rid in (one, two):
        assert client.get(f"/api/recipes/{rid['id']}", headers=a).json()["status"] == "ready"
    # das Synonym ist jetzt am Zutat-Eintrag sichtbar
    assert (
        session.query(catalog.IngredientSynonym).filter_by(alias="dinkelflocke").one().ingredient_id
        == oats.id
    )


def test_assign_without_synonym_and_errors(client, ings, a, session):
    one, two = _unknown_recipes(client, a)
    line_id = client.get("/api/recipe-lines/unassigned", headers=a).json()["items"][0]["line_id"]
    ing_id = ings["Olivenöl"].id
    r = client.post(
        f"/api/recipe-lines/{line_id}/assign",
        json={"ingredient_id": ing_id, "save_synonym": False},
        headers=a,
    )
    assert r.status_code == 200 and r.json()["synonym"] is None and r.json()["assigned_line_ids"] == [line_id]
    assert client.get("/api/recipe-lines/unassigned", headers=a).json()["total"] == 1
    assert (
        client.post("/api/recipe-lines/9999/assign", json={"ingredient_id": ing_id}, headers=a).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/recipe-lines/{line_id}/assign", json={"ingredient_id": 9999}, headers=a
        ).status_code
        == 404
    )
    assert client.post(f"/api/recipe-lines/{line_id}/assign", json={}, headers=a).status_code == 422
    assert client.get("/api/recipe-lines/unassigned", params={"limit": 0}, headers=a).status_code == 422
