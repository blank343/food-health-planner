"""Importer für Apple Health `export.xml` (Streaming, konstanter Speicher).

Die Datei kann über 1 GB groß sein. Sie wird deshalb mit `iterparse` gelesen; fertige
Elemente und regelmäßig auch das Wurzelelement werden geleert (`root.clear()`), damit der
Speicher unabhängig von der Dateigröße klein bleibt. Es werden keine externen Entities
aufgelöst (die DTD im Kopf der Datei wird von expat nur gelesen). `WorkoutRoute` und
`FileReference` (GPX-Dateien) werden ignoriert, Routendateien nie geöffnet.

Tageswerte (Tag = Datum von `startDate`, die Zeitzone wird ignoriert, die Uhrzeit gilt als
Ortszeit):

- Letzter Wert des Tages: Gewicht (danach `cleaning.clean_weights`), Körperfett
  (Bruchteil 0–1 wird zu Prozent; Werte > 1 gelten schon als Prozent), fettfreie Masse,
  Ruhepuls.
- Tagesmittel: HRV (SDNN).
- Tagessummen: Schritte, aktive und Grundumsatz-Energie. **Doppelzählung:** Apple Health
  speichert dieselben Schritte/Energie oft von mehreren Quellen (iPhone und Apple Watch,
  Attribut `sourceName`). Deshalb wird die Summe je Quelle gebildet und pro Tag und Typ die
  Quelle mit der größten Summe genommen (deterministisch, einfach). Summen werden nie
  über Quellen addiert.
- Schlaf: Records mit "Asleep" im Wert, dem Tag des Endes zugeordnet. Überlappende Intervalle
  (mehrere Quellen, Schlafphasen) werden je Tag vereinigt, nichts wird doppelt gezählt.
  Einschränkung: eine Nacht wird komplett dem Endtag zugerechnet, auch wenn sie vor
  Mitternacht beginnt.

Einheiten werden nach kcal, kg, cm, km normalisiert. Defekte Werte werden übersprungen und
in `stats["skipped_malformed"]` gezählt.
"""

import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from app.importers import cleaning
from app.importers.types import DailyRow, HealthImport, Progress, WorkoutRow

SOURCE = "apple_health_xml"

_Q = "HKQuantityTypeIdentifier"
_SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
_WORKOUT_PREFIX = "HKWorkoutActivityType"

KJ_PER_KCAL = 4.184
KM_PER_MILE = 1.609344
KG_PER_LB = 0.45359237

# Record-Typ -> (Art, Feld)
_LAST = "last"  # letzter Wert des Tages
_MEAN = "mean"  # Tagesmittel
_SUM = "sum"  # Tagessumme je Quelle, größte Quelle gewinnt
_RECORD_TYPES: dict[str, tuple[str, str]] = {
    _Q + "BodyMass": (_LAST, "weight_kg"),
    _Q + "BodyFatPercentage": (_LAST, "body_fat_pct"),
    _Q + "LeanBodyMass": (_LAST, "lean_mass_kg"),
    _Q + "RestingHeartRate": (_LAST, "resting_hr"),
    _Q + "Height": (_LAST, "height_cm"),
    _Q + "HeartRateVariabilitySDNN": (_MEAN, "hrv_ms"),
    _Q + "StepCount": (_SUM, "steps"),
    _Q + "ActiveEnergyBurned": (_SUM, "active_kcal"),
    _Q + "BasalEnergyBurned": (_SUM, "basal_kcal"),
}

_ROOT_CLEAR_EVERY = 2000  # fertige Top-Level-Elemente zwischen zwei root.clear()
_PROGRESS_EVERY = 20000  # Elemente zwischen zwei Fortschrittsprüfungen


def _to_kcal(value: float, unit: str | None) -> float:
    if unit and unit.lower() == "kj":
        return value / KJ_PER_KCAL
    return value


def _to_kg(value: float, unit: str | None) -> float:
    u = (unit or "").lower()
    if u == "lb":
        return value * KG_PER_LB
    if u == "g":
        return value / 1000
    return value


def _to_cm(value: float, unit: str | None) -> float:
    u = (unit or "").lower()
    if u == "m":
        return value * 100
    if u == "in":
        return value * 2.54
    if u == "ft":
        return value * 30.48
    return value


def _to_km(value: float, unit: str | None) -> float:
    u = (unit or "").lower()
    if u == "mi":
        return value * KM_PER_MILE
    if u == "m":
        return value / 1000
    if u == "yd":
        return value * 0.0009144
    return value


def _to_minutes(value: float, unit: str | None) -> float:
    u = (unit or "min").lower()
    if u in ("sec", "s"):
        return value / 60
    if u in ("hr", "h"):
        return value * 60
    return value


def _convert(field: str, value: float, unit: str | None) -> float:
    if field in ("active_kcal", "basal_kcal"):
        return _to_kcal(value, unit)
    if field in ("weight_kg", "lean_mass_kg"):
        return _to_kg(value, unit)
    if field == "height_cm":
        return _to_cm(value, unit)
    if field == "body_fat_pct":
        return value * 100 if value <= 1.0 else value
    return value


def _parse_ts(text: str | None) -> datetime:
    """`2026-10-04 06:12:00 +0200` -> naive Ortszeit (Zeitzonen-Suffix wird ignoriert)."""
    if not text:
        raise ValueError("leer")
    return datetime.fromisoformat(text[:19])


def _merge_hours(intervals: list[tuple[datetime, datetime]]) -> float:
    """Gesamtdauer der Vereinigung der Intervalle in Stunden."""
    total = 0.0
    cur_s: datetime | None = None
    cur_e: datetime | None = None
    for s, e in sorted(intervals):
        if cur_s is None or cur_e is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            if e > cur_e:
                cur_e = e
        else:
            total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
    if cur_s is not None and cur_e is not None:
        total += (cur_e - cur_s).total_seconds()
    return total / 3600


def _opt_float(text: str | None) -> float | None:
    if text is None or text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


class _Collector:
    """Sammelt Werte während des Streamings (Größe wächst nur mit der Zahl der Tage)."""

    def __init__(self) -> None:
        self._day_cache: dict[str, date | None] = {}
        # Feld -> Tag -> (startDate, Wert) des jüngsten Eintrags
        self.last: dict[str, dict[date, tuple[str, float]]] = defaultdict(dict)
        # Feld -> Tag -> [Summe, Anzahl]
        self.mean: dict[str, dict[date, list[float]]] = defaultdict(dict)
        # Feld -> (Tag, Quelle) -> Summe
        self.sums: dict[str, dict[tuple[date, str], float]] = defaultdict(lambda: defaultdict(float))
        self.weights: list[tuple[str, date, float]] = []  # (startDate, Tag, kg)
        self.sleep: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
        self.workouts: list[WorkoutRow] = []
        self.profile: dict[str, object] = {}
        self.records_seen = 0
        self.records_used = 0
        self.skipped = 0

    def day(self, text: str | None) -> date | None:
        """Datum aus den ersten 10 Zeichen eines Zeitstempels (mit Cache), None bei Fehler."""
        key = (text or "")[:10]
        try:
            return self._day_cache[key]
        except KeyError:
            try:
                d: date | None = date.fromisoformat(key)
            except ValueError:
                d = None
            self._day_cache[key] = d
            return d

    # ---- Record
    def record(self, el: ET.Element) -> None:
        self.records_seen += 1
        rtype = el.get("type")
        if rtype is None:
            return
        spec = _RECORD_TYPES.get(rtype)
        if spec is not None:
            self._quantity(el, spec)
        elif rtype == _SLEEP_TYPE:
            self._sleep(el)

    def _quantity(self, el: ET.Element, spec: tuple[str, str]) -> None:
        kind, field = spec
        start = el.get("startDate")
        day = self.day(start)
        try:
            if day is None or start is None:
                raise ValueError("Datum")
            value = _convert(field, float(el.get("value", "")), el.get("unit"))
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("Zahl")
        except ValueError:
            self.skipped += 1
            return
        self.records_used += 1
        if kind == _SUM:
            self.sums[field][(day, el.get("sourceName") or "")] += value
        elif kind == _MEAN:
            acc = self.mean[field].setdefault(day, [0.0, 0.0])
            acc[0] += value
            acc[1] += 1
        else:
            if field == "weight_kg":
                self.weights.append((start, day, value))
                return
            prev = self.last[field].get(day)
            if prev is None or start >= prev[0]:
                self.last[field][day] = (start, value)

    def _sleep(self, el: ET.Element) -> None:
        if "Asleep" not in (el.get("value") or ""):
            return
        try:
            start = _parse_ts(el.get("startDate"))
            end = _parse_ts(el.get("endDate"))
            if end <= start:
                raise ValueError("Dauer")
        except ValueError:
            self.skipped += 1
            return
        self.records_used += 1
        self.sleep[end.date()].append((start, end))

    # ---- Me
    def me(self, el: ET.Element) -> None:
        birth = el.get("HKCharacteristicTypeIdentifierDateOfBirth")
        if birth:
            try:
                self.profile["birth_date"] = date.fromisoformat(birth[:10])
            except ValueError:
                self.skipped += 1
        sex = el.get("HKCharacteristicTypeIdentifierBiologicalSex") or ""
        if sex.endswith("Female"):
            self.profile["sex"] = "f"
        elif sex.endswith("Male"):
            self.profile["sex"] = "m"

    # ---- Workout
    def workout(self, el: ET.Element) -> None:
        try:
            start = _parse_ts(el.get("startDate"))
            duration = _to_minutes(float(el.get("duration") or 0), el.get("durationUnit"))
        except ValueError:
            self.skipped += 1
            return
        wtype = (el.get("workoutActivityType") or "").removeprefix(_WORKOUT_PREFIX)
        energy = _opt_float(el.get("totalEnergyBurned"))
        if energy is not None:
            energy = _to_kcal(energy, el.get("totalEnergyBurnedUnit"))
        distance = _opt_float(el.get("totalDistance"))
        if distance is not None:
            distance = _to_km(distance, el.get("totalDistanceUnit"))
        avg_hr: float | None = None
        max_hr: float | None = None
        for stat in el.findall("WorkoutStatistics"):
            stype = stat.get("type") or ""
            if stype == _Q + "HeartRate":
                avg_hr = _opt_float(stat.get("average"))
                max_hr = _opt_float(stat.get("maximum"))
            elif stype == _Q + "ActiveEnergyBurned" and energy is None:
                s = _opt_float(stat.get("sum"))
                if s is not None:
                    energy = _to_kcal(s, stat.get("unit"))
            elif stype.startswith(_Q + "Distance") and distance is None:
                s = _opt_float(stat.get("sum"))
                if s is not None:
                    distance = _to_km(s, stat.get("unit"))
        self.records_used += 1
        self.workouts.append(
            WorkoutRow(
                type=wtype,
                start=start,
                duration_min=round(duration, 1),
                active_kcal=None if energy is None else round(energy, 1),
                avg_hr=None if avg_hr is None else round(avg_hr, 1),
                max_hr=None if max_hr is None else round(max_hr, 1),
                distance_km=None if distance is None else round(distance, 3),
            )
        )


def _best_source_sums(sums: dict[tuple[date, str], float]) -> dict[date, float]:
    """Je Tag die Summe der Quelle mit dem größten Wert (bei Gleichstand der kleinere Name)."""
    best: dict[date, tuple[float, str]] = {}
    for (day, source), total in sums.items():
        cur = best.get(day)
        if cur is None or total > cur[0] or (total == cur[0] and source < cur[1]):
            best[day] = (total, source)
    return {day: total for day, (total, _) in best.items()}


def import_apple_health(path: Path, progress: Progress | None = None) -> HealthImport:
    """Liest eine Apple-Health-`export.xml` im Streaming und liefert Tages- und Workoutdaten."""
    t0 = time.perf_counter()
    path = Path(path)
    total_bytes = max(path.stat().st_size, 1)
    col = _Collector()
    if progress:
        progress(0.0, "Apple Health: Lese Export")

    last_fraction = 0.0
    since_check = 0
    since_clear = 0
    root: ET.Element | None = None
    with path.open("rb") as fh:
        for event, el in ET.iterparse(fh, events=("start", "end")):
            if event == "start":
                if root is None:
                    root = el
                continue
            tag = el.tag
            if tag == "Record":
                col.record(el)
            elif tag == "Workout":
                col.workout(el)
            elif tag == "Me":
                col.me(el)
            else:
                continue
            el.clear()
            since_clear += 1
            if since_clear >= _ROOT_CLEAR_EVERY and root is not None:
                root.clear()
                since_clear = 0
            if progress:
                since_check += 1
                if since_check >= _PROGRESS_EVERY:
                    since_check = 0
                    fraction = min(fh.tell() / total_bytes, 0.99)
                    if fraction - last_fraction >= 0.01:
                        last_fraction = fraction
                        progress(fraction, f"Apple Health: {col.records_seen:,} Einträge gelesen")

    if progress:
        progress(0.99, "Apple Health: Werte zusammenführen")

    # Gewicht: alle Messungen chronologisch bereinigen, danach letzter Wert je Tag.
    col.weights.sort(key=lambda w: w[0])
    kept, weight_report = cleaning.clean_weights([(d, w) for _, d, w in col.weights])
    weight_by_day: dict[date, float] = {}
    for d, w in kept:
        weight_by_day[d] = w

    last_fields = {f: {d: v for d, (_, v) in per_day.items()} for f, per_day in col.last.items()}
    mean_fields = {f: {d: s / n for d, (s, n) in per_day.items()} for f, per_day in col.mean.items()}
    summed = {f: _best_source_sums(s) for f, s in col.sums.items()}
    sleep_hours = {d: _merge_hours(iv) for d, iv in col.sleep.items()}

    days: set[date] = set(weight_by_day) | set(sleep_hours)
    for table in (*last_fields.items(), *mean_fields.items(), *summed.items()):
        if table[0] != "height_cm":
            days |= set(table[1])

    def get(field: str, day: date) -> float | None:
        for table in (last_fields, mean_fields, summed):
            if field in table and day in table[field]:
                return table[field][day]
        return None

    daily: list[DailyRow] = []
    for day in sorted(days):
        row = DailyRow(day=day, weight_kg=weight_by_day.get(day))
        for field in ("body_fat_pct", "lean_mass_kg", "resting_hr", "hrv_ms"):
            v = get(field, day)
            if v is not None:
                setattr(row, field, round(v, 2))
        for field in ("active_kcal", "basal_kcal", "steps"):
            v = get(field, day)
            if v is not None:
                setattr(row, field, round(v, 1))
        if day in sleep_hours:
            row.sleep_h = round(sleep_hours[day], 2)
        daily.append(row)

    profile = dict(col.profile)
    heights = last_fields.get("height_cm")
    if heights:
        height = heights[max(heights)]
        if 100 <= height <= 250:
            profile["height_cm"] = round(height, 1)

    seconds = time.perf_counter() - t0
    stats: dict[str, object] = {
        "records_seen": col.records_seen,
        "records_used": col.records_used,
        "daily_rows": len(daily),
        "workout_rows": len(col.workouts),
        "date_from": daily[0].day.isoformat() if daily else None,
        "date_to": daily[-1].day.isoformat() if daily else None,
        "seconds": round(seconds, 2),
        "skipped_malformed": col.skipped,
    }
    if progress:
        progress(1.0, "Apple Health: fertig")
    return HealthImport(
        source=SOURCE,
        daily=daily,
        workouts=col.workouts,
        profile=profile,
        weight_report=weight_report,
        stats=stats,
    )
