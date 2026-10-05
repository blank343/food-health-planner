from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfiguration aus Umgebungsvariablen mit Praefix FHP_."""

    model_config = SettingsConfigDict(env_prefix="FHP_", extra="ignore")

    database_url: str = "postgresql+psycopg://fhp:fhp@db:5432/fhp"
    env: str = "dev"
    timezone: str = "Europe/Berlin"
    # Zwischenablage für hochgeladene Importdateien (leer = Systemtemp/fhp-uploads)
    upload_dir: str = ""
    max_upload_mb: int = 4096
    # Gebaute Web-Oberfläche (leer = ../web/dist neben dem Backend; im Container /app/web)
    web_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
