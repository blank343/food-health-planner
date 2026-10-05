from datetime import date, timedelta

import pytest

from app.models import GoalProfile, HealthDaily, Person, PersonSettingsRow, TrainingPlanItem
from app.services.targets import TargetsUnavailable, compute_targets, parse_shares

MONDAY = date(2026, 10, 5)  # ein Montag
SATURDAY = date(2026, 10, 10)


@pytest.fixture
def person(session):
    p = Person(name="Test A", sex="m", birth_date=date(1992, 2, 21), height_cm=190.0)
    session.add(p)
    session.commit()
    return p


def _seed(session, p, *, days=40, weight0=80.0, slope=0.0, energy=True, end=MONDAY, bf=None):
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        kw = {"weight_kg": round(weight0 + slope * i, 2)}
        if bf is not None and i == days - 1:
            kw["body_fat_pct"] = bf
        if energy:
            kw.update(active_kcal=750.0, basal_kcal=2000.0)
        session.add(HealthDaily(person_id=p.id, day=d, source="hae_zip", **kw))
    session.commit()


def _goal(session, p, **kw):
    kw.setdefault("kind", "lose")
    kw.setdefault("valid_from", date(2026, 1, 1))
    session.add(GoalProfile(person_id=p.id, **kw))
    session.commit()


def _settings(session, p, **data):
    session.add(PersonSettingsRow(person_id=p.id, data=data))
    session.commit()


def test_lose_goal_gives_deficit_and_macros(session, person):
    _seed(session, person)
    _goal(session, person, rate_kg_per_week=0.5)
    r = compute_targets(session, person, MONDAY)
    assert r.tdee.method == "device" and r.tdee.tdee_kcal == pytest.approx(2750, abs=1)
    assert r.target.kcal == pytest.approx(2750 - 550, abs=5)
    assert r.target.protein_g == pytest.approx(160.0, abs=1)  # 2,0 g/kg × 80 kg
    assert 4 * r.target.protein_g + 4 * r.target.carb_g + 9 * r.target.fat_g == pytest.approx(
        r.target.kcal, abs=3
    )
    assert r.applied_rate_kg_per_week == pytest.approx(0.5)
    assert sum(s.kcal for s in r.slots.values()) == pytest.approx(r.target.kcal, abs=0.01)


def test_no_goal_maintains_with_hint(session, person):
    _seed(session, person)
    r = compute_targets(session, person, MONDAY)
    assert r.goal.kind == "maintain" and r.goal_from is None
    assert r.target.kcal == pytest.approx(2750, abs=5)
    assert "no_goal" in [w.code for w in r.warnings]


def test_missing_weight_or_height_is_rejected(session, person):
    with pytest.raises(TargetsUnavailable, match="Gewicht"):
        compute_targets(session, person, MONDAY)
    _seed(session, person)
    person.height_cm = None
    with pytest.raises(TargetsUnavailable, match="Körpergröße"):
        compute_targets(session, person, MONDAY)


def test_stale_weight_warns(session, person):
    _seed(session, person, end=MONDAY - timedelta(days=45))
    r = compute_targets(session, person, MONDAY)
    assert "stale_weight" in [w.code for w in r.warnings]


def test_formula_fallback_without_energy_data(session, person):
    _seed(session, person, energy=False)
    r = compute_targets(session, person, MONDAY)
    assert r.tdee.method == "formula"
    assert "tdee_formula" in [w.code for w in r.warnings]


def test_calibration_with_reported_intake(session, person):
    _seed(session, person, days=40, weight0=82.0, slope=-0.06)  # fällt ~0,42 kg/Woche
    _goal(session, person, rate_kg_per_week=0.5)
    _settings(session, person, reported_intake_kcal=2000)
    r = compute_targets(session, person, MONDAY)
    assert r.tdee.method == "calibrated"
    assert r.tdee.implied_kcal == pytest.approx(2000 + 0.06 * 7700, abs=60)
    assert r.tdee.tdee_kcal < r.tdee.device_kcal


def test_calibration_can_be_switched_off(session, person):
    _seed(session, person, weight0=82.0, slope=-0.06)
    _settings(session, person, reported_intake_kcal=2000, tdee_calibration=False)
    assert compute_targets(session, person, MONDAY).tdee.method == "device"


def test_training_plan_shifts_energy_between_days(session, person):
    _seed(session, person)
    _goal(session, person, rate_kg_per_week=0.5)
    session.add(TrainingPlanItem(person_id=person.id, weekday=0, session_type="Beine", intensity="hard"))
    session.add(
        TrainingPlanItem(person_id=person.id, weekday=2, session_type="Spaziergang", intensity="easy")
    )
    session.commit()
    hard = compute_targets(session, person, MONDAY).target.kcal
    rest = compute_targets(session, person, MONDAY + timedelta(days=1)).target.kcal  # Dienstag: rest
    assert hard > rest


def test_weekend_uses_weekend_shares(session, person):
    _seed(session, person, end=SATURDAY)
    _settings(
        session,
        person,
        slot_shares={"breakfast": 1.0},
        slot_shares_weekend={"breakfast": 0.4, "dinner": 0.6},
    )
    weekday = compute_targets(session, person, MONDAY)
    weekend = compute_targets(session, person, SATURDAY)
    assert set(s for s, v in weekday.shares.items() if v > 0) == {"breakfast"}
    assert weekday.slots["breakfast"].kcal == pytest.approx(weekday.target.kcal, abs=0.01)
    assert weekend.slots["dinner"].kcal == pytest.approx(0.6 * weekend.target.kcal, abs=1)


def test_shares_override_and_parse(session, person):
    _seed(session, person)
    r = compute_targets(session, person, MONDAY, shares=parse_shares("breakfast:1, lunch:1"))
    assert r.slots["breakfast"].kcal == pytest.approx(r.target.kcal / 2, abs=1)
    with pytest.raises(TargetsUnavailable):
        parse_shares("breakfast:abc")
    with pytest.raises(TargetsUnavailable):
        parse_shares("breakfast:0")


def test_weight_floor_tapers_rate(session, person):
    _seed(session, person, weight0=71.0, bf=9.0)
    _goal(session, person, rate_kg_per_week=0.5)
    _settings(session, person, weight_floor_kg=70)
    r = compute_targets(session, person, MONDAY)
    assert r.applied_rate_kg_per_week < 0.5
    assert "rate_tapered" in [w.code for w in r.warnings]


def test_floor_below_lean_mass_gives_hint_but_is_applied(session, person):
    _seed(session, person, weight0=71.0, bf=2.0)  # Magermasse ~69,6 kg
    _goal(session, person, rate_kg_per_week=0.5)
    _settings(session, person, weight_floor_kg=70)
    r = compute_targets(session, person, MONDAY)
    assert "implausible_weight_floor" in [w.code for w in r.warnings]
    assert r.applied_rate_kg_per_week < 0.5  # die Grenze gilt trotzdem


def test_single_meal_limit_warns(session, person):
    _seed(session, person)
    _settings(session, person, slot_shares={"breakfast": 1.0}, single_meal_max_kcal=1500)
    r = compute_targets(session, person, MONDAY)
    assert any(w.code == "meal_too_large" and "Frühstück" in w.message for w in r.warnings)
