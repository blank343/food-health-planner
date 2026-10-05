"""Liefert die gebaute Web-Oberfläche (web/dist) aus, mit Rückfall auf index.html für App-Routen.

Alles unter `/api` gehört dem Backend: Unbekannte API-Pfade ergeben 404 (JSON), nie die Oberfläche.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings

_IMMUTABLE = "public, max-age=31536000, immutable"  # Dateien in /assets haben Hash im Namen
_NO_CACHE = "no-cache"


def find_web_dir() -> Path | None:
    """`FHP_WEB_DIR`, sonst `web/dist` neben dem Backend (Entwicklung). Nur mit vorhandener index.html."""
    configured = get_settings().web_dir
    candidates = [Path(configured)] if configured else [Path(__file__).resolve().parents[2] / "web" / "dist"]
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    return None


def mount_web(app: FastAPI, web_dir: Path | None = None) -> bool:
    """Registriert die Auslieferung. Muss NACH allen API-Routen aufgerufen werden."""
    root = (web_dir or find_web_dir())
    if root is None:
        return False
    root = root.resolve()
    index = root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Nicht gefunden.")
        if full_path:
            try:
                candidate = (root / full_path).resolve()
            except (OSError, ValueError):
                candidate = None
            if candidate is not None and candidate.is_file() and root in candidate.parents:
                cache = _IMMUTABLE if candidate.relative_to(root).parts[0] == "assets" else _NO_CACHE
                return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": _NO_CACHE})

    return True
