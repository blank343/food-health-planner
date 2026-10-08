"""Katalog-Dienst: BLS-Import, Seed-Synonyme, Zuordnung, Suche. Nur erfundene Zutaten (keine BLS-Daten)."""

from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.calc.synonym_seed import SYNONYM_SEED
from app.importers import bls as bls_module
from app.importers.types import IngredientRecord
from app.models import Ingredient, IngredientSynonym
from app.services import catalog


def rec(code, name, kcal=100.0, **kw) -> IngredientRecord:
    values = {"protein_100": 5.0, "fat_100": 2.0, "carb_100": 10.0, "fiber_100": 1.0, "salt_100": 0.1}
    values.update(kw)
    return IngredientRecord(
        name=name, source="bls", source_code=code, category="Testgruppe", kcal_100=kcal, **values
    )


def records() -> list[IngredientRecord]:
    return [
        rec("G100100", "Speisezwiebel roh", 30.0, micros={"potassium_mg": 170.0}),
        rec("E100100", "Hühnerei roh", 140.0, protein_100=12.5, fat_100=9.5, carb_100=0.5),
        rec("Q100000", "Olivenöl", 900.0, fat_100=100.0, protein_100=0.0, carb_100=0.0),
        rec("X100143", "Zwiebelsuppe gekocht", 40.0),
        rec("T100100", "Lachs roh", 200.0, is_fish=True),
    ]


@pytest.fixture
def patched_bls(monkeypatch):
    """BLS-Importer ersetzen: liefert die Datensätze der Liste `box`, ohne Datei."""
    box = {"records": records(), "skipped": 2}

    def fake(path, progress=None):
        if progress:
            progress(0.5, "gelesen")
            progress(1.0, "fertig")
        return list(box["records"]), {"rows": 7, "imported": len(box["records"]), "skipped": box["skipped"]}

    monkeypatch.setattr(bls_module, "import_bls_with_stats", fake)
    return box


def test_import_creates_then_is_idempotent(session, patched_bls):
    stats = catalog.import_bls_file(session, "ignored.xlsx")
    assert stats == {"created": 5, "updated": 0, "unchanged": 0, "skipped": 2}
    egg = session.scalar(select(Ingredient).where(Ingredient.source_code == "E100100"))
    assert (egg.name, egg.source, egg.kcal_100, egg.protein_100, egg.salt_100) == (
        "Hühnerei roh",
        "bls",
        140.0,
        12.5,
        0.1,
    )
    assert egg.category == "Testgruppe" and egg.is_fish is False and egg.hidden is False
    onion = session.scalar(select(Ingredient).where(Ingredient.source_code == "G100100"))
    assert onion.micros == {"potassium_mg": 170.0}
    assert session.scalar(select(Ingredient).where(Ingredient.source_code == "T100100")).is_fish is True

    again = catalog.import_bls_file(session, "ignored.xlsx")
    assert again == {"created": 0, "updated": 0, "unchanged": 5, "skipped": 2}
    assert session.scalar(select(func.count()).select_from(Ingredient)) == 5


def test_import_updates_changed_values_but_keeps_manual_fields(session, patched_bls):
    catalog.import_bls_file(session, "x")
    onion = session.scalar(select(Ingredient).where(Ingredient.source_code == "G100100"))
    onion.piece_g = 80.0
    onion.density_g_per_ml = 0.9
    onion.hidden = True
    onion.is_potassium_salt = True
    onion.shelf_days = 14
    session.commit()

    patched_bls["records"] = [
        rec("G100100", "Speisezwiebel roh (neu)", 35.0, micros={"potassium_mg": 180.0, "zinc_mg": 0.2}),
        *records()[1:],
    ]
    stats = catalog.import_bls_file(session, "x")
    assert stats["created"] == 0 and stats["updated"] == 1 and stats["unchanged"] == 4
    session.refresh(onion)
    assert onion.name == "Speisezwiebel roh (neu)" and onion.kcal_100 == 35.0
    assert onion.micros == {"potassium_mg": 180.0, "zinc_mg": 0.2}
    kept = (onion.piece_g, onion.density_g_per_ml, onion.hidden, onion.is_potassium_salt, onion.shelf_days)
    assert kept == (80.0, 0.9, True, True, 14)


def test_import_never_touches_manual_ingredients(session, patched_bls):
    manual = Ingredient(name="Hühnerei roh", source="manual", source_code="E100100", kcal_100=1.0)
    session.add(manual)
    session.commit()
    stats = catalog.import_bls_file(session, "x")
    assert stats["created"] == 5  # gleicher Code, andere Quelle: eigener Eintrag
    session.refresh(manual)
    assert manual.kcal_100 == 1.0 and manual.source == "manual"


def test_import_skips_records_without_code_and_commits_in_blocks(session, patched_bls, monkeypatch):
    monkeypatch.setattr(catalog, "COMMIT_EVERY", 2)
    patched_bls["records"] = [
        *records(),
        rec(None, "Ohne Code"),
        rec("Z1", "Doppelt"),
        rec("Z1", "Doppelt neu", 5.0),
    ]
    stats = catalog.import_bls_file(session, "x")
    assert stats["created"] == 6 and stats["updated"] == 1 and stats["skipped"] == 3
    assert session.scalar(select(Ingredient.name).where(Ingredient.source_code == "Z1")) == "Doppelt neu"


def test_import_reports_progress(session, patched_bls):
    seen: list[tuple[float, str]] = []
    catalog.import_bls_file(session, "x", lambda fraction, message: seen.append((fraction, message)))
    fractions = [f for f, _ in seen]
    assert fractions == sorted(fractions) and fractions[0] >= 0.0 and fractions[-1] == 1.0
    assert "5 neu" in seen[-1][1]


def test_import_real_xlsx_file(session, tmp_path: Path):
    """Der Weg über die echte Importer-Funktion mit einer winzigen erfundenen Datei."""
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "BLS Code", "Lebensmittelbezeichnung", "Food name",
            "ENERCC Energie (Kilokalorien) [kcal/100g]", "PROT625 Protein [g/100g]", "FAT Fett [g/100g]",
            "CHO Kohlenhydrate [g/100g]", "NA Natrium [mg/100g]",
        ]
    )  # fmt: skip
    ws.append(["G999100", "Testgemüse roh", "Test veg", 25, 2, 0.5, 3, 100])
    ws.append(["G999200", "Leere Zeile ohne Werte", "Empty", None, None, None, None, None])
    path = tmp_path / "bls_test.xlsx"
    wb.save(path)
    stats = catalog.import_bls_file(session, path)
    assert stats["created"] == 1 and stats["skipped"] == 1
    veg = session.scalar(select(Ingredient).where(Ingredient.source_code == "G999100"))
    assert veg.kcal_100 == 25 and veg.salt_100 == pytest.approx(0.25)  # Natrium 100 mg -> 0,25 g Salz
    assert veg.micros["sodium_mg"] == 100


# ---------------------------------------------------------------------------
# Synonyme
# ---------------------------------------------------------------------------


def _seed_targets(session, names: list[str]) -> dict[str, int]:
    ids = {}
    for index, name in enumerate(names):
        ing = Ingredient(name=name, source="bls", source_code=f"S{index}", kcal_100=100.0)
        session.add(ing)
        session.flush()
        ids[name] = ing.id
    session.commit()
    return ids


def test_seed_synonyms_creates_and_reports_missing(session):
    ids = _seed_targets(session, ["Hühnerei roh", "Speisezwiebel roh"])
    result = catalog.ensure_seed_synonyms(session)
    expected_eggs = [a for a, t in SYNONYM_SEED.items() if t == "Hühnerei roh"]
    expected_onions = [a for a, t in SYNONYM_SEED.items() if t == "Speisezwiebel roh"]
    assert result["created"] == len(expected_eggs) + len(expected_onions)
    assert result["skipped"] == 0
    assert result["not_found"] == len(SYNONYM_SEED) - result["created"]
    assert "Olivenöl" in result["missing"] and "Hühnerei roh" not in result["missing"]
    assert result["missing"] == sorted(set(result["missing"]))
    mapping = catalog.synonym_map(session)
    assert mapping["ei"] == ids["Hühnerei roh"] and mapping["zwiebel"] == ids["Speisezwiebel roh"]


def test_seed_synonyms_is_idempotent_and_never_overwrites(session):
    ids = _seed_targets(session, ["Hühnerei roh", "Speisezwiebel roh", "Olivenöl"])
    session.add(IngredientSynonym(alias="ei", ingredient_id=ids["Olivenöl"]))  # eigene Zuordnung
    session.commit()
    first = catalog.ensure_seed_synonyms(session)
    assert first["skipped"] == 1
    second = catalog.ensure_seed_synonyms(session)
    assert second["created"] == 0 and second["skipped"] == first["created"] + 1
    assert catalog.synonym_map(session)["ei"] == ids["Olivenöl"]
    count = session.scalar(
        select(func.count()).select_from(IngredientSynonym).where(IngredientSynonym.alias == "ei")
    )
    assert count == 1


def test_seed_synonyms_ignores_manual_ingredients_with_same_name(session):
    session.add(Ingredient(name="Hühnerei roh", source="manual", kcal_100=1.0))
    session.commit()
    assert catalog.ensure_seed_synonyms(session)["created"] == 0


def test_add_synonym_normalizes_and_detects_conflicts(session):
    ids = _seed_targets(session, ["Speisezwiebel roh", "Olivenöl"])
    row = catalog.add_synonym(session, ids["Speisezwiebel roh"], "  Frische ZWIEBELN ")
    assert row.alias == "zwiebel" and row.ingredient_id == ids["Speisezwiebel roh"]
    # gleiches Ziel: idempotent
    assert catalog.add_synonym(session, ids["Speisezwiebel roh"], "Zwiebel").id == row.id
    with pytest.raises(catalog.CatalogError, match="gehört bereits zu „Speisezwiebel roh“"):
        catalog.add_synonym(session, ids["Olivenöl"], "zwiebel")
    with pytest.raises(catalog.CatalogError, match="leer"):
        catalog.add_synonym(session, ids["Olivenöl"], "   ")
    with pytest.raises(catalog.CatalogNotFound):
        catalog.add_synonym(session, 9999, "irgendwas")


def test_remove_synonym(session):
    ids = _seed_targets(session, ["Speisezwiebel roh"])
    catalog.add_synonym(session, ids["Speisezwiebel roh"], "Gemüsezwiebel")
    assert catalog.synonyms_of(session, ids["Speisezwiebel roh"]) == ["gemüsezwiebel"]
    catalog.remove_synonym(session, ids["Speisezwiebel roh"], "Gemüsezwiebel")
    assert catalog.synonyms_of(session, ids["Speisezwiebel roh"]) == []
    with pytest.raises(catalog.CatalogNotFound):
        catalog.remove_synonym(session, ids["Speisezwiebel roh"], "Gemüsezwiebel")
    with pytest.raises(catalog.CatalogNotFound):
        catalog.remove_synonym(session, 9999, "x")


# ---------------------------------------------------------------------------
# Katalog, Zuordnung, Suche
# ---------------------------------------------------------------------------


def test_catalog_entries_rank_hints_and_hidden(session, patched_bls):
    catalog.import_bls_file(session, "x")
    session.add(Ingredient(name="Eigener Skyr", source="manual", kcal_100=60.0))
    session.add(
        Ingredient(name="Versteckt roh", source="bls", source_code="G555500", kcal_100=1.0, hidden=True)
    )
    session.commit()
    entries = {e.name: e for e in catalog.catalog_entries(session)}
    assert "Versteckt roh" not in entries
    assert entries["Speisezwiebel roh"].rank_hint == 10.0  # Rohware
    assert entries["Zwiebelsuppe gekocht"].rank_hint == -20.0  # Gericht
    assert entries["Eigener Skyr"].rank_hint == 15.0  # manuell
    assert entries["Olivenöl"].rank_hint == 10.0  # Grundprodukt (Code endet auf 00)
    only_manual = catalog.catalog_entries(session, source="manual")
    assert [e.name for e in only_manual] == ["Eigener Skyr"]


def test_synonym_map_skips_hidden_targets(session):
    ids = _seed_targets(session, ["Speisezwiebel roh", "Olivenöl"])
    catalog.add_synonym(session, ids["Speisezwiebel roh"], "zwiebel")
    catalog.add_synonym(session, ids["Olivenöl"], "öl")
    session.get(Ingredient, ids["Olivenöl"]).hidden = True
    session.commit()
    assert catalog.synonym_map(session) == {"zwiebel": ids["Speisezwiebel roh"]}


def test_match_text_prefers_synonym_then_raw_and_manual(session, patched_bls):
    catalog.import_bls_file(session, "x")
    onion = session.scalar(select(Ingredient).where(Ingredient.source_code == "G100100"))
    catalog.add_synonym(session, onion.id, "Zwiebel")
    top = catalog.match_text(session, "2 Zwiebeln"[2:].strip())[0]  # "Zwiebeln" -> normalisiert "zwiebel"
    assert (top.ingredient_id, top.via, top.score) == (onion.id, "synonym", 100.0)

    # ohne Synonym: Rohware vor Gericht, eigener Eintrag vor Rohware
    session.query(IngredientSynonym).delete()
    session.commit()
    first = catalog.match_text(session, "Zwiebel")
    assert first[0].name == "Speisezwiebel roh"
    session.add(Ingredient(name="Zwiebel", source="manual", kcal_100=33.0))
    session.commit()
    assert catalog.match_text(session, "Zwiebel")[0].name == "Zwiebel"


def test_match_text_accepts_preloaded_data(session, patched_bls):
    catalog.import_bls_file(session, "x")
    entries = catalog.catalog_entries(session)
    session.query(Ingredient).delete()  # nach dem Laden dürfen keine Abfragen mehr nötig sein
    session.commit()
    result = catalog.match_text(session, "Olivenöl", entries=entries, synonyms={})
    assert result and result[0].name == "Olivenöl" and result[0].via == "exact"


def test_search_ingredients_empty_query_sorted_and_paged(session, patched_bls):
    catalog.import_bls_file(session, "x")
    rows, total = catalog.search_ingredients(session, None, limit=2, offset=0)
    assert total == 5 and [r.name for r in rows] == ["Hühnerei roh", "Lachs roh"]
    rows, _ = catalog.search_ingredients(session, "", limit=2, offset=4)
    assert [r.name for r in rows] == ["Zwiebelsuppe gekocht"]


def test_search_ingredients_substring_relevance_source_and_hidden(session, patched_bls):
    catalog.import_bls_file(session, "x")
    session.add(Ingredient(name="Zwiebel", source="manual", kcal_100=33.0))
    session.add(Ingredient(name="Zwiebelschmalz", source="manual", kcal_100=700.0, hidden=True))
    session.commit()
    rows, total = catalog.search_ingredients(session, "zwiebel", limit=10, offset=0)
    names = [r.name for r in rows]
    assert names[0] == "Zwiebel" and set(names) == {"Zwiebel", "Speisezwiebel roh", "Zwiebelsuppe gekocht"}
    assert total == 3
    rows, total = catalog.search_ingredients(session, "zwiebel", 10, 0, source="manual")
    assert [r.name for r in rows] == ["Zwiebel"] and total == 1
    rows, _ = catalog.search_ingredients(session, "zwiebel", 10, 0, include_hidden=True)
    assert "Zwiebelschmalz" in [r.name for r in rows]
    rows, total = catalog.search_ingredients(session, "zwiebel", limit=1, offset=1)
    assert len(rows) == 1 and total == 3


def test_search_ingredients_escapes_wildcards_and_misses(session, patched_bls):
    catalog.import_bls_file(session, "x")
    assert catalog.search_ingredients(session, "%", 10, 0) == ([], 0)
    assert catalog.search_ingredients(session, "qqqqqq", 10, 0) == ([], 0)


def test_search_ingredients_finds_by_synonym(session, patched_bls):
    catalog.import_bls_file(session, "x")
    egg = session.scalar(select(Ingredient).where(Ingredient.source_code == "E100100"))
    catalog.add_synonym(session, egg.id, "Frühstücksei")
    rows, _ = catalog.search_ingredients(session, "Frühstücksei", 10, 0)
    assert [r.id for r in rows][:1] == [egg.id]


def test_ingredient_to_per100(session):
    ing = Ingredient(
        name="Test", source="manual", kcal_100=50.0, protein_100=None, fat_100=1.0, carb_100=2.0,
        fiber_100=3.0, salt_100=None, micros={"zinc_mg": 1.5},
    )  # fmt: skip
    per = catalog.ingredient_to_per100(ing)
    assert (per.kcal, per.protein_g, per.fat_g, per.carb_g, per.fiber_g, per.salt_g) == (
        50.0, None, 1.0, 2.0, 3.0, None,
    )  # fmt: skip
    assert per.micros == {"zinc_mg": 1.5} and per.micros is not ing.micros
