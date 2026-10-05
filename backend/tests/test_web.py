from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import mount_web


def _site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>APP</html>")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    (tmp_path.parent / "geheim.txt").write_text("nicht ausliefern")
    return tmp_path


def _client(tmp_path):
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    assert mount_web(app, _site(tmp_path)) is True
    return TestClient(app)


def test_index_and_spa_fallback(tmp_path):
    c = _client(tmp_path)
    for path in ("/", "/ziele", "/labor/bericht/3"):
        r = c.get(path)
        assert r.status_code == 200 and "APP" in r.text
        assert r.headers["cache-control"] == "no-cache"


def test_assets_are_cached_long(tmp_path):
    r = _client(tmp_path).get("/assets/app-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]


def test_other_static_files_not_cached_hard(tmp_path):
    r = _client(tmp_path).get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"


def test_api_routes_win_and_unknown_api_is_404_json(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/ping").json() == {"ok": True}
    r = c.get("/api/gibt-es-nicht")
    assert r.status_code == 404 and r.json()["detail"] == "Nicht gefunden."
    assert c.get("/api").status_code == 404


def test_path_traversal_is_not_served(tmp_path):
    c = _client(tmp_path)
    for path in ("/../geheim.txt", "/..%2fgeheim.txt", "/assets/../../geheim.txt", "/%2e%2e/geheim.txt"):
        r = c.get(path)
        assert "nicht ausliefern" not in r.text


def test_find_web_dir_uses_env_and_requires_index(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.web import find_web_dir

    empty = tmp_path / "leer"
    empty.mkdir()
    monkeypatch.setenv("FHP_WEB_DIR", str(empty))
    get_settings.cache_clear()
    try:
        assert find_web_dir() is None  # ohne index.html wird nichts ausgeliefert
        (empty / "index.html").write_text("x")
        assert find_web_dir() == empty
    finally:
        monkeypatch.delenv("FHP_WEB_DIR")
        get_settings.cache_clear()


def test_mount_returns_false_without_build(monkeypatch, tmp_path):
    from app.config import get_settings

    monkeypatch.setenv("FHP_WEB_DIR", str(tmp_path / "gibt-es-nicht"))
    get_settings.cache_clear()
    try:
        assert mount_web(FastAPI()) is False
    finally:
        monkeypatch.delenv("FHP_WEB_DIR")
        get_settings.cache_clear()
