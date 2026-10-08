"""Rezept-Dienst: Import, Zuordnung, Nährwerte, Prüfliste, Passung. Nur erfundene Daten, kein Netzwerk."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.calc.nutrition import fit_to_target
from app.calc.types import IngredientMatch
from app.importers.types import ImportedRecipe
from app.models import (
    HealthDaily,
    Ingredient,
    IngredientSynonym,
    Person,
    PersonSettingsRow,
    Recipe,
    RecipeIngredient,
)
from app.services import catalog
from app.services import recipes as svc
from app.services.targets import TargetsUnavailable, compute_targets

MONDAY = date(2026, 10, 5)

# Name, Code, kcal, Protein, Fett, KH, Ballaststoffe, Salz, Zusatz
CATALOG = [
    ("Speisezwiebel roh", "G100100", 30.0, 1.2, 0.2, 5.0, 1.5, None, {"piece_g": 80.0}),
    ("Hühnerei roh", "E100100", 140.0, 12.5, 9.5, 0.5, 0.0, None, {"piece_g": 60.0}),
    ("Weizen Mehl, Type 405", "C100100", 340.0, 10.0, 1.0, 70.0, 3.0, None, {}),
    ("Olivenöl", "Q100000", 900.0, 0.0, 100.0, 0.0, 0.0, None, {"density_g_per_ml": 0.9}),
    ("Speisesalz/Siedesalz/Tafelsalz", "R100000", 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, {}),
    ("Vollmilch frisch, 3,5 % Fett, pasteurisiert", "M100100", 65.0, 3.3, 3.5, 4.8, 0.0, 0.1, {}),
]


@pytest.fixture
def ings(session) -> dict[str, Ingredient]:
    out = {}
    for name, code, kcal, protein, fat, carb, fiber, salt, extra in CATALOG:
        ing = Ingredient(
            name=name, source="bls", source_code=code, kcal_100=kcal, protein_100=protein, fat_100=fat,
            carb_100=carb, fiber_100=fiber, salt_100=salt, **extra,
        )  # fmt: skip
        session.add(ing)
        out[name] = ing
    session.commit()
    catalog.ensure_seed_synonyms(session)
    return out


def imported(lines, **kw) -> ImportedRecipe:
    kw.setdefault("title", "Testkuchen")
    kw.setdefault("source_url", "https://example.org/kuchen")
    kw.setdefault("servings", 2.0)
    return ImportedRecipe(ingredient_lines=lines, **kw)


GOOD_LINES = ["200 g Mehl", "2 Eier", "1 EL Olivenöl", "1 Prise Salz", "1 Zwiebel"]


def line_by_text(recipe, text) -> RecipeIngredient:
    return next(line for line in recipe.ingredients if line.raw_text == text)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def test_import_assigns_computes_grams_and_is_ready(session, ings):
    result = svc.build_recipe_from_import(session, imported(GOOD_LINES, source_site="example.org"))
    recipe = result.recipe
    assert recipe.status == "ready" and recipe.servings == 2.0
    assert (result.line_count, result.assigned_count) == (5, 5)
    assert recipe.source_site == "example.org" and recipe.source_url == "https://example.org/kuchen"
    grams = {line.raw_text: line.grams for line in recipe.ingredients}
    assert grams["200 g Mehl"] == 200.0
    assert grams["2 Eier"] == 120.0  # 2 x 60 g (piece_g)
    assert grams["1 EL Olivenöl"] == pytest.approx(13.5)  # 15 ml x 0,9 g/ml
    assert grams["1 Prise Salz"] == pytest.approx(0.4)
    assert grams["1 Zwiebel"] == 80.0
    assert [line.position for line in recipe.ingredients] == [0, 1, 2, 3, 4]
    assert session.get(Recipe, recipe.id) is recipe and recipe.tag is not None


def test_recipe_nutrition_matches_hand_calculation(session, ings):
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    nutrition = svc.compute_recipe_nutrition(recipe)
    # kcal: 200 g Mehl 680 + 120 g Ei 168 + 13,5 g Öl 121,5 + Salz 0 + 80 g Zwiebel 24
    assert nutrition.total.kcal == pytest.approx(993.5)
    assert nutrition.per_serving.kcal == pytest.approx(496.75)
    # Protein: 20 + 15 + 0 + 0 + 0,96; Fett: 2 + 11,4 + 13,5 + 0 + 0,16; KH: 140 + 0,6 + 0 + 0 + 4
    assert nutrition.total.protein_g == pytest.approx(35.96)
    assert nutrition.total.fat_g == pytest.approx(27.06)
    assert nutrition.total.carb_g == pytest.approx(144.6)
    assert nutrition.total.fiber_g == pytest.approx(6.0 + 1.2)
    assert nutrition.total.salt_g == pytest.approx(0.4)
    assert nutrition.total_weight_g == pytest.approx(200 + 120 + 13.5 + 0.4 + 80)
    assert nutrition.serving_weight_g == pytest.approx(nutrition.total_weight_g / 2)
    assert nutrition.coverage == 1.0 and nutrition.missing == []
    lines = svc.recipe_line_nutrition(recipe)
    assert [ln.grams for ln in lines] == [200.0, 120.0, 13.5, 0.4, 80.0]
    assert all(ln.per100 is not None for ln in lines)


def test_unknown_lines_make_recipe_needs_review(session, ings):
    lines = [*GOOD_LINES, "1 Dose Kichererbsen", "2 Handvoll Rucola", "evtl. Petersilie"]
    result = svc.build_recipe_from_import(session, imported(lines))
    recipe = result.recipe
    assert recipe.status == "needs_review"
    assert result.assigned_count == 5 and result.line_count == 8
    chickpeas = line_by_text(recipe, "1 Dose Kichererbsen")
    assert chickpeas.ingredient is None and chickpeas.grams == 400.0  # Gramm gehen auch ohne Zutat
    assert line_by_text(recipe, "evtl. Petersilie").optional is True
    nutrition = svc.compute_recipe_nutrition(recipe)
    assert nutrition.coverage == pytest.approx(5 / 7)  # optionale Zeile zählt nicht
    assert nutrition.missing == ["1 Dose Kichererbsen", "2 Handvoll Rucola"]


def test_optional_unmatched_line_does_not_block_ready(session, ings):
    recipe = svc.build_recipe_from_import(session, imported([*GOOD_LINES, "Petersilie nach Belieben"])).recipe
    assert recipe.status == "ready"


def test_line_without_known_unit_amount_needs_review(session, ings):
    recipe = svc.build_recipe_from_import(session, imported(["3 Zwiebelringe frittiert", "1 Zwiebel"])).recipe
    assert recipe.status == "needs_review"


def test_missing_servings_default_to_one_with_warning(session, ings):
    result = svc.build_recipe_from_import(
        session, imported(GOOD_LINES, servings=None, warnings=["Keine Portionsangabe gefunden"])
    )
    assert result.recipe.servings == 1.0
    assert any("1 Portion" in w for w in result.warnings)
    assert "Keine Portionsangabe gefunden" in result.warnings


def test_empty_recipe_is_draft(session, ings):
    recipe = svc.build_recipe_from_import(session, imported([])).recipe
    assert recipe.status == "draft" and recipe.ingredients == []


def test_plausibility_note_only_when_far_off(session, ings):
    far = svc.build_recipe_from_import(
        session, imported(GOOD_LINES, source_url="https://example.org/a", site_nutrients={"kcal": 200.0})
    ).recipe
    assert far.notes and "497 kcal" in far.notes and "200 kcal" in far.notes
    near = svc.build_recipe_from_import(
        session, imported(GOOD_LINES, source_url="https://example.org/b", site_nutrients={"kcal": 450.0})
    ).recipe
    assert near.notes is None  # 497 gegen 450: gut 10 %
    none = svc.build_recipe_from_import(
        session, imported(GOOD_LINES, source_url="https://example.org/c")
    ).recipe
    assert none.notes is None


def test_default_tags_only_when_certain(session, ings):
    soup = svc.build_recipe_from_import(session, imported(GOOD_LINES, title="Kürbissuppe")).recipe
    assert soup.tag.warm is True and soup.tag.slot_types == []
    oats = svc.build_recipe_from_import(
        session, imported(GOOD_LINES, title="Overnight Oats mit Beeren")
    ).recipe
    assert oats.tag.slot_types == ["breakfast"] and oats.tag.warm is False
    plain = svc.build_recipe_from_import(session, imported(GOOD_LINES, title="Kuchen")).recipe
    assert plain.tag.slot_types == [] and plain.tag.warm is False


def test_commit_false_keeps_transaction_open(session, ings):
    result = svc.build_recipe_from_import(session, imported(GOOD_LINES), commit=False)
    session.rollback()
    assert session.scalar(select(Recipe).where(Recipe.id == result.recipe.id)) is None


def test_find_by_url(session, ings):
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    assert svc.find_by_url(session, "https://example.org/kuchen").id == recipe.id
    assert svc.find_by_url(session, "https://example.org/other") is None


# ---------------------------------------------------------------------------
# Automatische Zuordnung: Vorsicht bei Komposita
# ---------------------------------------------------------------------------


def _m(name, score, via="fuzzy", ing_id=1) -> IngredientMatch:
    return IngredientMatch(ing_id, name, score, via)


def test_pick_auto_match_rules():
    assert svc.pick_auto_match([]) is None
    assert svc.pick_auto_match([_m("X", 100.0, "synonym")]).via == "synonym"
    assert svc.pick_auto_match([_m("X", 99.0, "exact"), _m("Y", 98.0, "fuzzy")]).via == "exact"
    assert svc.pick_auto_match([_m("Tomate roh", 95.0)], "Tomate") is not None
    assert svc.pick_auto_match([_m("Tomate roh", 87.9)], "Tomate") is None  # Score zu niedrig
    assert (
        svc.pick_auto_match([_m("Tomate roh", 95.0), _m("Tomate gekocht", 90.0)], "Tomate") is None
    )  # Abstand
    assert svc.pick_auto_match([_m("Tomate roh", 95.0), _m("Tomate gekocht", 86.0)], "Tomate") is not None


def test_pick_auto_match_rejects_compound_word_fuzzy_hits():
    for query, name in [("Apfel", "Apfelmus"), ("Tomate", "Tomatensauce"), ("Banane", "Bananenchips")]:
        assert svc.pick_auto_match([_m(name, 94.0)], query) is None
    assert svc.pick_auto_match([_m("Speiseapfel roh", 94.0)], "Apfel") is None  # Anhang am Wortanfang
    assert (
        svc.pick_auto_match([_m("Apfel roh", 94.0)], "Äpfel") is not None
    )  # ganzes Wort (Plural vereinfacht)
    assert svc.pick_auto_match([_m("Apfel/Birne, roh", 94.0)], "apfel") is not None
    assert svc.pick_auto_match([_m("Rote Zwiebel roh", 94.0)], "rote zwiebel") is not None
    assert svc.pick_auto_match([_m("Rote Bete roh", 94.0)], "rote zwiebel") is None
    assert (
        svc.pick_auto_match([_m("Apfelmus", 100.0, "exact")], "Apfel") is not None
    )  # exakt bleibt automatisch


def test_apfel_does_not_pick_apfelmus_but_suggests_it(session):
    mus = Ingredient(name="Apfelmus", source="bls", source_code="F100100", kcal_100=70.0)
    session.add(mus)
    session.commit()
    result = svc.build_recipe_from_import(session, imported(["2 Äpfel", "100 g Apfel"]))
    assert result.assigned_count == 0 and result.recipe.status == "needs_review"
    items, total = svc.unassigned_lines(session)
    assert total == 2 and all(i.suggestions and i.suggestions[0].ingredient_id == mus.id for i in items)
    preview = svc.preview_lines(session, ["2 Äpfel"])[0]
    assert preview.chosen is None and preview.matches[0].name == "Apfelmus"


def test_whole_word_fuzzy_hit_is_still_assigned(session):
    ing = Ingredient(name="Apfel roh", source="bls", source_code="F100200", kcal_100=52.0, piece_g=150.0)
    session.add(ing)
    session.commit()
    recipe = svc.build_recipe_from_import(session, imported(["2 Äpfel"])).recipe
    line = recipe.ingredients[0]
    assert line.ingredient is not None and line.ingredient.id == ing.id and line.grams == 300.0


# ---------------------------------------------------------------------------
# Manuell anlegen, ändern, neu berechnen
# ---------------------------------------------------------------------------


def test_create_manual_recipe_with_text_and_fixed_lines(session, ings):
    recipe = svc.create_manual_recipe(
        session,
        {
            "title": " Pfannkuchen ",
            "servings": 2,
            "tag": {"slot_types": ["breakfast", "breakfast", "snack"], "warm": True, "cuisine": "deutsch"},
            "lines": [
                {"raw_text": "200 g Mehl"},
                {"ingredient_id": ings["Hühnerei roh"].id, "grams": 120},
                {"raw_text": "Zimt nach Belieben", "optional": True},
            ],
        },
    )
    assert recipe.title == "Pfannkuchen" and recipe.status == "ready"  # optionale Zeile stört nicht
    assert (
        recipe.tag.slot_types == ["breakfast", "snack"]
        and recipe.tag.warm
        and recipe.tag.cuisine == "deutsch"
    )
    egg = recipe.ingredients[1]
    assert (
        egg.ingredient.id == ings["Hühnerei roh"].id
        and egg.grams == 120.0
        and egg.raw_text == "120 g Hühnerei roh"
    )
    assert recipe.ingredients[2].optional is True


def test_create_manual_recipe_validates(session, ings):
    with pytest.raises(svc.RecipeServiceError, match="Titel"):
        svc.create_manual_recipe(session, {"title": "  "})
    with pytest.raises(svc.RecipeServiceError, match="Titel"):
        svc.create_manual_recipe(session, {})
    with pytest.raises(svc.RecipeServiceError, match="Portionszahl"):
        svc.create_manual_recipe(session, {"title": "X", "servings": 0})
    with pytest.raises(svc.RecipeServiceError, match="Slot"):
        svc.create_manual_recipe(session, {"title": "X", "tag": {"slot_types": ["brunch"]}})
    with pytest.raises(svc.RecipeServiceError, match="Zutat 9999"):
        svc.create_manual_recipe(session, {"title": "X", "lines": [{"ingredient_id": 9999, "grams": 5}]})
    with pytest.raises(svc.RecipeServiceError, match="Text oder eine Zutat"):
        svc.create_manual_recipe(session, {"title": "X", "lines": [{"ingredient_id": 1}]})
    session.rollback()


def test_update_recipe_keeps_manual_assignment_for_unchanged_lines(session, ings):
    recipe = svc.create_manual_recipe(
        session, {"title": "Mix", "lines": [{"raw_text": "100 g Quark-Mix"}, {"raw_text": "1 Zwiebel"}]}
    )
    mix, onion = recipe.ingredients
    assert mix.ingredient is None and recipe.status == "needs_review"
    mix_id = mix.id
    # manuell zuordnen: eine feste Zuordnung muss jede Neuberechnung überstehen
    svc.update_recipe(
        session,
        recipe,
        {"lines": [{"id": mix_id, "raw_text": "100 g Quark-Mix", "ingredient_id": ings["Olivenöl"].id}]},
    )
    assert recipe.ingredients[0].ingredient.name == "Olivenöl" and recipe.status == "ready"
    assert [line.raw_text for line in recipe.ingredients] == ["100 g Quark-Mix"]  # die andere Zeile ist weg
    svc.update_recipe(session, recipe, {"servings": 4})
    assert recipe.ingredients[0].ingredient.name == "Olivenöl" and recipe.servings == 4
    # gleicher Text ohne neue ingredient_id: Zuordnung bleibt
    svc.update_recipe(session, recipe, {"lines": [{"id": mix_id, "raw_text": "100 g Quark-Mix"}]})
    assert recipe.ingredients[0].ingredient.name == "Olivenöl"
    # geänderter Text ohne ingredient_id: Zuordnung wird neu bestimmt
    svc.update_recipe(session, recipe, {"lines": [{"id": mix_id, "raw_text": "3 Zwiebeln"}]})
    line = recipe.ingredients[0]
    assert line.ingredient.name == "Speisezwiebel roh" and line.grams == 240.0 and line.id == mix_id
    assert onion.id not in {ln.id for ln in recipe.ingredients}


def test_update_recipe_fields_tag_and_errors(session, ings):
    recipe = svc.create_manual_recipe(session, {"title": "A", "lines": [{"raw_text": "1 Zwiebel"}]})
    svc.update_recipe(
        session,
        recipe,
        {
            "title": "B",
            "favorite": True,
            "prep_min": 5,
            "tag": {"warm": True},
            "source_url": "https://www.beispiel.de/x",
        },
    )
    assert (recipe.title, recipe.favorite, recipe.prep_min, recipe.tag.warm) == ("B", True, 5, True)
    assert recipe.source_site == "beispiel.de"
    svc.update_recipe(session, recipe, {"tag": {"slot_types": ["dinner"]}})
    assert recipe.tag.slot_types == ["dinner"] and recipe.tag.warm is True  # nur gesendete Felder
    with pytest.raises(svc.RecipeServiceError):
        svc.update_recipe(session, recipe, {"lines": [{"id": 424242, "raw_text": "x"}]})
    session.rollback()


def test_recompute_assigns_after_new_synonym_but_keeps_manual(session, ings):
    recipe = svc.create_manual_recipe(
        session,
        {
            "title": "R",
            "lines": [
                {"raw_text": "1 Bund Frühlingsmix"},
                {"raw_text": "2 Stück Spezial", "ingredient_id": ings["Hühnerei roh"].id},
            ],
        },
    )
    assert recipe.ingredients[0].ingredient is None and recipe.status == "needs_review"
    catalog.add_synonym(session, ings["Speisezwiebel roh"].id, "Frühlingsmix")
    svc.recompute_recipe(session, recipe)
    assert recipe.ingredients[0].ingredient.name == "Speisezwiebel roh"
    assert recipe.ingredients[1].ingredient.name == "Hühnerei roh" and recipe.ingredients[1].grams == 120.0
    assert recipe.status == "ready"


def test_recipe_status_follows_grams(session, ings):
    recipe = svc.create_manual_recipe(session, {"title": "R", "lines": [{"raw_text": "1 Zwiebel"}]})
    assert recipe.ingredients[0].grams == 80.0 and recipe.status == "ready"
    # zugeordnete Zeile ohne Menge ("nach Geschmack") hält den Status nicht auf
    recipe = svc.create_manual_recipe(
        session, {"title": "S", "lines": [{"raw_text": "1 Zwiebel"}, {"raw_text": "Salz nach Geschmack"}]}
    )
    salt = recipe.ingredients[1]
    assert salt.ingredient is not None and salt.grams is None
    assert recipe.status == "ready" and svc.compute_recipe_nutrition(recipe).coverage == 1.0
    # unbekannte Zutat mit Stückangabe bleibt offen
    recipe = svc.create_manual_recipe(session, {"title": "T", "lines": [{"raw_text": "2 Dinkelflocken"}]})
    assert recipe.ingredients[0].ingredient is None and recipe.status == "needs_review"


# ---------------------------------------------------------------------------
# Sättigung
# ---------------------------------------------------------------------------


def test_satiety_uses_warm_flag_of_tag(session, ings):
    recipe = svc.create_manual_recipe(session, {"title": "R", "lines": [{"raw_text": "300 g Milch"}]})
    cold = svc.recipe_satiety(recipe, svc.compute_recipe_nutrition(recipe))
    recipe.tag.warm = True
    warm = svc.recipe_satiety(recipe, svc.compute_recipe_nutrition(recipe))
    assert warm.score > cold.score and warm.parts["warm"] == 1.0 and cold.parts["warm"] == 0.0


# ---------------------------------------------------------------------------
# Bewertungen
# ---------------------------------------------------------------------------


def _person(session, name, sex="m"):
    p = Person(name=name, sex=sex, birth_date=date(1992, 2, 21), height_cm=180.0)
    session.add(p)
    session.commit()
    return p


def test_ratings_are_per_person(session, ings):
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    a, b = _person(session, "Test A"), _person(session, "Test B", "f")
    svc.set_rating(session, recipe.id, a.id, 5)
    svc.set_rating(session, recipe.id, b.id, 2)
    svc.set_rating(session, recipe.id, a.id, 4)  # überschreibt nur die eigene
    assert [(r.person_id, r.rating, name) for r, name in svc.ratings_with_names(session, recipe.id)] == [
        (a.id, 4, "Test A"),
        (b.id, 2, "Test B"),
    ]
    svc.remove_rating(session, recipe.id, a.id)
    svc.remove_rating(session, recipe.id, a.id)  # zweimal: kein Fehler
    assert [r.person_id for r, _ in svc.ratings_with_names(session, recipe.id)] == [b.id]
    for bad in (0, 6):
        with pytest.raises(svc.RecipeServiceError, match="1 und 5"):
            svc.set_rating(session, recipe.id, a.id, bad)
    with pytest.raises(svc.RecipeNotFound):
        svc.set_rating(session, 9999, a.id, 3)
    with pytest.raises(svc.RecipeNotFound):
        svc.remove_rating(session, 9999, a.id)


# ---------------------------------------------------------------------------
# Prüfliste und Zuordnen
# ---------------------------------------------------------------------------


def _two_recipes_with_same_unknown(session):
    one = svc.build_recipe_from_import(
        session, imported(["200 g Mehl", "2 Stück Bio Dinkelflocken"], source_url="https://example.org/1")
    ).recipe
    two = svc.build_recipe_from_import(
        session,
        imported(
            ["100 g Dinkelflocken", "1 Zwiebel", "Dinkelflocken (optional)"],
            source_url="https://example.org/2",
        ),
    ).recipe
    return one, two


def test_unassigned_lines_listing(session, ings):
    one, two = _two_recipes_with_same_unknown(session)
    assert one.status == two.status == "needs_review"
    items, total = svc.unassigned_lines(session)
    assert total == 2  # die optionale Zeile fehlt in der Liste
    assert [(i.recipe_id, i.recipe_title, i.name) for i in items] == [
        (one.id, "Testkuchen", "Bio Dinkelflocken"),
        (two.id, "Testkuchen", "Dinkelflocken"),
    ]
    assert all(i.similar_count == 2 for i in items)  # nur nicht optionale Zeilen zählen
    page, total = svc.unassigned_lines(session, limit=1, offset=1)
    assert total == 2 and [i.recipe_id for i in page] == [two.id]
    assert svc.unassigned_lines(session, limit=5, offset=10) == ([], 2)


def test_assign_line_learns_synonym_and_pulls_other_lines(session, ings):
    one, two = _two_recipes_with_same_unknown(session)
    target = Ingredient(
        name="Hafer Flocken", source="bls", source_code="C200000", kcal_100=370.0, piece_g=100.0
    )
    session.add(target)
    session.commit()
    first = line_by_text(one, "2 Stück Bio Dinkelflocken")

    result = svc.assign_line(session, first.id, target.id)
    assert result.synonym == "dinkelflocke"
    assert result.recipe_ids == sorted([one.id, two.id])
    optional_line = line_by_text(two, "Dinkelflocken (optional)")
    assert result.assigned_line_ids == sorted(
        [first.id, line_by_text(two, "100 g Dinkelflocken").id, optional_line.id]
    )
    assert catalog.synonym_map(session)["dinkelflocke"] == target.id
    session.refresh(one)
    session.refresh(two)
    assert one.status == "ready" and two.status == "ready"
    assert line_by_text(two, "100 g Dinkelflocken").grams == 100.0
    assert svc.unassigned_lines(session) == ([], 0)
    # künftige Importe nutzen das gelernte Synonym automatisch
    third = svc.build_recipe_from_import(
        session, imported(["50 g Dinkelflocken"], source_url="https://example.org/3")
    )
    assert third.recipe.status == "ready" and third.recipe.ingredients[0].ingredient.id == target.id


def test_assign_line_without_synonym_only_touches_that_line(session, ings):
    one, two = _two_recipes_with_same_unknown(session)
    target = Ingredient(
        name="Hafer Flocken", source="bls", source_code="C200000", kcal_100=370.0, piece_g=100.0
    )
    session.add(target)
    session.commit()
    line = line_by_text(one, "2 Stück Bio Dinkelflocken")
    result = svc.assign_line(session, line.id, target.id, save_synonym=False)
    assert result.synonym is None and result.assigned_line_ids == [line.id] and result.recipe_ids == [one.id]
    assert session.scalar(select(IngredientSynonym).where(IngredientSynonym.alias == "dinkelflocke")) is None
    assert line.ingredient.id == target.id and line.grams == 200.0  # 2 Stück x 100 g (piece_g der Zutat)
    assert svc.unassigned_lines(session)[1] == 1


def test_assign_line_overrides_stale_synonym_and_reports_missing(session, ings):
    one, _ = _two_recipes_with_same_unknown(session)
    target = Ingredient(
        name="Hafer Flocken", source="bls", source_code="C200000", kcal_100=370.0, piece_g=100.0
    )
    hidden = Ingredient(name="Alt", source="bls", source_code="C300000", kcal_100=1.0, hidden=True)
    session.add_all([target, hidden])
    session.commit()
    session.add(IngredientSynonym(alias="dinkelflocke", ingredient_id=hidden.id))  # zeigt auf Ausgeblendetes
    session.commit()
    line = line_by_text(one, "2 Stück Bio Dinkelflocken")
    assert svc.assign_line(session, line.id, target.id).synonym == "dinkelflocke"
    assert catalog.synonym_map(session)["dinkelflocke"] == target.id
    with pytest.raises(svc.RecipeNotFound, match="zeile"):
        svc.assign_line(session, 9999, target.id)
    with pytest.raises(svc.RecipeNotFound, match="Zutat"):
        svc.assign_line(session, line.id, 9999)


def test_unassigned_suggestions_include_best_matches(session, ings):
    svc.build_recipe_from_import(session, imported(["200 g Roggen Mehl"]))
    items, _ = svc.unassigned_lines(session)
    assert items and items[0].suggestions[0].name == "Weizen Mehl, Type 405"


# ---------------------------------------------------------------------------
# Passung ins Tagesziel
# ---------------------------------------------------------------------------


@pytest.fixture
def person(session):
    p = _person(session, "Test A")
    for i in range(40):
        session.add(
            HealthDaily(
                person_id=p.id, day=MONDAY - timedelta(days=39 - i), source="hae_zip",
                weight_kg=80.0, active_kcal=750.0, basal_kcal=2000.0,
            )
        )  # fmt: skip
    session.commit()
    return p


def test_slot_fit_uses_slot_target_and_fit_function(session, ings, person):
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    result = svc.slot_fit_for_person(session, person, recipe, MONDAY, "lunch")
    slot = compute_targets(session, person, MONDAY).slots["lunch"]
    nutrition = svc.compute_recipe_nutrition(recipe)
    expected = fit_to_target(nutrition.per_serving, nutrition.serving_weight_g, slot)
    assert result.slot == "lunch" and result.day == MONDAY and result.slot_target == slot
    assert result.fit.factor == pytest.approx(slot.kcal / 496.75)
    assert result.fit.factor == pytest.approx(expected.factor)
    assert result.fit.fit_score == pytest.approx(expected.fit_score)
    assert result.fit.scaled.kcal == pytest.approx(slot.kcal)
    assert any("fach" in note for note in result.notes)  # Hinweise der Passung sind enthalten
    assert result.warnings == []


def test_slot_fit_context_is_reusable(session, ings, person):
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    ctx = svc.slot_context(session, person, MONDAY, "dinner")
    again = svc.fit_nutrition(ctx, svc.compute_recipe_nutrition(recipe))
    direct = svc.slot_fit_for_person(session, person, recipe, MONDAY, "dinner")
    assert again.fit.fit_score == pytest.approx(direct.fit.fit_score)


def test_slot_not_planned_is_rejected(session, ings, person):
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    with pytest.raises(svc.RecipeServiceError, match="Dieser Slot ist für den Tag nicht vorgesehen"):
        svc.slot_fit_for_person(session, person, recipe, MONDAY, "snack")
    session.add(
        PersonSettingsRow(person_id=person.id, data={"slot_shares": {"breakfast": 1.0, "snack": 0.0}})
    )
    session.commit()
    with pytest.raises(svc.RecipeServiceError, match="nicht vorgesehen"):
        svc.slot_fit_for_person(session, person, recipe, MONDAY, "snack")  # Anteil 0
    with pytest.raises(svc.RecipeServiceError, match="nicht vorgesehen"):
        svc.slot_fit_for_person(session, person, recipe, MONDAY, "lunch")  # gar nicht in den Anteilen


def test_targets_unavailable_is_passed_through(session, ings):
    nobody = _person(session, "Ohne Daten")
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    with pytest.raises(TargetsUnavailable, match="Gewicht"):
        svc.slot_fit_for_person(session, nobody, recipe, MONDAY, "lunch")


def test_single_meal_limit_adds_warning_to_notes(session, ings, person):
    session.add(PersonSettingsRow(person_id=person.id, data={"single_meal_max_kcal": 300}))
    session.commit()
    recipe = svc.build_recipe_from_import(session, imported(GOOD_LINES)).recipe
    result = svc.slot_fit_for_person(session, person, recipe, MONDAY, "lunch")
    assert [w.code for w in result.warnings] == ["meal_too_large"]
    assert any("Obergrenze" in note for note in result.notes)


def test_low_coverage_adds_note(session, ings, person):
    recipe = svc.build_recipe_from_import(session, imported([*GOOD_LINES, "1 Dose Kichererbsen"])).recipe
    result = svc.slot_fit_for_person(session, person, recipe, MONDAY, "lunch")
    assert any("der Zutaten haben Nährwerte" in note for note in result.notes)


def test_get_recipe_and_load_filters(session, ings):
    one = svc.build_recipe_from_import(
        session, imported(GOOD_LINES, title="Zwiebelkuchen", source_url="u1")
    ).recipe
    two = svc.build_recipe_from_import(
        session, imported(["1 Dose Bohnen"], title="Bohneneintopf", source_url="u2")
    ).recipe
    one.favorite = True
    session.commit()
    assert svc.get_recipe(session, one.id).title == "Zwiebelkuchen"
    with pytest.raises(svc.RecipeNotFound):
        svc.get_recipe(session, 9999)
    assert [r.id for r in svc.load_recipes(session)] == [one.id, two.id]
    assert [r.id for r in svc.load_recipes(session, q="BOHNEN")] == [two.id]
    assert [r.id for r in svc.load_recipes(session, favorite=True)] == [one.id]
    assert [r.id for r in svc.load_recipes(session, status="needs_review")] == [two.id]
    assert svc.load_recipes(session, q="%") == []
