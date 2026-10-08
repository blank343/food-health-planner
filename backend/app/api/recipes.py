"""Rezepte: Liste, Detail, Anlegen/Bearbeiten, URL-Import, Passung ins Tagesziel, Bewertungen, Prüfliste.

Rezepte sind für alle angemeldeten Personen gemeinsam sichtbar und pflegbar. Bewertung und Passung
(`fit_*`, `/fit`) gelten immer für die angemeldete Person.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.deps import CurrentPerson, Db, today_local
from app.api.targets import MacroOut, WarningOut
from app.calc.nutrition import scale_nutrients
from app.calc.types import IngredientMatch, Nutrients, RecipeNutrition, SatietyScore
from app.importers import recipe_web
from app.importers.recipe_web import RecipeImportError
from app.models import Recipe, RecipeIngredient
from app.services import catalog
from app.services import recipes as svc
from app.services.targets import TargetsUnavailable

router = APIRouter(tags=["Rezepte"])

SlotName = Literal["breakfast", "lunch", "dinner", "snack"]
RecipeStatus = Literal["draft", "ready", "needs_review"]
SortKey = Literal["title", "newest", "kcal", "protein", "satiety", "rating", "fit"]
# Importer-Meldungen, die auf eine unbrauchbare Eingabe hinweisen (422); der Rest: Fehler der Seite (502)
_BAD_INPUT_MARKERS = ("kein Rezept", "Nur http", "keine Webseite", "robots.txt")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NutrientsOut(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    fiber_g: float
    salt_g: float
    micros: dict[str, float]


class SatietyOut(BaseModel):
    score: float
    parts: dict[str, float]


class TagOut(BaseModel):
    slot_types: list[str]
    cuisine: str | None
    main_ingredient: str | None
    batch_cookable: bool
    transportable: bool
    warm: bool
    shelf_days: int | None
    season: str | None


class TagIn(BaseModel):
    slot_types: list[SlotName] = Field(default_factory=list, max_length=4)
    cuisine: str | None = Field(default=None, max_length=60)
    main_ingredient: str | None = Field(default=None, max_length=80)
    batch_cookable: bool = False
    transportable: bool = False
    warm: bool = False
    shelf_days: int | None = Field(default=None, ge=0, le=3650)
    season: str | None = Field(default=None, max_length=20)


class RatingOut(BaseModel):
    person_id: int
    person_name: str
    rating: int


class IngredientRefOut(BaseModel):
    id: int
    name: str
    source: str


class LineOut(BaseModel):
    id: int
    position: int
    raw_text: str
    quantity: float | None
    unit: str | None
    grams: float | None
    optional: bool
    ingredient: IngredientRefOut | None
    nutrients: NutrientsOut | None


class RecipeCardOut(BaseModel):
    id: int
    title: str
    image_url: str | None
    source_site: str | None
    favorite: bool
    status: str
    servings: float
    prep_min: int | None
    cook_min: int | None
    tag: TagOut
    # je Portion
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    serving_weight_g: float
    satiety_score: float
    coverage: float
    my_rating: int | None
    avg_rating: float | None
    # nur mit fit_slot: Passung für die angemeldete Person
    fit_score: float | None = None
    fit_factor: float | None = None


class RecipeListOut(BaseModel):
    items: list[RecipeCardOut]
    total: int
    limit: int
    offset: int


class FitOut(BaseModel):
    slot: str
    date: date
    factor: float
    unclamped_factor: float
    grams: float
    scaled: NutrientsOut
    deviation_pct: dict[str, float]
    fit_score: float
    notes: list[str]
    slot_target: MacroOut
    warnings: list[WarningOut]


class RecipeDetailOut(RecipeCardOut):
    source_url: str | None
    instructions: str | None
    notes: str | None
    lines: list[LineOut]
    total: NutrientsOut
    per_serving: NutrientsOut
    total_weight_g: float
    energy_density_kcal_per_100g: float | None
    missing: list[str]
    satiety: SatietyOut
    ratings: list[RatingOut]
    fit: FitOut | None = None
    warnings: list[str] = Field(default_factory=list)


class LineIn(BaseModel):
    """Eine Zutatenzeile: Freitext (`raw_text`) oder feste Zutat mit Gramm (`ingredient_id` + `grams`)."""

    id: int | None = Field(default=None, description="Vorhandene Zeile behalten (Zuordnung bleibt)")
    raw_text: str | None = Field(default=None, max_length=400)
    ingredient_id: int | None = None
    grams: float | None = Field(default=None, gt=0, le=100_000)
    optional: bool | None = None

    @model_validator(mode="after")
    def _needs_content(self) -> "LineIn":
        has_text = bool(self.raw_text and self.raw_text.strip())
        if not has_text and (self.ingredient_id is None or self.grams is None):
            raise ValueError("Jede Zeile braucht einen Text oder eine Zutat mit Gramm")
        return self


def _check_url(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("Nur http- und https-Adressen sind erlaubt")
    return value


class RecipeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    servings: float = Field(default=1.0, gt=0, le=100)
    prep_min: int | None = Field(default=None, ge=0, le=10_000)
    cook_min: int | None = Field(default=None, ge=0, le=10_000)
    instructions: str | None = Field(default=None, max_length=20_000)
    image_url: str | None = Field(default=None, max_length=600)
    source_url: str | None = Field(default=None, max_length=600)
    favorite: bool = False
    notes: str | None = Field(default=None, max_length=5_000)
    tag: TagIn | None = None
    lines: list[LineIn] = Field(default_factory=list, max_length=100)

    check_urls = field_validator("image_url", "source_url")(_check_url)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Der Titel darf nicht leer sein")
        return value


class RecipePatch(BaseModel):
    """Teiländerung; nur gesendete Felder gelten. `lines` ersetzt alle Zeilen (mit `id` = behalten)."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    servings: float | None = Field(default=None, gt=0, le=100)
    prep_min: int | None = Field(default=None, ge=0, le=10_000)
    cook_min: int | None = Field(default=None, ge=0, le=10_000)
    instructions: str | None = Field(default=None, max_length=20_000)
    image_url: str | None = Field(default=None, max_length=600)
    source_url: str | None = Field(default=None, max_length=600)
    favorite: bool | None = None
    notes: str | None = Field(default=None, max_length=5_000)
    tag: TagIn | None = None
    lines: list[LineIn] | None = Field(default=None, max_length=100)

    check_urls = field_validator("image_url", "source_url")(_check_url)


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=600)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("Bitte eine Adresse mit http:// oder https:// angeben")
        return value


class MatchOut(BaseModel):
    ingredient_id: int
    name: str
    score: float
    via: str


class PreviewLineOut(BaseModel):
    raw_text: str
    name: str
    quantity: float | None
    unit: str | None
    note: str | None
    optional: bool
    grams: float | None
    ingredient_id: int | None  # vorgeschlagene Zuordnung (nur bei sicherem Treffer)
    ingredient_name: str | None
    matches: list[MatchOut]


class ImportPreviewOut(BaseModel):
    title: str
    source_url: str
    source_site: str | None
    servings: float | None
    prep_min: int | None
    cook_min: int | None
    instructions: str | None
    image_url: str | None
    site_nutrients: dict[str, float]
    warnings: list[str]
    lines: list[PreviewLineOut]


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


class MyRatingOut(BaseModel):
    recipe_id: int
    person_id: int
    rating: int


class UnassignedLineOut(BaseModel):
    line_id: int
    recipe_id: int
    recipe_title: str
    raw_text: str
    name: str
    quantity: float | None
    unit: str | None
    similar_count: int
    suggestions: list[MatchOut]


class UnassignedListOut(BaseModel):
    items: list[UnassignedLineOut]
    total: int
    limit: int
    offset: int


class AssignIn(BaseModel):
    ingredient_id: int
    save_synonym: bool = True


class AssignOut(BaseModel):
    line: LineOut
    assigned_line_ids: list[int]
    recipe_ids: list[int]
    synonym: str | None


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except svc.RecipeNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (svc.RecipeServiceError, TargetsUnavailable, catalog.CatalogError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc


def _r(value: float, digits: int = 2) -> float:
    return round(value, digits)


def _nutrients(n: Nutrients) -> NutrientsOut:
    return NutrientsOut(
        kcal=_r(n.kcal, 1),
        protein_g=_r(n.protein_g),
        fat_g=_r(n.fat_g),
        carb_g=_r(n.carb_g),
        fiber_g=_r(n.fiber_g),
        salt_g=_r(n.salt_g, 3),
        micros={key: _r(value, 3) for key, value in n.micros.items()},
    )


def _tag(recipe: Recipe) -> TagOut:
    tag = recipe.tag
    if tag is None:
        return TagOut(
            slot_types=[], cuisine=None, main_ingredient=None, batch_cookable=False, transportable=False,
            warm=False, shelf_days=None, season=None,
        )  # fmt: skip
    return TagOut(
        slot_types=list(tag.slot_types or []),
        cuisine=tag.cuisine,
        main_ingredient=tag.main_ingredient,
        batch_cookable=bool(tag.batch_cookable),
        transportable=bool(tag.transportable),
        warm=bool(tag.warm),
        shelf_days=tag.shelf_days,
        season=tag.season,
    )


def _match(m: IngredientMatch) -> MatchOut:
    return MatchOut(ingredient_id=m.ingredient_id, name=m.name, score=_r(m.score, 1), via=m.via)


def _card_fields(
    recipe: Recipe,
    nutrition: RecipeNutrition,
    satiety: SatietyScore,
    person_id: int,
    fit: svc.FitResult | None,
) -> dict[str, Any]:
    ratings = [r.rating for r in recipe.ratings]
    mine = next((r.rating for r in recipe.ratings if r.person_id == person_id), None)
    per = nutrition.per_serving
    return {
        "id": recipe.id,
        "title": recipe.title,
        "image_url": recipe.image_url,
        "source_site": recipe.source_site,
        "favorite": bool(recipe.favorite),
        "status": recipe.status,
        "servings": recipe.servings,
        "prep_min": recipe.prep_min,
        "cook_min": recipe.cook_min,
        "tag": _tag(recipe),
        "kcal": _r(per.kcal, 1),
        "protein_g": _r(per.protein_g),
        "fat_g": _r(per.fat_g),
        "carb_g": _r(per.carb_g),
        "serving_weight_g": _r(nutrition.serving_weight_g, 1),
        "satiety_score": _r(satiety.score, 1),
        "coverage": _r(nutrition.coverage, 3),
        "my_rating": mine,
        "avg_rating": _r(sum(ratings) / len(ratings), 2) if ratings else None,
        "fit_score": _r(fit.fit.fit_score, 1) if fit else None,
        "fit_factor": _r(fit.fit.factor, 3) if fit else None,
    }


def _fit_out(fit: svc.FitResult) -> FitOut:
    t = fit.slot_target
    return FitOut(
        slot=fit.slot,
        date=fit.day,
        factor=_r(fit.fit.factor, 3),
        unclamped_factor=_r(fit.fit.unclamped_factor, 3),
        grams=_r(fit.fit.grams, 1),
        scaled=_nutrients(fit.fit.scaled),
        deviation_pct={key: _r(value, 1) for key, value in fit.fit.deviation_pct.items()},
        fit_score=_r(fit.fit.fit_score, 1),
        notes=fit.notes,
        slot_target=MacroOut(kcal=t.kcal, protein_g=t.protein_g, fat_g=t.fat_g, carb_g=t.carb_g),
        warnings=[WarningOut(code=w.code, severity=w.severity, message=w.message) for w in fit.warnings],
    )


def _line_out(line: RecipeIngredient) -> LineOut:
    ing = line.ingredient
    nutrients = None
    if ing is not None and line.grams is not None:
        nutrients = _nutrients(scale_nutrients(catalog.ingredient_to_per100(ing), line.grams))
    return LineOut(
        id=line.id,
        position=line.position,
        raw_text=line.raw_text,
        quantity=line.quantity,
        unit=line.unit,
        grams=line.grams,
        optional=bool(line.optional),
        ingredient=IngredientRefOut(id=ing.id, name=ing.name, source=ing.source) if ing else None,
        nutrients=nutrients,
    )


def _detail(db, recipe: Recipe, person_id: int, fit: svc.FitResult | None = None) -> RecipeDetailOut:
    nutrition = svc.compute_recipe_nutrition(recipe)
    satiety = svc.recipe_satiety(recipe, nutrition)
    return RecipeDetailOut(
        **_card_fields(recipe, nutrition, satiety, person_id, fit),
        source_url=recipe.source_url,
        instructions=recipe.instructions,
        notes=recipe.notes,
        lines=[_line_out(line) for line in recipe.ingredients],
        total=_nutrients(nutrition.total),
        per_serving=_nutrients(nutrition.per_serving),
        total_weight_g=_r(nutrition.total_weight_g, 1),
        energy_density_kcal_per_100g=(
            None
            if nutrition.energy_density_kcal_per_100g is None
            else _r(nutrition.energy_density_kcal_per_100g, 1)
        ),
        missing=nutrition.missing,
        satiety=SatietyOut(score=_r(satiety.score, 1), parts={k: _r(v, 3) for k, v in satiety.parts.items()}),
        ratings=[
            RatingOut(person_id=rating.person_id, person_name=name, rating=rating.rating)
            for rating, name in svc.ratings_with_names(db, recipe.id)
        ],
        fit=_fit_out(fit) if fit else None,
    )


def _load(db, recipe_id: int) -> Recipe:
    with _translate_errors():
        return svc.get_recipe(db, recipe_id)


def _reject_nulls(data: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in data and data[key] is None:
            raise HTTPException(422, detail=f"{key} darf nicht leer sein.")


def _import_error(exc: RecipeImportError) -> HTTPException:
    code = 422 if any(marker in str(exc) for marker in _BAD_INPUT_MARKERS) else status.HTTP_502_BAD_GATEWAY
    return HTTPException(code, detail=str(exc))


# ---------------------------------------------------------------------------
# Rezepte
# ---------------------------------------------------------------------------


@router.get("/recipes", response_model=RecipeListOut, summary="Rezepte auflisten (optional mit Passung)")
def list_recipes(
    person: CurrentPerson,
    db: Db,
    q: Annotated[str | None, Query(max_length=100, description="Suche im Titel")] = None,
    slot: Annotated[
        SlotName | None, Query(description="Nur Rezepte, die für diesen Slot getaggt sind")
    ] = None,
    include_untagged: Annotated[bool, Query(description="Mit `slot`: auch Rezepte ohne Slot-Tag")] = False,
    favorite: bool | None = None,
    status_: Annotated[RecipeStatus | None, Query(alias="status")] = None,
    fit_slot: Annotated[SlotName | None, Query(description="Passung für die angemeldete Person")] = None,
    fit_date: Annotated[date | None, Query(description="Stichtag der Passung, Standard: heute")] = None,
    sort: SortKey = "title",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecipeListOut:
    if sort == "fit" and fit_slot is None:
        raise HTTPException(422, detail="Für sort=fit wird fit_slot gebraucht.")
    recipes = svc.load_recipes(db, q=q, favorite=favorite, status=status_)
    if slot:
        recipes = [
            r
            for r in recipes
            if slot in (r.tag.slot_types if r.tag else [])
            or (include_untagged and not (r.tag and r.tag.slot_types))
        ]
    ctx = None
    if fit_slot:
        with _translate_errors():
            ctx = svc.slot_context(db, person, fit_date or today_local(), fit_slot)
    rows: list[tuple[Recipe, RecipeNutrition, SatietyScore, svc.FitResult | None]] = []
    for recipe in recipes:
        nutrition = svc.compute_recipe_nutrition(recipe)
        fit = svc.fit_nutrition(ctx, nutrition) if ctx else None
        rows.append((recipe, nutrition, svc.recipe_satiety(recipe, nutrition), fit))

    def my_rating(recipe: Recipe) -> int:
        return next((r.rating for r in recipe.ratings if r.person_id == person.id), 0)

    keys = {
        "title": lambda row: (row[0].title.lower(), row[0].id),
        "newest": lambda row: (-row[0].id,),
        "kcal": lambda row: (row[1].per_serving.kcal, row[0].title.lower()),
        "protein": lambda row: (-row[1].per_serving.protein_g, row[0].title.lower()),
        "satiety": lambda row: (-row[2].score, row[0].title.lower()),
        "rating": lambda row: (-my_rating(row[0]), row[0].title.lower()),
        "fit": lambda row: (-(row[3].fit.fit_score if row[3] else 0.0), row[0].title.lower()),
    }
    rows.sort(key=keys[sort])
    page = rows[offset : offset + limit]
    return RecipeListOut(
        items=[RecipeCardOut(**_card_fields(r, n, s, person.id, f)) for r, n, s, f in page],
        total=len(rows),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/recipes", response_model=RecipeDetailOut, status_code=status.HTTP_201_CREATED, summary="Rezept anlegen"
)
def create_recipe(body: RecipeCreate, person: CurrentPerson, db: Db) -> RecipeDetailOut:
    with _translate_errors():
        recipe = svc.create_manual_recipe(db, body.model_dump(exclude_unset=True))
    return _detail(db, svc.get_recipe(db, recipe.id), person.id)


@router.post(
    "/recipes/import-preview",
    response_model=ImportPreviewOut,
    summary="Rezept-URL prüfen (nichts wird gespeichert)",
)
def import_preview(body: UrlIn, _: CurrentPerson, db: Db) -> ImportPreviewOut:
    try:
        imported = recipe_web.import_recipe_url(body.url)
    except RecipeImportError as exc:
        raise _import_error(exc) from exc
    lines = svc.preview_lines(db, imported.ingredient_lines)
    return ImportPreviewOut(
        title=imported.title,
        source_url=imported.source_url,
        source_site=imported.source_site,
        servings=imported.servings,
        prep_min=imported.prep_min,
        cook_min=imported.cook_min,
        instructions=imported.instructions,
        image_url=imported.image_url,
        site_nutrients=imported.site_nutrients,
        warnings=imported.warnings,
        lines=[
            PreviewLineOut(
                raw_text=item.raw_text,
                name=item.parsed.name,
                quantity=item.parsed.quantity,
                unit=item.parsed.unit,
                note=item.parsed.note,
                optional=item.parsed.optional,
                grams=item.grams,
                ingredient_id=item.chosen.ingredient_id if item.chosen else None,
                ingredient_name=item.chosen.name if item.chosen else None,
                matches=[_match(m) for m in item.matches],
            )
            for item in lines
        ],
    )


@router.post(
    "/recipes/import",
    response_model=RecipeDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Rezept von einer URL importieren und speichern",
)
def import_recipe(body: UrlIn, person: CurrentPerson, db: Db) -> RecipeDetailOut:
    existing = svc.find_by_url(db, body.url)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Dieses Rezept ist schon vorhanden (ID {existing.id})."
        )
    try:
        imported = recipe_web.import_recipe_url(body.url)
    except RecipeImportError as exc:
        raise _import_error(exc) from exc
    result = svc.build_recipe_from_import(db, imported)
    detail = _detail(db, svc.get_recipe(db, result.recipe.id), person.id)
    detail.warnings = result.warnings
    return detail


@router.get("/recipes/{recipe_id}", response_model=RecipeDetailOut, summary="Rezept mit Nährwerten")
def get_recipe(
    recipe_id: int,
    person: CurrentPerson,
    db: Db,
    fit_slot: Annotated[SlotName | None, Query(description="Passung für die angemeldete Person")] = None,
    fit_date: Annotated[date | None, Query(description="Stichtag der Passung, Standard: heute")] = None,
) -> RecipeDetailOut:
    recipe = _load(db, recipe_id)
    fit = None
    if fit_slot:
        with _translate_errors():
            fit = svc.slot_fit_for_person(db, person, recipe, fit_date or today_local(), fit_slot)
    return _detail(db, recipe, person.id, fit)


@router.patch("/recipes/{recipe_id}", response_model=RecipeDetailOut, summary="Rezept ändern")
def patch_recipe(recipe_id: int, body: RecipePatch, person: CurrentPerson, db: Db) -> RecipeDetailOut:
    recipe = _load(db, recipe_id)
    data = body.model_dump(exclude_unset=True)
    _reject_nulls(data, ("title", "servings", "favorite", "lines"))
    with _translate_errors():
        svc.update_recipe(db, recipe, data)
    return _detail(db, svc.get_recipe(db, recipe_id), person.id)


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Rezept löschen")
def delete_recipe(recipe_id: int, _: CurrentPerson, db: Db) -> Response:
    db.delete(_load(db, recipe_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/recipes/{recipe_id}/fit",
    response_model=FitOut,
    summary="Passt das Rezept ins Mahlzeitenziel der Person?",
)
def recipe_fit(
    recipe_id: int,
    person: CurrentPerson,
    db: Db,
    slot: Annotated[SlotName, Query(description="Mahlzeit")],
    on: Annotated[date | None, Query(alias="date", description="Stichtag, Standard: heute")] = None,
) -> FitOut:
    recipe = _load(db, recipe_id)
    with _translate_errors():
        return _fit_out(svc.slot_fit_for_person(db, person, recipe, on or today_local(), slot))


@router.put("/recipes/{recipe_id}/rating", response_model=MyRatingOut, summary="Eigene Bewertung setzen")
def put_rating(recipe_id: int, body: RatingIn, person: CurrentPerson, db: Db) -> MyRatingOut:
    with _translate_errors():
        row = svc.set_rating(db, recipe_id, person.id, body.rating)
    return MyRatingOut(recipe_id=row.recipe_id, person_id=row.person_id, rating=row.rating)


@router.delete(
    "/recipes/{recipe_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eigene Bewertung entfernen",
)
def delete_rating(recipe_id: int, person: CurrentPerson, db: Db) -> Response:
    with _translate_errors():
        svc.remove_rating(db, recipe_id, person.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Prüfliste: Zeilen ohne Zutat
# ---------------------------------------------------------------------------


@router.get(
    "/recipe-lines/unassigned", response_model=UnassignedListOut, summary="Zutatenzeilen ohne Zuordnung"
)
def list_unassigned(
    _: CurrentPerson,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UnassignedListOut:
    items, total = svc.unassigned_lines(db, limit, offset)
    return UnassignedListOut(
        items=[
            UnassignedLineOut(
                line_id=item.line.id,
                recipe_id=item.recipe_id,
                recipe_title=item.recipe_title,
                raw_text=item.line.raw_text,
                name=item.name,
                quantity=item.line.quantity,
                unit=item.line.unit,
                similar_count=item.similar_count,
                suggestions=[_match(m) for m in item.suggestions],
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/recipe-lines/{line_id}/assign", response_model=AssignOut, summary="Zeile einer Zutat zuordnen")
def assign_line(line_id: int, body: AssignIn, _: CurrentPerson, db: Db) -> AssignOut:
    with _translate_errors():
        result = svc.assign_line(db, line_id, body.ingredient_id, save_synonym=body.save_synonym)
    return AssignOut(
        line=_line_out(result.line),
        assigned_line_ids=result.assigned_line_ids,
        recipe_ids=result.recipe_ids,
        synonym=result.synonym,
    )
