"""Zutaten-Katalog: Suche, Detail, manuelle Zutaten, Synonyme (`/api/ingredients`).

Zutaten sind für alle angemeldeten Personen gemeinsam sichtbar und pflegbar. BLS-Zutaten lassen
sich nicht löschen und nur eingeschränkt ändern (ausblenden, Dichte, Stückgewicht, Haltbarkeit).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, select

from app.api.deps import CurrentPerson, Db
from app.models import Component, ComponentVariant, Ingredient, RecipeIngredient
from app.services import catalog

router = APIRouter(prefix="/ingredients", tags=["Zutaten"])

Source = Literal["bls", "off", "manual"]
# Felder, die der BLS-Import nie überschreibt und die deshalb auch bei BLS-Zutaten änderbar sind
_BLS_EDITABLE = {"hidden", "density_g_per_ml", "piece_g", "shelf_days", "is_potassium_salt"}


class NutrientsPer100Out(BaseModel):
    kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carb_g: float | None
    fiber_g: float | None
    salt_g: float | None
    micros: dict[str, float]


class IngredientOut(BaseModel):
    id: int
    name: str
    category: str | None
    source: str
    source_code: str | None
    nutrients: NutrientsPer100Out
    density_g_per_ml: float | None
    piece_g: float | None
    is_fish: bool
    is_potassium_salt: bool
    shelf_days: int | None
    hidden: bool


class IngredientDetailOut(IngredientOut):
    synonyms: list[str]


class IngredientListOut(BaseModel):
    items: list[IngredientOut]
    total: int
    limit: int
    offset: int


class IngredientIn(BaseModel):
    """Eine manuell gepflegte Zutat (Werte je 100 g)."""

    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=60)
    kcal_100: float | None = Field(default=None, ge=0, le=900)
    protein_100: float | None = Field(default=None, ge=0, le=100)
    fat_100: float | None = Field(default=None, ge=0, le=100)
    carb_100: float | None = Field(default=None, ge=0, le=100)
    fiber_100: float | None = Field(default=None, ge=0, le=100)
    salt_100: float | None = Field(default=None, ge=0, le=100, description="Salz in g je 100 g")
    micros: dict[str, float] = Field(default_factory=dict, description="Schlüssel wie `zinc_mg`, je 100 g")
    density_g_per_ml: float | None = Field(default=None, gt=0, le=20)
    piece_g: float | None = Field(default=None, gt=0, le=5000, description="Gewicht eines Stücks in g")
    is_fish: bool = False
    is_potassium_salt: bool = False
    shelf_days: int | None = Field(default=None, ge=0, le=3650)
    hidden: bool = False

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Der Name darf nicht leer sein")
        return value

    @field_validator("micros")
    @classmethod
    def _check_micros(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 60:
            raise ValueError("Zu viele Mikronährstoffe (höchstens 60)")
        for key, amount in value.items():
            if not key or len(key) > 40:
                raise ValueError("Ungültiger Schlüssel bei den Mikronährstoffen")
            if not 0 <= amount <= 1_000_000:
                raise ValueError(f"Ungültiger Wert für {key}")
        return value

    @model_validator(mode="after")
    def _plausible(self) -> "IngredientIn":
        macros = sum(v or 0.0 for v in (self.protein_100, self.fat_100, self.carb_100))
        if macros > 100.5:
            raise ValueError(
                "Protein, Fett und Kohlenhydrate zusammen dürfen 100 g je 100 g nicht übersteigen"
            )
        return self


class IngredientPatch(BaseModel):
    """Teiländerung; nur gesendete Felder gelten."""

    name: str | None = None
    category: str | None = None
    kcal_100: float | None = None
    protein_100: float | None = None
    fat_100: float | None = None
    carb_100: float | None = None
    fiber_100: float | None = None
    salt_100: float | None = None
    micros: dict[str, float] | None = None
    density_g_per_ml: float | None = None
    piece_g: float | None = None
    is_fish: bool | None = None
    is_potassium_salt: bool | None = None
    shelf_days: int | None = None
    hidden: bool | None = None


class SynonymIn(BaseModel):
    alias: str = Field(min_length=1, max_length=200)


def _out(ing: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=ing.id,
        name=ing.name,
        category=ing.category,
        source=ing.source,
        source_code=ing.source_code,
        nutrients=NutrientsPer100Out(
            kcal=ing.kcal_100,
            protein_g=ing.protein_100,
            fat_g=ing.fat_100,
            carb_g=ing.carb_100,
            fiber_g=ing.fiber_100,
            salt_g=ing.salt_100,
            micros=dict(ing.micros or {}),
        ),
        density_g_per_ml=ing.density_g_per_ml,
        piece_g=ing.piece_g,
        is_fish=ing.is_fish,
        is_potassium_salt=ing.is_potassium_salt,
        shelf_days=ing.shelf_days,
        hidden=ing.hidden,
    )


def _detail(db, ing: Ingredient) -> IngredientDetailOut:
    return IngredientDetailOut(**_out(ing).model_dump(), synonyms=catalog.synonyms_of(db, ing.id))


def _get_or_404(db, ingredient_id: int) -> Ingredient:
    ing = db.get(Ingredient, ingredient_id)
    if ing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Zutat nicht gefunden.")
    return ing


def _name_taken(db, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(Ingredient.id).where(
        Ingredient.source == "manual", func.lower(Ingredient.name) == name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(Ingredient.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None


@router.get("", response_model=IngredientListOut, summary="Zutaten suchen")
def list_ingredients(
    _: CurrentPerson,
    db: Db,
    q: Annotated[
        str | None, Query(max_length=100, description="Suchtext (Teilstring und Ähnlichkeit)")
    ] = None,
    source: Annotated[Source | None, Query(description="Nur Zutaten dieser Quelle")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_hidden: Annotated[bool, Query(description="Ausgeblendete Zutaten mit anzeigen")] = False,
) -> IngredientListOut:
    rows, total = catalog.search_ingredients(db, q, limit, offset, source, include_hidden=include_hidden)
    return IngredientListOut(items=[_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{ingredient_id}", response_model=IngredientDetailOut, summary="Zutat mit Synonymen")
def get_ingredient(ingredient_id: int, _: CurrentPerson, db: Db) -> IngredientDetailOut:
    return _detail(db, _get_or_404(db, ingredient_id))


@router.post(
    "",
    response_model=IngredientDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Eigene Zutat anlegen",
)
def create_ingredient(body: IngredientIn, _: CurrentPerson, db: Db) -> IngredientDetailOut:
    if _name_taken(db, body.name):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Eine eigene Zutat mit diesem Namen gibt es schon."
        )
    ing = Ingredient(source="manual", source_code=None, **body.model_dump())
    db.add(ing)
    db.commit()
    return _detail(db, ing)


@router.patch("/{ingredient_id}", response_model=IngredientDetailOut, summary="Zutat ändern")
def patch_ingredient(
    ingredient_id: int, body: IngredientPatch, _: CurrentPerson, db: Db
) -> IngredientDetailOut:
    ing = _get_or_404(db, ingredient_id)
    changes = body.model_dump(exclude_unset=True)
    if ing.source != "manual":
        forbidden = sorted(set(changes) - _BLS_EDITABLE)
        if forbidden:
            raise HTTPException(
                422,
                detail="Name und Nährwerte importierter Zutaten lassen sich nicht ändern. "
                "Erlaubt sind Ausblenden, Dichte, Stückgewicht, Haltbarkeit und Kaliumsalz.",
            )
        for key, value in changes.items():
            if key in ("hidden", "is_potassium_salt") and value is None:
                raise HTTPException(422, detail=f"{key} darf nicht leer sein.")
        try:
            IngredientIn.model_validate(
                {
                    **{f: getattr(ing, f) for f in ("name", "density_g_per_ml", "piece_g", "shelf_days")},
                    **changes,
                }
            )
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_url=False, include_context=False)) from exc
        for key, value in changes.items():
            setattr(ing, key, value)
    else:
        merged = {name: getattr(ing, name) for name in IngredientIn.model_fields}
        merged.update(changes)
        for key in ("name", "micros", "is_fish", "is_potassium_salt", "hidden"):
            if key in changes and changes[key] is None:
                if key == "micros":
                    merged[key] = {}
                else:
                    raise HTTPException(422, detail=f"{key} darf nicht leer sein.")
        try:
            valid = IngredientIn.model_validate(merged)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_url=False, include_context=False)) from exc
        if _name_taken(db, valid.name, exclude_id=ing.id):
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Eine eigene Zutat mit diesem Namen gibt es schon."
            )
        for key, value in valid.model_dump().items():
            setattr(ing, key, value)
    db.commit()
    return _detail(db, ing)


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eigene Zutat löschen")
def delete_ingredient(ingredient_id: int, _: CurrentPerson, db: Db) -> Response:
    ing = _get_or_404(db, ingredient_id)
    if ing.source != "manual":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Importierte Zutaten lassen sich nicht löschen, nur ausblenden (hidden).",
        )
    in_recipes = db.scalar(
        select(func.count()).select_from(RecipeIngredient).where(RecipeIngredient.ingredient_id == ing.id)
    )
    in_components = db.scalar(
        select(func.count()).select_from(Component).where(Component.ingredient_id == ing.id)
    )
    in_variants = db.scalar(
        select(func.count()).select_from(ComponentVariant).where(ComponentVariant.ingredient_id == ing.id)
    )
    if in_recipes or in_components or in_variants:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Die Zutat wird noch in Rezepten oder im Baukasten verwendet "
            "und kann nicht gelöscht werden.",
        )
    db.delete(ing)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{ingredient_id}/synonyms",
    response_model=IngredientDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Synonym hinzufügen",
)
def add_synonym(ingredient_id: int, body: SynonymIn, _: CurrentPerson, db: Db) -> IngredientDetailOut:
    ing = _get_or_404(db, ingredient_id)
    try:
        catalog.add_synonym(db, ing.id, body.alias)
    except catalog.CatalogNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except catalog.CatalogConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except catalog.CatalogError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return _detail(db, ing)


@router.delete(
    "/{ingredient_id}/synonyms/{alias}", status_code=status.HTTP_204_NO_CONTENT, summary="Synonym entfernen"
)
def remove_synonym(ingredient_id: int, alias: str, _: CurrentPerson, db: Db) -> Response:
    try:
        catalog.remove_synonym(db, ingredient_id, alias)
    except catalog.CatalogError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
