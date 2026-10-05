"""Profil und Einstellungen der aktuellen Person."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentPerson, Db
from app.api.schemas import PersonOut, PersonPatch, SettingsIn, SettingsOut
from app.calc.types import PersonSettings
from app.models import Person, PersonSettingsRow

router = APIRouter(prefix="/me", tags=["Profil"])

_NAME_TAKEN = "Dieser Name ist bereits vergeben."


@router.get("", response_model=PersonOut, summary="Eigenes Profil")
def get_me(person: CurrentPerson):
    return person


@router.patch("", response_model=PersonOut, summary="Profil ändern")
def patch_me(body: PersonPatch, person: CurrentPerson, db: Db):
    changes = body.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name is not None and new_name != person.name:
        if db.scalar(select(Person.id).where(Person.name == new_name, Person.id != person.id)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=_NAME_TAKEN)
    for key, value in changes.items():
        setattr(person, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_NAME_TAKEN) from exc
    return person


def _settings_out(stored: dict) -> SettingsOut:
    return SettingsOut(effective=PersonSettings.model_validate(stored), stored=stored)


@router.get("/settings", response_model=SettingsOut, summary="Einstellungen (wirksam und gespeichert)")
def get_settings_(person: CurrentPerson, db: Db):
    row = db.get(PersonSettingsRow, person.id)
    return _settings_out(dict(row.data) if row and row.data else {})


@router.put("/settings", response_model=SettingsOut, summary="Einstellungen ersetzen")
def put_settings(body: SettingsIn, person: CurrentPerson, db: Db):
    # Gespeichert wird nur, was gesendet wurde: Standardwerte bleiben dadurch änderbar.
    stored = body.model_dump(mode="json", exclude_unset=True)
    row = db.get(PersonSettingsRow, person.id)
    if row is None:
        db.add(PersonSettingsRow(person_id=person.id, data=stored))
    else:
        row.data = stored
    db.commit()
    return _settings_out(stored)
