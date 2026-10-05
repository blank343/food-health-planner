"""CRUD-API: Profil, Einstellungen, Ziele, Supplemente, Regeln, Trainingsplan. Nur erfundene Daten."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.auth import generate_token, hash_token
from app.calc import defaults
from app.db import get_session
from app.main import app
from app.models import Person


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


def _make(session, name, sex="f") -> dict[str, str]:
    token = generate_token()
    session.add(Person(name=name, sex=sex, birth_date=date(1990, 5, 1), token_hash=hash_token(token)))
    session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def a(client, session):
    return _make(session, "Person A")


@pytest.fixture
def b(client, session):
    return _make(session, "Person B", "m")


# --------------------------------------------------------------------------- Profil


def test_patch_me(client, a):
    resp = client.patch("/api/me", json={"height_cm": 171.5, "name": "  Neuer Name "}, headers=a)
    assert resp.status_code == 200
    assert resp.json()["height_cm"] == 171.5
    assert resp.json()["name"] == "Neuer Name"
    assert client.get("/api/me", headers=a).json()["name"] == "Neuer Name"


def test_patch_me_name_conflict(client, a, b):
    resp = client.patch("/api/me", json={"name": "Person B"}, headers=a)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Dieser Name ist bereits vergeben."
    # eigener Name bleibt erlaubt
    assert client.patch("/api/me", json={"name": "Person A"}, headers=a).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"height_cm": 20},
        {"sex": "x"},
        {"birth_date": "2999-01-01"},
        {"name": ""},
        {"name": None},
        {"is_active": False},  # unbekanntes Feld
        {"token_hash": "x"},
    ],
)
def test_patch_me_validation(client, a, body):
    assert client.patch("/api/me", json=body, headers=a).status_code == 422


# --------------------------------------------------------------------------- Einstellungen


def test_settings_defaults_merged(client, a):
    resp = client.get("/api/me/settings", headers=a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"] == {}
    assert data["effective"]["protein_floor_g_per_kg"] == defaults.PROTEIN_FLOOR_G_PER_KG
    assert data["effective"]["source_priority"] == list(defaults.SOURCE_PRIORITY)
    assert data["effective"]["weight_floor_kg"] is None


def test_settings_put_replaces(client, a):
    resp = client.put(
        "/api/me/settings", json={"weight_floor_kg": 62.5, "use_katch_mcardle": True}, headers=a
    )
    assert resp.status_code == 200
    assert resp.json()["stored"] == {"weight_floor_kg": 62.5, "use_katch_mcardle": True}
    assert resp.json()["effective"]["weight_floor_kg"] == 62.5
    assert resp.json()["effective"]["kcal_per_kg"] == defaults.KCAL_PER_KG_BODY_MASS

    resp = client.put("/api/me/settings", json={"bf_floor_pct": 12}, headers=a)
    assert resp.json()["stored"] == {"bf_floor_pct": 12}
    got = client.get("/api/me/settings", headers=a).json()
    assert got["stored"] == {"bf_floor_pct": 12}
    assert got["effective"]["weight_floor_kg"] is None  # ersetzt, nicht zusammengeführt
    assert got["effective"]["use_katch_mcardle"] is False


def test_settings_validation(client, a):
    assert client.put("/api/me/settings", json={"kcal_per_kg": -1}, headers=a).status_code == 422
    assert client.put("/api/me/settings", json={"bf_floor_pct": 99}, headers=a).status_code == 422
    assert client.put("/api/me/settings", json={"slot_shares": {"x": -1}}, headers=a).status_code == 422
    resp = client.put("/api/me/settings", json={"unbekannt": 1}, headers=a)
    assert resp.status_code == 422
    assert client.get("/api/me/settings", headers=a).json()["stored"] == {}


def test_settings_isolated(client, a, b):
    client.put("/api/me/settings", json={"weight_floor_kg": 60}, headers=a)
    assert client.get("/api/me/settings", headers=b).json()["stored"] == {}


# --------------------------------------------------------------------------- Ziele


def goal(**kw):
    return {"kind": "lose", "rate_kg_per_week": 0.5, "protein_g_per_kg": 2.0, "fat_pct": 30, **kw}


def test_goals_versioning_and_active(client, a):
    today = date.today()
    first = client.post("/api/me/goals", json=goal(valid_from="2026-01-01", note="Start"), headers=a)
    assert first.status_code == 201
    assert first.json()["valid_from"] == "2026-01-01"
    client.post("/api/me/goals", json=goal(kind="maintain", valid_from="2026-06-01"), headers=a)
    no_date = client.post("/api/me/goals", json=goal(rate_kg_per_week=0.25), headers=a).json()
    assert no_date["valid_from"] == today.isoformat()

    listing = client.get("/api/me/goals", headers=a).json()
    assert [g["valid_from"] for g in listing] == sorted((g["valid_from"] for g in listing), reverse=True)
    assert len(listing) == 3

    act = client.get("/api/me/goals/active", params={"on": "2026-03-15"}, headers=a)
    assert act.json()["kind"] == "lose" and act.json()["note"] == "Start"
    assert (
        client.get("/api/me/goals/active", params={"on": "2026-06-01"}, headers=a).json()["kind"]
        == "maintain"
    )
    assert client.get("/api/me/goals/active", headers=a).json()["id"] == no_date["id"]


def test_goal_active_none_404(client, a):
    resp = client.get("/api/me/goals/active", params={"on": "2026-03-15"}, headers=a)
    assert resp.status_code == 404
    assert "2026-03-15" in resp.json()["detail"]
    client.post("/api/me/goals", json=goal(valid_from="2026-04-01"), headers=a)
    assert client.get("/api/me/goals/active", params={"on": "2026-03-15"}, headers=a).status_code == 404


def test_goal_same_day_newest_wins(client, a):
    client.post("/api/me/goals", json=goal(valid_from="2026-01-01", rate_kg_per_week=0.2), headers=a)
    newer = client.post("/api/me/goals", json=goal(valid_from="2026-01-01", rate_kg_per_week=0.4), headers=a)
    act = client.get("/api/me/goals/active", params={"on": "2026-02-01"}, headers=a).json()
    assert act["id"] == newer.json()["id"]


def test_goals_no_update_or_delete(client, a):
    gid = client.post("/api/me/goals", json=goal(), headers=a).json()["id"]
    assert client.delete(f"/api/me/goals/{gid}", headers=a).status_code in (404, 405)
    assert client.put(f"/api/me/goals/{gid}", json=goal(), headers=a).status_code in (404, 405)


def test_goals_isolated(client, a, b):
    client.post("/api/me/goals", json=goal(valid_from="2026-01-01"), headers=a)
    assert client.get("/api/me/goals", headers=b).json() == []
    assert client.get("/api/me/goals/active", params={"on": "2026-02-01"}, headers=b).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        goal(kind="shrink"),
        goal(rate_kg_per_week=-0.1),
        goal(protein_g_per_kg=0),
        goal(fat_pct=61),
        goal(fat_pct=-1),
        goal(valid_from="kein-datum"),
        {"rate_kg_per_week": 0.5},
        goal(extra="x"),
    ],
)
def test_goal_validation(client, a, body):
    assert client.post("/api/me/goals", json=body, headers=a).status_code == 422


def test_goal_minimal_maintain(client, a):
    resp = client.post("/api/me/goals", json={"kind": "maintain"}, headers=a)
    assert resp.status_code == 201
    assert resp.json()["rate_kg_per_week"] is None


# --------------------------------------------------------------------------- Supplemente

SUPPLEMENT = {
    "name": "Testkapsel",
    "dose_amount": 1,
    "dose_unit": "Kapsel",
    "nutrients_per_day": {"zinc_mg": 15, "epa_dha_mg": 600},
    "time_of_day": "morning",
}


def test_supplement_crud(client, a):
    created = client.post("/api/me/supplements", json=SUPPLEMENT, headers=a)
    assert created.status_code == 201
    item = created.json()
    assert item["taking"] is True and item["nutrients_per_day"]["zinc_mg"] == 15
    sid = item["id"]
    assert client.get(f"/api/me/supplements/{sid}", headers=a).json()["name"] == "Testkapsel"
    assert [s["id"] for s in client.get("/api/me/supplements", headers=a).json()] == [sid]

    patched = client.patch(f"/api/me/supplements/{sid}", json={"taking": False}, headers=a)
    assert patched.status_code == 200 and patched.json()["taking"] is False
    assert patched.json()["name"] == "Testkapsel"  # unverändert

    put = client.put(f"/api/me/supplements/{sid}", json={"name": "Anders"}, headers=a)
    assert put.status_code == 200
    assert put.json()["name"] == "Anders" and put.json()["nutrients_per_day"] == {}

    assert client.delete(f"/api/me/supplements/{sid}", headers=a).status_code == 204
    assert client.get(f"/api/me/supplements/{sid}", headers=a).status_code == 404
    assert client.get("/api/me/supplements", headers=a).json() == []


@pytest.mark.parametrize(
    "body",
    [
        {**SUPPLEMENT, "name": ""},
        {**SUPPLEMENT, "dose_amount": -1},
        {**SUPPLEMENT, "nutrients_per_day": {"zinc_mg": -3}},
        {**SUPPLEMENT, "nutrients_per_day": {"zinc_mg": "viel"}},
        {**SUPPLEMENT, "person_id": 7},
        {"dose_amount": 1},
    ],
)
def test_supplement_validation(client, a, body):
    assert client.post("/api/me/supplements", json=body, headers=a).status_code == 422


def test_supplement_patch_validation(client, a):
    sid = client.post("/api/me/supplements", json=SUPPLEMENT, headers=a).json()["id"]
    url = f"/api/me/supplements/{sid}"
    assert client.patch(url, json={"dose_amount": -5}, headers=a).status_code == 422
    assert client.patch(url, json={"name": None}, headers=a).status_code == 422
    assert client.patch(url, json={"unbekannt": 1}, headers=a).status_code == 422
    assert client.patch(url, json={"note": None}, headers=a).status_code == 200


def test_supplement_isolation_between_persons(client, a, b):
    sid = client.post("/api/me/supplements", json=SUPPLEMENT, headers=a).json()["id"]
    url = f"/api/me/supplements/{sid}"
    assert client.get("/api/me/supplements", headers=b).json() == []
    assert client.get(url, headers=b).status_code == 404
    assert client.put(url, json={"name": "Fremd"}, headers=b).status_code == 404
    assert client.patch(url, json={"taking": False}, headers=b).status_code == 404
    assert client.delete(url, headers=b).status_code == 404
    mine = client.get(url, headers=a).json()
    assert mine["name"] == "Testkapsel" and mine["taking"] is True


def test_unknown_id_404(client, a):
    resp = client.get("/api/me/supplements/9999", headers=a)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Eintrag nicht gefunden."


# --------------------------------------------------------------------------- Ernährungsregeln


def rule(**kw):
    return {"subject": "salt", "kind": "max", "value": 5, "unit": "g", **kw}


def test_nutrient_rule_crud(client, a):
    created = client.post("/api/me/nutrient-rules", json=rule(doctor_confirmed=True), headers=a)
    assert created.status_code == 201
    item = created.json()
    assert item["per"] == "day" and item["hard"] is True and item["enabled"] is True
    assert item["doctor_confirmed"] is True and item["suggested_by_app"] is False
    rid = item["id"]
    assert (
        client.patch(f"/api/me/nutrient-rules/{rid}", json={"enabled": False}, headers=a).json()["enabled"]
        is False
    )
    put = client.put(
        f"/api/me/nutrient-rules/{rid}",
        json=rule(subject="fish", kind="target", value=2, per="week"),
        headers=a,
    )
    assert put.json()["per"] == "week" and put.json()["subject"] == "fish"
    assert client.delete(f"/api/me/nutrient-rules/{rid}", headers=a).status_code == 204
    assert client.get("/api/me/nutrient-rules", headers=a).json() == []


def test_nutrient_rule_avoid_needs_no_value(client, a):
    resp = client.post(
        "/api/me/nutrient-rules", json={"subject": "potassium_salt", "kind": "avoid"}, headers=a
    )
    assert resp.status_code == 201 and resp.json()["value"] is None


@pytest.mark.parametrize(
    "body",
    [
        rule(kind="limit"),
        rule(per="month"),
        rule(value=-1),
        rule(value=None),  # max braucht einen Wert
        rule(subject=""),
    ],
)
def test_nutrient_rule_validation(client, a, body):
    assert client.post("/api/me/nutrient-rules", json=body, headers=a).status_code == 422


def test_nutrient_rule_patch_checks_merged_record(client, a):
    rid = client.post("/api/me/nutrient-rules", json=rule(), headers=a).json()["id"]
    assert client.patch(f"/api/me/nutrient-rules/{rid}", json={"value": None}, headers=a).status_code == 422
    assert (
        client.patch(
            f"/api/me/nutrient-rules/{rid}", json={"kind": "avoid", "value": None}, headers=a
        ).status_code
        == 200
    )


def test_nutrient_rule_isolation(client, a, b):
    rid = client.post("/api/me/nutrient-rules", json=rule(), headers=a).json()["id"]
    assert client.get(f"/api/me/nutrient-rules/{rid}", headers=b).status_code == 404
    assert client.delete(f"/api/me/nutrient-rules/{rid}", headers=b).status_code == 404
    assert client.get(f"/api/me/nutrient-rules/{rid}", headers=a).status_code == 200


# --------------------------------------------------------------------------- Trainingsplan


def item(**kw):
    return {"weekday": 1, "session_type": "Laufen", "intensity": "moderate", **kw}


def test_training_crud_and_order(client, a):
    client.post(
        "/api/me/training-plan", json=item(weekday=4, session_type="Kraft", intensity="hard"), headers=a
    )
    first = client.post(
        "/api/me/training-plan",
        json=item(weekday=0, start_time="18:30:00", duration_min=45, expected_kcal=400),
        headers=a,
    )
    assert first.status_code == 201
    assert first.json()["start_time"] == "18:30:00"
    listing = client.get("/api/me/training-plan", headers=a).json()
    assert [t["weekday"] for t in listing] == [0, 4]

    tid = first.json()["id"]
    assert (
        client.patch(f"/api/me/training-plan/{tid}", json={"intensity": "easy"}, headers=a).json()[
            "intensity"
        ]
        == "easy"
    )
    assert client.put(f"/api/me/training-plan/{tid}", json=item(weekday=6), headers=a).json()["weekday"] == 6
    assert client.delete(f"/api/me/training-plan/{tid}", headers=a).status_code == 204
    assert client.get(f"/api/me/training-plan/{tid}", headers=a).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        item(weekday=7),
        item(weekday=-1),
        item(intensity="extreme"),
        item(duration_min=0),
        item(expected_kcal=-5),
        item(start_time="25:00"),
        item(session_type=""),
    ],
)
def test_training_validation(client, a, body):
    assert client.post("/api/me/training-plan", json=body, headers=a).status_code == 422


def test_training_isolation(client, a, b):
    tid = client.post("/api/me/training-plan", json=item(), headers=a).json()["id"]
    assert client.get("/api/me/training-plan", headers=b).json() == []
    assert client.put(f"/api/me/training-plan/{tid}", json=item(weekday=2), headers=b).status_code == 404


# --------------------------------------------------------------------------- Laborregeln


def lab(**kw):
    return {
        "name": "Eisen niedrig",
        "analyte": "Ferritin",
        "comparator": "lt",
        "threshold_high": 30,
        "effect_key": "boost_iron_vitc",
        **kw,
    }


def test_lab_rule_crud(client, a):
    created = client.post("/api/me/lab-rules", json=lab(), headers=a)
    assert created.status_code == 201
    data = created.json()
    assert data["effect_weight"] == 0.5 and data["enabled"] is True and data["threshold_low"] is None
    lid = data["id"]
    patched = client.patch(
        f"/api/me/lab-rules/{lid}", json={"enabled": False, "effect_weight": 0.8}, headers=a
    )
    assert patched.json()["enabled"] is False and patched.json()["effect_weight"] == 0.8
    between = lab(comparator="between", threshold_low=10, threshold_high=30)
    assert client.put(f"/api/me/lab-rules/{lid}", json=between, headers=a).json()["comparator"] == "between"
    assert client.delete(f"/api/me/lab-rules/{lid}", headers=a).status_code == 204
    assert client.get("/api/me/lab-rules", headers=a).json() == []


def test_lab_rule_outside_ref_needs_no_threshold(client, a):
    resp = client.post(
        "/api/me/lab-rules", json=lab(comparator="outside_ref", threshold_high=None), headers=a
    )
    assert resp.status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        lab(comparator="eq"),
        lab(comparator="between", threshold_low=10, threshold_high=None),
        lab(comparator="between", threshold_low=None, threshold_high=30),
        lab(comparator="between", threshold_low=40, threshold_high=30),
        lab(comparator="gt", threshold_high=None),
        lab(effect_weight=1.5),
        lab(effect_weight=-0.1),
        lab(name=""),
    ],
)
def test_lab_rule_validation(client, a, body):
    assert client.post("/api/me/lab-rules", json=body, headers=a).status_code == 422


def test_lab_rule_patch_to_between_requires_both(client, a):
    lid = client.post("/api/me/lab-rules", json=lab(), headers=a).json()["id"]
    url = f"/api/me/lab-rules/{lid}"
    assert client.patch(url, json={"comparator": "between"}, headers=a).status_code == 422
    ok = client.patch(url, json={"comparator": "between", "threshold_low": 5}, headers=a)
    assert ok.status_code == 200 and ok.json()["threshold_low"] == 5


def test_lab_rule_isolation(client, a, b):
    lid = client.post("/api/me/lab-rules", json=lab(), headers=a).json()["id"]
    assert client.get("/api/me/lab-rules", headers=b).json() == []
    assert client.get(f"/api/me/lab-rules/{lid}", headers=b).status_code == 404
    assert client.patch(f"/api/me/lab-rules/{lid}", json={"enabled": False}, headers=b).status_code == 404
