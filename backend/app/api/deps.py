"""Gemeinsame Abhängigkeiten der API: Session, aktuelle Person, Zugriff auf eigene Datensätze."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import authenticate
from app.config import get_settings
from app.db import get_session
from app.models import Person

_bearer = HTTPBearer(auto_error=False, description="Zugangstoken der Person (`python -m app.cli`)")


def get_db(session: Annotated[Session, Depends(get_session)]) -> Session:
    """Session der Anfrage. Tests überschreiben `app.db.get_session`."""
    return session


def current_person(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> Person:
    person = authenticate(db, credentials.credentials if credentials else None)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet. Bitte Zugangstoken angeben.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return person


def get_owned_or_404[T](db: Session, model: type[T], item_id: int, person: Person) -> T:
    """Datensatz der aktuellen Person oder 404 (auch bei fremden Datensätzen, nie 403)."""
    obj = db.get(model, item_id)
    if obj is None or getattr(obj, "person_id", None) != person.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Eintrag nicht gefunden.")
    return obj


# Kurzformen für Endpunkt-Signaturen: `person: CurrentPerson, db: Db`
CurrentPerson = Annotated[Person, Depends(current_person)]
Db = Annotated[Session, Depends(get_db)]


def today_local() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()
