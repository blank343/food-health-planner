"""Tests für calc/slots.py (nur erfundene Daten)."""

import pytest

from app.calc.slots import distribute_to_slots, single_meal_check
from app.calc.types import DayTarget, PersonSettings, SlotTarget

DAY = DayTarget(kcal=2200, protein_g=156.0, fat_g=73.3, carb_g=229.1)


def assert_sums(day: DayTarget, slots: dict[str, SlotTarget]) -> None:
    assert sum(s.kcal for s in slots.values()) == pytest.approx(day.kcal, abs=1e-9)
    assert sum(s.protein_g for s in slots.values()) == pytest.approx(day.protein_g, abs=1e-9)
    assert sum(s.fat_g for s in slots.values()) == pytest.approx(day.fat_g, abs=1e-9)
    assert sum(s.carb_g for s in slots.values()) == pytest.approx(day.carb_g, abs=1e-9)


def test_default_shares_sum_exactly():
    slots = distribute_to_slots(DAY, {"breakfast": 0.3, "lunch": 0.3, "dinner": 0.4})
    assert list(slots) == ["breakfast", "lunch", "dinner"]
    assert slots["breakfast"].kcal == 660
    assert slots["dinner"].kcal == 880
    assert slots["dinner"].protein_g == pytest.approx(62.4)
    assert_sums(DAY, slots)


def test_shares_are_normalised():
    a = distribute_to_slots(DAY, {"a": 3, "b": 3, "c": 4})
    b = distribute_to_slots(DAY, {"a": 0.3, "b": 0.3, "c": 0.4})
    assert a == b


def test_rounding_remainder_goes_to_largest_slot():
    day = DayTarget(kcal=2000, protein_g=100.0, fat_g=60.0, carb_g=265.0)
    slots = distribute_to_slots(day, {"a": 1, "b": 1, "c": 1, "d": 2})
    assert_sums(day, slots)
    # 2000/5 x (1, 1, 1, 2) = 400, 400, 400, 800: ohne Rest; mit ungeraden Werten:
    odd = DayTarget(kcal=2001, protein_g=100.1, fat_g=60.3, carb_g=265.7)
    s2 = distribute_to_slots(odd, {"a": 1, "b": 1, "c": 1, "d": 2})
    assert_sums(odd, s2)
    assert all(s.kcal == round(s.kcal) for s in s2.values())
    assert all(round(s.protein_g, 1) == s.protein_g for s in s2.values())
    # drei gleiche Slots bei 1000 kcal: 333/333/334, der Rest geht an den ersten größten
    third = distribute_to_slots(DayTarget(1000, 90.0, 30.0, 100.0), {"x": 1, "y": 1, "z": 1})
    assert sorted(s.kcal for s in third.values()) == [333, 333, 334]


@pytest.mark.parametrize("kcal", [1503, 1999, 2234, 2761, 3100])
def test_sums_exact_for_many_values(kcal):
    day = DayTarget(kcal=kcal, protein_g=kcal / 14.1, fat_g=kcal / 31.7, carb_g=kcal / 9.3)
    day = DayTarget(day.kcal, round(day.protein_g, 1), round(day.fat_g, 1), round(day.carb_g, 1))
    slots = distribute_to_slots(day, {"b": 0.25, "l": 0.35, "d": 0.3, "s": 0.1})
    assert_sums(day, slots)


def test_zero_share_slot_returns_zeros():
    slots = distribute_to_slots(DAY, {"breakfast": 0.0, "lunch": 0.5, "dinner": 0.5})
    assert slots["breakfast"] == SlotTarget(0.0, 0.0, 0.0, 0.0)
    assert_sums(DAY, slots)


def test_invalid_shares_raise():
    with pytest.raises(ValueError):
        distribute_to_slots(DAY, {"a": 0.0, "b": 0.0})
    with pytest.raises(ValueError):
        distribute_to_slots(DAY, {"a": -1.0, "b": 2.0})


def test_single_meal_kcal_limit():
    big = SlotTarget(kcal=1100, protein_g=60, fat_g=40, carb_g=130)
    assert single_meal_check(big, PersonSettings()) == []  # keine Obergrenze gesetzt
    limits = PersonSettings(single_meal_max_kcal=900)
    ws = single_meal_check(big, limits)
    assert [w.code for w in ws] == ["meal_too_large"]
    assert ws[0].severity == "warn"
    assert "900" in ws[0].message
    assert single_meal_check(SlotTarget(900, 50, 30, 100), limits) == []


def test_single_meal_protein_minimum():
    meal = SlotTarget(kcal=600, protein_g=15, fat_g=20, carb_g=80)
    assert single_meal_check(meal, PersonSettings()) == []
    ws = single_meal_check(meal, PersonSettings(), protein_floor_g=25)
    assert [w.code for w in ws] == ["meal_protein_low"]
    assert single_meal_check(meal, PersonSettings(), protein_floor_g=15) == []


def test_single_meal_both_warnings():
    meal = SlotTarget(kcal=1200, protein_g=10, fat_g=50, carb_g=150)
    ws = single_meal_check(meal, PersonSettings(single_meal_max_kcal=1000), protein_floor_g=30)
    assert {w.code for w in ws} == {"meal_too_large", "meal_protein_low"}
