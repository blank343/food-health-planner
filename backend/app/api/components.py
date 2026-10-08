"""Komponenten-Baukasten (Christians Frühstück): `/api/components` (siehe docs/PHASE2.md, Abschnitt 7).

Komponenten sind gemeinsam sichtbar und pflegbar (nicht personengebunden). Die Passung ins Tagesziel
in `POST /components/meal` gilt immer für die angemeldete Person.
"""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.deps import CurrentPerson, Db
from app.api.targets import MacroOut, WarningOut
from app.models import Component, ComponentVariant, Ingredient
from app.services import components as svc
from app.services.targets import TargetsUnavailable

router = APIRouter(prefix="/components", tags=["Komponenten (Frühstücks-Baukasten)"])

Kind = Literal["protein", "carb", "dairy", "fruit", "veg", "other"]
SlotName = Literal["breakfast", "lunch", "dinner", "snack"]

SODIUM_TO_SALT = 2.5


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class Per100Out(BaseModel):
    """Nährwerte der Zutat je 100 g (None = unbekannt)."""

    kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carb_g: float | None
    fiber_g: float | None
    salt_g: float | None
    micros: dict[str, float]


class VariantOut(BaseModel):
    id: int
    component_id: int
    name: str
    ingredient_id: int
    ingredient_name: str
    grams_per_unit: float | None
    per100: Per100Out


class ComponentOut(BaseModel):
    id: int
    name: str
    kind: str
    ingredient_id: int
    ingredient_name: str
    min_g: float
    max_g: float
    step_g: float
    typical_g: float | None
    weekend_fixed: bool
    per100: Per100Out
    variants: list[VariantOut]


class ComponentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    kind: Kind
    ingredient_id: int = Field(gt=0)
    min_g: float = Field(default=0.0, ge=0, le=10_000)
    max_g: float = Field(default=500.0, gt=0, le=10_000)
    step_g: float = Field(default=10.0, gt=0, le=10_000)
    typical_g: float | None = Field(default=None, ge=0, le=10_000)
    weekend_fixed: bool = False


class ComponentPatch(BaseModel):
    """Nur gesendete Felder werden geändert; `typical_g: null` löscht die übliche Menge."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: Kind | None = None
    ingredient_id: int | None = Field(default=None, gt=0)
    min_g: float | None = Field(default=None, ge=0, le=10_000)
    max_g: float | None = Field(default=None, gt=0, le=10_000)
    step_g: float | None = Field(default=None, gt=0, le=10_000)
    typical_g: float | None = Field(default=None, ge=0, le=10_000)
    weekend_fixed: bool | None = None


class VariantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    ingredient_id: int | None = Field(default=None, gt=0, description="Standard: Zutat der Komponente")
    grams_per_unit: float | None = Field(default=None, gt=0, le=10_000, description="z. B. 1 Ei = 60 g")


class VariantPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    ingredient_id: int | None = Field(default=None, gt=0)
    grams_per_unit: float | None = Field(default=None, gt=0, le=10_000)


class MealItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: int = Field(gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    grams: float | None = Field(default=None, ge=0, le=10_000)
    units: float | None = Field(default=None, ge=0, le=1000, description="Stück × Gewicht je Einheit")

    @model_validator(mode="after")
    def _one_amount(self) -> "MealItemIn":
        if (self.grams is None) == (self.units is None):
            raise ValueError("Bitte entweder Gramm oder Stückzahl angeben.")
        return self


class MealIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    items: list[MealItemIn] = Field(min_length=1, max_length=50)
    date: dt.date | None = Field(default=None, description="Stichtag für die Passung, Standard: heute")
    slot: SlotName | None = Field(default=None, description="Slot für die Passung ins Tagesziel")

    @model_validator(mode="after")
    def _slot_for_date(self) -> "MealIn":
        if self.date is not None and self.slot is None:
            raise ValueError("Für die Passung ins Tagesziel bitte auch den Slot angeben.")
        return self


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


class MealLineOut(BaseModel):
    component_id: int
    component_name: str
    variant_id: int | None
    variant_name: str | None
    ingredient_id: int
    ingredient_name: str
    grams: float
    units: float | None
    nutrients: NutrientsOut


class MealFitOut(BaseModel):
    slot: str
    date: dt.date
    target: MacroOut
    deviation_pct: dict[str, float]
    fit_score: float
    notes: list[str]
    warnings: list[WarningOut]


class MealOut(BaseModel):
    total: NutrientsOut
    weight_g: float
    energy_density_kcal_per_100g: float | None
    satiety: SatietyOut
    coverage: float
    missing: list[str]
    lines: list[MealLineOut]
    notes: list[str]
    fit: MealFitOut | None


class SeedOut(BaseModel):
    created: list[str]
    skipped: list[str]
    missing: list[str]
    variants_created: int
    missing_variants: list[str]
    matched: dict[str, str]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


@contextmanager
def _mapped_errors() -> Iterator[None]:
    """Dienstfehler → HTTP: nicht gefunden 404, Konflikt 409, sonst 422 (deutsche Meldung)."""
    try:
        yield
    except svc.ComponentNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except svc.ComponentConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    except svc.ComponentError as e:
        raise HTTPException(422, detail=str(e)) from e
    except TargetsUnavailable as e:
        raise HTTPException(422, detail=str(e)) from e


def _per100_out(ing: Ingredient) -> Per100Out:
    salt = ing.salt_100
    micros = svc.ingredient_to_per100(ing).micros
    if salt is None and "sodium_mg" in micros:
        salt = micros["sodium_mg"] * SODIUM_TO_SALT / 1000.0
    return Per100Out(
        kcal=ing.kcal_100,
        protein_g=ing.protein_100,
        fat_g=ing.fat_100,
        carb_g=ing.carb_100,
        fiber_g=ing.fiber_100,
        salt_g=salt,
        micros=micros,
    )


def _variant_out(v: ComponentVariant) -> VariantOut:
    return VariantOut(
        id=v.id,
        component_id=v.component_id,
        name=v.name,
        ingredient_id=v.ingredient_id,
        ingredient_name=v.ingredient.name,
        grams_per_unit=v.grams_per_unit,
        per100=_per100_out(v.ingredient),
    )


def _component_out(c: Component) -> ComponentOut:
    return ComponentOut(
        id=c.id,
        name=c.name,
        kind=c.kind,
        ingredient_id=c.ingredient_id,
        ingredient_name=c.ingredient.name,
        min_g=c.min_g,
        max_g=c.max_g,
        step_g=c.step_g,
        typical_g=c.typical_g,
        weekend_fixed=c.weekend_fixed,
        per100=_per100_out(c.ingredient),
        variants=[_variant_out(v) for v in sorted(c.variants, key=lambda v: (v.name.casefold(), v.id))],
    )


def _nutrients_out(n) -> NutrientsOut:
    return NutrientsOut(
        kcal=round(n.kcal, 2),
        protein_g=round(n.protein_g, 2),
        fat_g=round(n.fat_g, 2),
        carb_g=round(n.carb_g, 2),
        fiber_g=round(n.fiber_g, 2),
        salt_g=round(n.salt_g, 2),
        micros={key: round(value, 3) for key, value in n.micros.items()},
    )


def _meal_out(r: svc.MealResult) -> MealOut:
    fit = None
    if r.fit is not None:
        t = r.fit.target
        fit = MealFitOut(
            slot=r.fit.slot,
            date=r.fit.day,
            target=MacroOut(kcal=t.kcal, protein_g=t.protein_g, fat_g=t.fat_g, carb_g=t.carb_g),
            deviation_pct={key: round(value, 1) for key, value in r.fit.deviation_pct.items()},
            fit_score=round(r.fit.fit_score, 1),
            notes=r.fit.notes,
            warnings=[
                WarningOut(code=w.code, severity=w.severity, message=w.message) for w in r.fit.warnings
            ],
        )
    return MealOut(
        total=_nutrients_out(r.total),
        weight_g=round(r.weight_g, 1),
        energy_density_kcal_per_100g=(
            None if r.energy_density_kcal_per_100g is None else round(r.energy_density_kcal_per_100g, 1)
        ),
        satiety=SatietyOut(
            score=round(r.satiety.score, 1), parts={k: round(v, 3) for k, v in r.satiety.parts.items()}
        ),
        coverage=round(r.coverage, 3),
        missing=r.missing,
        lines=[
            MealLineOut(
                component_id=line.component_id,
                component_name=line.component_name,
                variant_id=line.variant_id,
                variant_name=line.variant_name,
                ingredient_id=line.ingredient_id,
                ingredient_name=line.ingredient_name,
                grams=round(line.grams, 1),
                units=line.units,
                nutrients=_nutrients_out(line.nutrients),
            )
            for line in r.lines
        ],
        notes=r.notes,
        fit=fit,
    )


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------


@router.get(
    "", response_model=list[ComponentOut], summary="Komponenten: Liste (mit Varianten und Nährwerten)"
)
def list_components(person: CurrentPerson, db: Db) -> list[ComponentOut]:
    return [_component_out(c) for c in svc.list_components(db)]


@router.post(
    "", response_model=ComponentOut, status_code=status.HTTP_201_CREATED, summary="Komponente anlegen"
)
def create_component(body: ComponentIn, person: CurrentPerson, db: Db) -> ComponentOut:
    with _mapped_errors():
        comp = svc.create_component(db, **body.model_dump())
    return _component_out(comp)


@router.post(
    "/seed-defaults",
    response_model=SeedOut,
    summary="Standard-Komponenten für das Frühstück anlegen (idempotent)",
    description=(
        "Legt zu den im Zutaten-Katalog gefundenen Zutaten die Standard-Komponenten an. Nicht gefundene "
        "Namen stehen in `missing`. Vorhandene Komponenten gleichen Namens werden übersprungen."
    ),
)
def seed_defaults(person: CurrentPerson, db: Db) -> SeedOut:
    with _mapped_errors():
        return SeedOut(**svc.seed_default_components(db))


@router.post(
    "/meal",
    response_model=MealOut,
    summary="Baukasten-Mahlzeit berechnen (Nährwerte, Sättigung, Passung ins Tagesziel)",
    description=(
        "Mengen je Komponente als `grams` oder `units` (Stück × Gewicht je Einheit der Variante). Mit `slot` "
        "(und optional `date`) kommt die Passung ins Slot-Ziel der angemeldeten Person dazu, ohne "
        "Portionsskalierung."
    ),
)
def compute_meal(body: MealIn, person: CurrentPerson, db: Db) -> MealOut:
    items = [svc.MealItem(i.component_id, i.variant_id, i.grams, i.units) for i in body.items]
    with _mapped_errors():
        result = svc.compute_meal(db, items, person=person, on=body.date, slot=body.slot)
    return _meal_out(result)


@router.get("/{component_id}", response_model=ComponentOut, summary="Komponente lesen")
def get_component(component_id: int, person: CurrentPerson, db: Db) -> ComponentOut:
    with _mapped_errors():
        return _component_out(svc.get_component(db, component_id))


@router.patch("/{component_id}", response_model=ComponentOut, summary="Komponente ändern")
def update_component(component_id: int, body: ComponentPatch, person: CurrentPerson, db: Db) -> ComponentOut:
    with _mapped_errors():
        comp = svc.get_component(db, component_id)
        comp = svc.update_component(db, comp, body.model_dump(exclude_unset=True))
    return _component_out(comp)


@router.delete(
    "/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Komponente löschen (409, falls noch verwendet)",
)
def delete_component(component_id: int, person: CurrentPerson, db: Db) -> Response:
    with _mapped_errors():
        svc.delete_component(db, svc.get_component(db, component_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{component_id}/variants",
    response_model=VariantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Variante anlegen",
)
def create_variant(component_id: int, body: VariantIn, person: CurrentPerson, db: Db) -> VariantOut:
    with _mapped_errors():
        comp = svc.get_component(db, component_id)
        variant = svc.create_variant(
            db,
            comp,
            name=body.name,
            ingredient_id=body.ingredient_id,
            grams_per_unit=body.grams_per_unit,
        )
    return _variant_out(variant)


@router.patch("/{component_id}/variants/{variant_id}", response_model=VariantOut, summary="Variante ändern")
def update_variant(
    component_id: int, variant_id: int, body: VariantPatch, person: CurrentPerson, db: Db
) -> VariantOut:
    with _mapped_errors():
        comp = svc.get_component(db, component_id)
        variant = svc.get_variant(db, comp, variant_id)
        variant = svc.update_variant(db, comp, variant, body.model_dump(exclude_unset=True))
    return _variant_out(variant)


@router.delete(
    "/{component_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Variante löschen",
)
def delete_variant(component_id: int, variant_id: int, person: CurrentPerson, db: Db) -> Response:
    with _mapped_errors():
        comp = svc.get_component(db, component_id)
        svc.delete_variant(db, comp, svc.get_variant(db, comp, variant_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
