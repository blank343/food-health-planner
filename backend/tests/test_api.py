from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import get_settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_without_database(client, monkeypatch):
    """Muss auch ohne erreichbare DB 200 liefern (Port 1 ist garantiert zu)."""
    monkeypatch.setenv("FHP_DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/x")
    monkeypatch.setenv("FHP_ENV", "test")
    get_settings.cache_clear()
    main.get_engine.cache_clear()
    try:
        resp = client.get("/api/health")
    finally:
        get_settings.cache_clear()
        main.get_engine.cache_clear()
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "env": "test", "db": "unavailable"}


def test_health_db_ok(client, monkeypatch):
    monkeypatch.setattr(main, "check_db", lambda: True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["db"] == "ok"


def test_spike_shopping_list(client):
    resp = client.get("/api/spike/shopping-list.json")
    assert resp.status_code == 200
    data = resp.json()
    date.fromisoformat(data["date"])
    assert data["store"] == "Lidl"
    assert 6 <= len(data["items"]) <= 8
    for item in data["items"]:
        assert set(item) == {"name", "quantity", "note", "title"}
        assert item["name"] and item["quantity"]
        assert item["title"] == f"{item['name']} {item['quantity']}"
