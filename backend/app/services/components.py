"""Komponenten-Baukasten (Christians Frühstück): CRUD, Mahlzeitberechnung mit Passung, Standard-Seed.

Siehe docs/PHASE2.md (Abschnitte 3, 4.2, 6 und 7). Der Baukasten arbeitet mit festen Mengen, es gibt
keine Portionsskalierung: Die gewählten Mengen sind die Mengen. Das Vorschlagen von Mengen
(`suggest_amounts`) ist Aufgabe des Planers in Phase 3.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.calc import slots as slot_calc
from app.calc.ingredients import CatalogEntry, match_ingredient, normalize_name
from app.calc.nutrition import component_meal, fit_to_target, satiety_score, scale_nutrients
from app.calc.types import (
    ComponentChoice,
    Nutrients,
    NutrientsPer100,
    SatietyScore,
    SlotTarget,
    Warning,
)
from app.config import get_settings
from app.models import Component, ComponentVariant, Ingredient, IngredientSynonym, Person
from app.services import targets as targets_svc

COMPONENT_KINDS = ("protein", "carb", "dairy", "fruit", "veg", "other")
SLOT_LABELS = {"breakfast": "Frühstück", "lunch": "Mittagessen", "dinner": "Abendessen", "snack": "Snack"}
SEED_MIN_SCORE = 85.0  # nur sichere Katalogtreffer, niemals raten
HEAVY_MEAL_G = 1500.0  # darüber gibt es einen Hinweis zum Gewicht der Mahlzeit
KCAL_NOTE_PCT = 10.0  # Hinweis zur Energie ab dieser Abweichung vom Slot-Ziel
_MAX_G_LIMIT = 10_000.0
_FIT_NOTE_PREFIXES = ("Protein ", "Fett ", "Kohlenhydrate ")
_COMPONENT_FIELDS = {
    "name",
    "kind",
    "ingredient_id",
    "min_g",
    "max_g",
    "step_g",
    "typical_g",
    "weekend_fixed",
}
_NULLABLE_COMPONENT_FIELDS = {"typical_g"}
_VARIANT_FIELDS = {"name", "ingredient_id", "grams_per_unit"}
_NULLABLE_VARIANT_FIELDS = {"grams_per_unit"}


class ComponentError(Exception):
    """Ungültige Eingabe oder nicht berechenbar (deutsche, für Nutzer gedachte Meldung)."""


class ComponentNotFound(ComponentError):
    """Komponente oder Variante existiert nicht."""


class ComponentConflict(ComponentError):
    """Name schon vergeben oder Eintrag wird noch verwendet."""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _de(value: float, digits: int = 1) -> str:
    """Zahl mit deutschem Komma ohne überflüssige Nullen (2.0 → "2", 1.75 → "1,8")."""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text.replace(".", ",")


def ingredient_to_per100(ing: Ingredient) -> NutrientsPer100:
    """Nährwerte je 100 g einer Zutat; unbekannte Werte bleiben None (zählen nicht als 0)."""
    micros = {
        key: float(value)
        for key, value in (ing.micros or {}).items()
        if isinstance(value, int | float) and not isinstance(value, bool)
    }
    return NutrientsPer100(
        kcal=ing.kcal_100,
        protein_g=ing.protein_100,
        fat_g=ing.fat_100,
        carb_g=ing.carb_100,
        fiber_g=ing.fiber_100,
        salt_g=ing.salt_100,
        micros=micros,
    )


def _today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def _clean_name(name: Any, what: str) -> str:
    text = name.strip() if isinstance(name, str) else ""
    if not text:
        raise ComponentError(f"Der Name {what} darf nicht leer sein.")
    if len(text) > 120:
        raise ComponentError(f"Der Name {what} darf höchstens 120 Zeichen lang sein.")
    return text


def _get_ingredient(session: Session, ingredient_id: Any) -> Ingredient:
    ing = session.get(Ingredient, ingredient_id) if isinstance(ingredient_id, int) else None
    if ing is None:
        raise ComponentError(f"Die Zutat {ingredient_id} wurde nicht gefunden.")
    return ing


def _validate_amounts(min_g: Any, max_g: Any, step_g: Any, typical_g: Any) -> None:
    def num(value: Any) -> bool:
        return isinstance(value, int | float) and not isinstance(value, bool) and value == value

    if not (num(min_g) and num(max_g) and num(step_g)):
        raise ComponentError("Mindest-, Höchst- und Schrittmenge müssen Zahlen sein.")
    if min_g < 0:
        raise ComponentError("Die Mindestmenge darf nicht negativ sein.")
    if max_g > _MAX_G_LIMIT:
        raise ComponentError(f"Die Höchstmenge darf höchstens {_de(_MAX_G_LIMIT, 0)} g betragen.")
    if min_g > max_g:
        raise ComponentError("Die Mindestmenge darf nicht größer als die Höchstmenge sein.")
    if step_g <= 0:
        raise ComponentError("Die Schrittweite muss größer als 0 sein.")
    if typical_g is not None:
        if not num(typical_g):
            raise ComponentError("Die übliche Menge muss eine Zahl sein.")
        if not min_g <= typical_g <= max_g:
            raise ComponentError("Die übliche Menge muss zwischen Mindest- und Höchstmenge liegen.")


def _validate_gpu(grams_per_unit: Any) -> None:
    if grams_per_unit is None:
        return
    ok = isinstance(grams_per_unit, int | float) and not isinstance(grams_per_unit, bool)
    if not ok or not 0 < grams_per_unit <= _MAX_G_LIMIT:
        raise ComponentError("Das Gewicht je Einheit muss größer als 0 sein.")


def _check_kind(kind: Any) -> None:
    if kind not in COMPONENT_KINDS:
        raise ComponentError(f"Ungültige Art „{kind}“. Erlaubt: {', '.join(COMPONENT_KINDS)}.")


def _name_taken(session: Session, name: str, *, exclude_id: int | None = None) -> bool:
    key = name.casefold()
    return any(c.name.casefold() == key and c.id != exclude_id for c in session.scalars(select(Component)))


def _commit(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise ComponentConflict(message) from e


# ---------------------------------------------------------------------------
# CRUD: Komponenten
# ---------------------------------------------------------------------------


def list_components(session: Session) -> list[Component]:
    """Alle Komponenten (Werktag zuerst, dann Wochenende), je mit Zutat und Varianten."""
    stmt = (
        select(Component)
        .options(
            selectinload(Component.ingredient),
            selectinload(Component.variants).selectinload(ComponentVariant.ingredient),
        )
        .order_by(Component.weekend_fixed, Component.kind, Component.name, Component.id)
    )
    return list(session.scalars(stmt))


def get_component(session: Session, component_id: int) -> Component:
    comp = session.get(Component, component_id)
    if comp is None:
        raise ComponentNotFound("Komponente nicht gefunden.")
    return comp


def get_variant(session: Session, component: Component, variant_id: int) -> ComponentVariant:
    for variant in component.variants:
        if variant.id == variant_id:
            return variant
    raise ComponentNotFound("Variante nicht gefunden.")


def _add_component(
    session: Session,
    *,
    name: str,
    kind: str,
    ingredient_id: int,
    min_g: float = 0.0,
    max_g: float = 500.0,
    step_g: float = 10.0,
    typical_g: float | None = None,
    weekend_fixed: bool = False,
) -> Component:
    name = _clean_name(name, "der Komponente")
    _check_kind(kind)
    _get_ingredient(session, ingredient_id)
    _validate_amounts(min_g, max_g, step_g, typical_g)
    if _name_taken(session, name):
        raise ComponentConflict(f"Eine Komponente „{name}“ gibt es schon.")
    comp = Component(
        name=name,
        kind=kind,
        ingredient_id=ingredient_id,
        min_g=float(min_g),
        max_g=float(max_g),
        step_g=float(step_g),
        typical_g=None if typical_g is None else float(typical_g),
        weekend_fixed=bool(weekend_fixed),
    )
    session.add(comp)
    session.flush()
    return comp


def create_component(
    session: Session,
    *,
    name: str,
    kind: str,
    ingredient_id: int,
    min_g: float = 0.0,
    max_g: float = 500.0,
    step_g: float = 10.0,
    typical_g: float | None = None,
    weekend_fixed: bool = False,
) -> Component:
    """Legt eine Komponente an (prüft Name, Art, Zutat und Mengenspanne)."""
    comp = _add_component(
        session,
        name=name,
        kind=kind,
        ingredient_id=ingredient_id,
        min_g=min_g,
        max_g=max_g,
        step_g=step_g,
        typical_g=typical_g,
        weekend_fixed=weekend_fixed,
    )
    _commit(session, "Die Komponente konnte nicht gespeichert werden.")
    return comp


def update_component(session: Session, component: Component, changes: dict[str, Any]) -> Component:
    """Ändert die übergebenen Felder; der zusammengeführte Datensatz wird vollständig geprüft."""
    unknown = set(changes) - _COMPONENT_FIELDS
    if unknown:
        raise ComponentError(f"Unbekannte Felder: {', '.join(sorted(unknown))}.")
    for key, value in changes.items():
        if value is None and key not in _NULLABLE_COMPONENT_FIELDS:
            raise ComponentError(f"Das Feld „{key}“ darf nicht leer sein.")
    values = {key: getattr(component, key) for key in _COMPONENT_FIELDS} | changes
    values["name"] = _clean_name(values["name"], "der Komponente")
    _check_kind(values["kind"])
    if "ingredient_id" in changes:
        _get_ingredient(session, values["ingredient_id"])
    _validate_amounts(values["min_g"], values["max_g"], values["step_g"], values["typical_g"])
    if _name_taken(session, values["name"], exclude_id=component.id):
        raise ComponentConflict(f"Eine Komponente „{values['name']}“ gibt es schon.")
    for key, value in values.items():
        setattr(component, key, value)
    _commit(session, "Die Komponente konnte nicht gespeichert werden.")
    return component


def delete_component(session: Session, component: Component) -> None:
    """Löscht die Komponente samt Varianten; ComponentConflict, falls sie noch verwendet wird."""
    session.delete(component)
    _commit(session, "Die Komponente wird noch verwendet und kann nicht gelöscht werden.")


# ---------------------------------------------------------------------------
# CRUD: Varianten
# ---------------------------------------------------------------------------


def _add_variant(
    session: Session,
    component: Component,
    *,
    name: str,
    ingredient_id: int | None = None,
    grams_per_unit: float | None = None,
) -> ComponentVariant:
    name = _clean_name(name, "der Variante")
    ingredient_id = component.ingredient_id if ingredient_id is None else ingredient_id
    _get_ingredient(session, ingredient_id)
    _validate_gpu(grams_per_unit)
    if any(v.name.casefold() == name.casefold() for v in component.variants):
        raise ComponentConflict(f"Eine Variante „{name}“ gibt es bei dieser Komponente schon.")
    variant = ComponentVariant(
        component=component,  # hängt die Variante über die Beziehung an component.variants an
        name=name,
        ingredient_id=ingredient_id,
        grams_per_unit=None if grams_per_unit is None else float(grams_per_unit),
    )
    session.add(variant)
    session.flush()
    return variant


def create_variant(
    session: Session,
    component: Component,
    *,
    name: str,
    ingredient_id: int | None = None,
    grams_per_unit: float | None = None,
) -> ComponentVariant:
    """Legt eine Variante an. Ohne `ingredient_id` gilt die Zutat der Komponente."""
    variant = _add_variant(
        session, component, name=name, ingredient_id=ingredient_id, grams_per_unit=grams_per_unit
    )
    _commit(session, "Die Variante konnte nicht gespeichert werden.")
    return variant


def update_variant(
    session: Session, component: Component, variant: ComponentVariant, changes: dict[str, Any]
) -> ComponentVariant:
    unknown = set(changes) - _VARIANT_FIELDS
    if unknown:
        raise ComponentError(f"Unbekannte Felder: {', '.join(sorted(unknown))}.")
    for key, value in changes.items():
        if value is None and key not in _NULLABLE_VARIANT_FIELDS:
            raise ComponentError(f"Das Feld „{key}“ darf nicht leer sein.")
    values = {key: getattr(variant, key) for key in _VARIANT_FIELDS} | changes
    values["name"] = _clean_name(values["name"], "der Variante")
    if "ingredient_id" in changes:
        _get_ingredient(session, values["ingredient_id"])
    _validate_gpu(values["grams_per_unit"])
    if any(v.name.casefold() == values["name"].casefold() and v.id != variant.id for v in component.variants):
        raise ComponentConflict(f"Eine Variante „{values['name']}“ gibt es bei dieser Komponente schon.")
    for key, value in values.items():
        setattr(variant, key, value)
    _commit(session, "Die Variante konnte nicht gespeichert werden.")
    return variant


def delete_variant(session: Session, component: Component, variant: ComponentVariant) -> None:
    component.variants.remove(variant)  # delete-orphan löscht die Zeile
    _commit(session, "Die Variante wird noch verwendet und kann nicht gelöscht werden.")


# ---------------------------------------------------------------------------
# Mahlzeit berechnen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MealItem:
    """Eine Komponente mit Menge: entweder `grams` oder `units` (Stück, × Gewicht je Einheit)."""

    component_id: int
    variant_id: int | None = None
    grams: float | None = None
    units: float | None = None


@dataclass(frozen=True)
class MealLine:
    component_id: int
    component_name: str
    variant_id: int | None
    variant_name: str | None
    ingredient_id: int
    ingredient_name: str
    grams: float
    units: float | None
    nutrients: Nutrients


@dataclass(frozen=True)
class MealFit:
    """Passung der Summe ins Slot-Ziel der Person (ohne Portionsskalierung, Faktor fest 1)."""

    slot: str
    day: date
    target: SlotTarget
    deviation_pct: dict[str, float]  # kcal, protein, fat, carb
    fit_score: float  # 0–100
    notes: list[str] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)


@dataclass(frozen=True)
class MealResult:
    total: Nutrients
    weight_g: float
    energy_density_kcal_per_100g: float | None
    satiety: SatietyScore
    coverage: float
    missing: list[str]
    lines: list[MealLine]
    notes: list[str] = field(default_factory=list)
    fit: MealFit | None = None


def _resolve_item(
    session: Session, item: MealItem
) -> tuple[Component, ComponentVariant | None, Ingredient, float, float | None]:
    comp = session.get(Component, item.component_id)
    if comp is None:
        raise ComponentNotFound(f"Die Komponente {item.component_id} wurde nicht gefunden.")
    variant: ComponentVariant | None = None
    if item.variant_id is not None:
        variant = next((v for v in comp.variants if v.id == item.variant_id), None)
        if variant is None:
            raise ComponentError(f"Die Variante {item.variant_id} gehört nicht zur Komponente „{comp.name}“.")
    ingredient = variant.ingredient if variant is not None else comp.ingredient

    if (item.grams is None) == (item.units is None):
        raise ComponentError(f"Bei „{comp.name}“ bitte entweder Gramm oder Stückzahl angeben.")
    if item.grams is not None:
        if not 0 <= item.grams <= _MAX_G_LIMIT:
            raise ComponentError(f"Ungültige Menge bei „{comp.name}“.")
        return comp, variant, ingredient, float(item.grams), None
    units = item.units
    if units is None or not 0 <= units <= 1000:
        raise ComponentError(f"Ungültige Stückzahl bei „{comp.name}“.")
    per_unit = (variant.grams_per_unit if variant is not None else None) or ingredient.piece_g
    if not per_unit:
        raise ComponentError(
            f"Für „{comp.name}“ ist kein Gewicht je Einheit hinterlegt. Bitte Gramm angeben."
        )
    return comp, variant, ingredient, float(units) * float(per_unit), float(units)


def _meal_fit(
    session: Session, person: Person, on: date | None, slot: str, total: Nutrients, weight_g: float
) -> MealFit:
    day = on or _today()
    result = targets_svc.compute_targets(session, person, day)  # TargetsUnavailable wird durchgereicht
    label = SLOT_LABELS.get(slot, slot)
    if slot not in result.slots or result.shares.get(slot, 0) <= 0:
        raise ComponentError(f"Der Slot „{label}“ kommt im Plan dieses Tages nicht vor.")
    target = result.slots[slot]
    fit = fit_to_target(total, weight_g, target, min_factor=1.0, max_factor=1.0)

    notes = [n for n in fit.notes if n.startswith(_FIT_NOTE_PREFIXES)]
    kcal_dev = fit.deviation_pct["kcal"]
    if target.kcal > 0 and abs(kcal_dev) >= KCAL_NOTE_PCT:
        direction = "unter" if kcal_dev < 0 else "über"
        notes.insert(
            0,
            f"Energie {_de(total.kcal, 0)} kcal: {_de(abs(kcal_dev), 0)} % {direction} dem Ziel "
            f"von {_de(target.kcal, 0)} kcal",
        )
    meal_as_target = SlotTarget(
        kcal=total.kcal, protein_g=total.protein_g, fat_g=total.fat_g, carb_g=total.carb_g
    )
    warnings = slot_calc.single_meal_check(meal_as_target, targets_svc.load_settings(session, person.id))
    return MealFit(
        slot=slot,
        day=day,
        target=target,
        deviation_pct=fit.deviation_pct,
        fit_score=fit.fit_score,
        notes=notes,
        warnings=warnings,
    )


def compute_meal(
    session: Session,
    items: list[MealItem],
    *,
    person: Person | None = None,
    on: date | None = None,
    slot: str | None = None,
) -> MealResult:
    """Nährwerte, Gewicht und Sättigung einer Baukasten-Mahlzeit; mit `person` und `slot` auch die Passung.

    Die Menge je Posten ist entweder `grams` oder `units` × Gewicht je Einheit der Variante (ersatzweise
    `piece_g` der Zutat). Die Zutat kommt aus der Variante, sonst aus der Komponente. Die Passung nutzt
    das Slot-Ziel der Person am Tag `on` (Standard: heute) ohne Portionsskalierung.
    Wirft `ComponentError` (Eingabe) und `TargetsUnavailable` (Ziele nicht berechenbar).
    """
    if not items:
        raise ComponentError("Bitte mindestens eine Komponente angeben.")
    if slot is not None and person is None:
        raise ComponentError("Für die Passung ins Tagesziel wird eine Person benötigt.")

    resolved = [_resolve_item(session, item) for item in items]
    choices: list[ComponentChoice] = []
    for comp, variant, ingredient, grams, _units in resolved:
        label = f"{comp.name} ({variant.name})" if variant is not None else comp.name
        choices.append(ComponentChoice(label=label, grams=grams, per100=ingredient_to_per100(ingredient)))
    nutrition = component_meal(choices)

    # Einzelwerte je Posten (gleiche Rechnung wie in der Summe)
    lines: list[MealLine] = []
    notes: list[str] = []
    for (comp, variant, ingredient, grams, units), choice in zip(resolved, choices, strict=True):
        lines.append(
            MealLine(
                component_id=comp.id,
                component_name=comp.name,
                variant_id=variant.id if variant is not None else None,
                variant_name=variant.name if variant is not None else None,
                ingredient_id=ingredient.id,
                ingredient_name=ingredient.name,
                grams=grams,
                units=units,
                nutrients=scale_nutrients(choice.per100, grams),
            )
        )
        if grams > comp.max_g:
            notes.append(
                f"{comp.name}: {_de(grams, 0)} g liegen über dem üblichen Maximum von {_de(comp.max_g, 0)} g"
            )
        elif comp.min_g > 0 and grams < comp.min_g:
            notes.append(
                f"{comp.name}: {_de(grams, 0)} g liegen unter dem Minimum von {_de(comp.min_g, 0)} g"
            )

    weight = nutrition.total_weight_g
    if weight > 0:
        weight_text = f"{_de(weight / 1000, 1)} kg" if weight >= 1000 else f"{_de(weight, 0)} g"
        suffix = ": sehr viel auf einmal" if weight >= HEAVY_MEAL_G else ""
        notes.insert(0, f"Mahlzeit wiegt {weight_text}{suffix}")
    notes.insert(min(1, len(notes)), f"Salz in dieser Mahlzeit: {_de(nutrition.total.salt_g, 1)} g")
    if nutrition.missing:
        notes.append(f"Keine Kalorienwerte für: {', '.join(nutrition.missing)}")

    fit = None
    if slot is not None and person is not None:
        fit = _meal_fit(session, person, on, slot, nutrition.total, weight)

    return MealResult(
        total=nutrition.total,
        weight_g=weight,
        energy_density_kcal_per_100g=nutrition.energy_density_kcal_per_100g,
        satiety=satiety_score(nutrition, warm=False),
        coverage=nutrition.coverage,
        missing=list(nutrition.missing),
        lines=lines,
        notes=notes,
        fit=fit,
    )


# ---------------------------------------------------------------------------
# Standard-Komponenten (Christians Frühstück)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _VariantSeed:
    name: str
    grams_per_unit: float | None
    candidates: tuple[str, ...] | None = None  # None = Zutat der Komponente; sonst optional (nur bei Treffer)


@dataclass(frozen=True)
class _ComponentSeed:
    name: str
    kind: str
    candidates: tuple[str, ...]  # Zutatennamen, der Reihe nach probiert
    min_g: float
    max_g: float
    step_g: float
    typical_g: float
    weekend_fixed: bool = False
    variants: tuple[_VariantSeed, ...] = ()


_EGG = (_VariantSeed("Stück", 60.0), _VariantSeed("Rührei", 60.0, ("Rührei",)))
_BREAD = ("Vollkornbrot", "Mischbrot", "Brot")
_QUARK = ("Kräuterquark",)
_JAM = ("Marmelade", "Konfitüre", "Fruchtaufstrich")

DEFAULT_COMPONENTS: tuple[_ComponentSeed, ...] = (
    # Werktag (Mo–Fr)
    _ComponentSeed("Ei", "protein", ("Hühnerei", "Ei", "Vollei"), 0, 360, 60, 120, variants=_EGG),
    _ComponentSeed("Brot", "carb", _BREAD, 0, 200, 10, 100, variants=(_VariantSeed("Scheibe", 45.0),)),
    _ComponentSeed(
        "Brötchen",
        "carb",
        ("Brötchen", "Weizenbrötchen", "Semmel"),
        0,
        180,
        10,
        60,
        variants=(_VariantSeed("Stück", 55.0),),
    ),
    _ComponentSeed("Kräuterquark", "dairy", _QUARK, 0, 300, 10, 100),
    _ComponentSeed("Skyr", "dairy", ("Skyr",), 0, 400, 10, 250),
    _ComponentSeed("Apfel", "fruit", ("Apfel",), 0, 360, 180, 180, variants=(_VariantSeed("Stück", 180.0),)),
    _ComponentSeed(
        "Banane", "fruit", ("Banane",), 0, 240, 120, 120, variants=(_VariantSeed("Stück", 120.0),)
    ),
    _ComponentSeed(
        "Saure Gurken",
        "veg",
        ("Gewürzgurke", "Saure Gurke", "Essiggurke"),
        0,
        200,
        10,
        50,
        variants=(_VariantSeed("Stück", 40.0),),
    ),
    _ComponentSeed("Tomate", "veg", ("Tomate",), 0, 300, 10, 100, variants=(_VariantSeed("Stück", 100.0),)),
    # Wochenende (fest, wird nicht geplant)
    _ComponentSeed("Brot (Wochenende)", "carb", _BREAD, 0, 250, 10, 120, True),
    _ComponentSeed("Hummus (Wochenende)", "other", ("Hummus",), 0, 150, 10, 50, True),
    _ComponentSeed("Kräuterquark (Wochenende)", "dairy", _QUARK, 0, 300, 10, 100, True),
    _ComponentSeed(
        "Croissant (Wochenende)",
        "carb",
        ("Croissant", "Buttercroissant"),
        0,
        120,
        60,
        60,
        True,
        variants=(_VariantSeed("Stück", 60.0),),
    ),
    _ComponentSeed("Marmelade (Wochenende)", "other", _JAM, 0, 60, 10, 20, True),
    _ComponentSeed(
        "Rührei (Wochenende)",
        "protein",
        ("Rührei", "Hühnerei"),
        0,
        360,
        60,
        120,
        True,
        variants=(_VariantSeed("Stück", 60.0),),
    ),
    _ComponentSeed(
        "Kiwi (Wochenende)", "fruit", ("Kiwi",), 0, 225, 75, 75, True, variants=(_VariantSeed("Stück", 75.0),)
    ),
)


def _is_compound_of(query: str, catalog_name: str) -> bool:
    """True, wenn der Katalogname den Suchbegriff nur als Teil eines längeren Worts enthält."""
    q = normalize_name(query).replace(" ", "")
    head = normalize_name(catalog_name.split(",")[0]).replace(" ", "")
    return bool(q) and q != head and q in head


class _Finder:
    """Findet Zutaten im Katalog: exakter Name, dann `match_ingredient` mit Mindestscore."""

    def __init__(self, session: Session) -> None:
        rows = session.execute(
            select(Ingredient.id, Ingredient.name).where(Ingredient.hidden.is_(False)).order_by(Ingredient.id)
        ).all()
        self.names = {row.id: row.name for row in rows}
        self.exact: dict[str, int] = {}
        for row in rows:
            self.exact.setdefault(row.name.strip().casefold(), row.id)
        self.catalog = [CatalogEntry(id=row.id, name=row.name) for row in rows]
        self.synonyms = {
            alias: ingredient_id
            for alias, ingredient_id in session.execute(
                select(IngredientSynonym.alias, IngredientSynonym.ingredient_id)
            )
            if ingredient_id in self.names
        }
        self._cache: dict[str, int | None] = {}

    def find_one(self, name: str) -> int | None:
        key = name.strip().casefold()
        if key in self._cache:
            return self._cache[key]
        found = self.exact.get(key)
        if found is None:
            for match in match_ingredient(name, self.catalog, self.synonyms):
                if match.score >= SEED_MIN_SCORE and match.ingredient_id in self.names:
                    if match.via == "fuzzy" and _is_compound_of(name, match.name):
                        continue  # "Apfelsaft" ist nicht "Apfel": lieber fehlend melden als raten
                    found = match.ingredient_id
                    break
        self._cache[key] = found
        return found

    def find(self, candidates: tuple[str, ...]) -> int | None:
        for name in candidates:
            found = self.find_one(name)
            if found is not None:
                return found
        return None


def seed_default_components(session: Session) -> dict[str, Any]:
    """Legt Standard-Komponenten für Christians Frühstück an, soweit die Zutat im Katalog gefunden wird.

    Zutaten werden per exaktem Namen, dann per `match_ingredient` (Score ≥ 85) gesucht, niemals geraten.
    Idempotent: Komponenten mit gleichem Namen werden übersprungen. Rückgabe: `created`, `skipped`,
    `missing` (Komponenten ohne Zutat im Katalog), `variants_created`, `missing_variants` und
    `matched` (Komponente → gefundene Zutat).
    """
    finder = _Finder(session)
    existing = {c.name.casefold() for c in session.scalars(select(Component))}
    created: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    missing_variants: list[str] = []
    matched: dict[str, str] = {}
    variants_created = 0

    for seed in DEFAULT_COMPONENTS:
        if seed.name.casefold() in existing:
            skipped.append(seed.name)
            continue
        ingredient_id = finder.find(seed.candidates)
        if ingredient_id is None:
            missing.append(seed.name)
            continue
        comp = _add_component(
            session,
            name=seed.name,
            kind=seed.kind,
            ingredient_id=ingredient_id,
            min_g=seed.min_g,
            max_g=seed.max_g,
            step_g=seed.step_g,
            typical_g=seed.typical_g,
            weekend_fixed=seed.weekend_fixed,
        )
        existing.add(seed.name.casefold())
        created.append(seed.name)
        matched[seed.name] = finder.names[ingredient_id]
        for vseed in seed.variants:
            variant_ingredient = ingredient_id
            if vseed.candidates is not None:
                variant_ingredient = finder.find(vseed.candidates)
                if variant_ingredient is None:
                    missing_variants.append(f"{seed.name}: {vseed.name}")
                    continue
            _add_variant(
                session,
                comp,
                name=vseed.name,
                ingredient_id=variant_ingredient,
                grams_per_unit=vseed.grams_per_unit,
            )
            variants_created += 1

    _commit(session, "Die Standard-Komponenten konnten nicht gespeichert werden.")
    return {
        "created": created,
        "skipped": skipped,
        "missing": missing,
        "variants_created": variants_created,
        "missing_variants": missing_variants,
        "matched": matched,
    }
