"""Energiebedarf: Grundumsatz, Gesamtumsatz aus Gerätedaten, Gewichtstrend und Kalibrierung.

Reine Funktionen ohne Datenbank und ohne Zufall.
"""

from datetime import date
from statistics import median

from app.calc import defaults
from app.calc.types import DayEnergy, DeviceTdee, Sex, TdeeEstimate, WeightTrend

_MIN_TREND_POINTS = 3
_MIN_TREND_SPAN_DAYS = 7
_CONF_SATURATION_POINTS = 20
_CONF_SATURATION_SPAN_DAYS = 21


def bmr_mifflin(weight_kg: float, height_cm: float, age_years: float, sex: Sex) -> float:
    """Grundumsatz nach Mifflin-St-Jeor in kcal/Tag."""
    return 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age_years + (5.0 if sex == "m" else -161.0)


def bmr_katch_mcardle(lean_mass_kg: float) -> float:
    """Grundumsatz nach Katch-McArdle aus der Magermasse in kcal/Tag."""
    return 370.0 + 21.6 * lean_mass_kg


def device_tdee(daily: list[DayEnergy], window_days: int = defaults.TDEE_WINDOW_DAYS) -> DeviceTdee:
    """Mittlerer Gesamtumsatz (Ruhe + aktiv) aus Gerätedaten der letzten `window_days` Tage.

    Das Fenster endet am letzten Tag mit vollständigen Daten. Nur Tage mit Ruhe- UND
    Aktivenergie zählen. Ohne solche Tage ist `kcal` None.
    """
    complete = [d for d in daily if d.basal_kcal is not None and d.active_kcal is not None]
    if not complete or window_days <= 0:
        return DeviceTdee(kcal=None, n_days=0, coverage=0.0)
    last = max(d.day for d in complete)
    # pro Tag nur ein Wert (bei Dubletten gewinnt der zuletzt genannte)
    by_day = {d.day: d for d in complete if (last - d.day).days < window_days}
    totals = [(d.basal_kcal or 0.0) + (d.active_kcal or 0.0) for d in by_day.values()]
    n = len(totals)
    return DeviceTdee(kcal=sum(totals) / n, n_days=n, coverage=min(1.0, n / window_days))


def weight_trend(
    points: list[tuple[date, float]], window_days: int = defaults.TDEE_WINDOW_DAYS
) -> WeightTrend:
    """Robuster Gewichtstrend (Theil-Sen) über die letzten `window_days` Tage.

    Steigung in kg/Tag als Median aller paarweisen Steigungen, unempfindlich gegen einzelne
    Ausreißer. `last_smoothed_kg` ist der Wert der Trendgeraden am letzten Tag (Achsenabschnitt
    über den Median der Residuen). Unter 3 Punkten oder unter 7 Tagen Spanne ist die Steigung None;
    der geglättete Wert ist dann der Median der letzten (bis zu 3) Messungen.
    """
    if not points:
        return WeightTrend(slope_kg_per_day=None, last_smoothed_kg=None, n_points=0, span_days=0)
    ordered = sorted(points, key=lambda p: p[0])
    last_day = ordered[-1][0]
    window = [p for p in ordered if (last_day - p[0]).days < window_days]
    n = len(window)
    first_day = window[0][0]
    span = (last_day - first_day).days
    if n < _MIN_TREND_POINTS or span < _MIN_TREND_SPAN_DAYS:
        recent = [w for _, w in window[-3:]]
        return WeightTrend(
            slope_kg_per_day=None, last_smoothed_kg=float(median(recent)), n_points=n, span_days=span
        )
    xs = [(d - first_day).days for d, _ in window]
    ys = [w for _, w in window]
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(n) for j in range(i + 1, n) if xs[j] != xs[i]]
    if not slopes:  # alle Messungen am selben Tag (durch Spanne eigentlich ausgeschlossen)
        return WeightTrend(
            slope_kg_per_day=None, last_smoothed_kg=float(median(ys)), n_points=n, span_days=span
        )
    slope = float(median(slopes))
    intercept = float(median(y - slope * x for x, y in zip(xs, ys, strict=True)))
    return WeightTrend(
        slope_kg_per_day=slope,
        last_smoothed_kg=intercept + slope * xs[-1],
        n_points=n,
        span_days=span,
    )


def _confidence(trend: WeightTrend, coverage: float) -> float:
    """Vertrauen 0-1 aus Messpunkten, Spanne und Datenabdeckung der Gerätedaten."""
    f_n = min(1.0, trend.n_points / _CONF_SATURATION_POINTS)
    f_span = min(1.0, trend.span_days / _CONF_SATURATION_SPAN_DAYS)
    f_cov = max(0.0, min(1.0, coverage))
    return 0.4 * f_n + 0.3 * f_span + 0.3 * f_cov


def calibrate_tdee(
    device: DeviceTdee,
    trend: WeightTrend,
    reported_intake_kcal: float | None,
    *,
    kcal_per_kg: float = defaults.KCAL_PER_KG_BODY_MASS,
    min_points: int = defaults.TDEE_MIN_WEIGHT_POINTS,
    clamp: tuple[float, float] = defaults.TDEE_CLAMP,
    max_blend: float = defaults.TDEE_MAX_BLEND,
    formula_kcal: float | None = None,
) -> TdeeEstimate:
    """Gesamtumsatz aus Gerätewert, ergänzt um die Energiebilanz aus Gewichtstrend und Zufuhr.

    Energiebilanz: `implied = Zufuhr - Steigung * kcal_per_kg`. Ergebnis ist die Mischung
    `w * implied + (1 - w) * Gerät` mit `w = min(max_blend, Vertrauen)`, begrenzt auf
    `Gerät * clamp`. Ohne Zufuhr, mit zu wenig Messpunkten oder ohne Steigung gilt der Gerätewert
    (`method="device"`). Fehlt auch der Gerätewert, wird `formula_kcal` verwendet
    (`method="formula"`); ist es nicht gegeben, gibt es einen ValueError.
    Bei `method="device"` ist `confidence` die Datenabdeckung der Gerätedaten, bei "formula" 0.
    """
    notes: list[str] = []
    slope = trend.slope_kg_per_day
    can_imply = reported_intake_kcal is not None and slope is not None
    implied = reported_intake_kcal - slope * kcal_per_kg if can_imply else None  # type: ignore[operator]

    if device.kcal is None:
        if formula_kcal is None:
            raise ValueError("Kein Gerätewert und keine Formel für den Energiebedarf vorhanden.")
        notes.append("Keine Geräte-Energiedaten vorhanden: Schätzung aus Formel (Grundumsatz mal Aktivität).")
        return TdeeEstimate(
            tdee_kcal=round(formula_kcal, 1),
            device_kcal=None,
            implied_kcal=None if implied is None else round(implied, 1),
            confidence=0.0,
            method="formula",
            notes=notes,
        )

    def device_only(reason: str) -> TdeeEstimate:
        notes.append(reason)
        return TdeeEstimate(
            tdee_kcal=round(device.kcal, 1),  # type: ignore[arg-type]
            device_kcal=round(device.kcal, 1),  # type: ignore[arg-type]
            implied_kcal=None,
            confidence=round(max(0.0, min(1.0, device.coverage)), 3),
            method="device",
            notes=notes,
        )

    if reported_intake_kcal is None:
        return device_only("Keine Angabe zur Kalorienzufuhr: Es gilt der Wert aus den Geräte-Energiedaten.")
    if slope is None or trend.n_points < min_points:
        return device_only(
            f"Zu wenige Gewichtsmessungen für eine Kalibrierung ({trend.n_points} von mindestens "
            f"{min_points} über genug Zeit): Es gilt der Wert aus den Geräte-Energiedaten."
        )

    assert implied is not None
    confidence = _confidence(trend, device.coverage)
    weight = min(max_blend, confidence)
    blended = weight * implied + (1.0 - weight) * device.kcal
    lo, hi = device.kcal * clamp[0], device.kcal * clamp[1]
    result = min(max(blended, lo), hi)
    notes.append(
        f"Energiebilanz aus Gewichtstrend und Zufuhr ergibt {implied:.0f} kcal; "
        f"Mischung mit dem Gerätewert zu {weight * 100:.0f} % (Vertrauen {confidence * 100:.0f} %)."
    )
    if result != blended:
        notes.append(
            f"Das Ergebnis wurde auf {clamp[0] * 100:.0f} bis {clamp[1] * 100:.0f} % des Gerätewerts "
            f"begrenzt ({blended:.0f} kcal wären es ohne Begrenzung)."
        )
    return TdeeEstimate(
        tdee_kcal=round(result, 1),
        device_kcal=round(device.kcal, 1),
        implied_kcal=round(implied, 1),
        confidence=round(confidence, 3),
        method="calibrated",
        notes=notes,
    )
