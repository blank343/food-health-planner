"""Tests für Nährwertrechner, Sättigungsscore und Passung ins Slot-Ziel (alle Zahlen erfunden)."""

import pytest

from app.calc.nutrition import (
    component_meal,
    fit_to_target,
    recipe_nutrition,
    satiety_score,
    scale_nutrients,
)
from app.calc.types import (
    ComponentChoice,
    LineNutrition,
    Nutrients,
    NutrientsPer100,
    SlotTarget,
)

approx = pytest.approx


def per100(**kw) -> NutrientsPer100:
    return NutrientsPer100(**kw)


# ---------------------------------------------------------------------------
# Skalierung
# ---------------------------------------------------------------------------


def test_scale_nutrients_basic():
    p = per100(kcal=200, protein_g=10, fat_g=5, carb_g=30, fiber_g=2, salt_g=0.5, micros={"zinc_mg": 1.0})
    n = scale_nutrients(p, 150)
    assert n.kcal == approx(300)
    assert n.protein_g == approx(15)
    assert n.fat_g == approx(7.5)
    assert n.carb_g == approx(45)
    assert n.fiber_g == approx(3)
    assert n.salt_g == approx(0.75)
    assert n.micros == {"zinc_mg": approx(1.5)}


def test_scale_nutrients_unknown_counts_as_zero():
    n = scale_nutrients(per100(kcal=100), 50)
    assert n.kcal == approx(50)
    assert (n.protein_g, n.fat_g, n.carb_g, n.fiber_g, n.salt_g) == (0, 0, 0, 0, 0)
    assert n.micros == {}


def test_scale_nutrients_zero_grams():
    n = scale_nutrients(per100(kcal=100, micros={"iron_mg": 2}), 0)
    assert n.kcal == 0
    assert n.micros == {"iron_mg": 0}


def test_salt_from_sodium_when_salt_unknown():
    # 400 mg Natrium je 100 g = 1,0 g Salz je 100 g; 50 g davon = 0,5 g Salz
    n = scale_nutrients(per100(kcal=10, micros={"sodium_mg": 400}), 50)
    assert n.salt_g == approx(0.5)
    assert n.micros["sodium_mg"] == approx(200)


def test_explicit_salt_beats_sodium():
    n = scale_nutrients(per100(salt_g=2.0, micros={"sodium_mg": 400}), 100)
    assert n.salt_g == approx(2.0)


# ---------------------------------------------------------------------------
# Rezeptsummen
# ---------------------------------------------------------------------------

LINE_A = LineNutrition(
    "A",
    200,
    per100(
        kcal=100, protein_g=10, fat_g=1, carb_g=5, fiber_g=2, salt_g=0.1, micros={"iron_mg": 2, "zinc_mg": 1}
    ),
)
LINE_B = LineNutrition(
    "B",
    100,
    per100(kcal=400, protein_g=20, fat_g=30, carb_g=10, fiber_g=0, salt_g=1.0, micros={"iron_mg": 1}),
)


def test_recipe_nutrition_sums_and_serving():
    r = recipe_nutrition([LINE_A, LINE_B], servings=2)
    assert r.total.kcal == approx(600)
    assert r.total.protein_g == approx(40)
    assert r.total.fat_g == approx(32)
    assert r.total.carb_g == approx(20)
    assert r.total.fiber_g == approx(4)
    assert r.total.salt_g == approx(1.2)
    assert r.total.micros == {"iron_mg": approx(5), "zinc_mg": approx(2)}
    assert r.per_serving.kcal == approx(300)
    assert r.per_serving.protein_g == approx(20)
    assert r.per_serving.salt_g == approx(0.6)
    assert r.per_serving.micros == {"iron_mg": approx(2.5), "zinc_mg": approx(1)}
    assert r.servings == 2
    assert r.total_weight_g == approx(300)
    assert r.serving_weight_g == approx(150)
    assert r.energy_density_kcal_per_100g == approx(200)
    assert r.coverage == 1.0
    assert r.missing == []


def test_optional_lines_do_not_count():
    optional = LineNutrition("Deko", 50, per100(kcal=900), optional=True)
    unknown_optional = LineNutrition("Chili", None, None, optional=True)
    r = recipe_nutrition([LINE_A, optional, unknown_optional], servings=1)
    assert r.total.kcal == approx(200)
    assert r.total_weight_g == approx(200)
    assert r.coverage == 1.0
    assert r.missing == []


def test_missing_values_and_coverage():
    no_amount = LineNutrition("B", None, per100(kcal=100))
    no_ingredient = LineNutrition("C", 80, None)
    r = recipe_nutrition([LINE_A, no_amount, no_ingredient], servings=1)
    assert r.coverage == approx(1 / 3)
    assert r.missing == ["B", "C"]
    # nur Zeile A in der Summe
    assert r.total.kcal == approx(200)
    assert r.total_weight_g == approx(200)


def test_line_without_kcal_counts_as_missing_but_keeps_other_values():
    water_like = LineNutrition("Mineral", 100, per100(carb_g=3))
    r = recipe_nutrition([LINE_A, water_like], servings=1)
    assert r.missing == ["Mineral"]
    assert r.coverage == approx(0.5)
    assert r.total.carb_g == approx(13)
    assert r.total_weight_g == approx(300)


def test_empty_recipe():
    r = recipe_nutrition([], servings=4)
    assert r.coverage == 0.0
    assert r.total_weight_g == 0
    assert r.serving_weight_g == 0
    assert r.energy_density_kcal_per_100g is None
    assert r.total.kcal == 0
    assert r.missing == []


def test_only_optional_lines_gives_zero_coverage():
    r = recipe_nutrition([LineNutrition("x", 10, per100(kcal=10), optional=True)], servings=1)
    assert r.coverage == 0.0


@pytest.mark.parametrize("servings", [0, -1])
def test_invalid_servings(servings):
    with pytest.raises(ValueError):
        recipe_nutrition([LINE_A], servings=servings)


def test_negative_grams_rejected():
    with pytest.raises(ValueError):
        recipe_nutrition([LineNutrition("A", -5, per100(kcal=10))], servings=1)


def test_recipe_salt_from_sodium():
    line = LineNutrition("Brühe", 200, per100(kcal=5, micros={"sodium_mg": 400}))
    r = recipe_nutrition([line], servings=2)
    assert r.total.salt_g == approx(2.0)
    assert r.per_serving.salt_g == approx(1.0)


def test_fractional_servings():
    r = recipe_nutrition([LINE_A], servings=0.5)
    assert r.per_serving.kcal == approx(400)
    assert r.serving_weight_g == approx(400)


# ---------------------------------------------------------------------------
# Sättigung
# ---------------------------------------------------------------------------


def _soup():
    return recipe_nutrition(
        [
            LineNutrition("Gemüse", 300, per100(kcal=30, protein_g=2, fiber_g=3)),
            LineNutrition("Linsen", 50, per100(kcal=300, protein_g=24, fiber_g=10)),
            LineNutrition("Brühe", 350, per100(kcal=3)),
        ],
        servings=1,
    )


def _pizza():
    return recipe_nutrition([LineNutrition("Pizza", 300, per100(kcal=270, protein_g=11, fiber_g=2.3))], 1)


def test_satiety_soup_beats_pizza():
    soup = satiety_score(_soup(), warm=True)
    pizza = satiety_score(_pizza(), warm=True)
    assert soup.score > pizza.score + 40
    # Suppe: 250,5 kcal auf 700 g (≈ 36 kcal/100 g) → Dichte und Volumen voll, Ballaststoffe 5,6 g/100 kcal
    assert soup.parts["density"] == 1.0
    assert soup.parts["volume"] == 1.0
    assert soup.parts["fiber"] == 1.0
    assert soup.parts["protein"] == approx((18 / 250.5 * 100 - 2) / 6)
    # Pizza: 270 kcal/100 g (≥ 250) → Dichte 0; 300 g → (300 − 200) / 300 Volumen
    assert pizza.parts["density"] == 0.0
    assert pizza.parts["volume"] == approx(1 / 3)


def test_satiety_perfect_and_worst():
    best = recipe_nutrition([LineNutrition("x", 600, per100(kcal=10, protein_g=10, fiber_g=5))], 1)
    # 60 kcal je Portion; Protein 60 g/100 kcal, Ballaststoffe 50 g/100 kcal: alles weit über "gut"
    s = satiety_score(best, warm=True)
    assert s.score == approx(100)
    assert set(s.parts) == {"density", "volume", "protein", "fiber", "warm"}
    worst = recipe_nutrition([LineNutrition("y", 50, per100(kcal=500))], 1)
    assert satiety_score(worst, warm=False).score == approx(0)


def test_satiety_warm_bonus():
    cold = satiety_score(_soup(), warm=False)
    warm = satiety_score(_soup(), warm=True)
    assert cold.parts["warm"] == 0.0
    assert warm.parts["warm"] == 1.0
    assert warm.score - cold.score == approx(10)  # Standardgewicht 0,10


def test_satiety_density_midpoint():
    # (250 + 60) / 2 = 155 kcal/100 g → Teilwert 0,5
    r = recipe_nutrition([LineNutrition("x", 100, per100(kcal=155))], 1)
    assert satiety_score(r).parts["density"] == approx(0.5)


def test_satiety_custom_weights_override_and_normalize():
    s = satiety_score(_pizza(), weights={"density": 1, "volume": 0, "protein": 0, "fiber": 0, "warm": 0})
    assert s.score == approx(0.0)  # nur Dichte zählt, und die ist 0
    v = satiety_score(_soup(), weights={"density": 0, "volume": 2, "protein": 0, "fiber": 0, "warm": 0})
    assert v.score == approx(100)  # Gewicht wird normalisiert
    # nur "warm" überschrieben: andere Standardgewichte bleiben und werden normalisiert
    no_warm = satiety_score(_soup(), warm=True, weights={"warm": 0})
    default_cold = satiety_score(_soup(), warm=False)
    assert no_warm.score == approx(default_cold.score / 0.9)


def test_satiety_invalid_weights():
    with pytest.raises(ValueError):
        satiety_score(_soup(), weights={"density": -1})
    with pytest.raises(ValueError):
        satiety_score(_soup(), weights={"unbekannt": 1})
    with pytest.raises(ValueError):
        satiety_score(_soup(), weights={"density": 0, "volume": 0, "protein": 0, "fiber": 0, "warm": 0})


def test_satiety_unknown_density_is_neutral():
    empty = recipe_nutrition([], servings=1)
    s = satiety_score(empty)
    assert s.parts["density"] == 0.5
    assert s.parts["volume"] == 0.0
    assert s.parts["protein"] == 0.0  # keine kcal → keine Division durch 0


# ---------------------------------------------------------------------------
# Passung ins Slot-Ziel
# ---------------------------------------------------------------------------

SERVING = Nutrients(kcal=400, protein_g=20, fat_g=15, carb_g=50, fiber_g=5, salt_g=1.0, micros={"zinc_mg": 2})
TARGET_1_5 = SlotTarget(kcal=600, protein_g=30, fat_g=22.5, carb_g=75)


def test_fit_perfect_after_scaling():
    fit = fit_to_target(SERVING, 300, TARGET_1_5)
    assert fit.unclamped_factor == approx(1.5)
    assert fit.factor == approx(1.5)
    assert fit.grams == approx(450)
    assert fit.scaled.kcal == approx(600)
    assert fit.scaled.protein_g == approx(30)
    assert fit.scaled.fat_g == approx(22.5)
    assert fit.scaled.carb_g == approx(75)
    assert fit.scaled.fiber_g == approx(7.5)
    assert fit.scaled.salt_g == approx(1.5)
    assert fit.scaled.micros == {"zinc_mg": approx(3)}
    for macro in ("kcal", "protein", "fat", "carb"):
        assert fit.deviation_pct[macro] == approx(0, abs=1e-9)
    assert fit.fit_score == approx(100)
    assert fit.notes == []


def test_fit_clamped_to_max():
    small = Nutrients(kcal=200, protein_g=10, fat_g=5, carb_g=25)
    fit = fit_to_target(small, 250, SlotTarget(600, 30, 15, 75))
    assert fit.unclamped_factor == approx(3.0)
    assert fit.factor == approx(2.0)
    assert fit.grams == approx(500)
    assert fit.scaled.kcal == approx(400)
    assert fit.deviation_pct["kcal"] == approx(-100 / 3)
    assert "Portion wäre 3-fach: sehr groß" in fit.notes
    assert "Ziel-kcal wird mit maximal 2-facher Portion nicht erreicht" in fit.notes


def test_fit_clamped_to_min():
    big = Nutrients(kcal=1000, protein_g=50, fat_g=40, carb_g=100)
    fit = fit_to_target(big, 500, SlotTarget(300, 25, 12, 40))
    assert fit.unclamped_factor == approx(0.3)
    assert fit.factor == approx(0.5)
    assert fit.grams == approx(250)
    assert fit.deviation_pct["kcal"] == approx(500 / 300 * 100 - 100)
    assert "Portion wäre 0,3-fach: sehr klein" in fit.notes
    assert any("überschritten" in n for n in fit.notes)


def test_fit_custom_factor_limits():
    small = Nutrients(kcal=200)
    fit = fit_to_target(small, 100, SlotTarget(600, 0, 0, 0), min_factor=0.8, max_factor=2.5)
    assert fit.factor == approx(2.5)
    assert "Ziel-kcal wird mit maximal 2,5-facher Portion nicht erreicht" in fit.notes


def test_fit_invalid_limits():
    with pytest.raises(ValueError):
        fit_to_target(SERVING, 100, TARGET_1_5, min_factor=2.0, max_factor=1.0)
    with pytest.raises(ValueError):
        fit_to_target(SERVING, 100, TARGET_1_5, min_factor=0.0)


def test_fit_size_notes_only_beyond_thresholds():
    # Faktor 1,5 und 0,7 genau: keine Größenhinweise
    assert fit_to_target(SERVING, 300, SlotTarget(600, 30, 22.5, 75)).notes == []
    low = fit_to_target(SERVING, 300, SlotTarget(280, 14, 10.5, 35))
    assert low.unclamped_factor == approx(0.7)
    assert low.notes == []
    assert (
        "Portion wäre 1,8-fach: sehr groß" in fit_to_target(SERVING, 300, SlotTarget(720, 36, 27, 90)).notes
    )


def test_fit_deviations_in_percent():
    # Faktor 1 (kcal passt): Protein 20 vs 25 = -20 %, Fett 15 vs 12 = +25 %, Kohlenhydrate 50 vs 40 = +25 %
    fit = fit_to_target(SERVING, 300, SlotTarget(400, 25, 12, 40))
    assert fit.factor == approx(1.0)
    assert fit.deviation_pct["kcal"] == approx(0, abs=1e-9)
    assert fit.deviation_pct["protein"] == approx(-20)
    assert fit.deviation_pct["fat"] == approx(25)
    assert fit.deviation_pct["carb"] == approx(25)


def test_fit_protein_asymmetry():
    target = SlotTarget(kcal=500, protein_g=50, fat_g=20, carb_g=50)
    under = Nutrients(kcal=500, protein_g=40, fat_g=20, carb_g=50)  # -20 % → zählt wie 30 %
    over = Nutrients(kcal=500, protein_g=60, fat_g=20, carb_g=50)  # +20 %
    fit_under = fit_to_target(under, 300, target)
    fit_over = fit_to_target(over, 300, target)
    # Protein-Teilwert: 1 − (30 − 10) / 50 = 0,6 bzw. 1 − (20 − 10) / 50 = 0,8; Gewicht 0,4, Rest voll
    assert fit_under.fit_score == approx(100 - 0.4 * 0.4 * 100)
    assert fit_over.fit_score == approx(100 - 0.4 * 0.2 * 100)
    assert fit_under.fit_score < fit_over.fit_score


def test_fit_score_zero_and_tolerance():
    target = SlotTarget(kcal=500, protein_g=50, fat_g=20, carb_g=50)
    # genau 10 % Abweichung (Fett +10 %) → noch voller Score
    edge = Nutrients(kcal=500, protein_g=50, fat_g=22, carb_g=50)
    assert fit_to_target(edge, 300, target).fit_score == approx(100)
    # Fett +60 % (= FIT_ZERO_PCT) → Teilwert 0, Gewicht 0,15
    far = Nutrients(kcal=500, protein_g=50, fat_g=32, carb_g=50)
    assert fit_to_target(far, 300, target).fit_score == approx(85)


def test_fit_custom_weights():
    target = SlotTarget(kcal=500, protein_g=50, fat_g=20, carb_g=50)
    low_protein = Nutrients(kcal=500, protein_g=10, fat_g=20, carb_g=50)  # -80 % → Teilwert 0
    only_kcal = fit_to_target(
        low_protein, 300, target, weights={"kcal": 1, "protein": 0, "fat": 0, "carb": 0}
    )
    assert only_kcal.fit_score == approx(100)
    only_protein = fit_to_target(
        low_protein, 300, target, weights={"kcal": 0, "protein": 1, "fat": 0, "carb": 0}
    )
    assert only_protein.fit_score == approx(0)
    with pytest.raises(ValueError):
        fit_to_target(low_protein, 300, target, weights={"zinc": 1})


def test_fit_protein_deficit_note():
    # Faktor 1, Protein 28 statt 50 g
    target = SlotTarget(kcal=500, protein_g=50, fat_g=20, carb_g=50)
    fit = fit_to_target(Nutrients(kcal=500, protein_g=28, fat_g=20, carb_g=50), 300, target)
    assert "Protein 22 g unter Ziel" in fit.notes
    over = fit_to_target(Nutrients(kcal=500, protein_g=60, fat_g=20, carb_g=50), 300, target)
    assert not any("Protein" in n for n in over.notes)


def test_fit_fat_and_carb_over_notes():
    target = SlotTarget(kcal=500, protein_g=50, fat_g=20, carb_g=50)
    fit = fit_to_target(Nutrients(kcal=500, protein_g=50, fat_g=30, carb_g=70), 300, target)
    assert "Fett deutlich über Ziel (+50 %)" in fit.notes
    assert "Kohlenhydrate deutlich über Ziel (+40 %)" in fit.notes
    # +30 % genau löst noch keinen Hinweis aus
    edge = fit_to_target(Nutrients(kcal=500, protein_g=50, fat_g=26, carb_g=65), 300, target)
    assert edge.notes == []


def test_fit_target_zero_kcal():
    fit = fit_to_target(SERVING, 300, SlotTarget(0, 0, 0, 0))
    assert fit.factor == 1.0
    assert fit.unclamped_factor == 1.0
    assert fit.grams == approx(300)
    assert fit.deviation_pct == {"kcal": 100.0, "protein": 100.0, "fat": 100.0, "carb": 100.0}
    assert any("kein Kalorienziel" in n for n in fit.notes)
    assert not any("sehr groß" in n or "sehr klein" in n for n in fit.notes)


def test_fit_serving_without_kcal():
    fit = fit_to_target(Nutrients(), 0, SlotTarget(500, 30, 15, 60))
    assert fit.factor == 1.0
    assert fit.deviation_pct == {"kcal": -100.0, "protein": -100.0, "fat": -100.0, "carb": -100.0}
    assert fit.fit_score == approx(0)
    assert any("keine Kalorien bekannt" in n for n in fit.notes)
    assert any("Protein 30 g unter Ziel" in n for n in fit.notes)


def test_fit_everything_zero():
    fit = fit_to_target(Nutrients(), 0, SlotTarget(0, 0, 0, 0))
    assert fit.deviation_pct == {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
    assert fit.fit_score == approx(100)


# ---------------------------------------------------------------------------
# Baukasten
# ---------------------------------------------------------------------------


def test_component_meal_sums_including_salt():
    egg = ComponentChoice(
        "Ei", 120, per100(kcal=150, protein_g=12.5, fat_g=10, carb_g=1, micros={"sodium_mg": 140})
    )
    skyr = ComponentChoice("Skyr", 200, per100(kcal=63, protein_g=11, fat_g=0.2, carb_g=4, salt_g=0.1))
    r = component_meal([egg, skyr])
    assert r.servings == 1
    assert r.total.kcal == approx(180 + 126)
    assert r.total.protein_g == approx(15 + 22)
    assert r.total.fat_g == approx(12 + 0.4)
    # Salz: Ei 140 mg Natrium × 2,5 / 1000 = 0,35 g je 100 g → 0,42 g; Skyr 0,2 g
    assert r.total.salt_g == approx(0.62)
    assert r.per_serving.kcal == approx(r.total.kcal)
    assert r.total_weight_g == approx(320)
    assert r.serving_weight_g == approx(320)
    assert r.energy_density_kcal_per_100g == approx(306 / 320 * 100)
    assert r.coverage == 1.0
    assert r.missing == []


def test_component_meal_missing_kcal():
    ok = ComponentChoice("Haferflocken", 50, per100(kcal=370, protein_g=13))
    unknown = ComponentChoice("Mystery", 30, per100(protein_g=5))
    r = component_meal([ok, unknown])
    assert r.missing == ["Mystery"]
    assert r.coverage == approx(0.5)
    assert r.total.kcal == approx(185)


def test_component_meal_empty():
    r = component_meal([])
    assert r.coverage == 0.0
    assert r.total_weight_g == 0
    assert r.energy_density_kcal_per_100g is None
