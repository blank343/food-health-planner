"""Spike b: Importer für Health Auto Export (CSV/ZIP) und Apple-Health-XML.

Beide liefern dasselbe Zielschema:
  daily:    {date, weight_kg, body_fat_pct, lean_mass_kg, active_kcal, basal_kcal,
             steps, resting_hr, hrv_ms, sleep_h}
  workouts: {type, start, duration_min, active_kcal, avg_hr, max_hr, distance_km}

Einheiten: kcal (HAE liefert kJ, Umrechnung / 4.184), Körperfett in Prozent.
Streaming, damit auch 1,3-GB-XML in konstantem Speicher läuft.
"""
from __future__ import annotations

import csv
import io
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import xml.etree.ElementTree as ET

KJ_PER_KCAL = 4.184


# ------------------------------------------------------------------ Bereinigung
def clean_weights(series: list[tuple[str, float]], lo: float = 35.0, hi: float = 250.0):
    """Entfernt (1) unplausible Werte, (2) wiederholte Platzhalter, (3) Ausreißer.

    Platzhalter: derselbe Wert mit exakt zwei Nachkommastellen-Rundung, der in der
    Serie auffällig oft wiederholt wird (>= 5 % der Messungen und >= 4 Mal).
    Ausreißer: Abweichung > 6 MAD vom gleitenden Median (Fenster 15 Messungen).
    """
    vals = [(d, w) for d, w in series if lo <= w <= hi]
    cnt = Counter(round(w, 2) for _, w in vals)
    thresh = max(4, int(0.05 * len(vals)))
    placeholders = {v for v, c in cnt.items() if c >= thresh}
    after_ph = [(d, w) for d, w in vals if round(w, 2) not in placeholders]
    kept, dropped_outliers = [], []
    for i, (d, w) in enumerate(after_ph):
        win = [x for _, x in after_ph[max(0, i - 7): i + 8]]
        med = statistics.median(win)
        mad = statistics.median([abs(x - med) for x in win]) or 0.5
        if abs(w - med) > 6 * 1.4826 * mad and abs(w - med) > 3.0:
            dropped_outliers.append((d, w))
        else:
            kept.append((d, w))
    return kept, {"placeholders": sorted(placeholders), "outliers": dropped_outliers,
                  "raw": len(series), "kept": len(kept)}


# ------------------------------------------------------------------ Apple-Health-XML
def import_apple_health_xml(path: Path) -> dict:
    wanted_last = {  # Typ -> Feldname (letzter Wert des Tages)
        "BodyMass": "weight_kg", "BodyFatPercentage": "body_fat_pct",
        "LeanBodyMass": "lean_mass_kg", "RestingHeartRate": "resting_hr",
        "HeartRateVariabilitySDNN": "hrv_ms",
    }
    wanted_sum = {"ActiveEnergyBurned": "active_kcal", "BasalEnergyBurned": "basal_kcal",
                  "StepCount": "steps"}
    last: dict[str, dict[str, float]] = defaultdict(dict)
    hrv_acc: dict[str, list[float]] = defaultdict(list)
    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    weights: list[tuple[str, float]] = []
    sleep_s: dict[str, float] = defaultdict(float)
    workouts = []
    profile = {}
    prefix = "HKQuantityTypeIdentifier"

    for _ev, el in ET.iterparse(str(path), events=("end",)):
        tag = el.tag
        if tag == "Record":
            t = el.get("type", "")
            short = t.replace(prefix, "")
            day = (el.get("startDate") or "")[:10]
            try:
                if short in wanted_sum:
                    sums[day][wanted_sum[short]] += float(el.get("value"))
                elif short == "HeartRateVariabilitySDNN":
                    hrv_acc[day].append(float(el.get("value")))
                elif short in wanted_last:
                    v = float(el.get("value"))
                    if short == "BodyMass":
                        weights.append((day, v))
                    elif short == "BodyFatPercentage":
                        last[day]["body_fat_pct"] = v * 100 if v <= 1.0 else v
                    else:
                        last[day][wanted_last[short]] = v
                elif t == "HKCategoryTypeIdentifierSleepAnalysis" and "Asleep" in (el.get("value") or ""):
                    # Dauer in Sekunden aus Start/Ende, dem Tag des Endes zugeordnet
                    from datetime import datetime
                    fmt = "%Y-%m-%d %H:%M:%S %z"
                    s = datetime.strptime(el.get("startDate"), fmt)
                    e = datetime.strptime(el.get("endDate"), fmt)
                    sleep_s[(el.get("endDate") or "")[:10]] += (e - s).total_seconds()
            except (TypeError, ValueError):
                pass
            el.clear()
        elif tag == "Workout":
            try:
                dur = float(el.get("duration") or 0)
                if el.get("durationUnit") == "sec":
                    dur /= 60
            except ValueError:
                dur = 0.0
            workouts.append({
                "type": (el.get("workoutActivityType") or "").replace("HKWorkoutActivityType", ""),
                "start": (el.get("startDate") or "")[:16],
                "duration_min": round(dur, 1),
                "active_kcal": _f(el.get("totalEnergyBurned")),
                "distance_km": _f(el.get("totalDistance")),
            })
            el.clear()
        elif tag == "Me":
            profile = {k.replace("HKCharacteristicTypeIdentifier", ""): v for k, v in el.attrib.items()}
            el.clear()

    kept_w, wreport = clean_weights(weights)
    wmap = {}
    for d, w in kept_w:
        wmap[d] = w  # letzter bereinigter Wert des Tages
    days = sorted(set(last) | set(sums) | set(wmap) | set(hrv_acc))
    daily = []
    for d in days:
        row = {"date": d, "weight_kg": wmap.get(d)}
        row.update(last.get(d, {}))
        row.update({k: round(v, 1) for k, v in sums.get(d, {}).items()})
        if d in hrv_acc:
            row["hrv_ms"] = round(statistics.mean(hrv_acc[d]), 1)
        if d in sleep_s:
            row["sleep_h"] = round(sleep_s[d] / 3600, 2)
        daily.append(row)
    return {"source": "apple_health_xml", "profile": profile, "daily": daily,
            "workouts": workouts, "weight_report": wreport}


def _f(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ Health Auto Export
def _num(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def import_hae_zip(path: Path) -> dict:
    daily, workouts = [], []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        for name in names:
            base = Path(name).name
            if base.startswith("HealthAutoExport-") and base.endswith(".csv"):
                daily += _hae_daily(zf.read(name).decode("utf-8-sig"))
            elif base.startswith("Workouts-") and base.endswith(".csv"):
                workouts += _hae_workouts(zf.read(name).decode("utf-8-sig"))
    weights = [(r["date"], r["weight_kg"]) for r in daily if r.get("weight_kg")]
    kept, wreport = clean_weights(weights)
    keep = {d for d, _ in kept}
    for r in daily:
        if r.get("weight_kg") and r["date"] not in keep:
            r["weight_kg"] = None
    return {"source": "hae_zip", "daily": daily, "workouts": workouts, "weight_report": wreport}


def _hae_daily(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        d = (r.get("Date/Time") or "")[:10]
        if not d:
            continue
        ak, bk = _num(r.get("Active Energy (kJ)")), _num(r.get("Resting Energy (kJ)"))
        row = {
            "date": d,
            "weight_kg": _num(r.get("Weight (kg)")),
            "body_fat_pct": _num(r.get("Body Fat Percentage (%)")),
            "lean_mass_kg": _num(r.get("Lean Body Mass (kg)")),
            "active_kcal": round(ak / KJ_PER_KCAL, 1) if ak is not None else None,
            "basal_kcal": round(bk / KJ_PER_KCAL, 1) if bk is not None else None,
            "steps": _num(r.get("Step Count (count)")),
            "resting_hr": _num(r.get("Resting Heart Rate (count/min)")),
            "hrv_ms": _num(r.get("Heart Rate Variability (ms)")),
            "sleep_h": _num(r.get("Sleep Analysis [Asleep] (hr)")) or _num(r.get("Sleep Analysis [Total] (hr)")),
        }
        out.append({k: v for k, v in row.items() if v is not None})
    return out


def _hae_workouts(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        h, m, s = (r.get("Duration") or "0:0:0").split(":")
        ak = _num(r.get("Active Energy (kJ)"))
        out.append({
            "type": r.get("Workout Type"),
            "start": r.get("Start"),
            "duration_min": round(int(h) * 60 + int(m) + int(s) / 60, 1),
            "active_kcal": round(ak / KJ_PER_KCAL, 1) if ak is not None else None,
            "avg_hr": _num(r.get("Avg. Heart Rate (count/min)")),
            "max_hr": _num(r.get("Max. Heart Rate (count/min)")),
            "distance_km": _num(r.get("Distance (km)")),
        })
    return out
