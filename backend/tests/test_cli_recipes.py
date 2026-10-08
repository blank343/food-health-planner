"""CLI: import-bls, import-recipe, seed-synonyms. Kein Netzwerk, keine echten BLS-Dateien."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import cli
from app.importers import bls as bls_module
from app.importers import recipe_web
from app.importers.recipe_web import RecipeImportError
from app.importers.types import ImportedRecipe, IngredientRecord
from app.models import Ingredient, IngredientSynonym, Recipe


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def run_cli(factory, *argv):
    return cli.main(list(argv), session_factory=factory)


def record(code, name, kcal, **kw) -> IngredientRecord:
    return IngredientRecord(
        name=name,
        source="bls",
        source_code=code,
        kcal_100=kcal,
        protein_100=1.0,
        fat_100=1.0,
        carb_100=1.0,
        **kw,
    )


@pytest.fixture
def fake_bls(monkeypatch):
    records = [
        record("G100100", "Speisezwiebel roh", 30.0),
        record("E100100", "Hühnerei roh", 140.0),
        record("C100100", "Weizen Mehl, Type 405", 340.0),
    ]

    def fake(path, progress=None):
        if progress:
            progress(0.0, "BLS: geöffnet")
            progress(1.0, "BLS: 3 Zutaten gelesen")
        return list(records), {"rows": 4, "imported": 3, "skipped": 1}

    monkeypatch.setattr(bls_module, "import_bls_with_stats", fake)


def test_import_bls_prints_progress_and_summary(factory, session, fake_bls, capsys):
    assert run_cli(factory, "import-bls", "irgendwo/bls.xlsx") == 0
    out = capsys.readouterr().out
    assert "BLS: geöffnet" in out and "Katalog:" in out
    assert "Zutaten: 3 neu, 0 aktualisiert, 0 unverändert, 1 übersprungen." in out
    # Seed-Synonyme: nur die Ziele, die im Katalog stehen
    assert "Synonyme:" in out and "angelegt" in out and "Nicht gefundene Zielnamen" in out
    assert session.scalar(select(func.count()).select_from(Ingredient)) == 3
    mapping = {s.alias: s.ingredient_id for s in session.scalars(select(IngredientSynonym))}
    assert {"zwiebel", "ei", "mehl"} <= set(mapping)


def test_import_bls_is_idempotent(factory, session, fake_bls, capsys):
    run_cli(factory, "import-bls", "x.xlsx")
    first = session.scalar(select(func.count()).select_from(IngredientSynonym))
    capsys.readouterr()
    assert run_cli(factory, "import-bls", "x.xlsx") == 0
    out = capsys.readouterr().out
    assert "Zutaten: 0 neu, 0 aktualisiert, 3 unverändert, 1 übersprungen." in out
    assert "0 angelegt" in out
    assert session.scalar(select(func.count()).select_from(IngredientSynonym)) == first
    assert session.scalar(select(func.count()).select_from(Ingredient)) == 3


def test_import_bls_missing_or_invalid_file(factory, tmp_path, capsys):
    assert run_cli(factory, "import-bls", str(tmp_path / "gibt-es-nicht.xlsx")) == 1
    assert "BLS-Datei nicht gefunden" in capsys.readouterr().err
    not_xlsx = tmp_path / "text.xlsx"
    not_xlsx.write_text("das ist keine Excel-Datei", encoding="utf-8")
    assert run_cli(factory, "import-bls", str(not_xlsx)) == 1
    err = capsys.readouterr().err
    assert err.startswith("Fehler:") and "BLS-Datei konnte nicht gelesen werden" in err


def test_seed_synonyms_command(factory, session, capsys):
    session.add(Ingredient(name="Hühnerei roh", source="bls", source_code="E1", kcal_100=140.0))
    session.commit()
    assert run_cli(factory, "seed-synonyms") == 0
    out = capsys.readouterr().out
    assert "angelegt" in out and "ohne Treffer im Katalog" in out
    assert "  - Olivenöl" in out or "weitere" in out  # fehlende Ziele werden (gekürzt) genannt
    assert out.count("  - ") <= cli.MAX_MISSING_SHOWN
    assert session.scalar(select(IngredientSynonym.alias).where(IngredientSynonym.alias == "ei")) == "ei"
    capsys.readouterr()
    assert run_cli(factory, "seed-synonyms") == 0
    assert "0 angelegt" in capsys.readouterr().out


def _imported(lines, **kw) -> ImportedRecipe:
    kw.setdefault("title", "Testkuchen")
    kw.setdefault("source_url", "https://example.org/kuchen")
    kw.setdefault("servings", 2.0)
    return ImportedRecipe(ingredient_lines=lines, **kw)


@pytest.fixture
def catalog_ready(factory, fake_bls):
    assert run_cli(factory, "import-bls", "x.xlsx") == 0


def test_import_recipe_prints_summary(factory, session, catalog_ready, monkeypatch, capsys):
    calls = []

    def fake(url):
        calls.append(url)
        return _imported(
            ["200 g Mehl", "2 Eier", "1 Dose Kichererbsen"], warnings=["Keine Zeitangabe gefunden"]
        )

    monkeypatch.setattr(recipe_web, "import_recipe_url", fake)
    capsys.readouterr()
    assert run_cli(factory, "import-recipe", "https://example.org/kuchen") == 0
    out = capsys.readouterr().out
    assert calls == ["https://example.org/kuchen"]
    assert "Rezept 'Testkuchen' gespeichert" in out
    assert "Zutatenzeilen: 3, davon zugeordnet: 2. Status: needs_review." in out
    assert "Hinweis: Keine Zeitangabe gefunden" in out and "Prüfliste" in out
    recipe = session.scalar(select(Recipe))
    assert recipe.title == "Testkuchen" and recipe.status == "needs_review"


def test_import_recipe_ready_has_no_review_hint(factory, session, catalog_ready, monkeypatch, capsys):
    monkeypatch.setattr(recipe_web, "import_recipe_url", lambda url: _imported(["200 g Mehl", "1 Zwiebel"]))
    capsys.readouterr()
    assert run_cli(factory, "import-recipe", "https://example.org/kuchen") == 0
    out = capsys.readouterr().out
    assert "Zutatenzeilen: 2, davon zugeordnet: 2. Status: ready." in out and "Prüfliste" not in out


def test_import_recipe_duplicate_and_errors(factory, session, catalog_ready, monkeypatch, capsys):
    monkeypatch.setattr(recipe_web, "import_recipe_url", lambda url: _imported(["200 g Mehl"]))
    assert run_cli(factory, "import-recipe", "https://example.org/kuchen") == 0
    capsys.readouterr()
    assert run_cli(factory, "import-recipe", "https://example.org/kuchen") == 1
    assert "schon vorhanden" in capsys.readouterr().err
    assert session.scalar(select(func.count()).select_from(Recipe)) == 1

    def boom(url):
        raise RecipeImportError("Seite nicht gefunden (HTTP 404)")

    monkeypatch.setattr(recipe_web, "import_recipe_url", boom)
    assert run_cli(factory, "import-recipe", "https://example.org/anders") == 1
    assert "Fehler: Seite nicht gefunden (HTTP 404)" in capsys.readouterr().err
    assert session.scalar(select(func.count()).select_from(Recipe)) == 1


def test_new_commands_listed_in_help(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    for name in ("import-bls", "import-recipe", "seed-synonyms", "create-person", "list-persons"):
        assert name in out
