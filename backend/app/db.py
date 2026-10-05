"""Datenbankzugriff: Engine, Session, Basisklasse."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    """Lazy Engine: verbindet erst beim ersten Zugriff."""
    url = get_settings().database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs["connect_args"] = {"connect_timeout": 2}
    return create_engine(url, **kwargs)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI-Dependency: eine Session pro Anfrage."""
    session = make_session_factory()()
    try:
        yield session
    finally:
        session.close()
