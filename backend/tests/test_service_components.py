"""Tests für den Komponenten-Baukasten (Service). Alle Zutaten, Personen und Werte sind erfunden."""

from datetime import date, timedelta

import pytest

from app.calc.nutrition import fit_to_target
from app.models import (
    Component,
    ComponentVariant,
    GoalProfile,
    HealthDaily,
    Ingredient,
    IngredientSynonym,
    Person,
    PersonSettingsRow,
)
from app.services import components as svc
from app.services.components import (
    ComponentConflict,
    ComponentError,
    ComponentNotFound,
    MealItem,
    compute_meal,
    create_component,
    create_variant,
    delete_component,
    delete_variant,
    get_component,
    seed_default_components,
    update_component,
    update_variant,
)
from app.services.targets import TargetsUnavailable, compute_targets

MONDAY = date(2026, 10, 5)  # ein Montag
SATURDAY = date(2026, 10, 10)


def ing(session, name, **kw) -> Ingredient:
    kw.setdefault("source", "manual")
    row = Ingredient(name=name, **kw)
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def egg(session):
    return ing(
        session, "Testei", kcal_100=140, protein_100=12, fat_100=10, carb_100=1, fiber_100=0,
        salt_100=0.37, micros={"zinc_mg": 1.3},
    )  # fmt: skip


@pytest.fixture
def bread(session):
    return ing(
        session, "Testbrot", kcal_100=250, protein_100=9, fat_100=2, carb_100=48, fiber_100=7, salt_100=1.2
    )


@pytest.fixture
def skyr(session):
    return ing(session, "Testskyr", kcal_100=63, protein_100=11, fat_100=0.2, carb_100=4, salt_100=0.1)


@pytest.fixture
def parts(session, egg, bread, skyr):
    """Drei Komponenten: Ei (mit Variante Stück à 60 g), Brot, Skyr."""
    c_egg = create_component(
        session, name="Ei", kind="protein", ingredient_id=egg.id, min_g=0, max_g=360, step_g=60, typical_g=120
    )
    v_egg = create_variant(session, c_egg, name="Stück", grams_per_unit=60)
    c_bread = create_component(session, name="Brot", kind="carb", ingredient_id=bread.id, max_g=200)
    c_skyr = create_component(session, name="Skyr", kind="dairy", ingredient_id=skyr.id, max_g=400)
    return c_egg, v_egg, c_bread, c_skyr


# ---------------------------------------------------------------------------
# CRUD und Validierung
# ---------------------------------------------------------------------------


def test_create_component_defaults(session, egg):
    c = create_component(session, name="  Ei  ", kind="protein", ingredient_id=egg.id)
    assert c.id and c.name == "Ei"
    assert (c.min_g, c.max_g, c.step_g, c.typical_g, c.weekend_fixed) == (0.0, 500.0, 10.0, None, False)
    assert get_component(session, c.id) is c


@pytest.mark.parametrize(
    ("kwargs", "text"),
    [
        ({"min_g": 100, "max_g": 50}, "Mindestmenge"),
        ({"min_g": -1}, "negativ"),
        ({"typical_g": 600}, "übliche Menge"),
        ({"min_g": 50, "typical_g": 10}, "übliche Menge"),
        ({"step_g": 0}, "Schrittweite"),
        ({"step_g": -5}, "Schrittweite"),
        ({"max_g": 50_000}, "Höchstmenge"),
        ({"kind": "meat"}, "Ungültige Art"),
        ({"ingredient_id": 9999}, "Zutat"),
        ({"name": "   "}, "Name"),
        ({"name": "x" * 121}, "Name"),
    ],
)
def test_create_component_validation(session, egg, kwargs, text):
    args = {"name": "Ei", "kind": "protein", "ingredient_id": egg.id} | kwargs
    with pytest.raises(ComponentError, match=text):
        create_component(session, **args)
    assert session.query(Component).count() == 0


def test_typical_may_equal_bounds(session, egg):
    c = create_component(session, name="Ei", kind="protein", ingredient_id=egg.id, max_g=100, typical_g=100)
    assert c.typical_g == 100


def test_component_name_unique_case_insensitive(session, egg, skyr):
    create_component(session, name="Äpfel", kind="fruit", ingredient_id=egg.id)
    with pytest.raises(ComponentConflict):
        create_component(session, name="äpfel", kind="fruit", ingredient_id=skyr.id)


def test_update_component_merges_and_validates(session, parts, skyr):
    c_egg = parts[0]
    update_component(session, c_egg, {"max_g": 400, "typical_g": None, "weekend_fixed": True})
    assert (c_egg.max_g, c_egg.typical_g, c_egg.weekend_fixed) == (400, None, True)
    with pytest.raises(ComponentError, match="Mindestmenge"):
        update_component(session, c_egg, {"min_g": 500})
    with pytest.raises(ComponentError, match="übliche Menge"):
        update_component(session, c_egg, {"typical_g": 999})
    with pytest.raises(ComponentError, match="nicht leer"):
        update_component(session, c_egg, {"name": None})
    with pytest.raises(ComponentError, match="Unbekannte"):
        update_component(session, c_egg, {"id": 5})
    with pytest.raises(ComponentError, match="Zutat"):
        update_component(session, c_egg, {"ingredient_id": 424242})
    update_component(session, c_egg, {"ingredient_id": skyr.id, "name": "Ei"})  # eigener Name erlaubt
    assert c_egg.ingredient_id == skyr.id
    with pytest.raises(ComponentConflict):
        update_component(session, c_egg, {"name": "skyr"})
    assert c_egg.max_g == 400  # Fehlversuche haben nichts verändert


def test_get_missing_component(session):
    with pytest.raises(ComponentNotFound):
        get_component(session, 123)


def test_variants_crud_and_validation(session, parts, skyr):
    c_egg, v_egg, _, _ = parts
    assert v_egg.ingredient_id == c_egg.ingredient_id  # Standard: Zutat der Komponente
    assert [v.name for v in c_egg.variants] == ["Stück"]
    other = create_variant(session, c_egg, name="Skyr-Ei", ingredient_id=skyr.id, grams_per_unit=50)
    assert other.ingredient_id == skyr.id
    with pytest.raises(ComponentConflict):
        create_variant(session, c_egg, name="STÜCK")
    for bad in (0, -3):
        with pytest.raises(ComponentError, match="Gewicht je Einheit"):
            create_variant(session, c_egg, name="Neu", grams_per_unit=bad)
    with pytest.raises(ComponentError, match="Zutat"):
        create_variant(session, c_egg, name="Neu", ingredient_id=777)
    with pytest.raises(ComponentError, match="Name"):
        create_variant(session, c_egg, name=" ")

    update_variant(session, c_egg, other, {"grams_per_unit": None, "name": "Anders"})
    assert (other.name, other.grams_per_unit) == ("Anders", None)
    with pytest.raises(ComponentConflict):
        update_variant(session, c_egg, other, {"name": "Stück"})
    with pytest.raises(ComponentError, match="nicht leer"):
        update_variant(session, c_egg, other, {"ingredient_id": None})
    with pytest.raises(ComponentError, match="Gewicht je Einheit"):
        update_variant(session, c_egg, other, {"grams_per_unit": 0})

    delete_variant(session, c_egg, other)
    assert session.query(ComponentVariant).count() == 1
    assert [v.name for v in c_egg.variants] == ["Stück"]


def test_get_variant_of_other_component_is_not_found(session, parts):
    c_egg, v_egg, c_bread, _ = parts
    with pytest.raises(ComponentNotFound):
        svc.get_variant(session, c_bread, v_egg.id)
    assert svc.get_variant(session, c_egg, v_egg.id) is v_egg


def test_delete_component_removes_variants(session, parts):
    c_egg = parts[0]
    delete_component(session, c_egg)
    assert session.query(Component).count() == 2
    assert session.query(ComponentVariant).count() == 0


def test_ingredient_in_use_by_component_cannot_be_deleted(session, parts, egg):
    # RESTRICT schützt die Zutat; der Dienst meldet beim Löschen der Zutat einen Konflikt (E1)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.delete(egg)
        session.commit()
    session.rollback()


def test_list_components_order(session, egg, bread):
    create_component(session, name="Wochenend-Brot", kind="carb", ingredient_id=bread.id, weekend_fixed=True)
    create_component(session, name="Zeta", kind="protein", ingredient_id=egg.id)
    create_component(session, name="Alpha", kind="protein", ingredient_id=egg.id)
    assert [c.name for c in svc.list_components(session)] == ["Alpha", "Zeta", "Wochenend-Brot"]


def test_ingredient_to_per100_keeps_unknown_and_filters_micros(session):
    row = ing(session, "Teil", kcal_100=10, micros={"zinc_mg": 2, "bad": "x", "flag": True})
    p = svc.ingredient_to_per100(row)
    assert p.kcal == 10 and p.protein_g is None and p.salt_g is None
    assert p.micros == {"zinc_mg": 2.0}


# ---------------------------------------------------------------------------
# Mahlzeit berechnen
# ---------------------------------------------------------------------------


def test_compute_meal_by_hand(session, parts):
    c_egg, v_egg, c_bread, c_skyr = parts
    r = compute_meal(
        session,
        [
            MealItem(c_egg.id, v_egg.id, units=2),  # 2 × 60 g = 120 g Ei
            MealItem(c_bread.id, grams=100),
            MealItem(c_skyr.id, grams=250),
        ],
    )
    # kcal: 120×1,40 + 100×2,50 + 250×0,63 = 168 + 250 + 157,5
    assert r.total.kcal == pytest.approx(575.5)
    # Protein: 120×0,12 + 100×0,09 + 250×0,11 = 14,4 + 9 + 27,5
    assert r.total.protein_g == pytest.approx(50.9)
    # Salz: 120×0,0037 + 100×0,012 + 250×0,001 = 0,444 + 1,2 + 0,25
    assert r.total.salt_g == pytest.approx(1.894)
    assert r.total.micros == {"zinc_mg": pytest.approx(1.56)}
    assert r.weight_g == pytest.approx(470)
    assert r.energy_density_kcal_per_100g == pytest.approx(575.5 / 470 * 100)
    assert r.coverage == 1.0 and r.missing == []
    assert 0 <= r.satiety.score <= 100 and r.satiety.parts["warm"] == 0.0
    assert r.fit is None

    egg_line = r.lines[0]
    assert (egg_line.grams, egg_line.units, egg_line.variant_name) == (120.0, 2.0, "Stück")
    assert egg_line.ingredient_name == "Testei"
    assert egg_line.nutrients.kcal == pytest.approx(168)
    assert sum(line.nutrients.kcal for line in r.lines) == pytest.approx(r.total.kcal)
    assert r.lines[1].units is None and r.lines[1].variant_id is None
    assert any(n.startswith("Mahlzeit wiegt 470 g") for n in r.notes)
    assert any(n == "Salz in dieser Mahlzeit: 1,9 g" for n in r.notes)


def test_variant_with_other_ingredient_is_used(session, parts, skyr):
    c_egg = parts[0]
    v = create_variant(session, c_egg, name="Skyr statt Ei", ingredient_id=skyr.id, grams_per_unit=100)
    r = compute_meal(session, [MealItem(c_egg.id, v.id, units=1.5)])
    assert r.lines[0].ingredient_name == "Testskyr"
    assert r.total.kcal == pytest.approx(150 * 0.63)


def test_units_fall_back_to_piece_weight_of_ingredient(session):
    apple = ing(session, "Testapfel", kcal_100=52, piece_g=180)
    comp = create_component(session, name="Apfel", kind="fruit", ingredient_id=apple.id)
    r = compute_meal(session, [MealItem(comp.id, units=2)])
    assert r.weight_g == pytest.approx(360)
    assert r.total.kcal == pytest.approx(360 * 0.52)


def test_units_without_weight_is_rejected(session, parts):
    _, _, c_bread, _ = parts
    with pytest.raises(ComponentError, match="Gewicht je Einheit"):
        compute_meal(session, [MealItem(c_bread.id, units=2)])


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"grams": 10, "units": 1}, {"grams": -1}, {"units": -1}, {"grams": 99_999}, {"units": 5000}],
)
def test_invalid_amounts_are_rejected(session, parts, kwargs):
    with pytest.raises(ComponentError):
        compute_meal(session, [MealItem(parts[2].id, **kwargs)])


def test_unknown_component_and_foreign_variant(session, parts):
    c_egg, v_egg, c_bread, _ = parts
    with pytest.raises(ComponentNotFound):
        compute_meal(session, [MealItem(9999, grams=10)])
    with pytest.raises(ComponentError, match="gehört nicht zur Komponente"):
        compute_meal(session, [MealItem(c_bread.id, v_egg.id, grams=10)])
    with pytest.raises(ComponentError, match="mindestens eine"):
        compute_meal(session, [])


def test_zero_grams_is_allowed(session, parts):
    r = compute_meal(session, [MealItem(parts[2].id, grams=0), MealItem(parts[3].id, grams=100)])
    assert r.total.kcal == pytest.approx(63)
    assert r.lines[0].grams == 0


def test_weight_note_in_kg_and_range_notes(session, parts):
    _, _, _, c_skyr = parts  # max 400 g
    r = compute_meal(session, [MealItem(c_skyr.id, grams=1400)])
    assert r.notes[0] == "Mahlzeit wiegt 1,4 kg"
    assert any("über dem üblichen Maximum von 400 g" in n for n in r.notes)
    heavy = compute_meal(session, [MealItem(c_skyr.id, grams=1600)])
    assert heavy.notes[0] == "Mahlzeit wiegt 1,6 kg: sehr viel auf einmal"


def test_min_range_note(session, egg):
    comp = create_component(session, name="Ei", kind="protein", ingredient_id=egg.id, min_g=60, max_g=300)
    r = compute_meal(session, [MealItem(comp.id, grams=30)])
    assert any("unter dem Minimum von 60 g" in n for n in r.notes)


def test_missing_kcal_lowers_coverage(session, parts):
    mystery = ing(session, "Rätselzutat", protein_100=5)
    comp = create_component(session, name="Rätsel", kind="other", ingredient_id=mystery.id)
    r = compute_meal(session, [MealItem(comp.id, grams=50), MealItem(parts[3].id, grams=100)])
    assert r.coverage == pytest.approx(0.5)
    assert r.missing == ["Rätsel"]
    assert any("Keine Kalorienwerte für: Rätsel" in n for n in r.notes)


def test_label_with_variant_in_missing(session, parts):
    mystery = ing(session, "Rätselzutat2")
    comp = create_component(session, name="Rätsel", kind="other", ingredient_id=mystery.id)
    v = create_variant(session, comp, name="Stück", grams_per_unit=10)
    r = compute_meal(session, [MealItem(comp.id, v.id, units=3)])
    assert r.missing == ["Rätsel (Stück)"]


# ---------------------------------------------------------------------------
# Passung ins Tagesziel
# ---------------------------------------------------------------------------


@pytest.fixture
def person(session):
    p = Person(name="Test A", sex="m", birth_date=date(1992, 2, 21), height_cm=190.0)
    session.add(p)
    session.commit()
    return p


def seed_person(session, p, *, end=MONDAY, days=30, shares=None, **settings):
    for i in range(days):
        session.add(
            HealthDaily(
                person_id=p.id, day=end - timedelta(days=days - 1 - i), source="hae_zip",
                weight_kg=80.0, active_kcal=750.0, basal_kcal=2000.0,
            )
        )  # fmt: skip
    session.add(GoalProfile(person_id=p.id, kind="lose", rate_kg_per_week=0.5, valid_from=date(2026, 1, 1)))
    data = dict(settings)
    if shares is not None:
        data["slot_shares"] = shares
    session.add(PersonSettingsRow(person_id=p.id, data=data))
    session.commit()


def test_fit_for_person_without_scaling(session, parts, person):
    seed_person(session, person, shares={"breakfast": 1.0})
    c_egg, v_egg, c_bread, c_skyr = parts
    items = [
        MealItem(c_egg.id, v_egg.id, units=2),
        MealItem(c_bread.id, grams=100),
        MealItem(c_skyr.id, grams=250),
    ]
    r = compute_meal(session, items, person=person, on=MONDAY, slot="breakfast")
    target = compute_targets(session, person, MONDAY).slots["breakfast"]  # ≈ 2200 kcal, alles in einem Slot
    assert r.fit is not None and r.fit.slot == "breakfast" and r.fit.day == MONDAY
    assert r.fit.target == target

    # Abweichung der Summe (Menge bleibt wie gewählt, kein Faktor)
    assert r.fit.deviation_pct["kcal"] == pytest.approx((575.5 - target.kcal) / target.kcal * 100)
    assert r.fit.deviation_pct["protein"] == pytest.approx((50.9 - target.protein_g) / target.protein_g * 100)
    assert r.fit.deviation_pct["kcal"] < -50

    reference = fit_to_target(r.total, r.weight_g, target, min_factor=1.0, max_factor=1.0)
    assert r.fit.fit_score == pytest.approx(reference.fit_score)
    assert 0 <= r.fit.fit_score < 50

    joined = " | ".join(r.fit.notes)
    assert "Energie 576 kcal" in joined and "unter dem Ziel" in joined
    assert "Protein" in joined and "unter Ziel" in joined
    assert "Portion wäre" not in joined and "Faktor" not in joined and "-fach" not in joined


def test_fit_is_high_when_meal_matches_target(session, person):
    seed_person(session, person, shares={"breakfast": 1.0})
    target = compute_targets(session, person, MONDAY).slots["breakfast"]
    # Zutat mit genau den Zielwerten je 100 g (erfunden): 100 g ergeben das Ziel
    exact = ing(
        session, "Zielmix", kcal_100=target.kcal, protein_100=target.protein_g, fat_100=target.fat_g,
        carb_100=target.carb_g,
    )  # fmt: skip
    comp = create_component(session, name="Mix", kind="other", ingredient_id=exact.id, max_g=1000)
    r = compute_meal(session, [MealItem(comp.id, grams=100)], person=person, on=MONDAY, slot="breakfast")
    assert r.fit.fit_score == pytest.approx(100)
    assert all(abs(v) < 1e-6 for v in r.fit.deviation_pct.values())
    assert r.fit.notes == []


def test_fit_defaults_to_today(session, parts, person):
    import app.services.components as module

    seed_person(session, person, end=date.today(), shares={"breakfast": 1.0})
    r = compute_meal(session, [MealItem(parts[3].id, grams=100)], person=person, slot="breakfast")
    assert r.fit.day == module._today()


def test_single_meal_limit_warning(session, parts, person):
    seed_person(session, person, shares={"breakfast": 1.0}, single_meal_max_kcal=600)
    c_egg, v_egg, c_bread, c_skyr = parts
    big = compute_meal(
        session, [MealItem(c_bread.id, grams=200), MealItem(c_skyr.id, grams=400)],
        person=person, on=MONDAY, slot="breakfast",
    )  # fmt: skip
    # 200×2,5 + 400×0,63 = 752 kcal
    assert any(w.code == "meal_too_large" for w in big.fit.warnings)
    small = compute_meal(
        session, [MealItem(c_skyr.id, grams=100)], person=person, on=MONDAY, slot="breakfast"
    )
    assert small.fit.warnings == []


def test_slot_must_exist_in_plan(session, parts, person):
    seed_person(session, person, shares={"breakfast": 1.0, "lunch": 0.0})
    for slot in ("dinner", "lunch", "snack"):  # fehlt bzw. Anteil 0
        with pytest.raises(ComponentError, match="kommt im Plan"):
            compute_meal(session, [MealItem(parts[3].id, grams=50)], person=person, on=MONDAY, slot=slot)


def test_weekend_slot_shares_are_used(session, parts, person):
    seed_person(
        session, person, end=SATURDAY, shares={"breakfast": 1.0},
        slot_shares_weekend={"breakfast": 0.4, "dinner": 0.6},
    )  # fmt: skip
    items = [MealItem(parts[3].id, grams=100)]
    weekday = compute_meal(session, items, person=person, on=MONDAY, slot="breakfast")
    weekend = compute_meal(session, items, person=person, on=SATURDAY, slot="breakfast")
    assert weekend.fit.target.kcal == pytest.approx(
        0.4 * compute_targets(session, person, SATURDAY).target.kcal, abs=1
    )
    assert weekday.fit.target.kcal > weekend.fit.target.kcal
    dinner = compute_meal(session, items, person=person, on=SATURDAY, slot="dinner")
    assert dinner.fit.target.kcal > weekend.fit.target.kcal
    with pytest.raises(ComponentError, match="kommt im Plan"):
        compute_meal(session, items, person=person, on=MONDAY, slot="dinner")


def test_targets_unavailable_is_passed_through(session, parts, person):
    with pytest.raises(TargetsUnavailable, match="Gewicht"):
        compute_meal(session, [MealItem(parts[3].id, grams=50)], person=person, on=MONDAY, slot="breakfast")


def test_slot_needs_person(session, parts):
    with pytest.raises(ComponentError, match="Person"):
        compute_meal(session, [MealItem(parts[3].id, grams=50)], slot="breakfast")


def test_person_without_slot_gives_no_fit(session, parts, person):
    r = compute_meal(session, [MealItem(parts[3].id, grams=50)], person=person, on=MONDAY)
    assert r.fit is None


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def _catalog(session):
    """Kleiner erfundener Katalog: ein Teil der Standardnamen, einer nur über Synonym, einer versteckt."""
    rows = {
        "ei": ing(session, "Hühnerei", kcal_100=140, protein_100=12, fat_100=10, carb_100=1),
        "brot": ing(session, "Vollkornbrot", kcal_100=210, protein_100=7, fat_100=1.2, carb_100=40),
        "skyr": ing(session, "Skyr, natur", kcal_100=63, protein_100=11),  # Kopf vor dem Komma = "Skyr"
        "banane": ing(session, "Banane", kcal_100=95, protein_100=1.1, carb_100=21),
        "gurke": ing(session, "Gurkenkonserve", kcal_100=12),
        "tomate": ing(session, "Tomate", kcal_100=18, hidden=True),
        "apfelsaft": ing(session, "Apfelsaft", kcal_100=46),  # darf NICHT als "Apfel" gelten
    }
    session.add(IngredientSynonym(alias="saure gurke", ingredient_id=rows["gurke"].id))
    session.commit()
    return rows


def test_seed_creates_matches_and_reports_missing(session):
    rows = _catalog(session)
    result = seed_default_components(session)

    assert set(result["created"]) == {
        "Ei", "Brot", "Skyr", "Banane", "Saure Gurken", "Brot (Wochenende)", "Rührei (Wochenende)"
    }  # fmt: skip
    # nicht gefunden: nie raten (Apfelsaft ≠ Apfel, versteckte Zutat zählt nicht)
    for name in ("Apfel", "Tomate", "Brötchen", "Kräuterquark", "Hummus (Wochenende)", "Kiwi (Wochenende)"):
        assert name in result["missing"], name
    assert "Apfel" not in result["created"]
    assert result["skipped"] == []
    assert set(result["created"]).isdisjoint(result["missing"])
    assert len(result["created"]) + len(result["missing"]) == len(svc.DEFAULT_COMPONENTS)

    by_name = {c.name: c for c in session.query(Component)}
    assert by_name["Ei"].ingredient_id == rows["ei"].id
    assert by_name["Skyr"].ingredient_id == rows["skyr"].id
    assert by_name["Saure Gurken"].ingredient_id == rows["gurke"].id  # über Synonym
    assert by_name["Rührei (Wochenende)"].ingredient_id == rows["ei"].id  # Rückfall "Hühnerei"
    assert by_name["Rührei (Wochenende)"].weekend_fixed is True
    assert by_name["Ei"].weekend_fixed is False
    assert result["matched"]["Skyr"] == "Skyr, natur"

    egg = by_name["Ei"]
    assert (egg.min_g, egg.max_g, egg.typical_g) == (0, 360, 120)
    assert [(v.name, v.grams_per_unit) for v in egg.variants] == [("Stück", 60.0)]
    assert "Ei: Rührei" in result["missing_variants"]  # kein Rührei im Katalog: nicht erfunden
    assert result["variants_created"] == session.query(ComponentVariant).count()
    for c in by_name.values():  # alle angelegten Komponenten erfüllen die Regeln
        assert c.min_g <= (c.typical_g or 0) <= c.max_g and c.step_g > 0

    # Die Standard-Eier ergeben eine plausible Summe: 2 Stück à 60 g
    meal = compute_meal(session, [MealItem(egg.id, egg.variants[0].id, units=2)])
    assert meal.total.kcal == pytest.approx(168)


def test_seed_is_idempotent(session):
    _catalog(session)
    first = seed_default_components(session)
    n_components = session.query(Component).count()
    n_variants = session.query(ComponentVariant).count()
    second = seed_default_components(session)
    assert second["created"] == [] and second["variants_created"] == 0
    assert set(second["skipped"]) == set(first["created"])
    assert second["missing"] == first["missing"]
    assert session.query(Component).count() == n_components
    assert session.query(ComponentVariant).count() == n_variants


def test_seed_keeps_manual_edits_and_picks_up_new_ingredients(session):
    _catalog(session)
    seed_default_components(session)
    skyr_comp = session.query(Component).filter_by(name="Skyr").one()
    update_component(session, skyr_comp, {"max_g": 300, "typical_g": 150})
    ing(session, "Kiwi", kcal_100=61)
    result = seed_default_components(session)
    assert result["created"] == ["Kiwi (Wochenende)"]
    session.refresh(skyr_comp)
    assert (skyr_comp.max_g, skyr_comp.typical_g) == (300, 150)


def test_seed_does_not_guess_compound_names(session):
    # "Tomatensauce" und "Bananenchips" erreichen als Fuzzy-Treffer hohe Scores, sind aber andere Zutaten
    ing(session, "Tomatensauce", kcal_100=60)
    ing(session, "Bananenchips", kcal_100=500)
    result = seed_default_components(session)
    assert result["created"] == []
    assert "Tomate" in result["missing"] and "Banane" in result["missing"]


def test_seed_accepts_synonym_even_for_compound_names(session):
    sauce = ing(session, "Tomatensauce", kcal_100=60)
    session.add(IngredientSynonym(alias="tomate", ingredient_id=sauce.id))
    session.commit()
    assert seed_default_components(session)["created"] == ["Tomate"]


def test_seed_with_empty_catalog(session):
    result = seed_default_components(session)
    assert result["created"] == [] and len(result["missing"]) == len(svc.DEFAULT_COMPONENTS)
    assert session.query(Component).count() == 0


def test_seed_prefers_exact_name_over_fuzzy(session):
    ing(session, "Banane, getrocknet", kcal_100=300)
    exact = ing(session, "Banane", kcal_100=95)
    seed_default_components(session)
    assert session.query(Component).filter_by(name="Banane").one().ingredient_id == exact.id


def test_default_seed_table_is_consistent():
    names = [s.name for s in svc.DEFAULT_COMPONENTS]
    assert len({n.casefold() for n in names}) == len(names)
    for s in svc.DEFAULT_COMPONENTS:
        assert s.kind in svc.COMPONENT_KINDS and s.candidates
        assert s.min_g <= s.typical_g <= s.max_g and s.step_g > 0
        assert s.weekend_fixed == s.name.endswith("(Wochenende)")
        for v in s.variants:
            assert v.grams_per_unit is None or v.grams_per_unit > 0
