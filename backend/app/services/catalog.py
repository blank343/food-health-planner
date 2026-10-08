"""Zutaten-Katalog: BLS-Import, Synonyme, Suche und Zuordnung von Zutatennamen (docs/PHASE2.md, Abschnitt 5).

Der Katalog (`ingredient`) enthält BLS-Einträge (`source="bls"`, Upsert nach `source_code`) und
manuelle Einträge. Manuell gepflegte Felder (Dichte, Stückgewicht, Haltbarkeit, Kaliumsalz,
Ausblenden) fasst der BLS-Import nie an.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calc.ingredients import CatalogEntry, match_ingredient, normalize_name
from app.calc.piece_weights import PIECE_WEIGHT_SEED
from app.calc.synonym_seed import SYNONYM_SEED
from app.calc.types import IngredientMatch, NutrientsPer100
from app.importers import bls as bls_importer
from app.importers.bls import bls_dish_flag, bls_raw_flag
from app.importers.types import Progress
from app.models import Ingredient, IngredientSynonym

COMMIT_EVERY = 500
RANK_RAW = 10.0  # Rohware bevorzugen
RANK_DISH = -20.0  # Gerichte/Zubereitungen abwerten
RANK_MANUAL = 15.0  # eigene Einträge (z. B. Markenprodukte) bevorzugen
MAX_ALIAS_LEN = 200

_BLS_FIELDS = (
    "name", "category", "kcal_100", "protein_100", "fat_100", "carb_100", "fiber_100", "salt_100",
    "is_fish",
)  # fmt: skip


class CatalogError(Exception):
    """Fehler beim Pflegen des Katalogs (deutsche, für Nutzer gedachte Meldung)."""


class CatalogNotFound(CatalogError):
    """Zutat oder Synonym existiert nicht."""


class CatalogConflict(CatalogError):
    """Das Synonym gehört schon zu einer anderen Zutat."""


# ---------------------------------------------------------------------------
# Umrechnung
# ---------------------------------------------------------------------------


def ingredient_to_per100(ing: Ingredient) -> NutrientsPer100:
    """Nährwerte je 100 g einer Zutat; fehlende Werte bleiben None (zählen nicht als 0)."""
    return NutrientsPer100(
        kcal=ing.kcal_100,
        protein_g=ing.protein_100,
        fat_g=ing.fat_100,
        carb_g=ing.carb_100,
        fiber_g=ing.fiber_100,
        salt_g=ing.salt_100,
        micros=dict(ing.micros or {}),
    )


# ---------------------------------------------------------------------------
# BLS-Import
# ---------------------------------------------------------------------------


def import_bls_file(session: Session, path: Path | str, progress: Progress | None = None) -> dict[str, int]:
    """Liest eine BLS-Datei (XLSX/ZIP) und legt Zutaten an oder aktualisiert sie (Upsert nach source_code).

    Aktualisiert werden Name, Kategorie, Nährwerte (inkl. Salz), Mikros und `is_fish`. Dichte,
    Stückgewicht, Haltbarkeit, Kaliumsalz-Schalter und `hidden` bleiben unangetastet. Ergebnis:
    `created`, `updated`, `unchanged`, `skipped` (vom Importer übersprungene Zeilen und Datensätze
    ohne BLS-Code). Commit in Blöcken zu 500 Änderungen und am Ende.
    """

    def stage(low: float, high: float):
        if progress is None:
            return None
        return lambda fraction, message: progress(low + (high - low) * fraction, message)

    records, read_stats = bls_importer.import_bls_with_stats(Path(path), stage(0.0, 0.5))
    existing: dict[str, Ingredient] = {
        code: ing
        for code, ing in session.execute(
            select(Ingredient.source_code, Ingredient).where(
                Ingredient.source == "bls", Ingredient.source_code.is_not(None)
            )
        )
    }
    stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": int(read_stats.get("skipped", 0))}
    pending = 0
    total = max(len(records), 1)
    for index, rec in enumerate(records, start=1):
        if rec.source != "bls" or not rec.source_code:
            stats["skipped"] += 1
            continue
        values = {
            "name": rec.name[:200],
            "category": rec.category,
            "kcal_100": rec.kcal_100,
            "protein_100": rec.protein_100,
            "fat_100": rec.fat_100,
            "carb_100": rec.carb_100,
            "fiber_100": rec.fiber_100,
            "salt_100": rec.salt_100,
            "is_fish": rec.is_fish,
        }
        ing = existing.get(rec.source_code)
        if ing is None:
            ing = Ingredient(
                source="bls",
                source_code=rec.source_code,
                micros=dict(rec.micros),
                piece_g=PIECE_WEIGHT_SEED.get(values["name"]),
                **values,
            )
            session.add(ing)
            existing[rec.source_code] = ing
            stats["created"] += 1
            pending += 1
        else:
            changed = False
            for field in _BLS_FIELDS:
                if getattr(ing, field) != values[field]:
                    setattr(ing, field, values[field])
                    changed = True
            if (ing.micros or {}) != rec.micros:
                ing.micros = dict(rec.micros)
                changed = True
            if ing.piece_g is None and values["name"] in PIECE_WEIGHT_SEED:
                ing.piece_g = PIECE_WEIGHT_SEED[values["name"]]
                changed = True
            if changed:
                stats["updated"] += 1
                pending += 1
            else:
                stats["unchanged"] += 1
        if pending >= COMMIT_EVERY:
            session.commit()
            pending = 0
            if progress is not None:
                progress(0.5 + 0.5 * index / total, f"Katalog: {index} von {total} Zutaten gespeichert")
    session.commit()
    if progress is not None:
        progress(
            1.0,
            f"Katalog: {stats['created']} neu, {stats['updated']} aktualisiert, "
            f"{stats['unchanged']} unverändert, {stats['skipped']} übersprungen",
        )
    return stats


# ---------------------------------------------------------------------------
# Synonyme
# ---------------------------------------------------------------------------


def ensure_seed_synonyms(session: Session) -> dict[str, object]:
    """Legt die Start-Synonyme (`SYNONYM_SEED`) an, sofern ihr BLS-Zielname im Katalog steht.

    Idempotent; vorhandene Aliase werden nie überschrieben. Ergebnis: `created`, `skipped`
    (Alias existiert schon), `not_found` (Zahl der Aliase ohne Ziel) und `missing` (sortierte Namen
    der nicht gefundenen Ziele).
    """
    by_name: dict[str, int] = {}
    for ing_id, name in session.execute(
        select(Ingredient.id, Ingredient.name).where(Ingredient.source == "bls").order_by(Ingredient.id)
    ):
        by_name.setdefault(name, ing_id)
    known = set(session.scalars(select(IngredientSynonym.alias)))
    created = skipped = not_found = 0
    missing: set[str] = set()
    for alias, target in SYNONYM_SEED.items():
        if alias in known:
            skipped += 1
            continue
        target_id = by_name.get(target)
        if target_id is None:
            not_found += 1
            missing.add(target)
            continue
        session.add(IngredientSynonym(alias=alias, ingredient_id=target_id))
        known.add(alias)
        created += 1
    session.commit()
    return {"created": created, "skipped": skipped, "not_found": not_found, "missing": sorted(missing)}


def _clean_alias(alias: str) -> str:
    normalized = normalize_name(alias or "")
    if not normalized:
        raise CatalogError("Das Synonym darf nicht leer sein.")
    if len(normalized) > MAX_ALIAS_LEN:
        raise CatalogError(f"Das Synonym ist zu lang (höchstens {MAX_ALIAS_LEN} Zeichen).")
    return normalized


def get_ingredient(session: Session, ingredient_id: int) -> Ingredient:
    ing = session.get(Ingredient, ingredient_id)
    if ing is None:
        raise CatalogNotFound("Zutat nicht gefunden.")
    return ing


def set_synonym(session: Session, alias: str, ingredient: Ingredient, *, overwrite: bool = False) -> bool:
    """Legt einen (normalisierten) Alias an. True, wenn dabei etwas angelegt oder umgehängt wurde.

    Zeigt der Alias schon auf eine andere Zutat: mit `overwrite=True` wird er umgehängt, sonst
    `CatalogError`. Kein Commit.
    """
    key = _clean_alias(alias)
    row = session.scalar(select(IngredientSynonym).where(IngredientSynonym.alias == key))
    if row is None:
        session.add(IngredientSynonym(alias=key, ingredient_id=ingredient.id))
        session.flush()
        return True
    if row.ingredient_id == ingredient.id:
        return False
    if not overwrite:
        other = session.get(Ingredient, row.ingredient_id)
        raise CatalogConflict(
            f"Das Synonym „{key}“ gehört bereits zu „{other.name if other else row.ingredient_id}“."
        )
    row.ingredient_id = ingredient.id
    session.flush()
    return True


def add_synonym(session: Session, ingredient_id: int, alias: str) -> IngredientSynonym:
    """Synonym für eine Zutat anlegen (Alias wird normalisiert). Gleiches Ziel: idempotent."""
    ing = get_ingredient(session, ingredient_id)
    set_synonym(session, alias, ing)
    session.commit()
    key = _clean_alias(alias)
    return session.scalars(select(IngredientSynonym).where(IngredientSynonym.alias == key)).one()


def remove_synonym(session: Session, ingredient_id: int, alias: str) -> None:
    """Synonym entfernen. `CatalogNotFound`, wenn die Zutat oder das Synonym fehlt."""
    get_ingredient(session, ingredient_id)
    rows = session.scalars(select(IngredientSynonym).where(IngredientSynonym.ingredient_id == ingredient_id))
    wanted = {alias.strip().lower(), normalize_name(alias)}
    for row in rows:
        if row.alias in wanted:
            session.delete(row)
            session.commit()
            return
    raise CatalogNotFound("Synonym nicht gefunden.")


def synonyms_of(session: Session, ingredient_id: int) -> list[str]:
    return list(
        session.scalars(
            select(IngredientSynonym.alias)
            .where(IngredientSynonym.ingredient_id == ingredient_id)
            .order_by(IngredientSynonym.alias)
        )
    )


# ---------------------------------------------------------------------------
# Zuordnung und Suche
# ---------------------------------------------------------------------------


def _rank_hint(source: str, code: str | None, name: str) -> float:
    if source == "manual":
        return RANK_MANUAL
    if source == "bls" and code:
        if bls_dish_flag(code):
            return RANK_DISH
        if bls_raw_flag(code, name):
            return RANK_RAW
    return 0.0


def catalog_entries(session: Session, *, source: str | None = None) -> list[CatalogEntry]:
    """Alle sichtbaren (nicht ausgeblendeten) Zutaten als Katalog für `match_ingredient`.

    `rank_hint`: Rohware +10, Gerichte −20, manuelle Zutaten +15. Wird nicht gecacht; für mehrere
    Zeilen einer Anfrage einmal laden und per `entries=` weiterreichen.
    """
    stmt = select(Ingredient.id, Ingredient.name, Ingredient.source, Ingredient.source_code).where(
        Ingredient.hidden.is_(False)
    )
    if source:
        stmt = stmt.where(Ingredient.source == source)
    return [
        CatalogEntry(ing_id, name, _rank_hint(src, code, name))
        for ing_id, name, src, code in session.execute(stmt.order_by(Ingredient.id))
    ]


def synonym_map(session: Session) -> dict[str, int]:
    """Normalisierter Alias → Zutaten-ID (nur Synonyme sichtbarer Zutaten)."""
    rows = session.execute(
        select(IngredientSynonym.alias, IngredientSynonym.ingredient_id)
        .join(Ingredient, Ingredient.id == IngredientSynonym.ingredient_id)
        .where(Ingredient.hidden.is_(False))
    )
    return {alias: ing_id for alias, ing_id in rows}


def match_text(
    session: Session,
    text: str,
    limit: int = 5,
    *,
    entries: Sequence[CatalogEntry] | None = None,
    synonyms: Mapping[str, int] | None = None,
) -> list[IngredientMatch]:
    """Beste Katalogtreffer für einen Zutatennamen (Synonym, exakt, Fuzzy)."""
    if entries is None:
        entries = catalog_entries(session)
    if synonyms is None:
        synonyms = synonym_map(session)
    return match_ingredient(text, entries, synonyms, limit=limit)


def _substring_rank(query: str, name: str) -> float:
    q, n = query.lower(), name.lower()
    if n == q:
        rank = 100.0
    elif n.startswith(q):
        rank = 80.0
    elif f" {q}" in n or f"/{q}" in n:
        rank = 65.0
    else:
        rank = 50.0
    return rank - 0.02 * len(name)


def search_ingredients(
    session: Session,
    q: str | None,
    limit: int = 25,
    offset: int = 0,
    source: str | None = None,
    *,
    include_hidden: bool = False,
) -> tuple[list[Ingredient], int]:
    """Suche für die Oberfläche: Teilstring im Namen plus Treffer aus `match_ingredient`.

    Ohne Suchtext alphabetisch. Ergebnis: (Seite, Gesamtzahl). Sortierung nach Relevanz.
    """
    text = (q or "").strip()
    conditions = []
    if source:
        conditions.append(Ingredient.source == source)
    if not include_hidden:
        conditions.append(Ingredient.hidden.is_(False))
    if not text:
        total = session.scalar(select(func.count()).select_from(Ingredient).where(*conditions)) or 0
        page = select(Ingredient).where(*conditions).order_by(Ingredient.name, Ingredient.id)
        rows = session.scalars(page.limit(limit).offset(offset))
        return list(rows), total

    ranks: dict[int, tuple[float, int]] = {}  # id -> (Rang, Namenslänge)
    for ing_id, name in session.execute(
        select(Ingredient.id, Ingredient.name)
        .where(*conditions, Ingredient.name.icontains(text, autoescape=True))
        .limit(5000)
    ):
        ranks[ing_id] = (_substring_rank(text, name), len(name))

    entries = catalog_entries(session, source=source)
    ids = {e.id for e in entries}
    synonyms = {a: i for a, i in synonym_map(session).items() if i in ids}
    names = {e.id: e.name for e in entries}
    for match in match_ingredient(text, entries, synonyms, limit=50):
        length = len(names.get(match.ingredient_id, match.name))
        current = ranks.get(match.ingredient_id)
        if current is None or match.score > current[0]:
            ranks[match.ingredient_id] = (match.score, length)

    ordered = sorted(ranks.items(), key=lambda item: (-item[1][0], item[1][1], item[0]))
    page_ids = [ing_id for ing_id, _ in ordered[offset : offset + limit]]
    if not page_ids:
        return [], len(ordered)
    by_id = {ing.id: ing for ing in session.scalars(select(Ingredient).where(Ingredient.id.in_(page_ids)))}
    return [by_id[i] for i in page_ids if i in by_id], len(ordered)
