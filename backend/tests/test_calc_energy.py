"""Tests für calc/energy.py (nur erfundene Daten)."""

from datetime import date, timedelta

import pytest

from app.calc.energy import (
    bmr_katch_mcardle,
    bmr_mifflin,
    calibrate_tdee,
    device_tdee,
    weight_trend,
)
from app.calc.types import DayEnergy, DeviceTdee, WeightTrend

START = date(2025, 3, 1)


def series(n: int, start_kg: float = 80.0, per_day: float = -0.05, noise: tuple[float, ...] = (0.0,)):
    """Gewichtsreihe mit exakt linearem Trend plus wiederkehrendem Rauschmuster."""
    return [(START + timedelta(days=i), start_kg + per_day * i + noise[i % len(noise)]) for i in range(n)]


def test_bmr_mifflin_man_and_woman():
    # 34 J., 190 cm, 78 kg
    assert bmr_mifflin(78, 190, 34, "m") == pytest.approx(1802.5)
    # 30 J., 174 cm, 78 kg
    assert bmr_mifflin(78, 174, 30, "f") == pytest.approx(1556.5)


def test_bmr_katch_mcardle():
    assert bmr_katch_mcardle(65.0) == pytest.approx(370 + 21.6 * 65)


def test_device_tdee_mean_and_coverage():
    daily = [DayEnergy(START + timedelta(days=i), 1800.0, 900.0 + 10 * i) for i in range(14)]
    est = device_tdee(daily, window_days=28)
    assert est.n_days == 14
    assert est.coverage == pytest.approx(14 / 28)
    assert est.kcal == pytest.approx(2700 + 10 * 6.5)


def test_device_tdee_only_complete_days_and_window():
    daily = [DayEnergy(START + timedelta(days=i), 1800.0, 700.0) for i in range(40)]  # 2500 kcal
    # letzte Tage unvollständig: das Fenster endet am letzten vollständigen Tag
    daily.append(DayEnergy(START + timedelta(days=40), None, 500.0))
    daily.append(DayEnergy(START + timedelta(days=41), 1800.0, None))
    est = device_tdee(daily, window_days=28)
    assert est.n_days == 28
    assert est.coverage == pytest.approx(1.0)
    assert est.kcal == pytest.approx(2500.0)


def test_device_tdee_ignores_old_days_outside_window():
    daily = [DayEnergy(START, 1800.0, 3000.0)]  # sehr alt
    daily += [DayEnergy(START + timedelta(days=60 + i), 1700.0, 800.0) for i in range(10)]
    est = device_tdee(daily, window_days=28)
    assert est.n_days == 10
    assert est.kcal == pytest.approx(2500.0)


def test_device_tdee_no_data():
    assert device_tdee([]).kcal is None
    only_partial = [DayEnergy(START, None, 500.0), DayEnergy(START + timedelta(days=1), 1500.0, None)]
    est = device_tdee(only_partial)
    assert est.kcal is None
    assert est.n_days == 0
    assert est.coverage == 0.0


def test_weight_trend_exact_line():
    trend = weight_trend(series(28))
    assert trend.slope_kg_per_day == pytest.approx(-0.05)
    assert trend.last_smoothed_kg == pytest.approx(80.0 - 0.05 * 27)
    assert trend.n_points == 28
    assert trend.span_days == 27


def test_weight_trend_noise_is_smoothed():
    noise = (0.3, -0.2, 0.1, -0.3, 0.2, 0.0, -0.1)
    trend = weight_trend(series(28, noise=noise))
    assert trend.slope_kg_per_day == pytest.approx(-0.05, abs=0.01)
    assert trend.last_smoothed_kg == pytest.approx(80.0 - 0.05 * 27, abs=0.3)


def test_weight_trend_single_outlier_barely_matters():
    clean = series(28)
    outlier = list(clean)
    outlier[14] = (outlier[14][0], outlier[14][1] + 6.0)  # eine Fehlmessung
    a = weight_trend(clean)
    b = weight_trend(outlier)
    assert b.slope_kg_per_day == pytest.approx(a.slope_kg_per_day, abs=0.003)
    assert b.last_smoothed_kg == pytest.approx(a.last_smoothed_kg, abs=0.1)


def test_weight_trend_window_is_capped():
    # alte Phase steigend, letzte 28 Tage fallend: nur die letzten 28 Tage zählen
    old = series(30, start_kg=70.0, per_day=0.1)
    new = [(START + timedelta(days=100 + i), 80.0 - 0.05 * i) for i in range(28)]
    trend = weight_trend(old + new, window_days=28)
    assert trend.n_points == 28
    assert trend.slope_kg_per_day == pytest.approx(-0.05)


def test_weight_trend_unsorted_input():
    pts = series(21)
    pts.reverse()
    assert weight_trend(pts).slope_kg_per_day == pytest.approx(-0.05)


def test_weight_trend_too_few_points_or_too_short():
    two = weight_trend(series(2))
    assert two.slope_kg_per_day is None
    assert two.n_points == 2
    short = weight_trend([(START + timedelta(days=i), 80.0) for i in range(6)])  # Spanne 5 Tage
    assert short.slope_kg_per_day is None
    assert short.last_smoothed_kg == pytest.approx(80.0)
    empty = weight_trend([])
    assert empty.slope_kg_per_day is None
    assert empty.last_smoothed_kg is None
    assert empty.n_points == 0


# --- Kalibrierung ---

DEVICE = DeviceTdee(kcal=2750.0, n_days=28, coverage=1.0)
# Verlust von 0,5 kg/Woche: 0,5 x 7700 / 7 = 550 kcal Defizit pro Tag
TREND = WeightTrend(slope_kg_per_day=-0.5 / 7, last_smoothed_kg=77.0, n_points=28, span_days=27)


def test_calibrate_blends_implied_and_device():
    est = calibrate_tdee(DEVICE, TREND, 2000.0)
    assert est.method == "calibrated"
    assert est.implied_kcal == pytest.approx(2550.0)
    assert est.confidence == pytest.approx(1.0)
    # w = min(0.7, 1.0) = 0.7
    assert est.tdee_kcal == pytest.approx(0.7 * 2550 + 0.3 * 2750)
    assert est.device_kcal == pytest.approx(2750.0)
    assert est.notes


def test_calibrate_clamps_to_device_range_and_notes_it():
    est = calibrate_tdee(DEVICE, TREND, 1000.0)  # implied 1550, Mischung 1910 < 0,75 x 2750
    assert est.method == "calibrated"
    assert est.tdee_kcal == pytest.approx(0.75 * 2750)
    assert any("begrenzt" in n for n in est.notes)
    high = calibrate_tdee(DEVICE, TREND, 5000.0)  # implied 5550
    assert high.tdee_kcal == pytest.approx(1.15 * 2750)


def test_calibrate_confidence_scales_with_data_and_lowers_weight():
    weak = WeightTrend(slope_kg_per_day=-0.5 / 7, last_smoothed_kg=77.0, n_points=6, span_days=9)
    est = calibrate_tdee(DeviceTdee(2750.0, 14, 0.5), weak, 2000.0)
    expected_conf = 0.4 * (6 / 20) + 0.3 * (9 / 21) + 0.3 * 0.5
    assert est.confidence == pytest.approx(expected_conf, abs=1e-3)
    assert est.tdee_kcal == pytest.approx(expected_conf * 2550 + (1 - expected_conf) * 2750, abs=0.1)
    assert 2550 < est.tdee_kcal < 2750


def test_calibrate_max_blend_limits_weight():
    est = calibrate_tdee(DEVICE, TREND, 2000.0, max_blend=0.5)
    assert est.tdee_kcal == pytest.approx(0.5 * 2550 + 0.5 * 2750)


def test_calibrate_too_few_points_uses_device():
    few = WeightTrend(slope_kg_per_day=-0.07, last_smoothed_kg=77.0, n_points=5, span_days=20)
    est = calibrate_tdee(DEVICE, few, 2000.0)
    assert est.method == "device"
    assert est.tdee_kcal == pytest.approx(2750.0)
    assert est.implied_kcal is None
    assert any("Gewichtsmessungen" in n for n in est.notes)


def test_calibrate_no_slope_or_no_intake_uses_device():
    no_slope = WeightTrend(None, 77.0, 10, 3)
    assert calibrate_tdee(DEVICE, no_slope, 2000.0).method == "device"
    est = calibrate_tdee(DEVICE, TREND, None)
    assert est.method == "device"
    assert est.tdee_kcal == pytest.approx(2750.0)
    assert est.notes


def test_calibrate_with_real_trend_and_outlier():
    noise = (0.2, -0.1, 0.0, 0.1, -0.2)
    pts = series(28, start_kg=78.0, per_day=-0.5 / 7, noise=noise)
    pts[10] = (pts[10][0], pts[10][1] + 5.0)  # Ausreißer
    est = calibrate_tdee(DEVICE, weight_trend(pts), 2200.0)
    assert est.method == "calibrated"
    assert est.implied_kcal == pytest.approx(2750.0, abs=100)
    assert 2600 < est.tdee_kcal < 2900


def test_calibrate_without_device_needs_formula():
    nothing = DeviceTdee(kcal=None, n_days=0, coverage=0.0)
    with pytest.raises(ValueError):
        calibrate_tdee(nothing, TREND, 2000.0)
    est = calibrate_tdee(nothing, TREND, 2000.0, formula_kcal=2600.0)
    assert est.method == "formula"
    assert est.tdee_kcal == pytest.approx(2600.0)
    assert est.device_kcal is None
    assert est.confidence == 0.0
    assert est.notes


def test_calibrate_custom_kcal_per_kg():
    est = calibrate_tdee(DEVICE, TREND, 2000.0, kcal_per_kg=7000.0)
    assert est.implied_kcal == pytest.approx(2000 + 500)
