"""Schreibt die OpenAPI-Beschreibung nach web/openapi.json (Grundlage für die typisierten API-Typen).

Aufruf (im Projektordner):  .venv/Scripts/python backend/scripts/export_openapi.py
Danach:                     cd web && npm run gen:api
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

target = Path(__file__).resolve().parents[2] / "web" / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"geschrieben: {target}")
