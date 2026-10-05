from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, text

from app.config import get_settings

app = FastAPI(
    title="Food & Health Planner",
    version="0.1.0",
    description="Privater Essensplan und Einkaufsliste für 2 Personen.",
)


@lru_cache
def get_engine() -> Engine:
    """Lazy Engine: verbindet erst beim ersten Zugriff, kurzer Verbindungs-Timeout."""
    return create_engine(
        get_settings().database_url,
        connect_args={"connect_timeout": 2},
        pool_pre_ping=True,
    )


def check_db() -> bool:
    """True, wenn `SELECT 1` klappt. Wirft nie."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.get("/api/health", summary="Health-Check")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.env,
        "db": "ok" if check_db() else "unavailable",
    }


# ---------------------------------------------------------------------------
# SPIKE-DATEN: nur zum Testen des Apple Shortcuts. Wird in Phase 4 durch die
# echte, aus dem Wochenplan generierte Einkaufsliste ersetzt.
# ---------------------------------------------------------------------------
SPIKE_ITEMS = [
    {"name": "Skyr", "quantity": "500 g", "note": ""},
    {"name": "Haferflocken", "quantity": "1 Packung", "note": "kernig"},
    {"name": "Hähnchenbrustfilet", "quantity": "600 g", "note": ""},
    {"name": "Brokkoli", "quantity": "2 Stück", "note": "frisch"},
    {"name": "Vollkornreis", "quantity": "1 kg", "note": ""},
    {"name": "Eier", "quantity": "10 Stück", "note": "Freiland"},
    {"name": "Bananen", "quantity": "6 Stück", "note": ""},
    {"name": "Magerquark", "quantity": "250 g", "note": ""},
]


@app.get(
    "/api/spike/shopping-list.json",
    summary="SPIKE: Beispiel-Einkaufsliste (wird in Phase 4 ersetzt)",
    description=(
        "SPIKE-DATEN: fest hinterlegte Beispiel-Einkaufsliste zum Testen des Apple Shortcuts. "
        "Dieser Endpoint wird in Phase 4 durch die echte, aus dem Wochenplan generierte "
        "Einkaufsliste ersetzt und ist nicht stabil."
    ),
)
def spike_shopping_list() -> dict:
    today = datetime.now(ZoneInfo(get_settings().timezone)).date().isoformat()
    return {"date": today, "store": "Lidl", "items": SPIKE_ITEMS}
