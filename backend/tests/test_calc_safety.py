"""Tests für calc/safety.py (nur erfundene Daten)."""

import pytest

from app.calc.macros import daily_target
from app.calc.safety import CurrentBody, apply_safety_limits, kcal_floor, max_rate_kg_per_week
from app.calc.types import DayTarget, GoalSpec, PersonProfile, PersonSettings

MAN = PersonProfile(sex="m", age_years=34, height_cm=190, weight_kg=78)
WOMAN = PersonProfile(sex="f", age_years=30, height_cm=174, weight_kg=78)
DEFAULTS = PersonSettings()


def man_target(rate: float, tdee: float = 2750, settings: PersonSettings = DEFAULTS) -> DayTarget:
    return daily_target(MAN, GoalSpec("lose", rate_kg_per_week=rate), tdee, settings)


def codes(result) -> list[str]:
    return [w.code for w in result.warnings]


def energy_of(t: DayTarget) -> float:
    return 4 * t.protein_g + 4 * t.carb_g + 9 * t.fat_g


def test_unchanged_target_without_warnings():
    t = man_target(0.5)
    r = apply_safety_limits(t, MAN, DEFAULTS, CurrentBody(78.0), requested_rate_kg_per_week=0.5)
    assert r.target == t
    assert r.warnings == []
    assert r.applied_rate_kg_per_week == pytest.approx(0.5)


def test_without_requested_rate_only_floors_apply():
    t = man_target(0.5)
    r = apply_safety_limits(t, MAN, DEFAULTS, CurrentBody(78.0))
    assert r.target == t
    assert r.applied_rate_kg_per_week is None


def test_default_floors():
    # Mann: BMR 1802,5 > 1500; Frau: BMR 1556,5 > 1200
    assert kcal_floor(MAN, DEFAULTS, 78) == pytest.approx(1802.5)
    assert kcal_floor(WOMAN, DEFAULTS, 78) == pytest.approx(1556.5)
    # sehr leichte, kleine Person: absolute Grenze gewinnt
    small = PersonProfile(sex="f", age_years=60, height_cm=150, weight_kg=40)
    assert kcal_floor(small, DEFAULTS, 40) == pytest.approx(1200.0)
    assert kcal_floor(MAN, PersonSettings(kcal_floor=2000), 78) == 2000
    # Maximaltempo: min(1 kg, 1 % des Gewichts)
    assert max_rate_kg_per_week(DEFAULTS, 78) == pytest.approx(0.78)
    assert max_rate_kg_per_week(DEFAULTS, 120) == pytest.approx(1.0)
    assert max_rate_kg_per_week(PersonSettings(max_rate_kg_per_week=0.3), 78) == pytest.approx(0.3)


def test_rate_is_capped_and_energy_recomputed():
    s = PersonSettings(kcal_floor=1000)  # Energiegrenze soll hier nicht greifen
    t = man_target(1.5, settings=s)  # 2750 - 1650 = 1100 kcal
    r = apply_safety_limits(t, MAN, s, CurrentBody(78.0), requested_rate_kg_per_week=1.5)
    assert r.applied_rate_kg_per_week == pytest.approx(0.78)
    assert "rate_capped" in codes(r)
    # entspricht dem Ziel bei Tempo 0,78 und gleichem Bedarf
    expected = man_target(0.78, settings=s)
    assert r.target.kcal == pytest.approx(expected.kcal, abs=1)
    assert r.target.protein_g == pytest.approx(expected.protein_g)
    assert abs(r.target.kcal - energy_of(r.target)) < 2


def test_custom_max_rate():
    s = PersonSettings(max_rate_kg_per_week=0.3)
    r = apply_safety_limits(man_target(0.5), MAN, s, CurrentBody(78.0), requested_rate_kg_per_week=0.5)
    assert r.applied_rate_kg_per_week == pytest.approx(0.3)
    assert r.target.kcal == pytest.approx(2750 - 0.3 * 1100, abs=1)


def test_kcal_floor_kicks_in_for_extreme_rate():
    s = PersonSettings(max_rate_kg_per_week=2.0)
    t = man_target(1.0, tdee=2200, settings=s)  # 2200 - 1100 = 1100 kcal
    assert t.kcal == 1100
    r = apply_safety_limits(t, MAN, s, CurrentBody(78.0), requested_rate_kg_per_week=1.0)
    assert r.target.kcal == 1803  # aufgerundet auf BMR 1802,5
    assert "kcal_floor" in codes(r)
    kcal_warning = next(w for w in r.warnings if w.code == "kcal_floor")
    assert kcal_warning.severity == "block"
    assert "1803" in kcal_warning.message
    # das tatsächlich erreichte Tempo sinkt entsprechend
    assert r.applied_rate_kg_per_week == pytest.approx(1.0 - (1803 - 1100) * 7 / 7700)
    assert r.target.protein_g == pytest.approx(t.protein_g)
    assert abs(r.target.kcal - energy_of(r.target)) < 2


def test_kcal_floor_for_woman_uses_bmr_not_absolute():
    s = PersonSettings(max_rate_kg_per_week=2.0)
    t = daily_target(WOMAN, GoalSpec("lose", rate_kg_per_week=1.0), 2300, s)  # 1200 kcal
    r = apply_safety_limits(t, WOMAN, s, CurrentBody(78.0), requested_rate_kg_per_week=1.0)
    assert r.target.kcal == 1557


def test_protein_floor_raises_protein_keeps_energy():
    t = DayTarget(kcal=2000, protein_g=60.0, fat_g=66.7, carb_g=290.0)
    r = apply_safety_limits(t, MAN, DEFAULTS, CurrentBody(78.0))
    assert r.target.protein_g == pytest.approx(1.2 * 78, abs=0.1)
    assert r.target.kcal == 2000
    assert r.target.carb_g < t.carb_g
    assert "protein_floor" in codes(r)
    assert abs(r.target.kcal - energy_of(r.target)) < 2


def test_taper_near_weight_floor():
    s = PersonSettings(weight_floor_kg=70.0)
    t = man_target(0.5, settings=s)
    r = apply_safety_limits(t, MAN, s, CurrentBody(71.0), requested_rate_kg_per_week=0.5)
    # 1 kg über der Grenze bei 3 kg Auslauf: Faktor 1/3
    assert r.applied_rate_kg_per_week == pytest.approx(0.5 / 3)
    assert "rate_tapered" in codes(r)
    assert "floor_reached" not in codes(r)
    assert r.target.kcal == pytest.approx(2750 - 0.5 / 3 * 1100, abs=1)


def test_no_taper_far_from_weight_floor():
    s = PersonSettings(weight_floor_kg=70.0)
    r = apply_safety_limits(man_target(0.5), MAN, s, CurrentBody(75.0), requested_rate_kg_per_week=0.5)
    assert r.applied_rate_kg_per_week == pytest.approx(0.5)
    assert r.warnings == []


@pytest.mark.parametrize("weight", [70.0, 69.0])
def test_rate_zero_at_or_below_weight_floor(weight):
    s = PersonSettings(weight_floor_kg=70.0)
    r = apply_safety_limits(man_target(0.5), MAN, s, CurrentBody(weight), requested_rate_kg_per_week=0.5)
    assert r.applied_rate_kg_per_week == 0.0
    assert "floor_reached" in codes(r)
    assert r.target.kcal == 2750  # Erhaltung
    warning = next(w for w in r.warnings if w.code == "floor_reached")
    assert warning.severity == "block"


def test_taper_by_body_fat_stricter_wins():
    s = PersonSettings(weight_floor_kg=70.0, bf_floor_pct=12.0)
    # Gewicht weit weg (Faktor 1), Körperfett 1 Punkt über der Grenze bei 2 Punkten Auslauf: 0,5
    r = apply_safety_limits(
        man_target(0.5), MAN, s, CurrentBody(78.0, body_fat_pct=13.0), requested_rate_kg_per_week=0.5
    )
    assert r.applied_rate_kg_per_week == pytest.approx(0.25)
    assert "Körperfett" in next(w for w in r.warnings if w.code == "rate_tapered").message
    # Gewicht strenger (Faktor 1/3) als Körperfett (0,5)
    r2 = apply_safety_limits(
        man_target(0.5), MAN, s, CurrentBody(71.0, body_fat_pct=13.0), requested_rate_kg_per_week=0.5
    )
    assert r2.applied_rate_kg_per_week == pytest.approx(0.5 / 3)


def test_body_fat_at_floor_stops_loss():
    s = PersonSettings(bf_floor_pct=12.0)
    r = apply_safety_limits(
        man_target(0.5), MAN, s, CurrentBody(78.0, body_fat_pct=12.0), requested_rate_kg_per_week=0.5
    )
    assert r.applied_rate_kg_per_week == 0.0
    assert "floor_reached" in codes(r)


def test_implausible_weight_floor_warns_but_still_applies():
    s = PersonSettings(weight_floor_kg=70.0)
    r = apply_safety_limits(
        man_target(0.5),
        MAN,
        s,
        CurrentBody(71.0, body_fat_pct=None, lean_mass_kg=69.6),
        requested_rate_kg_per_week=0.5,
    )
    assert "implausible_weight_floor" in codes(r)
    warning = next(w for w in r.warnings if w.code == "implausible_weight_floor")
    assert warning.severity == "warn"
    # die Grenze wirkt trotzdem
    assert r.applied_rate_kg_per_week == pytest.approx(0.5 / 3)
    assert "rate_tapered" in codes(r)


def test_implausible_floor_derived_from_body_fat():
    s = PersonSettings(weight_floor_kg=70.0)
    r = apply_safety_limits(man_target(0.5), MAN, s, CurrentBody(78.0, body_fat_pct=10.0))
    assert "implausible_weight_floor" in codes(r)  # Magermasse 70,2 kg > Grenze


def test_plausible_weight_floor_has_no_hint():
    s = PersonSettings(weight_floor_kg=70.0)
    r = apply_safety_limits(man_target(0.5), MAN, s, CurrentBody(78.0, lean_mass_kg=62.0))
    assert "implausible_weight_floor" not in codes(r)


def test_bf_hint_only_without_own_floor_and_never_blocks():
    t = man_target(0.5)
    r = apply_safety_limits(
        t, MAN, DEFAULTS, CurrentBody(78.0, body_fat_pct=8.0), requested_rate_kg_per_week=0.5
    )
    hint = next(w for w in r.warnings if w.code == "bf_hint")
    assert hint.severity == "info"
    assert r.applied_rate_kg_per_week == pytest.approx(0.5)
    assert r.target == t

    own = PersonSettings(bf_floor_pct=6.0)
    r2 = apply_safety_limits(t, MAN, own, CurrentBody(78.0, body_fat_pct=8.0), requested_rate_kg_per_week=0.5)
    assert "bf_hint" not in codes(r2)

    r3 = apply_safety_limits(t, MAN, DEFAULTS, CurrentBody(78.0, body_fat_pct=15.0))
    assert "bf_hint" not in codes(r3)

    # Frauen-Richtwert liegt bei 18 %
    wt = daily_target(WOMAN, GoalSpec("lose", rate_kg_per_week=0.4), 2900, DEFAULTS)
    r4 = apply_safety_limits(wt, WOMAN, DEFAULTS, CurrentBody(78.0, body_fat_pct=17.0))
    assert "bf_hint" in codes(r4)


def test_gain_rate_capped_reduces_energy_and_is_not_tapered():
    s = PersonSettings(weight_floor_kg=77.9)  # darf bei Zunahme keinen Auslauf auslösen
    t = daily_target(MAN, GoalSpec("gain", rate_kg_per_week=1.5), 2750, s)  # 2750 + 1650
    r = apply_safety_limits(t, MAN, s, CurrentBody(78.0), requested_rate_kg_per_week=1.5, goal_kind="gain")
    assert r.applied_rate_kg_per_week == pytest.approx(0.78)
    assert r.target.kcal == pytest.approx(2750 + 0.78 * 1100, abs=1)
    assert "floor_reached" not in codes(r)


def test_maintain_leaves_rate_alone():
    t = daily_target(MAN, GoalSpec("maintain"), 2750, DEFAULTS)
    r = apply_safety_limits(
        t, MAN, DEFAULTS, CurrentBody(78.0), requested_rate_kg_per_week=0.5, goal_kind="maintain"
    )
    assert r.target == t
    assert r.applied_rate_kg_per_week is None


def test_day_type_is_preserved():
    t = DayTarget(kcal=1000, protein_g=60, fat_g=30, carb_g=122.5, day_type="hard")
    r = apply_safety_limits(t, MAN, DEFAULTS, CurrentBody(78.0))
    assert r.target.day_type == "hard"
    assert r.target.kcal == 1803


def test_messages_are_german_and_nonempty():
    s = PersonSettings(weight_floor_kg=70.0, max_rate_kg_per_week=2.0)
    r = apply_safety_limits(
        man_target(1.0, tdee=2200, settings=s),
        MAN,
        s,
        CurrentBody(70.5, body_fat_pct=8.0, lean_mass_kg=69.6),
        requested_rate_kg_per_week=1.0,
    )
    assert {"rate_tapered", "implausible_weight_floor", "bf_hint"} <= set(codes(r))
    assert all(len(w.message) > 20 for w in r.warnings)
