"""Generische CRUD-Routen für Ressourcen, die genau einer Person gehören."""

import copy as copy_module
from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, create_model
from sqlalchemy import select

from app.api.deps import CurrentPerson, Db, get_owned_or_404


def partial_model(model: type[BaseModel], name: str) -> type[BaseModel]:
    """Kopie des Schemas, in der alle Felder optional sind (für PATCH)."""
    fields: dict[str, Any] = {}
    for field_name, info in model.model_fields.items():
        copy = copy_module.copy(info)
        copy.default = None
        copy.default_factory = None
        fields[field_name] = (copy.annotation | None, copy)
    return create_model(name, __config__=model.model_config, **fields)


def crud_router(
    *,
    db_model: type,
    create: type[BaseModel],
    read: type[BaseModel],
    order_by: tuple,
    prefix: str,
    tag: str,
) -> APIRouter:
    """GET (Liste), POST, GET/PUT/PATCH/DELETE (einzeln). Alles auf die aktuelle Person beschränkt.

    `create` validiert POST und PUT (vollständiger Datensatz, inkl. feldübergreifender Regeln).
    PATCH validiert nur die gesendeten Felder und prüft danach den zusammengeführten Datensatz.
    """
    update = partial_model(create, f"{create.__name__}Patch")
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("", response_model=list[read], summary=f"{tag}: Liste")
    def list_items(person: CurrentPerson, db: Db):
        stmt = select(db_model).where(db_model.person_id == person.id).order_by(*order_by)
        return list(db.scalars(stmt))

    @router.post("", response_model=read, status_code=status.HTTP_201_CREATED, summary=f"{tag}: Anlegen")
    def create_item(body: create, person: CurrentPerson, db: Db):
        obj = db_model(person_id=person.id, **body.model_dump())
        db.add(obj)
        db.commit()
        return obj

    @router.get("/{item_id}", response_model=read, summary=f"{tag}: Einzeln lesen")
    def get_item(item_id: int, person: CurrentPerson, db: Db):
        return get_owned_or_404(db, db_model, item_id, person)

    @router.put("/{item_id}", response_model=read, summary=f"{tag}: Ersetzen")
    def replace_item(item_id: int, body: create, person: CurrentPerson, db: Db):
        obj = get_owned_or_404(db, db_model, item_id, person)
        for key, value in body.model_dump().items():
            setattr(obj, key, value)
        db.commit()
        return obj

    @router.patch("/{item_id}", response_model=read, summary=f"{tag}: Teilweise ändern")
    def patch_item(item_id: int, body: update, person: CurrentPerson, db: Db):
        obj = get_owned_or_404(db, db_model, item_id, person)
        merged = {name: getattr(obj, name) for name in create.model_fields}
        merged.update(body.model_dump(exclude_unset=True))
        try:
            valid = create.model_validate(merged)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_url=False, include_context=False)) from exc
        for key, value in valid.model_dump().items():
            setattr(obj, key, value)
        db.commit()
        return obj

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary=f"{tag}: Löschen")
    def delete_item(item_id: int, person: CurrentPerson, db: Db):
        obj = get_owned_or_404(db, db_model, item_id, person)
        db.delete(obj)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
