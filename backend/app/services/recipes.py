"""Rezepte: Import in die DB, Zutatenzeilen zuordnen, Nährwerte, Prüfliste und Passung ins Tagesziel.

Nährwerte werden nie gespeichert, sondern bei Bedarf aus Zutatenzeilen berechnet
(docs/PHASE2.md, Abschnitte 3, 5 und 6).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.calc.ingredients import (
    CatalogEntry,
    mean_quantity,
    normalize_name,
    parse_ingredient_line,
    to_grams,
)
from app.calc.nutrition import fit_to_target, recipe_nutrition, satiety_score
from app.calc.piece_weights import piece_weight_for_alias, unit_weight_for_name
from app.calc.slots import single_meal_check
from app.calc.types import (
    IngredientMatch,
    LineNutrition,
    ParsedIngredient,
    PersonSettings,
    RecipeNutrition,
    SatietyScore,
    SlotFit,
    SlotTarget,
    Warning,
)
from app.importers.types import ImportedRecipe
from app.models import Ingredient, Person, Recipe, RecipeIngredient, RecipeRating, RecipeTag
from app.services import catalog, targets

SLOTS = ("breakfast", "lunch", "dinner", "snack")
AUTO_FUZZY_SCORE = 88.0  # ab hier ordnet der Import einen Fuzzy-Treffer selbst zu ...
AUTO_FUZZY_MARGIN = 8.0  # ... wenn er so viele Punkte vor dem Zweiten liegt
PLAUSIBILITY_PCT = 25.0  # Abweichung der berechneten von den angegebenen kcal, ab der ein Hinweis entsteht
LOW_COVERAGE = 0.9
_WARM_WORDS = ("suppe", "eintopf", "auflauf", "gulasch", "curry", "ragout", "chili")
_BREAKFAST_WORDS = ("frühstück", "porridge", "müsli", "muesli", "overnight oats", "granola")


class RecipeServiceError(Exception):
    """Fehler mit deutscher Meldung für Nutzer."""


class RecipeNotFound(RecipeServiceError):
    """Rezept oder Zutatenzeile existiert nicht."""


# ---------------------------------------------------------------------------
# Zuordnung einer Zeile zum Katalog
# ---------------------------------------------------------------------------


_WORD_RE = re.compile(r"[\wäöüß]+")


def _has_whole_words(query: str, catalog_name: str) -> bool:
    """True, wenn jedes Wort des normalisierten Suchbegriffs als ganzes Wort im Katalognamen steht.

    "apfel" steht nicht in "Apfelmus" und nicht in "Speiseapfel" (nur Teil eines längeren Wortes).
    """
    words = _WORD_RE.findall(catalog_name.lower())
    present = set(words) | {normalize_name(word) for word in words}
    wanted = _WORD_RE.findall(normalize_name(query))
    return bool(wanted) and all(word in present for word in wanted)


def pick_auto_match(matches: Sequence[IngredientMatch], query: str | None = None) -> IngredientMatch | None:
    """Treffer, den der Import ohne Rückfrage übernimmt (sonst None).

    Synonym und exakter Treffer immer. Fuzzy nur bei Score ≥ 88, ≥ 8 Punkten Vorsprung und (mit
    `query`) wenn der Suchbegriff als ganzes Wort im Katalognamen vorkommt: "Apfel" → "Apfelmus"
    bleibt offen und erscheint als Vorschlag in der Prüfliste.
    """
    if not matches:
        return None
    top = matches[0]
    if top.via in ("synonym", "exact"):
        return top
    lead = top.score - matches[1].score if len(matches) > 1 else 100.0
    if top.score >= AUTO_FUZZY_SCORE and lead >= AUTO_FUZZY_MARGIN:
        if query is None or _has_whole_words(query, top.name):
            return top
    return None


@dataclass
class CatalogContext:
    """Katalog und Synonyme einer Anfrage (einmal laden, für viele Zeilen nutzen)."""

    entries: list[CatalogEntry]
    synonyms: dict[str, int]

    @classmethod
    def load(cls, session: Session) -> "CatalogContext":
        return cls(catalog.catalog_entries(session), catalog.synonym_map(session))


def _grams(
    quantity: float | None, unit: str | None, ing: Ingredient | None, name: str | None = None
) -> float | None:
    """Gramm einer Zeile. Stückangaben ohne bekanntes Stückgewicht bleiben offen (None)."""
    piece_g = ing.piece_g if ing else None
    if piece_g is None and name and unit in (None, "Stück"):
        piece_g = piece_weight_for_alias(name)
    grams = to_grams(
        quantity,
        unit,
        density_g_per_ml=ing.density_g_per_ml if ing else None,
        piece_g=piece_g,
        unit_g=unit_weight_for_name(ing.name, unit) if ing else None,
    )
    return None if grams is None else round(grams, 2)


def _auto_assign(session: Session, line: RecipeIngredient, ctx: CatalogContext) -> None:
    if line.ingredient is not None:
        return
    parsed = parse_ingredient_line(line.raw_text)
    if not parsed.name:
        return
    matches = catalog.match_text(session, parsed.name, 5, entries=ctx.entries, synonyms=ctx.synonyms)
    chosen = pick_auto_match(matches, parsed.name)
    if chosen is not None:
        line.ingredient = session.get(Ingredient, chosen.ingredient_id)


def _to_taste(line: RecipeIngredient) -> bool:
    """Zeile ohne Mengenangabe, aber mit zugeordneter Zutat ("Salz", "Pfeffer"): nach Geschmack."""
    return line.quantity is None and line.ingredient is not None


def _status(recipe: Recipe) -> str:
    relevant = [line for line in recipe.ingredients if not line.optional and not _to_taste(line)]
    if not relevant:
        return "draft"
    if all(line.ingredient is not None and line.grams is not None for line in relevant):
        return "ready"
    return "needs_review"


def recompute_recipe(session: Session, recipe: Recipe, ctx: CatalogContext | None = None) -> Recipe:
    """Setzt Zuordnung, Gramm und Status neu.

    Zeilen mit Zutat behalten sie (auch manuelle Zuordnungen); Zeilen ohne Zutat werden erneut
    automatisch zugeordnet (z. B. nach neuen Synonymen). Gramm folgen aus Menge, Einheit und
    Dichte/Stückgewicht der Zutat. Kein Commit.
    """
    if ctx is None and any(line.ingredient is None for line in recipe.ingredients):
        ctx = CatalogContext.load(session)
    for line in recipe.ingredients:
        if ctx is not None:
            _auto_assign(session, line, ctx)
        line.grams = _grams(
            line.quantity, line.unit, line.ingredient, parse_ingredient_line(line.raw_text).name
        )
    recipe.status = _status(recipe)
    session.flush()
    return recipe


# ---------------------------------------------------------------------------
# Rezepte laden
# ---------------------------------------------------------------------------


def _eager(stmt):
    return stmt.options(
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient),
        selectinload(Recipe.tag),
        selectinload(Recipe.ratings),
    )


def get_recipe(session: Session, recipe_id: int) -> Recipe:
    recipe = session.scalar(_eager(select(Recipe)).where(Recipe.id == recipe_id))
    if recipe is None:
        raise RecipeNotFound("Rezept nicht gefunden.")
    return recipe


def load_recipes(
    session: Session, *, q: str | None = None, favorite: bool | None = None, status: str | None = None
) -> list[Recipe]:
    """Rezepte mit Zutaten, Tag und Bewertungen (eine Abfrage je Beziehung), nach ID."""
    stmt = _eager(select(Recipe))
    if q and q.strip():
        stmt = stmt.where(Recipe.title.icontains(q.strip(), autoescape=True))
    if favorite is not None:
        stmt = stmt.where(Recipe.favorite.is_(favorite))
    if status:
        stmt = stmt.where(Recipe.status == status)
    return list(session.scalars(stmt.order_by(Recipe.id)))


def find_by_url(session: Session, url: str) -> Recipe | None:
    return session.scalar(select(Recipe).where(Recipe.source_url == url).limit(1))


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    recipe: Recipe
    warnings: list[str] = field(default_factory=list)
    line_count: int = 0
    assigned_count: int = 0


def _default_tag(title: str) -> RecipeTag:
    """Nur eindeutige Hinweise aus dem Titel: warm (Suppe, Eintopf ...) und Frühstück (Porridge ...)."""
    low = title.lower()
    return RecipeTag(
        slot_types=["breakfast"] if any(w in low for w in _BREAKFAST_WORDS) else [],
        warm=any(w in low for w in _WARM_WORDS),
    )


def _site_of(url: str | None) -> str | None:
    host = (urlparse(url or "").hostname or "").lower()
    host = host.removeprefix("www.")
    return host[:120] or None


def _make_line(position: int, raw_text: str, parsed: ParsedIngredient) -> RecipeIngredient:
    return RecipeIngredient(
        position=position,
        raw_text=raw_text.strip()[:400],
        quantity=mean_quantity(parsed),
        unit=parsed.unit,
        optional=parsed.optional,
    )


def _plausibility_note(recipe: Recipe, site_kcal: float) -> str | None:
    nutrition = compute_recipe_nutrition(recipe)
    calc = nutrition.per_serving.kcal
    if site_kcal <= 0 or calc <= 0:
        return None
    deviation = abs(calc - site_kcal) / site_kcal * 100.0
    if deviation <= PLAUSIBILITY_PCT:
        return None
    note = (
        f"Hinweis: Die berechneten {calc:.0f} kcal je Portion weichen um {deviation:.0f} % von der Angabe "
        f"der Seite ({site_kcal:.0f} kcal) ab. Bitte Zutaten und Portionszahl prüfen."
    )
    if nutrition.coverage < 1.0:
        note += f" Nur {nutrition.coverage * 100:.0f} % der Zutaten haben Nährwerte."
    return note


def build_recipe_from_import(
    session: Session, imported: ImportedRecipe, *, commit: bool = True
) -> ImportResult:
    """Legt aus einem Web-Import ein Rezept an (Zutaten zerlegt, zugeordnet, Gramm und Status berechnet).

    Automatisch zugeordnet wird nur sicher (Synonym, exakt, oder Fuzzy mit Score ≥ 88 und ≥ 8 Punkten
    Vorsprung). Status `ready`, wenn alle nicht optionalen Zeilen Zutat und Gramm haben, sonst
    `needs_review`. Fehlt die Portionszahl, gilt 1 (mit Warnung). Weichen die berechneten kcal je
    Portion um mehr als 25 % von der Seitenangabe ab, steht ein Hinweis in `notes`.
    """
    warnings = list(imported.warnings)
    servings = imported.servings
    if servings is None or servings <= 0:
        servings = 1.0
        warnings.append("Keine Portionszahl bekannt: Es wird mit 1 Portion gerechnet. Bitte prüfen.")
    recipe = Recipe(
        title=(imported.title.strip() or "Rezept ohne Titel")[:300],
        source_url=imported.source_url[:600] if imported.source_url else None,
        source_site=(imported.source_site or _site_of(imported.source_url) or None),
        servings=servings,
        prep_min=imported.prep_min,
        cook_min=imported.cook_min,
        instructions=imported.instructions,
        image_url=imported.image_url if imported.image_url and len(imported.image_url) <= 600 else None,
        status="draft",
    )
    if recipe.source_site:
        recipe.source_site = recipe.source_site[:120]
    recipe.tag = _default_tag(recipe.title)
    lines = [text for text in imported.ingredient_lines if text and text.strip()]
    recipe.ingredients = [
        _make_line(position, text, parse_ingredient_line(text)) for position, text in enumerate(lines)
    ]
    session.add(recipe)
    recompute_recipe(session, recipe)

    site_kcal = imported.site_nutrients.get("kcal")
    if site_kcal:
        note = _plausibility_note(recipe, float(site_kcal))
        if note:
            recipe.notes = note
    if commit:
        session.commit()
    return ImportResult(
        recipe=recipe,
        warnings=warnings,
        line_count=len(recipe.ingredients),
        assigned_count=sum(1 for line in recipe.ingredients if line.ingredient is not None),
    )


@dataclass
class PreviewLine:
    raw_text: str
    parsed: ParsedIngredient
    grams: float | None
    matches: list[IngredientMatch]
    chosen: IngredientMatch | None


def preview_lines(session: Session, lines: Sequence[str], *, limit: int = 5) -> list[PreviewLine]:
    """Zerlegt Zutatenzeilen und schlägt Zutaten vor, ohne etwas zu speichern."""
    ctx = CatalogContext.load(session)
    result: list[PreviewLine] = []
    for text in lines:
        parsed = parse_ingredient_line(text)
        matches = (
            catalog.match_text(session, parsed.name, limit, entries=ctx.entries, synonyms=ctx.synonyms)
            if parsed.name
            else []
        )
        chosen = pick_auto_match(matches, parsed.name)
        ing = session.get(Ingredient, chosen.ingredient_id) if chosen else None
        grams = _grams(mean_quantity(parsed), parsed.unit, ing, parsed.name)
        result.append(PreviewLine(text, parsed, grams, matches, chosen))
    return result


# ---------------------------------------------------------------------------
# Manuell anlegen und ändern
# ---------------------------------------------------------------------------

_SCALAR_FIELDS = (
    "title", "servings", "prep_min", "cook_min", "instructions", "image_url", "source_url", "source_site",
    "favorite", "notes",
)  # fmt: skip
_TAG_FIELDS = (
    "slot_types", "cuisine", "main_ingredient", "batch_cookable", "transportable", "warm", "shelf_days",
    "season",
)  # fmt: skip


def _apply_tag(recipe: Recipe, data: Mapping[str, Any]) -> None:
    tag = recipe.tag
    if tag is None:
        tag = recipe.tag = RecipeTag(slot_types=[])
    for key in _TAG_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if key == "slot_types":
            slots = list(dict.fromkeys(value or []))
            bad = [s for s in slots if s not in SLOTS]
            if bad:
                raise RecipeServiceError(f"Unbekannter Slot: {', '.join(bad)}.")
            value = slots
        elif key in ("batch_cookable", "transportable", "warm"):
            value = bool(value)
        setattr(tag, key, value)


def _load_ingredient(session: Session, ingredient_id: int) -> Ingredient:
    ing = session.get(Ingredient, ingredient_id)
    if ing is None:
        raise RecipeServiceError(f"Zutat {ingredient_id} nicht gefunden.")
    return ing


def _apply_lines(session: Session, recipe: Recipe, items: Sequence[Mapping[str, Any]]) -> None:
    existing = {line.id: line for line in recipe.ingredients if line.id is not None}
    result: list[RecipeIngredient] = []
    for position, item in enumerate(items):
        raw = (item.get("raw_text") or "").strip() or None
        grams = item.get("grams")
        ing_id = item.get("ingredient_id")
        ing = _load_ingredient(session, ing_id) if ing_id is not None else None
        if raw is None and (ing is None or grams is None):
            raise RecipeServiceError("Jede Zutatenzeile braucht einen Text oder eine Zutat mit Gramm.")
        line_id = item.get("id")
        line: RecipeIngredient | None = None
        if line_id is not None:
            line = existing.pop(line_id, None)
            if line is None:
                raise RecipeServiceError(f"Die Zeile {line_id} gehört nicht zu diesem Rezept.")
        if raw is None:
            raw = f"{grams:g} g {ing.name}"[:400]  # type: ignore[union-attr]
        text_changed = line is None or line.raw_text != raw[:400]
        parsed = parse_ingredient_line(raw) if (text_changed or grams is not None) else None
        if line is None:
            line = RecipeIngredient(raw_text=raw[:400])
        if text_changed:
            line.raw_text = raw[:400]
            line.ingredient = None
        if grams is not None:
            line.quantity, line.unit = float(grams), "g"
        elif text_changed and parsed is not None:
            line.quantity, line.unit = mean_quantity(parsed), parsed.unit
        if item.get("optional") is not None:
            line.optional = bool(item["optional"])
        elif text_changed and parsed is not None:
            line.optional = parsed.optional
        if ing is not None:
            line.ingredient = ing
        line.position = position
        result.append(line)
    recipe.ingredients = result


def _apply_fields(recipe: Recipe, data: Mapping[str, Any]) -> None:
    for key in _SCALAR_FIELDS:
        if key in data:
            setattr(recipe, key, data[key])
    if "title" in data:
        recipe.title = (data["title"] or "").strip()
        if not recipe.title:
            raise RecipeServiceError("Der Titel darf nicht leer sein.")
    if "servings" in data and (data["servings"] is None or data["servings"] <= 0):
        raise RecipeServiceError("Die Portionszahl muss größer als 0 sein.")
    if data.get("source_url") and "source_site" not in data:
        recipe.source_site = _site_of(data["source_url"])


def create_manual_recipe(session: Session, data: Mapping[str, Any], *, commit: bool = True) -> Recipe:
    """Rezept von Hand anlegen. `data`: Felder des Rezepts, `tag` (dict) und `lines` (Liste von dicts).

    Eine Zeile braucht `raw_text` (Freitext, wird zerlegt) oder `ingredient_id` + `grams`; eine feste
    `ingredient_id` bleibt bei jeder Neuberechnung erhalten.
    """
    recipe = Recipe(title="", servings=1.0, status="draft")
    recipe.tag = RecipeTag(slot_types=[])
    _apply_fields(recipe, {**data, "title": data.get("title")})
    session.add(recipe)
    if data.get("tag"):
        _apply_tag(recipe, data["tag"])
    _apply_lines(session, recipe, data.get("lines") or [])
    recompute_recipe(session, recipe)
    if commit:
        session.commit()
    return recipe


def update_recipe(
    session: Session, recipe: Recipe, data: Mapping[str, Any], *, commit: bool = True
) -> Recipe:
    """Ändert ein Rezept (nur enthaltene Schlüssel). `lines` ersetzt alle Zeilen; Zeilen mit `id` bleiben
    erhalten (Zuordnung bleibt, solange ihr Text unverändert ist), Zeilen ohne `id` sind neu."""
    _apply_fields(recipe, data)
    if data.get("tag") is not None:
        _apply_tag(recipe, data["tag"])
    if data.get("lines") is not None:
        _apply_lines(session, recipe, data["lines"])
    recompute_recipe(session, recipe)
    if commit:
        session.commit()
    return recipe


# ---------------------------------------------------------------------------
# Nährwerte
# ---------------------------------------------------------------------------


def recipe_line_nutrition(recipe: Recipe) -> list[LineNutrition]:
    return [
        LineNutrition(
            label=line.raw_text,
            grams=line.grams,
            per100=catalog.ingredient_to_per100(line.ingredient) if line.ingredient is not None else None,
            optional=line.optional or _to_taste(line),
        )
        for line in recipe.ingredients
    ]


def compute_recipe_nutrition(recipe: Recipe) -> RecipeNutrition:
    return recipe_nutrition(recipe_line_nutrition(recipe), recipe.servings)


def recipe_satiety(recipe: Recipe, nutrition: RecipeNutrition) -> SatietyScore:
    return satiety_score(nutrition, warm=bool(recipe.tag.warm) if recipe.tag else False)


# ---------------------------------------------------------------------------
# Bewertungen
# ---------------------------------------------------------------------------


def set_rating(session: Session, recipe_id: int, person_id: int, rating: int) -> RecipeRating:
    if not 1 <= rating <= 5:
        raise RecipeServiceError("Die Bewertung muss zwischen 1 und 5 liegen.")
    if session.get(Recipe, recipe_id) is None:
        raise RecipeNotFound("Rezept nicht gefunden.")
    row = session.get(RecipeRating, (recipe_id, person_id))
    if row is None:
        row = RecipeRating(recipe_id=recipe_id, person_id=person_id, rating=rating)
        session.add(row)
    else:
        row.rating = rating
    session.commit()
    return row


def remove_rating(session: Session, recipe_id: int, person_id: int) -> None:
    if session.get(Recipe, recipe_id) is None:
        raise RecipeNotFound("Rezept nicht gefunden.")
    row = session.get(RecipeRating, (recipe_id, person_id))
    if row is not None:
        session.delete(row)
        session.commit()


def ratings_with_names(session: Session, recipe_id: int) -> list[tuple[RecipeRating, str]]:
    rows = session.execute(
        select(RecipeRating, Person.name)
        .join(Person, Person.id == RecipeRating.person_id)
        .where(RecipeRating.recipe_id == recipe_id)
        .order_by(Person.id)
    )
    return [(rating, name) for rating, name in rows]


# ---------------------------------------------------------------------------
# Prüfliste: nicht zugeordnete Zeilen
# ---------------------------------------------------------------------------


@dataclass
class UnassignedLine:
    line: RecipeIngredient
    recipe_id: int
    recipe_title: str
    name: str  # zerlegter Zutatenname
    similar_count: int  # unzugeordnete Zeilen (inkl. dieser) mit demselben normalisierten Namen
    suggestions: list[IngredientMatch]


def _unassigned_stmt():
    return (
        select(RecipeIngredient, Recipe.title)
        .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        .where(RecipeIngredient.ingredient_id.is_(None), RecipeIngredient.optional.is_(False))
        .order_by(RecipeIngredient.recipe_id, RecipeIngredient.position)
    )


def unassigned_lines(session: Session, limit: int = 50, offset: int = 0) -> tuple[list[UnassignedLine], int]:
    """Zeilen ohne Zutat (optionale ausgeschlossen) mit Rezepttitel und den besten Vorschlägen."""
    rows = list(session.execute(_unassigned_stmt()))
    counts: dict[str, int] = {}
    keys: list[str] = []
    for line, _ in rows:
        key = normalize_name(parse_ingredient_line(line.raw_text).name)
        keys.append(key)
        counts[key] = counts.get(key, 0) + 1
    ctx = CatalogContext.load(session) if rows[offset : offset + limit] else None
    items: list[UnassignedLine] = []
    for index in range(offset, min(offset + limit, len(rows))):
        line, title = rows[index]
        parsed = parse_ingredient_line(line.raw_text)
        suggestions = (
            catalog.match_text(session, parsed.name, 5, entries=ctx.entries, synonyms=ctx.synonyms)
            if ctx is not None and parsed.name
            else []
        )
        items.append(
            UnassignedLine(line, line.recipe_id, title, parsed.name, counts.get(keys[index], 1), suggestions)
        )
    return items, len(rows)


@dataclass
class AssignResult:
    line: RecipeIngredient
    assigned_line_ids: list[int]
    recipe_ids: list[int]
    synonym: str | None  # gespeicherter (normalisierter) Alias


def assign_line(
    session: Session, line_id: int, ingredient_id: int, *, save_synonym: bool = True
) -> AssignResult:
    """Ordnet eine Zeile einer Zutat zu.

    Mit `save_synonym` wird der normalisierte Zeilenname als Synonym gespeichert (ein vorhandenes
    Synonym auf eine andere Zutat wird umgehängt), und alle anderen unzugeordneten Zeilen mit
    demselben normalisierten Namen werden mitzugeordnet. Betroffene Rezepte werden neu berechnet.
    """
    line = session.get(RecipeIngredient, line_id)
    if line is None:
        raise RecipeNotFound("Zutatenzeile nicht gefunden.")
    ing = session.get(Ingredient, ingredient_id)
    if ing is None:
        raise RecipeNotFound("Zutat nicht gefunden.")
    parsed = parse_ingredient_line(line.raw_text)
    key = normalize_name(parsed.name) if parsed.name else ""
    line.ingredient = ing
    assigned = [line]
    alias: str | None = None
    if save_synonym and key:
        try:
            catalog.set_synonym(session, key, ing, overwrite=True)
            alias = key
        except catalog.CatalogError:
            alias = None
    if alias is not None:
        open_lines = session.scalars(select(RecipeIngredient).where(RecipeIngredient.ingredient_id.is_(None)))
        for other in open_lines:
            if other.id != line.id and normalize_name(parse_ingredient_line(other.raw_text).name) == key:
                other.ingredient = ing
                assigned.append(other)
    recipe_ids = sorted({row.recipe_id for row in assigned})
    ctx = CatalogContext.load(session)
    for recipe_id in recipe_ids:
        recompute_recipe(session, session.get(Recipe, recipe_id), ctx)  # type: ignore[arg-type]
    session.commit()
    return AssignResult(line, sorted(row.id for row in assigned), recipe_ids, alias)


# ---------------------------------------------------------------------------
# Passung ins Tagesziel
# ---------------------------------------------------------------------------


@dataclass
class SlotContext:
    """Ziel einer Mahlzeit einer Person an einem Tag (einmal berechnen, für viele Rezepte nutzen)."""

    slot: str
    day: date
    target: SlotTarget
    settings: PersonSettings
    warnings: list[Warning]


@dataclass
class FitResult:
    slot: str
    day: date
    slot_target: SlotTarget
    fit: SlotFit
    notes: list[str]  # Hinweise der Passung plus Warnungen der Einzelmahlzeit-Prüfung
    warnings: list[Warning]  # Warnungen der Einzelmahlzeit-Prüfung (z. B. über der Obergrenze)


def slot_context(session: Session, person: Person, on: date, slot: str) -> SlotContext:
    """Slot-Ziel aus `targets.compute_targets`. `TargetsUnavailable` wird durchgereicht."""
    result = targets.compute_targets(session, person, on)
    target = result.slots.get(slot)
    if target is None or result.shares.get(slot, 0.0) <= 0 or target.kcal <= 0:
        raise RecipeServiceError("Dieser Slot ist für den Tag nicht vorgesehen.")
    return SlotContext(slot, on, target, targets.load_settings(session, person.id), list(result.warnings))


def fit_nutrition(ctx: SlotContext, nutrition: RecipeNutrition) -> FitResult:
    """Passung einer Portion ins Slot-Ziel plus Prüfung der skalierten Mahlzeit (Obergrenze kcal)."""
    fit = fit_to_target(nutrition.per_serving, nutrition.serving_weight_g, ctx.target)
    scaled = SlotTarget(
        kcal=fit.scaled.kcal,
        protein_g=fit.scaled.protein_g,
        fat_g=fit.scaled.fat_g,
        carb_g=fit.scaled.carb_g,
    )
    meal_warnings = single_meal_check(scaled, ctx.settings)
    notes = list(fit.notes)
    if nutrition.coverage < LOW_COVERAGE:
        notes.append(
            f"Nur {nutrition.coverage * 100:.0f} % der Zutaten haben Nährwerte; die Passung ist ungenau."
        )
    notes.extend(w.message for w in meal_warnings)
    return FitResult(ctx.slot, ctx.day, ctx.target, fit, notes, meal_warnings)


def slot_fit_for_person(session: Session, person: Person, recipe: Recipe, on: date, slot: str) -> FitResult:
    """Wie gut passt eine Portion des Rezepts in den Slot der Person an diesem Tag?"""
    ctx = slot_context(session, person, on, slot)
    return fit_nutrition(ctx, compute_recipe_nutrition(recipe))
