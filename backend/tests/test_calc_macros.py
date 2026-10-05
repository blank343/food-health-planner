"""Tests für calc/macros.py (nur erfundene Daten)."""

import pytest

from app.calc.macros import (
    compose_day_target,
    daily_target,
    energy_delta_kcal,
    implied_rate_kg_per_week,
    weekly_targets,
)
from app.calc.types import DayTarget, GoalSpec, PersonProfile, PersonSettings

MAN = PersonProfile(sex="m", age_years=34, height_cm=190, weight_kg=78)
WOMAN = PersonProfile(sex="f", age_years=30, height_cm=174, weight_kg=78)
SETTINGS = PersonSettings()


def energy_of(t: DayTarget) -> float:
    return 4 * t.protein_g + 4 * t.carb_g + 9 * t.fat_g


def test_man_lose_half_kg_per_week():
    t = daily_target(MAN, GoalSpec("lose", rate_kg_per_week=0.5), 2750, SETTINGS)
    assert t.kcal == 2200
    assert t.protein_g == pytest.approx(156.0)  # 2,0 g/kg x 78 kg
    assert t.fat_g == pytest.approx(73.3)  # 30 % von 2200 kcal / 9
    assert t.carb_g == pytest.approx(229.0, abs=0.2)
    assert abs(t.kcal - energy_of(t)) < 2
    assert t.day_type == "easy"


def test_woman_lose_point_four():
    t = daily_target(WOMAN, GoalSpec("lose", rate_kg_per_week=0.4), 2900, SETTINGS)
    assert t.kcal == pytest.approx(2900 - 0.4 * 7700 / 7)  # 2460
    assert t.protein_g == pytest.approx(156.0)
    assert t.fat_g == pytest.approx(0.3 * 2460 / 9, abs=0.1)
    assert abs(t.kcal - energy_of(t)) < 2


def test_gain_and_maintain_defaults():
    gain = daily_target(MAN, GoalSpec("gain", rate_kg_per_week=0.25), 2750, SETTINGS)
    assert gain.kcal == pytest.approx(2750 + 0.25 * 7700 / 7, abs=1)
    assert gain.protein_g == pytest.approx(1.8 * 78, abs=0.1)
    keep = daily_target(MAN, GoalSpec("maintain"), 2750, SETTINGS)
    assert keep.kcal == 2750
    assert keep.protein_g == pytest.approx(1.6 * 78, abs=0.1)
    assert abs(keep.kcal - energy_of(keep)) < 2


def test_maintain_ignores_rate_and_modifier():
    t = daily_target(MAN, GoalSpec("maintain", rate_kg_per_week=0.5, kcal_modifier_pct=-10), 2750, SETTINGS)
    assert t.kcal == 2750


def test_modifier_pct_used_without_rate():
    t = daily_target(MAN, GoalSpec("lose", kcal_modifier_pct=-10), 2750, SETTINGS)
    assert t.kcal == pytest.approx(2475)
    # Tempo hat Vorrang
    t2 = daily_target(MAN, GoalSpec("lose", rate_kg_per_week=0.5, kcal_modifier_pct=-10), 2750, SETTINGS)
    assert t2.kcal == 2200
    # Vorzeichen folgt der Art des Ziels
    t3 = daily_target(MAN, GoalSpec("lose", kcal_modifier_pct=10), 2750, SETTINGS)
    assert t3.kcal == pytest.approx(2475)


def test_goal_overrides_for_protein_and_fat():
    goal = GoalSpec("lose", rate_kg_per_week=0.5, protein_g_per_kg=2.2, fat_pct=25)
    t = daily_target(MAN, goal, 2750, SETTINGS)
    assert t.protein_g == pytest.approx(171.6)
    assert t.fat_g == pytest.approx(0.25 * 2200 / 9, abs=0.1)


def test_custom_kcal_per_kg_setting():
    s = PersonSettings(kcal_per_kg=7000)
    t = daily_target(MAN, GoalSpec("lose", rate_kg_per_week=0.5), 2750, s)
    assert t.kcal == pytest.approx(2750 - 500)


def test_carbs_never_negative_fat_reduced_first():
    # Sehr wenig Energie, viel Protein: Fett und nicht Protein wird gekürzt
    goal = GoalSpec("lose", rate_kg_per_week=1.0, protein_g_per_kg=3.0, fat_pct=40)
    t = daily_target(MAN, goal, 1800, SETTINGS)  # 1800 - 1100 = 700 kcal; Protein braucht 936 kcal
    assert t.carb_g >= 0
    assert t.protein_g <= 700 / 4
    assert abs(t.kcal - energy_of(t)) < 2

    goal2 = GoalSpec("lose", rate_kg_per_week=0.5, protein_g_per_kg=2.0, fat_pct=80)
    t2 = daily_target(MAN, goal2, 2750, SETTINGS)  # Fett 80 % + Protein 28 % > 100 %
    assert t2.protein_g == pytest.approx(156.0)
    assert t2.carb_g == 0
    assert t2.fat_g < 0.8 * 2200 / 9  # Fett wurde gekürzt
    assert abs(t2.kcal - energy_of(t2)) < 2


def test_compose_rounding_and_consistency():
    for kcal in (1500.4, 1999.5, 2234.7, 3010.2):
        t = compose_day_target(kcal, 143.37, 66.66)
        assert t.kcal == round(kcal)
        assert abs(t.kcal - energy_of(t)) < 2
        assert t.carb_g >= 0
        assert round(t.protein_g, 1) == t.protein_g


def test_energy_delta_and_implied_rate():
    goal = GoalSpec("lose", rate_kg_per_week=0.5)
    assert energy_delta_kcal(goal, 2750, 7700) == pytest.approx(-550)
    assert implied_rate_kg_per_week(goal, 2750, 7700) == pytest.approx(0.5)
    mod = GoalSpec("lose", kcal_modifier_pct=-20)
    assert implied_rate_kg_per_week(mod, 2750, 7700) == pytest.approx(550 * 7 / 7700)
    assert energy_delta_kcal(GoalSpec("lose"), 2750, 7700) == pytest.approx(-275)  # Standard -10 %
    assert energy_delta_kcal(GoalSpec("gain"), 2000, 7700) == pytest.approx(100)  # Standard +5 %


# --- Woche ---

WEEK = {0: "hard", 1: "easy", 2: "moderate", 3: "rest", 4: "hard", 5: "easy", 6: "rest"}


def test_weekly_keeps_weekly_sum():
    goal = GoalSpec("lose", rate_kg_per_week=0.5)
    days = weekly_targets(MAN, goal, 2750, SETTINGS, WEEK)
    assert len(days) == 7
    assert abs(sum(d.kcal for d in days) - 7 * 2200) <= 7
    assert [d.day_type for d in days] == [WEEK[i] for i in range(7)]


def test_weekly_protein_and_fat_constant_carbs_follow_energy():
    goal = GoalSpec("lose", rate_kg_per_week=0.5)
    days = weekly_targets(MAN, goal, 2750, SETTINGS, WEEK)
    assert {d.protein_g for d in days} == {156.0}
    assert len({d.fat_g for d in days}) == 1
    hard, rest = days[0], days[3]
    assert hard.kcal > days[1].kcal > rest.kcal
    assert hard.carb_g > rest.carb_g
    assert hard.kcal - rest.kcal == pytest.approx(2200 * (1.08 - 0.95) / 1.0, rel=0.05)
    for d in days:
        assert abs(d.kcal - energy_of(d)) < 2


def test_weekly_weights_are_normalised_to_mean_one():
    # Alle Tage gleich "hard": Gewicht 1,08 wird auf 1 normalisiert, die Energie bleibt gleich dem Tagesziel
    goal = GoalSpec("lose", rate_kg_per_week=0.5)
    days = weekly_targets(MAN, goal, 2750, SETTINGS, {i: "hard" for i in range(7)})
    assert {d.kcal for d in days} <= {2200.0}
    assert abs(sum(d.kcal for d in days) - 15400) <= 7


def test_weekly_missing_days_default_to_easy_and_custom_weights():
    goal = GoalSpec("maintain")
    s = PersonSettings(day_type_weights={"rest": 0.5, "easy": 1.0, "moderate": 1.0, "hard": 1.5})
    days = weekly_targets(MAN, goal, 2800, s, {0: "hard", 3: "rest"})
    assert days[1].day_type == "easy"
    assert abs(sum(d.kcal for d in days) - 7 * 2800) <= 7
    assert days[0].kcal > days[1].kcal > days[3].kcal
