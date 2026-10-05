from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfiguration aus Umgebungsvariablen mit Praefix FHP_."""

    model_config = SettingsConfigDict(env_prefix="FHP_", extra="ignore")

    database_url: str = "postgresql+psycopg://fhp:fhp@db:5432/fhp"
    env: str = "dev"
    timezone: str = "Europe/Berlin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
