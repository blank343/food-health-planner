"""Bearer-Token je Person. Gespeichert wird nur der SHA-256-Hash, nie das Token selbst.

Tokens werden niemals geloggt oder ausgegeben (außer einmalig bei der Erstellung durch die CLI).
"""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Person


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate(session: Session, token: str | None) -> Person | None:
    """Liefert die aktive Person zum Token oder None."""
    if not token:
        return None
    digest = hash_token(token)
    person = session.scalar(select(Person).where(Person.token_hash == digest))
    if person is None or person.token_hash is None:
        return None
    if not secrets.compare_digest(person.token_hash, digest):
        return None
    if not person.is_active:
        return None
    return person
