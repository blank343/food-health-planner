"""Zutaten-Vorlieben der angemeldeten Person: `/api/me/ingredient-preferences`.

Nur die eigenen Vorlieben sind sichtbar und änderbar (`like`, `dislike`, `never`).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentPerson, Db
from app.models import Ingredient, IngredientPreference

router = APIRouter(prefix="/me/ingredient-preferences", tags=["Zutaten-Vorlieben"])

Level = Literal["like", "dislike", "never"]


class PreferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Level


class PreferenceOut(BaseModel):
    ingredient_id: int
    ingredient_name: str
    level: str


def _out(pref: IngredientPreference, ingredient: Ingredient) -> PreferenceOut:
    return PreferenceOut(ingredient_id=ingredient.id, ingredient_name=ingredient.name, level=pref.level)


@router.get("", response_model=list[PreferenceOut], summary="Eigene Zutaten-Vorlieben (mit Zutatennamen)")
def list_preferences(
    person: CurrentPerson,
    db: Db,
    level: Annotated[Level | None, Query(description="Nur diese Stufe anzeigen")] = None,
) -> list[PreferenceOut]:
    stmt = (
        select(IngredientPreference, Ingredient)
        .join(Ingredient, Ingredient.id == IngredientPreference.ingredient_id)
        .where(IngredientPreference.person_id == person.id)
        .order_by(Ingredient.name, Ingredient.id)
    )
    if level is not None:
        stmt = stmt.where(IngredientPreference.level == level)
    return [_out(pref, ing) for pref, ing in db.execute(stmt)]


@router.put(
    "/{ingredient_id}",
    response_model=PreferenceOut,
    summary="Vorliebe für eine Zutat setzen oder ändern",
)
def set_preference(ingredient_id: int, body: PreferenceIn, person: CurrentPerson, db: Db) -> PreferenceOut:
    ingredient = db.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Zutat nicht gefunden.")
    pref = db.get(IngredientPreference, (person.id, ingredient_id))
    if pref is None:
        pref = IngredientPreference(person_id=person.id, ingredient_id=ingredient_id, level=body.level)
        db.add(pref)
    else:
        pref.level = body.level
    db.commit()
    return _out(pref, ingredient)


@router.delete(
    "/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Vorliebe für eine Zutat entfernen",
)
def delete_preference(ingredient_id: int, person: CurrentPerson, db: Db) -> Response:
    pref = db.get(IngredientPreference, (person.id, ingredient_id))
    if pref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Eintrag nicht gefunden.")
    db.delete(pref)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
